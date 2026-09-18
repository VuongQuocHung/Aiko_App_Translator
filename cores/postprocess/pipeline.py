"""Orchestration for the legacy post-translation pipeline."""

from cores.postprocess.glossary import validate_and_correct
from cores.stages.budget import ContextBudgetError


def run_post_translation_pipeline(
    runtime,
    chapter,
    chapter_number,
    context_text,
    pronoun_context,
    pronouns_file,
):
    """
    Wrapper chạy toàn bộ pipeline hậu dịch.

    Bước 1 (tuần tự): hiệu đính bằng provider đã chọn.
    Bước 2 (tuần tự): xét sót ngôn ngữ bằng cùng provider hiệu đính.
    Bước 3 (tuần tự): cập nhật pronouns.json bằng provider xưng hô đã chọn.
    Review nền được xếp riêng sau hàm này để mọi engine dùng chung một worker.

    Trả về (title, content) sau khi bước 1-3 hoàn tất.
    """
    chapter_id = chapter.get("id", f"chapter_{chapter_number}")
    print(f"\n{'─' * 55}")
    print(f"[PIPELINE] Bắt đầu hậu xử lý chương {chapter_number} ({chapter_id})")
    print(f"{'─' * 55}")

    title_fixed = chapter.get("title_translation", "")
    content_fixed = chapter.get("translation", "")
    if runtime.enabled("polish"):
        # ── Bước 1: Biên tập trau chuốt + chỉnh xưng hô ──
        print(f"[PIPELINE] Bước 1 — Biên tập trau chuốt...")
        try:
            title_polished, content_polished = runtime.polish_translation(
                chapter, chapter_number, context_text, pronoun_context,
                pronouns_file=pronouns_file,
            )
        except ContextBudgetError as error:
            print(f"[POLISH] Chưa hiệu đính: {error}. Giữ bản nháp.")
            chapter["proofreading_warning"] = str(error)
            title_polished, content_polished = title_fixed, content_fixed
        chapter["title_translation"] = title_polished
        chapter["translation"] = content_polished

        # ── Bước 2: Xét sót ngôn ngữ ──
        print(f"[PIPELINE] Bước 2 — Xét sót ngôn ngữ...")
        if not chapter.get("proofreading_warning"):
            title_fixed, content_fixed = runtime.fix_translation(
                chapter, chapter_number, context_text, pronoun_context
            )
    else:
        print("[PIPELINE] Bỏ qua hậu dịch vì chưa cấu hình model.")
    chapter["title_translation"] = title_fixed
    chapter["translation"] = content_fixed

    title_fixed, content_fixed = validate_and_correct(runtime, chapter, context_text)
    chapter["title_translation"] = title_fixed
    chapter["translation"] = content_fixed

    # ── Bước 3: Cập nhật bộ nhớ xưng hô ──
    if runtime.enabled("pronouns"):
        print(f"[PIPELINE] Bước 3 — Cập nhật bộ nhớ xưng hô...")
        runtime.update_pronoun_memory(chapter_id, chapter_number, content_fixed, pronouns_file)
    else:
        print("[PIPELINE] Bỏ qua xuất xưng hô vì công đoạn đã tắt.")

    status = "✅" if chapter["glossary_validation"]["passed"] else "⚠️ Còn lỗi glossary — cần kiểm tra"
    print(f"[PIPELINE] {status} Hoàn tất hậu xử lý chương {chapter_number}")
    return title_fixed, content_fixed
