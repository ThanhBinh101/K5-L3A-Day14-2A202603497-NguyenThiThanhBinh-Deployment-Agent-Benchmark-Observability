"""Production FastAPI entry point for the mock agent."""

import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from redis.exceptions import RedisError

from utils.mock_llm import ask as llm_ask

from .auth import verify_api_key
from .config import settings
from .cost_guard import cancel_reservation, check_budget, record_cost
from .rate_limiter import check_rate_limit
from .redis_client import r, redis_healthy

logger = logging.getLogger(__name__)
logger.setLevel(settings.log_level)
logger.addHandler(logging.StreamHandler())
logger.propagate = False


def log_event(event: str, **fields) -> None:
    logger.info(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "event": event, **fields}))


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_event("startup", environment=settings.environment)
    try:
        yield
    finally:
        # Uvicorn drains current requests before invoking lifespan shutdown.
        r.close()
        log_event("shutdown")


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@app.middleware("http")
async def request_log(request: Request, call_next):
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        log_event(
            "request",
            method=request.method,
            path=request.url.path,
            status=status,
            ms=round((time.perf_counter() - start) * 1000, 2),
        )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis is unavailable")
    return {"ready": True}


@app.post("/ask")
def ask(body: AskRequest, key: str = Depends(verify_api_key)):
    try:
        check_rate_limit(key)
        reservation = check_budget(body.question)
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Redis is unavailable") from exc

    try:
        answer = llm_ask(body.question)
    except Exception:
        try:
            cancel_reservation(reservation)
        except RedisError:
            log_event("reservation_cancel_failed")
        raise

    try:
        record_cost(reservation, answer)
    except RedisError:
        # A reservation was already charged, so return the answer even if refunding fails.
        log_event("cost_settlement_failed")
    return {"question": body.question, "answer": answer}
