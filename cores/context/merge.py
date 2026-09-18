"""Merge generated glossary text into project context state."""

from dataclasses import replace
from cores.context.glossary import parse_glossary, serialize_glossary


def merge_context(old, new_text):
    if not new_text.strip():
        return old

    if "###START###" in new_text and "###END###" in new_text:
        start = new_text.index("###START###") + len("###START###")
        end = new_text.index("###END###")
        new_text = new_text[start:end]
    elif "###START###" in new_text:
        start = new_text.index("###START###") + len("###START###")
        new_text = new_text[start:]

    previous = {entry.english: entry for entry in parse_glossary(str(old.get("glossary", "")))}
    incoming = []
    for entry in parse_glossary(new_text):
        existing = previous.get(entry.english)
        if existing and existing.extended and not entry.extended:
            entry = replace(existing, vietnamese=entry.vietnamese)
        incoming.append(entry)
    old["glossary"] = serialize_glossary(parse_glossary(
        serialize_glossary(previous.values()) + "\n" + serialize_glossary(incoming)))
    return old
