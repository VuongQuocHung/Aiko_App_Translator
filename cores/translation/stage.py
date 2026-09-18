"""Translate one chapter through the selected provider."""

from cores.api_logging import log_project_api_call as log_api_call
from cores.config import NOVEL_TXT
from cores.r19 import (
    mask_contexts,
    prepare_chapters,
    restore_results,
    strip_previous_context,
    translate_fragments,
)
from cores.config.runtime import option
from cores.stages import (
    TRANSPORT_OVERRIDES,
    build_reference_documents,
    generate_stage,
    parse_title_content,
    stage_model_and_thinking,
    stage_provider,
)
from cores.translation.prompts import build_single_prompt, build_polish_prompt, with_character_document_instruction
from cores.stages.budget import ContextBudgetError, estimate_tokens, split_source, stage_limits, fit_request
from cores.context.glossary import glossary_from_context, parse_glossary
from cores.context.validation import introduced_terms, CHAPTER_HEADING


def provider(stage):
    return stage_provider(stage, get_option=option)


def model_and_thinking(stage, provider_id):
    return stage_model_and_thinking(stage, provider_id, get_option=option)


def generate(stage, prompt, attachments=()):
    provider_id = provider(stage)
    model, _thinking = model_and_thinking(stage, provider_id)
    response, _provider_id, _model = generate_stage(
        stage,
        prompt,
        provider=provider_id,
        get_option=option,
        overrides=TRANSPORT_OVERRIDES,
        attachments=attachments,
    )
    return response, model


def translate_r19_fragments(entries):
    provider_id = provider("translate")
    model, _thinking = model_and_thinking("translate", provider_id)

    def generate_fragment(prompt):
        return generate_stage(
            "translate",
            prompt,
            provider=provider_id,
            get_option=option,
            overrides=TRANSPORT_OVERRIDES,
        )[0].text

    switcher = None
    key_count = 1
    if provider_id == "gemini-api":
        from cores.gemini import API_KEYS, switch_api_key

        switcher = switch_api_key
        key_count = max(1, len(API_KEYS))
    return translate_fragments(
        entries,
        generate_fragment,
        provider=provider_id,
        model=model,
        switcher=switcher,
        key_count=key_count,
    )


def translate_chapter(chapter, chapter_number, context_text="", pronoun_context=""):
    """Prefer a whole chapter; retain aligned source/draft segments if it must split."""
    entries = parse_glossary(glossary_from_context(context_text))
    seen = set(chapter.get("_glossary_introduced", ()))
    segments = []
    def translate_piece(piece, depth=0):
        piece = {**piece, "_glossary_introduced": sorted(seen)}
        try:
            _context_limit, output_limit = stage_limits("translate", provider("translate"), option)
            if estimate_tokens(piece.get("content", "")) * 2 > output_limit:
                raise ContextBudgetError("Nguồn có thể vượt giới hạn đầu ra; chia theo đoạn văn.")
            result = _translate_whole(piece, chapter_number, context_text, pronoun_context)
        except ContextBudgetError:
            if depth >= 12:
                raise
            left, right = split_source(piece.get("content", ""))
            print("[CONTEXT] Chia chương theo đoạn; giữ trạng thái thuật ngữ trong chương.")
            translate_piece({**piece, "content": left}, depth + 1)
            translate_piece({**piece, "content": right}, depth + 1)
            return
        title, content = result
        segments.append({**piece, "title_translation": title, "translation": content})
        if CHAPTER_HEADING.search(content):
            seen.clear()
        seen.update(introduced_terms(content, entries))
    translate_piece(chapter)
    if len(segments) > 1:
        chapter["_translation_segments"] = segments
    return segments[0]["title_translation"], "\n\n".join(s["translation"] for s in segments)


def _translate_whole(chapter, chapter_number, context_text="", pronoun_context=""):
    masked_chapters, r19_entries = prepare_chapters([chapter])
    masked_context, masked_pronouns = mask_contexts(
        [context_text, pronoun_context], r19_entries
    )
    previous = ""
    try:
        with open(NOVEL_TXT, "r", encoding="utf-8") as file:
            previous = file.read().strip()
    except OSError:
        pass
    prompt = build_single_prompt(
        masked_chapters[0],
        masked_context,
        masked_pronouns,
        strip_previous_context(previous),
    )
    provider_id = provider("translate")
    documents = build_reference_documents(chapter, pronoun_context)
    polish_provider = provider("polish")
    if polish_provider != "off" and model_and_thinking("polish", polish_provider)[0].lower() not in {"", "none"}:
        # Reserve room for both original and a potentially longer Vietnamese draft
        # before choosing chunk boundaries, keeping source/draft alignment exact.
        simulated = {**chapter, "title_translation": chapter.get("title", ""),
                     "translation": chapter.get("content", "") * 2}
        preview = build_polish_prompt(simulated, masked_context, masked_pronouns)
        window, output = stage_limits("polish", polish_provider, option)
        fit_request(preview, documents, context_tokens=window, output_tokens=output)
    if any(item["name"] == "characters.md" for item in documents):
        prompt = with_character_document_instruction(prompt)
    response, model = generate("translate", prompt, documents)
    log_api_call(
        chapter["id"],
        "translate",
        f"{provider_id}:{model}",
        prompt,
        response.text,
        attachments=list(documents),
    )
    result = parse_title_content(response.text, "Dịch")
    if r19_entries:
        result = restore_results(
            [result], r19_entries, translate_r19_fragments(r19_entries)
        )[0]
    return result
