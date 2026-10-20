import sqlite3

import pytest

from importer import (
    BATCH_SIZE,
    RateLimitError,
    SQLiteStore,
    TemporaryAPIError,
    import_records,
)
from sample_data import SAMPLE_RECORDS

# Expectations are derived from SAMPLE_RECORDS, so the tests keep working if you add data.
EXPECTED_ROWS = sorted((r["external_id"], r["name"]) for r in SAMPLE_RECORDS)
BATCHES = -(-len(SAMPLE_RECORDS) // BATCH_SIZE)  # ceiling division: 4 -> 1, 30 -> 2, 51 -> 3


def no_sleep(_seconds):
    pass


@pytest.fixture
def store():
    return SQLiteStore(sqlite3.connect(":memory:"))


def rows(store):
    return store.conn.execute("SELECT external_id, name FROM imported_records ORDER BY 1").fetchall()


def make_records(n):
    return [{"external_id": f"ID-{i}", "name": f"Item {i}"} for i in range(n)]


def fake_api(*errors):
    """Mock API (no network): raises the given errors one by one, then echoes each batch."""
    pending, batch_sizes = list(errors), []

    def call_api(batch):
        batch_sizes.append(len(batch))
        if pending:
            raise pending.pop(0)
        return batch

    call_api.batch_sizes = batch_sizes
    return call_api
    

def test_imports_sample_records(store):
    result = import_records(SAMPLE_RECORDS, fake_api(), store, sleep=no_sleep)
    assert rows(store) == EXPECTED_ROWS
    assert (result.saved, result.requests, result.remaining) == (len(SAMPLE_RECORDS), BATCHES, [])


def test_splits_records_into_batches_of_25(store):
    api = fake_api()
    import_records(make_records(60), api, store, sleep=no_sleep)
    assert api.batch_sizes == [25, 25, 10]


def test_temporary_error_is_retried_with_exponential_backoff(store):
    sleeps = []
    api = fake_api(TemporaryAPIError(), TemporaryAPIError())
    result = import_records(SAMPLE_RECORDS, api, store, sleep=sleeps.append)
    assert sleeps == [1.0, 2.0]
    assert result.saved == len(SAMPLE_RECORDS)
    assert result.requests == 2 + BATCHES  # 2 failed attempts + 1 successful request per batch


def test_429_waits_for_retry_after(store):
    sleeps = []
    import_records(SAMPLE_RECORDS, fake_api(RateLimitError(retry_after=7)), store,
                   sleep=sleeps.append)
    assert sleeps == [7]


def test_gives_up_after_max_retries(store):
    api = fake_api(*[TemporaryAPIError()] * 10)
    with pytest.raises(TemporaryAPIError):
        import_records(SAMPLE_RECORDS, api, store, sleep=no_sleep, max_retries=2)
    assert len(api.batch_sizes) == 3  # first attempt + 2 retries
    assert rows(store) == []


def test_does_not_wait_when_retry_after_is_too_long(store):
    sleeps = []
    with pytest.raises(RateLimitError):
        import_records(SAMPLE_RECORDS, fake_api(RateLimitError(retry_after=3600)), store,
                       sleep=sleeps.append)
    assert sleeps == []


def test_daily_limit_counts_failed_attempts_and_returns_the_rest(store):
    records = make_records(60)
    api = fake_api(TemporaryAPIError())  # 1st attempt fails, so 2 requests deliver only 1 batch
    result = import_records(records, api, store, sleep=no_sleep, max_requests=2)
    assert (result.requests, result.saved) == (2, 25)
    assert result.remaining == records[25:]


def test_does_not_wait_for_a_retry_it_cannot_afford(store):
    sleeps = []
    api = fake_api(*[TemporaryAPIError()] * 10)
    result = import_records(SAMPLE_RECORDS, api, store, sleep=sleeps.append, max_requests=2)
    assert sleeps == [1.0]  # one wait between the 2 attempts, none after the budget is gone
    assert result.remaining == SAMPLE_RECORDS


def test_rerun_does_not_duplicate_and_updates_existing(store):
    import_records(SAMPLE_RECORDS, fake_api(), store, sleep=no_sleep)
    import_records(SAMPLE_RECORDS, fake_api(), store, sleep=no_sleep)
    assert len(rows(store)) == len(SAMPLE_RECORDS)
    import_records([{"external_id": "SB-1001", "name": "Notebook A5"}], fake_api(), store,
                   sleep=no_sleep)
    assert ("SB-1001", "Notebook A5") in rows(store) and len(rows(store)) == len(SAMPLE_RECORDS)


def test_ids_with_stray_whitespace_do_not_create_duplicates(store):
    store.upsert_many([{"external_id": "SB-1 ", "name": "A"}, {"external_id": "SB-1", "name": "A"}])
    assert rows(store) == [("SB-1", "A")]


def test_a_bad_row_rolls_back_the_whole_batch(store):
    with pytest.raises(sqlite3.IntegrityError):
        store.upsert_many([{"external_id": "OK-1", "name": "fine"},
                           {"external_id": "BAD-1", "name": "   "}])
    assert rows(store) == []