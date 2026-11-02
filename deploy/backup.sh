#!/usr/bin/env bash
# Sao lưu hằng đêm: dump PostgreSQL + đồng bộ bản chụp thô ra object storage (rclone remote 'backup').
# Nâng cấp sau: dùng WAL-G để sao lưu liên tục (mất tối đa 5 phút dữ liệu), xem tài liệu thiết kế mục 7.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

STAMP=$(date +%Y%m%d-%H%M)
OUT=backups/db-$STAMP.dump
REMOTE=${RCLONE_REMOTE:-backup:luckey}

docker compose exec -T db pg_dump -U "${POSTGRES_USER:-luckey}" -d "${POSTGRES_DB:-luckey}" -Fc > "$OUT"
echo "Đã dump cơ sở dữ liệu: $OUT ($(du -h "$OUT" | cut -f1))"

rclone copy "$OUT" "$REMOTE/db/"
docker run --rm -v luckey_rawdata:/raw:ro -v "$HOME/.config/rclone:/config/rclone:ro" rclone/rclone \
  copy /raw "$REMOTE/raw/" --max-age 48h

# Giữ 7 bản dump trên máy, 30 ngày trên object storage
ls -1t backups/db-*.dump | tail -n +8 | xargs -r rm -f
rclone delete "$REMOTE/db/" --min-age 30d
echo "Sao lưu xong lúc $(date)"
