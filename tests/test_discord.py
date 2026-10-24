from __future__ import annotations

import re
import sqlite3

from app.destinations import DestinationError


UPLOAD_WEBHOOK = "https://discord.com/api/webhooks/111/upload-secret"
STREAM_WEBHOOK = "https://discord.com/api/webhooks/222/stream-secret"


def csrf_from(client, path="/notifications/discord"):
    response = client.get(path)
    assert response.status_code == 200
    match = re.search(r'name="csrf" value="([^"]+)"', response.text)
    assert match
    return match.group(1)


def save_webhooks(client, upload=UPLOAD_WEBHOOK, stream=STREAM_WEBHOOK):
    return client.post(
        "/destinations/discord",
        data={"upload_webhook": upload, "stream_webhook": stream, "csrf": csrf_from(client)},
        follow_redirects=False,
    )


def test_discord_webhooks_are_saved_encrypted_and_split(authenticated_client, app_env):
    app_env.store_secret("discord_webhook", "https://discord.com/api/webhooks/old/legacy")

    response = save_webhooks(authenticated_client)

    assert response.status_code == 303
    assert app_env.load_secret("discord_upload_webhook") == UPLOAD_WEBHOOK
    assert app_env.load_secret("discord_stream_webhook") == STREAM_WEBHOOK
    assert app_env.load_secret("discord_webhook") is None
    with sqlite3.connect(app_env.DB_PATH) as connection:
        stored_values = [row[0] for row in connection.execute(
            "SELECT value FROM app_meta WHERE key LIKE 'secret:discord_%'"
        )]
    assert UPLOAD_WEBHOOK not in stored_values
    assert STREAM_WEBHOOK not in stored_values
    assert all(not value.startswith("https://") for value in stored_values)


def test_invalid_webhook_does_not_partially_replace_saved_values(authenticated_client, app_env):
    app_env.store_secret("discord_upload_webhook", "https://discord.com/api/webhooks/original/upload")
    app_env.store_secret("discord_stream_webhook", "https://discord.com/api/webhooks/original/stream")

    response = save_webhooks(authenticated_client, upload=UPLOAD_WEBHOOK, stream="https://example.com/not-a-webhook")

    assert response.status_code == 303
    assert "error=discord_url" in response.headers["location"]
    assert app_env.load_secret("discord_upload_webhook") == "https://discord.com/api/webhooks/original/upload"
    assert app_env.load_secret("discord_stream_webhook") == "https://discord.com/api/webhooks/original/stream"


def test_discord_save_requires_authentication_and_csrf(client):
    response = client.post(
        "/destinations/discord",
        data={"upload_webhook": UPLOAD_WEBHOOK, "stream_webhook": STREAM_WEBHOOK, "csrf": "invalid"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_upload_and_stream_deliveries_use_their_matching_webhooks(authenticated_client, app_env, monkeypatch):
    save_webhooks(authenticated_client)
    calls = []
    monkeypatch.setattr(app_env, "discord_send", lambda webhook, message: calls.append((webhook, message)))
    with app_env.db_connection() as connection:
        connection.execute(
            "INSERT INTO channels(channel_id,title,uploads_playlist,added_at) VALUES(?,?,?,?)",
            ("channel-1", "Example Channel", "playlist-1", "2026-01-01T00:00:00+00:00"),
        )
        for kind in ("upload", "stream"):
            cursor = connection.execute(
                "INSERT INTO monitored_events(channel_id,video_id,event_type,title,url,event_time) VALUES(?,?,?,?,?,?)",
                ("channel-1", f"video-{kind}", kind, f"{kind.title()} title", "https://youtube.com/watch?v=x", "2026-10-01T00:00:00+00:00"),
            )
            connection.execute(
                "INSERT INTO deliveries(event_id,destination,status,updated_at) VALUES(?,'discord','pending','now')",
                (cursor.lastrowid,),
            )
        delivery_ids = [row[0] for row in connection.execute("SELECT id FROM deliveries ORDER BY id")]

    for delivery_id in delivery_ids:
        app_env._deliver(delivery_id)

    assert [call[0] for call in calls] == [UPLOAD_WEBHOOK, STREAM_WEBHOOK]
    assert "Upload title" in calls[0][1]
    assert "Stream title" in calls[1][1]
    with app_env.db_connection() as connection:
        assert [row[0] for row in connection.execute("SELECT status FROM deliveries ORDER BY id")] == ["sent", "sent"]


def test_retryable_discord_failure_records_failure_and_retry_time(authenticated_client, app_env, monkeypatch):
    save_webhooks(authenticated_client)

    def fail_send(_webhook, _message):
        raise DestinationError("Discord returned HTTP 503.", retryable=True)

    monkeypatch.setattr(app_env, "discord_send", fail_send)
    with app_env.db_connection() as connection:
        connection.execute(
            "INSERT INTO channels(channel_id,title,uploads_playlist,added_at) VALUES(?,?,?,?)",
            ("channel-1", "Example Channel", "playlist-1", "2026-01-01T00:00:00+00:00"),
        )
        cursor = connection.execute(
            "INSERT INTO monitored_events(channel_id,video_id,event_type,title,url,event_time) VALUES(?,?,?,?,?,?)",
            ("channel-1", "video-1", "upload", "Test title", "https://youtube.com/watch?v=x", "2026-10-01T00:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO deliveries(event_id,destination,status,updated_at) VALUES(?,'discord','pending','now')",
            (cursor.lastrowid,),
        )
        delivery_id = connection.execute("SELECT id FROM deliveries").fetchone()[0]

    app_env._deliver(delivery_id)

    with app_env.db_connection() as connection:
        delivery = connection.execute("SELECT * FROM deliveries WHERE id=?", (delivery_id,)).fetchone()
    assert delivery["status"] == "failed"
    assert delivery["attempts"] == 1
    assert delivery["next_attempt_at"]
    assert delivery["last_error"] == "Discord returned HTTP 503."
