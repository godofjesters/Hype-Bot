# Hype Bot project instructions

## Project goal

Hype Bot is a private, single-team web app that monitors YouTube channels and sends new upload and scheduled/live-stream alerts to Discord and Facebook Pages.

## Current product decisions

- Deploy on Debian 12 as a Docker container started with `docker run`; keep the dashboard behind a VPN. Store the container deployment settings under `/opt/hype-bot` on the Debian server. Publish host port `8018` to the app's internal port `8000` for the Nginx Proxy Manager upstream. Meta OAuth requires the configured HTTPS `APP_BASE_URL` and an exact redirect URL registered in the Meta app.
- Use one admin login for v1. Keep authentication code separable so multiple users can be added later.
- Monitor up to four channels hourly by default. The default YouTube `search.list` allowance is 100 calls/day; four channels checked hourly use 96 calls/day.
- Poll YouTube in v1; public YouTube push callbacks are a possible later milestone.
- Alert about upcoming streams on first scan. YouTube polling returns recent historical uploads and archived broadcasts on later scans too, so compare upload `publishedAt` and stream scheduled/actual start times against each channel's `added_at` on every poll. Never rely on skipping uploads only during the first scan.
- Per channel, allow uploads and streams to be enabled independently. Stream alerts default to the scheduled time; optionally wait until the stream begins.
- Configure one Discord webhook globally. The current Facebook integration supports one globally selected Page; the planned channel-routing milestone below supersedes that limitation for the user's business and personal workflow.
- Planned Facebook routing: authorize and retain multiple managed Pages, then assign an optional Facebook Page independently to each monitored YouTube channel. A business YouTube channel should post only to its business Page, and personal channels only to the personal Page. Never cross-post a channel event to a Page that was not assigned to that channel.
- Keep upload and stream message templates separate for each destination. Available fields: title, channel, URL, event type, scheduled time.
- Provide Business and Gaming dashboard themes, selectable in Settings and persisted in SQLite; Business is the default for new installations.
- Use separate authenticated dashboard pages for Overview, Channels, Discord, Facebook, Hosting & HTTPS, Activity, and Settings. Put step-by-step provider credential/setup guidance directly beside the relevant fields so routine setup does not require opening the README. Link the Facebook HTTPS prerequisite to the Hosting & HTTPS guide.
- Keep hosting and reverse-proxy support provider-agnostic. Explain the shared requirements first (domain/DNS, HTTPS, upstream host and published port, secure cookies, exact `APP_BASE_URL`, and VPN/firewall restrictions), then give clearly labeled examples such as Nginx Proxy Manager and Apache2. Do not imply that the app requires NPM or assumes the user's private server address.
- Do not send an upload alert for a video already announced as a stream.

## Implementation guidance

- Keep provider API calls behind small service functions so polling and delivery can be changed independently of the dashboard.
- Persist channel state, event deduplication keys, delivery attempts, settings, and event history in SQLite on a named Docker volume.
- Encrypt destination tokens and webhook URLs at rest using `APP_ENCRYPTION_KEY`. Never log credential values or provider response bodies that might include credentials.
- Use idempotent event and delivery records; retry temporary delivery errors and show the latest failure in the dashboard.
- Refresh the stored event title from YouTube on each poll when a video is renamed. Keep the event ID and delivery records unchanged so title edits never trigger another notification.
- Show detected events grouped by channel, newest first. Store YouTube's published timestamp for uploads and actual start time for start-triggered streams. Order scheduled-trigger streams by their scheduled time, including existing records created before source timestamps were stored.
- Keep Discord and Facebook test actions explicit and user initiated; validation must not publish provider messages.
- Keep the public interface limited to the authenticated dashboard and health status. Do not add an unauthenticated data API.
- Update `MILESTONES.md` when a milestone is materially completed or the project plan changes.
- Keep this file current when product decisions or operational constraints change.

## Planned follow-up

- Replace the single global Facebook Page destination with multiple authorized Pages and a per-YouTube-channel Page assignment. Preserve the global Discord webhook. Verify routing with distinct business and personal channel/Page pairs before considering this workflow complete.

## Local development and deployment

- Copy `.env.example` to `.env` and provide unique secrets and provider credentials before deployment.
- Build the app with `docker build -t hype-bot:local .` and start it with `docker run`; use a named volume for SQLite.
- Do not commit `.env`, SQLite databases, access tokens, webhook URLs, or generated runtime state.
