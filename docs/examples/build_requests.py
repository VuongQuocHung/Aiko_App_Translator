"""Generate reviewable example requests locally, without contacting any provider."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["NOVEL_PROJECT"] = ""
os.environ["NOVEL_WEB_CONFIG"] = json.dumps({"r19_mode": False})

from cores.translation.prompts import build_single_prompt, build_polish_prompt, build_correction_prompt
from cores.context.glossary import parse_glossary
from cores.context.validation import validate_glossary

folder = Path(__file__).parent
glossary = (folder / "glossary.txt").read_text(encoding="utf-8")
context = "<GLOSSARY>\n" + glossary.strip() + "\n</GLOSSARY>\n\nGhi chú văn phong:\n<STYLE_PROMPT>\nGiữ nhịp kể của nguyên tác; hội thoại tự nhiên.\n</STYLE_PROMPT>"
chapter = {
    "title": "Chapter 100",
    "content": "Lucid activated Chain of Heart. An Awakened stepped forward. Fate Essence filled the room. The Awakened stopped.",
    "title_translation": "Chương 100",
    "translation": "Lucid kích hoạt [Chain of Heart] (Xiềng Xích Trái Tim). Một [Awakened] bước tới. Fate Essence (Tinh Hoa Vận Mệnh) tràn khắp phòng. Người [Awakened] dừng lại.",
}
errors = validate_glossary(chapter["translation"], parse_glossary(glossary), chapter["content"])
requests = {
    "translation": build_single_prompt(chapter, context, "", ""),
    "proofreading": build_polish_prompt(chapter, context, ""),
    "correction": build_correction_prompt(chapter, context, errors),
}
for stage, request in requests.items():
    (folder / f"{stage}_request.json").write_text(json.dumps({"system_instruction": request.system, "user_content": request.user}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Generated translation, proofreading and correction requests; no API calls.")
