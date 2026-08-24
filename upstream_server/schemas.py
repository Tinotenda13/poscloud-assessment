from pydantic import BaseModel
from datetime import datetime


# Schema for receiving a transaction from the local server — includes created_at since it was set offline.
class TransactionIngest(BaseModel):
    idempotency_key: str
    cashier: str
    amount: float
    description: str
    created_at: datetime


# Schema for returning a transaction in API responses.
class TransactionResponse(BaseModel):
    id: int
    idempotency_key: str
    cashier: str
    amount: float
    description: str
    created_at: datetime

    model_config = {"from_attributes": True}  # allows reading from SQLAlchemy ORM objects
