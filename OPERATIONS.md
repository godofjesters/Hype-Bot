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

Stop Hype Bot before copying its SQLite volume so its database and write-ahead log are captured together. Save the backup somewhere secure. Keep it with the matching `.env` secrets, especially `APP_ENCRYPTION_KEY`.

```sh
docker stop hype-bot
mkdir -p "$HOME/hype-bot-backups"
docker run --rm --volume hype-bot-data:/data:ro --volume "$HOME/hype-bot-backups:/backup" alpine:3.20 tar -czf /backup/hype-bot-backup.tar.gz -C /data .
docker start hype-bot
```

This example overwrites `hype-bot-backup.tar.gz` each time. Rename or copy the file after each backup if you want to keep multiple dates.

## Update and roll back

Before an update, make a backup using the steps above. Then, from `/opt/hype-bot` on Debian:

```sh
git pull --ff-only
docker tag hype-bot:local hype-bot:rollback
docker build -t hype-bot:local .
docker rm -f hype-bot
docker run -d --name hype-bot --restart unless-stopped --publish 192.168.150.3:8018:8000 --env-file .env --volume hype-bot-data:/data hype-bot:local
docker inspect --format '{{.State.Health.Status}}' hype-bot
```

Wait for `healthy`, open the dashboard, and confirm your channels and recent Activity are present.

If the update fails, replace the container using the saved image:

```sh
docker rm -f hype-bot
docker run -d --name hype-bot --restart unless-stopped --publish 192.168.150.3:8018:8000 --env-file .env --volume hype-bot-data:/data hype-bot:rollback
```

Keep your database backup until the update is confirmed. An image rollback cannot always undo a database change made by a newer version.

## Restore a backup

Restore into a new volume so the current data stays untouched. Replace `BACKUP_FILE.tar.gz` with the backup filename.

```sh
docker volume create hype-bot-data-restore
docker run --rm --volume hype-bot-data-restore:/data --volume "$HOME/hype-bot-backups:/backup:ro" alpine:3.20 sh -c 'tar -xzf /backup/BACKUP_FILE.tar.gz -C /data && chown -R 10001:10001 /data'
```

After checking the extracted data, recreate the app using `hype-bot-data-restore` instead of `hype-bot-data` in the `docker run` command. Keep the original volume until the restored app is verified. The backup must use the same `APP_ENCRYPTION_KEY` as the saved database.

## YouTube polling quota

The default poll interval is 60 minutes. Each channel uses one `search.list` call per poll; four channels polled hourly use 96 of the default 100 daily `search.list` calls. Do not set a shorter interval for four channels unless the YouTube project has a larger quota. The app uses additional YouTube methods with their own daily quota bucket. Check the current quota in Google Cloud Console and see Google's [quota calculator](https://developers.google.com/youtube/v3/determine_quota_cost).

## Facebook notes

- `APP_BASE_URL` must be the exact HTTPS hostname used to open the dashboard. In Meta's Facebook Login settings, the allowed callback is that URL followed by `/destinations/facebook/callback`.
- After changing `.env`, remove and recreate the container so it loads the new values. Do not remove the `hype-bot-data` volume.
- The current release stores one global Facebook Page. Assigning different Pages to different channels is planned separately.

## YouTube push notifications

The current app polls YouTube and does not expose a YouTube callback. YouTube push notifications require a publicly reachable callback; keep the dashboard private behind the VPN if push support is added later. See Google's [push notification guide](https://developers.google.com/youtube/v3/guides/push_notifications).
