"""Provider-independent glossary generation."""

import time

from cores.gemini import switch_api_key
from cores.r19 import strip_r19_terms
from cores.config.runtime import int_option, option
from cores.stages import (
    browser_lifecycle as stage_browser_lifecycle,
    generate_stage,
    stage_model_and_thinking,
    stage_provider,
    stage_transports,
)
from cores.translation.prompts import wrap_r19_prompt


TRANSPORT_OVERRIDES = {}


DEFAULT_TASK = """Đọc kỹ toàn bộ các chương raw được cung cấp và đối chiếu với glossary hiện có trước khi trích xuất thuật ngữ.

Trong quá trình phân tích, cần nhận diện:
- bối cảnh, thể loại, hệ thống sức mạnh hoặc chuyên môn, tổ chức, chức vụ và cấp bậc;
- nhân vật, tên đầy đủ, bí danh, danh hiệu, cách gọi và quan hệ giữa các nhân vật;
- địa danh, vật phẩm, kỹ năng, phép thuật, chủng tộc, khái niệm riêng và các cụm từ lặp lại có nghĩa chuyên biệt;
- ngữ cảnh sử dụng để phân biệt tên riêng hoặc thuật ngữ với từ phổ thông.

Chỉ đưa vào glossary những mục cần giữ nhất quán khi dịch. Bỏ qua từ phổ thông, vật dụng đời thường, câu hoàn chỉnh và mục chỉ xuất hiện ngẫu nhiên mà không mang nghĩa riêng. Không suy diễn từ kiến thức ngoài văn bản. Khi dữ liệu chưa đủ chắc chắn, giữ nguyên từ nguồn hoặc không trích xuất.

Giữ nguyên chính xác từ hoặc cụm từ nguồn ở vế trái. Vế phải là cách viết hoặc bản dịch tiếng Việt tự nhiên, phù hợp ngữ cảnh. Tôn trọng cách dịch đã có trong glossary; không tự đổi một mục cũ nếu văn bản mới không cung cấp bằng chứng rõ ràng. Tên riêng viết hoa từng âm tiết; danh từ và chức vị thông thường viết thường."""


def context_provider():
    return stage_provider("context", get_option=option)


def context_model_and_thinking(provider):
    return stage_model_and_thinking("context", provider, get_option=option)


def context_transports():
    return stage_transports(TRANSPORT_OVERRIDES)


def browser_lifecycle(provider):
    return stage_browser_lifecycle(provider)


def build_glossary_prompt(chapters, old_glossary):
    content = strip_r19_terms("\n\n".join(
        f"{chapter.get('title', '')}\n{chapter.get('content', '')}"
        for chapter in chapters
        if chapter.get("content")
    ))
    if not content.strip():
        return ""
    old_glossary = strip_r19_terms(old_glossary)
    return wrap_r19_prompt(f"""# Vai trò
Bạn là biên tập viên chuyên phân tích ngữ cảnh và xây dựng bộ nhớ thuật ngữ cho bản dịch tiểu thuyết từ mọi ngôn ngữ nguồn sang tiếng Việt. Tự nhận diện ngôn ngữ và thể loại từ nội dung; không mặc định truyện thuộc thể loại fantasy.

# Nhiệm vụ
{DEFAULT_TASK}

# Glossary hiện có
{old_glossary}

# Nội dung raw cần phân tích
{content}

# Định dạng đầu ra
Chỉ xuất mỗi mục trên một dòng theo dạng:
Nguyên văn = Bản dịch

Bắt đầu bằng ###START### và kết thúc bằng ###END###.
Không thêm Markdown hoặc lời giải thích.""")


def generate_glossary(chapters, old_glossary):
    prompt = build_glossary_prompt(chapters, old_glossary)
    if not prompt:
        print("⚠️ Batch này không có nội dung, bỏ qua.")
        return ""
    provider = context_provider()
    model, thinking = context_model_and_thinking(provider)
    retries = int_option("context_retries", 3, minimum=1)
    for attempt in range(1, retries + 1):
        try:
            print(f"📤 Gửi {provider} bằng {model} (lần {attempt}/{retries})...")
            response = generate_stage(
                "context",
                prompt,
                provider=provider,
                get_option=option,
                overrides=TRANSPORT_OVERRIDES,
            )[0].text.strip()
            if "###START###" in response and "###END###" in response:
                return response
            print("⚠️ Kết quả thiếu marker START/END.")
        except Exception as error:
            print(f"⚠️ Lỗi tạo Context qua {provider}: {error}")
            if provider == "gemini-api" and (
                "429" in str(error) or "RESOURCE_EXHAUSTED" in str(error)
            ):
                switch_api_key()
        if attempt < retries:
            time.sleep(5)
    raise ValueError(f"{provider} không trả về glossary hợp lệ sau {retries} lần thử")
