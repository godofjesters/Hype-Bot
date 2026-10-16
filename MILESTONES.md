# Hype Bot milestones

## 1. App foundation

- [x] FastAPI dashboard, admin login, Docker image, and `docker run` deployment.
- [x] Persistent SQLite storage and encrypted provider credential support.
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

## 4. Debian deployment and operations

- [x] Document Debian secret setup, VPN/HTTPS reverse-proxy and Meta OAuth redirect requirements, health/log inspection, backup/restore, and upgrade/rollback using Docker CLI commands.
- [x] Verify settings, channels, and event history survive container restarts on the named volume.
- [x] Document YouTube polling quota and the future option for public push callbacks.

## Future

- [ ] **Per-channel Facebook routing:** authorize multiple managed Pages and assign a Facebook Page to each monitored YouTube channel. Route business channel alerts only to the business Page and personal channel alerts only to the personal Page; keep Discord configuration global.
- [ ] Add YouTube push notifications if public callback access becomes available.
- [ ] Evaluate multi-user accounts after the single-admin version is in use.

## Debian release and Facebook verification (in progress)

- [ ] Deploy the release candidate from `/opt/hype-bot` on Debian 12, with host port `8018` forwarded to container port `8000` and Nginx Proxy Manager restricted to VPN access.
- [ ] Confirm health, HTTPS login, channel polling, and persistent state after a container restart on the Debian server.
- [ ] Configure the production HTTPS `APP_BASE_URL` and exact Meta OAuth redirect, authorize the Meta app, and select one managed Facebook Page.
- [ ] Publish and verify the explicit Facebook test post, then verify one real detected event is delivered once using the configured template.
- [ ] Create the `v1.0` release only after the deployment and Facebook checks pass; per-channel Page routing remains a follow-up milestone.
