"""Chapter-aware detection only. Never replace words in a translation."""

import re
from dataclasses import dataclass, field


CHAPTER_HEADING = re.compile(r"(?im)^[ \t]*(?:#{1,6}[ \t]*)?(?:chapter|chương|section)[ \t]*\d+[^\n]*\n?")


@dataclass
class ChapterGlossaryState:
    already_introduced: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class GlossaryViolation:
    chapter: int
    term: str
    code: str
    position: int
    excerpt: str

    def __str__(self):
        return f"Chapter {self.chapter}, {self.term!r}, {self.code}, offset {self.position}: {self.excerpt}"


def term_pattern(term):
    return r"(?<!\w)" + re.escape(term) + r"(?!\w)"


def is_target_only(entry):
    """Whether an entry must be rendered as its plain target-language value."""
    value = entry.extra_metadata.get("target_only", "no")
    return entry.type.casefold() == "common" or str(value).strip().casefold() in {"yes", "true"}


def chapter_bodies(text):
    """Exclude chapter headings from first mentions, retaining body offsets."""
    boundaries = list(CHAPTER_HEADING.finditer(text))
    if not boundaries:
        return [(0, text)]
    bodies = []
    if text[:boundaries[0].start()].strip():
        bodies.append((0, text[:boundaries[0].start()]))
    for i, heading in enumerate(boundaries):
        end = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(text)
        bodies.append((heading.end(), text[heading.end():end]))
    return bodies


def validate_glossary(text, entries, source="", *, introduced=()):
    entries = tuple(entries)
    if not entries:
        return []
    by_name = {e.english.casefold(): e for e in entries}
    pattern = re.compile("|".join(term_pattern(e.english) for e in sorted(entries, key=lambda e: len(e.english), reverse=True)), re.I)
    violations = []
    source_bodies = chapter_bodies(source)
    for chapter_index, (offset, body) in enumerate(chapter_bodies(text), 1):
        seen = set(introduced) if chapter_index == 1 else set()
        protected = []
        matches = []
        first_en_output = set()
        def report(entry, code, start, end):
            violations.append(GlossaryViolation(chapter_index, entry.english, code, offset + start,
                                               body[max(0, start - 25):min(len(body), end + 45)]))
        # first_en reverses the normal display: Vietnamese is primary and English
        # is attached only to the first mention. Scan it first so its English
        # annotation is protected from the canonical-English pass below.
        for entry in sorted(entries, key=lambda e: len(e.vietnamese), reverse=True):
            if not entry.extended or not entry.first_en or is_target_only(entry):
                continue
            for match in re.finditer(term_pattern(entry.vietnamese), body, re.I):
                start, end = match.span()
                if any(a < end and start < b for a, b in protected):
                    continue
                bracketed = start > 0 and body[start - 1] == "[" and body[end:end + 1] == "]"
                suffix = end + 1 if bracketed else end
                annotation = re.match(r"[ \t]*\(([^)\n]*)\)", body[suffix:])
                protected.append((start, end))
                if annotation:
                    protected.append((suffix, suffix + annotation.end()))
                first_en_output.add(entry.english)
                if match.group() != entry.vietnamese:
                    report(entry, "target_spelling", start, end)
                if entry.brackets != bracketed:
                    report(entry, "missing_brackets" if entry.brackets else "unexpected_brackets", start, end)
                if bracketed and (body[max(0, start - 2):start] == "[[" or body[suffix:suffix + 1] == "]"):
                    report(entry, "nested_brackets", start, suffix)
                expected = entry.english not in seen and entry.english.casefold() != entry.vietnamese.casefold()
                if expected and (not annotation or annotation[1] != entry.english):
                    report(entry, "missing_first_english_annotation", start, end)
                elif annotation and annotation[1] == entry.english and not expected:
                    report(entry, "repeated_english_annotation", start, suffix + annotation.end())
                elif annotation and expected and annotation[1] != entry.english:
                    report(entry, "incorrect_english_annotation", start, suffix + annotation.end())
                seen.add(entry.english)
        for match in pattern.finditer(body):
            start, end = match.span()
            if any(a <= start < b for a, b in protected):
                continue
            entry = by_name[match.group().casefold()]
            bracketed = start > 0 and body[start - 1] == "[" and body[end:end + 1] == "]"
            suffix = end + 1 if bracketed else end
            annotation = re.match(r"[ \t]*\(([^)\n]*)\)", body[suffix:])
            if annotation:
                protected.append((suffix, suffix + annotation.end()))
            matches.append((entry, start, end))
            # A longest legacy/common phrase also shields its substrings.
            protected.append((start, end))
            if not entry.extended:
                if annotation and entry.english == entry.vietnamese and annotation[1] == entry.vietnamese:
                    report(entry, "redundant_annotation", start, suffix + annotation.end())
                continue
            if is_target_only(entry):
                prefix = "common" if entry.type.casefold() == "common" else "target_only"
                if entry.english.casefold() != entry.vietnamese.casefold():
                    report(entry, f"{prefix}_requires_vietnamese", start, suffix + annotation.end() if annotation else end)
                elif bracketed or annotation:
                    report(entry, f"{prefix}_plain_vietnamese", start, suffix + annotation.end() if annotation else end)
                continue
            if entry.first_en:
                report(entry, "english_without_vietnamese", start, suffix + annotation.end() if annotation else end)
                continue
            if match.group() != entry.english:
                report(entry, "canonical_spelling", start, end)
            if entry.brackets != bracketed:
                report(entry, "missing_brackets" if entry.brackets else "unexpected_brackets", start, end)
            if bracketed and (body[max(0, start - 2):start] == "[[" or body[suffix:suffix + 1] == "]"):
                report(entry, "nested_brackets", start, suffix)
            expected = entry.first_vi and entry.english not in seen and entry.english != entry.vietnamese
            if expected and (not annotation or annotation[1] != entry.vietnamese):
                report(entry, "missing_first_annotation", start, end)
            elif annotation and annotation[1] == entry.vietnamese and not expected:
                report(entry, "repeated_annotation" if entry.first_vi and entry.english != entry.vietnamese else "forbidden_annotation", start, suffix + annotation.end())
            elif annotation and expected and annotation[1] != entry.vietnamese:
                report(entry, "incorrect_annotation", start, suffix + annotation.end())
            seen.add(entry.english)

        source_body = source_bodies[min(chapter_index - 1, len(source_bodies) - 1)][1]
        source_terms = {by_name[m.group().casefold()].english for m in pattern.finditer(source_body)}
        output_terms = {entry.english for entry, _, _ in matches}
        for entry in entries:
            if not entry.extended or is_target_only(entry) or entry.english not in source_terms:
                continue
            if entry.first_en:
                if entry.english not in first_en_output:
                    report(entry, "missing_vietnamese", 0, 0)
            elif entry.english not in output_terms:
                report(entry, "missing_canonical", 0, 0)
        # Detect Vietnamese-only substitutions outside attached explanations.
        for entry in sorted(entries, key=lambda e: len(e.vietnamese), reverse=True):
            if not entry.extended or entry.english.casefold() == entry.vietnamese.casefold():
                continue
            if entry.first_en:
                continue
            if is_target_only(entry):
                prefix = "common" if entry.type.casefold() == "common" else "target_only"
                for match in re.finditer(term_pattern(entry.vietnamese), body, re.I):
                    if any(a < match.end() and match.start() < b for a, b in protected):
                        continue
                    start, end = match.span()
                    if start > 0 and body[start - 1] == "[" and body[end:end + 1] == "]":
                        report(entry, f"{prefix}_plain_vietnamese", start, end)
                    protected.append(match.span())
                continue
            for match in re.finditer(term_pattern(entry.vietnamese), body, re.I):
                if any(a < match.end() and match.start() < b for a, b in protected):
                    continue
                report(entry, "vietnamese_without_canonical", *match.span())
                protected.append(match.span())
    return violations


def introduced_terms(text, entries):
    """Update chunk state from story output only, never from a prompt."""
    last_body = chapter_bodies(text)[-1][1]
    if not entries:
        return set()
    by_name = {e.english.casefold(): e for e in entries}
    pattern = re.compile("|".join(term_pattern(e.english) for e in sorted(entries, key=lambda e: len(e.english), reverse=True)), re.I)
    introduced = {by_name[m.group().casefold()].english for m in pattern.finditer(last_body)
                  if by_name[m.group().casefold()].extended and not by_name[m.group().casefold()].first_en}
    for entry in entries:
        if entry.extended and entry.first_en and re.search(term_pattern(entry.vietnamese), last_body, re.I):
            introduced.add(entry.english)
    return introduced


def glossary_prose_signature(text, entries):
    """Comparison only: ignore glossary spelling/formatting, preserve all other prose."""
    entries = sorted(entries, key=lambda e: max(len(e.english), len(e.vietnamese)), reverse=True)
    if not entries:
        return text
    patterns = []
    for index, entry in enumerate(entries):
        vi_annotation = r"(?:[ \t]*\(" + re.escape(entry.vietnamese) + r"\))?"
        en_annotation = r"(?:[ \t]*\(" + re.escape(entry.english) + r"\))?"
        canonical = r"\[*" + term_pattern(entry.english) + vi_annotation + r"\]*" + vi_annotation
        translated = r"\[*" + term_pattern(entry.vietnamese) + r"\]*" + en_annotation
        patterns.append(f"(?P<t{index}>{canonical}|{translated})")
    matcher = re.compile("|".join(patterns), re.I)
    signature = matcher.sub(lambda match: "§" + entries[int(match.lastgroup[1:])].english + "§", text)
    return re.sub(r"\s+", " ", signature).strip()
