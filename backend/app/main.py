from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import engine, ensure_v01_schema
from .routers import events, feedback, files, generation


models.Base.metadata.create_all(bind=engine)
ensure_v01_schema()

app = FastAPI(title="Resume Coach App", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events.router)
app.include_router(generation.router)
app.include_router(files.router)
app.include_router(feedback.router)


@app.get("/api/health")
def health():
    return {"ok": True, "version": "0.1.0"}
