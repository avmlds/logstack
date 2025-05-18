from http import HTTPStatus

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.templating import Jinja2Templates

from logstack.comparison_api import comparison_router
from logstack.file_management_api import file_router

templates = Jinja2Templates("templates")

app = FastAPI()
app.include_router(file_router, prefix="/api")
app.include_router(comparison_router, prefix="/api")


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/{template}")
async def index(template: str, request: Request):
    if not template:
        template = "index"
    if "favicon" in template:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)

    return templates.TemplateResponse(f"{template}.html", {"request": request})


if __name__ == "__main__":
    uvicorn.run(app)
