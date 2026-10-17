# Hype Bot: advanced operations

Use [README.md](README.md) for a first install and normal dashboard use. This page covers backups, upgrades, troubleshooting, and YouTube quota.

## Check status and logs

Run these commands on the machine running Docker:

```sh
docker ps --filter name=hype-bot
docker inspect --format '{{.State.Health.Status}}' hype-bot
docker logs --since 1h hype-bot
```

The health status should say `healthy`. To check the app directly on the Debian server:

```sh
curl --fail http://192.168.150.3:8018/health
```

## Back up the database

In Hype Bot, open **Settings → Backup and restore → Download backup**. The download is a consistent SQLite snapshot and includes channels, detected events, delivery history, templates, themes, and encrypted destination credentials. Keep it private.

The backup does not include `.env`. Store the matching `.env` secrets separately, especially `APP_ENCRYPTION_KEY`, which must remain identical to restore saved Discord and Facebook credentials. Hype Bot also makes a recovery snapshot in `/data/backups` before replacing existing data during a restore.

## Update and roll back

Before an update, download a backup using the steps above. Then, from `/opt/hype-bot` on Debian, pull the desired GHCR image tag, replace the container, and keep the named volume:

```sh
docker pull ghcr.io/godofjesters/hype-bot:latest
docker rm -f hype-bot
docker run -d --name hype-bot --restart unless-stopped --publish 192.168.150.3:8018:8000 --env-file .env --volume hype-bot-data:/data ghcr.io/godofjesters/hype-bot:latest
docker inspect --format '{{.State.Health.Status}}' hype-bot
```

Wait for `healthy`, open the dashboard, and confirm your channels and recent Activity are present.

For a rollback, replace `latest` in both commands with the previous version tag, such as `v1.0.0`:

```sh
docker pull ghcr.io/godofjesters/hype-bot:v1.0.0
docker rm -f hype-bot
docker run -d --name hype-bot --restart unless-stopped --publish 192.168.150.3:8018:8000 --env-file .env --volume hype-bot-data:/data ghcr.io/godofjesters/hype-bot:v1.0.0
```

Keep the database backup until the update is confirmed. An image rollback cannot always undo a database change made by a newer version.

## Restore a backup

Sign in to Hype Bot, open **Settings → Backup and restore**, choose the `.sqlite3` backup file, confirm that you want to replace the saved data, and select **Restore backup**. The app validates the database and verifies that its encrypted credentials match the configured `APP_ENCRYPTION_KEY` before restoring. It saves the current database under `/data/backups` first. On a new server, set up `.env` with the matching `APP_ENCRYPTION_KEY` before restoring; the backup file does not include `.env`.

## YouTube polling quota

The default poll interval is 60 minutes. Each channel uses one `search.list` call per poll; four channels polled hourly use 96 of the default 100 daily `search.list` calls. Do not set a shorter interval for four channels unless the YouTube project has a larger quota. The app uses additional YouTube methods with their own daily quota bucket. Check the current quota in Google Cloud Console and see Google's [quota calculator](https://developers.google.com/youtube/v3/determine_quota_cost).

## Facebook notes

- `APP_BASE_URL` must be the exact HTTPS hostname used to open the dashboard. In Meta's Facebook Login settings, the allowed callback is that URL followed by `/destinations/facebook/callback`.
- After changing `.env`, remove and recreate the container so it loads the new values. Do not remove the `hype-bot-data` volume.
- The current release stores one global Facebook Page. Assigning different Pages to different channels is planned separately.

## YouTube push notifications

The current app polls YouTube and does not expose a YouTube callback. YouTube push notifications require a publicly reachable callback; keep the dashboard private behind the VPN if push support is added later. See Google's [push notification guide](https://developers.google.com/youtube/v3/guides/push_notifications).
