from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import os, sync
from database import init_db, get_db, Transaction
from schemas import TransactionCreate, TransactionResponse
from dotenv import load_dotenv

templates = Jinja2Templates(directory="templates")

load_dotenv(dotenv_path="../.env")
sync.UPSTREAM_URL = os.getenv("UPSTREAM_URL", "http://localhost:8001")

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler.add_job(sync.sync_pending_transactions, "interval", seconds=10)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="POS Local Server", lifespan=lifespan)

# Create a transaction endpoint that accepts a POST request with a JSON payload containing the transaction details. The endpoint should validate the payload, create a new transaction record in the database, and return a response indicating success or failure. If the transaction already exists (based on the idempotency key), it should return a 409 Conflict response
@app.post("/transactions", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(payload: TransactionCreate, db: AsyncSession = Depends(get_db)):
    txn = Transaction(**payload.model_dump())
    db.add(txn)
    try:
        await db.commit()
        await db.refresh(txn)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate idempotency_key")
    return txn

# List transactions endpoint that accepts a GET request and returns a list of all transactions in the database, ordered by creation date (most recent first). The response should include the transaction details in JSON format.
@app.get("/transactions", response_model=list[TransactionResponse])
async def list_transactions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Transaction).order_by(Transaction.created_at.desc()))
    return result.scalars().all()

#Get a transaction by idempotency_key
@app.get("/transactions/{idempotency_key}", response_model=TransactionResponse)
async def get_transaction(idempotency_key: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Transaction).where(Transaction.idempotency_key == idempotency_key)
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn

# Manually trigger sync endpoint that accepts a POST request and triggers the sync of pending transactions to the upstream server. The response should indicate that the sync has been triggered successfully.
@app.post("/sync/trigger")
async def manual_sync():
    """Manually trigger sync — useful for testing."""
    await sync.sync_pending_transactions()
    return {"detail": "Sync triggered"}


# UI Routes
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Transaction).order_by(Transaction.created_at.desc()))
    transactions = result.scalars().all()
    return templates.TemplateResponse(request, "dashboard.html", {"transactions": transactions})


@app.get("/new-transaction", response_class=HTMLResponse)
async def new_transaction_form(request: Request):
    return templates.TemplateResponse(request, "new_transaction.html", {"message": None})


@app.post("/new-transaction", response_class=HTMLResponse)
async def create_transaction_ui(
    request: Request,
    cashier: str = Form(...),
    amount: float = Form(...),
    description: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    payload = TransactionCreate(cashier=cashier, amount=amount, description=description)
    txn = Transaction(**payload.model_dump())
    db.add(txn)
    try:
        await db.commit()
        return templates.TemplateResponse(request, "new_transaction.html", {"message": "Transaction created successfully!", "message_type": "success"})
    except IntegrityError:
        await db.rollback()
        return templates.TemplateResponse(request, "new_transaction.html", {"message": "Duplicate transaction.", "message_type": "error"})


@app.get("/sync", response_class=HTMLResponse)
async def sync_page(request: Request):
    return templates.TemplateResponse(request, "sync.html", {"message": None})


@app.post("/sync", response_class=HTMLResponse)
async def sync_trigger_ui(request: Request):
    await sync.sync_pending_transactions()
    return templates.TemplateResponse(request, "sync.html", {"message": "Sync triggered successfully!", "message_type": "success"})
