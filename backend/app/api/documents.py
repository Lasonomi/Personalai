"""Documents API"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_documents():
    return {"message": "Documents endpoint — PDF upload + vector search coming in P2"}
