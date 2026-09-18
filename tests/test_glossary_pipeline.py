import importlib
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from cores.context.glossary import parse_glossary
from cores.context.validation import introduced_terms
from cores.postprocess.pipeline import run_post_translation_pipeline
from cores.postprocess.polish import polish_translation
from cores.translation import stage
from cores.translation import runner

runtime_module = importlib.import_module("cores.postprocess.runtime")
GLOSSARY = "Awakened = Thức Tỉnh | type=Rank | first_vi=yes | brackets=yes\nHeart = Tim | type=Concept | first_vi=yes | brackets=yes\nChain of Heart = Xiềng Xích Trái Tim | type=Skill | first_vi=yes | brackets=yes"


def output(content):
    return f"###TITLE###\nT\n###CONTENT###\n{content}\n###END###"


class GlossaryPipelineTests(unittest.TestCase):
    def test_mixed_provider_pipeline_translates_proofreads_and_corrects(self):
        calls = []
        def translate(prompt, **kwargs):
            calls.append(("translate", prompt, kwargs))
            return output("[Awakened]")
        def proofread(prompt, **kwargs):
            calls.append(("proofread", prompt, kwargs))
            return output("[Awakened] (Thức Tỉnh)" if "ERRORS:" in prompt else "[Awakened]")
        values = {"translate_provider": "gemini-api", "polish_provider": "openai-api",
                  "translate_stage_model": "translation-only", "polish_stage_model": "proofreading-only",
                  "pronouns_provider": "off", "r19_mode": False}
        option = lambda key, default=None: values.get(key, default)
        chapter = {"id": "test", "title": "Source title", "content": "Awakened"}
        with patch.object(stage, "option", side_effect=option), patch.object(runtime_module, "option", side_effect=option), \
             patch.dict(stage.TRANSPORT_OVERRIDES, {"gemini-api": translate, "openai-api": proofread}, clear=True), \
             patch.object(stage, "build_reference_documents", return_value=()), patch.object(stage, "log_api_call"), \
             patch.object(runtime_module.runtime, "log_api_call"), \
             patch("cores.postprocess.polish.build_characters_snapshot", return_value=None):
            title, draft = stage.translate_chapter(chapter, 1, GLOSSARY)
            chapter.update(title_translation=title, translation=draft)
            result = run_post_translation_pipeline(runtime_module.runtime, chapter, 1, GLOSSARY, "", None)
        self.assertEqual(result, ("T", "[Awakened] (Thức Tỉnh)"))
        self.assertEqual([call[0] for call in calls], ["translate", "proofread", "proofread"])
        self.assertEqual(calls[0][2]["model"], "translation-only")
        self.assertEqual(calls[1][2]["model"], "proofreading-only")
        self.assertIn("ENGLISH ORIGINAL", calls[1][1])
        for _, prompt, options in calls:
            self.assertIn("Chain of Heart", prompt)  # Full glossary, even absent in source.
            self.assertIn("GLOSSARY FORMATTING RULES", options["system_instruction"])

    def test_chunk_translation_retains_source_and_per_chapter_state(self):
        seen = []
        source = "Awakened arrives.\n\nAwakened leaves."
        def whole(chapter, *_args):
            seen.append(chapter)
            return "T", "[Awakened]" + ("" if chapter["_glossary_introduced"] else " (Thức Tỉnh)")
        chapter = {"id": "one", "title": "T", "content": source}
        with patch.object(stage, "_translate_whole", side_effect=whole), \
             patch.object(stage, "stage_limits", return_value=(5000, 20)):
            _, result = stage.translate_chapter(chapter, 1, GLOSSARY)
        self.assertEqual("".join(s["content"] for s in chapter["_translation_segments"]), source)
        self.assertEqual(result.count("(Thức Tỉnh)"), 1)
        self.assertEqual(seen[0]["_glossary_introduced"], [])
        self.assertIn("Awakened", seen[1]["_glossary_introduced"])
        with patch.object(stage, "_translate_whole", side_effect=whole):
            stage.translate_chapter({"id": "two", "content": "Awakened"}, 2, GLOSSARY)
        self.assertEqual(seen[-1]["_glossary_introduced"], [])

    def test_chunk_proofreading_has_independent_first_mention_state(self):
        runtime = Mock()
        runtime.model_and_thinking.return_value = ("model", "high")
        runtime.provider.return_value = "openai-api"
        runtime.project_polish_prompt.return_value = ("ROLE", "TASK")
        runtime.int_option.return_value = 20
        prompts = []
        def generate(_stage, prompt, _attachments):
            prompts.append(prompt)
            text = "[Awakened]" + ("" if "\nTERMS ALREADY INTRODUCED IN THIS CHAPTER:\n" in prompt.system else " (Thức Tỉnh)")
            return output(text), "openai-api", "model"
        runtime.generate.side_effect = generate
        segment = {"title": "T", "content": "Awakened", "title_translation": "T", "translation": "[Awakened]"}
        chapter = {"_translation_segments": [segment, {**segment, "_glossary_introduced": ["Awakened"]}]}
        with patch("cores.postprocess.polish.build_characters_snapshot", return_value=None):
            _, result = polish_translation(runtime, chapter, 1, GLOSSARY, "", "", None)
        self.assertEqual(result.count("(Thức Tỉnh)"), 1)
        self.assertNotIn("\nTERMS ALREADY INTRODUCED IN THIS CHAPTER:\n", prompts[0].system)
        self.assertIn("\nTERMS ALREADY INTRODUCED IN THIS CHAPTER:\n", prompts[1].system)

    def test_chunk_state_prefers_longest_match(self):
        self.assertEqual(introduced_terms("[Chain of Heart] (Xiềng Xích Trái Tim)", parse_glossary(GLOSSARY)), {"Chain of Heart"})

    def test_translation_failure_does_not_invoke_proofreading(self):
        proofread = Mock()
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, "_export_recent_translations"):
            raw = Path(directory) / "raw"
            raw.mkdir()
            (raw / "v1_c1_s1.md").write_text("# Title\n\nAwakened", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "translation failed"):
                runner.run_single_translation(Mock(side_effect=RuntimeError("translation failed")), raw,
                    Path(directory) / "translated", Path(directory) / "context.json", postprocess=proofread)
        proofread.assert_not_called()


if __name__ == "__main__":
    unittest.main()
