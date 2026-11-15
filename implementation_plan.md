# Kế Hoạch Triển Khai: Chuyển Đổi Sang Chuẩn Văn Xuôi Thuần Việt 100% (Hướng 2)

Kế hoạch này giải quyết triệt để sự mâu thuẫn giữa `defaults/glossary_rules.txt` + Code Validation (`cores/context/validation.py`, `web-client/src/services/glossary.ts`) với bộ Prompt văn phong mới, nhằm đưa toàn bộ tác phẩm *Our Journey's End* về chuẩn văn xuôi thuần Việt xuất bản (không còn ngoặc vuông `[English]` hay chú giải song ngữ `[English] (Vietnamese)` trong truyện).

---

## User Review Required

> [!IMPORTANT]
> **Điểm quyết định về phân loại Glossary:**
> Trong hệ thống hiện tại, `type` chỉ dùng để phân loại và không quyết định cách hiển thị. Thuật ngữ metadata không có `target_only=yes` hoặc `first_en=yes` vẫn bị validator yêu cầu giữ dạng canonical theo các cờ hiển thị.
> 
> Để đạt được 100% thuần Việt, có 2 phương án kỹ thuật:
> - **Phương án 1 (Sửa dữ liệu Glossary OJE):** Gắn `target_only=yes` cho các thuật ngữ cần dịch nghĩa trong [glossary.txt](file:///d:/Aiko-App-Translator-v1.2.2/truyen/OJE/glossary.txt). Giữ nguyên `type` để phân loại.
> - **Phương án 2 (Nâng cấp Hệ Thống - Khuyến nghị):** Bổ sung cờ `target_only=yes` vào [defaults/glossary_rules.txt](file:///d:/Aiko-App-Translator-v1.2.2/defaults/glossary_rules.txt) và cập nhật [validation.py](file:///d:/Aiko-App-Translator-v1.2.2/cores/context/validation.py) + [glossary.ts](file:///d:/Aiko-App-Translator-v1.2.2/web-client/src/services/glossary.ts). Khi đó thuật ngữ vẫn giữ được nhãn `type=Skill` hay `type=Place` trên giao diện, nhưng code cho phép dịch thẳng sang tiếng Việt mà không bắt giữ tiếng Anh.

---

## Proposed Changes

### 1. Hệ Thống Quy Tắc Chung (System Defaults)

#### [MODIFY] [glossary_rules.txt](file:///d:/Aiko-App-Translator-v1.2.2/defaults/glossary_rules.txt)
- Bổ sung quy tắc cho phép xuất thuần Việt trực tiếp:
  - Cho phép `target_only=yes` áp dụng cho các thuật ngữ được chỉ định dịch nghĩa thuần Việt, độc lập với `type`.
  - Làm rõ ưu tiên: Khi một tác phẩm được cấu hình theo hướng văn xuôi thuần Việt, bản dịch dùng 100% mục tiêu tiếng Việt, không chèn ngoặc vuông `[English]` hay chú giải tiếng Anh.

---

### 2. Code Validation & Web Client (Hậu dịch & Kiểm thử)

#### [MODIFY] [validation.py](file:///d:/Aiko-App-Translator-v1.2.2/cores/context/validation.py)
- Cập nhật logic `validate_glossary`:
  - Miễn trừ kiểm tra `missing_canonical` và `vietnamese_without_canonical` nếu entry có cờ `target_only=yes`.
  - Đảm bảo khi AI dịch `blood blade` thành `thanh huyết kiếm`, validator xác nhận hợp lệ thay vì báo lỗi.

#### [MODIFY] [glossary.ts](file:///d:/Aiko-App-Translator-v1.2.2/web-client/src/services/glossary.ts)
- Đồng bộ hàm `validateGlossary` phía client TypeScript tương ứng với backend Python để giao diện web không hiển thị lỗi sai lệch.

---

### 3. Dữ Liệu Thuật Ngữ OJE (Project Glossary)

#### [MODIFY] [glossary.txt](file:///d:/Aiko-App-Translator-v1.2.2/truyen/OJE/glossary.txt)
- Rà soát 640 dòng trong glossary của OJE:
  - Chuyển đổi 115 thuật ngữ kỹ năng/chiêu thức đang để `brackets=yes` (như `blood blade`, `Chain of Heart`, `Time Synchronization`, `Regeneration`...) thành dạng xuất thuần Việt (`target_only=yes`).
  - Giữ nguyên các Tên riêng nhân vật (`Lucid = Lucid | type=Name`, `Ayame = Ayame | type=Name`).
  - Đảm bảo các địa danh, tổ chức, danh hiệu được ánh xạ trực tiếp sang tiếng Việt chuẩn (`The Scattered Realms = Các Cõi Phân Tán`).

---

### 4. Đồng Bộ Bộ 5 Prompt

#### [MODIFY] [01-moi.md](file:///d:/Aiko-App-Translator-v1.2.2/truyen/OJE/01-moi.md)
#### [MODIFY] [02-moi.md](file:///d:/Aiko-App-Translator-v1.2.2/truyen/OJE/02-moi.md)
#### [MODIFY] [03-moi.md](file:///d:/Aiko-App-Translator-v1.2.2/truyen/OJE/03-moi.md)
#### [MODIFY] [04-moi.md](file:///d:/Aiko-App-Translator-v1.2.2/truyen/OJE/04-moi.md)
#### [MODIFY] [van-phong-moi.md](file:///d:/Aiko-App-Translator-v1.2.2/truyen/OJE/van-phong-moi.md)
- Nhất quán chỉ dẫn:
  - Áp dụng triệt để quy tắc dịch chuyển ngữ trực tiếp theo Glossary.
  - Xóa bỏ mọi sự mâu thuẫn giữa Prompt và Glossary Rules.
  - Duy trì các ví dụ đối chiếu TRÁNH vs NÊN để đảm bảo câu ghép mượt mà, giàu nhạc điệu.

---

## Verification Plan

### Automated Tests
1. **Chạy bộ kiểm thử Python**:
   ```powershell
   .venv\Scripts\python.exe -m unittest discover -s tests
   .venv\Scripts\python.exe -m unittest tests.test_glossary_metadata
   ```
2. **Kiểm tra thực nghiệm validate_glossary**:
   Chạy script kiểm tra với đoạn văn bản thuần Việt mẫu (không có ngoặc vuông) đối chiếu với glossary OJE mới, đảm bảo `violations == []`.

### Manual Verification
1. Chạy thử nghiệm prompt dịch (02-moi) và hiệu đính (03-moi) trên một phân đoạn có chứa nhiều chiêu thức (ví dụ Chapter 114 có `blood blade`, `Unfaithful`), xác nhận:
   - Bản dịch xuất ra 100% tiếng Việt mượt mà (`thanh huyết kiếm`, `quái thú Vô Tín`).
   - Không còn bất kỳ ngoặc vuông `[blood blade]` hay `(huyết kiếm)`.
   - Hệ thống postprocess / polish không báo lỗi và không gửi request ép sửa lại.
