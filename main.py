"""Run the importer example with the starter records and a mock API."""
import sqlite3

from importer import import_records
from sample_data import SAMPLE_RECORDS
from storage import SQLiteStore

# Echo the batch to demonstrate the importer without making a real API request.
if __name__ == "__main__":
    store = SQLiteStore(sqlite3.connect(":memory:"))
    result = import_records(SAMPLE_RECORDS, lambda batch: batch, store)
    print(f"Saved {result.saved} record(s) in {result.requests} request(s); "
          f"{len(result.remaining)} left over.")
    print(store.conn.execute("SELECT * FROM imported_records ORDER BY 1").fetchall())
