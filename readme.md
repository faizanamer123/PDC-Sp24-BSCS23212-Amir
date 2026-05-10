# Faizan Amir | BSCS23212

## PDC-Sp24-BSCS23212-Amir

### StudySync — Resilient Distributed Systems (Assignment 2)

---

## Overview

This repository is the Part 3 implementation for PDC Assignment 2.
It demonstrates the **Circuit Breaker** pattern to fix the Fault Tolerance bug
in the StudySync FastAPI backend.

**Problem fixed:** The synchronous LLM call blocks the server for up to 60 seconds
on timeout, making the app unresponsive for all users.

**Fix:** A Circuit Breaker wraps every LLM call. After 3 consecutive failures the
circuit opens and subsequent requests receive an instant fallback response,
keeping the app responsive.

---

## Project Structure

```
.
├── main.py              # FastAPI app with CB middleware and routes
├── circuit_breaker.py   # Circuit Breaker implementation (CLOSED/OPEN/HALF_OPEN)
├── test.py  # Test script — demonstrates failure vs. fixed behaviour
└── README.md
```

---

## Setup & Installation

**Requirements:** Python 3.10+

```bash
# Clone the repo
git clone https://github.com/<your-username>/PDC-Sp24-BSCS23212-Amir.git
cd PDC-Sp24-BSCS23212-Amir

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install fastapi uvicorn httpx
```

---

## Running the Server

```bash
# Start the FastAPI server
uvicorn main:app --reload --port 8000
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive API docs.

**Important:** The student ID `BSCS23212` is already set in `main.py`. Every API response will include the header:
```
X-Student-ID: BSCS23212
```

---

## Running the Tests

The test script does **not** require the server to be running. It exercises the
`CircuitBreaker` class directly and simulates an LLM that always times out.

```bash
python test_circuit_breaker.py
```

**What the test shows:**

| Scenario | Description |
|---|---|
| A — No CB | Every request waits the full timeout. Total time ≈ N × timeout. App hangs. |
| B — With CB | Circuit opens after 3 failures. Later requests return instantly via fallback. |
| C — Recovery | After the recovery timeout, the circuit probes the LLM and closes on success. |
| Header test | Verifies `X-Student-ID` header appears on all endpoints (requires server). |

**Example output:**

```
SCENARIO A — WITHOUT Circuit Breaker
  Request 01 | FAILED after 1.00s | TimeoutException
  Request 02 | FAILED after 1.00s | TimeoutException
  ...
  Total time: 8.00s  (8 requests × ~1.0s each)
  → Server was BLOCKED the entire time. All users affected.

SCENARIO B — WITH Circuit Breaker
  Request 01 | 1.001s | CB=CLOSED    | FALLBACK (slow)
  Request 02 | 1.001s | CB=CLOSED    | FALLBACK (slow)
  Request 03 | 1.001s | CB=OPEN      | FALLBACK (slow)
  Request 04 | 0.000s | CB=OPEN      | FALLBACK (fast)
  Request 05 | 0.000s | CB=OPEN      | FALLBACK (fast)
  ...
  Total time: 3.00s
  → App stayed responsive throughout.
```

---

## Key Design Decisions

- **No external dependencies** for the circuit breaker itself — pure Python + asyncio.
- **Hard timeout** (5s) on every LLM call via `httpx.AsyncClient(timeout=5.0)` prevents
  any request from ever blocking for 60s.
- **Fallback** returns a user-friendly message rather than a raw error.
- **Middleware** ensures `X-Student-ID` is injected at the framework level — impossible
  to forget on individual routes.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Health check |
| GET | `/health` | Health + CB status |
| POST | `/llm/ask` | Ask LLM (CB-protected) |
| GET | `/cb/status` | Circuit breaker state |
| POST | `/cb/reset` | Reset CB to CLOSED (demo use) |