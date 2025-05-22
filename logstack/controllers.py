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


def list_upload_times(
    session, prefix: str | None = None, page: int = 1, page_size: int = 50
):
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


def get_all_uploads(
    session,
    page: int = 1,
    page_size: int = 50,
    order_by: Literal[
        "upload_uuid",
        "filename",
        "created_at",
        "errors_total",
    ] = "created_at",
    descending: bool = True,
):
    order_by_map = {
        "upload_uuid": Flamechart.upload_uuid,
        "filename": Flamechart.filename,
        "created_at": Flamechart.created_at,
        "errors_total": func.sum(Flamechart.error_count).label("errors_total"),
    }
    order_by_column = order_by_map[order_by]

    query = (
        session.query(
            Flamechart.upload_uuid,
            Flamechart.filename,
            Flamechart.created_at,
            func.sum(Flamechart.error_count).label("errors_total"),
        )
        .group_by(
            Flamechart.upload_uuid,
            Flamechart.filename,
            Flamechart.created_at,
        )
        .order_by(order_by_column.desc() if descending else order_by_column.asc())
    )
    offset = (page - 1) * page_size
    return [
        {
            "upload_uuid": row.upload_uuid,
            "filename": row.filename,
            "created_at": row.created_at,
            "errors_total": row.errors_total,
        }
        for row in query.offset(offset).limit(page_size).all()
    ]


def get_upload_diffs(
    session,
    prefix: str | None = None,
    include_upload_uuids: list[str] | None = None,
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

    inner_query = session.query(
        Flamechart.prefix,
        Flamechart.created_at.label("upload_time"),
        Flamechart.upload_uuid,
        diff_expr,
    )

    if prefix:
        # apply prefix filter on prefix in subquery
        p = prefix.rstrip("/")
        inner_query = inner_query.filter(Flamechart.prefix.like(f"{p}%"))
    subq = inner_query.subquery()

    # 2) Outer query: aggregate improvements/degradations
    improvements = func.sum(case((subq.c.diff < 0, 1), else_=0)).label("improvements")
    degradations = func.sum(case((subq.c.diff > 0, 1), else_=0)).label("degradations")

    q = session.query(subq.c.prefix, improvements, degradations)
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


def calculate_trends(
    rows: list[Flamechart],
    group_by: str,
    sorting_key: str,
) -> list[tuple[str, float]]:
    trends = []
    for group_by_key, group in groupby(rows, key=lambda r: getattr(r, group_by)):
        recs = sorted(group, key=lambda row: getattr(row, sorting_key))
        if len(recs) < 2:
            trends.append((group_by_key, (1, 0)))
            continue

        x_values = np.array([i for i in range(len(recs))])
        errors = np.array([r.error_count for r in recs])
        k, b = np.polyfit(x_values, errors, 1)
        trends.append((group_by_key, (k, b)))

    return trends


def compute_trend_chart(session, prefix: str = "/"):
    prefix_len = len(prefix)
    grouped_prefix = func.substr(Flamechart.prefix, 1, prefix_len).label(
        "grouped_prefix",
    )
    q = (
        session.query(
            Flamechart.upload_uuid,
            grouped_prefix,
            Flamechart.to_date,
            func.sum(Flamechart.error_count).label("error_count"),
        )
        .filter(Flamechart.prefix.startswith(prefix))
        .group_by(Flamechart.upload_uuid, grouped_prefix, Flamechart.to_date)
        .order_by(Flamechart.to_date.asc())
    )
    rows = q.all()
    trends = dict(
        calculate_trends(rows, group_by="grouped_prefix", sorting_key="to_date"),
    )
    slope, intercept = trends.get(prefix, (1, 0))
    return [
        {
            "upload_uuid": str(row.upload_uuid),
            "to_date": row.to_date,
            "error_count": row.error_count,
            "predict": slope * n + intercept,
        }
        for n, row in enumerate(rows)
    ]


def compute_trends(
    session,
    prefix: str | None = None,
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

    trends = calculate_trends(rows, "prefix", "created_at")
    trends.sort(key=lambda x: x[0], reverse=descending)

    # apply pagination
    start = (page - 1) * page_size
    end = start + page_size
    return [
        {
            "prefix": trend[0],
            "slope": trend[1][0],
            "intercept": trend[1][1],
        }
        for trend in trends[start:end]
    ]


def get_basic_stats(
    session,
    prefix: str | None = None,
    order_by: str = "count",
    descending: bool = True,
    page: int = 1,
    page_size: int = 50,
):
    # 1) Define each aggregate and label it
    sum_column = func.sum(Flamechart.error_count).label("count")
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
        sum_column,
        mean_col,
        median_col,
        std_col,
        min_col,
        max_col,
    ).group_by(Flamechart.prefix)

    # 3) Optional prefix filter
    if prefix:
        q = q.filter(Flamechart.prefix.like(f"{prefix}%"))

    # 4) Map the user’s order_by key to the actual column
    ordering_map = {
        "count": sum_column,
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


def get_basic_stats_chart(
    session,
    prefix: str | None = None,
):
    # 1) Define each aggregate and label it
    sum_column = func.sum(Flamechart.error_count).label("count")
    mean_col = func.avg(Flamechart.error_count).label("mean")
    median_col = (
        func.percentile_cont(0.5).within_group(Flamechart.error_count).label("median")
    )
    std_col = func.stddev_pop(Flamechart.error_count).label("stddev")
    min_col = func.min(Flamechart.error_count).label("min")
    max_col = func.max(Flamechart.error_count).label("max")

    if prefix:
        prefix_len = len(prefix)
        grouped_prefix = func.substr(Flamechart.prefix, 1, prefix_len).label(
            "grouped_prefix",
        )
        q = (
            session.query(
                grouped_prefix,
                Flamechart.to_date,
                sum_column,
                mean_col,
                median_col,
                std_col,
                min_col,
                max_col,
            )
            .filter(Flamechart.prefix.startswith(prefix))
            .group_by(grouped_prefix, Flamechart.to_date)
        )
    else:
        q = session.query(
            Flamechart.to_date,
            sum_column,
            mean_col,
            median_col,
            std_col,
            min_col,
            max_col,
        ).group_by(Flamechart.to_date)

    return [
        {
            "prefix": getattr(row, "grouped_prefix", None),
            "count": row.to_date,
            "mean": row.count,
            "median": row.mean,
            "stddev": row.median,
            "min": row.stddev,
            "max": row.min,
        }
        for row in q.all()
    ]


def compare_uploads(
    session,
    upload_1_uuid: str,
    upload_2_uuid: str,
    prefix: str | None = None,
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


def get_prefix_autocomplete(session, prefix: str) -> list[str]:
    like_pattern = f"{prefix.rstrip('/')}%"
    query = session.query(Flamechart.prefix).filter(
        Flamechart.prefix.like(like_pattern),
    )

    next_segments = set()
    for row in query.limit(1000):
        remaining = row.prefix[len(prefix) :]
        if not remaining:
            continue

        split_remaining = remaining.split("/")
        if len(split_remaining) == 1:
            segment = split_remaining[0]
        else:
            segment = split_remaining[0] + "/"

        next_segments.add(segment)
    return sorted(next_segments)
