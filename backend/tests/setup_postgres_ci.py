"""Prepare only a fresh local PostgreSQL service for ordering integration tests."""

import os
from pathlib import Path
from urllib.parse import urlsplit

import psycopg


def local_url(name: str) -> str:
    url = os.environ[name]
    if urlsplit(url).hostname not in {"localhost", "127.0.0.1"}:
        raise RuntimeError(f"{name} must point to an isolated local PostgreSQL service")
    return url


def main() -> None:
    admin_url = local_url("TEST_ADMIN_URL")
    role_url = local_url("TEST_DATABASE_URL")
    root = Path(__file__).resolve().parents[2]
    migrations = [
        "20261007072436_create_kiosk_sessions.sql",
        "20261012110139_grant_kiosk_backend_session_access.sql",
        "20261101092640_create_order_storage.sql",
    ]
    with psycopg.connect(admin_url, autocommit=True, prepare_threshold=None) as connection:
        connection.execute("create role anon")
        connection.execute("create role authenticated")
        for name in migrations:
            connection.execute((root / "db" / "migration" / name).read_text(encoding="utf-8"))
        connection.execute(
            (root / "db" / "seed" / "20261101_demo_catalog.sql").read_text(encoding="utf-8"),
        )
    with psycopg.connect(role_url, sslmode="disable") as connection:
        count = connection.execute("select count(*) from kiosk.products").fetchone()[0]
    if count != 17:
        raise RuntimeError(f"expected 17 demo products, found {count}")
    print("Disposable ordering schema and 17 demo products ready")


if __name__ == "__main__":
    main()
