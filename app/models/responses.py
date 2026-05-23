"""Pydantic v2 response schemas for the API layer."""

from pydantic import BaseModel, Field


class SourceDocumentSchema(BaseModel):
    file_name: str = Field(description="Original file name of the source document.")
    source: str = Field(description="Absolute path or URI of the source document.")
    chunk_id: str = Field(description="Stable UUID of the retrieved chunk.")
    page: str | int = Field(description="Page number or chunk index within the document.")
    snippet: str = Field(description="First 200 characters of the retrieved chunk.")

    model_config = {"from_attributes": True}


class QueryResponse(BaseModel):
    answer: str = Field(description="The LLM-generated answer grounded in retrieved context.")
    sources: list[SourceDocumentSchema] = Field(
        default_factory=list,
        description="Deduplicated list of source chunks used to produce the answer.",
    )
    session_id: str = Field(description="Echo of the request session_id.")
    retrieved_chunks: int = Field(description="Number of context chunks retrieved from the vector store.")
    latency_ms: float = Field(description="End-to-end pipeline latency in milliseconds.")

    model_config = {"from_attributes": True}


class UploadResponse(BaseModel):
    message: str
    file_name: str
    total_child_chunks: int
    total_parent_chunks: int
    duration_seconds: float
    collection: str


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    chromadb: str = Field(examples=["connected"])
    embedding_model: str
    llm_provider: str
    version: str = "1.0.0"


class ErrorResponse(BaseModel):
    detail: str
    error_code: str | None = None
