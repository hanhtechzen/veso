#!/usr/bin/env bash
# Dựng VPS Ubuntu 24.04 cho LuckyVision. Chạy với quyền root:
#   curl -fsSL <đường dẫn tới tệp này> | bash      hoặc     sudo bash deploy/setup-vps.sh
set -euo pipefail

APP_DIR=/opt/luckey
DEPLOY_USER=deploy

echo "==> Cập nhật hệ thống và cài gói cần thiết"
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl git ufw fail2ban unattended-upgrades rclone
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "==> Cài Docker Engine và Compose plugin"
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

echo "==> Tạo người dùng triển khai '${DEPLOY_USER}'"
id "$DEPLOY_USER" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$DEPLOY_USER"
usermod -aG docker "$DEPLOY_USER"
mkdir -p "/home/$DEPLOY_USER/.ssh" && chmod 700 "/home/$DEPLOY_USER/.ssh"
if [ -f /root/.ssh/authorized_keys ] && [ ! -f "/home/$DEPLOY_USER/.ssh/authorized_keys" ]; then
  cp /root/.ssh/authorized_keys "/home/$DEPLOY_USER/.ssh/authorized_keys"
fi
chown -R "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"

echo "==> SSH: chỉ cho đăng nhập bằng khóa"
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl reload ssh || systemctl reload sshd || true

echo "==> Tường lửa: chỉ mở SSH (web đi qua Cloudflare Tunnel, không mở 80/443)"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw --force enable

echo "==> fail2ban cho SSH"
systemctl enable --now fail2ban

echo "==> Thư mục ứng dụng ${APP_DIR}"
mkdir -p "$APP_DIR" "$APP_DIR/backups"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"

cat <<MSG

Xong. Bước tiếp theo (đăng nhập bằng user ${DEPLOY_USER}):
  1. git clone <kho mã> ${APP_DIR} && cd ${APP_DIR}
  2. cp .env.example .env && nano .env      (APP_ENV=prod, mật khẩu, ADMIN_TOKENS, CLOUDFLARE_TUNNEL_TOKEN)
  3. docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
  4. rclone config                          (khai báo object storage cho sao lưu, đặt tên remote là 'backup')
  5. crontab -e  và thêm:  15 2 * * * ${APP_DIR}/deploy/backup.sh >> ${APP_DIR}/backups/backup.log 2>&1
MSG
