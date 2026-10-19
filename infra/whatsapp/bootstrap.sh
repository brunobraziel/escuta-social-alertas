#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose python3 curl
systemctl enable --now docker
install -d -m 700 /etc/escuta-whatsapp/secrets /etc/escuta-whatsapp/config
install -d -m 700 /var/lib/escuta-whatsapp/{sessions,delivery}
install -d -m 755 /opt/escuta-whatsapp
# Shutdown is independent of containers. An ephemeral external IP is released on stop.
cat > /etc/systemd/system/escuta-whatsapp-stop.service <<'EOF'
[Unit]
Description=Stop WhatsApp VM after the collection deadline
[Service]
Type=oneshot
ExecStart=/sbin/shutdown -h now
EOF
cat > /etc/systemd/system/escuta-whatsapp-stop.timer <<'EOF'
[Unit]
Description=WhatsApp deadline 24 October 2026 23:59 Fortaleza
[Timer]
OnCalendar=2026-10-25 03:00:00 UTC
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now escuta-whatsapp-stop.timer
