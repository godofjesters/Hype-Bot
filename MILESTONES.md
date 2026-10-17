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

- [ ] **Twitch schedule monitoring:** add Twitch as an optional event source alongside YouTube. Let users configure Twitch developer app credentials and monitored Twitch channels, poll published stream schedules, and route alerts through the existing destinations with duplicate prevention. Account for streams that go live without a published schedule.
- [ ] Expand Hosting & HTTPS guidance with a provider-neutral overview and an Apache2 reverse-proxy example; keep Nginx Proxy Manager as one option, not a requirement.
- [ ] **Per-channel Facebook routing:** authorize multiple managed Pages and assign a Facebook Page to each monitored YouTube channel. Route business channel alerts only to the business Page and personal channel alerts only to the personal Page; keep Discord configuration global.
- [ ] Add YouTube push notifications if public callback access becomes available.
- [ ] Evaluate multi-user accounts after the single-admin version is in use.

## Debian release and Facebook verification (in progress)

- [ ] Nginx Proxy Manager setup is intentionally paused until Hype Bot is deployed on Debian. Planned hostname: hype.digital-dreamer.org; DNS can alias hype to the existing home.digital-dreamer.org destination, while leaving the apex and home record unchanged. Resume with the Debian backend, then configure the proxy host and certificate.

- [ ] Build a screenshot-guided Meta app creation walkthrough for the Facebook dashboard and README, confirming the current app use case, Page permissions, OAuth redirect setup, and credential locations as the user shares each screen.
- [ ] Publish a prebuilt image to GHCR from GitHub Actions, then pull and run that image on Debian 12. Keep deployment settings in `/opt/hype-bot`, publish host port `8018` to container port `8000`, and restrict Nginx Proxy Manager to VPN access. The source repository and container package can have separate visibility; while the package is private, authenticate Debian to GHCR before pulling.
- [ ] Confirm health, HTTPS login, channel polling, and persistent state after a container restart on the Debian server.
- [ ] Configure the production HTTPS `APP_BASE_URL` and exact Meta OAuth redirect, authorize the Meta app, and select one managed Facebook Page.
- [ ] Publish and verify the explicit Facebook test post, then verify one real detected event is delivered once using the configured template.
- [ ] Create the `v1.0.0` release only after the pulled-image deployment, health and persistence checks, Facebook checks, and one real event delivery pass; use `vMAJOR.MINOR.PATCH` for subsequent releases. Per-channel Page routing remains a follow-up milestone.
