# PRODUCT REQUIREMENTS DOCUMENT (PRD)

## XS247 -- Lottery Analytics Platform

-   **Phiên bản:** 1.0
-   **Ngày:** 30/10/2026
-   **Thị trường:** Việt Nam
-   **Phạm vi:** Full -- xổ số miền Bắc, miền Trung, miền Nam
-   **Mục tiêu:** Xây dựng sản phẩm kinh doanh thực tế
-   **Định hướng:** Tra cứu kết quả, thống kê dữ liệu, dự báo tham khảo
    và đánh giá mô hình

------------------------------------------------------------------------

# 1. Tổng quan sản phẩm

## 1.1. Product Vision

XS247 là nền tảng web tra cứu và phân tích dữ liệu xổ số tại Việt
Nam. Sản phẩm giúp người dùng tiếp cận kết quả xổ số ba miền, khám phá
các thống kê lịch sử và theo dõi các nhận định được tạo ra từ thuật toán
thống kê hoặc Machine Learning.

**Nguyên tắc sản phẩm:** XS247 cung cấp thông tin, thống kê và dự
báo tham khảo; không cam kết trúng thưởng, không bán số đảm bảo trúng và
không tổ chức cá cược.

## 1.2. Product Goals

  ID    Mục tiêu            Kết quả mong muốn
  ----- ------------------- ---------------------------------------------
  G01   Tra cứu kết quả     Nhanh, chính xác, đầy đủ
  G02   Phân tích dữ liệu   Thống kê theo nhiều chiều
  G03   Dự báo              Có cơ sở dữ liệu, minh bạch
  G04   Đánh giá mô hình    Đo lường được hiệu quả
  G05   Kinh doanh          Có khả năng phát triển Freemium
  G06   Mở rộng             Có khả năng mở rộng khi lượng truy cập tăng

## 1.3. Giá trị cốt lõi

-   **Accuracy:** Dữ liệu kết quả phải chính xác.
-   **Transparency:** Minh bạch phương pháp phân tích.
-   **Usability:** Dễ sử dụng trên máy tính và điện thoại.
-   **Trust:** Không tạo kỳ vọng sai lệch về khả năng trúng thưởng.

# 2. Đối tượng người dùng

  -----------------------------------------------------------------------
  Persona                 Nhu cầu                 Giá trị sản phẩm
  ----------------------- ----------------------- -----------------------
  Người tra cứu           Xem kết quả hàng ngày   Tra cứu nhanh

  Người thích thống kê    Phân tích các con số    Biểu đồ và thống kê

  Người quan tâm AI       Tìm hiểu dự báo         Mô hình và đánh giá

  Người dùng thường xuyên Theo dõi thông tin mỗi  Lưu lịch sử, yêu thích
                          ngày                    
  -----------------------------------------------------------------------

## 2.1. User Journey chính

1.  Người dùng truy cập website.
2.  Chọn miền Bắc, miền Trung hoặc miền Nam.
3.  Chọn tỉnh/đài hoặc ngày quay.
4.  Xem kết quả xổ số.
5.  Mở trang thống kê để xem tần suất và xu hướng.
6.  Xem dự báo tham khảo.
7.  Theo dõi kết quả dự báo sau khi có kết quả thực tế.

# 3. Phạm vi sản phẩm

## 3.1. Public Website

-   Dashboard / Trang chủ.
-   Tra cứu kết quả xổ số.
-   Thống kê và phân tích.
-   Dự báo.
-   Lịch sử và đánh giá dự báo.
-   Tài khoản người dùng.
-   Bộ số yêu thích.

## 3.2. Admin Portal

-   Quản lý kết quả xổ số.
-   Quản lý tỉnh/đài và lịch quay.
-   Xác minh dữ liệu.
-   Quản lý mô hình dự báo.
-   Quản lý người dùng.
-   Quản lý nội dung và cấu hình.
-   Theo dõi audit log và tình trạng hệ thống.

# 4. Functional Requirements

Quy ước ưu tiên: - **P0:** Bắt buộc trong MVP. - **P1:** Quan trọng,
triển khai sau MVP. - **P2:** Có thể phát triển trong tương lai.

## 4.1. EPIC 01 -- Lottery Dashboard

  ID    Chức năng             Mô tả                                   Priority
  ----- --------------------- --------------------------------------- ----------
  F01   Latest Results        Hiển thị kết quả mới nhất đã xác minh   P0
  F02   Region Selection      Chọn ba miền                            P0
  F03   Quick Statistics      Thống kê tổng quan                      P0
  F04   Latest Prediction     Hiển thị dự báo mới nhất                P0
  F05   Popular Numbers       Số có tần suất cao                      P1
  F06   Historical Overview   Thống kê theo thời gian                 P1
  F07   Notification          Thông báo kết quả mới                   P2

**Business Rules** - Trang chủ hiển thị dữ liệu theo khu vực người dùng
chọn. - Không hiển thị kết quả chưa được xác minh như kết quả chính
thức. - Nếu dữ liệu chưa cập nhật, hiển thị thời điểm cập nhật gần
nhất. - Dự báo phải có ngày mục tiêu và thời gian tạo. - Không được thay
đổi dự báo đã công bố sau khi kết quả thực tế xuất hiện.

## 4.2. EPIC 02 -- Lottery Results

  ID    Chức năng         Mô tả                   Priority
  ----- ----------------- ----------------------- ----------
  F08   Result List       Danh sách kết quả       P0
  F09   Region Filter     Lọc theo miền           P0
  F10   Province Filter   Lọc theo tỉnh/đài       P0
  F11   Date Filter       Lọc theo ngày           P0
  F12   Result Detail     Chi tiết từng kỳ quay   P0
  F13   Result Search     Tìm kiếm kết quả        P1
  F14   Result Export     Xuất dữ liệu            P2

**Business Rules** - Miền Bắc có lịch và cơ cấu giải riêng. - Miền Trung
và miền Nam có nhiều đài quay trong một ngày. - Mỗi kết quả phải gắn với
một kỳ quay cụ thể. - Mỗi giải thưởng phải lưu đầy đủ các số trúng
thưởng. - Không gộp kết quả của các đài khác nhau thành một kỳ quay. -
Lưu nguồn dữ liệu và thời điểm cập nhật.

## 4.3. EPIC 03 -- Statistics & Analytics

  -----------------------------------------------------------------------
  ID                Chức năng         Mô tả             Priority
  ----------------- ----------------- ----------------- -----------------
  F15               Number Frequency  Tần suất xuất     P0
                                      hiện              

  F16               Date Range        Chọn khoảng thời  P0
                                      gian              

  F17               Hot Numbers       Nhóm số xuất hiện P0
                                      nhiều             

  F18               Cold Numbers      Nhóm số có tần    P0
                                      suất thấp/lâu     
                                      chưa xuất hiện    

  F19               Frequency Chart   Biểu đồ tần suất  P0

  F20               Number Trend      Xu hướng xuất     P1
                                      hiện              

  F21               Pair Analysis     Phân tích cặp số  P1

  F22               Heatmap           Bản đồ nhiệt      P1

  F23               Cross-region      So sánh giữa các  P2
                    Analysis          miền              
  -----------------------------------------------------------------------

**Tham số thống kê** - 7 ngày gần nhất. - 30 ngày gần nhất. - 90 ngày
gần nhất. - 180 ngày gần nhất. - 365 ngày gần nhất. - Khoảng thời gian
tùy chỉnh (nếu được hỗ trợ).

**Business Rules** 1. Chỉ sử dụng dữ liệu đã xác minh. 2. Người dùng có
thể chọn miền và tỉnh/đài. 3. Hiển thị số lượng kỳ quay được sử dụng. 4.
Khi thay đổi bộ lọc, biểu đồ và bảng phải cập nhật đồng bộ. 5. Hot/Cold
chỉ mô tả dữ liệu lịch sử, không khẳng định khả năng xuất hiện trong
tương lai.

## 4.4. EPIC 04 -- AI Prediction

  ID    Chức năng               Mô tả                    Priority
  ----- ----------------------- ------------------------ ----------
  F24   Prediction Engine       Engine tạo dự báo        P0
  F25   Number Ranking          Xếp hạng các số          P0
  F26   Prediction History      Lưu lịch sử dự báo       P0
  F27   Model Information       Thông tin mô hình        P0
  F28   Prediction Evaluation   Đánh giá dự báo          P0
  F29   Multiple Models         Nhiều thuật toán         P1
  F30   Model Comparison        So sánh mô hình          P1
  F31   Auto Retraining         Huấn luyện lại tự động   P2

**Phương pháp MVP** - Frequency Analysis. - Rolling Window Statistics. -
Historical Distribution. - Random Baseline để so sánh.

**Phương pháp thử nghiệm ở giai đoạn sau** - Logistic Regression. -
Random Forest. - XGBoost. - Ensemble Model.

**Business Rules** - Mỗi dự báo phải được lưu trước thời điểm quay
thưởng. - Mỗi dự báo gắn với miền hoặc đài, ngày quay mục tiêu và phiên
bản mô hình. - Không cho phép sửa dự báo đã công bố. - Lưu phương pháp,
dữ liệu đầu vào và phiên bản mô hình. - Không sử dụng thông điệp "chắc
chắn trúng" hoặc "đảm bảo thắng". - Chỉ hiển thị xác suất nếu đã được
hiệu chỉnh và kiểm định; nếu chưa, hiển thị điểm xếp hạng thống kê.

## 4.5. EPIC 05 -- Prediction Evaluation

  ID    Chức năng                Mô tả                               Priority
  ----- ------------------------ ----------------------------------- ----------
  F32   Actual Comparison        So sánh dự báo và kết quả thực tế   P0
  F33   Hit Rate                 Tỷ lệ trùng khớp theo định nghĩa    P0
  F34   Model Performance        Hiệu quả mô hình                    P0
  F35   Historical Performance   Hiệu quả theo thời gian             P1
  F36   Model Benchmark          So sánh với random baseline         P1

**Chỉ số đánh giá** - **Hit Count:** Số lượng kết quả trùng khớp. -
**Hit Rate:** Tỷ lệ dự báo có ít nhất một kết quả trùng, theo định nghĩa
được công bố. - **Precision@K:** Tỷ lệ số dự báo đúng trong K số được
chọn. - **Recall:** Khả năng tìm được các kết quả mục tiêu. - **Brier
Score:** Đánh giá chất lượng dự báo xác suất.

Cần định nghĩa chính xác cách tính từng metric theo từng loại xổ số và
mục tiêu dự báo. Không được dùng một công thức tùy ý rồi gọi là "độ
chính xác AI".

## 4.6. EPIC 06 -- User Account

  ID    Chức năng          Mô tả                 Priority
  ----- ------------------ --------------------- ----------
  F37   Register           Đăng ký tài khoản     P1
  F38   Login              Đăng nhập             P1
  F39   Profile            Quản lý thông tin     P1
  F40   Favorite Numbers   Lưu bộ số yêu thích   P1
  F41   User History       Lịch sử tra cứu       P2
  F42   Password Reset     Khôi phục mật khẩu    P1

MVP ưu tiên cho phép người dùng tra cứu và xem thống kê không cần đăng
nhập để giảm rào cản sử dụng.

## 4.7. EPIC 07 -- Admin Portal

  ID    Chức năng           Mô tả                Priority
  ----- ------------------- -------------------- ----------
  F43   Admin Login         Đăng nhập quản trị   P0
  F44   Result Management   Quản lý kết quả      P0
  F45   Data Verification   Xác minh dữ liệu     P0
  F46   Draw Schedule       Quản lý lịch quay    P0
  F47   Model Management    Quản lý mô hình      P1
  F48   User Management     Quản lý người dùng   P1
  F49   Audit Log           Nhật ký hoạt động    P0
  F50   System Monitoring   Theo dõi hệ thống    P1

**Business Rules** - Chỉ tài khoản có quyền phù hợp mới được truy cập
Admin Portal. - Admin có thể thêm và chỉnh sửa kết quả. - Mọi thay đổi
dữ liệu quan trọng phải được ghi audit. - Kết quả sau chỉnh sửa phải
được xác minh lại. - Không xóa lịch sử chỉnh sửa.

# 5. MVP -- Minimum Viable Product

## 5.1. Mục tiêu MVP

Ra mắt phiên bản có thể sử dụng thực tế, hỗ trợ dữ liệu xổ số ba miền,
tra cứu kết quả, thống kê lịch sử và dự báo tham khảo có thể đánh giá
được.

## 5.2. MVP Feature List

  Module          Chức năng MVP                      Priority
  --------------- ---------------------------------- ----------
  Dashboard       Trang chủ, kết quả mới nhất        P0
  Results         Tra cứu kết quả ba miền            P0
  Statistics      Tần suất 7/30/90 ngày              P0
  Prediction      Dự báo bằng phương pháp thống kê   P0
  Evaluation      Đối chiếu dự báo với kết quả       P0
  Admin           Quản lý và xác minh kết quả        P0
  Data Pipeline   Thu thập, xử lý dữ liệu            P0
  Account         Đăng ký, đăng nhập                 P1
  Favorites       Lưu số yêu thích                   P1
  Notifications   Thông báo                          P2

## 5.3. Màn hình MVP

1.  Home -- Trang chủ.
2.  Results -- Kết quả xổ số.
3.  Statistics -- Thống kê.
4.  Prediction -- Dự báo.
5.  Evaluation -- Đánh giá dự báo.
6.  Login/Register -- Đăng nhập/đăng ký (P1).
7.  Result Management -- Quản lý kết quả.
8.  Data Verification -- Xác minh dữ liệu.
9.  Audit Log -- Nhật ký quản trị.

## 5.4. Ngoài phạm vi MVP

-   Chatbot AI.
-   Thanh toán trực tuyến.
-   Subscription trả phí.
-   Mobile Application.
-   Push Notification.
-   Social Community.
-   Deep Learning phức tạp.
-   Tự động huấn luyện mô hình nâng cao.
-   Affiliate.

# 6. User Stories & Acceptance Criteria

Acceptance Criteria sử dụng cấu trúc Given -- When -- Then để QA có thể
chuyển thành Test Case.

## EPIC 01 -- Lottery Results

### US-001: Xem kết quả xổ số mới nhất

**User Story**

As a visitor, I want to view the latest lottery results, so that I can
quickly check the results.

**Acceptance Criteria**

  -----------------------------------------------------------------------
  Given                   When                    Then
  ----------------------- ----------------------- -----------------------
  Người dùng truy cập     Trang được tải          Hiển thị kết quả mới
  trang chủ                                       nhất đã xác minh

  Có nhiều tỉnh quay      Người dùng chọn miền    Hiển thị các đài tương
  trong ngày              Nam                     ứng

  Người dùng chọn miền    Trang tải dữ liệu       Hiển thị kết quả theo
  Trung                                           từng tỉnh

  Không có dữ liệu mới    Trang được tải          Hiển thị trạng thái
                                                  chưa có kết quả

  Dữ liệu đang cập nhật   Người dùng truy cập     Hiển thị trạng thái cập
                                                  nhật
  -----------------------------------------------------------------------

### US-002: Lọc kết quả theo ngày

**User Story**

As a visitor, I want to filter lottery results by date, so that I can
view historical results.

**Acceptance Criteria** 1. Người dùng có thể chọn ngày cần tra cứu. 2.
Hệ thống chỉ hiển thị kết quả thuộc ngày đã chọn. 3. Người dùng có thể
kết hợp bộ lọc miền và tỉnh/đài. 4. Nếu không có dữ liệu, hiển thị thông
báo phù hợp. 5. Ngày hiển thị theo múi giờ Việt Nam.

### US-003: Xem chi tiết một kỳ quay

**Acceptance Criteria** 1. Mỗi kỳ quay có mã định danh duy nhất. 2. Hiển
thị tên tỉnh hoặc đài. 3. Hiển thị đầy đủ các giải thưởng. 4. Hiển thị
ngày quay. 5. Hiển thị nguồn dữ liệu và thời điểm xác minh.

## EPIC 02 -- Statistics

### US-004: Thống kê tần suất xuất hiện

**User Story**

As a visitor, I want to see the frequency of lottery numbers, so that I
can understand historical patterns.

**Acceptance Criteria** - Given người dùng chọn miền Bắc. - When người
dùng chọn khoảng thời gian 30 ngày. - Then hệ thống hiển thị tần suất
của từng số từ 00 đến 99 theo định nghĩa thống kê đã chọn. - Then hệ
thống hiển thị số kỳ quay được sử dụng. - Then người dùng có thể chuyển
đổi giữa 7, 30 và 90 ngày. - Then dữ liệu biểu đồ phải khớp với dữ liệu
bảng.

### US-005: Xem Hot Numbers và Cold Numbers

**Acceptance Criteria** 1. Hệ thống xếp hạng số theo tần suất trong
khoảng thời gian được chọn. 2. Hot Numbers là nhóm có tần suất cao. 3.
Cold Numbers là nhóm có tần suất thấp hoặc chưa xuất hiện. 4. Khi hai số
có cùng tần suất, sử dụng quy tắc sắp xếp ổn định. 5. Hiển thị rõ khoảng
thời gian và số kỳ quay được phân tích.

## EPIC 03 -- AI Prediction

### US-006: Xem dự báo cho kỳ quay tiếp theo

**User Story**

As a visitor, I want to view statistical predictions, so that I can
explore numbers suggested by the analysis system.

**Acceptance Criteria**

  -----------------------------------------------------------------------
  Given                   When                    Then
  ----------------------- ----------------------- -----------------------
  Có dữ liệu lịch sử hợp  Hệ thống chạy           Tạo kết quả dự báo
  lệ                      prediction              

  Prediction hoàn tất     Người dùng mở trang     Hiển thị danh sách số
                                                  được xếp hạng

  Người dùng chọn miền    Đổi bộ lọc              Hiển thị dự báo tương
  khác                                            ứng

  Chưa có prediction      Người dùng truy cập     Hiển thị trạng thái
                                                  chưa có dữ liệu

  Prediction đã công bố   Có kết quả thực tế      Không được chỉnh sửa
                                                  bản dự báo cũ
  -----------------------------------------------------------------------

**Thông tin bắt buộc hiển thị** - Khu vực hoặc đài. - Ngày quay mục
tiêu. - Thời gian tạo dự báo. - Phiên bản thuật toán. - Khoảng thời gian
dữ liệu đầu vào. - Danh sách số được xếp hạng. - Giải thích phương pháp
phân tích.

### US-007: Lưu lịch sử dự báo

**Acceptance Criteria** 1. Mỗi lần tạo dự báo có prediction ID. 2. Dự
báo được lưu vào database. 3. Không cho phép chỉnh sửa dự báo đã công
bố. 4. Dự báo liên kết với kỳ quay mục tiêu. 5. Có thể truy xuất lại dự
báo cũ để đánh giá.

## EPIC 04 -- Prediction Evaluation

### US-008: So sánh dự báo với kết quả thực tế

**User Story**

As a visitor, I want to compare predictions with actual results, so that
I can understand the historical performance of the prediction model.

**Acceptance Criteria** 1. Khi kết quả thực tế đã được xác minh, hệ
thống thực hiện đối chiếu. 2. Chỉ so sánh dự báo và kết quả cùng mục
tiêu. 3. Hiển thị số lượng kết quả trùng khớp. 4. Hiển thị số dự báo đã
chọn. 5. Hiển thị số kỳ đã đánh giá. 6. Không đánh giá kỳ quay chưa có
kết quả xác minh. 7. Kết quả đánh giá có thể được tái tính toán và kiểm
tra.

## EPIC 05 -- Admin

### US-009: Quản lý kết quả xổ số

**User Story**

As an administrator, I want to manage lottery results, so that I can
maintain accurate data.

**Acceptance Criteria** - Chỉ Admin có quyền mới được sử dụng chức
năng. - Có thể thêm kết quả mới. - Có thể chỉnh sửa kết quả sai. - Có
xác nhận trước khi lưu. - Không cho phép tạo bản ghi trùng kỳ quay và
giải thưởng. - Mọi thay đổi phải được ghi vào Audit Log. - Kết quả sau
chỉnh sửa phải được đánh dấu cần xác minh lại.

### US-010: Xác minh kết quả

**Acceptance Criteria** 1. Kết quả mới nhập mặc định là chưa xác minh.
2. Admin có thể kiểm tra dữ liệu trước khi xác nhận. 3. Chỉ dữ liệu đã
xác minh mới được sử dụng cho thống kê chính thức. 4. Khi xác minh thành
công, lưu người xác minh và thời gian. 5. Nếu phát hiện sai sót, có thể
chuyển về trạng thái cần kiểm tra.

### US-011: Theo dõi Audit Log

**Acceptance Criteria** 1. Ghi lại người thực hiện. 2. Ghi lại thời
gian. 3. Ghi lại hành động. 4. Ghi lại dữ liệu trước và sau khi chỉnh
sửa. 5. Admin thông thường không được phép xóa lịch sử audit.

# 7. Data Requirements

## 7.1. Nguồn dữ liệu

Hệ thống thu thập kết quả từ nguồn được phép sử dụng, ưu tiên nguồn công
bố chính thức hoặc nhà cung cấp dữ liệu có quyền cung cấp.

## 7.2. Data Pipeline

1.  **Data Sources:** Nguồn dữ liệu kết quả xổ số.
2.  **Data Collector:** Thu thập dữ liệu tự động.
3.  **Data Validation:** Kiểm tra định dạng, tính đầy đủ và trùng lặp.
4.  **Data Verification:** Xác minh dữ liệu.
5.  **PostgreSQL:** Lưu trữ dữ liệu.
6.  **Statistics Engine:** Tính toán thống kê.
7.  **Prediction Engine:** Tạo dự báo.
8.  **Backend API:** Cung cấp dữ liệu cho Frontend.

## 7.3. Database Design -- Các bảng chính

  Table                      Mục đích
  -------------------------- ----------------------
  `regions`                  Quản lý ba miền
  `provinces`                Quản lý tỉnh/đài
  `draw_schedules`           Lịch quay
  `lottery_draws`            Các kỳ quay
  `prizes`                   Danh mục giải thưởng
  `lottery_results`          Kết quả từng giải
  `data_sources`             Nguồn dữ liệu
  `data_verifications`       Lịch sử xác minh
  `predictions`              Dự báo
  `prediction_items`         Các số dự báo
  `prediction_models`        Phiên bản mô hình
  `prediction_evaluations`   Kết quả đánh giá
  `users`                    Người dùng
  `favorites`                Bộ số yêu thích
  `audit_logs`               Nhật ký quản trị

## 7.4. Data Relationships

``` mermaid
erDiagram
    REGIONS ||--o{ PROVINCES : contains
    PROVINCES ||--o{ DRAW_SCHEDULES : has
    PROVINCES ||--o{ LOTTERY_DRAWS : conducts
    LOTTERY_DRAWS ||--o{ LOTTERY_RESULTS : contains
    PRIZES ||--o{ LOTTERY_RESULTS : classifies
    DATA_SOURCES ||--o{ LOTTERY_RESULTS : provides
    LOTTERY_DRAWS ||--o{ PREDICTIONS : target
    PREDICTION_MODELS ||--o{ PREDICTIONS : generates
    PREDICTIONS ||--o{ PREDICTION_ITEMS : contains
    PREDICTIONS ||--o{ PREDICTION_EVALUATIONS : evaluated
    USERS ||--o{ FAVORITES : owns
```

**Quyết định thiết kế** - `lottery_draws` đại diện cho một kỳ quay cụ
thể. - `lottery_results` lưu từng giải và từng số trúng thưởng. - Số
trúng thưởng phải lưu dưới kiểu chuỗi để giữ số 0 ở đầu, ví dụ `"08"`. -
Dữ liệu dự báo phải có snapshot độc lập, không phụ thuộc vào dữ liệu kết
quả thay đổi sau này. - Kết quả đã công bố cần có version hoặc lịch sử
thay đổi.

## 7.5. Trạng thái dữ liệu

``` text
COLLECTED → VALIDATED → VERIFIED → PUBLISHED
```

Chỉ dữ liệu ở trạng thái `PUBLISHED` mới được hiển thị như kết quả chính
thức trên website.

# 8. Non-Functional Requirements (NFR)

  ID      Yêu cầu          Tiêu chí mục tiêu
  ------- ---------------- -----------------------------------------
  NFR01   Performance      API đọc thông thường P95 dưới 500ms
  NFR02   Availability     Mục tiêu 99.5%/tháng
  NFR03   Responsive       Hỗ trợ mobile, tablet, desktop
  NFR04   Security         HTTPS, phân quyền, bảo vệ API
  NFR05   Data Integrity   Không tạo kết quả trùng kỳ quay
  NFR06   Backup           Sao lưu database hàng ngày
  NFR07   Monitoring       Theo dõi lỗi API và pipeline
  NFR08   Scalability      Có khả năng mở rộng ngang
  NFR09   SEO              URL thân thiện, metadata đầy đủ
  NFR10   Audit            Lưu lịch sử thay đổi dữ liệu quan trọng

Đây là mục tiêu ban đầu cần được đội kỹ thuật kiểm chứng và điều chỉnh
theo ngân sách, không phải SLA đã được xác nhận.

## 8.1. Data Quality Requirements

-   Không có kết quả trùng lặp.
-   Không thiếu giải thưởng bắt buộc.
-   Số lượng chữ số đúng theo cơ cấu giải.
-   Kết quả thuộc đúng tỉnh và ngày quay.
-   Mỗi bản ghi truy xuất được nguồn.
-   Có cơ chế phát hiện kết quả bất thường.
-   Có cảnh báo khi quá thời gian dự kiến mà chưa có dữ liệu.

# 9. Business Model

Định hướng Freemium, chỉ triển khai thương mại sau khi hoàn tất rà soát
pháp lý.

## 9.1. Free Plan

-   Tra cứu kết quả ba miền.
-   Xem thống kê cơ bản.
-   Xem lịch sử kết quả.
-   Xem báo cáo dự báo cơ bản.

## 9.2. Premium Plan

Mức giá giả định để kiểm chứng thị trường: **49.000--99.000 VNĐ/tháng**.

-   Thống kê nâng cao.
-   Biểu đồ chuyên sâu.
-   Lọc dữ liệu tùy chỉnh.
-   Lịch sử phân tích mở rộng.
-   So sánh nhiều phương pháp thống kê.
-   Xuất báo cáo.

## 9.3. Nguồn doanh thu tiềm năng

1.  Gói thuê bao Premium.
2.  Quảng cáo phù hợp quy định pháp luật.
3.  Dịch vụ dữ liệu và báo cáo phân tích B2B nếu có quyền khai thác.

Không lấy doanh thu từ bán số dự đoán hoặc cam kết khả năng trúng thưởng
làm nền tảng kinh doanh.

**Legal Gate:** Trước khi thương mại hóa, cần rà soát pháp lý đối với
nội dung xổ số, quảng cáo, dữ liệu nguồn, thu phí và các hoạt động liên
quan. Nếu chưa được xác nhận phù hợp, chỉ triển khai mô hình thông tin
và phân tích không thu phí.

# 10. Product Metrics -- KPI

  Nhóm           KPI                                               Mục tiêu ban đầu
  -------------- --------------------------------- --------------------------------
  Acquisition    Monthly Active Users                5.000 sau giai đoạn thử nghiệm
  Engagement     Returning Users                                           Trên 30%
  Performance    API P95                                                 Dưới 500ms
  Data Quality   Dữ liệu chính xác                                            99.9%
  Data Quality   Kỳ quay cập nhật đúng quy trình                           Trên 98%
  Product        Tỷ lệ sử dụng Statistics                                  Trên 30%
  Product        Tỷ lệ quay lại sau 7 ngày                                 Trên 20%

Các KPI người dùng là mục tiêu giả định, cần điều chỉnh sau khi có dữ
liệu thực tế.

Đối với AI Prediction, cần theo dõi: - Khả năng tái lập kết quả đánh
giá. - Backtesting không bị data leakage. - Baseline ngẫu nhiên. - Công
khai kết quả cả khi mô hình kém baseline. - Chất lượng dự báo theo thời
gian.

# 11. Roadmap -- Kế hoạch triển khai

Kế hoạch mục tiêu: 10--12 tuần với đội ngũ nhỏ, phụ thuộc vào khả năng
tiếp cận nguồn dữ liệu hợp pháp và chất lượng.

  -----------------------------------------------------------------------
  Sprint                  Thời gian               Phạm vi
  ----------------------- ----------------------- -----------------------
  Sprint 1 -- Discovery & Tuần 1--2               Yêu cầu nghiệp vụ,
  Foundation                                      UI/UX, database, khởi
                                                  tạo project, CI/CD

  Sprint 2 -- Lottery     Tuần 3--4               Data Collector, dữ liệu
  Data                                            ba miền, API kết quả,
                                                  Admin, xác minh

  Sprint 3 -- Statistics  Tuần 5--6               Frequency Analysis,
                                                  Hot/Cold, API thống kê,
                                                  biểu đồ

  Sprint 4 -- Prediction  Tuần 7--8               Prediction Engine, lịch
                                                  sử dự báo, baseline,
                                                  backtesting, evaluation

  Sprint 5 -- Integration Tuần 9--10              Tích hợp, Integration
  & QA                                            Test, E2E, Security và
                                                  Performance Test

  Sprint 6 -- Release     Tuần 11--12             UAT, sửa lỗi,
                                                  production deployment,
                                                  theo dõi phản hồi
  -----------------------------------------------------------------------

## 11.1. Đội ngũ đề xuất

  Vai trò                 Số lượng
  -------------------- -----------
  Product Owner                  1
  UI/UX Designer                 1
  Frontend Developer             1
  Backend Developer              1
  Data/ML Engineer               1
  QA Engineer                    1
  DevOps Engineer        Part-time

# 12. Risks & Mitigation

  -----------------------------------------------------------------------
  Rủi ro                  Mức độ                  Giải pháp
  ----------------------- ----------------------- -----------------------
  Nguồn dữ liệu không ổn  Cao                     Nguồn được cấp quyền,
  định                                            kiểm tra chéo

  Dữ liệu sai             Cao                     Validation và xác minh

  AI không dự báo tốt     Cao                     Baseline, backtesting,
                                                  công khai hạn chế

  Chi phí vận hành        Trung bình              Cache, tối ưu truy vấn

  Traffic tăng đột biến   Trung bình              CDN, autoscaling

  Rủi ro pháp lý          Cao                     Legal review trước
                                                  thương mại hóa

  Lộ dữ liệu tài khoản    Cao                     Encryption, IAM,
                                                  security audit
  -----------------------------------------------------------------------

# 13. Definition of Done

Một tính năng không được xem là hoàn thành chỉ vì Developer đã code
xong.

-   [ ] Code đã được review và merge.
-   [ ] Unit Test đạt yêu cầu.
-   [ ] Integration Test đạt yêu cầu.
-   [ ] Acceptance Criteria được QA xác nhận.
-   [ ] Không còn bug Critical/Blocker.
-   [ ] API có tài liệu.
-   [ ] Có logging và monitoring.
-   [ ] Có kiểm tra quyền truy cập.
-   [ ] UI hoạt động trên desktop và mobile.
-   [ ] PO xác nhận kết quả UAT.

## 13.1. MVP Release Gate

Chỉ phát hành khi: 1. Tra cứu được dữ liệu ba miền. 2. Có khả năng quản
lý và xác minh kết quả. 3. Thống kê đúng với dữ liệu nguồn đã xác minh.
4. Tạo và lưu được dự báo. 5. Dự báo có timestamp trước thời điểm quay
thưởng. 6. Đánh giá được dự báo so với kết quả thực tế. 7. Admin có thể
truy vết lịch sử chỉnh sửa. 8. Không còn lỗi bảo mật nghiêm trọng. 9. Đã
hoàn thành rà soát pháp lý cần thiết.

# 14. Product Owner Decisions

## 14.1. Phạm vi dự báo

**Option A -- Dự báo 2 chữ số cuối (00--99)** - Phân tích các số từ 00
đến 99. - Thống kê tần suất. - Xếp hạng con số. - Đánh giá dự báo theo
kết quả thực tế.

**Option B -- Dự báo đầy đủ các giải** - Phân tích từng giải thưởng. -
Phân tích cấu trúc chữ số. - Thử nghiệm dự báo theo từng giải.

**Option C -- Dự báo kết hợp** - Dự báo 2 chữ số cuối. - Phân tích cặp
số. - Phân tích theo tỉnh và khu vực. - So sánh nhiều mô hình.

**Đề xuất PO:** Chọn Option A cho MVP vì dễ chuẩn hóa dữ liệu và đánh
giá mô hình hơn. Option B và C được xem xét sau khi có đủ dữ liệu và kết
quả kiểm chứng.

## 14.2. Quy tắc phân tích dữ liệu

  Phạm vi      Ý nghĩa
  ------------ ----------------------------------------
  Miền Bắc     Phân tích riêng kết quả xổ số miền Bắc
  Miền Trung   Phân tích theo từng tỉnh/đài
  Miền Nam     Phân tích theo từng tỉnh/đài
  Toàn quốc    So sánh dữ liệu giữa các khu vực

Không trộn kết quả các tỉnh vào cùng một tập dữ liệu dự báo vì lịch
quay, cơ cấu giải và số lượng kỳ quay khác nhau.

## 14.3. Tiêu chí thành công MVP

-   Người dùng tra cứu được kết quả chính xác.
-   Hệ thống hoạt động ổn định.
-   Dữ liệu được cập nhật và xác minh.
-   Người dùng hiểu được cách thống kê.
-   Dự báo có lịch sử minh bạch.
-   Có thể đo lường hiệu quả mô hình.
-   Có cơ sở để phát triển sản phẩm thương mại.

# 15. Kết luận

XS247 MVP tập trung vào các module cốt lõi:

1.  Lottery Data Management.
2.  Lottery Results.
3.  Statistics & Analytics.
4.  Prediction Engine.
5.  Prediction Evaluation.
6.  Admin Portal.

**Quyết định cần chốt trước khi thiết kế kỹ thuật:** Phạm vi dự báo 2
chữ số cuối (00--99) có phù hợp để làm chức năng AI Prediction đầu tiên
không?

Quyết định này ảnh hưởng trực tiếp đến Database Design, thuật toán, API
và bộ Test Case.

------------------------------------------------------------------------

## Tài liệu tiếp theo

Sau PRD, đề xuất xây dựng: 1. UI/UX Specification -- Wireframe, giao
diện và luồng người dùng. 2. Software Architecture -- Kiến trúc hệ thống
và công nghệ. 3. Database Design -- ERD, bảng, quan hệ và indexes. 4.
API Specification -- REST API, request/response và validation. 5.
Product Backlog -- Epic, User Story, Task và Test Case.
