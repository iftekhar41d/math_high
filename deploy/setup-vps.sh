#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu/Debian VPS. Run once, manually, as a user
# with sudo access (not root). After this, CI/CD handles every future deploy.
#
# Usage: ./setup-vps.sh <git-repo-url> <domain-or-ip> [app-dir]
#
# Example: ./setup-vps.sh git@github.com:me/math-high.git app.example.com
set -euo pipefail

REPO_URL="${1:?Usage: setup-vps.sh <git-repo-url> <domain-or-ip> [app-dir]}"
DOMAIN="${2:?Usage: setup-vps.sh <git-repo-url> <domain-or-ip> [app-dir]}"
APP_DIR="${3:-$HOME/math-high}"
DEPLOY_USER="$(whoami)"

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
sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__DOMAIN__|$DOMAIN|g" \
  "$APP_DIR/deploy/nginx.conf" | sudo tee /etc/nginx/sites-available/math-high >/dev/null
sudo ln -sf /etc/nginx/sites-available/math-high /etc/nginx/sites-enabled/math-high
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo "==> Allowing passwordless restart/reload for CI/CD (scoped to just these two commands)"
SUDOERS_LINE="$DEPLOY_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart math-high-api, /usr/bin/systemctl reload nginx"
echo "$SUDOERS_LINE" | sudo tee /etc/sudoers.d/math-high-deploy >/dev/null
sudo chmod 440 /etc/sudoers.d/math-high-deploy
sudo visudo -c

echo "==> Setup complete."
echo "    App directory: $APP_DIR"
echo "    Service:       sudo systemctl status math-high-api"
echo "    Site:          http://$DOMAIN"
echo ""
echo "To enable HTTPS (requires DNS already pointing $DOMAIN at this server):"
echo "    sudo apt-get install -y certbot python3-certbot-nginx"
echo "    sudo certbot --nginx -d $DOMAIN"
echo ""
echo "Add '$APP_DIR' as the APP_DIR secret and '$DEPLOY_USER' as VPS_USER in your GitHub repo for CI/CD."
