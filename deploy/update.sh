#!/usr/bin/env bash
# Cập nhật XS247 trên VPS. Cách dùng (trong /opt/luckey, sau khi chép bản mới đè lên, giữ nguyên .env):
#   bash deploy/update.sh
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "Không thấy .env, hãy cài lần đầu theo mục 10 của hướng dẫn"; exit 1; }
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
bash deploy/check-env.sh || { echo "Sửa .env theo các mục [LỖI] ở trên rồi chạy lại."; exit 1; }
mkdir -p backups
STAMP=$(date +%Y%m%d-%H%M)
echo "1/3 Sao lưu cơ sở dữ liệu..."
$COMPOSE exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "backups/truoc-cap-nhat-$STAMP.dump"
echo "    Đã lưu backups/truoc-cap-nhat-$STAMP.dump"
echo "2/3 Dựng lại và khởi động (tự áp dụng thay đổi cơ sở dữ liệu)..."
$COMPOSE up -d --build
# Caddy không tự đọc lại Caddyfile: tạo lại để chắc chắn dùng cấu hình mới
$COMPOSE up -d --force-recreate --no-deps caddy
sleep 8
echo "3/3 Tự kiểm tra..."
$COMPOSE exec -T api python -m xs247.cli migrate
$COMPOSE exec -T api python -m xs247.cli doctor
echo "Xong. Nếu trang vẫn hiện bản cũ, vào Cloudflare xóa bộ nhớ đệm (Caching, Purge Everything)."
