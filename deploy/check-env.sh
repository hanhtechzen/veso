#!/usr/bin/env bash
# Kiểm tra .env trước khi chạy thật trên VPS. Lỗi (ĐỎ) thì dừng, cảnh báo (VÀNG) thì vẫn chạy.
#   bash deploy/check-env.sh            # kiểm tra .env trong thư mục dự án
#   bash deploy/check-env.sh path/.env  # kiểm tra một tệp khác
set -uo pipefail
cd "$(dirname "$0")/.."
ENV_FILE=${1:-.env}
[ -f "$ENV_FILE" ] || { echo "Không thấy $ENV_FILE. Tạo bằng: cp .env.example .env"; exit 1; }

# Đọc giá trị một biến trong .env (không chạy tệp, tránh lệnh lạ trong .env)
val() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- | sed -e 's/\r$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/"; }

ERR=0; WARN=0
bad()  { echo "  [LỖI]     $1"; ERR=$((ERR + 1)); }
warn() { echo "  [NÊN SỬA] $1"; WARN=$((WARN + 1)); }
ok()   { echo "  [ổn]      $1"; }

echo "Kiểm tra $ENV_FILE cho môi trường chạy thật:"

[ "$(val APP_ENV)" = prod ] && ok "APP_ENV=prod" || bad "APP_ENV phải là prod (đang là '$(val APP_ENV)'), nếu không trang sẽ dùng dữ liệu mẫu"

SU=$(val SITE_URL)
case "$SU" in
  https://localhost*|http://*) bad "SITE_URL phải là https://tên-miền-thật (đang là '$SU'): Google và nút chia sẻ dùng địa chỉ này" ;;
  https://*) ok "SITE_URL=$SU" ;;
  *) bad "SITE_URL chưa đặt hoặc sai dạng (ví dụ https://xs247.mobi)" ;;
esac

PW=$(val POSTGRES_PASSWORD)
if [ -z "$PW" ] || [ "$PW" = doi-mat-khau-nay ] || [ ${#PW} -lt 16 ]; then
  bad "POSTGRES_PASSWORD phải là chuỗi ngẫu nhiên từ 16 ký tự (tạo: openssl rand -hex 18)"
else ok "POSTGRES_PASSWORD đủ mạnh"; fi

[ -n "$(val CLOUDFLARE_TUNNEL_TOKEN)" ] && ok "Có CLOUDFLARE_TUNNEL_TOKEN" \
  || bad "Thiếu CLOUDFLARE_TUNNEL_TOKEN: không có thì người ngoài không vào được trang (xem hướng dẫn, bước Cloudflare)"

SA=$(val SITE_ADDRESS)
[ -z "$SA" ] || [ "$SA" = ":80" ] && ok "SITE_ADDRESS=:80 (Cloudflare lo HTTPS)" \
  || warn "SITE_ADDRESS='$SA': khi dùng Cloudflare Tunnel nên để :80"

MS=$(val MIN_SOURCES_BY_REGION)
for r in mb mt vl mega; do   # mn có 2 nguồn tự đối chiếu (MIN_MATCHING_SOURCES) nên không bắt buộc
  case ",$MS," in *",$r:"*) ;; *) warn "MIN_SOURCES_BY_REGION chưa có '$r:…' -> kết quả $r có thể phải chờ quản trị duyệt tay (đang là '$MS')" ;; esac
done

SC=$(val SUPPORT_CONTACT)
case "$SC" in ""|*"09xx"*|*"ten-mien"*) warn "SUPPORT_CONTACT còn để mẫu: thành viên quên mật khẩu sẽ không biết liên hệ ai" ;; *) ok "SUPPORT_CONTACT đã đặt" ;; esac

if [ -n "$(val TELEGRAM_BOT_TOKEN)" ] && [ -n "$(val TELEGRAM_CHAT_ID)" ]; then ok "Có cảnh báo Telegram"
elif [ -n "$(val SLACK_WEBHOOK_URL)" ]; then ok "Có cảnh báo Slack"
else warn "Chưa có kênh cảnh báo (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID): nguồn lỗi hay thiếu kết quả sẽ không ai biết"; fi

[ -n "$(val HEALTHCHECKS_URL)" ] && ok "Có HEALTHCHECKS_URL (báo khi máy chủ ngừng)" \
  || warn "Chưa có HEALTHCHECKS_URL: nên tạo miễn phí ở healthchecks.io để biết khi máy chủ ngừng chạy"

AT=$(val ADMIN_TOKENS)
[ -z "$AT" ] && ok "ADMIN_TOKENS để trống (an toàn)" || warn "ADMIN_TOKENS đang bật: token này bỏ qua xác thực hai lớp, chỉ dùng khi thật cần"

echo
if [ "$ERR" -gt 0 ]; then echo "Có $ERR lỗi phải sửa trong $ENV_FILE trước khi chạy."; exit 1; fi
echo "Không có lỗi chặn. $WARN mục nên sửa."
