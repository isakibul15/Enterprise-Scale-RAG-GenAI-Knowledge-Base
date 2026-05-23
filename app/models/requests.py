"""Pydantic v2 request schemas for the API layer."""

from pydantic import BaseModel, Field, field_validator, ConfigDict


class QueryRequest(BaseModel):
    """Request schema for query/answer endpoint.
    
    Handles user questions with session tracking and retrieval preferences.
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "What is your refund policy?",
                "session_id": "user-123-session-abc",
                "top_k": 6,
                "use_parent_retriever": True,
                "stream": False,
            }
        }
    )

    question: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="The user's natural-language question.",
        examples=["What is the refund policy for enterprise customers?"],
    )
    session_id: str = Field(
        default="default",
        max_length=128,
        description="Conversation thread identifier. Use a stable UUID per user session.",
        examples=["user-123-session-abc"],
    )
    top_k: int = Field(
        default=6,
        ge=1,
        le=20,
        description="Number of document chunks to retrieve before generating the answer.",
    )
    use_parent_retriever: bool = Field(
        default=True,
        description=(
            "When True, child-chunk hits are swapped for their larger parent chunks "
            "to provide richer context to the LLM."
        ),
    )
    stream: bool = Field(
        default=False,
        description="When True, the answer is streamed as Server-Sent Events.",
    )

    @field_validator("session_id")
    @classmethod
    def sanitise_session_id(cls, v: str) -> str:
        """Validate session_id to prevent injection attacks."""
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
        if not all(c in allowed for c in v):
            raise ValueError("session_id may only contain alphanumerics, hyphens, underscores, and dots")
        return v

    @field_validator("question")
    @classmethod
    def validate_question_content(cls, v: str) -> str:
        """Ensure question is not just whitespace."""
        if not v.strip():
            raise ValueError("question cannot be empty or whitespace-only")
        return v.strip()


class ClearSessionRequest(BaseModel):
    """Request schema for clearing a chat session."""
    session_id: str = Field(
        ..., 
        min_length=1, 
        max_length=128,
        description="Session identifier to clear"
    )
