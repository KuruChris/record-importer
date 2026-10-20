"""Retry-safe batched import: at most 25 records per request, at most 100 requests per day."""
import sqlite3
import time
from dataclasses import dataclass, field

from sample_data import SAMPLE_RECORDS

BATCH_SIZE = 25             # the service returns at most 25 records per request
DAILY_REQUEST_LIMIT = 100   # the service allows at most 100 requests per day
MAX_RETRIES = 4             # retries after the first attempt (so at most 5 attempts per batch)
BASE_DELAY = 1.0            # seconds; doubles on each retry: 1, 2, 4, 8
MAX_WAIT = 60.0             # never wait longer than this; give up instead

class TemporaryAPIError(Exception):
    """Retryable failure (timeout, 5xx). Permanent errors such as a 400 should NOT use this."""


class RateLimitError(TemporaryAPIError):
    """HTTP 429. ``retry_after`` is the Retry-After header in seconds, if the server sent one."""

    def __init__(self, retry_after=None):
        super().__init__("rate limited")
        self.retry_after = retry_after


@dataclass
class ImportResult:
    saved: int = 0
    requests: int = 0
    remaining: list = field(default_factory=list)  # not imported yet: feed to the next run


def _retry_delay(exc, attempt):
    if isinstance(exc, RateLimitError) and exc.retry_after is not None:
        return exc.retry_after                      # never retry sooner than the server asked
    return min(BASE_DELAY * 2**attempt, MAX_WAIT)   # otherwise exponential backoff, capped


def import_records(records, call_api, store, *, sleep=time.sleep,
                   max_requests=DAILY_REQUEST_LIMIT, max_retries=MAX_RETRIES):
    """Process ``records`` in batches of <= 25: one API request per batch, then upsert it.

    Returns an ImportResult. If the daily budget runs out it stops cleanly and returns the
    unprocessed records in ``remaining``. Raises if a batch still fails after its retries.
    """
    result = ImportResult()
    for start in range(0, len(records), BATCH_SIZE):
        batch = records[start:start + BATCH_SIZE]
        attempt, delay = 0, 0.0
        while True:
            if result.requests >= max_requests:     # checked BEFORE waiting or calling
                result.remaining = records[start:]
                return result
            if delay:
                sleep(delay)
            result.requests += 1                    # every attempt counts, even failures and 429s
            try:
                fetched = call_api(batch)
                break
            except TemporaryAPIError as exc:
                delay = _retry_delay(exc, attempt)
                if attempt >= max_retries or delay > MAX_WAIT:
                    raise                           # no endless retries, no hammering a 429
                attempt += 1
        store.upsert_many(fetched)                  # saved before moving to the next batch
        result.saved += len(fetched)
    return result


# --- persistence -----------------------------------------------------------------------
# The PRIMARY KEY on external_id is the duplicate guard; ON CONFLICT turns a repeat insert
# into an update. Same statement in PostgreSQL with %s placeholders and EXCLUDED.name.
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS imported_records (
    external_id TEXT NOT NULL PRIMARY KEY CHECK (trim(external_id) <> ''),
    name        TEXT NOT NULL CHECK (trim(name) <> '')
)"""
UPSERT = """
INSERT INTO imported_records (external_id, name) VALUES (?, ?)
ON CONFLICT (external_id) DO UPDATE SET name = excluded.name"""


class SQLiteStore:
    def __init__(self, conn):
        self.conn = conn
        conn.execute(CREATE_TABLE)

    def upsert_many(self, records):
        with self.conn:  # one transaction per batch: all rows are saved or none are
            self.conn.executemany(
                UPSERT, [(r["external_id"].strip(), r["name"]) for r in records]
            )


if __name__ == "__main__":
    store = SQLiteStore(sqlite3.connect(":memory:"))
    result = import_records(SAMPLE_RECORDS, lambda batch: batch, store)  # mock API echoes batch
    print(f"Saved {result.saved} record(s) in {result.requests} request(s); "
          f"{len(result.remaining)} left over.")
    print(store.conn.execute("SELECT * FROM imported_records ORDER BY 1").fetchall())
