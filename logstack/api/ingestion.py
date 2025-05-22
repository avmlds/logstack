import datetime
import uuid

from fastapi import APIRouter, Body, Depends, File, Query, UploadFile

from logstack.api.models import EventRequestModel, EventResponseModel
from logstack.constants import EVENT
from logstack.database import SessionLocal, get_db
from logstack.database_models import Flamechart

ingestion_router = APIRouter(prefix="/ingestion")


@ingestion_router.post("/upload-file")
async def upload_file(
    from_date: datetime.date = Query(...),
    to_date: datetime.date = Query(...),
    environment: str | None = Query(None),
    file: UploadFile = File(...),
    db: SessionLocal = Depends(get_db),
):
    created_at = datetime.datetime.now(tz=datetime.UTC)
    upload_uuid = str(uuid.uuid4())
    f = await file.read()
    for line in f.decode().split("\n"):
        line = line.strip()
        if not line:
            continue

        parts = line.rsplit(" ", 1)
        if len(parts) != 2:
            continue

        prefix_raw = parts[0].replace(";", "/")
        if prefix_raw.startswith("//"):
            prefix_raw = prefix_raw[1:]

        error_count = int(parts[1])

        flamechart_entry = Flamechart(
            upload_uuid=upload_uuid,
            filename=file.filename,
            from_date=from_date,
            to_date=to_date,
            created_at=created_at,
            prefix=prefix_raw,
            environment=environment,
            error_count=error_count,
        )
        db.add(flamechart_entry)

    db.commit()
    return {"status": "Uploaded and saved."}


@ingestion_router.post("/event", response_model=EventResponseModel)
async def receive_event(
    payload: EventRequestModel = Body(...),
    db: SessionLocal = Depends(get_db),
):
    created_at = datetime.datetime.now(tz=datetime.UTC)
    filename = EVENT if payload.filename is None else payload.filename
    upload_uuid = EVENT if payload.upload_uuid is None else payload.upload_uuid
    from_date = created_at if payload.from_date is None else payload.from_date
    to_date = created_at if payload.to_date is None else payload.to_date
    event = Flamechart(
        upload_uuid=upload_uuid,
        filename=filename,
        from_date=from_date,
        to_date=to_date,
        created_at=created_at,
        prefix=payload.prefix,
        environment=payload.environment,
        error_count=payload.error_count,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return {"id": event.id}
