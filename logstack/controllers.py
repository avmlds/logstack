from itertools import groupby
from typing import Literal

import numpy as np
from database_models import Flamechart
from sqlalchemy import and_, case, func
from sqlalchemy.orm import aliased


def _apply_prefix_filter(query, prefix):
    """Apply SQL LIKE prefix filtering, normalizing trailing slashes."""
    if prefix:
        p = prefix.rstrip("/")
        query = query.filter(Flamechart.prefix.like(f"{p}%"))
    return query


def list_upload_times(session, prefix: str = None, page: int = 1, page_size: int = 50):
    """List distinct upload timestamps (created_at), optionally filtered by prefix prefix,
    with pagination.
    """
    q = session.query(Flamechart).distinct().order_by(Flamechart.created_at)
    if prefix:
        q = q.filter(Flamechart.prefix.startswith(prefix))

    offset = (page - 1) * page_size
    return [
        {
            "id": row.id,
            "upload_uuid": str(row.upload_uuid),
            "filename": row.filename,
            "prefix": row.prefix,
            "error_count": row.error_count,
            "from_date": row.from_date,
            "to_date": row.to_date,
            "created_at": row.created_at,
        }
        for row in q.offset(offset).limit(page_size).all()
    ]


def get_upload_diffs(
    session,
    prefix: str = None,
    include_upload_uuids: list[str] = None,
    page: int = 1,
    page_size: int = 50,
    order_by: Literal["improvements", "degradations"] = "improvements",
    descending: bool = True,
):
    """Get per-upload improvements and degradations for specified uploads.
    Uses a subquery to compute per-row diffs before aggregation.
    """
    # 1) Subquery: compute diff per row
    prev_ec = func.lag(Flamechart.error_count).over(
        partition_by=Flamechart.prefix,
        order_by=Flamechart.created_at,
    )
    diff_expr = (Flamechart.error_count - prev_ec).label("diff")

    subq = session.query(
        Flamechart.prefix,
        Flamechart.created_at.label("upload_time"),
        Flamechart.upload_uuid,
        Flamechart.prefix,
        diff_expr,
    ).subquery()

    # 2) Outer query: aggregate improvements/degradations
    improvements = func.sum(case((subq.c.diff < 0, 1), else_=0)).label("improvements")
    degradations = func.sum(case((subq.c.diff > 0, 1), else_=0)).label("degradations")

    q = session.query(subq.c.prefix, improvements, degradations)

    if prefix:
        # apply prefix filter on prefix in subquery
        q = q.join(subq, Flamechart.prefix == subq.c.prefix)
        q = _apply_prefix_filter(q, prefix)

    if include_upload_uuids:
        q = q.filter(subq.c.upload_uuid.in_(include_upload_uuids))

    q = q.group_by(subq.c.prefix)
    offset = (page - 1) * page_size
    result = [
        {
            "prefix": row[0],
            "improvements": row[1],
            "degradations": row[2],
        }
        for row in q.offset(offset).limit(page_size).all()
    ]
    return sorted(result, key=lambda row: row[order_by], reverse=descending)


def compute_trends(
    session,
    prefix: str = None,
    page: int = 1,
    page_size: int = 100,
    descending: bool = True,
):
    """Compute linear regression slope of error_count vs. time (days) for each prefix.
    Returns list of (prefix, slope) sorted by slope descending.
    Pagination supported.
    """
    # fetch raw series
    q = session.query(
        Flamechart.prefix,
        Flamechart.created_at,
        Flamechart.error_count,
    ).order_by(Flamechart.prefix, Flamechart.created_at)
    if prefix:
        q = q.filter(Flamechart.prefix.startswith(prefix))
    rows = q.all()

    trends = []
    for prefix, group in groupby(rows, key=lambda r: r.prefix):
        recs = list(group)
        if len(recs) < 2:
            continue
        base = recs[0].created_at
        times = np.array(
            [(r.created_at - base).total_seconds() / 86400.0 for r in recs],
        )
        errors = np.array([r.error_count for r in recs])
        slope, _ = np.polyfit(times, errors, 1)
        trends.append((prefix, round(slope, 3)))

    # sort by slope
    trends.sort(key=lambda x: x[1], reverse=descending)

    # apply pagination
    start = (page - 1) * page_size
    end = start + page_size
    return [
        {
            "prefix": trend[0],
            "slope": trend[1],
        }
        for trend in trends[start:end]
    ]


def get_basic_stats(
    session,
    prefix: str = None,
    order_by: str = "mean",
    descending: bool = True,
    page: int = 1,
    page_size: int = 50,
):
    # 1) Define each aggregate and label it
    runs_col = func.count(Flamechart.error_count).label("runs")
    mean_col = func.avg(Flamechart.error_count).label("mean")
    median_col = (
        func.percentile_cont(0.5).within_group(Flamechart.error_count).label("median")
    )
    std_col = func.stddev_pop(Flamechart.error_count).label("stddev")
    min_col = func.min(Flamechart.error_count).label("min")
    max_col = func.max(Flamechart.error_count).label("max")

    # 2) Build the base query
    q = session.query(
        Flamechart.prefix,
        runs_col,
        mean_col,
        median_col,
        std_col,
        min_col,
        max_col,
    ).group_by(Flamechart.prefix)

    # 3) Optional prefix filter
    if prefix:
        p = prefix.rstrip("/")
        q = q.filter(Flamechart.prefix.like(f"{p}%"))

    # 4) Map the user’s order_by key to the actual column
    ordering_map = {
        "count": runs_col,
        "mean": mean_col,
        "median": median_col,
        "stddev": std_col,
        "min": min_col,
        "max": max_col,
    }
    if order_by not in ordering_map:
        raise ValueError(f"order_by must be one of {list(ordering_map)}")

    order_col = ordering_map[order_by]
    q = q.order_by(order_col.desc() if descending else order_col.asc())

    # 5) Pagination
    offset = (page - 1) * page_size
    return [
        {
            "prefix": row[0],
            "count": row[1],
            "mean": row[2],
            "median": row[3],
            "stddev": row[4],
            "min": row[5],
            "max": row[6],
        }
        for row in q.offset(offset).limit(page_size).all()
    ]


def compare_uploads(
    session,
    upload_1_uuid: str,
    upload_2_uuid: str,
    prefix: str = None,
    page: int = 1,
    page_size: int = 50,
):
    """Compare two specific uploads (by exact created_at timestamps).
    Returns per-prefix error counts and delta between date2 - date1.
    """
    f1 = aliased(Flamechart)
    f2 = aliased(Flamechart)

    join_cond = and_(
        f1.prefix == f2.prefix,
        f1.upload_uuid == upload_1_uuid,
        f2.upload_uuid == upload_2_uuid,
    )

    q = session.query(
        f1.prefix,
        f1.error_count.label("error_count_1"),
        f2.error_count.label("error_count_2"),
        (f2.error_count - f1.error_count).label("delta"),
    ).join(f2, join_cond)

    if prefix:
        q = q.filter(f1.prefix.startswith(prefix))

    # sort by absolute delta desc
    q = q.order_by(func.abs(f2.error_count - f1.error_count).desc())

    offset = (page - 1) * page_size
    return [
        {
            "prefix": row[0],
            "error_count_1": row[1],
            "error_count_2": row[2],
            "delta": row[3],
        }
        for row in q.offset(offset).limit(page_size).all()
    ]
