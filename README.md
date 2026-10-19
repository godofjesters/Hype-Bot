# Hype Bot

Hype Bot watches YouTube channels and sends new upload and livestream alerts to Discord and Facebook Pages.

## Project summary

Hype Bot is a self-hosted Docker app with an authenticated dashboard for channel monitoring, notification setup, activity, and appearance settings. Setup instructions are built into the relevant dashboard pages, with a separate Hosting & HTTPS guide for Facebook's domain and HTTPS requirements. The app does not require a particular reverse proxy; Nginx Proxy Manager is currently the documented example, and Apache2 guidance is planned. Hosting remains the user's choice, and private access should be enforced through a VPN, firewall, or equivalent network controls.

## Pick where to run it

- **Try it on your Windows computer:** follow [Docker Desktop for Windows](#install-on-windows-with-docker-desktop).
- **Install it on your Debian server:** follow [Debian server install](#install-on-your-debian-server).

You only need to follow one install guide. Both use Docker commands; you do not need a `.yaml` or Compose file.

## Before you start

Have these ready:

- Docker Desktop (Windows) or Docker Engine (Debian).
- A YouTube Data API key, if you want channel monitoring.
- For Discord alerts: choose separate text channels for video uploads and stream alerts. You need **Manage Webhooks** permission in both channels to create their webhooks.
- Meta app credentials and an HTTPS website address, if you want Facebook alerts.

Facebook setup can wait. You can start with YouTube and Discord.

## Install on Windows with Docker Desktop

### 1. Open the project folder

Start Docker Desktop and wait until it says it is running. Open PowerShell in the Hype Bot project folder—the folder containing `Dockerfile`.

If the project is not on this computer yet, clone the GitHub repository first. Your GitHub account must have access to this private repository.

### 2. Create your settings file

For a first install, copy the sample settings file and open it. If `.env` already exists, do not overwrite it.

```powershell
Copy-Item .env.example .env
notepad .env
```

Set `ADMIN_USERNAME` and `ADMIN_PASSWORD`. Create two different random values for `APP_SECRET` and `APP_ENCRYPTION_KEY`. In PowerShell 7, run this once for each value:

```powershell
$bytes = [byte[]]::new(32)
[System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
[Convert]::ToHexString($bytes)
```

Paste the first output into `APP_SECRET` and the second into `APP_ENCRYPTION_KEY`. Keep both safe; losing the encryption key means saved Discord and Facebook credentials cannot be read.

Also set `YOUTUBE_API_KEY` if you want YouTube monitoring. Leave the `META_APP_ID` and `META_APP_SECRET` lines empty for now if you are not setting up Facebook. Leave `COOKIE_SECURE=false` for local use.

Save and close Notepad. Keep `.env` private; never send or commit it.

### 3. Build and start Hype Bot

Run these commands in the same PowerShell window:

```powershell
docker build -t hype-bot:local .
docker run -d --name hype-bot --restart unless-stopped -p 127.0.0.1:8018:8000 --env-file .env -v hype-bot-data:/data hype-bot:local
```

Docker creates the `hype-bot-data` storage volume automatically. It keeps your channels, settings, and history if you replace the container.

Run the `docker run` command only for a new install. If the container already exists, start it with `docker start hype-bot`.

### 4. Open the dashboard

Go to <http://localhost:8018> and sign in with the username and password from `.env`.

To check that Hype Bot is running, use:

```powershell
Invoke-RestMethod http://localhost:8018/health
```

## Install on your Debian server

These steps use your server folder `/opt/hype-bot`, Nginx Proxy Manager, and host port `8018`. You choose where and how to host Hype Bot; the Debian and NPM setup below is one example. Facebook has one extra requirement: Meta authorization must use a real HTTPS URL with a domain name, such as `https://hypebot.example.com`. An IP address by itself (even with HTTPS) is not a suitable Facebook callback URL. You can use a domain you own or a domain-based dynamic DNS service if that fits your hosting setup.

### 1. Put the project on the server

Connect to Debian using SSH. Run these commands there. The server must already have access to your private GitHub repository:

```sh
sudo install -d -o "$USER" -g "$(id -gn)" -m 750 /opt/hype-bot
git clone git@github.com:godofjesters/Hype-Bot.git /opt/hype-bot
cd /opt/hype-bot
```

If Hype Bot is already in `/opt/hype-bot`, skip `git clone` and run `cd /opt/hype-bot`.

### 2. Add your settings

For a first install, create and open the settings file. If `/opt/hype-bot/.env` already exists, keep it and open it with `nano .env` instead—do not overwrite it.

```sh
cp .env.example .env
chmod 600 .env
nano .env
```

In `.env`:

1. Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` to your dashboard login.
2. Run `openssl rand -hex 32` twice. Put one result in `APP_SECRET`, the other in `APP_ENCRYPTION_KEY`. Keep these values safe and do not reuse them.
3. Put your YouTube API key in `YOUTUBE_API_KEY`.
4. Set `COOKIE_SECURE=true`.
5. Set `APP_BASE_URL` to the HTTPS address you use for Hype Bot, with no trailing slash. Example: `https://hypebot.example.com`.
6. For Facebook, also fill in `META_APP_ID` and `META_APP_SECRET`. You can leave them empty until Facebook setup.

Save in nano with **Ctrl+O**, press **Enter**, then exit with **Ctrl+X**.

### 3. Pull and start the prebuilt container

After the GitHub Actions run named **Publish Docker image** succeeds, pull the image from GHCR. The first publish creates the package. Because this repository and package are private, sign in to GHCR on Debian with a GitHub personal access token (classic) that has `read:packages` access. Enter the token when Docker prompts; do not put it in a command or save it in `.env`.

```sh
docker login ghcr.io -u YOUR_GITHUB_USERNAME
docker pull ghcr.io/godofjesters/hype-bot:latest
docker run -d --name hype-bot --restart unless-stopped --publish 192.168.150.3:8018:8000 --env-file .env --volume hype-bot-data:/data ghcr.io/godofjesters/hype-bot:latest
```

The source repository and its GHCR package have separate visibility settings. Making the repository public later will not automatically make the package public. To allow anonymous `docker pull`, change the package visibility to public in the package's GitHub settings. Until then, each server that pulls the image needs GHCR authentication.

The app uses port `8000` inside Docker. Port `8018` is the port Nginx Proxy Manager uses to reach it. Docker creates the `hype-bot-data` volume automatically. The GitHub Actions workflow publishes `latest` from `main` plus a commit SHA tag. Releases use Semantic Versioning tags in `vMAJOR.MINOR.PATCH` form, such as `v1.0.0`; pushing one publishes a matching versioned image. For a stable server install, pull the chosen version tag instead of `latest`.

Run this `docker run` command only for the first install. If the container already exists, use `docker start hype-bot`.

### 4. Point Nginx Proxy Manager to Hype Bot

Nginx Proxy Manager (NPM) is the web page you already use to manage your proxy hosts and certificates. These steps add one entry that sends requests for your Hype Bot web address to the app on your Debian server. Your main website can stay hosted elsewhere. If an existing hostname such as home.yourdomain.com already points to NPM, create a CNAME for the new Hype Bot subdomain (Host/Name hype, Target home.yourdomain.com). Alternatively, create an A record for hype with the same public IPv4 address as home. Do not change the main domain or existing home record, and never use a private LAN IP such as 192.168.x.x in public DNS. Wait for DNS to resolve before requesting an HTTP-validated certificate.

Before opening NPM, decide on the web address you will use, such as `hypebot.example.com`. Replace that example with your own domain everywhere below. In `.env`, `APP_BASE_URL` must be `https://` followed by that same address, with no trailing slash.

#### Add the proxy entry

1. Sign in to NPM. In the top menu, choose **Hosts**, then **Proxy Hosts**.
2. Select **Add Proxy Host**.
3. On the **Details** tab, enter:

   - **Domain Names:** your Hype Bot address, for example `hypebot.example.com`. This is the address you will type into your browser.
   - **Scheme:** `http`
   - **Forward Hostname / IP:** `192.168.150.3` (your Debian server's local network address)
   - **Forward Port:** `8018` (the port Docker published for Hype Bot)

4. For **Access List**, choose the list you already use to limit your private sites to VPN users. Do not choose **Publicly Accessible**. If you do not have a VPN-only access list yet, set that up before making Hype Bot reachable through NPM.
5. Turn on **Block Common Exploits**. Leave **Cache Assets** and **Websockets Support** off, then select **Save**.

#### Add HTTPS

1. Find the Hype Bot entry in **Proxy Hosts**, open its three-dot menu, and choose **Edit**.
2. Open the **SSL** tab.
3. If you already have a certificate for this exact domain, select it. Otherwise choose the option to request a new Let's Encrypt certificate, enter your email address, accept the terms, and save.
4. If shown, enable **Force SSL**, then select **Save**.

If NPM runs on a different computer from Docker Desktop, use the desktop computer's LAN IP as the Forward Hostname / IP; localhost will not work across computers. Publish Hype Bot on a LAN-reachable host port (for example, 8018:8000 rather than 127.0.0.1:8018:8000) and restrict inbound port 8018 with the desktop firewall so only the NPM host can reach it. Do not forward port 8018 from the Internet. For a new Let's Encrypt certificate, the domain's public DNS must point to your home/server public IP, and your router/firewall must allow inbound port `80` to NPM while the certificate is requested. NPM uses that connection to prove you control the domain. Keep Docker's Hype Bot port `8018` private; do not forward `8018` from your router to the Internet. If you already have a working certificate for the domain, select it instead of requesting another one.

After saving, open `https://` followed by your Hype Bot domain in a browser while connected to your VPN. For example, open `https://hypebot.example.com`—not the raw IP and port. NPM's **Domain Names** field is the browser address; the **Forward Hostname / IP** and **Forward Port** fields tell NPM where the app is on your local network.

On the Debian server, check the app with:

```sh
docker inspect --format '{{.State.Health.Status}}' hype-bot
```

Wait for `healthy`. Then open the HTTPS domain in your browser and sign in.

## Use the dashboard

The dashboard has separate pages for Overview, Channels, Discord, Facebook, Hosting & HTTPS, Activity, and Settings. The YouTube, Discord, Facebook, and Hosting & HTTPS pages include setup steps and links to official instructions, so routine configuration can be completed without referring back to this README.

1. Open **Channels** and add a YouTube channel link.
2. Choose whether to monitor uploads, streams, or both. Stream alerts default to when YouTube schedules the stream.
3. For Discord, create two webhooks: one in the channel for video uploads and one in the channel for stream alerts. In Discord, open **Server Settings** → **Integrations** → **Webhooks** → **Create Webhook**, choose the destination channel, then copy its URL. You need **Manage Webhooks** permission in both channels; ask a server administrator if needed. Webhooks post directly, so you do not need to invite a Hype Bot account. Treat both URLs like passwords.
4. Open the **Discord** page and save the two webhook URLs in their matching fields. Use the separate test buttons to confirm each channel. Upload events go only to the video channel; stream events go only to the stream channel.
5. Open **Activity** to review detected events and delivery status.
6. Open **Settings** to switch between the Business and Gaming themes, and to download or restore an app data backup.

Settings backups contain saved channels, events, delivery history, templates, themes, and encrypted destination credentials. They do not contain `.env`. When moving the database to another server, configure `.env` separately and keep the same `APP_ENCRYPTION_KEY` so saved provider credentials can be decrypted.

When a channel is first added, Hype Bot announces its upcoming public streams. It uses that time as the starting point for uploads, so older videos are not replayed as alerts.

## Connect Facebook

> **⚠️ IMPORTANT: FACEBOOK SETUP IS OPTIONAL AND INVOLVED.** Hype Bot works without Facebook. You can monitor YouTube channels and send alerts to Discord without creating a Facebook Page or Meta developer app. Facebook setup is a separate, multi-step process involving Meta permissions, a Facebook Page, and an HTTPS domain. Skip this section if you do not need Facebook alerts.

The signed-in dashboard has a **Facebook setup guide** with the step-by-step flow and troubleshooting. Open **Facebook → Open the Facebook setup guide** after signing in.

Hype Bot can publish to a Facebook **Page**, not to a personal Facebook profile. A Page can represent a creator, hobby, or brand; it does not have to be a business. The Facebook account you authorize must have permission to create content on the Page. The current version sends all Facebook alerts to one selected Page.

### If you need to create a Page

1. Sign in to Facebook with the account you plan to connect to Hype Bot.
2. Open [Facebook's Create a Page screen](https://www.facebook.com/pages/create/).
3. Enter a Page name, choose a fitting category (for example, Digital Creator), add an optional description, and create the Page.
4. Make sure that same account has permission to create content on the Page. See [Facebook Page access settings](https://www.facebook.com/help/187316341316631) if you need to check or change access.

### Create the Meta app

1. Register for a [Meta for Developers account](https://developers.facebook.com/) if you do not already have one.
2. From [My Apps](https://developers.facebook.com/apps/), choose **Create App**. Enter an app name and a contact email associated with the Facebook account you use to manage Pages. Use an inbox you check regularly; Meta may contact you about the app.
3. Under **Use cases**, select **Manage everything on your Page**. In the creation wizard shown here, this Page use case cannot be selected together with **Authenticate and request data from users with Facebook Login**. Choose the Page management use case for Hype Bot's Page publishing.
4. Under **Business**, you can choose **I don't want to connect a business portfolio yet** and associate one later. Meta notes that business verification may be required to complete verification and gain data access.
5. Review the **Requirements** and **Overview** screens, then choose **Create app**.
6. In the app dashboard, open **Customize the Manage everything on your Page use case** and configure the Page permissions and login callback described below.

### Configure permissions and OAuth

Facebook requires an HTTPS URL with a domain name that routes to Hype Bot. It cannot use an IP address by itself or plain `http://localhost:8018`. Where Hype Bot is hosted is up to you; the key requirement is that the domain-based HTTPS address and callback are configured for Meta.

1. In the Page use case's permissions, verify that `pages_show_list` and `pages_manage_posts` show **Ready for testing**. Hype Bot uses them to list Pages and publish posts. If you need Pages linked to a Meta business portfolio, enable `business_management` for testing too; Meta requires it for `/me/accounts` to return business-linked Pages, and your Facebook account must have a role in that business. Hype Bot does not request `pages_read_engagement`. Meta may require app review or business verification for use beyond development. Skip unrelated permissions. For a private development test, leave **Actions → Add to App Review** alone unless broader access is needed. Then return to the app dashboard, expand **Facebook Login for Business** in the left sidebar, and choose **Settings**. Leave **Client OAuth login**, **Web OAuth login**, **Enforce HTTPS**, and **Use Strict Mode for redirect URIs** enabled. Do not enter the callback in **Redirect URI Validator**; that box only checks a URI. Enter Hype Bot’s exact callback in **Valid OAuth Redirect URIs** (the field lower on the page), then choose **Save Changes**:

   ```text
   https://hypebot.example.com/destinations/facebook/callback
   ```

   The address must exactly match `APP_BASE_URL` plus `/destinations/facebook/callback`.
2. Add `META_APP_ID` and `META_APP_SECRET` to `/opt/hype-bot/.env` on Debian.
3. Recreate the container so it loads the new settings:

   ```sh
   docker rm -f hype-bot
   docker run -d --name hype-bot --restart unless-stopped --publish 192.168.150.3:8018:8000 --env-file .env --volume hype-bot-data:/data hype-bot:local
   ```

   This keeps your `hype-bot-data` volume.
4. Open Hype Bot through its HTTPS domain. On the **Facebook** page, select **Authorize with Meta**, sign in, and choose the Page. The dashboard also shows the setup checklist and callback URL.
5. Select **Publish test post** when you are ready. It creates a real, visible post on the selected Page.

The current version sends Facebook alerts to one selected Page for all channels. It cannot yet send one channel to a business Page and another to a creator Page.

## Stop, start, and update

On Windows, run these in PowerShell. On Debian, run them in SSH from `/opt/hype-bot`:

```sh
docker stop hype-bot
docker start hype-bot
```

To update on Debian after GitHub Actions publishes a new image, run `docker pull ghcr.io/godofjesters/hype-bot:latest`, remove the old container with `docker rm -f hype-bot`, then run the same `docker run` command from your install section. Do not remove the `hype-bot-data` volume. Copy that `docker run` line somewhere safe; you will need it when updating. On Windows development installs, continue to build from source as described in the Windows section.

For backups, rollback, logs, YouTube quota, and other advanced notes, see [OPERATIONS.md](OPERATIONS.md).
