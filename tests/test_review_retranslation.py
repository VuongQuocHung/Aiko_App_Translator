import tempfile
import threading
import unittest
from concurrent.futures import Future
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

from cores.translation import runner
from cores.postprocess.review import enqueue_background_review
from cores.storage.project import load_json


class ReviewRetranslationTests(unittest.TestCase):
    def run_chapter(self, scores, *, enabled=True, threshold=9, failure=False, future=False, stop=False):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp)
            raw = root / "raw" / "v1_c1_s1.md"
            raw.parent.mkdir()
            raw.write_text("# Source\n\nOriginal text", encoding="utf-8")
            output = root / "translated" / raw.name
            reviews = []
            calls = []

            def translate(chapter, number, context, pronouns):
                calls.append((dict(chapter), context))
                if failure and len(calls) == 2:
                    raise RuntimeError("retry unavailable")
                return "Title", f"Translation {len(calls)}"

            def review(chapter, number, context):
                reviews.append(dict(chapter))
                result = {"score": scores[len(reviews) - 1], "issues": [{"suggestion": "Fix meaning"}], "summary": "Feedback"}
                if future:
                    value = Future()
                    value.set_result(result)
                    return value
                return result

            stack.enter_context(patch.object(runner, "filtered_context_and_names", return_value=("Glossary", [], "pronouns.json")))
            stack.enter_context(patch.object(runner, "format_pronoun_context", return_value="Pronouns"))
            stack.enter_context(patch.object(runner, "_export_recent_translations"))
            stack.enter_context(patch.object(runner, "with_previous_titles", side_effect=lambda context, *a, **kw: context))
            stack.enter_context(patch.object(runner, "option", side_effect=lambda name, default=None: 0 if name == "previous_context_chapters" else default))
            stack.enter_context(patch.object(runner, "bool_option", side_effect=lambda name, default=False: enabled if name == "review_retranslate_enabled" else False))
            stack.enter_context(patch.object(runner, "int_option", side_effect=lambda name, default=None: threshold if name == "review_retranslate_threshold" else default))
            stack.enter_context(patch.object(runner, "stop_requested", side_effect=lambda: stop and bool(reviews)))
            stack.enter_context(patch.object(runner, "enqueue_background_review", side_effect=review))
            def correction(chapter, title, content, feedback, context, pronouns):
                import json
                return translate(chapter, 1, context + json.dumps({"content": content, "review": feedback}), pronouns)
            stack.enter_context(patch.object(runner, "correct_review", side_effect=correction))
            result = runner.run_single_translation(
                translate, raw.parent, output.parent, root / "context.json",
                postprocess=lambda chapter, *args: (chapter["title_translation"], chapter["translation"]),
                max_attempts=3,
            )
            saved = output.read_text(encoding="utf-8")
            backup = Path(str(output) + ".before-review.bak")
            return result, calls, reviews, saved, backup.read_text(encoding="utf-8") if backup.exists() else None

    def test_low_score_retries_once_even_when_second_score_is_low(self):
        result, calls, reviews, saved, backup = self.run_chapter([8, 7], future=True)
        self.assertEqual(result, 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(reviews), 2)
        self.assertEqual(calls[1][0]["content"], "Original text")
        for value in ("Translation 1", "Fix meaning", "Feedback", "Glossary"):
            self.assertIn(value, calls[1][1])
        self.assertNotIn("Translation 1", calls[0][1])
        self.assertIn("Translation 2", saved)
        self.assertIn("Translation 1", backup)
        self.assertEqual(reviews[1]["translation"], "Translation 2")
        self.assertTrue(reviews[1]["_review_retry"])

    def test_web_review_result_also_triggers_retry(self):
        self.assertEqual(len(self.run_chapter([8.9, 9])[1]), 2)

    def test_threshold_and_invalid_scores_do_not_trigger_retry(self):
        for score in (9, 10, None, "bad", True, float("nan"), float("inf"), -1, 11, 0):
            with self.subTest(score=score):
                self.assertEqual(len(self.run_chapter([score])[1]), 1)

    def test_configured_threshold_controls_retry(self):
        self.assertEqual(len(self.run_chapter([7.9, 9], threshold=8)[1]), 2)
        self.assertEqual(len(self.run_chapter([8], threshold=8)[1]), 1)

    def test_failed_retry_preserves_saved_translation_without_outer_retry(self):
        result, calls, reviews, saved, backup = self.run_chapter([8], failure=True)
        self.assertEqual(result, 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(saved, backup)

    def test_disabled_setting_keeps_background_behavior(self):
        self.assertEqual(len(self.run_chapter([8], enabled=False)[1]), 1)

    def test_stop_after_review_does_not_retranslate(self):
        self.assertEqual(len(self.run_chapter([8], stop=True)[1]), 1)

    def test_review_transport_returns_score_and_clears_old_score_on_failed_final_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Mock()
            runtime.REVIEW_JSON = str(Path(tmp) / "review.json")
            runtime.REVIEW_BG_CRITERIA = "Check meaning"
            runtime._review_lock = threading.Lock()
            runtime._latest_review_tokens = {}
            runtime.enabled.return_value = True
            runtime.provider.return_value = "gemini-web"
            runtime.model_and_thinking.return_value = ("model", "high")
            runtime.generate.return_value = ('{"overall_score":8,"issues":[],"summary":"fix"}', "gemini-web", "model")
            chapter = {"id": "c1", "title": "Source", "content": "Original", "translation": "Old"}
            with patch("cores.postprocess.review.build_reference_documents", return_value=[]):
                review = enqueue_background_review(runtime, chapter, 1)
                self.assertEqual(review["score"], 8)
                runtime.generate.side_effect = RuntimeError("failed")
                result = enqueue_background_review(runtime, {**chapter, "translation": "New", "_review_retry": True}, 1)
            self.assertIsNone(result)
            self.assertIsNone(load_json(runtime.REVIEW_JSON, {})["c1"]["score"])

    def test_review_disabled_does_not_call_model(self):
        runtime = Mock()
        runtime.enabled.return_value = False
        self.assertIsNone(enqueue_background_review(runtime, {"id": "c1"}, 1))
        runtime.generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
