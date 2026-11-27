#!/usr/bin/env bash
# Chạy trên MÁY ĐANG CÓ DỮ LIỆU (WSL/máy Windows) để chuyển toàn bộ dữ liệu sang VPS:
#   bash deploy/export-data.sh
# Tạo tệp backups/chuyen-du-lieu-NGAY.dump (kết quả, lịch sử, tài khoản, vé thử...), rồi in lệnh chép lên VPS.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
OUT=backups/chuyen-du-lieu-$(date +%Y%m%d-%H%M).dump
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$OUT"
N=$(docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT count(*) FROM lottery_draws WHERE current_version IS NOT NULL"' | tr -d '[:space:]')
echo "Đã xuất $OUT ($(du -h "$OUT" | cut -f1), $N kỳ quay đã có kết quả)."
echo
echo "Chép lên VPS (thay IP-VPS):"
echo "  scp $OUT deploy@IP-VPS:/opt/luckey/backups/"
echo "Rồi trên VPS:"
echo "  cd /opt/luckey && bash deploy/import-data.sh backups/$(basename "$OUT")"
