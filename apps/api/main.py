"""FastAPI application entrypoint for Patchwork."""

from apps.api.database import check_db_connection
from apps.api.routers.approvals import router as approvals_router
from apps.api.routers.incidents import router as incidents_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Patchwork API",
    version="0.1.0",
    description="Autonomous incident-response and self-healing DevOps copilot API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(incidents_router)
app.include_router(approvals_router)


@app.get("/health")
async def health_check() -> dict[str, object]:
    """Return service and database connectivity status."""
    db_ok = await check_db_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
    }
