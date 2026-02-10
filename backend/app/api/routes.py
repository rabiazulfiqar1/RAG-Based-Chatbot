from fastapi import APIRouter
from app.api.rag import router as rag
router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "OK"}

router.include_router(rag, prefix="/api")