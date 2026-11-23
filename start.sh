#!/usr/bin/env bash
# Chạy LuckyVision trên Linux, WSL (Ubuntu trong Windows) hoặc VPS thử nghiệm.
#   cd ~/luckey && bash start.sh
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "Chưa có Docker. Cài bằng: curl -fsSL https://get.docker.com | sudo sh"; exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker chưa chạy hoặc bạn chưa có quyền dùng Docker."
  echo "  Bật Docker:      sudo service docker start"
  echo "  Cấp quyền:       sudo usermod -aG docker \$USER   (rồi đóng và mở lại cửa sổ WSL)"
  exit 1
fi

# Tệp tải từ Windows có thể mang ký tự xuống dòng kiểu Windows (CRLF): chuyển về kiểu Linux
for f in .env .env.example Caddyfile deploy/*.sh; do [ -f "$f" ] && sed -i 's/\r$//' "$f"; done

FIRST=0
if [ ! -f .env ]; then
  FIRST=1
  cp .env.example .env
  # Không dùng tr | head: với pipefail, tr nhận SIGPIPE và làm script dừng giữa chừng
  DBPW=$(od -An -N18 -tx1 /dev/urandom | tr -d ' \n')
  sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$DBPW/" .env
  echo "Đã tạo tệp .env (mật khẩu cơ sở dữ liệu ngẫu nhiên)."
fi

docker compose up -d --build
docker compose up -d --force-recreate --no-deps caddy   # luôn dùng Caddyfile mới nhất
echo "Đang chờ API sẵn sàng..."
for i in $(seq 1 60); do
  if curl -fsS http://localhost/healthz >/dev/null 2>&1; then break; fi
  sleep 2
done

if [ "$FIRST" = 1 ]; then
  # Dữ liệu mẫu để xem thử giao diện
  docker compose exec -T api python -m luckyvision.cli collect --date 2026-10-26
  docker compose exec -T api python -m luckyvision.cli collect --date 2026-10-29
  echo
  # Tài khoản quản trị đầu tiên (mật khẩu tạm, bắt đổi ở lần đăng nhập đầu)
  docker compose exec -T api python -m luckyvision.cli create-admin --username admin --name "Quản trị"
  echo "Hãy chép lại mật khẩu tạm ở trên."
fi
docker compose exec -T api python -m luckyvision.cli forecast

cat << 'MSG'

Mở trên trình duyệt Windows:
  Trang kết quả:    http://localhost
  Công cụ:          http://localhost/cong-cu/
  Trực tiếp:        http://localhost/live.html
  Dự báo và AI:     http://localhost/du-doan.html
  Quản trị:         http://localhost/admin.html  (tên đăng nhập: admin)

Hiện mới có dữ liệu mẫu 2 ngày. Bước tiếp theo: mục 6 trong HUONG-DAN-CHAY.md để bật nguồn và tải lịch sử.
Tự kiểm tra: docker compose exec api python -m luckyvision.cli doctor
MSG
