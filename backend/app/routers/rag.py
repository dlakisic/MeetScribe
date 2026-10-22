import openai
from fastapi import APIRouter, Depends, HTTPException
from instructor.core.exceptions import InstructorError

from ..core.logging import get_logger
from ..dependencies import get_rag_service, require_auth
from ..rag.service import RAGService
from ..schemas.rag import RAGAskRequest, RAGAskResponse, RAGCitation

router = APIRouter(prefix="/api/rag", dependencies=[Depends(require_auth)])
log = get_logger("rag")


@router.post("/ask", response_model=RAGAskResponse)
async def ask(
    payload: RAGAskRequest,
    service: RAGService = Depends(get_rag_service),
):
    try:
        result = await service.ask(
            query=payload.query,
            meeting_ids=payload.meeting_ids,
            top_k=payload.top_k,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except (openai.APIError, InstructorError) as exc:
        log.warning("RAG synthesis failed", extra={"error": str(exc)})
        raise HTTPException(status_code=503, detail="LLM unavailable")
    return RAGAskResponse(
        answer=result.answer,
        confidence=result.confidence,
        fallback_used=result.fallback_used,
        citations=[
            RAGCitation(
                meeting_id=c.meeting_id,
                segment_id=c.segment_id,
                speaker=c.speaker,
                text=c.text,
                start_time=c.start_time,
                end_time=c.end_time,
                score=c.score,
                segment_ids=c.segment_ids,
                meeting_title=c.meeting_title,
                meeting_date=c.meeting_date,
            )
            for c in result.citations
        ],
    )
