import asyncio
import logging
import httpx
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from pydantic import BaseModel

from circuit_breaker import CircuitBreaker, CircuitState

STUDENT_ID = "BSCS23212"
LLM_API_URL = "http://localhost:9999/generate"
LLM_TIMEOUT_SECONDS = 5.0
CB_FAILURE_THRESHOLD = 3
CB_RECOVERY_TIMEOUT = 10.0

FALLBACK_RESPONSE = {
    "source": "fallback",
    "message": "Our AI assistant is temporarily unavailable. Please try again in a few moments.",
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

llm_breaker = CircuitBreaker(
    name="llm-api",
    failure_threshold=CB_FAILURE_THRESHOLD,
    recovery_timeout=CB_RECOVERY_TIMEOUT,
    expected_exception=(httpx.RequestError, httpx.TimeoutException, Exception),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("StudySync backend starting up")
    yield
    logger.info("StudySync backend shutting down")


app = FastAPI(
    title="StudySync API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class StudentIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Student-ID"] = STUDENT_ID
        return response


app.add_middleware(StudentIDMiddleware)


class LLMRequest(BaseModel):
    prompt: str


async def _call_llm_api(prompt: str) -> dict:
    async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS) as client:
        resp = await client.post(LLM_API_URL, json={"prompt": prompt})
        resp.raise_for_status()
        return resp.json()


@app.get("/", tags=["health"])
async def root():
    return {"status": "ok", "service": "StudySync API"}


@app.get("/health", tags=["health"])
async def health():
    return {
        "status": "ok",
        "circuit_breaker": llm_breaker.status(),
    }


@app.post("/llm/ask", tags=["llm"])
async def ask_llm(payload: LLMRequest):
    if not payload.prompt:
        raise HTTPException(status_code=422, detail="'prompt' field is required")

    result = await llm_breaker.call(
        _call_llm_api,
        payload.prompt,
        fallback=FALLBACK_RESPONSE,
    )

    return JSONResponse(
        content={
            "result": result,
            "circuit_breaker_state": llm_breaker.status()["state"],
        }
    )


@app.get("/cb/status", tags=["circuit-breaker"])
async def cb_status():
    return llm_breaker.status()


@app.post("/cb/reset", tags=["circuit-breaker"])
async def cb_reset():
    llm_breaker._state = CircuitState.CLOSED
    llm_breaker._failure_count = 0
    llm_breaker._last_failure_time = None
    return {"message": "Circuit breaker reset", "state": llm_breaker.status()}