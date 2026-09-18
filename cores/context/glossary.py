"""Parse and filter glossary.txt entries against source text."""

import re
import logging
from dataclasses import dataclass, field
from functools import lru_cache

logger = logging.getLogger(__name__)
GLOSSARY_TYPES = tuple("Skill Ability Trait Rank Title Concept System Artifact Organization Faction Place World Species Name Common Alias Unknown".split())


@dataclass(frozen=True)
class GlossaryEntry:
    english: str
    vietnamese: str
    type: str = "Unknown"
    first_vi: bool = False
    first_en: bool = False
    brackets: bool = False
    extra_metadata: dict[str, str] = field(default_factory=dict)
    # Legacy source -> translation mappings retain their original semantics.
    extended: bool = False

    def __post_init__(self):
        if self.type != "Unknown" or self.first_vi or self.first_en or self.brackets or self.extra_metadata:
            object.__setattr__(self, "extended", True)

    def serialize(self):
        line = f"{self.english} = {self.vietnamese}"
        if self.extended or self.type != "Unknown" or self.first_vi or self.first_en or self.brackets or self.extra_metadata:
            line += f" | type={self.type} | first_vi={'yes' if self.first_vi else 'no'} | first_en={'yes' if self.first_en else 'no'} | brackets={'yes' if self.brackets else 'no'}"
            line += "".join(f" | {key}={value}" for key, value in self.extra_metadata.items())
        return line

    def payload(self):
        return dict(source=self.english, target=self.vietnamese, type=self.type,
                    first_vi=self.first_vi, first_en=self.first_en, brackets=self.brackets,
                    extra_metadata=dict(self.extra_metadata), extended=self.extended)


def parse_boolean(value, *, field_name="boolean"):
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized not in {"yes", "no", "true", "false"}:
        logger.warning("Glossary: invalid %s=%r; using no", field_name, value)
    return normalized in {"yes", "true"}


@lru_cache(maxsize=16)
def parse_glossary(text):
    """Parse once per text revision; last valid entry wins, with warnings."""
    entries = {}
    for number, raw in enumerate(str(text or "").splitlines(), 1):
        line = raw.strip().lstrip("\ufeff")
        if not line or line.startswith("#"):
            continue
        mapping, *metadata = line.split("|")
        source, separator, target = mapping.partition("=")
        source, target = source.strip(), target.strip()
        if not separator or not source or not target:
            logger.warning("Glossary: skipping invalid entry at line %s", number)
            continue
        fields = {}
        for item in metadata:
            key, equals, value = item.partition("=")
            if not equals or not key.strip():
                logger.warning("Glossary: invalid metadata at line %s", number)
                continue
            fields[key.strip().lower()] = value.strip()
        kind = fields.pop("type", "Unknown") or "Unknown"
        kind = next((t for t in GLOSSARY_TYPES if t.lower() == kind.lower()), kind)
        first_vi = parse_boolean(fields.pop("first_vi", "no"), field_name="first_vi")
        first_en = parse_boolean(fields.pop("first_en", "no"), field_name="first_en")
        if first_vi and first_en:
            logger.warning("Glossary: first_vi and first_en cannot both be yes at line %s; keeping first_vi", number)
            first_en = False
        entry = GlossaryEntry(source, target, kind, first_vi, first_en,
                              parse_boolean(fields.pop("brackets", "no"), field_name="brackets"),
                              fields, bool(metadata))
        if source in entries:
            logger.warning("Glossary: duplicate %r at line %s; last valid entry wins", source, number)
        entries[source] = entry
    return tuple(entries.values())


def serialize_glossary(entries):
    return "\n".join(entry.serialize() for entry in entries)


def glossary_from_context(context):
    """Read only the delimited glossary, never style notes/reference chapters."""
    if "<GLOSSARY>\n" in context:
        return context.split("<GLOSSARY>\n", 1)[1].split("\n</GLOSSARY>", 1)[0]
    # Compatibility for callers supplying a bare glossary.
    return "\n".join(line for line in context.splitlines() if "=" in line and not line.lstrip().startswith("#"))


def glossary_source_is_relevant(source, raw_text):
    searchable = (raw_text or "").casefold()
    source_folded = source.casefold()
    if source_folded in searchable:
        return True

    raw_cjk_terms = re.findall(
        r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3]+", searchable
    )
    if any(term in source_folded for term in raw_cjk_terms):
        return True

    source_words = set(re.findall(r"[^\W_]+", source_folded, flags=re.UNICODE))
    raw_words = set(re.findall(r"[^\W_]+", searchable, flags=re.UNICODE))
    return bool(source_words & raw_words)


def filter_glossary(glossary_text, raw_text):
    """Keep glossary entries related to words found in the given chapters."""
    entries = parse_glossary(glossary_text)
    matched = {entry.english for entry in entries if glossary_source_is_relevant(entry.english, raw_text)
               or glossary_source_is_relevant(entry.vietnamese, raw_text)}
    # Preserve explicit aliases and aliases sharing a target, transitively.
    while True:
        targets = {e.vietnamese for e in entries if e.english in matched}
        linked = {e.extra_metadata.get("canonical") for e in entries if e.english in matched}
        updated = matched | {e.english for e in entries if e.vietnamese in targets
                             or e.english in linked or e.extra_metadata.get("canonical") in matched}
        if updated == matched:
            break
        matched = updated
    return serialize_glossary(e for e in entries if e.english in matched)
