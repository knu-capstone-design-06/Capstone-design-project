"""Short-lived TLS connections for the private Supabase kiosk schema."""

import psycopg
from psycopg.rows import dict_row


class PostgresDatabase:
    def __init__(self, url: str):
        self._url = url

    def connect(self) -> psycopg.Connection:
        # Session pooler supports transactions and prepared statements; disabling
        # preparation also permits the same code to run with a transaction pooler.
        return psycopg.connect(
            self._url, row_factory=dict_row, connect_timeout=5,
            sslmode="require", prepare_threshold=None,
        )

    def check(self) -> None:
        with self.connect() as connection:
            row = connection.execute("select current_user as role").fetchone()
            if row is None or row["role"] != "kiosk_backend":
                raise RuntimeError("DATABASE_URL must authenticate as kiosk_backend")
