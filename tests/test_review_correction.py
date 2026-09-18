import unittest
from unittest.mock import patch

from cores.postprocess.review_correction import apply_review_edits, correct_review


class ReviewCorrectionTests(unittest.TestCase):
    def test_only_selected_span_changes(self):
        content = "Keep this.\n\nWrong word.\nKeep this too."
        result = apply_review_edits("Title", content, [{}], {"edits": [
            {"issue_index": 0, "field": "content", "old": "Wrong", "new": "Right"}
        ]})
        self.assertEqual(result, ("Title", content.replace("Wrong", "Right")))

    def test_invalid_edits_rejected(self):
        base = {"issue_index": 0, "field": "content", "old": "word", "new": "fixed"}
        for edit in ({**base, "issue_index": 1}, {**base, "old": "missing"},
                     {**base, "field": "source"}, {**base, "issue_index": True}):
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                apply_review_edits("Title", "word", [{}], {"edits": [edit]})
        with self.assertRaises(ValueError):
            apply_review_edits("Title", "word word", [{}], {"edits": [base]})
        with self.assertRaises(ValueError):
            apply_review_edits("Title", "word", [{}], {"edits": [base, base]})

    def test_empty_issues_do_not_call_ai(self):
        with patch("cores.postprocess.runtime.runtime.generate") as generate:
            self.assertEqual(correct_review({}, "Title", "Text", {"issues": []}, "", ""), ("Title", "Text"))
            generate.assert_not_called()

    def test_uses_polish_stage_and_applies_patch(self):
        with patch("cores.postprocess.runtime.runtime.generate", return_value=(
            '{"edits":[{"issue_index":0,"field":"content","old":"bad","new":"good"}]}',
            "provider", "model",
        )) as generate, patch("cores.postprocess.runtime.runtime.log_api_call"):
            self.assertEqual(correct_review({"content": "source"}, "Title", "bad", {"issues": [{}]}, "rules", "names"), ("Title", "good"))
            self.assertEqual(generate.call_args.args[0], "polish")
