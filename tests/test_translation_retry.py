import unittest
from unittest.mock import Mock, patch

from cores.translation import runner


class TranslationRetryTests(unittest.TestCase):
    def _runner_patches(self, raw_files, *, translated=None):
        translated = translated if translated is not None else set()
        return (
            patch.object(runner, "scan_md_dir", return_value=raw_files),
            patch.object(
                runner,
                "is_translated",
                side_effect=lambda chapter, _directory: chapter in translated,
            ),
            patch.object(
                runner, "option", side_effect=lambda _name, default=None: default
            ),
            patch.object(runner, "stop_requested", return_value=False),
        )

    def test_retries_three_times_then_skips_to_next_chapter(self):
        raw_files = ["raw/v1_c1_s1.md", "raw/v1_c2_s1.md"]
        skipped = set()
        attempted = []

        def process(_translate, raw_path, *_args, **_kwargs):
            chapter = runner.chapter_id(raw_path)
            attempted.append(chapter)
            if chapter == "v1_c1_s1":
                raise RuntimeError("chapter failed")
            return 1

        scan, translated_check, option, stopped = self._runner_patches(raw_files)
        with (
            scan,
            translated_check,
            option,
            stopped,
            patch.object(runner, "_translate_candidate", side_effect=process),
        ):
            result = runner.run_single_translation(
                Mock(),
                "raw",
                "translated",
                "context.yaml",
                skipped_chapters=skipped,
                max_attempts=3,
                retry_delay_seconds=0,
            )

        self.assertEqual(result, 1)
        self.assertEqual(
            attempted,
            ["v1_c1_s1", "v1_c1_s1", "v1_c1_s1", "v1_c2_s1"],
        )
        self.assertEqual(skipped, {"v1_c1_s1"})

    def test_persistent_skipped_set_avoids_failed_chapter_on_next_invocation(self):
        raw_files = [
            "raw/v1_c1_s1.md",
            "raw/v1_c2_s1.md",
            "raw/v1_c3_s1.md",
        ]
        skipped = set()
        translated = set()
        attempted = []

        def process(_translate, raw_path, *_args, **_kwargs):
            chapter = runner.chapter_id(raw_path)
            attempted.append(chapter)
            if chapter == "v1_c1_s1":
                raise RuntimeError("chapter failed")
            translated.add(chapter)
            return 1

        scan, translated_check, option, stopped = self._runner_patches(
            raw_files, translated=translated
        )
        with (
            scan,
            translated_check,
            option,
            stopped,
            patch.object(runner, "_translate_candidate", side_effect=process),
        ):
            first = runner.run_single_translation(
                Mock(),
                "raw",
                "translated",
                "context.yaml",
                skipped_chapters=skipped,
                max_attempts=3,
                retry_delay_seconds=0,
            )
            second = runner.run_single_translation(
                Mock(),
                "raw",
                "translated",
                "context.yaml",
                skipped_chapters=skipped,
                max_attempts=3,
                retry_delay_seconds=0,
            )

        self.assertEqual((first, second), (1, 1))
        self.assertEqual(
            attempted,
            [
                "v1_c1_s1",
                "v1_c1_s1",
                "v1_c1_s1",
                "v1_c2_s1",
                "v1_c3_s1",
            ],
        )
        self.assertEqual(skipped, {"v1_c1_s1"})

    def test_default_max_attempts_none_propagates_for_manual_compatibility(self):
        raw_files = ["raw/v1_c1_s1.md"]
        failure = RuntimeError("manual result is invalid")
        process = Mock(side_effect=failure)
        scan, translated_check, option, stopped = self._runner_patches(raw_files)

        with (
            scan,
            translated_check,
            option,
            stopped,
            patch.object(runner, "_translate_candidate", process),
        ):
            with self.assertRaisesRegex(RuntimeError, "manual result is invalid"):
                runner.run_single_translation(
                    Mock(), "raw", "translated", "context.yaml"
                )

        process.assert_called_once()

    def test_interrupted_error_is_not_retried_or_silently_skipped(self):
        raw_files = ["raw/v1_c1_s1.md", "raw/v1_c2_s1.md"]
        process = Mock(side_effect=InterruptedError("stream interrupted"))
        scan, translated_check, option, stopped = self._runner_patches(raw_files)

        with (
            scan,
            translated_check,
            option,
            stopped,
            patch.object(runner, "_translate_candidate", process),
        ):
            with self.assertRaisesRegex(InterruptedError, "stream interrupted"):
                runner.run_single_translation(
                    Mock(),
                    "raw",
                    "translated",
                    "context.yaml",
                    skipped_chapters=set(),
                    max_attempts=3,
                    retry_delay_seconds=0,
                )

        process.assert_called_once()

    def test_review_enqueue_failure_after_save_does_not_retranslate(self):
        raw_files = ["raw/v1_c1_s1.md"]
        chapter = {
            "id": "v1_c1_s1",
            "title": "Raw title",
            "content": "Raw content",
        }
        translate = Mock(return_value=("Translated title", "Translated content"))
        postprocess = Mock(return_value=("Final title", "Final content"))

        scan, translated_check, option, stopped = self._runner_patches(raw_files)
        with (
            scan,
            translated_check,
            option,
            stopped,
            patch.object(runner, "load_md_chapter", return_value=chapter),
            patch.object(
                runner,
                "filtered_context_and_names",
                return_value=("context", [], "pronouns.json"),
            ),
            patch.object(runner, "format_pronoun_context", return_value="pronouns"),
            patch.object(runner, "_export_recent_translations"),
            patch.object(runner, "with_previous_titles", return_value="translation context"),
            patch.object(runner, "bool_option", return_value=False),
            patch.object(
                runner,
                "save_translated_md",
                return_value="translated/v1_c1_s1.md",
            ) as save,
            patch.object(
                runner,
                "enqueue_background_review",
                side_effect=RuntimeError("review unavailable"),
            ) as enqueue,
        ):
            result = runner.run_single_translation(
                translate,
                "raw",
                "translated",
                "context.yaml",
                postprocess=postprocess,
                skipped_chapters=set(),
                max_attempts=3,
                retry_delay_seconds=0,
            )

        self.assertEqual(result, 1)
        translate.assert_called_once()
        postprocess.assert_called_once()
        save.assert_called_once_with(
            "raw/v1_c1_s1.md", "translated", "Final title", "Final content"
        )
        enqueue.assert_called_once()


if __name__ == "__main__":
    unittest.main()
