#!/usr/bin/env bash
# Khôi phục thử bản dump mới nhất vào một PostgreSQL tạm để chắc chắn bản sao lưu dùng được.
set -euo pipefail
cd "$(dirname "$0")/.."
LATEST=$(ls -1t backups/db-*.dump | head -1)
echo "Khôi phục thử $LATEST"
docker run -d --rm --name lv-restore-test -e POSTGRES_PASSWORD=test postgres:16-alpine >/dev/null
trap 'docker stop lv-restore-test >/dev/null' EXIT
until docker exec lv-restore-test pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
docker exec -i lv-restore-test pg_restore -U postgres -d postgres --no-owner < "$LATEST"
N=$(docker exec lv-restore-test psql -U postgres -tAc "SELECT count(*) FROM lottery_draws")
echo "Khôi phục thành công: $N kỳ quay"
