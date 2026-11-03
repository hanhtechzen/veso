# Báo cáo kiểm tra LuckyVision

Ngày kiểm tra: 02/11/2026. Phạm vi: toàn bộ mã trong `C:\Luckey` (backend, các trang web, cấu hình triển khai).

## 1. Cách kiểm tra

- Tạo cơ sở dữ liệu trống, chạy đủ 6 migration, nạp khoảng 2.100 kỳ quay lịch sử để thử.
- Chạy API và worker cùng lúc, theo dõi nhật ký lỗi.
- Gọi lần lượt 32 điểm API, so mã trả về với mong đợi.
- Mở 8 trang và màn hình bằng trình duyệt tự động, ghi lại mọi lỗi JavaScript.
- Chạy lại các trang với chính sách bảo mật nội dung (CSP) mới để chắc không bị chặn nhầm.
- Thử tấn công: chèn mã độc vào tên đài (XSS), chèn SQL vào tham số, dùng lại mã xác thực, đoán mật khẩu liên tục, dùng token mẫu, gửi yêu cầu thiếu header chống giả mạo.
- 47 bài kiểm thử tự động.

## 2. Kết quả chức năng

| Phần | Kết quả |
| --- | --- |
| 47 bài kiểm thử tự động | Đạt hết |
| 6 migration trên cơ sở dữ liệu trống | Đạt |
| Worker chạy 75 giây: lập lịch, tạo 45 dự báo, chuyển sự kiện | Không lỗi |
| 32 điểm API (công khai, dự báo, xác suất, AI, quản trị) | Đúng mã trả về cả 32 |
| 8 trang và màn hình (trang chính, trực tiếp, dự báo, quản trị, các mục miền Bắc, Nam, Trung) | Không lỗi JavaScript |
| Các trang khi bật CSP mới | Không bị chặn nhầm |
| Kiểm thử lùi 3 loại xổ số | Chạy đúng, kết quả nhất quán với trang dự báo |

## 3. Những chỗ khác biệt giữa các phần

| Khác biệt | Mức độ | Xử lý |
| --- | --- | --- |
| Trang chính `index.html` dùng dữ liệu nhúng sẵn đến 29/10/2026, không lấy từ API | Lớn | Đã thêm dòng thông báo và liên kết sang các trang dùng dữ liệu thật. **Cần làm tiếp:** nối trang chính vào API |
| Trang chính có 4 mô hình dự báo, backend có 5 (thêm học máy) | Vừa | Ghi nhận; sẽ thống nhất khi nối trang chính vào API |
| Hệ số làm trơn mô hình "Phân phối lịch sử" cho miền Nam: trang chính 30, backend 10 | Nhỏ | **Đã sửa**: backend dùng 30 cho mọi miền |
| Mục Quản trị, sổ dự đoán dùng chung, đọc ảnh vé trong trang chính chỉ chạy khi mở trên Claude | Vừa | Khi tự chạy trên máy chủ, các mục này tự ẩn hoặc lưu trên trình duyệt. Quản trị thật dùng `admin.html` |
| Đấu trường chiến lược Power 6/55 (số nóng, số gan...) chỉ có ở trang chính | Nhỏ | Ghi nhận |
| Mã kỳ Power 6/55: thiết kế ghi `power655-01417`, mã nguồn dùng `vl-power655-2026-10-29` | Nhỏ | Đã ghi trong `docs/README.md`; số kỳ Vietlott lưu ở cột `draw_seq` |
| Miền Trung | Nhỏ | **Đã bổ sung** (02/11/2026): 14 đài, lịch quay 17:15, bộ cào xoso.com.vn, trang chính có dữ liệu từ 08/2025 |

## 4. Bảo mật

### 4.1. Lỗi đã phát hiện và đã sửa

| # | Vấn đề | Mức độ | Đã sửa |
| --- | --- | --- | --- |
| 1 | Tệp `.env.example` có sẵn token quản trị mẫu đủ dài để dùng được. Ai cài theo cách thủ công mà quên đổi sẽ để lộ quyền admin cho bất kỳ ai đọc mã nguồn | **Nghiêm trọng** | Để trống mặc định; hệ thống bỏ qua mọi token chứa giá trị mẫu hoặc ngắn hơn 24 ký tự |
| 2 | Khi chạy sau Cloudflare Tunnel, cookie đăng nhập không có cờ `Secure`, vì Caddy nhận kết nối HTTP từ tunnel | Cao | Ở `APP_ENV=prod`, cookie luôn có `Secure`; có thể ép bằng `COOKIE_SECURE` |
| 3 | Kẻ xấu có thể đoán mật khẩu từ một máy để cố tình khóa tài khoản admin | Vừa | Giới hạn 10 lần thử đăng nhập mỗi địa chỉ IP trong 5 phút, cộng khóa tài khoản sau 5 lần sai |
| 4 | Mã xác thực hai lớp có thể dùng lại trong 30–90 giây nếu bị nhìn trộm | Vừa | Mỗi mã chỉ dùng được một lần (migration 006) |
| 5 | Trang tường thuật trực tiếp đưa tên đài, tên giải vào trang mà không thoát ký tự | Vừa | Đã thoát ký tự; thử chèn mã độc vào tên đài không chạy được |
| 6 | Trang có thể bị nhúng vào trang khác để lừa bấm nút (clickjacking), thiếu CSP | Vừa | Thêm `X-Frame-Options`, `Content-Security-Policy`, `Permissions-Policy`, HSTS trong `Caddyfile` |
| 7 | Trang quản trị và API đăng nhập có thể bị trình duyệt hoặc CDN lưu đệm | Thấp | Thêm `Cache-Control: no-store` cho các đường dẫn này |
| 8 | Một người có thể gửi liên tục yêu cầu biểu đồ độ tin cậy (tính toán nặng) để làm chậm máy chủ | Thấp | Chỉ cho chạy một phép tính nặng mỗi lúc, kết quả lưu đệm |
| 9 | Ở chế độ phát triển, API cho phép trang khác gửi yêu cầu POST | Thấp | Chỉ cho phép GET |
| 10 | Một nút trong trang quản trị dùng mã JavaScript nội tuyến chứa dữ liệu | Thấp | Đổi sang gắn sự kiện an toàn |

### 4.2. Đã kiểm tra và đạt

- **Mật khẩu:** băm scrypt có muối riêng; so sánh an toàn về thời gian, kể cả khi tên đăng nhập không tồn tại; tối thiểu 10 ký tự, có chữ hoa, chữ thường, chữ số.
- **Phiên đăng nhập:**
  - Cookie `HttpOnly`, `SameSite=Strict`, hết hạn sau 12 giờ.
  - Cơ sở dữ liệu chỉ lưu mã băm của phiên.
  - Đăng xuất hoặc đổi mật khẩu là thu hồi phiên ngay.
- **Chống giả mạo yêu cầu (CSRF):** mọi yêu cầu thay đổi dữ liệu phải kèm header `X-LV-CSRF`; thiếu header bị từ chối.
- **Phân quyền:** viewer, editor, admin được kiểm tra ở từng API. Admin không tự khóa hay tự hạ quyền của mình được.
- **SQL injection:** mọi truy vấn dùng tham số; thử chèn vào tham số và đường dẫn đều không có tác dụng.
- **XSS:** các trang dùng dữ liệu từ API đều thoát ký tự. Câu trả lời của AI được hiển thị dạng chữ thuần.
- **Dữ liệu không sửa được:**
  - Nhật ký và dự báo đã công bố có trigger chặn sửa, xóa ngay ở cơ sở dữ liệu.
  - Kết quả bị sửa luôn tạo phiên bản mới.
- **Khóa bí mật:**
  - Khóa Claude API và mật khẩu chỉ nằm trong `.env` trên máy chủ, `.env` nằm trong `.gitignore`.
  - Trình duyệt không bao giờ thấy khóa.
- **Mạng:**
  - PostgreSQL và Redis không mở cổng ra ngoài.
  - Trên VPS chỉ mở cổng SSH, đăng nhập SSH bằng khóa, có fail2ban.
- **Container** chạy bằng người dùng không phải root.
- **Bộ cào dữ liệu:** tôn trọng robots.txt, giới hạn tần suất, không vượt chống bot. Nguồn chưa duyệt pháp lý không bật được.
- **Đầu ra AI:** bộ số được kiểm tra lại theo luật trò chơi, và mỗi IP bị giới hạn số lượt để kiểm soát chi phí.

### 4.3. Khuyến nghị còn lại (chưa làm)

| Ưu tiên | Việc nên làm | Lý do |
| --- | --- | --- |
| Cao | Bật xác thực hai lớp cho mọi tài khoản admin và editor | Lệnh `doctor` sẽ nhắc tài khoản nào chưa bật |
| Cao | Đặt Cloudflare Access trước `/admin.html` và `/v1/admin/*` | Thêm một lớp đăng nhập trước khi tới được trang quản trị |
| Vừa | Tạo tài khoản PostgreSQL riêng cho ứng dụng, không phải chủ sở hữu bảng | Hiện ứng dụng dùng tài khoản chủ sở hữu, về lý thuyết có thể gỡ trigger chống sửa nhật ký |
| Vừa | Mã hóa bản sao lưu trước khi đẩy lên object storage (`rclone crypt`) | Bản sao lưu chứa toàn bộ dữ liệu, kể cả mã băm mật khẩu |
| Vừa | Cố định phiên bản thư viện Python (tệp khóa) và ảnh `cloudflared` | Tránh tự động nhận bản cập nhật chưa kiểm tra |
| Thấp | Mã hóa khóa bí mật TOTP trong cơ sở dữ liệu | Hiện lưu dạng thường; chỉ người có quyền vào cơ sở dữ liệu đọc được |
| Thấp | Cấu hình nguồn `http_json` cho phép admin trỏ tới địa chỉ nội bộ (SSRF) | Chỉ admin làm được; cần lưu ý khi cấp quyền admin |
| Thấp | Giới hạn lượt gọi AI hiện tính riêng cho từng tiến trình API | Với 2 tiến trình, giới hạn thực tế gấp đôi; Cloudflare có thể giới hạn thêm |

## 5. Chưa kiểm tra được trong môi trường này

- **Dựng Docker và chạy `start.ps1` trên Windows:** môi trường kiểm tra không có Docker.
- **Bộ cào trên trang thật:** không truy cập được các trang nguồn; hãy dùng lệnh `probe-source`.
- **Cloudflare Tunnel, HTTPS thật và các tiêu đề bảo mật qua Caddy:** đã kiểm tra CSP bằng máy chủ thử nghiệm, chưa qua Caddy thật.
- **Gọi Claude API thật:** đã thử với máy chủ giả lập.
- **Chịu tải 5.000 kết nối realtime.**

Sau khi cài trên máy bạn hoặc VPS, chạy lệnh sau để tự kiểm tra cấu hình, dữ liệu và bảo mật:

```powershell
docker compose exec api python -m luckyvision.cli doctor
```

## 6. Bổ sung 03/11/2026: thêm trò chơi

- Vietlott Lotto 5/35, Keno, Max 3D, Max 3D Pro, Bingo18: luật kiểm tra riêng, mã kỳ có số kỳ cho trò quay nhiều lần mỗi ngày,
  bộ đọc trang vietlott.vn theo dự án mã nguồn mở. Đã kiểm thử bộ đọc với HTML mẫu; **chưa chạy với trang thật** (dùng `probe-feed`).
- Xổ số điện toán 1*2*3, Thần Tài 4, 6x36: luật và trang hiển thị; **chưa có nguồn tự động**, nhập tay trong trang quản trị.
- Cơ sở dữ liệu: bỏ ràng buộc "mỗi đài một kỳ mỗi ngày" cho Lotto 5/35, Keno, Bingo18; giữ nguyên cho các loại khác.
