from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import settings
from .routers import accounts, entries, forecast, summary

app = FastAPI(title="WealthLens API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(accounts.router, prefix="/api/v1")
app.include_router(entries.router, prefix="/api/v1")
app.include_router(summary.router, prefix="/api/v1")
app.include_router(forecast.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
