#validation.py
from pydantic import BaseModel, Field
from typing import Optional
import uuid

class ValidationRequest(BaseModel):
    idea_description: str = Field(..., min_length=10, description="The core idea description")
    target_market: Optional[str] = Field(None, description="The target market for the idea")
    budget_constraints: Optional[str] = Field(None, description="Budget constraints if any")
    idempotency_key: Optional[str] = Field(None, description="Client-provided idempotency key for safe retries")

class ValidationResponse(BaseModel):
    validation_id: uuid.UUID
    status: str
    message: str
