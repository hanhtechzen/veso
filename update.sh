#!/usr/bin/env bash
# Cập nhật XS247 trên Linux/WSL: chép bản mới đè lên (giữ .env) rồi chạy  bash update.sh
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "Không thấy .env: chạy bash start.sh cho lần đầu"; exit 1; }
for f in .env Caddyfile deploy/*.sh; do [ -f "$f" ] && sed -i 's/\r$//' "$f"; done
mkdir -p backups; STAMP=$(date +%Y%m%d-%H%M)
echo "1/3 Sao lưu cơ sở dữ liệu..."
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "backups/truoc-cap-nhat-$STAMP.dump"
echo "2/3 Dựng lại và khởi động..."
docker compose up -d --build
# Caddy không tự đọc lại Caddyfile: tạo lại để chắc chắn dùng cấu hình mới
docker compose up -d --force-recreate --no-deps caddy
sleep 8
echo "3/3 Tự kiểm tra..."
docker compose exec -T api python -m xs247.cli migrate
docker compose exec -T api python -m xs247.cli doctor
echo "Xong. Mở http://localhost và nhấn Ctrl+F5."
