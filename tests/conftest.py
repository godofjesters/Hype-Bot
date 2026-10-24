from __future__ import annotations

import os
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient


# Set deterministic test-only credentials before importing the application.
os.environ["ADMIN_USERNAME"] = "test-admin"
os.environ["ADMIN_PASSWORD"] = "test-password-for-local-suite"
os.environ["APP_SECRET"] = "test-session-secret-that-is-long-enough-123456"
os.environ["APP_ENCRYPTION_KEY"] = "test-encryption-secret-that-is-long-enough-123456"
os.environ["COOKIE_SECURE"] = "false"


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    main.initialize_database()
    return main


@pytest.fixture
def client(app_env):
    @asynccontextmanager
    async def no_background_workers(_app):
        yield

    app_env.app.router.lifespan_context = no_background_workers
    with TestClient(app_env.app) as test_client:
        yield test_client


@pytest.fixture
def authenticated_client(client):
    import re

    response = client.get("/login")
    csrf = re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)
    response = client.post(
        "/login",
        data={"username": "test-admin", "password": "test-password-for-local-suite", "csrf": csrf},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return client
