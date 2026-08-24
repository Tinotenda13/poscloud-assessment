from pydantic import BaseModel, Field
from datetime import datetime
import uuid


# Schema for creating a transaction — idempotency_key is auto-generated as a UUID if not provided.
class TransactionCreate(BaseModel):
    cashier: str
    amount: float
    description: str
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))


# Schema for returning a transaction in API responses — includes DB fields like id, created_at, sync_status.
class TransactionResponse(BaseModel):
    id: int
    idempotency_key: str
    cashier: str
    amount: float
    description: str
    created_at: datetime
    sync_status: str

    model_config = {"from_attributes": True}  # allows reading from SQLAlchemy ORM objects
