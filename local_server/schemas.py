from pydantic import BaseModel, Field
from datetime import datetime
import uuid


class TransactionCreate(BaseModel):
    cashier: str
    amount: float
    description: str
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))


class TransactionResponse(BaseModel):
    id: int
    idempotency_key: str
    cashier: str
    amount: float
    description: str
    created_at: datetime
    sync_status: str

    model_config = {"from_attributes": True}
