"""SQLite persistence for imported records."""
import sqlite3


CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS imported_records (
    external_id TEXT NOT NULL PRIMARY KEY CHECK (trim(external_id) <> ''),
    name        TEXT NOT NULL CHECK (trim(name) <> '')
)"""

UPSERT = """
INSERT INTO imported_records (external_id, name) VALUES (?, ?)
ON CONFLICT (external_id) DO UPDATE SET name = excluded.name"""


class SQLiteStore:
    def __init__(self, conn: sqlite3.Connection):
        """Use the supplied SQLite connection and create the table if it is missing."""
        self.conn = conn
        conn.execute(CREATE_TABLE)

    def upsert_many(self, records):
        """Insert or update a batch in one transaction so partial batches are not saved."""
        with self.conn:
            self.conn.executemany(
                UPSERT, [(record["external_id"].strip(), record["name"]) for record in records]
            )
