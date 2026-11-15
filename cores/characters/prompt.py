"""Prompt construction for character analysis."""

from cores.r19 import strip_r19_terms
from cores.translation.prompts import wrap_r19_prompt


DEFAULT_TASK = """Đọc văn bản theo đúng trình tự và đối chiếu glossary cùng hồ sơ hiện có để trích xuất hoặc cập nhật hồ sơ nhân vật bằng tiếng Việt.

Trước khi viết hồ sơ, phân tích vai trò của nhân vật trong cảnh, hành động, lời thoại, người nói và người nghe, quan hệ, phe phái, mục tiêu, cảm xúc và những thay đổi xảy ra theo diễn biến. Phân biệt dữ kiện được xác nhận với suy đoán. Không dùng kiến thức ngoài văn bản và không biến điều chưa rõ thành sự thật.

Với nhân vật chuyển sinh, tráo đổi hoặc biến đổi cơ thể/giới tính, ghi riêng thân phận trước đây, cơ thể hiện tại, nhận thức bản thân, cách người khác nhìn nhận và thời điểm áp dụng. Không giản lược các trạng thái này thành một giới tính cố định.

Chỉ ghi nhân vật có thoại, hành động, quan hệ hoặc ảnh hưởng đáng kể đến cốt truyện. Bỏ qua người qua đường và NPC chỉ xuất hiện thoáng qua. Khi cập nhật nhân vật cũ, hợp nhất dữ kiện mới với dữ liệu đã có, giữ nguyên thông tin không bị văn bản mới phủ định và nêu rõ sự thay đổi theo thời điểm nếu hai dữ kiện khác nhau."""


def build_character_prompt(chapters: list, existing_md: str, glossary: str = "") -> str:
    content_blocks = [
        f"### {chapter.get('title', '')}\n{chapter.get('content', '')}"
        for chapter in chapters
        if chapter.get("content")
    ]
    full_text = strip_r19_terms("\n\n".join(content_blocks))
    glossary = strip_r19_terms(glossary)
    existing_md = strip_r19_terms(existing_md)
    return wrap_r19_prompt(f"""
# Vai trò
Bạn là trợ lý biên tập chuyên phân tích nhân vật trong tiểu thuyết.

# Nhiệm vụ
{DEFAULT_TASK}

# Văn bản gốc
{full_text}

# Glossary tên nhân vật và thuật ngữ
{glossary if glossary else "(Chưa có glossary)"}

# Dữ liệu nhân vật hiện có
{existing_md if existing_md else "(Chưa có dữ liệu nhân vật)"}

# Yêu cầu
1. Header `## Tên nhân vật` phải dùng tên đầy đủ theo glossary.
2. Nếu nhân vật đã có, giữ nguyên tên header hiện tại.
3. Không dùng biệt danh, danh hiệu hoặc tên tắt làm header.
4. Ghi “Chưa xác định” cho trường bắt buộc chưa đủ căn cứ; không tự đoán.
5. Với quan hệ và xưng hô, ghi rõ hai chiều, đối tượng và hoàn cảnh nếu văn bản cho biết.

# Template bắt buộc
```
## [Tên nhân vật]

### Thông tin cơ bản
- **Tên gốc**:
- **Biệt danh / Danh hiệu**:
- **Giới tính**: Nam / Nữ / Không xác định
- **Tuổi / Độ tuổi ước lượng**:
- **Chủng tộc / Xuất thân**:
- **Địa vị / Chức vụ**:
- **Phe / Tổ chức**:

### Vai trò và diễn biến
- **Vai trò trong truyện**:
- **Mục tiêu / Động cơ**:
- **Năng lực / Kỹ năng**:
- **Diễn biến đáng chú ý**:

### Quan hệ và xưng hô
- **Quan hệ quan trọng**:
- **Cách tự xưng / Gọi người khác**:
- **Giọng điệu / Đặc điểm lời thoại**:

### Ghi chú dịch thuật
- (Tên gốc, cách dịch đặc biệt, lưu ý khi dịch thoại...)
```

Bọc toàn bộ kết quả trong duy nhất một code block `markdown` để giữ nguyên các dấu `##`.
Bên trong code block, bắt đầu bằng `###START###` và kết thúc bằng `###END###`.
Không thêm giải thích hoặc nội dung ngoài code block.
""")
