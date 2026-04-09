# QuickDrop

A tiny Flask web app for quickly sharing photos/files between devices.

## Features
- User accounts (username + password) with isolated per-user storage/workspaces.
- Built-in admin account: username `admin`, password `dropper`.
- Non-admin accounts get a 1 GB storage limit each by default.
- A text transfer area with visible history for quick copy/paste on another device.
- A LaTeX rendering area that saves PDFs for download from `/latex/<filename>`.
- A reader tool with both cached and live views for remote webpages, including Reddit-aware JSON parsing and a proxy fallback mode for 403-heavy sites.
- An HTML viewer tool where you can paste HTML/CSS/JS, save static interactive pages, preview them in a sandboxed frame, and download `.html` files.
- Dedicated Access / Files / Reader / Text / LaTeX pages so each tool has its own URL instead of anchor scrolling.
- Live total storage usage summary, remaining space, and file count.
- Configurable per-file and total-storage limits to reduce server abuse.

## Run locally
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export QUICKDROP_SECRET_KEY=change-me
export QUICKDROP_MAX_UPLOAD_MB=100
export QUICKDROP_MAX_STORAGE_MB=1024
export QUICKDROP_PDFLATEX_BIN=pdflatex
PORT=8003 python app.py
```
Then open `http://YOUR_SERVER_IP:8003`.

## Docker Compose troubleshooting (service names and ports)

If you get `no such service: platform-caddy`, your compose command is targeting a service name that is not defined in your current compose file.

Use:
```bash
docker compose config --services
docker compose ps
```

Then rebuild/restart the actual app service from that list:
```bash
docker compose build <actual-app-service>
docker compose up -d <actual-app-service>
docker compose logs --tail=200 -f <actual-app-service>
```

QuickDrop itself listens on port `8003` by default (not `3003`), so validate the app first:
```bash
ss -ltnp | grep ':8003'
curl -i 127.0.0.1:8003
```

## Exact SSH deployment steps for Oracle Linux on port 8003

> Replace placeholders before running:
> - `YOUR_REPO_SSH_URL` (example: `git@github.com:you/quickdrop.git`)
> - `YOUR_BRANCH` (example: `work`)
> - `YOUR_USER` (for example `opc`)
> - `YOUR_SERVER_IP`
>
> Important: run each command on its own line. If you paste `sudo dnf install ... sudo systemctl ...` as one line, `dnf` will treat `sudo` and `systemctl` as extra package names and fail.

### 1) SSH to the server
```bash
ssh YOUR_USER@YOUR_SERVER_IP
```

### 2) On the server: install system packages
```bash
sudo dnf install -y git python3 python3-pip policycoreutils-python-utils firewalld texlive-scheme-basic
sudo systemctl enable --now firewalld
```

### 3) Clone the repo on the server
```bash
cd ~
git clone YOUR_REPO_SSH_URL quickdrop
cd quickdrop
git fetch --all
git checkout YOUR_BRANCH
git pull --ff-only origin YOUR_BRANCH
```

### 4) Create Python venv and install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 5) Set a strong app secret and quick test on 8003
```bash
export QUICKDROP_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
PORT=8003 python app.py
```
- Verify from another terminal: `curl -I http://YOUR_SERVER_IP:8003`
- Press `Ctrl+C` to stop.

### 6) Create a systemd service that always runs on port 8003
```bash
sudo tee /etc/systemd/system/quickdrop.service >/dev/null <<'EOF'
[Unit]
Description=QuickDrop Flask app
After=network.target

[Service]
Type=simple
User=YOUR_USER
Group=YOUR_USER
WorkingDirectory=/home/YOUR_USER/quickdrop
Environment="PATH=/home/YOUR_USER/quickdrop/.venv/bin"
Environment="PORT=8003"
Environment="QUICKDROP_SECRET_KEY=CHANGE_ME_TO_A_LONG_RANDOM_VALUE"
Environment="QUICKDROP_PDFLATEX_BIN=pdflatex"
ExecStart=/home/YOUR_USER/quickdrop/.venv/bin/python /home/YOUR_USER/quickdrop/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
```

Now set a real secret in that service file:
```bash
sudo sed -i "s#CHANGE_ME_TO_A_LONG_RANDOM_VALUE#$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')#" /etc/systemd/system/quickdrop.service
```

Enable + start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now quickdrop
sudo systemctl status quickdrop --no-pager
```

### 7) Open firewall port 8003
```bash
sudo firewall-cmd --permanent --add-port=8003/tcp
sudo firewall-cmd --reload
sudo firewall-cmd --list-ports
```

### 8) Validate it is reachable
```bash
curl -I http://127.0.0.1:8003
```
From another device/browser, open:
- `http://YOUR_SERVER_IP:8003`

### 9) Helpful operations over SSH
```bash
sudo systemctl restart quickdrop
sudo systemctl stop quickdrop
sudo systemctl start quickdrop
sudo journalctl -u quickdrop -f
```

### 10) One-command version after you know your repo URL and branch
```bash
ssh YOUR_USER@YOUR_SERVER_IP
sudo dnf install -y git python3 python3-pip policycoreutils-python-utils firewalld texlive-scheme-basic
sudo systemctl enable --now firewalld
cd ~
git clone YOUR_REPO_SSH_URL quickdrop
cd quickdrop
git fetch --all
git checkout YOUR_BRANCH
git pull --ff-only origin YOUR_BRANCH
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
sudo tee /etc/systemd/system/quickdrop.service >/dev/null <<'EOF'
[Unit]
Description=QuickDrop Flask app
After=network.target

[Service]
Type=simple
User=YOUR_USER
Group=YOUR_USER
WorkingDirectory=/home/YOUR_USER/quickdrop
Environment="PATH=/home/YOUR_USER/quickdrop/.venv/bin"
Environment="PORT=8003"
Environment="QUICKDROP_SECRET_KEY=CHANGE_ME_TO_A_LONG_RANDOM_VALUE"
Environment="QUICKDROP_PDFLATEX_BIN=pdflatex"
ExecStart=/home/YOUR_USER/quickdrop/.venv/bin/python /home/YOUR_USER/quickdrop/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
sudo sed -i "s#CHANGE_ME_TO_A_LONG_RANDOM_VALUE#$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')#" /etc/systemd/system/quickdrop.service
sudo systemctl daemon-reload
sudo systemctl enable --now quickdrop
sudo firewall-cmd --permanent --add-port=8003/tcp
sudo firewall-cmd --reload
curl -I http://127.0.0.1:8003
```

## Notes
- Uploaded files are stored in `uploads/`.
- Upload, delete, login, and logout forms use CSRF tokens tied to the Flask session, so cross-site form submission is harder.
- The app defaults to a **100 MB per-file cap** and a **1 GB per-user storage cap** for non-admin users. Override with `QUICKDROP_MAX_UPLOAD_MB` and `QUICKDROP_MAX_STORAGE_MB`.
- Upload/delete/text/LaTeX/reader write access uses per-user login sessions that persist for `QUICKDROP_LOGIN_DAYS` days (default `30`).
- Persistent app data now defaults to `~/.quickdrop_storage` (or `$XDG_STATE_HOME/quickdrop`) so it survives app restarts and repo updates. You can still override the location with `QUICKDROP_STORAGE_ROOT=/path/to/storage`. Existing data in the old `./.dropper_storage` path is automatically migrated when empty.
- Text history is stored in `data/text_history.json`. Rendered LaTeX PDFs are stored in `latex_outputs/` and indexed in `data/latex_history.json`.
- LaTeX rendering calls `pdflatex` (or whatever `QUICKDROP_PDFLATEX_BIN` points to), so the server needs a TeX installation for that feature.
- When a filename already exists, QuickDrop now keeps the old file and stores the new upload with a numbered suffix instead of overwriting it.
- Files that are not obviously safe to render inline are now sent as downloads to reduce browser-side script surprises from uploaded HTML/SVG-like content.
- This is intentionally simple and now uses per-user accounts in signed browser sessions; downloads are still limited to authenticated users. Do not expose it broadly without access controls such as a VPN, reverse-proxy auth, or firewall restrictions.
- Set `QUICKDROP_SECRET_KEY` in production so Flask sessions survive restarts and keep their CSRF protection stable.

## Security answer: can someone brick the server by uploading junk?

**Less likely now, but not impossible if you expose it too broadly.** The main server-bricking risk for this app is filling disk space. The app now defends against that by:

- rejecting uploads above the configured per-file size limit (`QUICKDROP_MAX_UPLOAD_MB`, default `100`),
- rejecting uploads once the configured total storage limit (`QUICKDROP_MAX_STORAGE_MB`, default `2048`) is full,
- refusing to overwrite an existing file with the same name, and
- forcing download for most non-image/non-text file types instead of rendering them inline.

What this still **does not** solve:

- Downloads and text/PDF history are still intentionally visible to anyone who can reach the app. If that is too open, add firewall restrictions, VPN, or reverse-proxy auth.
- A malicious user can still fill the allowed quota with garbage files until the app limit is reached. That protects the rest of the server **only if your configured cap is comfortably below free disk space**.
- Running this directly on the public internet is still risky. Best practice is to restrict access with firewall source IP rules, a VPN, or reverse-proxy authentication.

For a small personal transfer box, a practical setup is: set `QUICKDROP_MAX_STORAGE_MB` to something intentionally small for your server, keep the app behind a firewall allowlist if possible, and monitor free disk with `df -h`.

## Password answer

The app now has a built-in admin login (`admin` / `dropper`). Other users are created the first time they log in with a new username/password pair.
