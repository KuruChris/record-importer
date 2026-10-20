"""Retry-safe batched import: at most 25 records per request, at most 100 requests per day."""
import time
from dataclasses import dataclass, field

# The service accepts at most 25 records per request.
BATCH_SIZE = 25
# The service allows at most 100 requests per day.
DAILY_REQUEST_LIMIT = 100
# Retries after the first attempt, so a batch gets at most 5 attempts.
MAX_RETRIES = 4
# Delay in seconds; doubles on each retry: 1, 2, 4, 8.
BASE_DELAY = 1.0
# Give up rather than wait longer than this.
MAX_WAIT = 60.0

class TemporaryAPIError(Exception):
    """Retryable failure (timeout, 5xx). Permanent errors such as a 400 should NOT use this."""


class RateLimitError(TemporaryAPIError):
    """HTTP 429. ``retry_after`` is the Retry-After header in seconds, if the server sent one."""

    def __init__(self, retry_after=None):
        """Keep the server's requested wait so retries respect its rate limit."""
        super().__init__("rate limited")
        self.retry_after = retry_after


@dataclass
class ImportResult:
    """Summarize saved records, requests used, and records left for a later run."""

    saved: int = 0
    requests: int = 0
    remaining: list = field(default_factory=list)


def _retry_delay(exc, attempt):
    """Use the server's requested delay for rate limits; otherwise apply capped backoff."""
    if isinstance(exc, RateLimitError) and exc.retry_after is not None:
        return exc.retry_after
    return min(BASE_DELAY * 2**attempt, MAX_WAIT)


def import_records(records, call_api, store, *, sleep=time.sleep,
                   max_requests=DAILY_REQUEST_LIMIT, max_retries=MAX_RETRIES):
    """Import records in batches, retrying temporary failures within the request budget.

    Every attempt counts toward ``max_requests``. Successful batches are saved before the
    next starts; if the budget runs out, unprocessed records are returned in ``remaining``.
    ``sleep`` is injectable so retry timing can be tested without waiting.
    """
    result = ImportResult()
    for start in range(0, len(records), BATCH_SIZE):
        batch = records[start:start + BATCH_SIZE]
        attempt, delay = 0, 0.0
        while True:
            # Check the budget before waiting or sending another request.
            if result.requests >= max_requests:
                result.remaining = records[start:]
                return result
            if delay:
                sleep(delay)
            # Failed requests and rate limits still consume the daily allowance.
            result.requests += 1
            try:
                fetched = call_api(batch)
                break
            except TemporaryAPIError as exc:
                delay = _retry_delay(exc, attempt)
                if attempt >= max_retries or delay > MAX_WAIT:
                    raise
                attempt += 1
        # Save each successful batch before starting another one.
        store.upsert_many(fetched)
        result.saved += len(fetched)
    return result
