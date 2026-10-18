# Hype Bot milestones

## 1. App foundation

- [x] FastAPI dashboard, admin login, Docker image, and `docker run` deployment.
- [x] Persistent SQLite storage and encrypted provider credential support.
- [x] Download and restore SQLite backups from Settings, with validation, encryption-key checks, and a pre-restore recovery copy.
- [x] Health status and basic operational error display.

## 2. YouTube monitoring

- [x] Add and resolve channel links; support up to four monitored channels.
- [x] Poll uploads and upcoming streams hourly with quota-aware scheduling.
- [x] Ignore historical uploads, announce upcoming streams on setup, and deduplicate stream archives.
- [x] Support per-channel event switches and scheduled-time or stream-start alerts.
- [x] Show channel check status, provider errors, and detected event history in the dashboard.

## 3. Notification destinations

- [x] Configure a Discord webhook, encrypt it at rest, and provide an explicit test action.
- [x] Route video upload and stream alerts to independently configured Discord channels using separate encrypted webhooks and explicit test actions.
- [x] Authorize Meta, select one managed Facebook Page, encrypt its token, and publish Page posts.
- [x] Edit and preview separate upload and stream templates for each platform.
- [x] Create idempotent independent deliveries, retry temporary failures, and display per-destination delivery status.
- [x] Split the dashboard into dedicated pages and add inline YouTube API, Discord webhook, and Meta/Facebook setup guidance.
- [x] Add a Hosting & HTTPS guide with Nginx Proxy Manager example steps, linked from Facebook setup.

## 4. Debian deployment and operations

- [x] Document Debian secret setup, VPN/HTTPS reverse-proxy and Meta OAuth redirect requirements, health/log inspection, backup/restore, and upgrade/rollback using Docker CLI commands.
- [x] Verify settings, channels, and event history survive container restarts on the named volume.
- [x] Document YouTube polling quota and the future option for public push callbacks.

## Future

- [x] **Mobile-friendly dashboard:** make every dashboard page responsive and touch-friendly on phones, and verify the stylesheet and other static assets load correctly over the HTTPS deployment.
- [ ] **Twitch schedule monitoring:** add Twitch as an optional event source alongside YouTube. Let users configure Twitch developer app credentials and monitored Twitch channels, poll published stream schedules, and route alerts through the existing destinations with duplicate prevention. Account for streams that go live without a published schedule.
- [ ] Expand Hosting & HTTPS guidance with a provider-neutral overview and an Apache2 reverse-proxy example; keep Nginx Proxy Manager as one option, not a requirement.
- [ ] **Per-channel Facebook routing:** authorize multiple managed Pages and assign a Facebook Page to each monitored YouTube channel. Route business channel alerts only to the business Page and personal channel alerts only to the personal Page; keep Discord configuration global.
- [ ] Add YouTube push notifications if public callback access becomes available.
- [ ] Evaluate multi-user accounts after the single-admin version is in use.

## Production verification and v1.0.0 release (complete)

- [x] Deploy Hype Bot on Debian behind Nginx Proxy Manager with HTTPS and VPN-only access.

- [x] Add a text-based Meta app setup walkthrough to the Facebook dashboard and link it from the README, covering Page permissions, OAuth redirect setup, and credential locations without personal screenshots.
- [x] Publish a prebuilt image to GHCR from GitHub Actions, then pull and run that image on Debian 12 with deployment settings under `/opt/hype-bot`, host port `8018` mapped to container port `8000`, and VPN-only access.
- [x] Confirm health, HTTPS login, channel polling, and persistent state after a container restart on the Debian server.
- [x] Configure the production HTTPS `APP_BASE_URL` and exact Meta OAuth redirect, authorize the Meta app, and select a managed Facebook Page.
- [x] Publish and verify the explicit Facebook test post, then verify one real detected event reached both configured destinations. Hype Bot recorded one attempt per destination; a local test bot was also active during the Discord check and was shut down afterward.
- [x] Create the `v1.0.0` release after the pulled-image deployment, health and persistence checks, Facebook checks, and one real event delivery passed. Use `vMAJOR.MINOR.PATCH` for subsequent releases. Per-channel Page routing remains a follow-up milestone.
