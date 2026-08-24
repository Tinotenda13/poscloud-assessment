# POSCloud – Offline-First Retail Transaction System

## Project Overview

POSCloud is an offline-first Point of Sale (POS) system built as part of a software development internship project. It solves a real-world problem faced by retail businesses in areas with unreliable internet connectivity — transactions must never be lost, even when the network goes down.

The system consists of two servers:
- A **local server** that runs on the POS device, stores transactions in SQLite, and works fully offline
- An **upstream server** that runs in the cloud, receives synced transactions, and stores them in PostgreSQL

---

## Architecture

```
[Cashier / Browser UI]
        │
        ▼
 local_server  (FastAPI + SQLite, port 8000)   ← always available, offline-first
        │  background sync every 10s (only when online)
        ▼
upstream_server (FastAPI + PostgreSQL, port 8001)   ← central cloud server
```

---

## Features

- Cashier login with session-based authentication
- Create and view transactions from a browser UI
- Transactions saved locally first — no network required
- Automatic background sync to upstream every 10 seconds when online
- Manual sync trigger from the UI
- Dashboard with summary stats: total transactions, total sales, synced count, pending count
- Duplicate prevention using UUID idempotency keys
- Transactions survive app and device restarts (SQLite persists to disk)

---

## Technologies

| Layer | Technology |
|-------|------------|
| Local server | FastAPI, SQLite (via aiosqlite) |
| Upstream server | FastAPI, PostgreSQL (via asyncpg) |
| ORM | SQLAlchemy (async) |
| Background sync | APScheduler |
| HTTP client | HTTPX |
| UI | Jinja2 templates |
| Auth | Cookie-based sessions |

---

## Setup

### Prerequisites
- Python 3.12+
- PostgreSQL running locally

### 1. Clone and navigate
```bash
git clone https://github.com/Tinotenda13/poscloud-assessment.git
cd poscloud-assessment
```

### 2. Create virtual environment
```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment
Edit `.env`:
```
UPSTREAM_POSTGRES_URL=postgresql+asyncpg://<user>:<password>@localhost:5432/poscloud_upstream
UPSTREAM_URL=http://localhost:8001
```

### 5. Create upstream PostgreSQL database
```bash
psql -U postgres -c "CREATE DATABASE poscloud_upstream;"
```

### 6. Run upstream server (port 8001)
```bash
cd upstream_server
python -m uvicorn main:app --port 8001 --reload
```

### 7. Run local server (port 8000) — in a new terminal
```bash
cd local_server
python -m uvicorn main:app --port 8000 --reload
```

Open http://localhost:8000 in your browser and log in with:
- **Username:** admin
- **Password:** admin123

---

## How Sync Works

1. On startup, APScheduler registers a job that runs `sync_pending_transactions()` every 10 seconds.
2. Before syncing, the function pings `https://www.google.com` with a 3-second timeout. If it fails, sync is skipped and retried on the next tick.
3. If online, all transactions with `sync_status = pending` are fetched and pushed one by one to the upstream `/transactions` endpoint.
4. A `201` (created) or `409` (already exists) response both result in the local record being marked `synced`.
5. Any network error during sync stops the loop — remaining `pending` records are retried next cycle.

---

## Key Design Decisions

| Concern | Decision | Reasoning |
|---------|----------|-----------|
| Local storage | SQLite | File-based, zero-config, survives restarts, no server needed on device |
| Upstream storage | PostgreSQL | Robust, production-grade central database |
| Duplicate prevention | UUID `idempotency_key` + `UNIQUE` constraint | Retrying a sync never creates duplicates |
| Connectivity check | Ping `google.com` | Simple, reliable offline simulation |
| Sync trigger | APScheduler every 10s | Automatic recovery without manual intervention |
| Auth | Cookie-based session | Simple and stateless, no extra dependencies |
| Mid-sync recovery | Mark `synced` only after confirmed upstream response | Guarantees no silent data loss |

---

## Test Scenario

### Online → Offline → Restart → Restore Internet → Auto Sync

**Step 1 — Start both servers**
```bash
# Terminal 1
cd upstream_server && python -m uvicorn main:app --port 8001 --reload

# Terminal 2
cd local_server && python -m uvicorn main:app --port 8000 --reload
```

**Step 2 — Login and process a sale while online**
- Open http://localhost:8000/login and log in
- Submit a transaction via http://localhost:8000/new-transaction
- Dashboard should show it as `synced` within 10 seconds

**Step 3 — Go offline**
- Disconnect from the internet (turn off Wi-Fi or unplug ethernet)

**Step 4 — Process multiple sales while offline**
- Submit 2–3 more transactions
- They will appear on the dashboard with status `pending`

**Step 5 — Restart the application**
- Stop the local server (`CTRL+C`) and restart it
- All offline transactions are still there with status `pending`

**Step 6 — Restore internet**
- Reconnect to the internet
- Within 10 seconds all pending transactions will sync automatically
- Verify on the upstream: http://localhost:8001/transactions
