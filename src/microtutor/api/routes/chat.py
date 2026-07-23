"""Chat-related API endpoints."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from microtutor.api.dependencies import get_tutor_service
from microtutor.api.dependencies import get_db
from microtutor.core.config.config_helper import config
from microtutor.schemas.api.requests import StartCaseRequest, ChatRequest, FeedbackRequest, CaseFeedbackRequest
from microtutor.schemas.api.responses import StartCaseResponse, ChatResponse, ErrorResponse, OpeningMessage
from microtutor.schemas.domain.domain import TutorContext
from microtutor.prompts.patient_prompts import normalize_patient_style
from microtutor.services.case import (
    CaseOpeningSnapshot,
    get_case_package_store,
    resolve_case_package,
    resolve_case_package_by_id,
)
from microtutor.services.emr import get_emr_service
from microtutor.services.emr.service import notes_to_emr_data
from microtutor.services.infrastructure.background import BackgroundTaskService, get_background_service
from microtutor.services.tutor.service import TutorService
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)
router = APIRouter()

# Tools whose replies should feed structured EMR extraction
_EMR_SOURCE_TOOLS = {"patient", "tests_management"}


async def _start_case_locked(
    *,
    request: StartCaseRequest,
    tutor_service: TutorService,
    background_service: BackgroundTaskService,
    model_name: str,
    store,
) -> StartCaseResponse:
    """Body of start_case; caller must hold store.get_start_lock(case_id)."""
    session_settings = store.put_settings(
        request.case_id,
        patient_style=normalize_patient_style(request.patient_style),
        allow_plausible_findings=bool(request.allow_plausible_findings),
    )

    # Idempotent reuse after the first successful start for this case_id
    cached_opening = store.get_opening(request.case_id)
    existing_package = store.get(request.case_id)
    if cached_opening and existing_package:
        logger.warning(
            "[START_CASE] Idempotent reuse for case_id=%s library_id=%s "
            "(duplicate start ignored)",
            request.case_id,
            existing_package.library_case_id,
        )
        emr_service = get_emr_service()
        emr_notes = emr_service.get_notes(request.case_id)
        emr_data = notes_to_emr_data(emr_notes)
        if cached_opening.presentation and not emr_data.get("chief_complaint"):
            emr_data = {**emr_data, "chief_complaint": cached_opening.presentation}
        return StartCaseResponse(
            initial_message=cached_opening.initial_message,
            history=cached_opening.history,
            case_id=request.case_id,
            organism=cached_opening.organism,
            case_library_id=cached_opening.library_case_id,
            figures=cached_opening.figures,
            emr_notes=emr_notes,
            emr_data=emr_data,
            presentation=cached_opening.presentation or None,
            opening_messages=[
                OpeningMessage(speaker=m["speaker"], content=m["content"])
                for m in cached_opening.opening_messages
            ],
            patient_style=session_settings.patient_style,
            allow_plausible_findings=session_settings.allow_plausible_findings,
        )

    if request.library_case_id:
        package = resolve_case_package_by_id(request.library_case_id)
    elif existing_package:
        package = existing_package
        logger.info(
            "[START_CASE] Reusing existing package for case_id=%s library_id=%s",
            request.case_id,
            package.library_case_id,
        )
    else:
        package = resolve_case_package(request.organism or "", prefer_figures=True)

    organism = package.organism or (request.organism or "")
    store.put(request.case_id, package)

    response = await tutor_service.start_case(
        organism=organism,
        case_id=request.case_id,
        model_name=request.model_name,
        enable_guidelines=request.enable_guidelines or False,
        case_description=package.narrative,
        case_source=package.source,
    )

    presentation = ((response.metadata or {}).get("presentation") or "").strip()
    opening_raw = (response.metadata or {}).get("opening_messages") or []
    opening_messages = [
        OpeningMessage(speaker=m["speaker"], content=m["content"])
        for m in opening_raw
        if isinstance(m, dict) and m.get("content")
    ]

    emr_service = get_emr_service()
    if emr_service.get_session(request.case_id) is None:
        emr_service.start_case(request.case_id)
        if presentation:
            emr_service.enqueue_exchange(
                case_id=request.case_id,
                student_question="(Patient introduces themselves)",
                patient_response=presentation,
            )
    elif presentation and not emr_service.get_notes(request.case_id):
        emr_service.enqueue_exchange(
            case_id=request.case_id,
            student_question="(Patient introduces themselves)",
            patient_response=presentation,
        )

    background_service.log_conversation_async(
        case_id=request.case_id,
        role="system",
        content=f"Case started: {organism}",
        metadata={
            "organism": organism,
            "model": model_name,
            "library_case_id": package.library_case_id,
            "case_source": package.source,
            "patient_style": session_settings.patient_style,
        },
    )
    for msg in opening_messages:
        background_service.log_conversation_async(
            case_id=request.case_id,
            role="assistant",
            content=msg.content,
            metadata={"tools_used": response.tools_used, "speaker": msg.speaker},
        )

    logger.info(
        f"[START_CASE] Success for case_id={request.case_id} "
        f"source={package.source} library_id={package.library_case_id} "
        f"figures={len(package.figures)}"
    )

    emr_data = notes_to_emr_data(emr_service.get_notes(request.case_id))
    if presentation and not emr_data.get("chief_complaint"):
        emr_data = {**emr_data, "chief_complaint": presentation}

    history = [
        {"role": "assistant", "content": m.content} for m in opening_messages
    ] or [{"role": "assistant", "content": response.content}]

    store.put_opening(
        request.case_id,
        CaseOpeningSnapshot(
            organism=organism,
            initial_message=response.content,
            presentation=presentation,
            opening_messages=[
                {"speaker": m.speaker, "content": m.content} for m in opening_messages
            ],
            history=history,
            library_case_id=package.library_case_id,
            figures=list(package.figures or []),
        ),
    )

    return StartCaseResponse(
        initial_message=response.content,
        history=history,
        case_id=request.case_id,
        organism=organism,
        case_library_id=package.library_case_id,
        figures=package.figures,
        emr_notes=emr_service.get_notes(request.case_id),
        emr_data=emr_data,
        presentation=presentation or None,
        opening_messages=opening_messages,
        patient_style=session_settings.patient_style,
        allow_plausible_findings=session_settings.allow_plausible_findings,
    )


@router.post(
    "/start_case",
    response_model=StartCaseResponse,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse}
    },
    summary="Start a new microbiology case",
    description="Initialize a new case for the selected organism with a unique case ID"
)
async def start_case(
    request: StartCaseRequest,
    tutor_service: TutorService = Depends(get_tutor_service),
    background_service: BackgroundTaskService = Depends(get_background_service)
) -> StartCaseResponse:
    """Start a new case with the selected organism.
    
    - **organism**: The microorganism to study (e.g., "staphylococcus aureus")
    - **case_id**: Client-generated unique case ID
    - **model_name**: Optional LLM model to use (defaults to o3-mini)
    """
    model_name = request.model_name or config.API_MODEL_NAME
    logger.info(
        f"[START_CASE] organism={request.organism}, "
        f"library_case_id={request.library_case_id}, "
        f"case_id={request.case_id}, model={model_name}"
    )
    
    try:
        store = get_case_package_store()
        # Serialize duplicate starts for the same case_id (React StrictMode fires twice).
        async with store.get_start_lock(request.case_id):
            return await _start_case_locked(
                request=request,
                tutor_service=tutor_service,
                background_service=background_service,
                model_name=model_name,
                store=store,
            )
    except ValueError as e:
        logger.error(f"[START_CASE] ValueError: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"[START_CASE] Error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to start case")


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse}
    },
    summary="Send a chat message",
    description="Send a message to the tutor and receive a response"
)
async def chat(
    request: ChatRequest,
    tutor_service: TutorService = Depends(get_tutor_service),
    background_service: BackgroundTaskService = Depends(get_background_service)
    ,db: Session = Depends(get_db)
) -> ChatResponse:
    """Process a chat message from the student.
    
    - **message**: The student's question or response
    - **history**: Full conversation history including system messages
    - **organism_key**: Current organism being studied
    - **case_id**: Active case ID
    """
    start_time = datetime.now()
    
    # Validate required fields
    if not request.case_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active case ID. Please start a new case.")
    if not request.organism_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active organism. Please start a new case.")
    
    model_name = request.model_name or config.API_MODEL_NAME
    use_azure = request.model_provider.lower() == 'azure' if request.model_provider else None
    
    logger.info(f"[CHAT] case_id={request.case_id}, model={model_name}, organism={request.organism_key}")
    
    try:
        # Filter system messages from incoming history
        from microtutor.utils.conversation_utils import filter_system_messages
        clean_history = filter_system_messages([msg.model_dump() for msg in request.history])

        # If client history is empty (or clearly incomplete), fall back to server-side history.
        # This prevents "I don't see any tests ordered yet" when the client failed to send prior turns.
        if (not clean_history) and db is not None:
            try:
                # Pull a bounded window of messages, then restore chronological order.
                # Note: conversation_logs in V4 schema stores role/content; metadata may not exist.
                result = db.execute(
                    text(
                        """
                        SELECT role, content
                        FROM conversation_logs
                        WHERE case_id = :case_id
                        ORDER BY timestamp DESC
                        LIMIT :limit
                        """
                    ),
                    {"case_id": request.case_id, "limit": 80},
                )
                rows = result.fetchall()
                db_history = [{"role": r[0], "content": r[1]} for r in reversed(rows)]
                db_history = filter_system_messages(db_history)
                if db_history:
                    logger.warning(
                        f"[CHAT] Client sent empty history; hydrated {len(db_history)} msgs from DB for case_id={request.case_id}"
                    )
                    clean_history = db_history
            except Exception as e:
                logger.warning(f"[CHAT] Failed to hydrate history from DB: {e}")
        
        # Prefer the bound package narrative so chat turns use the same case as figures
        bound_narrative = get_case_package_store().get_narrative(request.case_id)
        store = get_case_package_store()
        session_settings = store.get_settings(request.case_id)
        if request.patient_style is not None or request.allow_plausible_findings is not None:
            session_settings = store.put_settings(
                request.case_id,
                patient_style=request.patient_style,
                allow_plausible_findings=request.allow_plausible_findings,
            )
        context = TutorContext(
            case_id=request.case_id,
            organism=request.organism_key,
            case_description=bound_narrative,
            conversation_history=clean_history,
            model_name=model_name,
            use_azure=use_azure,
            session_metadata={
                "enable_guidelines": request.enable_guidelines or False,
                "patient_style": session_settings.patient_style,
                "allow_plausible_findings": session_settings.allow_plausible_findings,
            },
        )
        # Persist phase across requests.
        # Without this, every /chat call starts from INITIALIZING and the tutor may
        # infer/overwrite phase back to information gathering after a skip.
        if request.current_phase:
            try:
                from microtutor.schemas.domain.domain import TutorState
                context.current_state = TutorState(request.current_phase)
            except Exception:
                logger.warning(f"[CHAT] Invalid current_phase from client: {request.current_phase!r}")
        
        # Log user message asynchronously
        background_service.log_conversation_async(
            case_id=request.case_id,
            role="user",
            content=request.message,
            metadata={"organism": request.organism_key}
        )
        
        # Process message
        response = await tutor_service.process_message(
            message=request.message,
            context=context,
            feedback_enabled=request.feedback_enabled,
            feedback_threshold=request.feedback_threshold
        )
        
        # Log assistant response asynchronously
        background_service.log_conversation_async(
            case_id=request.case_id,
            role="assistant",
            content=response.content,
            metadata={"tools_used": response.tools_used, "organism": request.organism_key}
        )

        # Queue structured EMR extraction for patient / test-result replies
        emr_service = get_emr_service()
        tools_used = response.tools_used or []
        if any(t in _EMR_SOURCE_TOOLS for t in tools_used):
            emr_service.enqueue_exchange(
                case_id=request.case_id,
                student_question=request.message,
                patient_response=response.content,
            )
        
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(f"[CHAT] Completed in {processing_time:.2f}ms for case_id={request.case_id}")
        
        return ChatResponse(
            response=response.content,
            history=[{"role": msg["role"], "content": msg["content"]} for msg in context.conversation_history],
            tools_used=response.tools_used,
            metadata={
                "processing_time_ms": processing_time,
                "case_id": request.case_id,
                "organism": request.organism_key,
                "patient_style": session_settings.patient_style,
                "allow_plausible_findings": session_settings.allow_plausible_findings,
                **(response.metadata or {}),
                "current_phase": (response.metadata or {}).get("current_phase") or (response.metadata or {}).get("state"),
            },
            feedback_examples=response.feedback_examples or [],
            emr_notes=emr_service.get_notes(request.case_id),
            emr_data=notes_to_emr_data(emr_service.get_notes(request.case_id)),
            emr_busy=emr_service.is_busy(request.case_id),
        )
        
    except ValueError as e:
        logger.error(f"[CHAT] ValueError: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"[CHAT] Error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process message")


@router.post(
    "/feedback",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse}
    },
    summary="Submit feedback for a tutor response",
    description="Submit rating and optional feedback for a specific tutor message"
)
async def submit_feedback(
    request: FeedbackRequest,
    background_service: BackgroundTaskService = Depends(get_background_service)
) -> dict:
    """Submit feedback for a specific tutor response."""
    logger.info(f"[FEEDBACK] case_id={request.case_id}, rating={request.rating}, organism={request.organism}")
    
    try:
        # Convert history to list of dicts for storage
        chat_history = [{"role": msg.role, "content": msg.content} for msg in request.history] if request.history else []
        
        background_service.log_feedback_async(
            case_id=request.case_id or "unknown",
            rating=request.rating,
            message=request.message,
            feedback_text=request.feedback_text or "",
            replacement_text=request.replacement_text or "",
            organism=request.organism or "",
            chat_history=chat_history
        )
        return {"status": "success", "message": "Feedback received"}
        
    except Exception as e:
        logger.error(f"[FEEDBACK] Error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to submit feedback")


@router.post(
    "/case_feedback",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse}
    },
    summary="Submit overall case feedback",
    description="Submit ratings and comments for the entire case experience"
)
async def submit_case_feedback(
    request: CaseFeedbackRequest,
    background_service: BackgroundTaskService = Depends(get_background_service)
) -> dict:
    """Submit overall feedback for a completed case."""
    logger.info(f"[CASE_FEEDBACK] case_id={request.case_id}, organism={request.organism}, ratings=({request.detail}, {request.helpfulness}, {request.accuracy})")
    
    try:
        background_service.log_case_feedback_async(
            case_id=request.case_id,
            detail_rating=request.detail,
            helpfulness_rating=request.helpfulness,
            accuracy_rating=request.accuracy,
            comments=request.comments or "",
            organism=request.organism or ""
        )
        return {"status": "success", "message": "Case feedback received"}
        
    except Exception as e:
        logger.error(f"[CASE_FEEDBACK] Error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to submit case feedback")


@router.post(
    "/clarify",
    summary="Quick clarification helper",
    description="Answer general medical education questions without case context"
)
async def clarify_question(request: dict) -> dict:
    """Answer a clarifying question - no case context, just general medical knowledge.
    
    This is a simple helper for students to ask things like:
    - "What is a pertinent positive?"
    - "How do I interpret CRP levels?"
    - "What's the difference between sensitivity and specificity?"
    """
    message = request.get("message", "")
    history = request.get("history", [])
    
    if not message:
        return {"response": "Please ask a question!"}
    
    logger.info(f"[CLARIFY] Question: {message[:50]}...")
    
    try:
        from microtutor.core.llm.llm_router import chat_complete
        
        system_prompt = """You are a helpful medical education assistant. Answer questions clearly and concisely.

You help students understand:
- Medical terminology and concepts
- How to interpret lab values and tests
- Clinical reasoning approaches
- General medical knowledge

Keep answers brief (2-4 sentences) and educational. You do NOT have access to any specific patient case - 
you're just a general helper for clarifying concepts.

If asked about a specific patient or case, politely explain that you're just a general helper 
and they should ask the main tutor about case-specific questions."""

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history[-6:])  # Last 3 exchanges for context
        messages.append({"role": "user", "content": message})
        
        response = chat_complete(
            system_prompt="",
            user_prompt="",
            model=config.API_MODEL_NAME,  # Use configured model (default: gpt-5)
            conversation_history=messages
        )
        
        return {"response": response}
        
    except Exception as e:
        logger.error(f"[CLARIFY] Error: {e}", exc_info=True)
        return {"response": "Sorry, I couldn't process that question. Please try again."}


@router.get(
    "/organisms",
    summary="Get available organisms",
    description="Get list of organisms with pre-generated cases"
)
async def get_available_organisms() -> dict:
    """Get list of organisms that have pre-generated cases available."""
    try:
        from microtutor.services.case import CaseGeneratorRAGAgent
        
        case_generator = CaseGeneratorRAGAgent()
        cached_organisms = case_generator.get_cached_organisms()
        hpi_organisms = case_generator.get_hpi_organisms()
        
        logger.info(f"[ORGANISMS] Found {len(cached_organisms)} cached organisms")
        
        return {
            "status": "success",
            "organisms": cached_organisms,
            "hpi_organisms": hpi_organisms,
            "count": len(cached_organisms)
        }
        
    except Exception as e:
        logger.error(f"[ORGANISMS] Error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve organisms")


class EmrRefreshRequest(BaseModel):
    history: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Full conversation history for a complete EMR rebuild",
    )


@router.get(
    "/emr_notes/{case_id}",
    summary="Poll structured EMR notes",
    description="Return the current structured EMR notes snapshot for a case",
)
async def get_emr_notes(case_id: str) -> dict:
    emr_service = get_emr_service()
    # Recreate empty session after server restart so polling does not 404
    session = emr_service.ensure_session(case_id)
    notes = session.snapshot()
    return {
        "emr_notes": notes,
        "emr_busy": session.is_busy(),
        "emr_data": notes_to_emr_data(notes),
    }


@router.post(
    "/emr_refresh/{case_id}",
    summary="Rebuild EMR notes from conversation",
    description="Full re-extraction of structured EMR notes from the conversation history",
)
async def emr_refresh(case_id: str, request: EmrRefreshRequest) -> dict:
    emr_service = get_emr_service()
    history = request.history or []
    clean_history = [
        {"role": m.get("role", ""), "content": m.get("content", "")}
        for m in history
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    notes = await asyncio.to_thread(emr_service.rebuild, case_id, clean_history)
    return {
        "emr_notes": notes,
        "emr_busy": False,
        "emr_data": notes_to_emr_data(notes),
    }
