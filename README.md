# LuckyVision (Luckey)

Hệ thống thu thập kết quả xổ số tự động, API và luồng realtime cho LuckyVision, chạy trên **một VPS** bằng Docker Compose.
Hướng dẫn chạy từng bước: `HUONG-DAN-CHAY.md`. Thiết kế chi tiết: `docs/README.md`.

```
Luckey/
├─ backend/                 Python 3.12: worker thu thập + API FastAPI
│  ├─ luckyvision/
│  │  ├─ domain/            Cơ cấu giải, kiểm tra, đối chiếu nguồn (không phụ thuộc DB)
│  │  ├─ sources/           Bộ chuyển đổi nguồn: fixture (tệp mẫu), http_json (nhà cung cấp)
│  │  ├─ collector/         Tải, lưu bản gốc, xử lý, lập lịch kỳ quay, theo dõi trực tiếp
│  │  ├─ api/               REST /v1, SSE, /v1/auth (đăng nhập), /v1/admin, /v1/forecasts, /v1/ai
│  │  ├─ site/              Trang công khai tạo sẵn HTML cho SEO (Jinja2), sitemap, robots
│  │  ├─ forecast/          5 mô hình dự báo (gồm hồi quy logistic), tạo trước giờ quay, chấm điểm, kiểm thử lùi
│  │  ├─ migrations/        Lược đồ PostgreSQL + dữ liệu danh mục
│  │  ├─ worker.py          Tiến trình nền (APScheduler, giờ Việt Nam)
│  │  └─ cli.py             Lệnh quản trị
│  ├─ fixtures/             Kết quả mẫu để chạy thử
│  └─ tests/                Kiểm thử (pytest)
├─ web/cong-cu/index.html   Công cụ tương tác (dò vé, máy thời gian, tạo bộ số, sổ dự đoán, đấu trường), lấy dữ liệu từ máy chủ
├─ web/sw.js, manifest      Ứng dụng cài được trên điện thoại (PWA), chạy ngoại tuyến
├─ web/live.html            Tường thuật trực tiếp: lịch quay + bảng kết quả nhận qua SSE
├─ web/du-doan.html         Dự báo kỳ tới, hiệu quả mô hình, trợ lý AI, AI chọn số
├─ web/admin.html           Trang quản trị: đăng nhập, xác thực hai lớp, duyệt, nhập, nguồn, tài khoản, nhật ký
├─ deploy/                  Script dựng VPS, sao lưu, khôi phục thử
├─ docker-compose.yml       db, redis, api, worker, caddy
├─ docker-compose.prod.yml  Bổ sung cho VPS: Cloudflare Tunnel, không mở cổng 80/443
├─ Caddyfile                Reverse proxy: /v1/* -> api, còn lại -> web
├─ start.ps1                Chạy nhanh trên Windows
└─ .github/workflows/       Kiểm thử và tự triển khai khi đẩy lên nhánh main
```

## 1. Chạy trên Windows (C:\Luckey)

1. Cài **Docker Desktop** (bật WSL 2) và mở nó lên.
2. Giải nén `Luckey.zip` vào `C:\` để có thư mục `C:\Luckey`.
3. Mở PowerShell:

   ```powershell
   cd C:\Luckey
   Set-ExecutionPolicy -Scope Process Bypass
   .\start.ps1
   ```

   Script tạo tệp `.env` (kèm token quản trị ngẫu nhiên, in ra màn hình), dựng các container, rồi nạp dữ liệu mẫu.
4. Mở:
   - Trang web: http://localhost
   - Tường thuật trực tiếp (nối với API thật): http://localhost/live.html
   - Tài liệu API tương tác: http://localhost/v1/docs
   - Kết quả mới nhất miền Bắc: http://localhost/v1/draws/latest?region=mb

Chạy tay thay cho script: `copy .env.example .env`, sửa `POSTGRES_PASSWORD`, chạy `docker compose up -d --build`, rồi tạo tài khoản bằng `docker compose exec api python -m luckyvision.cli create-admin --username admin --name "Quản trị"`.

Dừng: `docker compose down` (giữ dữ liệu) hoặc `docker compose down -v` (xóa sạch dữ liệu).

## 2. Thử luồng realtime

Mở http://localhost/live.html?draw=mn-tp-hcm-2026-10-26 trên trình duyệt, hoặc nghe sự kiện thô trong PowerShell:

```powershell
curl.exe -N "http://localhost/v1/live/stream?region=mn"
```

Ở cửa sổ khác, giả lập buổi quay miền Nam từ tệp mẫu (mỗi số cách nhau 1,5 giây):

```powershell
docker compose exec api python -m luckyvision.cli plan --date 2026-10-26
docker compose exec api python -m luckyvision.cli simulate-live --draw mn-tp-hcm-2026-10-26
```

Cửa sổ thứ nhất sẽ nhận lần lượt `draw.started`, 18 sự kiện `prize.updated`, `draw.completed` và `draw.published`
(chỉ có `draw.published` nếu kỳ đó đã được công bố từ trước).

## 3. Lệnh quản trị

```
docker compose exec api python -m luckyvision.cli migrate
docker compose exec api python -m luckyvision.cli plan --date 2026-11-02
docker compose exec api python -m luckyvision.cli collect --date 2026-11-02
docker compose exec api python -m luckyvision.cli collect --draw mb-mb-2026-11-02
docker compose logs -f worker
```

Mã kỳ quay có dạng `<miền>-<đài>-<YYYY-MM-DD>`: `mb-mb-2026-10-29`, `mn-tp-hcm-2026-10-26`, `vl-power655-2026-10-29`.

## 4. API quản trị

Người dùng đăng nhập tại `/admin.html`. Script tự động có thể gọi API bằng header `Authorization: Bearer <token>` với token khai báo trong `ADMIN_TOKENS` (tối thiểu 24 ký tự; token bỏ qua xác thực hai lớp nên chỉ dùng khi cần).

```powershell
$H = @{ Authorization = "Bearer <token>" }
Invoke-RestMethod http://localhost/v1/admin/review-queue -Headers $H
Invoke-RestMethod http://localhost/v1/admin/draws/mn-tp-hcm-2026-10-26/candidates -Headers $H
```

| Việc | Lệnh |
| --- | --- |
| Hàng chờ xử lý | `GET /v1/admin/review-queue` |
| So sánh bản của các nguồn | `GET /v1/admin/draws/{id}/candidates` |
| Duyệt và công bố một bản | `POST /v1/admin/draws/{id}/verify` với `{"candidate_id": 12, "reason": "..."}` |
| Nhập tay hoặc sửa kết quả | `PUT /v1/admin/draws/{id}/results` với `{"prizes": {"db": ["472899"], ...}, "reason": "..."}` |
| Chuyển về chờ kiểm tra | `POST /v1/admin/draws/{id}/needs-review` với `{"reason": "..."}` |
| Tải lại ngay một kỳ | `POST /v1/admin/collect` với `{"draw_id": "..."}` |
| Cấu hình nguồn | `GET /v1/admin/sources`, `PATCH /v1/admin/sources/{code}` |
| Nhật ký | `GET /v1/admin/audit-logs` |

Kết quả nhập tay luôn ở trạng thái chờ xác minh; sửa kết quả đã công bố bắt buộc ghi lý do và tạo phiên bản mới, không ghi đè.

## 5. Tự động lấy kết quả mỗi ngày (bộ cào dữ liệu)

Dự án có sẵn ba bộ cào, viết theo cấu trúc trang mà các dự án mã nguồn mở đang dùng:

| Mã nguồn | Trang | Lấy gì |
| --- | --- | --- |
| `vietlott-web` | vietlott.vn (trang chính thức) | Power 6/55, kèm số kỳ |
| `minhngoc-web` | minhngoc.net | Miền Nam, 21 đài |
| `xoso-com-vn` | xoso.com.vn | Miền Bắc |

Cả ba **mặc định tắt**. Trước khi bật, hãy đọc điều khoản sử dụng của từng trang: việc dùng dữ liệu của họ là quyết định của chủ dự án.
Bộ cào tôn trọng robots.txt, tải chậm (5–10 giây một lần mỗi trang) và không tìm cách vượt qua chống bot.

**Bước 1: chạy thử trên máy bạn** (không lưu gì, chỉ in ra kết quả đọc được):

```powershell
docker compose exec api python -m luckyvision.cli probe-source vietlott-web --draw vl-power655-2026-10-29
docker compose exec api python -m luckyvision.cli probe-source minhngoc-web --draw mn-tp-hcm-2026-10-26
docker compose exec api python -m luckyvision.cli probe-source xoso-com-vn  --draw mb-mb-2026-10-29
```

Kết quả đúng sẽ in đủ các giải và dòng `Kiểm tra: hợp lệ`. Nếu báo bị chặn hoặc không tìm thấy kết quả, trang đã đổi cấu trúc
hoặc không cho truy cập tự động: đừng bật nguồn đó.

**Bước 2: bật nguồn và cấu hình tự công bố**

```powershell
docker compose exec api python -m luckyvision.cli source-enable vietlott-web
docker compose exec api python -m luckyvision.cli source-enable minhngoc-web
docker compose exec api python -m luckyvision.cli source-enable xoso-com-vn
docker compose exec api python -m luckyvision.cli sources
```

Trong `.env`, đặt `APP_ENV=prod` (tắt nguồn tệp mẫu) và chọn mức tin cậy:

- `MIN_SOURCES_BY_REGION=vl:1,mn:1,mb:1`: mỗi miền một nguồn là đủ, kết quả tự công bố ngay.
- `MIN_SOURCES_BY_REGION=vl:1` (mặc định): Power 6/55 tự công bố; miền Bắc, miền Nam chờ quản trị duyệt trong hàng chờ, hoặc
  tự công bố khi bạn thêm nguồn thứ hai và hai nguồn khớp nhau.

Rồi `docker compose up -d`. Từ đó worker tự lấy kết quả mỗi ngày theo lịch ở mục 3 của tài liệu thiết kế.
Nếu trang nguồn đổi giao diện, worker gửi cảnh báo "không nhận ra cấu trúc dữ liệu" và các kỳ sẽ báo "quá giờ".

**Thêm nguồn khác.** Nhà cung cấp trả JSON: chỉ cần thêm cấu hình, không viết mã:

```sql
INSERT INTO data_sources (code, name, kind, adapter, config, regions, legal_approved, enabled, rate_limit_ms, priority)
VALUES ('provider-x', 'Nhà cung cấp X', 'provider', 'http_json',
        '{"url_template": "https://api.x.vn/v1/results?province={province}&date={date}",
          "api_key_env": "PROVIDER_X_API_KEY", "prizes_path": "data.prizes",
          "prize_map": {"DB": "db", "G1": "g1", "G8": "g8"}, "complete_path": "data.complete"}',
        '{mn}', true, true, 5000, 10);
```

Trang web khác: viết lớp mới kế thừa `sources/scrape_base.py: ScrapeAdapter` (hai hàm `fetch` và `parse`, xem `minhngoc.py`),
đăng ký trong `sources/registry.py`, thêm HTML mẫu vào `tests/test_scrapers.py`.

Ở `APP_ENV=prod`, hai nguồn tệp mẫu `fixture-a`, `fixture-b` tự động bị bỏ qua.

## 6. Triển khai lên VPS (Ubuntu 24.04)

1. Trên VPS (quyền root): sao chép thư mục dự án lên rồi chạy `bash deploy/setup-vps.sh`
   (cài Docker, tường lửa chỉ mở SSH, fail2ban, tự cập nhật bản vá, user `deploy`).
2. Trên Cloudflare: tạo **Tunnel** (Zero Trust → Networks → Tunnels), trỏ tên miền tới `http://caddy:80`, lấy token.
   Có thể thêm **Cloudflare Access** cho đường dẫn `/v1/admin/*`.
3. Đăng nhập bằng user `deploy`:

   ```bash
   cd /opt/luckey
   cp .env.example .env && nano .env     # APP_ENV=prod, POSTGRES_PASSWORD, CLOUDFLARE_TUNNEL_TOKEN, cảnh báo
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```

4. Sao lưu: `rclone config` (tạo remote tên `backup`), rồi thêm cron
   `15 2 * * * /opt/luckey/deploy/backup.sh >> /opt/luckey/backups/backup.log 2>&1`.
   Kiểm tra định kỳ bằng `deploy/restore-test.sh`.
5. Tự triển khai: đẩy mã lên GitHub, thêm secrets `VPS_HOST` và `VPS_SSH_KEY`; mỗi lần đẩy lên `main`,
   GitHub Actions chạy kiểm thử rồi cập nhật VPS.

Yêu cầu: Docker Compose từ 2.24 trở lên (dùng thẻ `!reset` trong `docker-compose.prod.yml`).

## 7. Phát triển và kiểm thử

```powershell
cd C:\Luckey\backend
py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
```

## 8. Chưa làm trong bản này

- Mọi trang đã dùng dữ liệu thật từ máy chủ, kể cả trang Công cụ `/cong-cu/` (tải qua `/v1/export/tools`).
- Bộ cào chưa được chạy thử với trang thật (môi trường phát triển không truy cập được các trang này): dùng lệnh `probe-source` để kiểm tra trước khi bật.
- Miền Bắc và miền Trung mới có một nguồn (xoso.com.vn); miền Nam có hai nguồn để tự đối chiếu.
- Sao lưu liên tục bằng WAL-G (hiện là `pg_dump` hằng đêm), Ansible playbook, Sentry.
