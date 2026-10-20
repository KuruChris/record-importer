"""Retry-safe batched import for a rate-limited external service.

The service returns at most 25 records per request and allows at most
100 requests per day. ``import_records`` is the entry point.
"""

import time
from dataclasses import dataclass, field

# Maximum number of records handled by a single request.
BATCH_SIZE = 25
# Maximum number of requests the service allows per day.
DAILY_REQUEST_LIMIT = 100
# Retries after the first attempt, so a batch gets at most 5 attempts.
MAX_RETRIES = 4
# Delay in seconds before the first retry; it doubles on each retry
# (1, 2, 4, 8).
BASE_DELAY = 1.0
# Longest wait in seconds; give up rather than wait longer than this.
MAX_WAIT = 60.0

# A failure worth retrying, such as a timeout or an HTTP 5xx.
# Permanent errors, such as an HTTP 400, must not use this class.
class TemporaryAPIError(Exception):

# The service rejected a request with HTTP 429 (rate limited).
class RateLimitError(TemporaryAPIError):

    """Store the wait requested by the server.
        Args:
            retry_after: Seconds to wait, taken from the ``Retry-After``
            header, or None if the server did not send one.
    """
    def __init__(self, retry_after=None):
        
        super().__init__("rate limited")
        self.retry_after = retry_after


"""Outcome of one ``import_records`` run.

    Attributes:
    saved: Number of records written to the store.
    requests: Number of API requests made, including failed ones.
    remaining: Records not processed because the request budget ran
    out. Pass them to a later run.
"""
@dataclass
class ImportResult:

    saved: int = 0
    requests: int = 0
    remaining: list = field(default_factory=list)

"""Return how many seconds to wait before the next retry.

    A rate-limit error that carries ``retry_after`` uses the server's
    wait, so we never retry sooner than it asked. That value is not
    capped here; the caller decides whether it is too long. Any other
    error uses exponential backoff capped at ``MAX_WAIT``.

    Args:
        exc: The ``TemporaryAPIError`` that caused the retry.
        attempt: Number of retries already made for this batch,
            starting at 0.
"""
def _retry_delay(exc, attempt):
    
    if isinstance(exc, RateLimitError) and exc.retry_after is not None:
        return exc.retry_after
    return min(BASE_DELAY * 2**attempt, MAX_WAIT)

"""Import records in batches, retrying temporary failures.

    Records are split into batches of at most ``BATCH_SIZE``. Each batch
    costs one request, and every attempt counts toward ``max_requests``,
    including failed and rate-limited ones. A batch is saved before the
    next one starts.

    Args:
        records: List of records to import.
        call_api: Function that takes one batch (a list of records) and
            returns the records to save. It should raise
            ``TemporaryAPIError`` or ``RateLimitError`` for failures
            worth retrying.
        store: Object with an ``upsert_many(records)`` method.
        sleep: Function that waits for a number of seconds. Replace it
            in tests to avoid real waiting.
        max_requests: Request budget for this run.
        max_retries: Retries allowed per batch after the first attempt.

    Returns:
        An ``ImportResult``. If the budget runs out, ``remaining`` holds
        the records not yet saved, starting with the batch in progress,
        so a later run can continue with them.

    Raises:
        TemporaryAPIError: If a batch still fails after ``max_retries``
            retries, or the server asks for a wait longer than
            ``MAX_WAIT``. Batches saved earlier are kept.
"""
def import_records(records, call_api, store, *, sleep=time.sleep,
                   max_requests=DAILY_REQUEST_LIMIT,
                   max_retries=MAX_RETRIES):
    
    result = ImportResult()
    for start in range(0, len(records), BATCH_SIZE):
        batch = records[start:start + BATCH_SIZE]
        attempt, delay = 0, 0.0
        while True:
            # Check the budget before waiting, so we never sleep for a
            # request we cannot afford to make.
            if result.requests >= max_requests:
                result.remaining = records[start:]
                return result
            if delay:
                sleep(delay)
            # Count the request before sending it: failed attempts and
            # HTTP 429 responses use up the daily allowance too.
            result.requests += 1
            try:
                fetched = call_api(batch)
                break
            except TemporaryAPIError as exc:
                delay = _retry_delay(exc, attempt)
                # Stop when retries run out or the server wants a longer
                # wait than we accept. The caller can run again later.
                if attempt >= max_retries or delay > MAX_WAIT:
                    raise
                attempt += 1
        store.upsert_many(fetched)
        result.saved += len(fetched)
    return result