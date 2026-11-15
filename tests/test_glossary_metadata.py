import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from cores.context.glossary import parse_glossary, serialize_glossary, filter_glossary
from cores.context.validation import validate_glossary, introduced_terms
from cores.stages.budget import ContextBudgetError, fit_request, split_source
from cores.translation.request import PromptText
from cores.stages.transport import generate_for_stage
from cores.translation.prompts import build_single_prompt, build_polish_prompt
from cores.postprocess.glossary import validate_and_correct
from services.context import ContextService

GLOSSARY = """Chain of Heart = Xiềng Xích Trái Tim | type=Skill | first_vi=yes | brackets=yes
Awakened = Thức Tỉnh | type=Rank | first_vi=yes | brackets=yes
Fate Essence = Tinh Hoa Vận Mệnh | type=Concept | first_vi=yes | brackets=no
Lucid = Lucid | type=Name | first_vi=no | brackets=no
Shield = Khiên | type=Artifact | first_vi=no | brackets=yes"""
VALID = """Lucid kích hoạt [Chain of Heart] (Xiềng Xích Trái Tim).
Một [Awakened] (Thức Tỉnh) bước tới.
Fate Essence (Tinh Hoa Vận Mệnh) trào ra.
[Chain of Heart] chuyển động. [Awakened] lùi lại. Fate Essence dâng lên.
[Shield] bảo vệ Lucid."""


class GlossaryParserTests(unittest.TestCase):
    def test_legacy_keeps_mapping_and_safe_defaults(self):
        entry, = parse_glossary("Chain of Heart = Xiềng Xích Trái Tim")
        self.assertEqual((entry.type, entry.first_vi, entry.brackets, entry.extended), ("Unknown", False, False, False))
        self.assertEqual(entry.serialize(), "Chain of Heart = Xiềng Xích Trái Tim")

    def test_extended_whitespace_booleans_and_unknown_metadata(self):
        entry, = parse_glossary("  Ōhiroma = Heaven’s Judgment  | type = Skill | first_vi = TRUE | brackets = No | canonical=A=B | priority=high")
        self.assertTrue(entry.first_vi)
        self.assertFalse(entry.brackets)
        self.assertEqual(entry.extra_metadata, {"canonical": "A=B", "priority": "high"})
        self.assertEqual(parse_glossary(entry.serialize()), (entry,))

    def test_all_boolean_spellings(self):
        for value, expected in [("TRUE", True), ("False", False), ("YES", True), ("no", False)]:
            with self.subTest(value=value):
                entry, = parse_glossary(f"A = B | first_en={value} | brackets={value}")
                self.assertEqual((entry.first_en, entry.brackets), (expected, expected))

    def test_first_vi_and_first_en_are_mutually_exclusive(self):
        parse_glossary.cache_clear()
        with self.assertLogs("cores.context.glossary", level="WARNING") as logs:
            entry, = parse_glossary("A = B | type=Concept | first_vi=yes | first_en=yes")
        self.assertTrue(entry.first_vi)
        self.assertFalse(entry.first_en)
        self.assertIn("cannot both be yes", " ".join(logs.output))

    def test_invalid_entries_and_duplicates_warn(self):
        parse_glossary.cache_clear()
        with self.assertLogs("cores.context.glossary", level="WARNING") as logs:
            entries = parse_glossary("# Comment\nEnglish =\n= Vietnamese\nA = B | first_vi=yess\nA = C\nA =")
        self.assertEqual(serialize_glossary(entries), "A = C")
        self.assertIn("last valid entry wins", " ".join(logs.output))

    def test_equals_in_target_is_not_split(self):
        self.assertEqual(parse_glossary("A = B=C")[0].vietnamese, "B=C")

    def test_filter_retains_alias_links(self):
        result = filter_glossary("A = B | type=Skill\nOther = Khác\nThe A = Tên khác | type=Alias | canonical=A", "A")
        self.assertIn("The A", result)
        self.assertNotIn("Other", result)

    def test_import_edit_save_and_raw_editor_preserve_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            service = ContextService(lambda _: Path(directory))
            result = service.save("p", {"glossary_text": GLOSSARY + " | priority=high\n旧 = Cũ"})
            result["glossary"][0]["target"] = "Tên đã sửa"
            saved = service.save("p", {"glossary_items": result["glossary"]})
            self.assertTrue(saved["glossary"][0]["first_vi"])
            self.assertEqual(saved["glossary"][-2]["extra_metadata"], {"priority": "high"})
            raw = (Path(directory) / "glossary.txt").read_text(encoding="utf-8")
            self.assertIn("旧 = Cũ", raw)
            self.assertIn("Tên đã sửa | type=Skill", raw)
            service.save("p", {"context_fields": {"index": 0, "glossary": raw}})
            self.assertEqual(service.data("p")["glossary"], saved["glossary"])


class GlossaryValidationTests(unittest.TestCase):
    def setUp(self):
        self.entries = parse_glossary(GLOSSARY)

    def codes(self, text, source=""):
        return {e.code for e in validate_glossary(text, self.entries, source)}

    def test_all_four_valid_cases(self):
        self.assertEqual(validate_glossary(VALID, self.entries), [])

    def test_common_obeys_format_flags_instead_of_overriding_them(self):
        entries = parse_glossary("Empire = Đế Quốc | type=Common | first_vi=yes | brackets=yes")
        self.assertEqual(validate_glossary("[Empire] (Đế Quốc) và [Empire]", entries, "Empire and Empire"), [])
        self.assertIn("missing_first_annotation", {e.code for e in validate_glossary("[Empire]", entries)})
        self.assertIn("vietnamese_without_canonical", {e.code for e in validate_glossary("Đế Quốc", entries)})

    def test_target_only_preserves_type_and_requires_plain_vietnamese(self):
        entries = parse_glossary("blood blade = huyết kiếm | type=Skill | first_vi=yes | brackets=yes | target_only=yes")
        self.assertEqual(validate_glossary("thanh huyết kiếm lóe lên", entries, "A blood blade flashed."), [])
        self.assertNotIn("missing_canonical", {e.code for e in validate_glossary("huyết kiếm", entries, "blood blade")})
        self.assertNotIn("vietnamese_without_canonical", {e.code for e in validate_glossary("huyết kiếm", entries)})
        self.assertIn("target_only_requires_vietnamese", {e.code for e in validate_glossary("blood blade", entries)})
        self.assertIn("target_only_plain_vietnamese", {e.code for e in validate_glossary("[huyết kiếm]", entries)})
        self.assertEqual(entries[0].type, "Skill")
        self.assertEqual(parse_glossary(entries[0].serialize()), entries)

    def test_first_en_uses_vietnamese_primary_and_english_first_annotation(self):
        entries = parse_glossary("Fate Essence = Tinh Hoa Vận Mệnh | type=Concept | first_en=yes | brackets=yes")
        valid = "[Tinh Hoa Vận Mệnh] (Fate Essence) trào lên. [Tinh Hoa Vận Mệnh] dần lắng xuống."
        self.assertEqual(validate_glossary(valid, entries, "Fate Essence surged. Fate Essence settled."), [])
        self.assertIn("missing_first_english_annotation", {e.code for e in validate_glossary("[Tinh Hoa Vận Mệnh]", entries)})
        self.assertIn("repeated_english_annotation", {e.code for e in validate_glossary("[Tinh Hoa Vận Mệnh] (Fate Essence) rồi [Tinh Hoa Vận Mệnh] (Fate Essence)", entries)})
        self.assertIn("english_without_vietnamese", {e.code for e in validate_glossary("Fate Essence", entries)})
        self.assertIn("missing_vietnamese", {e.code for e in validate_glossary("Không có thuật ngữ.", entries, "Fate Essence")})

    def test_first_en_chunk_state_prevents_repeated_english_annotation(self):
        entries = parse_glossary("Fate Essence = Tinh Hoa Vận Mệnh | type=Concept | first_en=yes | brackets=no")
        state = introduced_terms("Tinh Hoa Vận Mệnh (Fate Essence)", entries)
        self.assertEqual(validate_glossary("Tinh Hoa Vận Mệnh", entries, introduced=state), [])

    def test_common_does_not_override_longer_named_term(self):
        entries = parse_glossary("House = Gia Tộc | type=common\nHouse Fenshore = Gia Tộc Fenshore | type=Name | first_vi=yes")
        self.assertEqual(validate_glossary("House Fenshore (Gia Tộc Fenshore). House.", entries), [])

    def test_missing_brackets(self):
        self.assertIn("missing_brackets", self.codes("Awakened (Thức Tỉnh)"))

    def test_nested_brackets(self):
        self.assertIn("nested_brackets", self.codes("[[Awakened]] (Thức Tỉnh)"))

    def test_first_mention_and_repeated_annotation(self):
        self.assertIn("missing_first_annotation", self.codes("[Awakened]"))
        self.assertIn("repeated_annotation", self.codes("[Awakened] (Thức Tỉnh) [Awakened] (Thức Tỉnh)"))

    def test_no_redundant_annotation(self):
        self.assertIn("forbidden_annotation", self.codes("Lucid (Lucid)"))

    def test_vietnamese_only_and_canonical_absence(self):
        self.assertIn("vietnamese_without_canonical", self.codes("người Thức Tỉnh"))
        self.assertIn("missing_canonical", self.codes("Người ấy bước tới.", "An Awakened came."))

    def test_case_spelling_and_longest_term(self):
        self.assertIn("canonical_spelling", self.codes("[awakened] (Thức Tỉnh)"))
        entries = parse_glossary(GLOSSARY + "\nHeart = Tim | type=Concept | first_vi=yes | brackets=yes")
        self.assertEqual(validate_glossary(VALID, entries), [])

    def test_unicode_boundaries_do_not_match_substrings(self):
        self.assertEqual(self.codes("UnAwakened Awakenedness SuperLucid"), set())

    def test_chapter_reset_and_heading_is_not_first_mention(self):
        text = "Chapter 1: Awakened\n[Awakened] (Thức Tỉnh) [Awakened]\nChương 2: Awakened\n[Awakened] (Thức Tỉnh) [Awakened]"
        self.assertEqual(self.codes(text), set())
        self.assertIn("missing_first_annotation", self.codes(text.replace("Chương 2: Awakened\n[Awakened] (Thức Tỉnh)", "Chương 2: Awakened\n[Awakened]")))

    def test_chunk_state_uses_output_only(self):
        state = introduced_terms("[Awakened] (Thức Tỉnh)", self.entries)
        self.assertEqual(validate_glossary("[Awakened]", self.entries, introduced=state), [])
        self.assertEqual(self.codes("[Awakened]"), {"missing_first_annotation"})


class GlossaryPromptTests(unittest.TestCase):
    def test_translation_and_proofreading_structure(self):
        context = f"<GLOSSARY>\n{GLOSSARY}\n</GLOSSARY>\n\nGhi chú văn phong:\nSTYLE"
        chapter = {"title": "TITLE", "content": "SOURCE", "translation": "DRAFT"}
        with patch("cores.translation.prompts._project_prompt", return_value=("ROLE", "TASK")):
            translation = build_single_prompt(chapter, context, "PRONOUNS", "PREVIOUS")
        self.assertIn("ROLE", translation.system)
        self.assertIn("STYLE", translation.system)
        self.assertIn("GLOSSARY FORMATTING RULES", translation.system)
        for value in ("TASK", GLOSSARY, "SOURCE"):
            self.assertIn(value, translation.user)
        polish = build_polish_prompt(chapter, context, "PRONOUNS", role="PROOF ROLE", task="PROOF TASK")
        self.assertIn("PROOF ROLE", polish.system)
        self.assertIn("STYLE", polish.system)
        for value in ("PROOF TASK", "SOURCE", "DRAFT", GLOSSARY):
            self.assertIn(value, polish.user)

    def test_adapters_share_system_and_user_without_losing_browser_rules(self):
        for provider in ("gemini-api", "openai-api", "gemini-web", "chatgpt-web"):
            call = Mock(return_value="response")
            generate_for_stage(provider, "translate", PromptText("SYSTEM", "USER"), "model", "high", {provider: call})
            if provider.endswith("-api"):
                self.assertEqual(call.call_args.args[0], "USER")
                self.assertEqual(call.call_args.kwargs["system_instruction"], "SYSTEM")
            else:
                self.assertIn("SYSTEM", call.call_args.args[0])
                self.assertIn("USER", call.call_args.args[0])

    def test_full_glossary_only_filters_on_context_overflow(self):
        glossary = "A = B | type=Skill\n" + "\n".join(f"Unrelated{i} = Distant{i}" for i in range(100))
        request = PromptText("SYSTEM", glossary + "\nSOURCE A", glossary=glossary, relevance="A")
        self.assertIs(fit_request(request, (), context_tokens=10000, output_tokens=100), request)
        fitted = fit_request(request, (), context_tokens=800, output_tokens=100)
        self.assertIn("SOURCE A", fitted.user)
        self.assertNotIn("Unrelated99", fitted.user)
        with self.assertRaises(ContextBudgetError):
            fit_request(request, [{"content": "x" * 2000}], context_tokens=800, output_tokens=100)

    def test_chunk_boundaries_preserve_every_source_character(self):
        source = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        left, right = split_source(source)
        self.assertEqual(left + right, source)


class GlossaryCorrectionTests(unittest.TestCase):
    def runtime(self, response):
        runtime = Mock()
        runtime.enabled.return_value = True
        runtime.generate.return_value = (response, "openai-api", "proof-model")
        return runtime

    def test_pass_skips_correction(self):
        runtime = self.runtime("")
        result = validate_and_correct(runtime, {"title_translation": "T", "translation": VALID}, GLOSSARY)
        self.assertEqual(result, ("T", VALID))
        runtime.generate.assert_not_called()

    def test_invalid_output_triggers_one_correction(self):
        corrected = "[Awakened] (Thức Tỉnh)"
        response = f"###TITLE###\nT\n###CONTENT###\n{corrected}\n###END###"
        runtime = self.runtime(response)
        chapter = {"content": "Awakened", "title_translation": "T", "translation": "[Awakened]"}
        self.assertEqual(validate_and_correct(runtime, chapter, GLOSSARY), ("T", corrected))
        self.assertTrue(chapter["glossary_validation"]["passed"])
        runtime.generate.assert_called_once()
        self.assertEqual(runtime.generate.call_args.args[0], "polish")

    def test_correction_cannot_delete_or_rewrite_correct_prose(self):
        runtime = self.runtime("###TITLE###\nT\n###CONTENT###\n[Awakened] (Thức Tỉnh)\n###END###")
        chapter = {"content": "Awakened", "title_translation": "T", "translation": "[Awakened] bước tới. Cậu đóng cửa."}
        self.assertEqual(validate_and_correct(runtime, chapter, GLOSSARY)[1], chapter["translation"])

    def test_empty_invalid_and_failed_correction_preserve_proofread(self):
        for response in ("", "###TITLE###\nT\n###CONTENT###\n[Awakened]\n###END###", "###TITLE###\nT\n###CONTENT###\nText without term\n###END###"):
            runtime = self.runtime(response)
            chapter = {"content": "Awakened", "title_translation": "T", "translation": "[Awakened]"}
            self.assertEqual(validate_and_correct(runtime, chapter, GLOSSARY), ("T", "[Awakened]"))
            self.assertFalse(chapter["glossary_validation"]["passed"])
        runtime.generate.side_effect = TimeoutError("timeout")
        self.assertEqual(validate_and_correct(runtime, chapter, GLOSSARY), ("T", "[Awakened]"))


if __name__ == "__main__":
    unittest.main()
