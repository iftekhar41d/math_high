#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu/Debian VPS. Run once, manually, as a user
# with sudo access (not root). After this, CI/CD handles every future deploy.
#
# Usage:  ./setup-vps.sh [domain] [repo-url] [app-dir]
#
# Every value has a default in the CONFIG block below. Override it for a single
# run with a positional arg OR an environment variable of the same name
# (the positional arg wins). Examples:
#
#   ./setup-vps.sh                                   # all defaults
#   ./setup-vps.sh app.example.com                   # just a different domain
#   DOMAIN=app.example.com LETSENCRYPT_EMAIL=me@example.com ./setup-vps.sh
set -euo pipefail

# ─── CONFIG ────────────────────────────────────────────────────────────────
DOMAIN="${1:-${DOMAIN:-math.mentisq.com}}"
REPO_URL="${2:-${REPO_URL:-https://github.com/iftekhar41d/math_high.git}}"
APP_DIR="${3:-${APP_DIR:-$HOME/math-high}}"
# Set this to an email address to provision HTTPS automatically (certbot runs
# non-interactively). Leave empty and the script just prints the manual command.
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:-}"
# ──────────────────────────────────────────────────────────────────────────

DEPLOY_USER="$(whoami)"
NGINX_SITE=/etc/nginx/sites-available/math-high

echo "==> Configuration for this run"
echo "    Domain:   $DOMAIN"
echo "    Repo:     $REPO_URL"
echo "    App dir:  $APP_DIR"
echo "    Run as:   $DEPLOY_USER"
if [ -n "$LETSENCRYPT_EMAIL" ]; then
  echo "    HTTPS:    automatic via certbot ($LETSENCRYPT_EMAIL)"
else
  echo "    HTTPS:    skipped (set LETSENCRYPT_EMAIL to automate it)"
fi
echo

echo "==> Installing system packages (git, python3, nginx)"
sudo apt-get update -y
sudo apt-get install -y git python3 python3-venv python3-pip nginx curl

if ! command -v node &>/dev/null; then
  echo "==> Installing Node.js 20.x (NodeSource)"
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi

echo "==> Opening firewall for SSH/HTTP/HTTPS (if ufw is in use)"
if command -v ufw &>/dev/null; then
  sudo ufw allow OpenSSH
  sudo ufw allow 80/tcp
  sudo ufw allow 443/tcp
  sudo ufw --force enable
fi

echo "==> Cloning repository"
if [ -d "$APP_DIR/.git" ]; then
  echo "Repo already present at $APP_DIR, pulling latest instead."
  git -C "$APP_DIR" pull
else
  git clone "$REPO_URL" "$APP_DIR"
fi

echo "==> Setting up Python venv and installing API dependencies"
cd "$APP_DIR/api"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "==> Applying database migrations (alembic upgrade head)"
.venv/bin/alembic upgrade head

echo "==> Building the web frontend"
cd "$APP_DIR/web"
npm install
npm run build

echo "==> Installing systemd service"
sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__DEPLOY_USER__|$DEPLOY_USER|g" \
  "$APP_DIR/deploy/math-high-api.service" | sudo tee /etc/systemd/system/math-high-api.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now math-high-api

echo "==> Installing nginx site config"
if sudo grep -q "managed by Certbot" "$NGINX_SITE" 2>/dev/null && [ "${FORCE_NGINX:-0}" != "1" ]; then
  echo "    $NGINX_SITE already has a Certbot-managed TLS block — leaving it as is."
  echo "    (re-run with FORCE_NGINX=1 to regenerate it from deploy/nginx.conf)"
else
  sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__DOMAIN__|$DOMAIN|g" \
    "$APP_DIR/deploy/nginx.conf" | sudo tee "$NGINX_SITE" >/dev/null
fi
sudo ln -sf "$NGINX_SITE" /etc/nginx/sites-enabled/math-high
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo "==> Allowing passwordless restart/reload for CI/CD (scoped to just these two commands)"
SUDOERS_LINE="$DEPLOY_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart math-high-api, /usr/bin/systemctl reload nginx"
echo "$SUDOERS_LINE" | sudo tee /etc/sudoers.d/math-high-deploy >/dev/null
sudo chmod 440 /etc/sudoers.d/math-high-deploy
sudo visudo -c

if [ -n "$LETSENCRYPT_EMAIL" ]; then
  echo "==> Provisioning HTTPS with Let's Encrypt"
  sudo apt-get install -y certbot python3-certbot-nginx
  if getent hosts "$DOMAIN" >/dev/null; then
    sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos \
      -m "$LETSENCRYPT_EMAIL" --redirect \
      || echo "!! certbot failed — check that $DOMAIN points here, then rerun: sudo certbot --nginx -d $DOMAIN"
  else
    echo "!! $DOMAIN does not resolve yet — skipping certbot for now."
    echo "   Once DNS points at this server, run:"
    echo "   sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m $LETSENCRYPT_EMAIL --redirect"
  fi
fi

echo
echo "==> Setup complete."
echo "    App directory: $APP_DIR"
echo "    Service:       sudo systemctl status math-high-api"
echo "    Site:          http://$DOMAIN"
if [ -z "$LETSENCRYPT_EMAIL" ]; then
  echo
  echo "To enable HTTPS (requires DNS already pointing $DOMAIN at this server):"
  echo "    sudo apt-get install -y certbot python3-certbot-nginx"
  echo "    sudo certbot --nginx -d $DOMAIN"
fi
echo
echo "GitHub repo secrets for CI/CD:"
echo "    VPS_HOST   = this server's IP or hostname"
echo "    VPS_USER   = $DEPLOY_USER"
echo "    VPS_SSH_KEY= the deploy private key"
echo "    APP_DIR    = $APP_DIR"
echo "    VPS_PORT   = SSH port (optional, defaults to 22)"
