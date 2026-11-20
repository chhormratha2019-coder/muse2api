#!/usr/bin/env bash
# ============================================================================
# Isolated Ubuntu deployment for muse2api.
#
#   ./install.sh /tmp/muse2api.tar
#
# Only touches:
#   /opt/muse2api                         (code + venv + data + chrome profile)
#   /etc/muse2api.env                     (secrets, mode 600)
#   /etc/systemd/system/muse2api.service  (unit)
#   /var/log/muse2api                     (log dir)
#
# It does NOT modify nginx, ufw, Cloudflare, or any other project's files.
# The app binds 127.0.0.1:6391; expose it with a Cloudflare Tunnel hostname.
# ============================================================================
set -euo pipefail

SRC="${1:-/tmp/muse2api.tar}"
APP=/opt/muse2api
SVC=muse2api
PORT=6391

[ "$(id -u)" -eq 0 ] || { echo "error: run as root" >&2; exit 1; }
[ -f "$SRC" ] || { echo "error: tarball not found: $SRC" >&2; exit 1; }
command -v python3 >/dev/null || { echo "error: python3 missing" >&2; exit 1; }

if [ ! -x /usr/bin/google-chrome ]; then
  echo "warn: /usr/bin/google-chrome not found; set MUSE2API_CHROMIUM in /etc/muse2api.env"
fi

if ! id "$SVC" >/dev/null 2>&1; then
  useradd --system --home-dir "$APP/home" --shell /usr/sbin/nologin --user-group "$SVC"
fi

mkdir -p "$APP" "$APP/data" "$APP/home" /var/log/muse2api

echo "[1/5] extracting code"
tar -xf "$SRC" -C "$APP"

echo "[2/5] python venv + dependencies"
[ -x "$APP/venv/bin/python" ] || python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install --upgrade pip --quiet
"$APP/venv/bin/pip" install -r "$APP/requirements.txt" --quiet

echo "[3/5] permissions"
chown -R root:"$SVC" "$APP"
chmod -R g+rX,g-w,o-rwx "$APP"
chown -R "$SVC":"$SVC" "$APP/data" "$APP/home" /var/log/muse2api
chmod 750 "$APP" "$APP/data" "$APP/home"

echo "[4/5] env file"
if [ ! -f /etc/muse2api.env ]; then
  KEY="m2a_$(openssl rand -hex 24)"
  umask 077
  cat > /etc/muse2api.env <<EOF
MUSE2API_HOME=$APP
MUSE2API_HOST=127.0.0.1
MUSE2API_PORT=$PORT
MUSE2API_KEY=$KEY
MUSE2API_CHROMIUM=/usr/bin/google-chrome
MUSE2API_CDP_PORT=19211
MUSE2API_PROFILE_ROOT=$APP/home/muse2api-profiles
MUSE2API_HOME_DIR=$APP/home
MUSE2API_CONCURRENCY=1
MUSE2API_IMAGE_TIMEOUT=300
MUSE2API_VIDEO_TIMEOUT=900
MUSE2API_CHAT_TIMEOUT=300
MUSE2API_UPDATER_ENABLED=0
MUSE2API_ALLOW_WEB_PUSH=0
PYTHONDONTWRITEBYTECODE=1
EOF
  chmod 600 /etc/muse2api.env
  echo "generated API key: $KEY"
else
  echo "keeping existing /etc/muse2api.env"
fi

echo "[5/5] systemd unit"
cat > /etc/systemd/system/muse2api.service <<'EOF'
[Unit]
Description=Muse2API bridge (isolated instance)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=muse2api
Group=muse2api
WorkingDirectory=/opt/muse2api
EnvironmentFile=/etc/muse2api.env
Environment=HOME=/opt/muse2api/home
ExecStart=/opt/muse2api/venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 6391
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

NoNewPrivileges=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
ProtectClock=yes
ProtectHostname=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK
RestrictRealtime=yes
RestrictSUIDSGID=yes
LockPersonality=yes
SystemCallArchitectures=native
CapabilityBoundingSet=
AmbientCapabilities=
UMask=0027
ReadWritePaths=/opt/muse2api/data /opt/muse2api/home /var/log/muse2api

MemoryMax=4G
CPUQuota=200%
KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "$SVC"
sleep 6
systemctl is-active "$SVC"
curl -s -m 10 -o /dev/null -w "health HTTP %{http_code}\n" "http://127.0.0.1:$PORT/healthz"
