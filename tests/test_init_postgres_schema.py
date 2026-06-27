from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_init_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "init-postgres-schema.py"
    spec = importlib.util.spec_from_file_location("init_postgres_schema", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakePool:
    def __init__(self, connection):
        self._connection = connection
        self.closed = False

    def connection(self):
        return FakeConnectionContext(self._connection)


def test_main_reads_database_url_from_env_and_initializes_schema(monkeypatch):
    module = load_init_module()
    connection = object()
    pool = FakePool(connection)
    created_urls = []
    initialized_connections = []
    closed_pools = []
    monkeypatch.setenv("DATABASE_URL", "postgresql://from-env/db")
    monkeypatch.delenv("DATABASE_URL_FILE", raising=False)
    monkeypatch.setattr(module, "create_postgres_pool", lambda url, min_size, max_size: created_urls.append(url) or pool)
    monkeypatch.setattr(module, "initialize_postgres_schema", lambda conn: initialized_connections.append(conn))
    monkeypatch.setattr(module, "close_postgres_pool", lambda closed_pool: closed_pools.append(closed_pool))

    assert module.main([]) == 0

    assert created_urls == ["postgresql://from-env/db"]
    assert initialized_connections == [connection]
    assert closed_pools == [pool]


def test_main_prefers_database_url_file(monkeypatch, tmp_path):
    module = load_init_module()
    secret_file = tmp_path / "database_url"
    secret_file.write_text("postgresql://from-file/db\n", encoding="utf-8")
    connection = object()
    pool = FakePool(connection)
    created_urls = []
    monkeypatch.setenv("DATABASE_URL", "postgresql://from-env/db")
    monkeypatch.setenv("DATABASE_URL_FILE", str(secret_file))
    monkeypatch.setattr(module, "create_postgres_pool", lambda url, min_size, max_size: created_urls.append(url) or pool)
    monkeypatch.setattr(module, "initialize_postgres_schema", lambda conn: None)
    monkeypatch.setattr(module, "close_postgres_pool", lambda closed_pool: None)

    assert module.main([]) == 0

    assert created_urls == ["postgresql://from-file/db"]
