"""Polish translated chapters with provider-neutral reference snapshots."""

import os
import time
from pathlib import Path

from cores.postprocess.snapshots import build_characters_snapshot
from cores.retry import chapter_retry_managed, managed_chapter_attempt
from cores.translation.prompts import build_polish_prompt
from cores.stages.outputs import parse_title_content
from cores.config.runtime import stop_requested
from cores.context.glossary import glossary_from_context, parse_glossary
from cores.context.validation import introduced_terms, CHAPTER_HEADING
from cores.stages.budget import ContextBudgetError
from cores.postprocess.glossary import validate_and_correct


def polish_translation(
    runtime,
    chapter,
    chapter_number,
    context_text,
    pronoun_context,
    characters_md_path,
    pronouns_file,
    model=None,
    thinking_level=None,
):
    """Polish one translated chapter through the configured polish provider."""
    segments = chapter.get("_translation_segments", [])
    if segments:
        # Original and draft remain aligned; proofreading gets its OWN mention state.
        entries = parse_glossary(glossary_from_context(context_text))
        seen = set(chapter.get("_glossary_introduced", ()))
        polished = []
        for segment in segments:
            piece = {**segment, "_glossary_introduced": sorted(seen)}
            piece.pop("_translation_segments", None)
            result = polish_translation(runtime, piece, chapter_number, context_text,
                                        pronoun_context, characters_md_path, pronouns_file,
                                        model, thinking_level)
            piece["title_translation"], piece["translation"] = result
            result = validate_and_correct(runtime, piece, context_text)
            polished.append(result)
            if CHAPTER_HEADING.search(result[1]):
                seen.clear()
            seen.update(introduced_terms(result[1], entries))
        return polished[0][0], "\n\n".join(result[1] for result in polished)
    chapter_id = chapter.get("id", f"chapter_{chapter_number}")
    raw_title = chapter.get("title", "")
    raw_content = chapter.get("content", "")
    title_cur = chapter.get("title_translation", "")
    content_cur = chapter.get("translation", "")
    configured_model, _thinking = runtime.model_and_thinking("polish")
    effective_model = str(model or configured_model)
    if not content_cur.strip():
        return title_cur, content_cur

    provider = runtime.provider("polish")
    print(
        f"[POLISH] Biên tập chương {chapter_number} ({chapter_id}) "
        f"với {provider}:{effective_model}..."
    )
    tmp_characters = None
    try:
        relevant_text = "\n".join(
            [raw_title, raw_content, title_cur, content_cur, pronoun_context]
        )
        tmp_characters = build_characters_snapshot(
            characters_md_path,
            relevant_text,
            max_characters=min(
                runtime.int_option("character_snapshot_limit", 20, minimum=1), 50
            ),
        )
        attachments = []
        if tmp_characters:
            attachments.append(
                {
                    "name": "characters.md",
                    "mime_type": "text/markdown",
                    "content": Path(tmp_characters).read_text(encoding="utf-8"),
                }
            )
        role, task = runtime.project_polish_prompt()
        prompt = build_polish_prompt(chapter, context_text, pronoun_context, role=role, task=task)
        if tmp_characters:
            prompt = runtime.with_character_document_instruction(prompt)

        for attempt in range(3):
            if stop_requested():
                raise InterruptedError("Đã dừng hiệu đính")
            try:
                with managed_chapter_attempt():
                    text, provider, effective_model = runtime.generate(
                        "polish", prompt, attachments
                    )
                if "###TITLE###" not in text or "###CONTENT###" not in text:
                    print("[POLISH] Output sai format -- giữ nguyên bản dịch cũ.")
                    runtime.log_api_call(
                        chapter_id,
                        "polish",
                        f"{provider}:{effective_model}",
                        prompt,
                        text,
                        ok=False,
                        attachments=attachments,
                    )
                    if chapter_retry_managed():
                        raise ValueError("Output hiệu đính sai định dạng")
                    return title_cur, content_cur
                title_out, content_out = parse_title_content(text, "Hiệu đính")
                runtime.log_api_call(
                    chapter_id,
                    "polish",
                    f"{provider}:{effective_model}",
                    prompt,
                    text,
                    ok=True,
                    attachments=attachments,
                )
                print(
                    f"[POLISH] Đã biên tập chương {chapter_number} "
                    f"({len(content_out)} ký tự)"
                )
                return title_out, content_out
            except InterruptedError:
                raise
            except ContextBudgetError:
                # Not a network failure. The caller retains the original draft.
                raise
            except Exception as error:
                message = str(error)
                print(f"[POLISH] Lỗi: {message}")
                if chapter_retry_managed():
                    raise
                if attempt == 2:
                    print("[POLISH] Đã hết số lần thử; giữ bản dịch nháp.")
                    return title_cur, content_cur
                if provider == "gemini-api" and (
                    "429" in message
                    or "RESOURCE_EXHAUSTED" in message
                    or "403" in message
                    or "PERMISSION_DENIED" in message
                ):
                    runtime.switch_key_for("polish")
                    delay = 30 if "429" in message or "RESOURCE_EXHAUSTED" in message else 15
                elif any(code in message for code in ("500", "502", "503", "504")):
                    delay = 10
                else:
                    delay = 15
                print(f"[POLISH] Chờ {delay}s rồi thử lại...")
                time.sleep(delay)
    finally:
        for path in (tmp_characters,):
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass
