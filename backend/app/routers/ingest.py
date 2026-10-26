from fastapi import APIRouter

from app.models.schemas import IngestResponse
from app.services.ingest import run_ingestion

router = APIRouter()


@router.post("/ingest", response_model=IngestResponse)
async def ingest():
    result = run_ingestion()
    return IngestResponse(**result)
