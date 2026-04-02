# Dropper / QuickDrop recovery behind Caddy

This runbook restores the existing QuickDrop app after another app took over the same Oracle host and Caddy now needs to serve Dropper from a subpath such as `/dropper`.

## What changed in this branch

- Adds `wsgi.py`, a small entrypoint that wraps the existing Flask app with `ProxyFix`.
- This preserves forwarded host/proto/port information and, most importantly, honors `X-Forwarded-Prefix` so generated URLs continue to use `/dropper/...` when the app is mounted under a subpath.

## Why this is needed

The app still defines routes like `/`, `/files`, `/reader`, `/text`, `/latex`, and `/chat`. That works when QuickDrop owns the site root, but breaks when Caddy strips `/dropper` before proxying unless Flask is told that the public path prefix exists.

`wsgi.py` solves that by applying:

```python
ProxyFix(..., x_prefix=1)
```

## Server commands to run first

Run these on the Oracle host to confirm whether the failure is in the app, the service wiring, or Caddy.

### 1) Check the QuickDrop process and direct port

```bash
sudo systemctl status quickdrop --no-pager
sudo journalctl -u quickdrop -n 200 --no-pager
ss -ltnp | grep ':8003'
curl -I http://127.0.0.1:8003
```

### 2) Check Caddy config and logs

```bash
sudo cat /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl status caddy --no-pager
sudo journalctl -u caddy -n 200 --no-pager
```

### 3) Check the externally mounted Dropper path

```bash
curl -I http://127.0.0.1/dropper
curl -I http://129.149.122.156/dropper
```

## Recommended systemd change

If the app should run through the new proxied entrypoint, point the service to `wsgi.py` instead of `app.py`.

Example:

```ini
[Service]
WorkingDirectory=/Research
Environment="PATH=/Research/.venv/bin"
Environment="PORT=8003"
Environment="QUICKDROP_SECRET_KEY=replace-this-with-a-long-random-secret"
ExecStart=/Research/.venv/bin/python /Research/wsgi.py
Restart=always
RestartSec=3
```

Reload afterward:

```bash
sudo systemctl daemon-reload
sudo systemctl restart quickdrop
sudo systemctl status quickdrop --no-pager
```

## Recommended Caddy shape

If another app owns `/`, keep QuickDrop on `/dropper`.

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

Then reload Caddy:

```bash
sudo caddy fmt --overwrite /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

## Quick diagnosis

- If `curl -I http://127.0.0.1:8003` fails, the app or service is broken before Caddy is involved.
- If `127.0.0.1:8003` works but `/dropper` fails, the issue is Caddy config or missing `X-Forwarded-Prefix`.
- If `/dropper` loads but links or redirects lose the prefix, the app is not running through `wsgi.py` (or an equivalent `ProxyFix(x_prefix=1)` wrapper).
