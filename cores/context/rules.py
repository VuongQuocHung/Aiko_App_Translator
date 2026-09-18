"""Glossary rules shared with the standalone browser client."""

from pathlib import Path

GLOSSARY_RULES = (Path(__file__).resolve().parents[2] / "defaults" / "glossary_rules.txt").read_text(encoding="utf-8")
