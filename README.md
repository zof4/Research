# QuickDrop

A tiny Flask web app for quickly sharing photos/files between devices.

## Features
- Upload files from the browser.
- Download/view files from `/files/<filename>` links.
- File list sorted newest first.

## Run locally
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PORT=8003 python app.py
```
Then open `http://YOUR_SERVER_IP:8003`.

## Exact SSH deployment steps for Oracle Linux on port 8003

> Replace placeholders before running:
> - `YOUR_USER` (for example `opc`)
> - `YOUR_SERVER_IP`
> - `~/quickdrop` local folder where this repo is located

### 1) From your local machine: copy project to the server
```bash
cd ~/quickdrop
tar --exclude='.git' --exclude='.venv' -czf quickdrop.tar.gz .
scp quickdrop.tar.gz YOUR_USER@YOUR_SERVER_IP:/tmp/
```

### 2) SSH to the server
```bash
ssh YOUR_USER@YOUR_SERVER_IP
```

### 3) On the server: install system packages
```bash
sudo dnf install -y python3 python3-pip policycoreutils-python-utils firewalld
sudo systemctl enable --now firewalld
```

### 4) Put app files in `/opt/quickdrop`
```bash
sudo mkdir -p /opt/quickdrop
sudo tar -xzf /tmp/quickdrop.tar.gz -C /opt/quickdrop
sudo chown -R YOUR_USER:YOUR_USER /opt/quickdrop
cd /opt/quickdrop
```

### 5) Create Python venv and install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 6) Set a strong app secret and quick test on 8003
```bash
export QUICKDROP_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
PORT=8003 python app.py
```
- Verify from another terminal: `curl -I http://YOUR_SERVER_IP:8003`
- Press `Ctrl+C` to stop.

### 7) Create a systemd service that always runs on port 8003
```bash
sudo tee /etc/systemd/system/quickdrop.service >/dev/null <<'EOF'
[Unit]
Description=QuickDrop Flask app
After=network.target

[Service]
Type=simple
User=YOUR_USER
Group=YOUR_USER
WorkingDirectory=/opt/quickdrop
Environment="PATH=/opt/quickdrop/.venv/bin"
Environment="PORT=8003"
Environment="QUICKDROP_SECRET_KEY=CHANGE_ME_TO_A_LONG_RANDOM_VALUE"
ExecStart=/opt/quickdrop/.venv/bin/python /opt/quickdrop/app.py
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

### 8) Open firewall port 8003
```bash
sudo firewall-cmd --permanent --add-port=8003/tcp
sudo firewall-cmd --reload
sudo firewall-cmd --list-ports
```

### 9) Validate it is reachable
```bash
curl -I http://127.0.0.1:8003
```
From another device/browser, open:
- `http://YOUR_SERVER_IP:8003`

### 10) Helpful operations over SSH
```bash
sudo systemctl restart quickdrop
sudo systemctl stop quickdrop
sudo systemctl start quickdrop
sudo journalctl -u quickdrop -f
```

## Notes
- Uploaded files are stored in `uploads/`.
- This is intentionally simple and has no authentication; do not expose it publicly without access controls.
