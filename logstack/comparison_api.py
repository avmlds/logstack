from http import HTTPStatus

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from logstack.api_models import (
    BasicStatsModel,
    CompareRequest,
    CompareResponse,
    DiffsRequest,
    DiffsResponse,
    GenericResponse,
    PrefixRequest,
    StatsRequest,
    TrendsRequest,
    TrendsResponse,
    UploadsModel,
    AllUploadsRequest,
    TrendsChartResponse,
)
from logstack.controllers import (
    compare_uploads,
    compute_trends,
    get_basic_stats,
    get_upload_diffs,
    list_upload_times,
    get_all_uploads,
    compute_trend_chart,
    get_prefix_autocomplete,
)
from logstack.database import get_db

comparison_router = APIRouter(prefix="/data")


@comparison_router.post("/uploads_all")
def uploads_all(req: AllUploadsRequest, db: Session = Depends(get_db)):
    return {
        "result": get_all_uploads(
            db, req.page, req.page_size, req.order_by, req.descending
        )
    }


@comparison_router.post("/uploads", response_model=GenericResponse[UploadsModel])
def api_list_uploads(req: PrefixRequest = Body(...), db: Session = Depends(get_db)):
    return {"result": list_upload_times(db, req.prefix, req.page, req.page_size)}


@comparison_router.post("/diffs", response_model=GenericResponse[DiffsResponse])
def api_get_diffs(req: DiffsRequest = Body(...), db: Session = Depends(get_db)):
    return {
        "result": get_upload_diffs(
            db,
            req.prefix,
            req.upload_uuids,
            req.page,
            req.page_size,
            req.order_by,
            req.descending,
        ),
    }


@comparison_router.post("/trends", response_model=GenericResponse[TrendsResponse])
def api_trends(req: TrendsRequest = Body(...), db: Session = Depends(get_db)):
    return {
        "result": compute_trends(
            db,
            req.prefix,
            req.page,
            req.page_size,
            req.descending,
        ),
    }


@comparison_router.post(
    "/trends-chart", response_model=GenericResponse[TrendsChartResponse]
)
def api_trend_chart(req: TrendsRequest = Body(...), db: Session = Depends(get_db)):
    return {
        "result": compute_trend_chart(
            db,
            req.prefix,
        ),
    }


@comparison_router.post("/stats", response_model=GenericResponse[BasicStatsModel])
def api_stats(req: StatsRequest = Body(...), db: Session = Depends(get_db)):
    return {
        "result": get_basic_stats(
            db,
            req.prefix,
            req.order_by,
            req.descending,
            req.page,
            req.page_size,
        ),
    }


@comparison_router.post("/compare", response_model=GenericResponse[CompareResponse])
def api_compare(req: CompareRequest = Body(...), db: Session = Depends(get_db)):
    if req.upload_uuid_1 == req.upload_uuid_2:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="upload_uuid_1 and upload_uuid_2 must differ",
        )

    return {
        "result": compare_uploads(
            db,
            req.upload_uuid_1,
            req.upload_uuid_2,
            req.prefix,
            req.page,
            req.page_size,
        ),
    }


@comparison_router.get("/prefix-autocomplete", response_model=GenericResponse[str])
def get_prefix_suggestions(
    prefix: str = Query("/", description="Current prefix"),
    db: Session = Depends(get_db),
):
    """Return next-level prefix segments under the given prefix."""

    return {"result": get_prefix_autocomplete(db, prefix)}
