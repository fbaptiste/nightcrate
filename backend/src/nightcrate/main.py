"""NightCrate FastAPI application."""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nightcrate.api import files, images, settings
from nightcrate.db.migrations import apply_migrations


@asynccontextmanager
async def lifespan(app: FastAPI):
    apply_migrations()
    yield


app = FastAPI(title="NightCrate", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(files.router)
app.include_router(images.router)
app.include_router(settings.router)

APP_VERSION = "0.3.0"


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": APP_VERSION}


def run() -> None:
    uvicorn.run("nightcrate.main:app", host="127.0.0.1", port=8000, reload=True)
