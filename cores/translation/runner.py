"""Run and persist one translation chapter."""

import os
import math
import shutil
import time
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from collections.abc import Callable
from contextlib import nullcontext

from cores.chapters.files import (
    export_recent_translations,
    is_translated,
    load_md_chapter,
    save_translated_md,
    scan_md_dir,
)
from cores.config import NOVEL_TXT, RAW_DIR, TRANSLATED_DIR
from cores.postprocess import enqueue_background_review, run_post_translation_pipeline
from cores.postprocess.review_correction import correct_review
from cores.pronouns import format_pronoun_context
from cores.retry import managed_chapter_attempt
from cores.r19 import (
    mask_postprocess_contexts,
    prepare_postprocess_chapter,
    restore_results,
)
from cores.config.runtime import bool_option, int_option, option, stop_requested
from cores.translation.context import (
    chapter_id,
    filtered_context_and_names,
    with_previous_titles,
)
from cores.storage.project import load_json, save_json
from pathlib import Path
from cores.stages.budget import ContextBudgetError

TranslateOne = Callable[[dict, int, str, str], tuple[str, str]]
MAX_CHAPTER_ATTEMPTS = 3
CHAPTER_RETRY_DELAY_SECONDS = 5


def _await_review(result):
    if isinstance(result, Future):
        while not stop_requested():
            try:
                return result.result(timeout=0.5)
            except FutureTimeoutError:
                continue
        return None
    return result


def _needs_review_retry(review, threshold=9):
    if not isinstance(review, dict) or isinstance(review.get("score"), bool):
        return False
    try:
        score = float(review.get("score"))
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(score) and 1 <= score <= 10 and score < threshold


def _export_recent_translations(target_chapter_id, count):
    return export_recent_translations(
        RAW_DIR,
        TRANSLATED_DIR,
        NOVEL_TXT,
        n=count,
        target_chapter_id=target_chapter_id,
    )


def _wait_before_retry(seconds):
    """Wait in short intervals so a stop request remains responsive."""
    for _ in range(max(0, int(seconds))):
        if stop_requested():
            return False
        time.sleep(1)
    return not stop_requested()


def _translate_candidate(
    translate,
    raw_path,
    raw_files,
    index,
    translated_dir,
    context_path,
    postprocess,
    *,
    review_feedback=None,
    allow_review_retry=True,
):
    """Translate one candidate. Exceptions are handled by the chapter runner."""
    current_chapter_id = chapter_id(raw_path)
    chapter_number = index + 1
    # Reload on every attempt because post-processing mutates this dictionary.
    chapter = load_md_chapter(raw_path)
    context_text, glossary_names, pronouns_path = filtered_context_and_names(
        context_path, raw_files, index
    )
    pronoun_context = format_pronoun_context(
        chapter_number,
        pronouns_file=pronouns_path,
        glossary_names=glossary_names,
    )
    previous_count = int(option("previous_context_chapters", 3))
    _export_recent_translations(current_chapter_id, previous_count)
    print(f"Dang dich Chuong {chapter_number}: {chapter['id']}...")

    translation_context = with_previous_titles(
        context_text,
        raw_files,
        index,
        translated_dir,
        count=previous_count,
        heading="Cac tieu de truoc da dich:",
    )
    if review_feedback is not None:
        result = correct_review(
            chapter, review_feedback["title"], review_feedback["content"],
            review_feedback["review"], translation_context, pronoun_context,
        )
    else:
        result = translate(chapter, chapter_number, translation_context, pronoun_context)
    if result is None:
        return 0
    title, content = result
    if review_feedback and (not isinstance(content, str) or not content.strip()):
        raise ValueError("Bản hiệu đính lần 2 rỗng; giữ bản dịch trước review.")
    chapter["title_translation"] = title
    chapter["translation"] = content

    postprocess_entries = []
    postprocess_translations = {}
    pipeline_context = context_text
    pipeline_pronouns = pronoun_context
    # Review corrections must not trigger broad polishing or language rewriting.
    if review_feedback is None:
        if bool_option("r19_mode", False):
            chapter, postprocess_entries, postprocess_translations = (
                prepare_postprocess_chapter(chapter)
            )
            pipeline_context, pipeline_pronouns = mask_postprocess_contexts(
                [context_text, pronoun_context], postprocess_translations
            )
        if postprocess is None:
            title, content = run_post_translation_pipeline(
                chapter,
                chapter_number,
                pipeline_context,
                pipeline_pronouns,
                pronouns_file=pronouns_path,
            )
        else:
            title, content = postprocess(
                chapter, chapter_number, pipeline_context, pipeline_pronouns
            )
        if postprocess_entries:
            title, content = restore_results(
                [(title, content)], postprocess_entries, postprocess_translations
            )[0]
    chapter["title_translation"] = title
    chapter["translation"] = content

    if review_feedback and not content.strip():
        raise ValueError("Bản hậu xử lý rỗng; giữ bản dịch trước review.")
    output_path = save_translated_md(raw_path, translated_dir, title, content)
    print(f"Da luu: {output_path}")
    if chapter.get("glossary_validation"):
        report_path = Path(context_path).parent / "glossary_validation.json"
        try:
            reports = load_json(report_path, {})
            reports[current_chapter_id] = chapter["glossary_validation"]
            if chapter.get("proofreading_warning"):
                reports[current_chapter_id]["proofreading_warning"] = chapter["proofreading_warning"]
            save_json(report_path, reports)
        except (OSError, ValueError, TypeError) as error:
            print(f"[GLOSSARY] Không lưu được báo cáo kiểm tra: {error}")
    try:
        # Postprocessing may have masked raw text for R19. Review must compare
        # the restored final translation against the actual original.
        review_chapter = {**chapter, **load_md_chapter(raw_path),
                          "title_translation": title, "translation": content,
                          "_review_retry": review_feedback is not None}
        pending_review = enqueue_background_review(review_chapter, chapter_number, context_text)
        if allow_review_retry and bool_option("review_retranslate_enabled", True):
            review_threshold = min(10, max(1, int_option("review_retranslate_threshold", 9)))
            review = _await_review(pending_review)
            if review_feedback is not None and isinstance(review, dict):
                print(f"[REVIEW] {current_chapter_id}: sau hiệu đính lần 2 {review.get('score')}/10; không hiệu đính thêm.")
            if review_feedback is None and _needs_review_retry(review, review_threshold) and review.get("issues") and not stop_requested():
                print(f"[REVIEW] {current_chapter_id}: {review['score']}/10 < {review_threshold}; hiệu đính lần 2 theo lỗi review.")
                # Keep both the previous text and its review for inspection or recovery.
                shutil.copy2(output_path, str(output_path) + ".before-review.bak")
                save_json(str(output_path) + ".before-review.json", review)
                _translate_candidate(
                    translate, raw_path, raw_files, index, translated_dir,
                    context_path, postprocess,
                    review_feedback={"title": title, "content": content, "review": review},
                )
    except Exception as error:
        # The translated file is already committed. Do not translate it again only
        # because the optional background review could not be queued.
        print(f"[REVIEW] Review/hiệu đính lần 2 {current_chapter_id} chưa hoàn tất; giữ bản đã lưu: {error}")
    return 1


def run_single_translation(
    translate: TranslateOne,
    raw_dir,
    translated_dir,
    context_path,
    postprocess=None,
    *,
    skipped_chapters=None,
    max_attempts=None,
    retry_delay_seconds=CHAPTER_RETRY_DELAY_SECONDS,
    allow_review_retry=True,
):
    """Translate the next chapter, optionally retrying and skipping failures."""
    raw_files = scan_md_dir(raw_dir)
    if not raw_files:
        print(f"[INFO] Khong tim thay file .md nao trong {raw_dir}")
        return 0

    retry_enabled = max_attempts is not None
    attempt_limit = max(1, int(max_attempts or 1))
    skipped = skipped_chapters if skipped_chapters is not None else set()
    target_chapter = str(option("target_chapter", "") or "").strip()

    for index, raw_path in enumerate(raw_files):
        if target_chapter and os.path.basename(raw_path) != target_chapter:
            continue
        current_chapter_id = chapter_id(raw_path)
        if current_chapter_id in skipped:
            continue

        translation_state_checked = False
        for attempt in range(1, attempt_limit + 1):
            if stop_requested():
                return 0
            try:
                if not translation_state_checked:
                    if is_translated(current_chapter_id, translated_dir):
                        break
                    translation_state_checked = True
                retry_scope = (
                    managed_chapter_attempt() if retry_enabled else nullcontext()
                )
                with retry_scope:
                    return _translate_candidate(
                        translate,
                        raw_path,
                        raw_files,
                        index,
                        translated_dir,
                        context_path,
                        postprocess,
                        allow_review_retry=allow_review_retry,
                    )
            except InterruptedError:
                if stop_requested():
                    return 0
                raise
            except ContextBudgetError as error:
                if not retry_enabled:
                    raise
                skipped.add(current_chapter_id)
                print(f"[CONTEXT] Không thể chia chương {current_chapter_id}: {error}")
                break
            except Exception as error:
                if not retry_enabled:
                    raise
                print(
                    f"⚠️ Lỗi khi xử lý chương {current_chapter_id} "
                    f"(lần {attempt}/{attempt_limit}): {error}"
                )
                if attempt < attempt_limit:
                    print(
                        f"⏳ Thử lại chương {current_chapter_id} sau "
                        f"{retry_delay_seconds} giây..."
                    )
                    if not _wait_before_retry(retry_delay_seconds):
                        return 0
                    continue

                skipped.add(current_chapter_id)
                print(
                    f"⏭️ Chương {current_chapter_id} vẫn lỗi sau "
                    f"{attempt_limit} lần; bỏ qua và chuyển sang chương tiếp theo."
                )
        # The candidate was already translated or exhausted all attempts.
        # Continue scanning instead of selecting it again.
    return 0
