# Hành trình thử local model thay Claude — số liệu thật, không làm tròn

Ghi lại NGẮN GỌN vì sao `matching_agent` hiện có 3 chế độ (`anthropic` / `ollama` /
`ollama_ensemble`), dựa trên số liệu thu được thật qua từng bước thử, không phải quyết định lý
thuyết. Mục đích: đọc code sau này (kể cả 6 tháng nữa) hiểu được TẠI SAO kiến trúc trông như vậy.

## 0. Vì sao bắt đầu thử

Claude API trả phí theo token — với 1 personal tool chạy hàng ngày qua ITviec (nhiều job/ngày),
chi phí tuy nhỏ nhưng cộng dồn không cần thiết cho 1 tác vụ chấm điểm không đòi hỏi reasoning quá
sâu. Ollama chạy local, miễn phí hoàn toàn, đáng thử trước khi chấp nhận trả phí lâu dài.

## 1. Thử 1 model đơn (qwen2.5:7b)

Chạy test case tham khảo gốc (`matching_v1.md`, CV 3 năm React không TypeScript thành thạo, kỳ
vọng `score` 65-80/`good_match`) 3 lần: **score=65, verdict=good_match, ổn định cả 3 lần** — qua
được bài test tối thiểu.

Nhưng 2 phát hiện đáng chú ý ngay từ vòng đầu:

- **JSON không hợp lệ ngay lần đầu** — phải qua fallback (strip code fence / cắt từ `{` tới `}`)
  ở cả 3 lần chạy. Không lỗi nghiêm trọng (đã có fallback từ Phase 0) nhưng đáng lưu ý.
- **"Floor-clustering"** — mọi case chạy đúng dải đều rơi ĐÚNG ĐÁY của dải kỳ vọng (65/65-80,
  85/85-100), không phân bố tự nhiên trong dải. Model không phân biệt "vừa đủ" và "rất phù hợp"
  trong cùng 1 verdict.

Mở rộng thêm 3 test case để phủ đủ 4 dải điểm (`prompts/reference_cases.py`), chạy 3 lần/case:

| Case | Kỳ vọng | Kết quả (3 lần) |
|---|---|---|
| good_match (gốc) | 65-80, `good_match` | 65, `good_match` — ổn định, đúng |
| strong_match (A) | 85-100, `strong_match` | 85, `strong_match` — ổn định, đúng |
| weak_match (B) | 0-39, `weak_match` | 45, verdict dao động `weak_match`→`partial_match` (2/3 lần) — **sai** |
| partial_match (C) | 40-64, `partial_match` | 65, `good_match` — ổn định — **sai** |

Sửa JSON bằng **structured output thật** (`format=<json_schema>` của Ollama, ép model chỉ sinh
token khớp schema) — JSON hợp lệ ngay lần đầu **100% (12/12 lần chạy)** sau đó, không cần fallback
nữa. Nhưng 2 case B/C vẫn sai — đây không phải lỗi parse, là lỗi **calibration**: model thổi phồng
điểm khi CV có nice-to-have nổi bật dù thiếu must-have thật (Case C), và cho điểm quá cao với ứng
viên hoàn toàn không liên quan lĩnh vực (Case B).

## 2. Thử few-shot — sửa được 2 case, làm hỏng 2 case khác

Thêm 2 ví dụ few-shot vào cuối System Prompt (`matching_v1_ollama.md`), minh hoạ đúng 2 ranh giới
bị sai ở bước 1. Kết quả (3 lần/case):

| Case | Trước few-shot | Sau few-shot |
|---|---|---|
| good_match (gốc) | 65, `good_match` — đúng | **50, `partial_match`** — sai, hồi quy |
| strong_match (A) | 85, `strong_match` — đúng | **75, `good_match`** — sai, hồi quy |
| weak_match (B) | 45, dao động — sai | **20, `weak_match`** — đúng, ổn định |
| partial_match (C) | 65, `good_match` — sai | **50, `partial_match`** — đúng, ổn định |

2/4 sửa được, nhưng 2/4 đang đúng bị hỏng. Nghiêm trọng hơn số điểm: ở case good_match (gốc), CV
thực tế có ĐỦ 3 năm kinh nghiệm React đúng yêu cầu (không thiếu gì) — nhưng reasoning sau few-shot
lại viết *"thiếu 2 năm kinh nghiệm ReactJS so với yêu cầu 3+ năm"*, một con số **bịa ra, không có
trong input**, giống hệt cách diễn đạt trong ví dụ few-shot số 2 (case đó thật sự thiếu 2 năm).
Model có dấu hiệu "bắt chước" chi tiết cụ thể trong ví dụ thay vì học đúng quy tắc tổng quát —
không dùng file này nữa, giữ lại làm tham khảo kèm cảnh báo ở đầu file.

## 3. Thử ensemble 2 model — vẫn không sửa được, nhưng tìm ra tín hiệu đúng hơn

Chạy song song qwen2.5:7b + llama3.1:8b (kiến trúc khác hẳn nhau, tránh 2 model cùng họ mắc chung
lỗi), CẢ HAI dùng `matching_v1.md` gốc (không few-shot — để bất đồng phản ánh đúng khác biệt
reasoning, không phải do prompt khác nhau). Ban đầu: đồng thuận → tin dùng, luôn lấy điểm model
THẤP hơn (thận trọng hơn). Kết quả (3 lần/case):

| Case | qwen2.5:7b | llama3.1:8b | Đồng thuận? | Kết quả (lấy điểm thấp hơn) |
|---|---|---|---|---|
| good_match (gốc) | 65, `good_match` | 65, `good_match` | Đồng thuận | 65, `good_match` — đúng |
| strong_match (A) | 85, `strong_match` | 90, `strong_match` | Đồng thuận | 85, `strong_match` — đúng |
| weak_match (B) | 45, `weak_match` | 40, `partial_match` | **Bất đồng** | 40, `partial_match` — vẫn sai |
| partial_match (C) | 65, `good_match` | 85, `strong_match` | **Bất đồng** | 65, `good_match` — vẫn sai |

"Lấy điểm thấp hơn" không sửa được Case B/C — vì cả 2 model, độc lập, đều mắc CÙNG một thiên lệch
theo CÙNG một hướng (llama ở Case C còn lạc quan hơn cả qwen: 85 so với 65). Nhưng có 1 tín hiệu
nổi bật: **đồng thuận/bất đồng khớp hoàn hảo với đúng/sai trong toàn bộ 4 case** — 2 case đồng
thuận đều đúng, 2 case bất đồng đều sai. Đây là tín hiệu mạnh hơn hẳn bản thân con số "điểm thấp
hơn".

## 4. Thiết kế cuối — không tự chọn khi bất đồng

Đổi reconciliation: **đồng thuận** (cùng verdict) → giữ nguyên logic cũ, lấy toàn bộ output của
model điểm thấp hơn. **Bất đồng** (khác verdict, bất kỳ mức nào kể cả 2 dải liền kề như Case C) →
KHÔNG tự chọn 1 bên, KHÔNG lấy trung bình — đánh dấu `needs_review`, lưu đủ cả 2 kết quả để người
dùng tự đọc và tự quyết định (`GET /api/jobs/{id}/agent-runs`). Không escalate lên Claude — giữ
$0 hoàn toàn cho chế độ này.

## 5. Bài học

Model nhỏ (7-8B) chạy cùng 1 task có thể **chia sẻ cùng 1 thiên lệch hệ thống**, không phải nhiễu
độc lập ngẫu nhiên giữa các lần chạy hay giữa các kiến trúc khác nhau. Vì vậy:

- **Chạy lại nhiều lần cùng 1 model không tự sửa được** — bias ổn định, không phải variance (đã
  verify: mọi case đều cho cùng 1 kết quả xuyên suốt 3 lần chạy, kể cả các case sai).
- **Kiểm tra chéo bằng cách lấy trung bình/lấy điểm thấp hơn giữa 2 model KHÔNG hiệu quả** khi cả
  2 model chia sẻ cùng thiên lệch — 2 "ý kiến độc lập" hoá ra không độc lập ở đúng những case khó.
- **Đồng thuận/bất đồng mới là tín hiệu hữu ích thật sự** — không phải vì nó "sửa" được câu trả
  lời sai, mà vì nó cho biết KHI NÀO nên tin và KHI NÀO không nên tự động tin — đúng việc 1 hệ
  thống chấm điểm CV cho quyết định thật (có nên dành thời gian apply hay không) cần có.
