# Dropper / QuickDrop Caddy recovery runbook

This document is for restoring the original Dropper/QuickDrop app behind Caddy after another application took over the same server.

Repo: `zof4/Research`
Server IP: `129.149.122.156`
App file: `app.py`
Default app port: `8003`

## Goal

Make the original Dropper app work again on the same host as another application by:

1. keeping Dropper healthy on `127.0.0.1:8003`,
2. putting it behind Caddy at a subpath such as `/dropper`, and
3. updating the Flask app so URL generation works correctly behind that prefix.

---

## 1) Required code change in `app.py`

The app currently defines routes at `/`, `/files`, `/reader`, `/text`, `/latex`, `/chat`, etc. When it is mounted under a Caddy subpath like `/dropper`, Flask needs forwarded-prefix support so `url_for(...)` and redirects keep the `/dropper` prefix.

### Add this import near the other imports

```python
from werkzeug.middleware.proxy_fix import ProxyFix
```

### Add this block right after `app.permanent_session_lifetime = timedelta(days=LOGIN_DAYS)`

```python
app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1,
    x_port=1,
    x_prefix=1,
)
```

### Resulting section should look like this

```python
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.secret_key = os.environ.get("QUICKDROP_SECRET_KEY") or secrets.token_hex(32)
app.permanent_session_lifetime = timedelta(days=LOGIN_DAYS)
app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1,
    x_port=1,
    x_prefix=1,
)
```

Notes:
- No `requirements.txt` change is required because `werkzeug` is already pulled in through Flask.
- This change is only needed if Dropper lives at `/dropper` or another subpath.
- If Dropper is moved back to `/` as the primary root app, this code is still safe.

---

## 2) Verify the app itself without Caddy

SSH to the server and test the app directly first.

```bash
ssh opc@129.149.122.156
cd /Research
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
export QUICKDROP_SECRET_KEY='replace-this-with-a-long-random-secret'
PORT=8003 python app.py
```

In a second shell on the server:

```bash
curl -I http://127.0.0.1:8003
```

Expected result: the app returns a normal HTTP response. If this fails, fix the app/service before touching Caddy.

---

## 3) Run it under systemd

Create `/etc/systemd/system/quickdrop.service`:

```ini
[Unit]
Description=QuickDrop Flask app
After=network.target

[Service]
Type=simple
User=opc
Group=opc
WorkingDirectory=/Research
Environment="PATH=/Research/.venv/bin"
Environment="PORT=8003"
Environment="QUICKDROP_SECRET_KEY=replace-this-with-a-long-random-secret"
Environment="QUICKDROP_PDFLATEX_BIN=pdflatex"
ExecStart=/Research/.venv/bin/python /Research/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Then enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now quickdrop
sudo systemctl status quickdrop --no-pager
sudo journalctl -u quickdrop -n 100 --no-pager
```

Validate again:

```bash
curl -I http://127.0.0.1:8003
```

---

## 4) Restore Caddy with both apps on the same host

If the new app should remain on `/`, mount Dropper under `/dropper`.

Example `/etc/caddy/Caddyfile`:

```caddy
http://129.149.122.156 {
    encode gzip zstd

    handle_path /dropper* {
        reverse_proxy 127.0.0.1:8003 {
            header_up X-Forwarded-Prefix /dropper
        }
    }

    handle {
        reverse_proxy 127.0.0.1:3000
    }
}
```

Replace `127.0.0.1:3000` with the actual upstream for the newer application.

Why `handle_path` + `X-Forwarded-Prefix` are both used:
- `handle_path /dropper*` strips `/dropper` before proxying to Flask, so Flask still receives normal paths like `/`, `/files`, `/reader`, etc.
- `X-Forwarded-Prefix /dropper` tells Flask it is externally mounted under `/dropper`, which allows `url_for(...)` and redirects to generate the correct public URLs.

If instead Dropper should own `/` again, then point the root `handle` back to `127.0.0.1:8003` and move the newer app to its own subpath.

---

## 5) Validate Caddy and reload

```bash
sudo caddy fmt --overwrite /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo systemctl status caddy --no-pager
sudo journalctl -u caddy -n 100 --no-pager
```

---

## 6) End-to-end checks

Run these on the server:

```bash
curl -I http://127.0.0.1:8003
curl -I http://129.149.122.156/dropper
```

Then test in a browser:

- `http://129.149.122.156/` should load the newer app.
- `http://129.149.122.156/dropper` should load Dropper.
- Internal navigation inside Dropper should continue to use `/dropper/...` URLs.

---

## 7) Fast diagnosis matrix

### Case A: `curl http://127.0.0.1:8003` fails
Problem is the app or service, not Caddy.

Check:

```bash
sudo systemctl status quickdrop --no-pager
sudo journalctl -u quickdrop -n 200 --no-pager
```

### Case B: `127.0.0.1:8003` works but `/dropper` fails
Problem is Caddy config, or the app is missing the `ProxyFix` change.

Check:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo journalctl -u caddy -n 200 --no-pager
```

### Case C: `/dropper` loads but links/redirects lose the prefix
The `ProxyFix(... x_prefix=1 ...)` change is missing, or Caddy is not sending:

```caddy
header_up X-Forwarded-Prefix /dropper
```

---

## 8) Suggested PR scope for the code agent

Make a PR that does only this:

1. update `app.py` to add `ProxyFix` import,
2. wrap `app.wsgi_app` with `ProxyFix(..., x_prefix=1)`,
3. optionally add a short deployment note in `README.md` stating that when served from `/dropper` behind Caddy, the proxy must send `X-Forwarded-Prefix /dropper`.

Keep infra changes (`systemd`, `Caddyfile`) on-server, not in the repo, unless there is a deployment folder already meant for them.
