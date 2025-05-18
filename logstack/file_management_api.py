import datetime
import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile

from logstack.database import SessionLocal, get_db
from logstack.database_models import Flamechart

file_router = APIRouter(prefix="/files")


@file_router.post("/upload")
async def upload_file(
    from_date: datetime.date = Query(...),
    to_date: datetime.date = Query(...),
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
            error_count=error_count,
        )
        db.add(flamechart_entry)

    db.commit()
    return {"status": "Uploaded and saved."}
