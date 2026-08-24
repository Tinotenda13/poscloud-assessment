# POSCloud – Offline Retail Transaction System

## Technologies

| Layer | Technology |
|-------|------------|
| Local server | FastAPI, SQLite (via aiosqlite) |
| Upstream server | FastAPI, PostgreSQL (via asyncpg) |
| ORM | SQLAlchemy (async) |
| Background sync | APScheduler |
| HTTP client | HTTPX |
| UI | Jinja2 templates |

---

## Architecture

```
[Cashier / Browser UI]
        │
        ▼
 local_server  (FastAPI + SQLite, port 8000)   ← always available, offline-first
        │  background sync every 10s (only when online)
        ▼
upstream_server (FastAPI + PostgreSQL, port 8001)   ← central server
```

- The **local server** runs on the POS device. Transactions are always written to a local SQLite file (`local_pos.db`) first — no network required.
- A background scheduler checks internet connectivity every 10 seconds by pinging `google.com`. If online, it pushes all `pending` transactions to the upstream server.
- The **upstream server** uses PostgreSQL and enforces a `UNIQUE` constraint on `idempotency_key` — duplicate pushes return `409` and are safely ignored.
- Both `201` and `409` responses from upstream cause the local record to be marked `synced`.
- If connectivity drops mid-sync, remaining `pending` records are retried on the next scheduler tick.
- SQLite persists to disk — transactions survive application and device restarts.

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

### 6. Activate venv python environment
```
venv\Scripts\activate   

```

### 6.1 Run upstream server (port 8001)
```bash
cd upstream_server
python -m uvicorn main:app --port 8001 --reload
```

### 7. Run local server (port 8000) — in a new terminal
```bash


cd local_server

python -m uvicorn main:app --port 8000 --reload
```

Open http://localhost:8000 in your browser.

---

## Local Storage Approach

The local server uses **SQLite** via `aiosqlite`. The database file (`local_pos.db`) lives on the device filesystem. This means:
- No database server required on the device
- Transactions persist across application and device restarts
- Works completely without any network connection

---

## Synchronization Strategy

1. On startup, APScheduler registers a job that runs `sync_pending_transactions()` every 10 seconds.
2. Before attempting sync, the function pings `https://www.google.com` with a 3-second timeout. If it fails, sync is skipped and retried on the next tick.
3. If online, all transactions with `sync_status = pending` are fetched and pushed one by one to the upstream `/transactions` endpoint.
4. A `201` (created) or `409` (already exists) response both result in the local record being marked `synced`.
5. Any network error during sync stops the loop — already-synced records keep their status and remaining `pending` records are retried next cycle.

---

## Key Technical Decisions

| Concern | Decision | Reasoning |
|---------|----------|-----------|
| Local storage | SQLite | File-based, zero-config, survives restarts, no server needed on device |
| Upstream storage | PostgreSQL | Robust, production-grade central database |
| Duplicate prevention | UUID `idempotency_key` + `UNIQUE` constraint on both DBs | Retrying a sync never creates duplicates |
| Connectivity check | Ping `google.com` | Simple, reliable way to simulate offline by toggling internet |
| Sync trigger | APScheduler every 10s | Automatic recovery without manual intervention |
| Mid-sync recovery | Mark `synced` only after confirmed upstream response | Guarantees no silent data loss |

---

## Test Scenario

### Online → Process Sale → Go Offline → Process Multiple Sales → Restart → Restore Internet → Auto Sync

**Step 1 — Start both servers**
```bash
# Terminal 1
cd upstream_server && python -m uvicorn main:app --port 8001 --reload

# Terminal 2
cd local_server && python -m uvicorn main:app --port 8000 --reload
```

**Step 2 — Process a sale while online**
- Open http://localhost:8000/new-transaction
- Submit a transaction (e.g. Cashier: Alice, Amount: 25.00, Description: Coffee)
- Go to http://localhost:8000 — the transaction should show `synced` within 10 seconds

**Step 3 — Go offline**
- Disconnect your machine from the internet (turn off Wi-Fi or unplug ethernet)

**Step 4 — Process multiple sales while offline**
- Submit 2–3 more transactions via http://localhost:8000/new-transaction
- They will appear on the dashboard with status `pending`
- The local server logs will show: `No internet connection, skipping sync.`

**Step 5 — Restart the application**
- Stop the local server (`CTRL+C`)
- Restart it: `python -m uvicorn main:app --port 8000 --reload`
- Open http://localhost:8000 — all offline transactions are still there with status `pending`

**Step 6 — Restore internet**
- Reconnect to the internet
- Within 10 seconds the scheduler will sync all pending transactions
- Refresh http://localhost:8000 — all transactions now show `synced`
- Verify on the upstream: http://localhost:8001/transactions
