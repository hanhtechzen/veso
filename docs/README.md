# Tài liệu

- **Thiết kế kỹ thuật bộ thu thập** (bản đầy đủ, có sơ đồ):
  https://claude.ai/artifact/ABLkE9Dh8sVSnPNhkTp1gg
- **PRD**: `LuckyVision_PRD_v1_0.md` (bản gốc của chủ dự án).

## Mã nguồn so với thiết kế

| Thiết kế | Bản cài đặt |
| --- | --- |
| Bảng `expected_draws` | Gộp vào `lottery_draws`: tác vụ lập lịch tạo sẵn dòng trạng thái `scheduled` kèm `warn_at`, `critical_at` |
| Mã kỳ Power 6/55 `power655-01417` | `vl-power655-2026-10-29` (theo ngày, giống các miền khác); số kỳ Vietlott lưu ở cột `draw_seq` |
| Khung giờ theo dõi lưu trong DB | Khai báo trong `backend/luckyvision/config.py` (`WINDOWS`) |
| WAL-G sao lưu liên tục | Bản đầu dùng `pg_dump` hằng đêm (`deploy/backup.sh`) |
| Mở cổng 443 cho dải IP Cloudflare | Dùng Cloudflare Tunnel: không mở cổng web nào, chỉ SSH |
| Cổng quản trị (giao diện) | `web/admin.html`: tài khoản (scrypt), phiên cookie, xác thực hai lớp TOTP, khóa sau 5 lần sai |
| Bảng `forecasts` của PRD | `forecasts` (không sửa được, có trigger) + `forecast_evaluations`; 5 mô hình trong `luckyvision/forecast` |

## Trạng thái kỳ quay

`scheduled` → `collected` (có số đầu tiên) → `validated` (đủ giải, đúng định dạng) → `published`
(hai nguồn khớp và tự xác minh, hoặc quản trị duyệt). Mọi bất thường chuyển sang `needs_review`.
Trang công khai chỉ hiển thị kỳ có `current_version`; khi sửa, phiên bản cũ vẫn hiển thị đến lúc bản mới được duyệt.
