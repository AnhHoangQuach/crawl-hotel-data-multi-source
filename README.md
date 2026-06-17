# crawl-traveloka

Crawl thông tin chi tiết khách sạn trên Traveloka từ một danh sách (tên + địa chỉ) trong file CSV: tên, loại hình, hạng sao, điểm/review, toạ độ, amenities, mô tả, ảnh, review/comment, và thông tin phòng (giá, bữa ăn, chính sách huỷ).

## Yêu cầu

- Python 3.10+
- Google Chrome/Chromium sẽ được Playwright tự quản lý (cài ở bước dưới)

## Cài đặt

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium       # tải browser headless cho crawl4ai
```

## Chuẩn bị input

Tạo/sửa file CSV (mẫu: `hotels.csv`) với 2 cột `name` và `address`:

```csv
name,address
Muong Thanh Luxury Phu Quoc Hotel,"Kien Giang"
THE SEA PHÚ QUỐC,"Kien Giang"
```

- `name`: tên khách sạn cần tìm.
- `address`: địa chỉ/khu vực để chọn đúng khách sạn khi có nhiều kết quả trùng tên (dùng để so khớp gần đúng, không cần chính xác 100%).
- Nếu địa chỉ có dấu phẩy, phải đặt trong dấu ngoặc kép `"..."`.

## Chạy

```bash
source venv/bin/activate
python3 main.py hotels.csv
```

Không truyền đường dẫn thì script dùng mặc định `hotels.csv` trong thư mục hiện tại.

Quá trình chạy:
1. Tự tìm và test một danh sách proxy free công khai để xoay vòng khi bị Traveloka chặn (có thể không tìm được proxy nào sống — script sẽ tự chạy trực tiếp).
2. Với mỗi khách sạn: tìm trên Traveloka, chọn kết quả khớp nhất với tên + địa chỉ đã cho, mở trang chi tiết và trích xuất dữ liệu.
3. Lưu toàn bộ kết quả vào `hotels_result.json`.

## Output

`hotels_result.json` là một mảng object, mỗi khách sạn gồm:

| Field | Ý nghĩa |
|---|---|
| `query_name`, `query_address` | input gốc từ CSV |
| `match_score` | độ khớp (0-1) giữa input và khách sạn được chọn |
| `name`, `accommodation_type`, `star_rating` | tên, loại hình, hạng sao |
| `rating_summary` | điểm đánh giá + số lượt review |
| `address`, `latitude`, `longitude` | địa chỉ và toạ độ |
| `amenities`, `facilities`, `description` | tiện ích, mô tả |
| `photos` | danh sách URL ảnh (mở lightbox lấy toàn bộ ảnh, không chỉ ảnh đại diện) |
| `reviews` | danh sách đoạn review/comment thật (tối đa ~5 trang đầu, xem `MAX_REVIEW_PAGES` trong `traveloka/config.py`) |
| `rooms` | danh sách phòng còn trống: tên phòng, loại giường, bữa ăn, giá, số phòng còn lại, chính sách huỷ |
| `detail_url`, `error` | URL trang chi tiết, lỗi nếu crawl thất bại |

## Cấu trúc project

```
main.py                  CLI entrypoint
hotels.csv                file input mẫu
traveloka/
  config.py               CSS selector + hằng số (sửa ở đây nếu Traveloka đổi UI)
  proxy.py                  fetch/validate/xoay proxy free
  matching.py                so khớp mờ (fuzzy) để chọn khách sạn gần đúng nhất
  extraction.py                trích xuất ảnh/review/phòng từ trang chi tiết
  scraper.py                    luồng Playwright: tìm kiếm -> chọn best-match -> mở tab chi tiết
```

## Giới hạn cần biết

- Dùng proxy free công khai nên độ tin cậy thấp; nếu cần ổn định hơn, đổi sang proxy trả phí trong `traveloka/proxy.py`.
- Reviews lấy tối đa `MAX_REVIEW_PAGES` trang (mặc định 5) — là mẫu lớn, không phải toàn bộ review của khách sạn có hàng trăm/nghìn review.
- `rooms` rỗng nếu khách sạn hết phòng ở ngày tìm kiếm mặc định (mai/mốt) trên Traveloka, không phải lỗi script.
- Traveloka có thể đổi cấu trúc trang bất kỳ lúc nào — nếu script không lấy được dữ liệu, kiểm tra lại các selector trong `traveloka/config.py`.
