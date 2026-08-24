from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import os, sync
from database import init_db, get_db, Transaction, User
from schemas import TransactionCreate, TransactionResponse
from dotenv import load_dotenv

templates = Jinja2Templates(directory="templates")

load_dotenv(dotenv_path="../.env")
sync.UPSTREAM_URL = os.getenv("UPSTREAM_URL", "http://localhost:8001")
SECRET_KEY = os.getenv("SECRET_KEY", "poscloud-secret")

scheduler = AsyncIOScheduler()


# On startup: init DB, seed default admin user, start background sync every 10s. On shutdown: stop scheduler.
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async for db in get_db():  # seed a default user if none exists
        existing = await db.execute(select(User).where(User.username == "admin"))
        if not existing.scalar_one_or_none():
            db.add(User(username="admin", password="admin123"))
            await db.commit()
    scheduler.add_job(sync.sync_pending_transactions, "interval", seconds=10)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="POS Local Server", lifespan=lifespan)


# Helper: reads username from session cookie. Returns None if not logged in.
def get_current_user(request: Request) -> str | None:
    return request.cookies.get("session_user")


# Helper: redirects to login if user is not logged in.
def require_login(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return None


# Accepts a new transaction, saves it to DB. Returns 409 if idempotency_key already exists (duplicate prevention).
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

# Returns all transactions from local DB, newest first.
@app.get("/transactions", response_model=list[TransactionResponse])
async def list_transactions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Transaction).order_by(Transaction.created_at.desc()))
    return result.scalars().all()

# Looks up a single transaction by its idempotency_key. Returns 404 if not found.
@app.get("/transactions/{idempotency_key}", response_model=TransactionResponse)
async def get_transaction(idempotency_key: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Transaction).where(Transaction.idempotency_key == idempotency_key)
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn

# Manually triggers sync of pending transactions to upstream — useful for testing without waiting for the scheduler.
@app.post("/sync/trigger")
async def manual_sync():
    await sync.sync_pending_transactions()
    return {"detail": "Sync triggered"}


# UI: Login page — renders the login form.
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"message": None})


# UI: Handles login form — checks credentials, sets session cookie on success.
@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, username: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == username, User.password == password))
    user = result.scalar_one_or_none()
    if not user:
        return templates.TemplateResponse(request, "login.html", {"message": "Invalid username or password.", "message_type": "error"})
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(key="session_user", value=username, httponly=True)  # set session cookie
    return response


# UI: Logout — clears session cookie and redirects to login.
@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session_user")
    return response


# UI: Dashboard — protected. Shows all transactions + summary stats (total, synced, pending).
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    redirect = require_login(request)
    if redirect:
        return redirect
    result = await db.execute(select(Transaction).order_by(Transaction.created_at.desc()))
    transactions = result.scalars().all()
    total = len(transactions)
    synced = sum(1 for t in transactions if t.sync_status == "synced")
    pending = sum(1 for t in transactions if t.sync_status == "pending")
    total_amount = sum(t.amount for t in transactions)
    return templates.TemplateResponse(request, "dashboard.html", {
        "transactions": transactions,
        "total": total,
        "synced": synced,
        "pending": pending,
        "total_amount": total_amount,
        "user": get_current_user(request),
    })


# UI: Renders the new transaction form — protected.
@app.get("/new-transaction", response_class=HTMLResponse)
async def new_transaction_form(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "new_transaction.html", {"message": None})


# UI: Handles form submission — saves transaction, shows success or duplicate error on the same page.
@app.post("/new-transaction", response_class=HTMLResponse)
async def create_transaction_ui(
    request: Request,
    cashier: str = Form(...),
    amount: float = Form(...),
    description: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    redirect = require_login(request)
    if redirect:
        return redirect
    payload = TransactionCreate(cashier=cashier, amount=amount, description=description)
    txn = Transaction(**payload.model_dump())
    db.add(txn)
    try:
        await db.commit()
        return templates.TemplateResponse(request, "new_transaction.html", {"message": "Transaction created successfully!", "message_type": "success"})
    except IntegrityError:
        await db.rollback()
        return templates.TemplateResponse(request, "new_transaction.html", {"message": "Duplicate transaction.", "message_type": "error"})


# UI: Renders the sync page — protected.
@app.get("/sync", response_class=HTMLResponse)
async def sync_page(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "sync.html", {"message": None})


# UI: Triggers sync from the browser and shows a success message.
@app.post("/sync", response_class=HTMLResponse)
async def sync_trigger_ui(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect
    await sync.sync_pending_transactions()
    return templates.TemplateResponse(request, "sync.html", {"message": "Sync triggered successfully!", "message_type": "success"})


# UI: Manage users page — admin only. Shows all users and a form to add a new cashier.
@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, db: AsyncSession = Depends(get_db)):
    redirect = require_login(request)
    if redirect:
        return redirect
    if get_current_user(request) != "admin":  # only admin can access this page
        return RedirectResponse(url="/", status_code=302)
    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()
    return templates.TemplateResponse(request, "users.html", {"users": users, "message": None})


# UI: Handles new user form — admin creates a cashier account. Returns error if username already exists.
@app.post("/users", response_class=HTMLResponse)
async def create_user(request: Request, username: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)):
    redirect = require_login(request)
    if redirect:
        return redirect
    if get_current_user(request) != "admin":
        return RedirectResponse(url="/", status_code=302)
    db.add(User(username=username, password=password))
    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()
    try:
        await db.commit()
        result = await db.execute(select(User).order_by(User.id))
        users = result.scalars().all()
        return templates.TemplateResponse(request, "users.html", {"users": users, "message": f"User '{username}' created successfully!", "message_type": "success"})
    except IntegrityError:
        await db.rollback()
        return templates.TemplateResponse(request, "users.html", {"users": users, "message": f"Username '{username}' already exists.", "message_type": "error"})
