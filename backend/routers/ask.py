"""
Events router — Q&A over the video timeline using RAG.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Header

from models.schemas import QuestionRequest, QuestionResponse, VideoStatus
import store
from services.rag_service import answer_question

router = APIRouter(prefix="/ask", tags=["ask"])


@router.post("", response_model=QuestionResponse)
async def ask_question(
    body: QuestionRequest,
    x_groq_api_key: Optional[str] = Header(None, alias="X-Groq-Api-Key"),
):
    """
    Ask a natural language question about a processed video.
    Retrieves relevant timeline events and answers with an LLM.
    Supports client-provided Groq API key via header or request body.
    """
    client_key = (x_groq_api_key or body.groq_api_key or "").strip() or None

    video = store.get_video(body.video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found.")
    if video.status != VideoStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Video is not ready yet. Current status: {video.status.value}"
        )

    all_events = store.get_events(body.video_id)
    if not all_events:
        raise HTTPException(status_code=404, detail="No events found for this video.")

    result = answer_question(
        video_id=body.video_id,
        question=body.question,
        all_events=all_events,
        groq_api_key=client_key,
    )
    return result
