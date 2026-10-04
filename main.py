import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config.settings import settings
from app.data.models import Base, seed_database
from app.data.repository import get_engine
from app.escalation.service import escalation_service
from app.gateway.websocket import router as ws_router


app = FastAPI(
    title="Nova Finance Real-Time Voice Agent",
    description="Real-Time Voice Agent for Loan Servicing Workflows with Turn-Taking, Barge-in, and Safe Escalation",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client_dir = os.path.join(os.path.dirname(__file__), "client")
app.mount("/client", StaticFiles(directory=client_dir), name="client")

app.include_router(ws_router)


@app.on_event("startup")
async def on_startup():
    engine = get_engine()
    Base.metadata.create_all(engine)
    seed_database(engine)


@app.get("/")
async def get_index():
    return FileResponse(os.path.join(client_dir, "index.html"))


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "agent": settings.agent_name,
        "company": settings.company_name,
        "primary_model": settings.primary_llm_model,
        "stt_provider": settings.stt_provider,
        "tts_provider": settings.tts_provider,
    }


@app.get("/api/escalations")
async def list_escalations():
    return {"escalations": [item.dict() for item in escalation_service.get_pending_queue()]}
