# Atlas Amazon Performance — Project Knowledge

Tài liệu này là nguồn quy ước chính thức của dashboard. Khi thay đổi logic,
phải cập nhật cả code, test và tài liệu này.

## 1. Mục tiêu và phạm vi

- Dashboard Streamlit nội bộ cho Wrappiness và Pawsionate.
- Bốn khu vực chính: Tổng quan, Sản phẩm, Ads performance và Team KPI.
- Dữ liệu Order không cần upload lại mỗi lần truy cập.
- Không lưu file report gốc, order-level data hay thông tin khách hàng trong
  repository/dashboard snapshot.
- Team KPI có lớp mật khẩu riêng. Dashboard không còn dùng data-encryption key
  để giải mã snapshot Order.

## 2. Hai hệ thời gian độc lập

### Lark calendar time

- Record ID, ASIN, ownership và workflow KPI dùng ngày trả về từ Lark.
- Không đổi timezone cho bất kỳ trường ngày Lark nào.
- Bộ lọc tháng bao gồm trọn ngày đầu và ngày cuối theo ngày lịch Lark.
- Timestamp có giờ trong ngày cuối tháng vẫn phải được tính.

### Amazon Order time

- `purchase-date` của Order Report được parse theo UTC rồi đổi sang
  `America/Los_Angeles`.
- Sau khi đổi timezone mới lấy Purchase Date và Purchase Month.
- Orders, Units và Revenue chỉ được lọc theo Purchase Month Los Angeles.
- Không dùng ngày Lark để lọc Revenue và không dùng Purchase Time để lọc output
  workflow của Lark.

## 3. Order Report và Revenue

- Hai store: Wrappiness và Pawsionate.
- Chỉ dùng currency USD.
- Loại toàn bộ dòng `Cancelled`.
- `Revenue = Item Price + Shipping Price`.
- Daily import upsert theo `order-item-id`.
- Weekly/monthly import thay thế toàn bộ store + khoảng ngày Los Angeles được
  chỉ định trước khi insert report mới.
- Pipeline từ chối report có order nằm ngoài replacement window.
- Tổng quan, Sản phẩm và Team KPI phải dùng chung
  `snapshot/dashboard_snapshot.csv`; không dùng số demo hard-code cho Revenue.

Snapshot Order chỉ chứa:

- Store
- Purchase Date Los Angeles
- ASIN
- Revenue
- Orders
- Units
- Record ID hint lấy từ SKU

`snapshot/dashboard_snapshot.metadata.json` lưu schema version, thời điểm report
nguồn được cập nhật, timezone, phạm vi ngày và số dòng snapshot.

## 4. Lark Base và mapping sản phẩm

Các bảng nguồn:

- `TOTAL ASINs`
- `MRND IDEA`
- `CLIPARTS`

Mapping chuẩn:

- ASIN Order Report nối với ASIN trong TOTAL ASINs.
- Các ASIN cùng Record ID được gộp thành một sản phẩm.
- Nếu ASIN chưa map được trực tiếp, dùng Record ID hint trong SKU làm fallback.
- Bốn cột nhân sự: `Idea By`, `Managed By`, `Custom By`, `Ads By`.
- Không tìm thấy nhân sự thì để trống, không tự gán tên.

Trang Sản phẩm:

- Gộp Revenue, Orders và Units của tất cả ASIN theo Record ID.
- Xếp hạng theo Revenue giảm dần và chỉ lấy Top 50 Record ID.
- `Share = Revenue Record ID / tổng Revenue của store đang chọn`.
- Revenue hiển thị có dấu phân cách hàng nghìn.
- Share chỉ hiển thị phần trăm, không dùng progress bar.
- Bảng được kéo dài để hạn chế thanh cuộn dọc ngắn.

## 5. Workflow KPI toàn portfolio

Cách tính phải giống Lark Metrics: lọc record theo ngày rồi dùng `Record count`,
không deduplicate theo ASIN hoặc visible Record ID.

- **Qualified Ideas:** số record MRND IDEA có `Date Pickup` trong tháng.
- **Listing Done:** số record TOTAL ASINs có `Listing Done Date` trong tháng.
- **Custom Check Done:** số record TOTAL ASINs có `Custom Check Done Date` trong
  tháng.
- **Ads Tested:** số record TOTAL ASINs có `Testing Start Date` trong tháng.
- **Listing Lead Time:** Average trực tiếp cột `Listing Lead Time` của các record
  có Listing Done Date trong tháng.
- **Custom Lead Time:** Average trực tiếp cột `Custom Lead Time` của các record
  có Custom Check Done Date trong tháng. Tạm dùng Custom Check Done Date cho đến
  khi Custom Done Date đủ dữ liệu.
- Tạm thời chưa tính PD Custom Check Time và Ads Lead Time.

## 6. Ngưỡng chung

- Validated Record và Sold Record: Record ID có tổng Units `>= 10`.
- Winner Record: Record ID có Revenue tháng `>= $5,000`.
- Validation/New cohort: từ ngày 20 của tháng trước đến ngày cuối tháng đang
  chọn, dùng ngày lịch Lark của đúng stage.

## 7. KPI theo vị trí

### Team Idea

- Qualified Ideas: Pickup Date trong tháng, weight 40%.
- Validated Rate: Validated Records / Cohort Records, weight 30%.
- Revenue: toàn bộ Revenue tháng của portfolio do nhân sự Idea sở hữu,
  weight 30%.

### Team Product

- Qualified ASINs: ASIN có Custom Check Done Date trong tháng, weight 30%.
- Sold Rate: Sold Records / Cohort Records của Listing Done cohort, weight 20%.
- New Revenue: Revenue tháng từ sản phẩm thuộc Listing Done cohort, weight 30%.
- Portfolio Revenue: toàn bộ Revenue tháng của portfolio Managed By,
  weight 20%.
- Listing Lead Days: average Listing Lead Time của ASIN hoàn thành Listing trong
  tháng.

### Team Product Support

- Qualified Custom ASINs: ASIN có Custom Check Done Date trong tháng,
  weight 80%.
- Asset Points: tài nguyên tạo/cập nhật trong tháng, weight 20%.
- Matrix điểm: New Multi-layer = 10; New 1-layer = 5; Update Multi-layer Full =
  10; Update Multi-layer Partial = 5.
- Không tính Reuse hoặc Duplicate Custom.

### Team Ads

- New Winner Created: Record ID lần đầu đạt ngưỡng Winner trong phạm vi quản lý,
  weight 20%.
- ACOS portfolio tháng, weight 25%.
- Portfolio Revenue tháng, weight 20%.
- New Revenue từ Testing Start cohort, weight 35%.
- Ads Report phải map `Ads Report ASIN -> TOTAL ASIN ASIN -> Record ID/Ads By`.
- `Ads Spend = tổng Spend`; `Ads Sales = tổng Sales`;
  `ACOS = Ads Spend / Ads Sales`.
- Hiện chưa có Ads Report theo ASIN trong snapshot, vì vậy ACOS nhân sự vẫn N/A.

## 8. Snapshot và cập nhật dữ liệu

### Order snapshot

- Dashboard luôn đọc snapshot tổng hợp gần nhất.
- Snapshot được tạo lại sau khi pipeline ingest report mới.
- Metadata ghi rõ source report update và timezone Los Angeles.

### Lark snapshot

- Một lần refresh lưu đồng bộ các frame `total`, `workflow`, `workflow_ideas`,
  `ideas` và `cliparts` cùng metadata.
- Mở dashboard bình thường chỉ đọc snapshot đã lưu.
- Chỉ gọi Lark API khi bấm `Cập nhật snapshot Lark · tất cả bảng`, hoặc khi chưa
  từng có snapshot hợp lệ.
- Nếu refresh lỗi, dashboard tiếp tục dùng snapshot thành công gần nhất.
- Snapshot Lark nằm trong `snapshot/lark/` và đang bị gitignore vì chứa dữ liệu
  sản phẩm/nhân sự nội bộ. Không push snapshot này nếu chưa xác nhận repository
  và chính sách bảo mật phù hợp.

## 9. Bảo mật và repository

- `.streamlit/secrets.toml` luôn bị gitignore.
- Chỉ commit `.streamlit/secrets.toml.example` với placeholder.
- Không commit App ID, App Secret, Base token, table IDs thật hoặc Team KPI
  password.
- Không commit raw reports, SQLite database hoặc thông tin khách hàng.
- Snapshot Order dạng aggregate được phép đưa vào repository theo thiết kế hiện
  tại; snapshot Lark thì không.

## 10. Trạng thái dữ liệu kiểm tra gần nhất — 07/2026

- Order Revenue: `$180,517.89`; Tổng quan và Team KPI cùng hiển thị `$180,518`.
- Orders tổng hợp: 4,429.
- Units: 4,912.
- Active ASINs: 897.
- Qualified Ideas: 122.
- Listing Done: 289.
- Custom Check Done: 314.
- Ads Tested: 48.
- Listing Lead Time: 8.08 ngày.
- Custom Lead Time: 13.35 ngày.
- Lark snapshot: TOTAL ASIN 15,612 records; MRND IDEA 297 records; CLIPARTS
  128 records.
- Automated tests: 18 tests passing tại thời điểm cập nhật tài liệu.

## 11. Điểm còn mở cần xác nhận hoặc bổ sung

- Cần Ads Report theo ASIN để thay dữ liệu Ads demo và tính Spend, Sales, ACOS
  theo Ads By.
- Cần xác nhận có được phép đưa snapshot Lark nội bộ lên Git hay tiếp tục chỉ lưu
  local/runtime.
- Khi `Custom Done Date` đủ dữ liệu, đổi filter Custom Lead Time từ Custom Check
  Done Date sang Custom Done Date.
- PD Custom Check Time và Ads Lead Time đang chủ động để trống.
