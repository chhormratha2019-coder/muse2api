# muse2api — Ubuntu / Cloudflare Tunnel deployment

Isolated instance deployed on **185.143.228.203**. It does not share any port,
user, directory, nginx site, or systemd unit with the other projects on the box.

## What was deployed

| Item | Value |
|---|---|
| Hostname | `muse2api.crdubber-api.world` |
| Service | `muse2api.service` (systemd) |
| App user | `muse2api` (system user, no login shell) |
| Code | `/opt/muse2api` |
| Python venv | `/opt/muse2api/venv` |
| Data (accounts/media) | `/opt/muse2api/data` |
| Chrome profile | `/opt/muse2api/home/muse2api-profiles` |
| Secrets | `/etc/muse2api.env` (mode 600) |
| Listen address | `127.0.0.1:6391` (loopback only) |
| CDP port | `19211` (loopback only) |
| Browser | `/usr/bin/google-chrome` |
| Resource guard | `MemoryMax=4G`, `CPUQuota=200%` |
| Version | **v1.6.12** (deployed 2026-11-20, commit `1b70d8f`) — upstream `czg86389-hub/muse2api` |
| Dashboard languages | 中文 / English / **ខ្មែរ** (switcher in the header) |
| Creator page | `/studio` — Muse Studio (EN/KM/ZH, async task UX) |

Because it binds to loopback, **no ufw or nginx change is required**. Cloudflare
Tunnel connects from the same host to `localhost:6391`.

## 1. Add the Cloudflare Tunnel public hostname

Cloudflare Zero Trust dashboard → **Networks → Tunnels** → select the tunnel that
serves `crdubber-api.world` → **Public Hostname → Add a public hostname**:

| Field | Value |
|---|---|
| Subdomain | `muse2api` |
| Domain | `crdubber-api.world` |
| Path | *(empty)* |
| Type | `HTTP` |
| URL | `localhost:6391` |

Save. Cloudflare creates the DNS record automatically. No server reload needed.

> Why HTTP and not HTTPS: the tunnel terminates TLS at Cloudflare's edge and
> forwards plain HTTP to the loopback port. uvicorn itself serves HTTP.

## 2. Verify

```bash
curl -s https://muse2api.crdubber-api.world/healthz
# {"status":"ok", ...}
```

Local check (no DNS needed):

```bash
curl -s http://127.0.0.1:6391/healthz
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:6391/v1/models   # 401
```

## 3. Use it

- Admin: `https://muse2api.crdubber-api.world/admin?key=<MUSE2API_KEY>`
- Studio: `https://muse2api.crdubber-api.world/studio`
- API base: `https://muse2api.crdubber-api.world/v1`
- The key lives in `/etc/muse2api.env` (`MUSE2API_KEY`).

Import your muse.ai account either from the admin page or with
`tools/get_muse_cookie.py --base https://muse2api.crdubber-api.world --key <KEY>`.
No account data was copied from the local machine.

## 4. Update the code

```bash
# On your PC: build a clean tarball (excludes .env and data/)
# NOTE: `git archive HEAD` exports *committed* code — commit your changes first,
# otherwise you will deploy the previous version.
git add -A && git commit -m "chore: sync to upstream v1.6.12 + Khmer dashboard"
git archive --format=tar HEAD -o /tmp/muse2api.tar
scp /tmp/muse2api.tar root@185.143.228.203:/tmp/muse2api.tar

# On the server
tar -xf /tmp/muse2api.tar -C /opt/muse2api
chown -R root:muse2api /opt/muse2api
chmod -R g+rX,g-w,o-rwx /opt/muse2api
/opt/muse2api/venv/bin/pip install -r /opt/muse2api/requirements.txt --quiet
systemctl restart muse2api
curl -s http://127.0.0.1:6391/healthz
```

`/etc/muse2api.env` and `/opt/muse2api/data` are never touched by an update.

For a risky upgrade, test first on a throwaway instance (same venv, separate
port/CDP/profile), then switch. Example used for the v1.6.12 upgrade:

```bash
# staging copy
rm -rf /opt/muse2api-staging && mkdir -p /opt/muse2api-staging
tar -xf /tmp/muse2api.tar -C /opt/muse2api-staging --strip-components=1
cp /opt/muse2api/data/accounts.json /opt/muse2api-staging/data/
# env: MUSE2API_PORT=6392, MUSE2API_CDP_PORT=19212, MUSE2API_HOME=/opt/muse2api-staging
# unit: muse2api-staging.service (same venv, /opt/muse2api/venv/bin/python)
# verify /healthz, /v1/models, one chat and one image, then:
systemctl stop muse2api-staging
cd /opt/muse2api-staging && tar -cf - --exclude=./data --exclude=./home . | tar -xf - -C /opt/muse2api
systemctl restart muse2api
```

## 5. Operations

```bash
systemctl status muse2api
journalctl -u muse2api -f
systemctl restart muse2api
```

Rollback / remove this instance only:

```bash
systemctl disable --now muse2api
rm -f /etc/systemd/system/muse2api.service
systemctl daemon-reload
# then optionally: rm -rf /opt/muse2api /etc/muse2api.env /var/log/muse2api
# and remove the muse2api public hostname in the Cloudflare dashboard
```

## Notes

- Essential cookie is `hatch_sess` only (upstream v1.6.12 `ESSENTIAL_COOKIES`).
  `hatch_vml` is an optional workspace token (≈2 days) and `hatch_gw` /
  `hatch_native_auth_device` are optional identifiers — a missing `hatch_gw` does
  **not** block import or generation.
- **Khmer UI (km)** lives in `admin.html` as `I18N_KM`, `I18N_KM_HTML` and
  `I18N_KM_PATTERNS`, layered on upstream's zh→en mechanism. Any key we did not
  translate falls back to English automatically. To add a language, extend
  `LANGS`, the `#langSel` options, and the same three dictionaries.
- The one-click upstream upgrade buttons (`#btnBannerUpgrade`, `#btnRepoPull`) are
  hidden on purpose: an online upgrade replaces `admin.html` and would wipe the
  Khmer translation. Upgrade manually with the tarball flow in section 4, then
  re-apply `admin.html`.
- The Cloudflare edge cuts a request that sends no response byte for ~100s. muse2api
  image/video jobs are asynchronous (submit → poll `/v1/videos/{id}`), so they are
  not affected. Very long non-streaming chat calls can hit that limit; use streaming.
- Keep `MUSE2API_UPDATER_ENABLED=0` and `MUSE2API_ALLOW_WEB_PUSH=0`.
- `data/` holds live muse.ai session cookies. Restrict access and back it up securely.
- Pre-upgrade backups on the server: `/root/muse2api-live-backup-*.tar.gz`
  (code + `data/`, excludes `venv/` and `home/`).
