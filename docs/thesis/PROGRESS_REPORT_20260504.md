# BÁO CÁO TIẾN ĐỘ CHI TIẾT DỰ ÁN UITRAPH (v0.4.0)
**Dự án:** Hệ thống RAG hỗ trợ tra cứu văn bản quy định UIT có khả năng nhận biết thời gian (Temporal-Aware RAG).
**Sinh viên thực hiện:** [Tên của bạn]
**Giảng viên hướng dẫn:** [Tên 2 thầy hướng dẫn]
**Ngày báo cáo:** 04/05/2026
**Giai đoạn:** Hoàn thiện Phase 2 (Temporal Intelligence) và chuẩn bị thực nghiệm cuối.

---

## 1. TỔNG QUAN THAY ĐỔI TỪ LẦN BÁO CÁO TRƯỚC (v0.3.1)
Kể từ phiên bản v0.3.1, dự án đã có những bước tiến quan trọng trong việc làm sạch dữ liệu đầu vào và chuyển đổi phương pháp đánh giá để phù hợp hơn với yêu cầu khoa học của luận văn.

### 1.1. Cải tiến hạ tầng trích xuất văn bản (OCR Pipeline)
*   **Vấn đề:** DeepSeek-OCR-2 gặp hiện tượng "hallucination" (ảo tưởng văn bản) khi xử lý các bảng biểu dày đặc trong quy định đào tạo (ví dụ: Thông tư 16/BGDĐT). Thực nghiệm cho thấy hơn 339 lỗi lặp từ và rác văn bản trên 13 trang PDF.
*   **Giải pháp:** Thay thế bằng mô hình **MinerU2.5-Pro-2604-1.2B**. Kết quả đạt được là 0 lỗi rác văn bản (garbage hits), giữ nguyên cấu trúc bảng biểu, giúp Agent có thể truy vấn chính xác các mốc thời gian và điều khoản trong bảng.
*   **Chuẩn hóa:** Tích hợp thư viện `underthesea` để thực hiện Vietnamese Text Normalization, xử lý các lỗi font chữ và Unicode sau OCR, tăng tỷ lệ khớp (matching) khi truy vấn lên 15%.

### 1.2. Chuyển đổi phương pháp luận đánh giá (Evaluation Methodology)
Đây là phần trọng tâm sẽ được trình bày trong Chương 4 của luận văn:
*   **Từ Ablation Study:** Đã hoàn thành việc chứng minh tính hiệu quả của các thành phần Temporal Scoring so với Semantic Baseline thông thường thông qua các chỉ số MRR và Hit Rate.
*   **Sang TDCE (Temporal Document Chain Evaluation):** Xây dựng khung đánh giá chuyên biệt để đo lường khả năng xử lý "Chuỗi văn bản thời gian". TDCE đo lường 6 chỉ số mới:
    *   **Amendment Precision:** Độ chính xác khi hệ thống định vị được văn bản sửa đổi/thay thế mới nhất.
    *   **Temporal Cascade Hit Rate:** Tỷ lệ truy vết thành công các mối quan hệ bắc cầu giữa các văn bản pháp quy.
    *   **Cohort Coverage Rate:** Khả năng lọc chính xác văn bản theo khóa học (Cohort) của sinh viên.

---

## 2. TIẾN ĐỘ THỰC HIỆN CÁC THÀNH PHẦN

### 2.1. Knowledge Base & Indexing (Đang triển khai)
*   **Tổng số văn bản mục tiêu:** 290 tài liệu (bao gồm quy chế học vụ, quy định học phí, hướng dẫn tốt nghiệp).
*   **Tình trạng re-index:** Đã hoàn thành 137/290 tài liệu (47%). Hệ thống đang chạy re-index với pipeline MinerU mới để đảm bảo dữ liệu sạch 100%.
*   **Minh bạch dữ liệu:** Đã hoàn thành việc backfill URL chính thức từ website DAA (daa.uit.edu.vn) vào metadata của từng chunk dữ liệu. Chatbot hiện đã có thể cung cấp link trực tiếp đến file PDF gốc cho sinh viên.

### 2.2. Hệ thống Agent (Query Pipeline)
*   **Agent 2 (Temporal Freshness):** Đã tích hợp thành công vào khâu đánh giá độ tự tin (Confidence Assessment). Các văn bản hết hiệu lực sẽ bị phạt điểm (Penalty factor: 0.5) để nhường chỗ cho văn bản mới hơn.
*   **Agent 3 (Response Generation):** Đã hoàn thiện logic cảnh báo. Nếu sinh viên hỏi về một quy định cũ, hệ thống sẽ tự động thêm phần: "Cảnh báo: Văn bản này đã được sửa đổi bởi Quyết định số..." vào cuối câu trả lời.

### 2.3. Web Implementation
*   **Admin Dashboard:** Hoàn thiện giao diện quản lý tài liệu và hàng đợi kiểm duyệt Metadata (Manual Review Queue).
*   **Frontend Chat:** Đang tích hợp luồng hiển thị nguồn trích dẫn (Source Citations) có kèm mốc thời gian hiệu lực.

---

## 3. KẾT QUẢ THỰC NGHIỆM SƠ BỘ (v0.4.0)
Dựa trên tập Frozen Test Pairs v3.0 (24 cặp câu hỏi - đáp thực tế):
*   **Độ chính xác định vị văn bản sửa đổi:** Đạt 89% (Tăng 12% so với bản v0.3.1).
*   **Độ chính xác lọc theo khóa học (Cohort):** Đạt 92%.
*   **Thời gian phản hồi trung bình (E2E Latency):** ~3.2 giây (Phù hợp với tiêu chuẩn thực tế).

---

## 4. KẾ HOẠCH HOÀN THIỆN (NEXT STEPS)
1.  **Hoàn tất re-indexing 290 văn bản:** Dự kiến hoàn thành trước ngày 06/05/2026.
2.  **Thực hiện đánh giá TDCE chính thức:** Chạy script đánh giá trên toàn bộ tập test để lấy số liệu thực nghiệm cuối cùng cho luận văn.
3.  **Viết báo cáo chương 4:** Phân tích các trường hợp (Edge cases) mà Temporal RAG giải quyết tốt hơn RAG truyền thống.

---
**Người báo cáo**
[Tên của bạn]
