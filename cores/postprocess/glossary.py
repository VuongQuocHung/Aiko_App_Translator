"""Bounded glossary correction using the configured proofreading model."""

from cores.context.glossary import glossary_from_context, parse_glossary
from cores.context.validation import validate_glossary, glossary_prose_signature
from cores.stages.outputs import parse_title_content
from cores.translation.prompts import build_correction_prompt
from cores.config.runtime import stop_requested
from cores.retry import managed_chapter_attempt


def validate_and_correct(runtime, chapter, context_text):
    entries = parse_glossary(glossary_from_context(context_text))
    title, content = chapter.get("title_translation", ""), chapter.get("translation", "")
    def validate(value):
        return validate_glossary(value, entries, chapter.get("content", ""),
                                introduced=chapter.get("_glossary_introduced", ()))
    errors = validate(content)
    chapter["glossary_validation"] = {"passed": not errors, "errors": [str(e) for e in errors], "corrected": False}
    if not errors:
        return title, content
    print(f"[GLOSSARY] Phát hiện {len(errors)} lỗi định dạng.")
    if not runtime.enabled("polish"):
        print("[GLOSSARY] Chưa sửa lỗi vì công đoạn hiệu đính đã tắt.")
        return title, content
    if stop_requested():
        raise InterruptedError("Đã dừng sửa glossary")
    prompt = build_correction_prompt(chapter, context_text, errors)
    try:
        # A single semantic correction, independent of network retry policy.
        with managed_chapter_attempt():
            text, provider, model = runtime.generate("polish", prompt)
        candidate_title, candidate = parse_title_content(text, "Sửa glossary")
        remaining = validate(candidate)
        prose_preserved = (glossary_prose_signature(content, entries) == glossary_prose_signature(candidate, entries)
                           and glossary_prose_signature(title, entries) == glossary_prose_signature(candidate_title, entries))
        runtime.log_api_call(chapter.get("id", "chapter"), "glossary_correction",
                             f"{provider}:{model}", prompt, text, ok=not remaining and prose_preserved)
        # Never promote another invalid candidate over the proofread version.
        if not remaining and prose_preserved:
            chapter["glossary_validation"] = {"passed": True, "errors": [], "corrected": True}
            return candidate_title, candidate
        print(f"[GLOSSARY] Bản sửa còn {len(remaining)} lỗi hoặc thay đổi câu văn; giữ bản hiệu đính để kiểm tra.")
    except InterruptedError:
        raise
    except Exception as error:
        print(f"[GLOSSARY] Sửa lỗi thất bại; giữ bản hiệu đính: {error}")
    return title, content
