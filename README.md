# Hype Bot

Hype Bot watches YouTube channels and sends new upload and livestream alerts to Discord and Facebook Pages.

## Pick where to run it

- **Try it on your Windows computer:** follow [Docker Desktop for Windows](#install-on-windows-with-docker-desktop).
- **Install it on your Debian server:** follow [Debian server install](#install-on-your-debian-server).

You only need to follow one install guide. Both use Docker commands; you do not need a `.yaml` or Compose file.

## Before you start

Have these ready:

- Docker Desktop (Windows) or Docker Engine (Debian).
- A YouTube Data API key, if you want channel monitoring.
- A Discord webhook, if you want Discord alerts.
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

### 3. Build and start the container

Run these commands from `/opt/hype-bot`:

```sh
docker build -t hype-bot:local .
docker run -d --name hype-bot --restart unless-stopped --publish 192.168.150.3:8018:8000 --env-file .env --volume hype-bot-data:/data hype-bot:local
```

The app uses port `8000` inside Docker. Port `8018` is the port Nginx Proxy Manager uses to reach it. Docker creates the `hype-bot-data` volume automatically.

Run this `docker run` command only for the first install. If the container already exists, use `docker start hype-bot`.

### 4. Point Nginx Proxy Manager to Hype Bot

Nginx Proxy Manager (NPM) is the web page you already use to manage your proxy hosts and certificates. These steps add one entry that sends requests for your Hype Bot web address to the app on your Debian server.

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
5. Leave the other options at their defaults and select **Save**.

#### Add HTTPS

1. Find the Hype Bot entry in **Proxy Hosts**, open its three-dot menu, and choose **Edit**.
2. Open the **SSL** tab.
3. If you already have a certificate for this exact domain, select it. Otherwise choose the option to request a new Let's Encrypt certificate, enter your email address, accept the terms, and save.
4. If shown, enable **Force SSL**, then select **Save**.

For a new Let's Encrypt certificate, the domain's public DNS must point to your home/server public IP, and your router/firewall must allow inbound port `80` to NPM while the certificate is requested. NPM uses that connection to prove you control the domain. Keep Docker's Hype Bot port `8018` private; do not forward `8018` from your router to the Internet. If you already have a working certificate for the domain, select it instead of requesting another one.

After saving, open `https://` followed by your Hype Bot domain in a browser while connected to your VPN. For example, open `https://hypebot.example.com`—not the raw IP and port. NPM's **Domain Names** field is the browser address; the **Forward Hostname / IP** and **Forward Port** fields tell NPM where the app is on your local network.

On the Debian server, check the app with:

```sh
docker inspect --format '{{.State.Health.Status}}' hype-bot
```

Wait for `healthy`. Then open the HTTPS domain in your browser and sign in.

## Use the dashboard

1. Open **Channels** and add a YouTube channel link.
2. Choose whether to monitor uploads, streams, or both. Stream alerts default to when YouTube schedules the stream.
3. Open **Notifications**. Add a Discord webhook and use **Send test message** if you want to confirm it works.
4. Open **Activity** to review detected events and delivery status.
5. Open **Settings** to switch between the Business and Gaming themes.

When a channel is first added, Hype Bot announces its upcoming public streams. It uses that time as the starting point for uploads, so older videos are not replayed as alerts.

## Connect Facebook

Facebook requires an HTTPS URL with a domain name that routes to Hype Bot. It cannot use an IP address by itself or plain `http://localhost:8018`. Where Hype Bot is hosted is up to you; the key requirement is that the domain-based HTTPS address and callback are configured for Meta.

1. The Meta app needs Facebook Login and Page permissions `pages_show_list` and `pages_manage_posts`. In its Facebook Login settings, add this redirect address, replacing the example domain with your own:

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
4. Open Hype Bot through its HTTPS domain. Under **Notifications**, select **Authorize with Meta**, sign in, and choose the Page.
5. Select **Publish test post** when you are ready. It creates a real, visible post on the selected Page.

The current version sends Facebook alerts to one selected Page for all channels. It cannot yet send one channel to a business Page and another to a personal Page.

## Stop, start, and update

On Windows, run these in PowerShell. On Debian, run them in SSH from `/opt/hype-bot`:

```sh
docker stop hype-bot
docker start hype-bot
```

To update after pulling new project files, build the new image, remove the old container, and start it again with the same `docker run` command from your install section. Do not remove the `hype-bot-data` volume. Copy that `docker run` line somewhere safe; you will need it when updating.

For backups, rollback, logs, YouTube quota, and other advanced notes, see [OPERATIONS.md](OPERATIONS.md).
