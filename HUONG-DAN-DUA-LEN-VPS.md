# Đưa XS247 lên VPS (chạy 24/7, có tên miền và HTTPS)

Mô hình: **VPS Ubuntu** chạy toàn bộ hệ thống bằng Docker. **Cloudflare Tunnel** đưa tên miền vào máy chủ:
không mở cổng web nào ra Internet, HTTPS miễn phí, chống tấn công từ chối dịch vụ cơ bản.

```
Người dùng ──https──> Cloudflare ──đường hầm──> cloudflared ──> Caddy ──> API / trang web
                                                 (trên VPS, tường lửa chỉ mở SSH)
```

## Danh sách việc (đánh dấu khi xong)

- [ ] 1. Mã nguồn mới nhất đã đưa lên GitHub (kho **Private**)
- [ ] 2. Thuê VPS, đăng nhập được bằng khóa SSH
- [ ] 3. Chạy `setup-vps.sh` (Docker, tường lửa, sao lưu hằng đêm)
- [ ] 4. Tải mã nguồn về VPS
- [ ] 5. Tên miền trên Cloudflare, tạo Tunnel, lấy token
- [ ] 6. Điền `.env`, `check-env.sh` không còn [LỖI]
- [ ] 7. Khởi động, chuyển dữ liệu từ máy cũ sang
- [ ] 8. Bật xác thực hai lớp cho quản trị, tắt bản chạy trên máy nhà
- [ ] 9. Sao lưu ra ngoài VPS, cảnh báo khi có sự cố
- [ ] 10. Google Search Console
- [ ] 11. Tự động cập nhật khi đẩy mã mới (tùy chọn)

Chi phí tham khảo: VPS 2 vCPU, 4 GB RAM khoảng 200.000–400.000đ/tháng; tên miền .com khoảng 300.000đ/năm
(.vn đắt hơn và cần giấy tờ tùy thân); Cloudflare gói Free đủ dùng.

---

## Bước 1. Đưa mã nguồn lên GitHub

VPS lấy mã từ GitHub, nên mọi thay đổi phải được commit và đẩy lên trước. Kho phải để **Private**
(Settings, General, Danger Zone, Change visibility).

## Bước 2. Thuê VPS

- Hệ điều hành **Ubuntu 24.04**, tối thiểu **2 vCPU, 4 GB RAM, 40 GB SSD**, ảo hóa **KVM** (chạy được Docker).
- Đặt máy ở Việt Nam hoặc Singapore để người dùng trong nước truy cập nhanh.
- Từ máy của bạn (PowerShell hoặc WSL), tạo khóa SSH nếu chưa có rồi chép lên VPS:

```bash
ssh-keygen -t ed25519            # bấm Enter để nhận mặc định
ssh-copy-id root@IP-VPS          # nhập mật khẩu root nhà cung cấp gửi (lần cuối dùng mật khẩu)
ssh root@IP-VPS                  # phải vào được mà không hỏi mật khẩu
```

Trên Windows không có `ssh-copy-id`: mở tệp `C:\Users\<tên>\.ssh\id_ed25519.pub`, chép nội dung,
rồi trên VPS dán vào cuối tệp `/root/.ssh/authorized_keys`.

## Bước 3. Dựng máy chủ

Từ thư mục dự án trên máy của bạn:

```bash
scp deploy/setup-vps.sh root@IP-VPS:/root/
ssh root@IP-VPS "bash /root/setup-vps.sh"
```

Script cài Docker, tạo người dùng `deploy`, chỉ cho đăng nhập SSH bằng khóa, tường lửa chỉ mở SSH, fail2ban,
tự cập nhật bản vá bảo mật, múi giờ Việt Nam, swap (máy ít RAM), giới hạn dung lượng log, và lịch sao lưu
cơ sở dữ liệu lúc 02:15 hằng đêm. Từ đây đăng nhập bằng `ssh deploy@IP-VPS`.

## Bước 4. Tải mã nguồn về VPS

Kho Private nên VPS cần một "khóa chỉ đọc" (deploy key):

```bash
ssh deploy@IP-VPS
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub
```

Trên GitHub: kho `veso`, **Settings, Deploy keys, Add deploy key**, dán nội dung vừa in, **không** tích
"Allow write access". Rồi:

```bash
git clone git@github.com:hanhtechzen/veso.git /opt/luckey
cd /opt/luckey
```

## Bước 5. Tên miền và Cloudflare Tunnel

1. Đăng ký tài khoản Cloudflare, **Add a domain**, chọn gói **Free**.
2. Ở nơi mua tên miền, đổi **nameserver** sang hai địa chỉ Cloudflare đưa ra. Chờ Cloudflare báo "Active"
   (vài phút đến vài giờ).
3. Cloudflare, **Zero Trust, Networks, Tunnels, Create a tunnel**, chọn **Cloudflared**, đặt tên `xs247`.
   Ở bước cài đặt, chép **token** (chuỗi dài sau `--token`). Không cần chạy lệnh cài trên trang đó.
4. Tab **Public Hostname**, thêm:
   - Hostname: `xs247.mobi` (để trống Subdomain), Service: **HTTP**, URL: `caddy:80`
   - Thêm một dòng nữa cho `www` trỏ cùng `caddy:80`.
5. Cloudflare, tên miền, **SSL/TLS, Edge Certificates**: bật **Always Use HTTPS**.

## Bước 6. Điền `.env`

```bash
cd /opt/luckey
cp .env.example .env
openssl rand -hex 18        # dùng làm POSTGRES_PASSWORD
nano .env
```

Các dòng phải sửa:

| Biến | Giá trị |
|---|---|
| `APP_ENV` | `prod` |
| `SITE_URL` | `https://xs247.mobi` |
| `POSTGRES_PASSWORD` | chuỗi vừa tạo bằng `openssl` |
| `CLOUDFLARE_TUNNEL_TOKEN` | token ở Bước 5 |
| `MIN_SOURCES_BY_REGION` | giống máy đang chạy, ví dụ `vl:1,mega:1,mb:1,mt:1` (thêm `mn:1` hoặc `mn:2` tùy số nguồn đã bật) |
| `SUPPORT_CONTACT` | Zalo hoặc email hỗ trợ thật |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | để nhận cảnh báo (xem Bước 9) |
| `AI_API_KEY` | nếu dùng trợ lý AI |

Mẹo: mở `.env` trên máy đang chạy để chép lại `MIN_SOURCES_BY_REGION`, khóa AI, Telegram.
**Không** chép `SITE_URL`, `APP_ENV`, `POSTGRES_PASSWORD` của máy cũ.

Kiểm tra:

```bash
bash deploy/check-env.sh
```

Phải không còn dòng **[LỖI]**. Các dòng **[NÊN SỬA]** không chặn chạy nhưng nên xử lý sớm.

## Bước 7. Khởi động và chuyển dữ liệu

Khởi động:

```bash
cd /opt/luckey
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Lần dựng đầu mất vài phút. Mở `https://xs247.mobi`: thấy trang chủ (chưa có dữ liệu) là đường hầm đã thông.

**Chuyển dữ liệu từ máy đang chạy** (kết quả, lịch sử, nguồn đã bật, tài khoản quản trị và thành viên, vé thử).
Trên máy cũ (WSL):

```bash
cd ~/veso
bash deploy/export-data.sh
scp backups/chuyen-du-lieu-*.dump deploy@IP-VPS:/opt/luckey/backups/
```

Trên VPS:

```bash
cd /opt/luckey
bash deploy/import-data.sh backups/chuyen-du-lieu-NGAY-GIO.dump    # gõ: dong y
docker compose exec api python -m xs247.cli doctor
```

Không chuyển dữ liệu mà muốn bắt đầu từ đầu: tạo tài khoản quản trị bằng
`docker compose exec api python -m xs247.cli create-admin --username admin --name "Quản trị"`,
rồi bật nguồn theo mục 6 của `HUONG-DAN-CHAY.md`.

## Bước 8. Bảo mật và tắt bản cũ

1. Vào `https://xs247.mobi/admin.html`, đăng nhập, **bật xác thực hai lớp** (mục 7 của `HUONG-DAN-CHAY.md`).
2. **Tắt bản đang chạy trên máy nhà**, để không còn hai nơi cùng thu thập và người dùng không vào nhầm:
   ```bash
   cd ~/veso && docker compose stop
   ```
   (Dùng `stop`, **không** dùng `down -v`: giữ lại dữ liệu cũ phòng khi cần.)

## Bước 9. Sao lưu ra ngoài và cảnh báo

**Sao lưu**: VPS đã tự dump cơ sở dữ liệu lúc 02:15 mỗi đêm vào `/opt/luckey/backups` (giữ 14 bản).
Để phòng mất cả VPS, chép thêm ra ngoài (Cloudflare R2 hoặc Backblaze B2 đều có mức miễn phí):

```bash
rclone config          # tạo remote tên đúng là: backup
bash deploy/backup.sh  # chạy thử, cuối phải có "Đã chép lên lưu trữ ngoài"
```

Mỗi tháng thử khôi phục một lần để chắc bản sao lưu dùng được: `bash deploy/restore-test.sh`.

**Cảnh báo khi có sự cố**:
- Telegram: tạo bot với @BotFather lấy `TELEGRAM_BOT_TOKEN`, nhắn cho bot một tin rồi lấy `TELEGRAM_CHAT_ID`
  (chi tiết ở mục 8 của `HUONG-DAN-CHAY.md`). Hệ thống báo khi nguồn lỗi, quá giờ chưa có kết quả.
- Máy chủ ngừng chạy: tạo một "check" miễn phí ở healthchecks.io, dán đường dẫn vào `HEALTHCHECKS_URL`.
  Worker gửi tín hiệu mỗi phút, im lặng thì healthchecks.io gửi email cho bạn.

Sửa `.env` xong thì chạy lại: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`.

## Bước 10. Google Search Console

1. Vào search.google.com/search-console, **Add property**, chọn **Domain**, nhập `xs247.mobi`.
2. Google đưa một bản ghi TXT: thêm vào Cloudflare (**DNS, Records, Add record**, loại TXT, tên `@`).
3. Sau khi xác minh: mục **Sitemaps**, gửi `https://xs247.mobi/sitemap.xml`.

Google cần vài ngày đến vài tuần để đưa trang lên kết quả tìm kiếm.

## Bước 11. Cập nhật bản mới

**Thủ công** (mỗi khi có mã mới trên GitHub):

```bash
ssh deploy@IP-VPS
cd /opt/luckey && git pull && bash deploy/update.sh
```

`update.sh` kiểm tra `.env`, sao lưu trước khi cập nhật, dựng lại, áp dụng thay đổi cơ sở dữ liệu và tự kiểm tra.

**Tự động** khi đẩy mã lên nhánh `main` (GitHub Actions chạy test rồi mới cập nhật):
1. Trên máy của bạn tạo một khóa riêng cho GitHub: `ssh-keygen -t ed25519 -f gh-deploy -N ""`.
2. Thêm nội dung `gh-deploy.pub` vào cuối `/home/deploy/.ssh/authorized_keys` trên VPS.
3. GitHub, kho `veso`, **Settings, Secrets and variables, Actions**, thêm:
   `VPS_HOST` = IP của VPS, `VPS_SSH_KEY` = toàn bộ nội dung tệp `gh-deploy` (khóa riêng). Xóa tệp khóa riêng trên máy sau đó.

Test không qua thì GitHub không cập nhật VPS.

---

## Xử lý sự cố

| Hiện tượng | Kiểm tra |
|---|---|
| Trang báo lỗi 1033 / không vào được | Đường hầm: `docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail 50 cloudflared` (sai token, hoặc Public Hostname chưa trỏ `caddy:80`) |
| Lỗi 502 | API chưa chạy xong hoặc lỗi: `docker compose logs --tail 100 api` |
| Không có kết quả mới | `docker compose logs --tail 100 worker`, rồi `docker compose exec api python -m xs247.cli doctor` |
| Trang vẫn hiện bản cũ sau cập nhật | Cloudflare, **Caching, Configuration, Purge Everything** |
| Đầy ổ đĩa | `df -h`, `docker system df`; dọn ảnh cũ: `docker image prune -f` |
| Cần quay về dữ liệu trước khi cập nhật | `bash deploy/import-data.sh backups/truoc-cap-nhat-NGAY-GIO.dump` |

Lệnh thường dùng trên VPS: thêm `-f docker-compose.yml -f docker-compose.prod.yml` sau `docker compose` khi
khởi động lại (`up -d`). Các lệnh xem log, `exec` không cần thêm.
