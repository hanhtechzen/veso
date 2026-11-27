#!/usr/bin/env bash
# Sao lưu hằng đêm (cron): dump PostgreSQL giữ 14 bản trên VPS.
# Nếu đã khai báo lưu trữ ngoài bằng `rclone config` (remote tên 'backup'), chép thêm bản dump và bản chụp thô lên đó,
# giữ 30 ngày. Chưa khai báo thì chỉ lưu trên VPS (vẫn chạy, không báo lỗi) — nên khai báo để phòng mất cả VPS.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups

STAMP=$(date +%Y%m%d-%H%M)
OUT=backups/db-$STAMP.dump
REMOTE=${RCLONE_REMOTE:-backup:luckey}

docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$OUT"
[ -s "$OUT" ] || { echo "LỖI: bản dump rỗng"; rm -f "$OUT"; exit 1; }
echo "Đã dump cơ sở dữ liệu: $OUT ($(du -h "$OUT" | cut -f1))"

# Giữ 14 bản dump hằng đêm trên máy
ls -1t backups/db-*.dump | tail -n +15 | xargs -r rm -f

if command -v rclone >/dev/null && rclone listremotes 2>/dev/null | grep -qx "${REMOTE%%:*}:"; then
  rclone copy "$OUT" "$REMOTE/db/"
  docker run --rm -v luckey_rawdata:/raw:ro -v "$HOME/.config/rclone:/config/rclone:ro" rclone/rclone \
    copy /raw "$REMOTE/raw/" --max-age 48h
  rclone delete "$REMOTE/db/" --min-age 30d
  echo "Đã chép lên lưu trữ ngoài $REMOTE"
else
  echo "Chưa khai báo lưu trữ ngoài (rclone remote '${REMOTE%%:*}'): bản sao lưu chỉ nằm trên VPS."
fi
echo "Sao lưu xong lúc $(date)"
