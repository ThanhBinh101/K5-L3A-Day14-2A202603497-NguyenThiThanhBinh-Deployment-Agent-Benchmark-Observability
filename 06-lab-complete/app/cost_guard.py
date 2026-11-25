"""Reserve estimated mock LLM cost against a shared daily budget."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from utils.mock_llm import MOCK_RESPONSES

from .config import settings
from .redis_client import r

NANODOLLARS_PER_USD = 1_000_000_000
INPUT_NANODOLLARS_PER_TOKEN = 150
OUTPUT_NANODOLLARS_PER_TOKEN = 600
MAX_MOCK_ANSWER_LENGTH = max(
    len(answer) for answers in MOCK_RESPONSES.values() for answer in answers
)

_reserve = r.register_script("""
local spent = tonumber(redis.call('GET', KEYS[1]) or '0')
if spent + tonumber(ARGV[1]) > tonumber(ARGV[2]) then
    return 0
end
redis.call('INCRBY', KEYS[1], ARGV[1])
redis.call('EXPIREAT', KEYS[1], ARGV[3])
return 1
""")

_refund = r.register_script("""
if redis.call('EXISTS', KEYS[1]) == 1 then
    redis.call('DECRBY', KEYS[1], ARGV[1])
end
""")


@dataclass(frozen=True)
class Reservation:
    redis_key: str
    amount: int
    input_length: int


def _estimated_cost(input_length: int, output_length: int) -> int:
    # The mock does not return token usage. Estimate one token per four characters.
    input_tokens = (input_length + 3) // 4
    output_tokens = (output_length + 3) // 4
    return input_tokens * INPUT_NANODOLLARS_PER_TOKEN + output_tokens * OUTPUT_NANODOLLARS_PER_TOKEN


def check_budget(question: str) -> Reservation:
    now = datetime.now(timezone.utc)
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    key = f"day14:cost:{now.date().isoformat()}"
    amount = _estimated_cost(len(question), MAX_MOCK_ANSWER_LENGTH)
    limit = int(settings.daily_budget_usd * NANODOLLARS_PER_USD)

    if not _reserve(keys=[key], args=[amount, limit, int(tomorrow.timestamp())]):
        raise HTTPException(status_code=402, detail="Daily budget exceeded")
    return Reservation(key, amount, len(question))


def record_cost(reservation: Reservation, answer: str) -> float:
    amount = _estimated_cost(reservation.input_length, len(answer))
    unused = reservation.amount - amount
    if unused:
        _refund(keys=[reservation.redis_key], args=[unused])
    return amount / NANODOLLARS_PER_USD


def cancel_reservation(reservation: Reservation) -> None:
    _refund(keys=[reservation.redis_key], args=[reservation.amount])
