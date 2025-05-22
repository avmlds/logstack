from http import HTTPStatus

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from logstack.api.analytics import comparison_router
from logstack.api.ingestion import ingestion_router

templates = Jinja2Templates("templates")

app = FastAPI()
app.include_router(ingestion_router, prefix="/api")
app.include_router(comparison_router, prefix="/api")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/{template}")
async def template_index(template: str, request: Request):
    if "favicon" in template:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)

    return templates.TemplateResponse(f"{template}.html", {"request": request})


if __name__ == "__main__":
    uvicorn.run(app)
