# Hướng dẫn chạy LuckyVision

Tài liệu này hướng dẫn từng bước: chạy thử trên máy Windows, bật tự động lấy kết quả, xử lý lỗi thường gặp và đưa lên VPS.

---

## Tóm tắt: 5 bước từ máy tính đến trang web chạy thật

| Bước | Làm gì | Mục |
| --- | --- | --- |
| 1 | Cài Docker Desktop, giải nén `Luckey.zip` vào `C:\Luckey`, chạy `.\start.ps1` | 1–3 |
| 2 | Mở http://localhost/admin.html, đăng nhập `admin` bằng mật khẩu tạm, đổi mật khẩu, bật xác thực hai lớp | 7 |
| 3 | Chạy thử và bật nguồn dữ liệu, sửa `.env` (`APP_ENV=prod`...), **tải bù lịch sử** bằng `backfill` và `feed` | 6, 7b |
| 4 | Tùy chọn: AI (`AI_API_KEY`), Telegram, `SUPPORT_CONTACT` cho người quên mật khẩu | 7b, 7c, 8 |
| 5 | Thuê VPS, đưa lên chạy 24/7, gắn tên miền, khai báo Google Search Console | 10, 7c |

Sau mỗi bước, chạy `docker compose exec api python -m luckyvision.cli doctor` để tự kiểm tra.

**Sau bước 1, trang mới có dữ liệu mẫu 2 ngày** (1 kỳ Power 6/55, miền Bắc 29/10, TP. Hồ Chí Minh 26/10). Nhiều trang sẽ hiện
"Chưa có kết quả" hoặc "Chưa đủ dữ liệu" (ví dụ Đấu trường cần ít nhất 110 kỳ Power). Đó là bình thường;
sau bước 3 mọi trang sẽ đầy đủ.

**Các địa chỉ chính:**

| Địa chỉ | Dành cho |
| --- | --- |
| `/` | Trang kết quả công khai (tối ưu Google), tìm kiếm, so sánh số, lịch quay, sổ kết quả, thống kê |
| `/cong-cu/` | Công cụ: Power 6/55, ba miền, dò vé, máy thời gian, tạo bộ số, sổ dự đoán, đấu trường |
| `/live.html` | Tường thuật trực tiếp giờ quay |
| `/du-doan.html` | Dự báo, xác suất từng số, trợ lý AI |
| `/dang-ky`, `/tai-khoan` | Thành viên: tỉnh và bộ số yêu thích, tự dò |
| `/lien-he` | Form liên hệ |
| `/admin.html` | Quản trị: hàng chờ, truy cập, liên hệ, thành viên, kỳ quay, nhập kết quả, nguồn, tài khoản, nhật ký |

---

## 1. Chuẩn bị

| Cần có | Ghi chú |
| --- | --- |
| Windows 10/11 (64-bit) | Máy có ít nhất 8 GB RAM |
| Docker Desktop | Tải tại https://www.docker.com/products/docker-desktop/ . Khi cài, chọn **Use WSL 2** |
| Tệp `Luckey.zip` | Mã nguồn dự án |

Sau khi cài Docker Desktop, mở nó lên và chờ đến khi biểu tượng cá voi ở góc màn hình báo **Engine running**.

Kiểm tra trong PowerShell:

```powershell
docker --version
docker compose version
```

Cả hai lệnh đều phải in ra số phiên bản. `docker compose` cần từ 2.24 trở lên.

---

## 2. Giải nén

Giải nén `Luckey.zip` vào ổ `C:\` để có thư mục:

```
C:\Luckey
├─ backend\
├─ web\
├─ deploy\
├─ docs\
├─ docker-compose.yml
├─ start.ps1
└─ ...
```

> Lưu ý: giải nén sao cho đường dẫn là `C:\Luckey\docker-compose.yml`, không phải `C:\Luckey\Luckey\docker-compose.yml`.

---

## 3. Chạy lần đầu (cách nhanh)

Mở **PowerShell** và chạy:

```powershell
cd C:\Luckey
Set-ExecutionPolicy -Scope Process Bypass
.\start.ps1
```

Script sẽ tự làm các việc sau:

1. Tạo tệp `.env` từ `.env.example`, với mật khẩu cơ sở dữ liệu ngẫu nhiên.
2. Dựng và chạy 5 container: cơ sở dữ liệu (`db`), `redis`, `api`, `worker`, và `caddy` (máy chủ web).
3. Chờ API sẵn sàng rồi nạp dữ liệu mẫu cho ngày 26/10 và 29/10/2026.
4. Tạo tài khoản quản trị `admin` với **mật khẩu tạm**, in ra bằng chữ màu vàng. Hãy chép lại; lần đăng nhập đầu sẽ bắt đổi mật khẩu.

Lần đầu mất khoảng 3–5 phút vì phải tải các image Docker. Những lần sau chỉ vài giây.

### Kiểm tra đã chạy được

Mở trình duyệt:

| Địa chỉ | Thấy gì |
| --- | --- |
| http://localhost | Trang chủ công khai: kết quả ba miền và Vietlott (máy chủ tạo sẵn, tối ưu tìm kiếm Google) |
| http://localhost/xsmb, /xsmn-26-10-2026, /xs-tp-hcm | Trang kết quả theo miền, theo ngày, theo đài |
| http://localhost/cong-cu/ | Công cụ tương tác: dò vé, máy thời gian, tạo bộ số, sổ dự đoán, đấu trường, thống kê và dự báo ba miền. **Lấy dữ liệu thật từ máy chủ**, tự cập nhật mỗi 5 phút |
| http://localhost/live.html | Trang tường thuật trực tiếp, nối với API thật |
| http://localhost/du-doan.html | Dự báo kỳ tới, hiệu quả các mô hình, trợ lý AI |
| http://localhost/admin.html | Trang quản trị (đăng nhập bằng tài khoản `admin`) |
| http://localhost/v1/docs | Tài liệu API, bấm thử được từng lệnh |
| http://localhost/healthz | `{"ok": true, ...}` nghĩa là API và cơ sở dữ liệu đều chạy |
| http://localhost/v1/draws/latest?region=mb | Kết quả miền Bắc mới nhất (dữ liệu mẫu) |

Xem trạng thái các container:

```powershell
docker compose ps
```

Cả 5 dịch vụ phải ở trạng thái `running` (riêng `api` có thêm `healthy`).

---

## 4. Chạy thủ công (nếu không dùng start.ps1)

```powershell
cd C:\Luckey
copy .env.example .env
notepad .env
```

Trong `.env`, sửa ít nhất dòng `POSTGRES_PASSWORD=...`. Sau đó:

```powershell
docker compose up -d --build
docker compose exec api python -m luckyvision.cli collect --date 2026-10-29
docker compose exec api python -m luckyvision.cli create-admin --username admin --name "Quản trị"
```

Lệnh cuối in ra mật khẩu tạm của tài khoản `admin`.

---

## 5. Thử tường thuật trực tiếp

1. Mở trình duyệt tới: http://localhost/live.html?draw=mn-tp-hcm-2026-10-26
2. Trong PowerShell, giả lập một buổi quay từ dữ liệu mẫu:

```powershell
docker compose exec api python -m luckyvision.cli plan --date 2026-10-26
docker compose exec api python -m luckyvision.cli simulate-live --draw mn-tp-hcm-2026-10-26
```

Trên trình duyệt, từng số sẽ hiện ra lần lượt, kèm nhãn "Đang quay, chưa xác minh". Khi đủ giải và hai nguồn khớp nhau, trang chuyển sang "Đã xác minh và công bố".

> Nếu kỳ này đã được công bố từ trước (ví dụ do `start.ps1` đã nạp), bảng sẽ hiện đủ số ngay. Muốn xem lại từ đầu, chạy lệnh xóa dữ liệu ở mục 9 rồi thử lại.

---

## 6. Bật tự động lấy kết quả mỗi ngày

Mặc định hệ thống chỉ đọc **dữ liệu mẫu**. Để lấy kết quả thật, bật các bộ cào dữ liệu.

### Bước 6.1: Xem danh sách nguồn

```powershell
docker compose exec api python -m luckyvision.cli sources
```

| Mã nguồn | Trang | Lấy gì |
| --- | --- | --- |
| `vietlott-web` | vietlott.vn | Power 6/55 |
| `minhngoc-web` | minhngoc.net | Miền Nam (21 đài) |
| `xoso-com-vn` | xoso.com.vn | Miền Bắc, Miền Nam, Miền Trung (14 đài) |
| `vietlott-mega` | vietlott.vn | Mega 6/45 |
| `vietlott-lotto535`, `vietlott-keno`, `vietlott-max3d`, `vietlott-max3dpro`, `vietlott-bingo18` | vietlott.vn | Lotto 5/35, Keno, Max 3D, Max 3D Pro, Bingo18 (xem mục 6.5) |

Cả ba mặc định **tắt**. Trước khi bật, hãy đọc điều khoản sử dụng của từng trang.

### Bước 6.2: Chạy thử từng nguồn

Lệnh này chỉ tải và in ra kết quả đọc được, **không lưu gì**:

```powershell
docker compose exec api python -m luckyvision.cli probe-source vietlott-web --draw vl-power655-2026-10-29
docker compose exec api python -m luckyvision.cli probe-source minhngoc-web --draw mn-tp-hcm-2026-10-26
docker compose exec api python -m luckyvision.cli probe-source xoso-com-vn  --draw mb-mb-2026-10-29
docker compose exec api python -m luckyvision.cli probe-source xoso-com-vn  --draw mt-da-nang-2026-10-28
```

Thay ngày trong mã kỳ bằng một ngày gần đây có quay thưởng. Mã kỳ có dạng `<miền>-<đài>-<YYYY-MM-DD>`.

Kết quả **tốt** trông như sau:

```
URL:        https://www.minhngoc.net/ket-qua-xo-so/mien-nam/tp-hcm/26-10-2026.html
HTTP:       200
  Giải tám      74
  Giải bảy      010
  ...
  Đặc biệt      472899
Đủ giải:    có
Kiểm tra:   hợp lệ
```

Nếu thấy `robots.txt ... không cho phép`, `Trang chặn truy cập tự động` hoặc `Không tìm thấy kết quả`, **đừng bật nguồn đó**. Hãy gửi nội dung lỗi để chỉnh bộ cào.

### Bước 6.3: Bật nguồn đã chạy thử ổn

```powershell
docker compose exec api python -m luckyvision.cli source-enable vietlott-web
docker compose exec api python -m luckyvision.cli source-enable vietlott-mega
docker compose exec api python -m luckyvision.cli source-enable minhngoc-web
docker compose exec api python -m luckyvision.cli source-enable xoso-com-vn
```

Tắt lại khi cần: `source-disable <mã nguồn>`.

### Bước 6.4: Sửa `.env`

```
APP_ENV=prod
MIN_SOURCES_BY_REGION=vl:1,mega:1,mn:1,mb:1,mt:1
```

- `APP_ENV=prod` tắt các nguồn dữ liệu mẫu.
- `MIN_SOURCES_BY_REGION` là số nguồn cần khớp nhau để tự công bố:
  - `vl:1,mn:1,mb:1,mt:1`: lấy về là tự công bố ngay.
  - `vl:1,mb:1,mt:1,mn:2`: miền Nam có hai nguồn (minhngoc.net và xoso.com.vn) nên có thể đòi hai nguồn khớp nhau mới công bố.
  - `vl:1` (mặc định): chỉ Power 6/55 tự công bố. Miền Bắc và miền Nam nằm trong hàng chờ để bạn duyệt (mục 7).

Áp dụng thay đổi:

```powershell
docker compose up -d
```

### 6.5. Lotto 5/35, Keno, Max 3D, Max 3D Pro, Bingo18

Các trò chơi này được lấy **theo dòng kết quả mới nhất** trên vietlott.vn, không cần lập lịch trước.
Worker tự đọc lại trang kết quả: Keno và Bingo18 mỗi 5 phút, Lotto 5/35 mỗi 15 phút, Max 3D mỗi 30 phút
(từ 6:00 đến 23:30). Kết quả từ trang chính thức được tự công bố.

Chạy thử trước khi bật (chỉ đọc, không lưu):

```powershell
docker compose exec api python -m luckyvision.cli probe-feed lotto535
docker compose exec api python -m luckyvision.cli probe-feed keno
docker compose exec api python -m luckyvision.cli probe-feed max3d
docker compose exec api python -m luckyvision.cli probe-feed max3dpro
docker compose exec api python -m luckyvision.cli probe-feed bingo18
```

Kết quả đúng in ra vài kỳ gần nhất. Bật nguồn nào chạy ổn:

```powershell
docker compose exec api python -m luckyvision.cli source-enable vietlott-keno
```

Tải bù lịch sử (mỗi trang khoảng 5–10 kỳ; Keno có hàng trăm kỳ mỗi ngày nên tải bù chậm):

```powershell
docker compose exec api python -m luckyvision.cli feed --game lotto535 --pages 100
docker compose exec api python -m luckyvision.cli feed --game max3d --pages 200
```

Lưu ý: yêu cầu gửi tới Vietlott dùng một "khóa" lấy từ dự án mã nguồn mở; nếu `probe-feed` báo lỗi hoặc đọc được 0 kỳ,
có thể Vietlott đã đổi khóa hoặc giao diện. Khi đó đừng bật nguồn và gửi nội dung lỗi để chỉnh lại.

### 6.6. Xổ số điện toán miền Bắc (1*2*3, Thần Tài 4, 6x36)

Chưa có nguồn tự động được kiểm chứng, nên kết quả **nhập tay** trong trang quản trị:
vào **Nhập kết quả**, chọn loại (Điện toán 1*2*3, Thần Tài 4, Điện toán 6x36), ngày quay, nhập số rồi duyệt.
Hệ thống kiểm tra đúng luật (ví dụ 6x36 chỉ nhận số 01–36, không trùng; Thần Tài 4 đúng 4 chữ số).

Nếu bạn mua được API dữ liệu của nhà cung cấp, khai báo nguồn `http_json` (README mục 5) với `regions` là
`{dt123}`, `{tt4}` hoặc `{dt6x36}` để lấy tự động.

### Lịch tự động của worker (giờ Việt Nam)

| Giờ | Việc |
| --- | --- |
| 15:55 | Lập danh sách kỳ quay hôm nay và ngày mai |
| 16:10–16:50 | Theo dõi trực tiếp miền Nam |
| 17:10–17:50 | Theo dõi trực tiếp miền Trung |
| 18:00–19:00 | Theo dõi trực tiếp Power 6/55 (thứ Ba, Năm, Bảy) |
| 18:10–18:50 | Theo dõi trực tiếp miền Bắc |
| 17:00 đến 23:00 | Các lượt đối soát lại sau giờ quay |
| 03:00 | Quét bù các kỳ còn thiếu trong 30 ngày |
| Mỗi phút | Cảnh báo nếu kỳ quay quá giờ mà chưa có kết quả |

Theo dõi worker đang làm gì:

```powershell
docker compose logs -f worker
```

> Worker chỉ chạy khi máy bật. Muốn cập nhật đều mỗi ngày, hãy đưa lên VPS (mục 10).

---

## 7. Quản trị: tài khoản, duyệt và sửa kết quả

Mở http://localhost/admin.html và đăng nhập bằng tài khoản `admin` cùng mật khẩu tạm. Lần đầu, hệ thống bắt đổi mật khẩu (ít nhất 10 ký tự, có chữ hoa, chữ thường và chữ số).

### Bật xác thực hai lớp (nên làm ngay)

1. Cài **Google Authenticator** hoặc **Microsoft Authenticator** trên điện thoại.
2. Trong trang quản trị, vào **Tài khoản của tôi**, bấm **Thiết lập**.
3. Quét mã QR bằng ứng dụng, nhập mã 6 số đang hiện, bấm **Bật**.

Từ đó mỗi lần đăng nhập cần thêm mã 6 số. Đăng nhập sai 5 lần liên tiếp, tài khoản bị khóa 15 phút.

### Các mục trong trang quản trị

| Mục | Dùng để |
| --- | --- |
| Hàng chờ | Kỳ quay cần xử lý: nguồn lệch nhau, đủ giải chờ duyệt, quá giờ chưa có kết quả |
| Kỳ quay | So sánh kết quả của từng nguồn (số khác nhau tô đỏ), duyệt và công bố, tải lại từ nguồn |
| Nhập kết quả | Nhập tay hoặc sửa kết quả theo đúng cơ cấu giải. Bản nhập luôn chờ xác minh |
| Nguồn dữ liệu | Chạy thử, duyệt và bật/tắt từng nguồn |
| Tài khoản | Tạo tài khoản, đổi vai trò, khóa, đặt lại mật khẩu, tắt xác thực hai lớp (chỉ vai trò admin) |
| Nhật ký | Mọi thao tác: ai, lúc nào, làm gì. Không sửa hay xóa được |

Vai trò: **viewer** chỉ xem; **editor** nhập kết quả và đề xuất sửa; **admin** duyệt, công bố, cấu hình nguồn và quản lý tài khoản.

Tạo thêm người dùng: vào **Tài khoản**, nhập tên đăng nhập, tên hiển thị, vai trò rồi bấm **Tạo**. Trang hiện mật khẩu tạm **một lần duy nhất**; hãy gửi riêng cho người đó.

**Quên mật khẩu hoặc mất điện thoại có ứng dụng xác thực?** Chạy lệnh sau trên máy chủ: lệnh tạo mật khẩu tạm mới và tắt xác thực hai lớp của tài khoản đó.

```powershell
docker compose exec api python -m luckyvision.cli create-admin --username admin --name "Quản trị"
```

> `ADMIN_TOKENS` trong `.env` chỉ dành cho script tự động gọi API; người dùng nên đăng nhập bằng tài khoản.

---

## 7b. Dự báo và AI

### Dự báo tự động

Worker tự tạo dự báo cho các kỳ quay hôm nay và ngày mai (mỗi 30 phút kiểm tra một lần), và tự chấm điểm sau khi có kết quả. Dự báo đã tạo **không sửa hay xóa được**.

| Mô hình | Cách làm |
| --- | --- |
| Tần suất gần đây | Đếm số lần về trong các kỳ gần nhất |
| Cửa sổ trượt có trọng số | Kỳ càng xa càng ít trọng số |
| Phân phối lịch sử | Tỉ lệ về trên toàn bộ lịch sử, có ước lượng xác suất |
| Học máy: hồi quy logistic | Học từ tần suất ngắn hạn, dài hạn, số kỳ chưa về, tỉ lệ lịch sử |
| Ngẫu nhiên | Mốc so sánh |

Xem tại http://localhost/du-doan.html. Mô hình cần đủ lịch sử của đài (học máy cần khoảng 40 kỳ). Để có lịch sử, tải bù kết quả các ngày đã qua từ các nguồn đang bật:

```powershell
docker compose exec api python -m luckyvision.cli backfill --region mb --days 120
docker compose exec api python -m luckyvision.cli backfill --region vl --days 365
docker compose exec api python -m luckyvision.cli backfill --region mn --days 365
```

Kiểm thử lùi các mô hình trên dữ liệu đã có:

```powershell
docker compose exec api python -m luckyvision.cli backtest --region mb --last 365
docker compose exec api python -m luckyvision.cli backtest --region mn --province tp-hcm --last 60 --k 5
```

> Nói thật: trên dữ liệu thật, không mô hình nào (kể cả học máy) đoán tốt hơn chọn ngẫu nhiên một cách có ý nghĩa thống kê. Trang dự báo và lệnh `backtest` luôn hiện rõ điều này.

### Xác suất từng số

Trang http://localhost/du-doan.html có phần **Xác suất từng số**, giúp người dùng tự đánh giá thay vì chỉ nhìn một con số phần trăm:

- **Xác suất lý thuyết** của mỗi số khi kết quả hoàn toàn ngẫu nhiên: lô miền Bắc khoảng 23,8%, lô miền Nam khoảng 16,5%, mỗi số Power 6/55 là 10,9%.
- **Bản đồ nhiệt**: tần suất thực tế của từng số trong khoảng thời gian chọn. Chỉ tô màu những số lệch khỏi lý thuyết **vượt quá sai số ngẫu nhiên** (khoảng tin cậy 95%). Trang cũng ghi rõ: dù hoàn toàn ngẫu nhiên, vẫn có khoảng 5% số bị tô màu.
- **Bấm vào một số** để xem chi tiết: số lần về, khoảng sai số, ước lượng của mô hình cho kỳ tới.
- **Bảng đầy đủ**: lý thuyết, lịch sử, khoảng 95%, ước lượng của mô hình phân phối và học máy; sắp xếp theo số, theo độ lệch, hoặc theo mô hình.
- **Biểu đồ độ tin cậy**: khi mô hình nói X%, thực tế số đó về bao nhiêu %. Khi đã có từ 20 kỳ dự báo được công bố và chấm điểm, biểu đồ dùng số liệu đó; trước đó dùng kiểm thử lùi 120 kỳ gần nhất. Lần mở đầu tiên có thể mất 10–15 giây để tính, sau đó được lưu đệm.

API tương ứng: `GET /v1/probabilities?region=mb&days=365` và `GET /v1/forecasts/calibration?region=mb&model=logreg`.

### Trợ lý AI và AI chọn số (tùy chọn)

Dùng được **Claude hoặc bất kỳ dịch vụ nào theo chuẩn API của OpenAI** (OpenAI, Google Gemini, DeepSeek, Groq, OpenRouter,
hoặc mô hình chạy ngay trên máy bằng Ollama). Điền vào `.env` theo một trong các mẫu:

| Dịch vụ | Cấu hình |
| --- | --- |
| Claude | `AI_PROVIDER=anthropic`, `AI_API_KEY=sk-ant-...` |
| OpenAI | `AI_PROVIDER=openai`, `AI_API_KEY=sk-...`, `AI_MODEL=gpt-4o-mini` |
| Google Gemini | `AI_PROVIDER=openai`, `AI_API_KEY=...`, `AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai`, `AI_MODEL=gemini-2.0-flash` |
| DeepSeek | `AI_PROVIDER=openai`, `AI_API_KEY=...`, `AI_BASE_URL=https://api.deepseek.com/v1`, `AI_MODEL=deepseek-chat` |
| Ollama trên máy | `AI_PROVIDER=openai`, `AI_BASE_URL=http://host.docker.internal:11434/v1`, `AI_MODEL=qwen2.5` (không cần khóa) |

Tên cũ `ANTHROPIC_API_KEY` vẫn dùng được. Sau khi sửa, chạy `docker compose up -d`, rồi mở http://localhost/v1/ai/status:
thấy `"enabled": true` và tên dịch vụ là xong. Tên mô hình cụ thể của từng dịch vụ có thể thay đổi; xem trang tài liệu của dịch vụ đó.

Trên trang http://localhost/du-doan.html sẽ có thêm:

- **Trợ lý AI:** trả lời câu hỏi bằng số liệu thật của hệ thống, ví dụ "lô nào lâu chưa về nhất?".
- **AI chọn số cho vui:** nhập mong muốn (ngày sinh, số yêu thích...), AI tạo bộ số kèm giải thích. Mọi bộ số đều được kiểm tra lại theo luật trò chơi.

Mỗi địa chỉ IP chỉ gọi được `AI_REQUESTS_PER_MINUTE` lần mỗi phút để giới hạn chi phí.

### Tìm kiếm thông minh, so sánh số, lịch quay, tài khoản người dùng

- **Tìm kiếm** (ô trên đầu mọi trang): gõ tự nhiên, ví dụ `xsmn 26/10`, `xổ số đà nẵng thứ 7`, `xsmb hôm qua`, `lô 27 tp hcm`,
  `27 72 xsmb`, `power kỳ 1417`, `max 3d pro`, `vé 472899 hcm` (dò vé trong 7 ngày gần nhất), `lô gan miền trung`, `lịch quay`.
- **So sánh các con số** (`/so-sanh`): đặt 2–4 số cạnh nhau theo miền, theo đài hoặc theo trò Vietlott: số kỳ có về, tỉ lệ so với
  lý thuyết, lần về gần nhất, số kỳ chưa về, lâu nhất chưa về, khoảng cách trung bình, số hay về cùng, dải 40 kỳ gần nhất.
- **Lịch quay** (`/lich-quay-xo-so`): bảng 7 ngày theo miền, hôm nay được tô màu, lịch Vietlott, câu hỏi thường gặp (có dữ liệu cấu trúc FAQ cho Google).
- **Tài khoản người dùng** (`/dang-ky`, `/dang-nhap`, `/tai-khoan`): miễn phí, đăng ký bằng email và mật khẩu.
  - Lưu **tỉnh/đài yêu thích** (nút "☆ Lưu đài này" trên trang đài, trang Vietlott) và xem kết quả mới nhất của chúng ở một chỗ.
  - Lưu **bộ số yêu thích**: số lô (theo miền hoặc đài), số vé ba miền, bộ số Power/Mega/Lotto. Mỗi lần mở "Trang của tôi", hệ thống tự dò với kỳ mới nhất và tô vàng số trúng.
  - Đổi mật khẩu, đăng xuất, xóa tài khoản (xóa luôn dữ liệu đã lưu).
  - Bảo mật: mật khẩu băm scrypt, cookie httpOnly, chống giả mạo yêu cầu, giới hạn số lần đăng ký và đăng nhập theo IP, khóa tạm khi sai nhiều lần.
  - **Quên mật khẩu:** trang đăng nhập hướng dẫn liên hệ quản trị theo `SUPPORT_CONTACT` trong `.env`. Quản trị vào
    **Quản trị, Thành viên**, tìm theo email, bấm **Đặt lại mật khẩu** và gửi mật khẩu tạm cho thành viên (chỉ hiện một lần).
    Thành viên đăng nhập bằng mật khẩu tạm sẽ được nhắc đặt mật khẩu mới; dữ liệu đã lưu giữ nguyên.
    Hãy xác nhận đúng chủ tài khoản trước khi cấp mật khẩu (ví dụ yêu cầu nhắn từ chính email đã đăng ký).
  - Mục **Thành viên** còn cho khóa, mở khóa, xóa tài khoản; mọi thao tác được ghi vào Nhật ký.
- **Form liên hệ** (`/lien-he`, có liên kết ở chân mọi trang và ở trang đăng nhập): chủ đề Quên mật khẩu, Báo sai kết quả, Góp ý,
  Hợp tác, Khác. Tin gửi về mục **Quản trị, Liên hệ** (menu có huy hiệu số tin mới) và báo qua Telegram nếu đã cài `TELEGRAM_CHAT_ID`.
  - Mỗi tin: trả lời qua email (bấm vào địa chỉ), ghi chú nội bộ, đánh dấu Đang xử lý, Đã xong hoặc Thư rác.
  - Tin "Quên mật khẩu" có nút **Mở Thành viên** để cấp mật khẩu tạm ngay.
  - Chống thư rác: ô bẫy ẩn, phải mở form ít nhất 3 giây mới gửi được, mỗi địa chỉ tối đa 5 tin mỗi giờ, giới hạn số đường dẫn trong tin.

### Trang Công cụ dùng dữ liệu thật

Trang `/cong-cu/` không còn nhúng dữ liệu cũ: khi mở, trang tải toàn bộ kết quả Power 6/55 và 3 năm gần nhất của ba miền
từ máy chủ (`/v1/export/tools`, khoảng 130 KB khi nén, có lưu đệm), rồi tự tải lại mỗi 5 phút khi trang đang mở.
Kết quả vừa được công bố hiện ngay ở lần tải kế tiếp.

**Sổ dự đoán** gắn với tài khoản thành viên: đăng nhập rồi khóa dự đoán Power hoặc số lô, sổ được lưu trên máy chủ và
tên hiển thị xuất hiện trên **bảng xếp hạng chung**. Máy chủ chỉ cho thêm dự đoán của kỳ chưa quay; dự đoán của kỳ đã quay
bị khóa, không sửa hay xóa được. Chưa đăng nhập thì sổ lưu trên trình duyệt như trước.

Lưu ý: trang Công cụ cần dữ liệu lịch sử để thống kê và dự báo có ý nghĩa; hãy chạy `backfill` sau khi bật nguồn.

### Thống kê truy cập (trang Quản trị, mục "Truy cập")

- Lượt xem và số khách mỗi ngày (biểu đồ; bấm một cột để xem riêng ngày đó), so với hôm trước.
- Trang xem nhiều nhất, theo nhóm trang (ví dụ mọi trang "XSMN theo ngày" gộp lại), nguồn khách (Google, Facebook, Zalo, vào trực tiếp...), thiết bị.
- Chọn hôm nay, 7, 30, 90 ngày hoặc khoảng ngày tùy ý; nút **Tải CSV** để phân tích thêm bằng Excel.

Cách đếm tôn trọng quyền riêng tư: không cookie, không lưu IP; khách được nhận diện trong ngày bằng mã băm với "muối" đổi mỗi ngày
và tự xóa sau 2 ngày, nên không thể truy ngược. Bot và người dùng bật "Không theo dõi" không bị đếm.
Nếu bật Cloudflare lưu đệm trang, lượt xem vẫn được đếm vì việc đếm chạy trên trình duyệt.

---

## 7c. Trang công khai, SEO, ứng dụng điện thoại, kênh Telegram

### Trang công khai cho Google

Trang chủ và các trang kết quả do máy chủ tạo sẵn HTML (không cần JavaScript để đọc), mỗi trang có tiêu đề, mô tả,
đường dẫn chuẩn (canonical), dữ liệu cấu trúc và liên kết qua lại:

| Đường dẫn | Nội dung |
| --- | --- |
| `/` | Kết quả mới nhất ba miền, Power 6/55, Mega 6/45 |
| `/xsmb`, `/xsmn`, `/xsmt` | Kết quả mới nhất từng miền |
| `/xsmb-29-10-2026` | Kết quả một ngày, kèm lô tô, ngày trước và sau, nút in bảng dò vé |
| `/xs-tp-hcm`, `/xs-da-nang`... | Trang từng đài: lịch quay, 10 kỳ gần nhất |
| `/vietlott` | Kết quả mới nhất mọi trò chơi Vietlott |
| `/vietlott-power-655`, `/vietlott-mega-645`, `/vietlott-lotto-535`, `/vietlott-keno`, `/vietlott-max-3d`, `/vietlott-max-3d-pro`, `/vietlott-bingo18` | Kỳ mới nhất và các kỳ gần đây; thêm `-29-10-2026` để xem một ngày (Keno, Bingo18, Lotto 5/35: mọi kỳ trong ngày) |
| `/xs-dien-toan`, `/xs-dien-toan-123`, `/xs-than-tai-4`, `/xs-dien-toan-6x36` | Xổ số điện toán miền Bắc |
| `/so-ket-qua-xsmb-30-ngay` (30, 60, 90) | Sổ kết quả, in được |
| `/thong-ke-xsmb`, `/thong-ke-xs-da-nang` | Lô gan, lô về nhiều, về ít |
| `/sitemap.xml`, `/robots.txt` | Tự cập nhật theo dữ liệu |

Khi đưa lên tên miền thật:

1. Trong `.env`, đặt `SITE_URL=https://ten-mien-cua-ban.vn` (không có dấu `/` cuối), rồi `docker compose up -d`.
2. Vào **Google Search Console**, thêm tên miền, xác minh bằng bản ghi DNS (làm trên Cloudflare).
3. Trong Search Console, mục **Sitemaps**, gửi `https://ten-mien-cua-ban.vn/sitemap.xml`.
4. Bật Cloudflare **Cache Everything** cho các trang ngày cũ nếu muốn nhanh hơn (trang đã gửi sẵn `Cache-Control`).

### Cài như ứng dụng trên điện thoại

Trang có sẵn biểu tượng và chế độ ngoại tuyến. Trên điện thoại:
- **Android (Chrome):** mở trang, bấm menu ⋮, chọn **Cài đặt ứng dụng** hoặc **Thêm vào màn hình chính**.
- **iPhone (Safari):** bấm nút Chia sẻ, chọn **Thêm vào Màn hình chính**.

Khi mất mạng, các trang đã xem vẫn mở được.

### Kênh Telegram nhận kết quả

1. Tạo kênh Telegram công khai (ví dụ `@luckyvision_kq`), thêm bot (mục 8) làm quản trị kênh.
2. Trong `.env`: `TELEGRAM_RESULTS_CHAT_ID=@luckyvision_kq`, rồi `docker compose up -d`.

Mỗi khi một kỳ được công bố lần đầu, kênh nhận tin gồm giải đặc biệt, giải nhất, lô tô và đường dẫn tới trang kết quả.

---

## 8. Cảnh báo qua Telegram (tùy chọn)

1. Trên Telegram, nhắn cho **@BotFather**, gõ `/newbot` để tạo bot và lấy token.
2. Nhắn một tin bất kỳ cho bot vừa tạo, rồi mở `https://api.telegram.org/bot<TOKEN>/getUpdates` để lấy `chat.id`.
3. Điền vào `.env`:

```
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=987654321
```

4. Chạy `docker compose up -d`.

Bạn sẽ nhận cảnh báo khi kỳ quay quá giờ, nguồn lỗi liên tục, hai nguồn lệch nhau, hoặc trang nguồn đổi cấu trúc.

---

## 9. Lệnh thường dùng

| Việc | Lệnh |
| --- | --- |
| **Tự kiểm tra cấu hình, dữ liệu, bảo mật** | `docker compose exec api python -m luckyvision.cli doctor` |
| Xem trạng thái | `docker compose ps` |
| Xem nhật ký | `docker compose logs -f worker` hoặc `docker compose logs -f api` |
| Khởi động lại | `docker compose restart` |
| Dừng (giữ dữ liệu) | `docker compose down` |
| Dừng và **xóa sạch dữ liệu** | `docker compose down -v` |
| Cập nhật sau khi sửa mã | `docker compose up -d --build` |
| Lập kỳ quay cho một ngày | `docker compose exec api python -m luckyvision.cli plan --date 2026-11-02` |
| Tải lại một ngày | `docker compose exec api python -m luckyvision.cli collect --date 2026-11-02` |
| Tải lại một kỳ | `docker compose exec api python -m luckyvision.cli collect --draw mb-mb-2026-11-02` |
| Tạo dự báo và chấm điểm ngay | `docker compose exec api python -m luckyvision.cli forecast` |
| Tạo hoặc đặt lại tài khoản | `docker compose exec api python -m luckyvision.cli create-admin --username ten --name "Tên" --role editor` |
| Vào cơ sở dữ liệu | `docker compose exec db psql -U luckey -d luckey` |

---

## 10. Đưa lên VPS (chạy 24/7)

Tóm tắt; chi tiết ở `README.md`, mục 6.

1. Thuê VPS Ubuntu 24.04, cấu hình 4 vCPU, 8 GB RAM.
2. Chép thư mục dự án lên VPS, rồi chạy với quyền root:
   ```bash
   sudo bash deploy/setup-vps.sh
   ```
   Script cài Docker, bật tường lửa (chỉ mở SSH), fail2ban và tự cập nhật bản vá.
3. Trên Cloudflare, tạo **Tunnel** trỏ tên miền tới `http://caddy:80`, lấy token.
4. Trên VPS:
   ```bash
   cd /opt/luckey
   cp .env.example .env && nano .env    # APP_ENV=prod, POSTGRES_PASSWORD, CLOUDFLARE_TUNNEL_TOKEN
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   docker compose exec api python -m luckyvision.cli create-admin --username admin --name "Quản trị"
   ```
5. Làm lại mục 6.2 đến 6.4 trên VPS để bật các nguồn dữ liệu, rồi chạy `doctor` (mục 9) để tự kiểm tra.
6. Cài sao lưu hằng đêm: `rclone config` rồi thêm vào `crontab -e`:
   ```
   15 2 * * * /opt/luckey/deploy/backup.sh >> /opt/luckey/backups/backup.log 2>&1
   ```

---

## 11. Xử lý lỗi thường gặp

| Hiện tượng | Cách xử lý |
| --- | --- |
| `docker: command not found` hoặc `Cannot connect to the Docker daemon` | Mở Docker Desktop và chờ báo **Engine running** |
| `running scripts is disabled on this system` khi chạy `start.ps1` | Chạy `Set-ExecutionPolicy -Scope Process Bypass` trong cùng cửa sổ PowerShell |
| `port is already allocated` hoặc không mở được http://localhost | Cổng 80 đang bị chương trình khác dùng (IIS, Skype, XAMPP). Mở `docker-compose.yml`, đổi `"80:80"` thành `"8080:80"`, chạy lại `docker compose up -d`, rồi vào http://localhost:8080 |
| `Đặt POSTGRES_PASSWORD trong .env` | Chưa có tệp `.env`. Làm lại mục 4 |
| `api` không lên `healthy` | Xem `docker compose logs api`. Thường do sai `POSTGRES_PASSWORD` sau khi đã tạo dữ liệu: chạy `docker compose down -v` rồi `docker compose up -d --build` |
| Trang quản trị báo sai mật khẩu nhiều lần, bị khóa | Chờ 15 phút, hoặc đặt lại bằng lệnh `create-admin` ở mục 7 |
| Mất điện thoại có ứng dụng xác thực | Admin khác vào **Tài khoản** bấm **Tắt 2 lớp**; hoặc chạy lệnh `create-admin` ở mục 7 |
| Trang dự báo báo "Tính năng AI chưa bật" | Chưa đặt `AI_API_KEY` trong `.env` (mục 7b) |
| Dự báo kỳ tới trống | Đài chưa đủ lịch sử. Chạy `backfill` (mục 7b) |
| `probe-source` báo `robots.txt ... không cho phép` | Trang không cho phép tải tự động. Không bật nguồn này |
| `probe-source` báo `Trang chặn truy cập tự động` | Trang bật chống bot. Không bật nguồn này; dùng nguồn khác |
| `probe-source` báo `Không tìm thấy kết quả của ngày này` | Ngày đó không có kỳ quay, hoặc trang đã đổi cấu trúc. Thử một ngày khác; nếu vẫn lỗi, gửi kết quả để chỉnh bộ cào |
| Kỳ quay báo "Quá giờ" dù đã qua giờ quay | Chưa bật nguồn thật (mục 6), hoặc nguồn đang lỗi: xem `docker compose logs worker` |
| Trang báo "Chưa có kết quả" hoặc "Chưa đủ dữ liệu" | Cơ sở dữ liệu mới có dữ liệu mẫu. Bật nguồn và chạy `backfill`, `feed` (mục 6, 7b) |
| Trang Công cụ báo "Chưa tải được dữ liệu" | API chưa chạy hoặc cơ sở dữ liệu trống: xem `docker compose ps`, `docker compose logs api`, rồi chạy `backfill` (mục 7b) |

---

## 12. Chạy kiểm thử (dành cho lập trình viên)

Cần Python 3.12:

```powershell
cd C:\Luckey\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
```

Kết quả mong đợi: `71 passed`.
