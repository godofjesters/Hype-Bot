# Hype Bot

Private YouTube notification app for a Debian 12 server. The project is being delivered in milestones; see [MILESTONES.md](MILESTONES.md) for progress and [AGENTS.md](AGENTS.md) for the decisions to preserve.

## Debian 12 deployment with Docker CLI

This deployment runs one container named `hype-bot`, publishes only on host loopback, and stores SQLite in the named volume `hype-bot-data`. Put the dashboard behind your VPN and an HTTPS reverse proxy. The host must have Docker Engine installed and running.

### 1. Create configuration and secrets

From a private project directory on the Debian host, copy the sample and restrict access to it:

```sh
cp .env.example .env
chmod 600 .env
```

Create three different random values on the server with `openssl rand -hex 32`. Put one in each of `ADMIN_PASSWORD`, `APP_SECRET`, and `APP_ENCRYPTION_KEY` in `.env`; do not reuse values. Use the generated password to sign in. Keep a protected offline copy of the exact `APP_ENCRYPTION_KEY` and `APP_SECRET` alongside the backup plan. Losing the encryption key makes saved Discord and Meta credentials unreadable; changing it does not re-encrypt them. Changing `APP_SECRET` signs out existing sessions.

Create a Google Cloud project, enable YouTube Data API v3, and create an API key. Set `YOUTUBE_API_KEY` in `.env` and restrict the key to YouTube Data API v3 where practical. Channel setup and polling are disabled without this key. Set `COOKIE_SECURE=true` and set `APP_BASE_URL` to the exact externally used HTTPS origin, for example `https://hype-bot.example.net` (no trailing slash). If Facebook Page authorization is needed, also set `META_APP_ID` and `META_APP_SECRET`.

### 2. Build and start

Run these commands from the directory containing the Dockerfile and `.env`:

```sh
docker build -t hype-bot:local .
docker volume create hype-bot-data
docker run -d --name hype-bot --restart unless-stopped \
  --publish 127.0.0.1:8000:8000 \
  --env-file .env \
  --volume hype-bot-data:/data \
  hype-bot:local
```

Docker reads `.env` when creating the container; editing it later requires recreating the container. The image runs as UID 10001 and writes its database to `/data/hype-bot.sqlite3`. The volume preserves channel state, event and delivery history, templates, and encrypted destination credentials across container replacement. Do not mount a host folder over `/app` or `/data` in place of the named volume.

### 3. VPN, HTTPS proxy, and Meta OAuth

Keep the container bound to `127.0.0.1` when the reverse proxy is on the same Debian host. Configure the proxy to serve the dashboard only through the VPN-restricted HTTPS hostname, proxy requests to `http://127.0.0.1:8000`, preserve the `Host` header, and send the usual `X-Forwarded-Proto: https` and client address headers. Restrict the proxy listener/firewall to the VPN as appropriate. Do not expose port 8000 to the public Internet. If a proxy must run on another machine, bind Docker to a specific VPN interface address and firewall that port so only the proxy can reach it.

For Facebook, register this exact redirect URI in the Meta app's Facebook Login settings:

```text
https://hype-bot.example.net/destinations/facebook/callback
```

It must match `APP_BASE_URL` plus `/destinations/facebook/callback` exactly, including scheme, hostname, and any port. The callback must be reachable over HTTPS from the user's browser. Meta's authorization flow uses the signed-in dashboard session, so the dashboard and callback should use the same public hostname. Permissions required by the current app are `pages_show_list` and `pages_manage_posts`; Meta may require app review or app/Page roles outside development mode. After changing `.env`, recreate the container with the updated environment.

### 4. Inspect health and logs

```sh
docker ps --filter name=hype-bot
docker inspect --format '{{.State.Health.Status}}' hype-bot
curl --fail http://127.0.0.1:8000/health
docker logs --since 1h hype-bot
docker logs --follow hype-bot
```

The health endpoint checks that the app can query SQLite and returns `{"status":"ok"}`. Docker's image health check probes it every 30 seconds. Logs contain operational errors, but should not contain provider credentials. Inspect channel and delivery failures in the authenticated dashboard as well.

### 5. Back up and restore

SQLite uses WAL mode. Stop the app before copying the volume so the database and its WAL are captured consistently. Store backups and `.env`/key material in access-controlled, encrypted storage outside the server; test restores periodically.

```sh
docker stop hype-bot
install -d -m 700 "$HOME/hype-bot-backups"
docker run --rm --volume hype-bot-data:/data:ro \
  --volume "$HOME/hype-bot-backups:/backup" alpine:3.20 \
  tar -czf /backup/hype-bot-$(date -u +%Y%m%dT%H%M%SZ).tar.gz -C /data .
docker start hype-bot
```

To restore without overwriting the current volume, create a new volume, extract the archive there, then recreate the app container against that volume. Replace the archive path with the backup you intend to restore:

```sh
docker stop hype-bot
docker volume create hype-bot-data-restore
docker run --rm --volume hype-bot-data-restore:/data \
  --volume "$HOME/hype-bot-backups:/backup:ro" alpine:3.20 \
  sh -c 'tar -xzf /backup/REPLACE_WITH_BACKUP.tar.gz -C /data && chown -R 10001:10001 /data'
docker rm hype-bot
docker run -d --name hype-bot --restart unless-stopped \
  --publish 127.0.0.1:8000:8000 --env-file .env \
  --volume hype-bot-data-restore:/data hype-bot:local
```

Check `docker inspect --format '{{.State.Health.Status}}' hype-bot`, sign in, and confirm channels and recent history before treating a restore as complete. Keep the old volume until the restored instance is verified. The database backup must be paired with the matching `APP_ENCRYPTION_KEY`; restoring encrypted credentials with a different key will fail.

### 6. Upgrade and rollback

Build the candidate image before stopping the running container. Keep the old image tag and take a fresh database backup before upgrading, especially before schema changes. The app initializes/migrates its database when it starts; use the same named volume for a normal upgrade.

```sh
docker tag hype-bot:local hype-bot:rollback
docker build -t hype-bot:local .
docker stop hype-bot
docker rm hype-bot
docker run -d --name hype-bot --restart unless-stopped \
  --publish 127.0.0.1:8000:8000 --env-file .env \
  --volume hype-bot-data:/data hype-bot:local
docker inspect --format '{{.State.Health.Status}}' hype-bot
docker logs --since 10m hype-bot
```

If the new image fails, remove that container and rerun the same `docker run` command with `hype-bot:rollback`. A rollback of the image may not reverse a database schema migration; restore the pre-upgrade backup to a separate volume if the prior image cannot read the upgraded database. Keep the backup until the upgraded app is confirmed healthy.

### YouTube polling quota

The app polls immediately at startup and then after each `POLL_INTERVAL_MINUTES` (default 60; values below 15 are clamped to 15). Each configured channel uses one `search.list` request per poll. Google's current default is 100 `search.list` calls per day; four channels polled hourly use 96 of those calls. A `search.list` request is in its own daily bucket (currently 100 calls/day); it is not 100 units in the shared quota. The current scan also calls `playlistItems.list` and usually one `videos.list` request per channel per poll, using the separate combined daily quota for other methods. Check the project's YouTube Data API quotas in Google Cloud Console; quotas currently reset at midnight Pacific Time. Avoid shortening the interval: four channels at 15 minutes would request 384 `search.list` calls/day, above the default. Channel resolution also makes a `channels.list` call. See Google's [quota calculator](https://developers.google.com/youtube/v3/determine_quota_cost).

### Future YouTube push callbacks

The current app polls and has no public callback endpoint. YouTube's documented push option uses WebSub/PubSubHubbub: a callback server subscribes through Google's hub to a channel's uploads feed and receives Atom notifications for uploads and video title/description updates. It requires a publicly reachable callback URL; the VPN-only dashboard should remain private. A future implementation would need a separately exposed, HTTPS callback route, subscription renewal/verification, notification validation and idempotent event processing, while retaining polling as a fallback. Upload notifications alone do not replace polling for scheduled/live-stream state. See Google's [push notification guide](https://developers.google.com/youtube/v3/guides/push_notifications).

## Notification destinations

In the authenticated dashboard, save one Discord webhook and connect one Facebook Page. Discord webhook URLs and Meta Page access tokens are encrypted in SQLite using `APP_ENCRYPTION_KEY`. Use the explicit test buttons only when you intend to send a test message or post.

For Facebook, create/configure a Meta app with Facebook Login and the `pages_show_list` and `pages_manage_posts` permissions. Add `${APP_BASE_URL}/destinations/facebook/callback` as an allowed OAuth redirect URI, set `META_APP_ID`, `META_APP_SECRET`, and the HTTPS `APP_BASE_URL` in `.env`, then recreate the container so it receives the new environment. The signed-in dashboard redirects through Meta; after authorization, select one managed Page. Meta may require app review or a role on the app/Page for use outside development roles. The Graph API version defaults to `v26.0` and can be changed with `META_GRAPH_VERSION`.

The dashboard stores independent upload/stream templates for Discord and Facebook. Supported placeholders are `{title}`, `{channel}`, `{url}`, `{event_type}`, and `{scheduled_time}`. Each newly detected event gets an idempotent delivery for each configured destination. Temporary network, rate-limit, and provider server errors retry with bounded exponential backoff; permanent errors remain visible in delivery history.

The YouTube polling quota and Docker CLI operational procedures are documented above. No YouTube OAuth is needed for public channel data.

## Configuration

| Variable | Purpose |
| --- | --- |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Single administrator account for v1 |
| `APP_SECRET` | Signs the session cookie |
| `APP_ENCRYPTION_KEY` | Key material for encrypting provider credentials stored in SQLite |
| `YOUTUBE_API_KEY` | YouTube Data API v3 key with the API enabled in Google Cloud Console; required for channel resolution and monitoring |
| `META_APP_ID`, `META_APP_SECRET` | Meta app credentials for Facebook Login |
| `META_GRAPH_VERSION` | Graph API version; defaults to `v26.0` |
| `APP_BASE_URL` | HTTPS dashboard URL used for the Meta OAuth redirect; register its callback URL in the Meta app |
| `COOKIE_SECURE`, `PORT` | Enable secure session cookies behind HTTPS; app's internal port |
| `POLL_INTERVAL_MINUTES` | Desired provider polling interval; defaults to 60 minutes |

Do not commit `.env`, database files, access tokens, or Discord webhook URLs.

## Current status

Milestones 1–3 provide the protected dashboard, signed admin sessions, persistent SQLite state, YouTube channel monitoring, event history, encrypted Discord and Facebook Page connections, platform-specific templates, and retryable delivery history. Milestone 4 documents Debian Docker CLI deployment and operations, with named-volume restart persistence verified.
