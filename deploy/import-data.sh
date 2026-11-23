#!/usr/bin/env bash
# Chạy trên VPS để nạp dữ liệu chuyển từ máy cũ (tệp tạo bởi deploy/export-data.sh):
#   bash deploy/import-data.sh backups/chuyen-du-lieu-NGAY.dump
# THAY THẾ toàn bộ dữ liệu hiện có trên VPS. Tự sao lưu dữ liệu cũ trước khi nạp.
set -euo pipefail
cd "$(dirname "$0")/.."
DUMP=${1:?Cách dùng: bash deploy/import-data.sh backups/chuyen-du-lieu-NGAY.dump}
[ -f "$DUMP" ] || { echo "Không thấy tệp $DUMP"; exit 1; }
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

read -r -p "Dữ liệu hiện có trên máy này sẽ bị THAY bằng $DUMP. Gõ 'dong y' để tiếp tục: " A
[ "$A" = "dong y" ] || { echo "Đã hủy."; exit 1; }

mkdir -p backups
$COMPOSE up -d db
until $COMPOSE exec -T db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do sleep 1; done
BAK=backups/truoc-nap-du-lieu-$(date +%Y%m%d-%H%M).dump
$COMPOSE exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BAK"
echo "1/4 Đã sao lưu dữ liệu cũ: $BAK"

echo "2/4 Tạm dừng API và worker..."
$COMPOSE stop api worker >/dev/null 2>&1 || true

echo "3/4 Nạp dữ liệu..."
# --no-owner: tên người dùng cơ sở dữ liệu trên VPS có thể khác máy cũ
$COMPOSE exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --no-privileges' < "$DUMP"

echo "4/4 Khởi động lại và tự kiểm tra..."
$COMPOSE up -d
for i in $(seq 1 60); do $COMPOSE exec -T api python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/healthz')" >/dev/null 2>&1 && break; sleep 2; done
$COMPOSE exec -T api python -m luckyvision.cli migrate
N=$($COMPOSE exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT count(*) FROM lottery_draws WHERE current_version IS NOT NULL"' | tr -d '[:space:]')
echo "Xong: $N kỳ quay đã có kết quả. Nếu có lỗi, nạp lại bản cũ: bash deploy/import-data.sh $BAK"
