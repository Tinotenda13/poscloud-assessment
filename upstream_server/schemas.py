from pydantic import BaseModel
from datetime import datetime


class TransactionIngest(BaseModel):
    idempotency_key: str
    cashier: str
    amount: float
    description: str
    created_at: datetime


class TransactionResponse(BaseModel):
    id: int
    idempotency_key: str
    cashier: str
    amount: float
    description: str
    created_at: datetime

    model_config = {"from_attributes": True}
