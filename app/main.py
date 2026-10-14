from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import asyncio
import json
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from app.youtube import YouTubeClient, YouTubeError
from app.destinations import (DestinationError, discord_send, facebook_send,
                              meta_exchange_code, meta_authorize_url, meta_pages,
                              render_message)


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data")).expanduser()
DB_PATH = Path(os.environ.get("DB_PATH", str(DATA_DIR / "hype-bot.sqlite3")))
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "").strip()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
APP_SECRET = os.environ.get("APP_SECRET", "")
APP_ENCRYPTION_KEY = os.environ.get("APP_ENCRYPTION_KEY", "")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() not in {"0", "false", "no"}
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
META_APP_ID = os.environ.get("META_APP_ID", "").strip()
META_APP_SECRET = os.environ.get("META_APP_SECRET", "").strip()
META_GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v26.0").strip()
APP_BASE_URL = os.environ.get("APP_BASE_URL", "").rstrip("/")
POLL_INTERVAL_MINUTES = max(15, int(os.environ.get("POLL_INTERVAL_MINUTES", "60")))


def validate_configuration() -> None:
    missing = [
        name
        for name, value in (
            ("ADMIN_USERNAME", ADMIN_USERNAME),
            ("ADMIN_PASSWORD", ADMIN_PASSWORD),
            ("APP_SECRET", APP_SECRET),
            ("APP_ENCRYPTION_KEY", APP_ENCRYPTION_KEY),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing required configuration: " + ", ".join(missing)
            + ". Copy .env.example to .env and set unique values."
        )
    if len(APP_SECRET) < 32 or len(APP_ENCRYPTION_KEY) < 32:
        raise RuntimeError("APP_SECRET and APP_ENCRYPTION_KEY must each be at least 32 characters.")


@contextmanager
def db_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with db_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS system_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                uploads_playlist TEXT NOT NULL,
                enabled_uploads INTEGER NOT NULL DEFAULT 1,
                enabled_streams INTEGER NOT NULL DEFAULT 1,
                stream_timing TEXT NOT NULL DEFAULT 'scheduled',
                added_at TEXT NOT NULL,
                last_checked_at TEXT,
                last_error TEXT,
                first_scan_done INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS monitored_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
                video_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                scheduled_at TEXT,
                event_time TEXT NOT NULL,
                UNIQUE(video_id, event_type)
            );
            CREATE TABLE IF NOT EXISTS message_templates (
                destination TEXT NOT NULL, event_type TEXT NOT NULL, body TEXT NOT NULL,
                PRIMARY KEY(destination,event_type)
            );
            CREATE TABLE IF NOT EXISTS deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL REFERENCES monitored_events(id) ON DELETE CASCADE,
                destination TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TEXT,
                last_error TEXT, remote_id TEXT, updated_at TEXT NOT NULL,
                UNIQUE(event_id,destination)
            );
            """
        )
        connection.execute(
            "INSERT INTO app_meta (key, value) VALUES ('schema_version', '3') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        started_at = datetime.now(timezone.utc).isoformat()
        for destination in ("discord", "facebook"):
            for event_type in ("upload", "stream"):
                default = "{event_type}: {title} — {url}" if destination == "discord" else "{event_type}: {title}\n{url}"
                connection.execute("INSERT OR IGNORE INTO message_templates VALUES (?,?,?)", (destination,event_type,default))
        connection.execute(
            "INSERT INTO system_events (level, message, created_at) VALUES (?, ?, ?)",
            ("info", "Hype Bot started.", started_at),
        )


def seal_secret(value: str) -> str:
    """Encrypt a provider credential before storing it in SQLite."""
    key = hashlib.sha256(APP_ENCRYPTION_KEY.encode("utf-8")).digest()
    fernet = Fernet(__import__("base64").urlsafe_b64encode(key))
    return fernet.encrypt(value.encode("utf-8")).decode("ascii")


def open_secret(value: str) -> str:
    key = hashlib.sha256(APP_ENCRYPTION_KEY.encode("utf-8")).digest()
    fernet = Fernet(__import__("base64").urlsafe_b64encode(key))
    return fernet.decrypt(value.encode("ascii")).decode("utf-8")


def store_secret(name: str, value: str) -> None:
    """Persist an encrypted setting; provider integrations use this in later milestones."""
    with db_connection() as connection:
        connection.execute(
            "INSERT INTO app_meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (f"secret:{name}", seal_secret(value)),
        )


def load_secret(name: str) -> str | None:
    with db_connection() as connection:
        row = connection.execute(
            "SELECT value FROM app_meta WHERE key = ?", (f"secret:{name}",)
        ).fetchone()
    return open_secret(row["value"]) if row else None


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def require_csrf(request: Request, submitted: str) -> None:
    expected = request.session.get("csrf_token", "")
    if not expected or not hmac.compare_digest(expected, submitted):
        raise HTTPException(status_code=403, detail="The form expired. Reload the page and try again.")


def is_authenticated(request: Request) -> bool:
    return request.session.get("username") == ADMIN_USERNAME


def page_context(request: Request, **extra: Any) -> dict[str, Any]:
    return {
        "request": request,
        "csrf_token": csrf_token(request),
        "username": request.session.get("username"),
        **extra,
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_configuration()
    initialize_database()
    poller = asyncio.create_task(poll_loop())
    delivery_worker = asyncio.create_task(delivery_loop())
    yield
    poller.cancel()
    delivery_worker.cancel()
    try:
        await poller
    except asyncio.CancelledError:
        pass
    try:
        await delivery_worker
    except asyncio.CancelledError:
        pass


def record_system_event(level: str, message: str) -> None:
    with db_connection() as connection:
        connection.execute(
            "INSERT INTO system_events (level, message, created_at) VALUES (?, ?, ?)",
            (level, message[:300], datetime.now(timezone.utc).isoformat()),
        )


def parse_youtube_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def poll_channels(channel_ids: list[str] | None = None) -> None:
    if not YOUTUBE_API_KEY:
        return
    client = YouTubeClient(YOUTUBE_API_KEY)
    with db_connection() as connection:
        if channel_ids:
            placeholders = ",".join("?" for _ in channel_ids)
            channels = connection.execute(
                f"SELECT * FROM channels WHERE channel_id IN ({placeholders}) ORDER BY added_at",
                channel_ids,
            ).fetchall()
        else:
            channels = connection.execute("SELECT * FROM channels ORDER BY added_at").fetchall()
    for channel in channels:
        try:
            monitoring_started_at = parse_youtube_datetime(channel["added_at"])
            if monitoring_started_at is None:
                raise ValueError("Channel monitoring start time is invalid.")
            videos = client.scan(channel["channel_id"], channel["uploads_playlist"])
            now = datetime.now(timezone.utc).isoformat()
            with db_connection() as connection:
                for video in videos:
                    video_id = video.get("id")
                    snippet = video.get("snippet", {})
                    live = video.get("liveStreamingDetails", {})
                    if not video_id or not snippet:
                        continue
                    # YouTube titles can change after an event is first detected.
                    # Refresh the stored title without creating a new event or
                    # delivery, so dashboard history reflects the current name.
                    connection.execute(
                        "UPDATE monitored_events SET title=? WHERE video_id=?",
                        (snippet.get("title", "Untitled video"), video_id),
                    )
                    scheduled = live.get("scheduledStartTime")
                    started = live.get("actualStartTime")
                    ended = live.get("actualEndTime")
                    scheduled_dt = parse_youtube_datetime(scheduled)
                    started_dt = parse_youtube_datetime(started)
                    is_stream = bool(scheduled or started or ended)
                    if is_stream:
                        if not channel["enabled_streams"]:
                            continue
                        should_record = (
                            channel["stream_timing"] == "scheduled"
                            and scheduled_dt is not None
                            and scheduled_dt > datetime.now(timezone.utc)
                            and scheduled_dt >= monitoring_started_at
                        ) or (
                            channel["stream_timing"] == "start"
                            and started_dt is not None
                            and started_dt >= monitoring_started_at
                        )
                        # First scan announces only upcoming streams. Later scans
                        # honor the configured scheduled-time or actual-start trigger.
                        if not channel["first_scan_done"]:
                            should_record = bool(
                                scheduled_dt
                                and scheduled_dt > datetime.now(timezone.utc)
                                and scheduled_dt >= monitoring_started_at
                            )
                        if not should_record:
                            continue
                        event_type = "stream"
                        # A video can gain live-stream metadata between polls.
                        # Keep its event history stream-only in that case too.
                        connection.execute(
                            "DELETE FROM monitored_events WHERE video_id=? AND event_type='upload'",
                            (video_id,),
                        )
                    else:
                        # Use the channel's monitoring start time on every scan;
                        # the API returns recent historical uploads repeatedly.
                        published_dt = parse_youtube_datetime(snippet.get("publishedAt"))
                        if (
                            not channel["enabled_uploads"]
                            or published_dt is None
                            or published_dt <= monitoring_started_at
                        ):
                            continue
                        previously_announced = connection.execute(
                            "SELECT 1 FROM monitored_events WHERE video_id=? AND event_type='stream'",
                            (video_id,),
                        ).fetchone()
                        if previously_announced:
                            continue
                        event_type = "upload"
                    connection.execute(
                        "INSERT OR IGNORE INTO monitored_events "
                        "(channel_id, video_id, event_type, title, url, scheduled_at, event_time) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (channel["channel_id"], video_id, event_type, snippet.get("title", "Untitled video"),
                         f"https://www.youtube.com/watch?v={video_id}", scheduled, now),
                    )
                    event = connection.execute("SELECT id FROM monitored_events WHERE video_id=? AND event_type=?", (video_id,event_type)).fetchone()
                    if connection.execute("SELECT changes()").fetchone()[0]:
                        enqueue_deliveries(connection, event["id"])
                connection.execute(
                    "UPDATE channels SET last_checked_at=?, last_error=NULL, first_scan_done=1 WHERE channel_id=?",
                    (now, channel["channel_id"]),
                )
        except (YouTubeError, ValueError) as exc:
            with db_connection() as connection:
                connection.execute(
                    "UPDATE channels SET last_checked_at=?, last_error=? WHERE channel_id=?",
                    (datetime.now(timezone.utc).isoformat(), str(exc)[:240], channel["channel_id"]),
                )
            record_system_event("error", f"YouTube check failed for {channel['title']}: {exc}")


async def poll_loop() -> None:
    while True:
        await asyncio.to_thread(poll_channels)
        await asyncio.sleep(POLL_INTERVAL_MINUTES * 60)


def enqueue_deliveries(connection: sqlite3.Connection, event_id: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    configured = []
    if load_secret("discord_webhook"):
        configured.append("discord")
    if load_secret("facebook_page_token") and load_secret("facebook_page_id"):
        configured.append("facebook")
    for destination in configured:
        connection.execute("INSERT OR IGNORE INTO deliveries(event_id,destination,status,updated_at) VALUES(?,?,'pending',?)", (event_id,destination,now))


def _template(destination: str, event_type: str) -> str:
    with db_connection() as connection:
        row = connection.execute("SELECT body FROM message_templates WHERE destination=? AND event_type=?", (destination,event_type)).fetchone()
    return row[0] if row else "{title} — {url}"


def _deliver(delivery_id: int) -> None:
    with db_connection() as connection:
        row = connection.execute("SELECT d.*,e.title,e.url,e.event_type,e.scheduled_at,e.channel_id,c.title AS channel_title FROM deliveries d JOIN monitored_events e ON e.id=d.event_id JOIN channels c ON c.channel_id=e.channel_id WHERE d.id=?", (delivery_id,)).fetchone()
        if not row:
            return
        fields = {"title": row["title"], "channel": row["channel_title"], "url": row["url"], "event_type": row["event_type"], "scheduled_time": row["scheduled_at"] or ""}
        message = render_message(_template(row["destination"], row["event_type"]), fields)
        dest = row["destination"]
    try:
        remote_id = ""
        if dest == "discord":
            discord_send(load_secret("discord_webhook") or "", message)
        else:
            remote_id = facebook_send(load_secret("facebook_page_id") or "", load_secret("facebook_page_token") or "", message)
        status, error, retry_at = "sent", None, None
    except DestinationError as exc:
        status, error = "failed", str(exc)[:240]
        retry_at = (datetime.now(timezone.utc).replace(microsecond=0)).isoformat() if exc.retryable else None
        if exc.retryable:
            # Bounded exponential backoff, capped at six hours.
            with db_connection() as connection:
                attempts = connection.execute("SELECT attempts FROM deliveries WHERE id=?",(delivery_id,)).fetchone()[0]
            from datetime import timedelta
            retry_at = (datetime.now(timezone.utc) + timedelta(minutes=min(360, 2 ** min(attempts, 8)))).isoformat()
    with db_connection() as connection:
        connection.execute("UPDATE deliveries SET status=?,attempts=attempts+1,next_attempt_at=?,last_error=?,remote_id=?,updated_at=? WHERE id=?", (status,retry_at,error,remote_id,datetime.now(timezone.utc).isoformat(),delivery_id))


async def delivery_loop() -> None:
    while True:
        now = datetime.now(timezone.utc).isoformat()
        with db_connection() as connection:
            rows = connection.execute("SELECT id FROM deliveries WHERE status='pending' OR (status='failed' AND next_attempt_at IS NOT NULL AND next_attempt_at<=?) ORDER BY id LIMIT 30", (now,)).fetchall()
        for row in rows:
            await asyncio.to_thread(_deliver, row["id"])
        await asyncio.sleep(15)


app = FastAPI(
    title="Hype Bot",
    description="Private YouTube notification dashboard",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=APP_SECRET or "configuration-required",
    session_cookie="hype_bot_session",
    max_age=60 * 60 * 12,
    same_site="lax",
    https_only=COOKIE_SECURE,
)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")


@app.get("/health")
def health() -> dict[str, str]:
    try:
        with db_connection() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"status": "ok"}
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=303)
    with db_connection() as connection:
        events = connection.execute(
            "SELECT level, message, created_at FROM system_events ORDER BY id DESC LIMIT 8"
        ).fetchall()
        channels = connection.execute(
            "SELECT * FROM channels ORDER BY added_at"
        ).fetchall()
        history = connection.execute(
            "SELECT e.*, c.title AS channel_title FROM monitored_events e "
            "JOIN channels c USING(channel_id) ORDER BY e.id DESC LIMIT 12"
        ).fetchall()
        deliveries = connection.execute("SELECT d.*,e.title,e.event_type,c.title AS channel_title FROM deliveries d JOIN monitored_events e ON e.id=d.event_id JOIN channels c ON c.channel_id=e.channel_id ORDER BY d.id DESC LIMIT 20").fetchall()
        template_rows = connection.execute("SELECT destination,event_type,body FROM message_templates").fetchall()
    templates_map = {f"{row['destination']}_{row['event_type']}": row['body'] for row in template_rows}
    template_previews = {key: render_message(value, {"title":"New video title", "channel":"Example channel", "url":"https://youtube.com/watch?v=example", "event_type":"Stream", "scheduled_time":"2026-10-14 18:00 UTC"}) for key,value in templates_map.items()}
    page_options = json.loads(load_setting("meta_page_options") or "[]")
    flash = request.query_params.get("message")
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context=page_context(request, events=events, channels=channels, history=history,
                             flash=flash, channel_error=request.query_params.get("error"),
                             poll_minutes=POLL_INTERVAL_MINUTES, youtube_ready=bool(YOUTUBE_API_KEY),
                             deliveries=deliveries, message_templates=templates_map,
                             template_previews=template_previews,
                             discord_ready=bool(load_secret("discord_webhook")),
                             facebook_page=load_setting("facebook_page_name"),
                             page_options=page_options, meta_ready=bool(META_APP_ID and META_APP_SECRET and APP_BASE_URL)),
    )


def load_setting(name: str) -> str | None:
    with db_connection() as connection:
        row = connection.execute("SELECT value FROM app_meta WHERE key=?", (name,)).fetchone()
    return row[0] if row else None


def save_setting(name: str, value: str) -> None:
    with db_connection() as connection:
        connection.execute("INSERT INTO app_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (name,value))


@app.post("/destinations/discord")
def save_discord(request: Request, webhook: str = Form(...), csrf: str = Form(...)):
    if not is_authenticated(request): return RedirectResponse("/login", status_code=303)
    require_csrf(request, csrf)
    webhook = webhook.strip()
    if not webhook.startswith("https://discord.com/api/webhooks/") and not webhook.startswith("https://discordapp.com/api/webhooks/"):
        return RedirectResponse("/?error=discord_url", status_code=303)
    store_secret("discord_webhook", webhook)
    return RedirectResponse("/?message=discord_saved", status_code=303)


@app.post("/destinations/templates")
def save_templates(request: Request, discord_upload: str = Form(...), discord_stream: str = Form(...),
                   facebook_upload: str = Form(...), facebook_stream: str = Form(...), csrf: str = Form(...)):
    if not is_authenticated(request): return RedirectResponse("/login", status_code=303)
    require_csrf(request, csrf)
    allowed = {"title", "channel", "url", "event_type", "scheduled_time"}
    try:
        for key, body in (("discord_upload",discord_upload),("discord_stream",discord_stream),
                          ("facebook_upload",facebook_upload),("facebook_stream",facebook_stream)):
            import string
            fields = {name for _, name, _, _ in string.Formatter().parse(body) if name}
            if not fields <= allowed or not body.strip(): raise ValueError()
            render_message(body, {name: name for name in allowed})
    except (ValueError, DestinationError):
        return RedirectResponse("/?error=template", status_code=303)
    with db_connection() as connection:
        for key, body in (("discord_upload",discord_upload),("discord_stream",discord_stream),
                          ("facebook_upload",facebook_upload),("facebook_stream",facebook_stream)):
            destination, event_type = key.rsplit("_",1)
            connection.execute("INSERT INTO message_templates VALUES(?,?,?) ON CONFLICT(destination,event_type) DO UPDATE SET body=excluded.body", (destination,event_type,body))
    return RedirectResponse("/?message=templates_saved", status_code=303)


@app.post("/destinations/discord/test")
def test_discord(request: Request, csrf: str = Form(...)):
    if not is_authenticated(request): return RedirectResponse("/login", status_code=303)
    require_csrf(request, csrf)
    webhook = load_secret("discord_webhook")
    if not webhook: return RedirectResponse("/?error=discord_missing", status_code=303)
    try: discord_send(webhook, "Hype Bot test message. This was sent by an explicit dashboard test action.")
    except DestinationError: return RedirectResponse("/?error=discord_test", status_code=303)
    return RedirectResponse("/?message=discord_test", status_code=303)


@app.post("/destinations/facebook/connect")
def connect_facebook(request: Request, csrf: str = Form(...)):
    if not is_authenticated(request): return RedirectResponse("/login", status_code=303)
    require_csrf(request, csrf)
    if not (META_APP_ID and META_APP_SECRET and APP_BASE_URL): return RedirectResponse("/?error=meta_config", status_code=303)
    state = secrets.token_urlsafe(32); request.session["meta_oauth_state"] = state
    return RedirectResponse(meta_authorize_url(META_APP_ID, APP_BASE_URL + "/destinations/facebook/callback", state), status_code=303)


@app.get("/destinations/facebook/callback")
def facebook_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if not is_authenticated(request): return RedirectResponse("/login", status_code=303)
    expected = request.session.pop("meta_oauth_state", "")
    if error or not expected or not hmac.compare_digest(expected,state) or not code:
        return RedirectResponse("/?error=meta_auth", status_code=303)
    try:
        user_token = meta_exchange_code(META_APP_ID,META_APP_SECRET,APP_BASE_URL + "/destinations/facebook/callback",code)
        pages = meta_pages(user_token)
    except DestinationError:
        return RedirectResponse("/?error=meta_auth", status_code=303)
    for page in pages: store_secret("meta_page_token:" + page["id"], page["token"])
    options = [{"id": page["id"],"name":page["name"]} for page in pages]
    save_setting("meta_page_options", json.dumps(options))
    return RedirectResponse("/?message=pages_loaded" if options else "/?error=no_pages", status_code=303)


@app.post("/destinations/facebook/page")
def select_facebook_page(request: Request, page_id: str = Form(...), csrf: str = Form(...)):
    if not is_authenticated(request): return RedirectResponse("/login", status_code=303)
    require_csrf(request, csrf)
    pages = json.loads(load_setting("meta_page_options") or "[]")
    selected = next((page for page in pages if page["id"] == page_id), None)
    token = load_secret("meta_page_token:" + page_id) if selected else None
    if not selected or not token: return RedirectResponse("/?error=page_select", status_code=303)
    store_secret("facebook_page_id",page_id); store_secret("facebook_page_token",token)
    save_setting("facebook_page_name",selected["name"])
    return RedirectResponse("/?message=facebook_saved", status_code=303)


@app.post("/destinations/facebook/test")
def test_facebook(request: Request, csrf: str = Form(...)):
    if not is_authenticated(request): return RedirectResponse("/login", status_code=303)
    require_csrf(request, csrf)
    page_id, token = load_secret("facebook_page_id"), load_secret("facebook_page_token")
    if not page_id or not token: return RedirectResponse("/?error=facebook_missing", status_code=303)
    try: facebook_send(page_id,token,"Hype Bot test message. This was sent by an explicit dashboard test action.")
    except DestinationError: return RedirectResponse("/?error=facebook_test", status_code=303)
    return RedirectResponse("/?message=facebook_test", status_code=303)


@app.post("/channels")
def add_channel(request: Request, background_tasks: BackgroundTasks,
                channel_url: str = Form(...), csrf: str = Form(...)):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=303)
    require_csrf(request, csrf)
    if not YOUTUBE_API_KEY:
        return RedirectResponse("/?error=missing_key", status_code=303)
    try:
        resolved = YouTubeClient(YOUTUBE_API_KEY).resolve_channel(channel_url)
        with db_connection() as connection:
            count = connection.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
            exists = connection.execute("SELECT 1 FROM channels WHERE channel_id=?", (resolved["channel_id"],)).fetchone()
            if not exists and count >= 4:
                return RedirectResponse("/?error=channel_limit", status_code=303)
            connection.execute(
                "INSERT OR IGNORE INTO channels(channel_id,title,uploads_playlist,added_at) VALUES(?,?,?,?)",
                (resolved["channel_id"], resolved["title"], resolved["uploads_playlist"], datetime.now(timezone.utc).isoformat()),
            )
        background_tasks.add_task(poll_channels, [resolved["channel_id"]])
        record_system_event("info", f"Monitoring channel added: {resolved['title']}.")
        return RedirectResponse("/?message=channel_added", status_code=303)
    except YouTubeError:
        return RedirectResponse("/?error=channel_resolve", status_code=303)


@app.post("/channels/{channel_id}/settings")
def update_channel(channel_id: str, request: Request, uploads: str = Form("off"),
                   streams: str = Form("off"), stream_timing: str = Form("scheduled"),
                   csrf: str = Form(...)):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=303)
    require_csrf(request, csrf)
    if stream_timing not in {"scheduled", "start"}:
        raise HTTPException(status_code=400, detail="Invalid stream timing")
    with db_connection() as connection:
        connection.execute(
            "UPDATE channels SET enabled_uploads=?, enabled_streams=?, stream_timing=? WHERE channel_id=?",
            (uploads == "on", streams == "on", stream_timing, channel_id),
        )
    return RedirectResponse("/?message=settings_saved", status_code=303)


@app.post("/channels/{channel_id}/delete")
def delete_channel(channel_id: str, request: Request, csrf: str = Form(...)):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=303)
    require_csrf(request, csrf)
    with db_connection() as connection:
        connection.execute("DELETE FROM channels WHERE channel_id=?", (channel_id,))
    return RedirectResponse("/?message=channel_removed", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context=page_context(request, error=request.query_params.get("error")),
    )


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), csrf: str = Form(...)):
    require_csrf(request, csrf)
    username_ok = hmac.compare_digest(username.strip(), ADMIN_USERNAME)
    password_ok = hmac.compare_digest(password, ADMIN_PASSWORD)
    if not (username_ok and password_ok):
        request.session.pop("csrf_token", None)
        return RedirectResponse("/login?error=1", status_code=303)
    request.session.clear()
    request.session["username"] = ADMIN_USERNAME
    request.session["csrf_token"] = secrets.token_urlsafe(32)
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request, csrf: str = Form(...)):
    require_csrf(request, csrf)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

