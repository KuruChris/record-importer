# Batched importer
A dependency-free Python(standard library plus `pytest` for tests) example demonstrating offset/limit 
pagination, retry handling, request-budget accounting, input validation, and idempotent upserts.

## Setup

If Python is not installed, download and install the latest Python 3 release from
[python.org](https://www.python.org/downloads/). On Windows, check **Add python.exe to PATH**
in the installer before selecting **Install Now**.

Open a terminal and verify Python is available:

```bash
python --version
```

If that command is not recognized on Windows, try `py --version`. Use `py` instead of
`python` in the commands below if needed.

Install the test dependency and run the example and tests:

```bash
python main.py         # runs the example with the four starter records
pip install pytest
pytest -q              # all external calls are mocked; no network, no real database
```

## Project structure

- `importer.py` contains batching, request limits, and retry behavior.
- `storage.py` contains the SQLite schema and `SQLiteStore` upsert implementation.
- `main.py` wires the sample data, importer, and in-memory store for the runnable demo.
- `sample_data.py` contains the starter records.

## Assumptions

- `import_records(records, call_api, store)` takes a **list of records** and sends it in
  batches of at most 25. **One batch = one request** to the external service, and
  `call_api(batch)` returns the records to save. In the tests and demo the API is a mock.
  If the real service is pull-based (offset/limit), only the batching line changes.
- Only temporary failures (timeouts, 5xx, HTTP 429) should be raised as `TemporaryAPIError` /
  `RateLimitError` by a real API client. Permanent errors such as a 400 are not retried.
- SQLite in memory stands in for the internal database. The SQL is also valid PostgreSQL
  (use `%s` placeholders and `EXCLUDED.name`).

## How it works

**Daily limit (100 requests).** A counter is checked before *every* attempt, so retries,
failures and 429s all count. When the budget is spent the function stops cleanly *before*
waiting or calling, and returns the unprocessed records in `result.remaining` for the next
day's run. One run therefore never uses more than 100 requests (at most 2,500 records).

**Retries.** Only `TemporaryAPIError` is retried, at most 4 times per batch (5 attempts).
The wait doubles each time (1s, 2s, 4s, 8s, capped at 60s). For a 429 the server's
`Retry-After` is used instead, because retrying earlier would just be rejected again. If
`Retry-After` is longer than the 60s cap, or the retries run out, the error is raised
rather than retrying forever. `sleep` is injectable, so tests do not really wait.

**No duplicates.** `external_id` is the table's `PRIMARY KEY`. The upsert
`INSERT ... ON CONFLICT (external_id) DO UPDATE SET name = excluded.name` turns a repeat
into an update, so re-running or retrying never creates a second row. IDs are stripped
of stray whitespace, and `CHECK` constraints reject blank IDs and names. Each batch is
saved in one transaction (all rows or none), and a batch is only saved after its API
call succeeds.

## Before deploying to production

1. **Safe resume and a durable request counter.** The request counter lives in memory, so a
   restart resets it, and a rerun starts from the first record again. That is harmless
   (the upsert is idempotent) but wastes requests. I would store the day's request count and
   a checkpoint (last saved batch or cursor) in the database, in the same transaction as
   each batch.
2. **Logging and monitoring.** Log each attempt (batch, attempt number, outcome, wait),
   count 429s and failures, and alert when the budget runs low or an import stops with
   records remaining or raises.

## Deliberate simplifications

No jitter on the backoff (it matters with many parallel workers, not one importer), no
input-validation layer beyond the database constraints, and no persistence of the budget.

## AI tools disclosure
1. Claude Code (CLI) – Claude Opus 5.5: Mostlty used as an AI-assisted development for code refactoring, improving code readability and maintainability while maintaining strict rules/guardrails. All AI suggestions and code changes was reviewed, validated and tested before being incorporated in the codebase.