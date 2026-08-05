"""Pydantic request models with automatic validation.

This module defines all request models used by the FastAPI endpoints.
Each model includes validation, examples, and comprehensive documentation.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import Annotated
from datetime import datetime


class Message(BaseModel):
    """A single message in conversation history.
    
    Attributes:
        role: Message role (user, assistant, or system)
        content: Message content
    """
    
    role: str = Field(
        ..., 
        description="Message role: user, assistant, or system"
    )
    content: str = Field(
        ..., 
        description="Message content"
    )
    
    @field_validator('role')
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate that role is one of the accepted values."""
        if v not in ['user', 'assistant', 'system']:
            raise ValueError('Role must be user, assistant, or system')
        return v
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "role": "user",
                "content": "What are the patient's vital signs?"
            }
        }
    )


class StartCaseRequest(BaseModel):
    """Request to start a new medical microbiology case.
    
    Attributes:
        organism: The microorganism for the case (optional if library_case_id set)
        case_id: Client-generated unique case ID
        library_case_id: Optional explicit case_library id (e.g. Case_02032)
        model_name: Optional LLM model to use
    """
    
    organism: Optional[Annotated[str, Field(min_length=1)]] = Field(
        default=None,
        description="Organism name for the case (derived from library case if omitted)",
        json_schema_extra={"example": "staphylococcus aureus"}
    )
    case_id: Annotated[str, Field(min_length=1)] = Field(
        ...,
        description="Client-generated unique case ID",
        json_schema_extra={"example": "case_2024_abc123"}
    )
    library_case_id: Optional[str] = Field(
        default=None,
        description="Explicit case_library id to bind (skips organism random pick)",
        json_schema_extra={"example": "Case_02032"},
    )
    model_name: Optional[str] = Field(
        default=None,
        description="LLM model to use for this case (defaults to config)"
    )
    enable_guidelines: Optional[bool] = Field(
        default=False,
        description="Whether to enable clinical guidelines for this case"
    )
    patient_style: Optional[str] = Field(
        default="neutral",
        description="Patient communication style (1st-person history voice)",
    )
    allow_plausible_findings: Optional[bool] = Field(
        default=False,
        description="When true, invent plausible ix findings if not in case data",
    )
    
    @field_validator('organism')
    @classmethod
    def organism_not_empty(cls, v: Optional[str]) -> Optional[str]:
        """Ensure organism name is not just whitespace when provided."""
        if v is None:
            return None
        if not v.strip():
            raise ValueError('Organism name cannot be empty')
        return v.strip().lower()

    @field_validator('library_case_id')
    @classmethod
    def library_case_id_strip(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None

    @model_validator(mode="after")
    def require_organism_or_library_case(self) -> "StartCaseRequest":
        if not self.library_case_id and not self.organism:
            raise ValueError("Provide organism and/or library_case_id")
        return self
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "organism": "staphylococcus aureus",
                "case_id": "case_2024_abc123",
                "model_name": None
            }
        }
    )


class ChatRequest(BaseModel):
    """Request to send a chat message to the tutor.
    
    Attributes:
        message: User's message to the tutor
        history: Full conversation history
        organism_key: Current organism being studied
        case_id: Active case ID
        model_name: Optional LLM model to use
    """
    
    message: Annotated[str, Field(min_length=1)] = Field(
        ...,
        description="User's message to the tutor",
        json_schema_extra={"example": "What are the patient's symptoms?"}
    )
    history: List[Message] = Field(
        default_factory=list,
        description="Full conversation history including system messages"
    )
    organism_key: Optional[str] = Field(
        None,
        description="Current organism being studied"
    )
    case_id: Optional[str] = Field(
        None,
        description="Active case ID"
    )
    model_name: Optional[str] = Field(
        None,
        description="LLM model to use for this chat"
    )
    model_provider: Optional[str] = Field(
        None,
        description="Model provider: 'azure' or 'personal'"
    )
    feedback_enabled: Optional[bool] = Field(
        True,
        description="Whether to enable in context feedback for this request"
    )
    feedback_threshold: Optional[float] = Field(
        0.7,
        ge=0.1,
        le=1.0,
        description="Similarity threshold for feedback retrieval (0.1-1.0)"
    )
    enable_guidelines: Optional[bool] = Field(
        default=False,
        description="Whether to enable clinical guidelines for this request"
    )
    current_phase: Optional[str] = Field(
        default=None,
        description="Frontend-reported current phase (e.g. 'information_gathering', 'differential_diagnosis', 'tests_management', 'feedback')"
    )
    patient_style: Optional[str] = Field(
        default=None,
        description="Patient communication style; updates session when provided",
    )
    allow_plausible_findings: Optional[bool] = Field(
        default=None,
        description="Ix policy toggle; updates session when provided",
    )
    active_module: Optional[str] = Field(
        default=None,
        description="Frontend module id (e.g. history_taking, differential_diagnosis)",
    )
    route_to: Optional[str] = Field(
        default=None,
        description="Explicit route: 'tutor' for Ask Docent coach; omit for module agent",
    )
    
    @field_validator('message')
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        """Ensure message is not just whitespace."""
        if not v.strip():
            raise ValueError('Message cannot be empty')
        return v.strip()
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "What are the patient's vital signs?",
                "history": [
                    {
                        "role": "system",
                        "content": "You are an expert microbiology tutor..."
                    },
                    {
                        "role": "assistant",
                        "content": "Welcome to the case of a 45-year-old patient..."
                    }
                ],
                "organism_key": "staphylococcus aureus",
                "case_id": "case_2024_abc123",
                "model_name": None
            }
        }
    )


class FeedbackRequest(BaseModel):
    """User feedback on a specific tutor response.
    
    Attributes:
        rating: Rating from 1-5
        message: The assistant message being rated
        history: Conversation history at feedback time
        feedback_text: Optional additional feedback text
        replacement_text: Optional suggested replacement text
        case_id: Associated case ID
        organism: Current organism being studied (for feedback categorization)
    """
    
    rating: int = Field(
        ...,
        ge=1,
        le=5,
        description="Rating from 1 (poor) to 5 (excellent)"
    )
    message: str = Field(
        ...,
        description="The specific assistant message being rated"
    )
    history: List[Message] = Field(
        ...,
        description="Conversation history at the time of feedback"
    )
    feedback_text: Optional[str] = Field(
        default="",
        description="Optional detailed feedback from the user"
    )
    replacement_text: Optional[str] = Field(
        default="",
        description="Optional suggested replacement text"
    )
    case_id: Optional[str] = Field(
        None,
        description="Associated case ID"
    )
    organism: Optional[str] = Field(
        default="",
        description="Current organism being studied (for feedback categorization)"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rating": 4,
                "message": "The patient's temperature is 38.5°C...",
                "history": [],
                "feedback_text": "Good response, but could be more detailed",
                "replacement_text": "",
                "case_id": "case_2024_abc123",
                "organism": "staphylococcus aureus"
            }
        }
    )


class CaseFeedbackRequest(BaseModel):
    """Overall feedback for an entire case.
    
    Attributes:
        detail: Rating for level of detail
        helpfulness: Rating for how helpful the case was
        accuracy: Rating for medical accuracy
        comments: Optional additional comments
        case_id: Case ID
        organism: Current organism for the case
    """
    
    detail: int = Field(
        ..., 
        ge=1, 
        le=5, 
        description="Rating for level of detail (1-5)"
    )
    helpfulness: int = Field(
        ..., 
        ge=1, 
        le=5, 
        description="Rating for educational value (1-5)"
    )
    accuracy: int = Field(
        ..., 
        ge=1, 
        le=5, 
        description="Rating for medical accuracy (1-5)"
    )
    comments: Optional[str] = Field(
        default="", 
        description="Additional comments about the case"
    )
    case_id: str = Field(
        ..., 
        description="Case ID for this feedback"
    )
    organism: Optional[str] = Field(
        default="",
        description="Current organism for the case"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": 5,
                "helpfulness": 4,
                "accuracy": 5,
                "comments": "Great case! Very educational.",
                "case_id": "case_2024_abc123",
                "organism": "staphylococcus aureus"
            }
        }
    )

