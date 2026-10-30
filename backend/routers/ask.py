"""
Events router — Q&A over the video timeline using RAG.
Scoped to the authenticated user and uses their encrypted BYOK Groq API key.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException

from core.deps import get_current_user, resolve_user_groq_key
from db.models import User
from models.schemas import QuestionRequest, QuestionResponse, VideoStatus
import store
from services.rag_service import answer_question

router = APIRouter(prefix="/ask", tags=["ask"])


@router.post("", response_model=QuestionResponse)
async def ask_question(
    body: QuestionRequest,
    user: User = Depends(get_current_user),
    user_groq_key: str = Depends(resolve_user_groq_key),
):
    """
    Ask a natural language question about a processed media item owned by the user.
    Retrieves relevant timeline events and answers with the user's BYOK Groq API key.
    """
    video = store.get_video(body.video_id, user_id=user.id)
    if not video:
        raise HTTPException(status_code=404, detail="Media not found in your account.")
    if video.status != VideoStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Media is not ready yet. Current status: {video.status.value}"
        )

    all_events = store.get_events(body.video_id)
    if not all_events:
        raise HTTPException(status_code=404, detail="No events found for this media.")

    result = answer_question(
        video_id=body.video_id,
        question=body.question,
        all_events=all_events,
        groq_api_key=user_groq_key,
        history=body.history,
        use_agent=body.use_agent,
    )
    return result
