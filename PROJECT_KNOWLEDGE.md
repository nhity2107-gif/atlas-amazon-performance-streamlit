# Atlas Amazon Performance — Project Knowledge

Tài liệu này là nguồn quy ước chính thức của dashboard. Khi thay đổi logic,
phải cập nhật cả code, test và tài liệu này.

## 1. Mục tiêu và phạm vi

- Dashboard Streamlit nội bộ cho Wrappiness và Pawsionate.
- Bốn khu vực chính: Tổng quan, Sản phẩm, Ads performance và Team KPI.
- Dữ liệu Order không cần upload lại mỗi lần truy cập.
- Không lưu file report gốc, order-level data hay thông tin khách hàng trong
  repository/dashboard snapshot.
- Team KPI được mở công khai cùng các tab còn lại, không có màn hình mật khẩu.

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
- Order/Revenue và phạm vi Ads report dùng kỳ báo cáo theo
  `America/Los_Angeles`; `report_as_of_date` chỉ thuộc hệ thời gian Amazon.
- KPI workflow Lark độc lập với Order: ngày cuối kỳ là ngày lịch Việt Nam của lần
  refresh snapshot Lark mới nhất. Local Update Tool refresh đủ TOTAL
  ASIN/MRND IDEA/CLIPARTS mỗi lần cập nhật hằng ngày; nếu API lỗi phải cảnh báo
  rõ khi fallback snapshot cũ và dùng ngày cập nhật của snapshot đó.
- Nếu Streamlit Cloud đồng thời có snapshot Lark runtime cũ và snapshot mã hóa
  đã publish, luôn chọn snapshot có `updated_at` mới hơn; không ưu tiên mù quáng
  bản local vì có thể khiến KPI dừng ở ngày cũ.
- Không dùng ngày Lark để lọc Revenue và không dùng Purchase Time để lọc output
  workflow của Lark.

## 3. Order Report và Revenue

- Hai store: Wrappiness và Pawsionate.
- Chỉ dùng currency USD.
- Loại toàn bộ dòng `Cancelled`.
- `Revenue = Item Price + Shipping Price`.
- Tab Tổng quan tách Revenue theo `Fulfill By` từ TOTAL ASIN. Ưu tiên map trực
  tiếp ASIN; nếu ASIN Order chưa khớp thì fallback qua `record_id_hint` để lấy
  Fulfill By của Record ID. FBA + FBM phải bằng Net Revenue.
- Daily Performance trên tab Tổng quan hiển thị hai biểu đồ và hai bảng dữ liệu
  riêng cho FBM và FBA. Cả hai dùng Purchase Date Los Angeles và cùng logic
  mapping `Fulfill By` như các thẻ Revenue; các ngày không phát sinh được giữ
  với Revenue/Quantity bằng 0 để hai chuỗi thời gian thẳng hàng.
- Daily import upsert theo `order-item-id`.
- Weekly/monthly import thay thế toàn bộ store + khoảng ngày Los Angeles được
  chỉ định trước khi insert report mới.
- Daily live chuẩn dùng scope `mtd`: report chứa ngày 01 của tháng đến ngày
  input; pipeline tự thay thế đúng khoảng này để phản ánh late order, cancelled
  và không cộng trùng.
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

### FBM Revenue Target

- Nguồn target chỉ dùng sheet `Revenue Forecast Q1&2 - 2026` trong workbook
  forecast và ba cột theo ngày: `Date`, `DAILY REV 2025`, `FORECAST 2026`;
  không dùng `2026 Forecast Rev Monthly`, `Output Plan`, `Estimated Margin` hay
  bất kỳ sheet nào khác.
- Target hiện là tổng FBM của `All Stores`, chưa phân bổ cho Wrappiness hoặc
  Pawsionate. Khi chọn riêng một store, dashboard không tự chia target.
- Actual là FBM Revenue của Order snapshot trong Purchase Month Los Angeles.
- `Forecast MTD 2026` là tổng các giá trị `FORECAST 2026` cụ thể từ ngày 01 đến
  `report_as_of_date`; tuyệt đối không chia đều target tháng cho từng ngày.
- `Revenue 2025 MTD` là tổng `DAILY REV 2025` trên cùng số ngày. Dashboard hiển
  thị `Actual vs Forecast = Actual 2026 / Forecast 2026 - 1` và
  `YoY MTD = Actual 2026 / Revenue 2025`. YoY là chỉ số so sánh: `100%` nghĩa
  là bằng năm trước, `163.86%` nghĩa là doanh thu bằng 163.86% năm trước
  (tương đương tăng trưởng `+63.86%`).
- Actual 2026 lấy từ Order snapshot FBM theo Purchase Date Los Angeles. Ngày
  chốt so sánh lấy từ `report_as_of_date`, không lấy Purchase Date mới nhất.
  Tháng đã kết thúc dùng toàn bộ các dòng ngày của tháng.
- Local Update Tool chỉ yêu cầu upload workbook khi target thay đổi. Dữ liệu đã
  chuẩn hóa thành 365 dòng ngày tại `snapshot/fbm_target.csv` kèm metadata và được tái sử
  dụng cho những lần cập nhật Order tiếp theo.

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

Cách tính phải giống Lark Metrics theo từng loại KPI. Qualified Ideas lọc theo
ngày rồi đếm **unique Record ID**; các output ở TOTAL ASIN dùng `Record count`
của dòng ASIN sau khi lọc ngày.

- **Qualified Ideas:** số unique Record ID trong MRND IDEA có ít nhất một
  `Date Pickup` trong tháng.
- Toàn bộ MRND IDEA được xem là FBM theo quy ước nghiệp vụ. Qualified Ideas và
  Pickup Cohort không yêu cầu Record ID đã xuất hiện trong TOTAL ASIN; chỉ các
  chỉ số Revenue/Units mới cần mapping ASIN FBM.
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
- Revenue: tổng Revenue tháng của toàn bộ ASIN thuộc ownership của nhân sự Idea,
  weight 30%.

### Team Product

- Qualified ASINs: ASIN có Custom Check Done Date trong tháng, weight 30%.
- Sold Rate: Sold Records / Cohort Records của Listing Done cohort, weight 20%.
- New Revenue: Revenue tháng chỉ từ các ASIN thuộc Managed By có chính
  `Custom Check Done Date` trong cohort ngày 20 tháng trước đến cuối tháng,
  weight 30%.
- Portfolio Revenue: tổng Revenue tháng của toàn bộ ASIN thuộc ownership
  Managed By,
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
- Portfolio Revenue: tổng Revenue trong Purchase Month của toàn bộ ASIN thuộc
  Ads ownership, weight 20%.
- New Revenue: tổng Revenue trong Purchase Month chỉ từ các ASIN có chính
  `Custom Check Done Date` trong cohort ngày 20 tháng trước đến cuối tháng hiện
  tại, phân bổ theo Ads revenue ownership, weight 35%.
- Ads Report phải map `Ads Report ASIN -> TOTAL ASIN ASIN -> Record ID/Ads By`.
- `Ads Spend = tổng Spend`; `Ads Sales = tổng Sales`;
  `ACOS = Ads Spend / Ads Sales`.
- `TACOS = Ads Spend / Portfolio Revenue` chỉ áp dụng cho hàng có ownership
  Revenue. Trong trang Ads tổng, FBA vẫn được đối soát riêng; trong Team KPI,
  toàn bộ Order Revenue/Units và Ads Spend/Sales/Orders FBA bị loại.
  `Nhi-Support`, `Linh`, `Hieu` và `Ha` là các hàng Ads thực thi, không nhận
  Revenue và TACOS phải là `N/A`.
- Wrappiness dùng đủ ba workbook SP/SB/SD. SP map trực tiếp bằng `Advertised
  ASIN`; SB/SD map bằng ASIN đầu tiên trong `Campaign Name`, vì tổng campaign
  collection chỉ được phân bổ một lần. Mọi campaign có chữ `Support` (không
  phân biệt hoa/thường, kể cả viết liền như `NhiSupport`) được gán trực tiếp
  sang hàng `Nhi-Support`, không cộng thêm report support cũ.
- Marker campaign có `LINH`, `HIEU`, `HA` (kể cả viết liền như `LINHAMZ`,
  `HIEUAMZ`, `HIEUMRND`, `HAMRND`) được gán lần lượt sang hàng
  thực thi `Linh`, `Hieu`, `Ha`; Spend/Sales/Orders của các campaign này bị loại
  khỏi Ads By gốc nhưng tổng report phải được bảo toàn.
- FBA phải lấy từ TOTAL ASIN `Fulfill By = FBA`, không suy ra từ hậu tố product
  trong Ads report. Ownership FBA lấy từ `Custom By`: `Trương Ý Nhi` →
  `Nhi-FBA`; `Phương Linh/MRnD` → `Linh-FBA`. Ownership FBA được ưu tiên hơn
  marker Support/LINH/HIEU/HA trong tên campaign để mọi Ads FBA luôn nằm đúng
  một trong hai hàng FBA và không lọt vào KPI FBM.
- Hai correction đã xác nhận trong TOTAL ASIN: `B0F1XZT333` và `B0F1XPZ1JX`
  đang bị mark nhầm `FBM` nhưng phải được xử lý là `FBA`. Override này áp dụng
  đồng nhất cho phân bổ Ads, TACOS và Revenue FBA/FBM cho đến khi Lark được sửa.
- Việc phân bổ phải bảo toàn tổng Spend, Sales và Orders của cả ba report.
- Tab Ads Performance hiển thị riêng FBM và FBA cho Spend, Sales, Orders và ACOS;
  tổng hai nhóm phải khớp tuyệt đối với toàn bộ Ads report. Bên dưới có bảng
  FBA ownership riêng gồm đủ `Nhi-FBA` và `Linh-FBA` (kể cả khi một hàng bằng 0).

### Revenue milestone theo ownership

- Bảng Idea, Product và Ads đều hiển thị thêm số unique Record ID đạt Revenue
  tháng `>= $1,000`, `>= $3,000`, `>= $5,000`, `>= $10,000`, `>= $15,000`
  và `>= $20,000`.
- Milestone dùng Purchase Month của Order snapshot đã đổi sang Los Angeles.
- Đây là chỉ số toàn portfolio ownership, không giới hạn Pickup/Listing/Testing
  cohort. Revenue của toàn bộ ASIN cùng Record ID được cộng trước khi so ngưỡng.
- Idea dùng `Idea By`; Product dùng `Managed By`; Ads dùng `Ads By`, chỉ trên
  các ASIN `Fulfill By = FBM`. FBA không tham gia KPI nhân sự. Các hàng thực thi `Nhi-Support`,
  `Linh`, `Hieu`, `Ha` không có ownership Order Revenue nên milestone bằng 0.

## 8. Snapshot và cập nhật dữ liệu

### Raw input chuẩn

- Cấu trúc bắt buộc: `data/input/<YYYY-MM>/<store>/{orders,ads}`.
- Store slug chỉ dùng `wrappiness` hoặc `pawsionate`.
- Tên file dùng `YYYY-MM__<store>__<dataset>__<scope>.<ext>`; tháng là kỳ dữ
  liệu, không phải ngày download.
- Order live chuẩn: `YYYY-MM__<store>__order__mtd.txt`.
- Ads chuẩn: `sp-advertised-product`, `sb-campaign`, `sd-campaign`.
- Raw input và `manifest.csv` từng tháng chỉ lưu local, bị gitignore. Manifest
  ghi trạng thái, dung lượng và SHA-256 để phát hiện việc thay file nguồn.
- Chạy `scripts/validate_input_layout.py` trước pipeline; Wrappiness yêu cầu đủ
  ba Ads report. Pawsionate không phát sinh SB/SD nên hai nguồn này có trạng
  thái `not-applicable`; SP dùng workbook Advertised Product đầy đủ.

### Order snapshot

- Dashboard luôn đọc snapshot tổng hợp gần nhất.
- Snapshot được tạo lại sau khi pipeline ingest report mới.
- Snapshot xuất từ toàn bộ SQLite database để giữ lịch sử nhiều tháng; toàn bộ
  dashboard dùng chung bộ chọn tháng ở sidebar.
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

### Ads snapshot

- Snapshot Ads schema v2 nằm trong `snapshot/ads/` và bị gitignore; mỗi dòng có
  `Month` và `Store`, import mới chỉ thay đúng cặp Store/Month tương ứng.
- Wrappiness sinh từ đủ SP/SB/SD. Pawsionate sinh từ workbook SP
  Advertised Product; SB/SD là `not-applicable`, vì store không phát sinh hai
  loại Ads này.
- Mọi dòng phát sinh Spend/Sales/Orders phải trích được ASIN và map được Ads By
  trong TOTAL ASIN. Campaign nhiều ASIN dùng ASIN đầu tiên làm primary mapping
  và không nhân campaign total theo số ASIN.
- Dashboard chỉ dùng snapshot khi month/store khớp lựa chọn hiện tại. All Stores
  cộng các store đã import rồi tính lại ACOS từ tổng Spend/Sales.
- Order được import hằng ngày theo month-to-date cho cả hai store. Ads chỉ import
  một lần vào cuối tháng, đủ SP/SB/SD cho cả hai store và thay thế cùng Store + Month;
  metadata lưu `period_start`, `period_end` để dashboard hiển thị ngày cập nhật.
- Local Update Tool chạy riêng trên `127.0.0.1:8502`; mặc định chỉ nhận 2 Order.
  Tùy chọn Ads cuối tháng mới hiển thị và bắt buộc 6 Ads report. Vì GitHub public, chỉ
  `snapshot/published_ads_snapshot.enc` đã mã hóa Fernet được phép push;
  Streamlit giải mã bằng `DASHBOARD_DATA_KEY` trong Secrets. Tên cũ
  `PUBLISHED_SNAPSHOT_KEY` vẫn được hỗ trợ để tương thích ngược.

## 9. Bảo mật và repository

- `.streamlit/secrets.toml` luôn bị gitignore.
- Chỉ commit `.streamlit/secrets.toml.example` với placeholder.
- Không commit App ID, App Secret, Base token hoặc table IDs thật.
- Không commit raw reports, SQLite database hoặc thông tin khách hàng.
- Snapshot Order dạng aggregate được phép đưa vào repository theo thiết kế hiện
  tại; snapshot Lark thì không.

## 10. Trạng thái dữ liệu kiểm tra gần nhất — 07/2026

- Full Order Revenue: `$181,763.46` (`Wrappiness $180,821.46` + `Pawsionate
  $942.00`); Tổng quan và Team KPI phải dùng cùng snapshot này.
- Orders tổng hợp: 4,454.
- Units: 4,945.
- Active ASINs: 903; snapshot có 2,705 dòng tổng hợp theo Store/Date/ASIN.
- FBA Revenue sau correction: `$4,805.60`, 268 orders, 289 units, 11 ASINs.
- FBM Revenue sau correction: `$176,957.86`, 4,186 orders, 4,656 units,
  892 ASINs. FBA + FBM = `$181,763.46` Net Revenue.
- Qualified Ideas: 117 unique Record ID (122 dòng MRND IDEA trong kỳ, gồm 5
  dòng trùng Record ID).
- Listing Done: 289.
- Custom Check Done: 314.
- Ads Tested: 48.
- Listing Lead Time: 8.08 ngày.
- Custom Lead Time: 13.35 ngày.
- KPI nhân sự đã đối soát: Gary có 117 Qualified Ideas và 6/119 Validated
  Records; Phương Linh có 115 Qualified ASINs và 17/138 Sold Records;
  Sammie/Nhật Hạ có 196 Qualified ASINs và 20/195 Sold Records. Validated/Sold
  đều gộp Units của toàn bộ ASIN theo Record ID trước khi áp ngưỡng `>=10`;
  một Record ID có nhiều dòng ngày chỉ cần ít nhất một ngày nằm trong cohort.
- Số Record ID đạt tổng Units `>=10` trên toàn portfolio: Gary 6, Trương Ý Nhi
  3; Phương Linh 50; Sammie/Nhật Hạ 40. Trong cohort 20/06–31/07, số KPI lần
  lượt là Gary 6/119, Phương Linh 17/138 và Sammie/Nhật Hạ 20/195.
- Wrappiness SP: 848 ASIN phát sinh; Spend `$35,889.43`; Sales `$98,274.42`;
  Orders `2,946`; weighted ACOS `36.52%`.
- Wrappiness SB: 114 primary ASIN phát sinh; Spend `$2,931.99`; Sales
  `$8,380.83`; Orders `294`; weighted ACOS `34.98%`. SD không phát sinh.
- Tổng Wrappiness SP+SB+SD: Spend `$38,821.42`; Sales `$106,655.25`; Orders
  `3,240`; weighted ACOS `36.40%`.
- Nhi-Support: 25 ASIN; 46 campaign; Spend `$651.38`; Sales `$1,224.86`;
  ACOS `53.18%`.
- Hàng thực thi sau khi đọc marker campaign trên cả hai store: `Linh` 92 campaign /
  Spend `$391.79` / Sales `$450.14`; `Hieu` 69 campaign / Spend `$254.23` /
  Sales `$100.87`; `Ha` 91 campaign / Spend `$321.26` / Sales `$336.54`.
- Lark snapshot: TOTAL ASIN 15,611 records; MRND IDEA 297 records; CLIPARTS
  128 records.
- Wrappiness FBA trong đủ ba report sau khi ưu tiên marker nhân sự: `Nhi-FBA`
  7 ASIN / Spend `$873.25` / Sales `$2,521.24`. Campaign FBA trước đây của
  `B0F32KP4K3` nay mang marker `LINH`, nên được ưu tiên sang hàng thực thi `Linh`
  và không còn phát sinh `Linh-FBA`.
- Pawsionate Ads report: 8 ASIN / Spend `$156.19` / Sales `$342.68`; có 1
  `Nhi-FBA` với Spend `$1.80`, chưa có Sales nên ACOS `N/A`.
- Ads New Revenue theo từng ASIN có Custom Check Done trong cohort 20/06–31/07
  trên All Stores: `Danni/Quỳnh Như/MRnD` 258 ASIN / `$46,244.66`;
  `Kaythlyn/Phương Trinh/MRnD` 213 ASIN / `$10,426.70`;
  `Trương Ý Nhi` 49 ASIN / `$6,160.41`.
- Tổng New ASIN trong cohort 20/06–31/07 có Product ownership: `520`; có Ads
  ownership: `520`. Hai tổng đếm unique ASIN, không đếm Record ID.
- Automated tests: 30 tests passing tại thời điểm cập nhật tài liệu.

## 11. Điểm còn mở cần xác nhận hoặc bổ sung

- Ads snapshot tháng 07/2026 đã có đủ Wrappiness và Pawsionate.
- Cần xác nhận có được phép đưa snapshot Lark nội bộ lên Git hay tiếp tục chỉ lưu
  local/runtime.
- Khi `Custom Done Date` đủ dữ liệu, đổi filter Custom Lead Time từ Custom Check
  Done Date sang Custom Done Date.
- PD Custom Check Time và Ads Lead Time đang chủ động để trống.
