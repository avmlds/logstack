from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class GenericResponse(BaseModel, Generic[T]):
    result: list[T]


class AllUploadsRequest(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(1000, ge=1, le=1000)
    order_by: Literal["upload_uuid", "filename", "created_at", "errors_total"] = (
        "created_at"
    )
    descending: bool = True


class BasePrefixRequest(BaseModel):
    prefix: str | None = Field(None, description="prefix prefix filter")


class PrefixRequest(BasePrefixRequest):
    page: int = Field(1, ge=1)
    page_size: int = Field(1000, ge=1, le=1000)


class DiffsRequest(PrefixRequest):
    upload_uuids: list[str] | None = Field(
        None,
        description="UUIDs of uploads to include",
    )
    order_by: Literal["improvements", "degradations"] = "improvements"
    descending: bool = True


class DiffsResponse(BaseModel):
    prefix: str
    improvements: int
    degradations: int


class TrendsRequest(PrefixRequest):
    descending: bool = True


class TrendsResponse(BaseModel):
    prefix: str
    slope: float
    intercept: float


class TrendsChartResponse(BaseModel):
    upload_uuid: str
    to_date: datetime
    error_count: int
    predict: float


class StatsRequest(PrefixRequest):
    order_by: str = Field("mean", description="Field to order by")
    descending: bool = Field(True, description="Descending order")


class CompareRequest(BaseModel):
    upload_uuid_1: str = Field(..., description="First upload UUID")
    upload_uuid_2: str = Field(..., description="Second upload UUID")
    prefix: str | None = Field(None, description="prefix prefix filter")
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=100)


class CompareResponse(BaseModel):
    prefix: str
    error_count_1: int
    error_count_2: int
    delta: int


class UploadsModel(BaseModel):
    id: int
    upload_uuid: str
    filename: str
    prefix: str
    error_count: int
    from_date: datetime
    to_date: datetime
    created_at: datetime


class BasicStatsModel(BaseModel):
    prefix: str
    count: float
    mean: float
    median: float
    stddev: float
    min: float
    max: float


class EventRequestModel(BaseModel):
    prefix: str
    error_count: int = 1
    filename: str | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None
    upload_uuid: str | None = None
    environment: str | None = None


class EventResponseModel(BaseModel):
    id: str
