#!/usr/bin/env bash
# Dựng VPS Ubuntu 24.04 cho XS247. Chạy MỘT LẦN với quyền root:
#   sudo bash deploy/setup-vps.sh
# Làm: cập nhật hệ thống, Docker, người dùng 'deploy', SSH chỉ bằng khóa, tường lửa chỉ mở SSH, fail2ban,
# tự cập nhật bản vá, múi giờ Việt Nam, swap (máy ít RAM), giới hạn log Docker, lịch sao lưu hằng đêm.
set -euo pipefail

APP_DIR=/opt/luckey
DEPLOY_USER=deploy

[ "$(id -u)" = 0 ] || { echo "Hãy chạy bằng quyền root: sudo bash deploy/setup-vps.sh"; exit 1; }

# Không khóa người dùng ra ngoài: chỉ tắt đăng nhập bằng mật khẩu khi đã có khóa SSH
if [ ! -s /root/.ssh/authorized_keys ] && [ ! -s "/home/$DEPLOY_USER/.ssh/authorized_keys" ]; then
  echo "Chưa có khóa SSH trên máy này. Từ máy của bạn, chạy trước:  ssh-copy-id root@IP-VPS"
  echo "rồi chạy lại script. (Script sẽ tắt đăng nhập bằng mật khẩu, nên cần khóa để vào lại.)"
  exit 1
fi

echo "==> Cập nhật hệ thống và cài gói cần thiết"
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl git ufw fail2ban unattended-upgrades rclone
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "==> Múi giờ Việt Nam (log và lịch sao lưu theo giờ VN)"
timedatectl set-timezone Asia/Ho_Chi_Minh || true

echo "==> Swap 2 GB nếu máy dưới 4 GB RAM (tránh bị tắt tiến trình khi dựng Docker)"
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [ "$MEM_MB" -lt 3900 ] && ! swapon --show | grep -q .; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "==> Cài Docker Engine và Compose plugin"
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi
# Giới hạn log mặc định cho mọi container (dự phòng cho container ngoài docker-compose.prod.yml)
if [ ! -f /etc/docker/daemon.json ]; then
  echo '{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}' > /etc/docker/daemon.json
  systemctl restart docker
fi
systemctl enable --now docker

echo "==> Tạo người dùng triển khai '${DEPLOY_USER}'"
id "$DEPLOY_USER" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$DEPLOY_USER"
usermod -aG docker "$DEPLOY_USER"
mkdir -p "/home/$DEPLOY_USER/.ssh" && chmod 700 "/home/$DEPLOY_USER/.ssh"
if [ -f /root/.ssh/authorized_keys ] && [ ! -f "/home/$DEPLOY_USER/.ssh/authorized_keys" ]; then
  cp /root/.ssh/authorized_keys "/home/$DEPLOY_USER/.ssh/authorized_keys"
fi
chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys" 2>/dev/null || true
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

echo "==> Lịch sao lưu hằng đêm lúc 02:15 (người dùng ${DEPLOY_USER})"
CRON="15 2 * * * ${APP_DIR}/deploy/backup.sh >> ${APP_DIR}/backups/backup.log 2>&1"
( crontab -u "$DEPLOY_USER" -l 2>/dev/null | grep -v 'deploy/backup.sh'; echo "$CRON" ) | crontab -u "$DEPLOY_USER" -

cat <<MSG

Xong phần máy chủ. Các bước tiếp theo nằm trong HUONG-DAN-DUA-LEN-VPS.md (từ Bước 5).
Đăng nhập lại bằng:  ssh ${DEPLOY_USER}@$(hostname -I | awk '{print $1}')
MSG
