"""Read, validate, and safely update project context and glossary data."""

import json

from cores.storage.project import load_context, save_context
from cores.context.glossary import GlossaryEntry, parse_boolean, parse_glossary, serialize_glossary
from cores.translation.prompts import (
    DEFAULT_POLISH_ROLE,
    DEFAULT_POLISH_TASK,
    DEFAULT_ROLE,
    DEFAULT_TASK,
    POLISH_PROMPT_PRESETS,
    PROMPT_PRESETS,
    polish_prompt_presets_payload,
    prompt_presets_payload,
)


class ContextService:
    def __init__(self, safe_project):
        self._safe_project = safe_project

    def data(self, project_name):
        project = self._safe_project(project_name)
        path = project / "context.json"
        if not path.exists() and not (project / "glossary.txt").exists():
            return self._payload({}, "")
        data = load_context(project)
        if not isinstance(data, dict):
            raise ValueError("context.json không hợp lệ")
        raw_json = json.dumps(data, ensure_ascii=False, indent=2)
        return self._payload(data, raw_json)

    @staticmethod
    def _payload(data, raw_json):
        glossary = [entry.payload() for entry in parse_glossary(str(data.get("glossary", "")))]
        return {
            "index": data.get("index", 0),
            "glossary": glossary,
            "style_notes": str(data.get("style_notes", "")).strip(),
            "prompt_preset": str(data.get("prompt_preset", "default")),
            "prompt_role": str(data.get("prompt_role", "")).strip()
            or DEFAULT_ROLE,
            "prompt_task": str(data.get("prompt_task", "")).strip()
            or DEFAULT_TASK,
            "prompt_presets": prompt_presets_payload(),
            "polish_prompt_preset": str(
                data.get("polish_prompt_preset", "default")
            ),
            "polish_prompt_role": str(
                data.get("polish_prompt_role", "")
            ).strip()
            or DEFAULT_POLISH_ROLE,
            "polish_prompt_task": str(
                data.get("polish_prompt_task", "")
            ).strip()
            or DEFAULT_POLISH_TASK,
            "polish_prompt_presets": polish_prompt_presets_payload(),
            "raw_json": raw_json,
        }

    def save(self, project_name, payload):
        project = self._safe_project(project_name)
        path = project / "context.json"
        if "glossary_items" in payload:
            return self._save_glossary_items(project_name, path, payload)
        if "context_fields" in payload:
            return self._save_fields(project_name, path, payload)
        if "raw_json" in payload or "raw_yaml" in payload:
            return self._save_raw(project_name, project, payload)
        return self._import_glossary(project_name, project, payload)

    def _save_glossary_items(self, project_name, path, payload):
        items = payload.get("glossary_items")
        if not isinstance(items, list):
            raise ValueError("Dữ liệu glossary không hợp lệ")
        data = self._current(path.parent)
        previous = {entry.english: entry for entry in parse_glossary(str(data.get("glossary", "")))}
        glossary_lines = []
        for number, item in enumerate(items, 1):
            if not isinstance(item, dict):
                raise ValueError(f"Glossary sai định dạng tại dòng {number}")
            source = str(item.get("source", "")).strip()
            target = str(item.get("target", "")).strip()
            if source in previous:
                item = {**previous[source].payload(), **item}
            if not source or not target or "=" in source or any(c in source + target for c in "\r\n|"):
                raise ValueError(f"Glossary sai định dạng tại dòng {number}")
            extra = item.get("extra_metadata", {})
            if not isinstance(extra, dict) or any(any(c in str(k) + str(v) for c in "\r\n|") or "=" in str(k) for k, v in extra.items()):
                raise ValueError(f"Metadata sai định dạng tại dòng {number}")
            kind = str(item.get("type", "Unknown")).strip() or "Unknown"
            if any(c in kind for c in "\r\n|"):
                raise ValueError(f"Type sai định dạng tại dòng {number}")
            first_vi = parse_boolean(item.get("first_vi", False))
            first_en = parse_boolean(item.get("first_en", False))
            if first_vi and first_en:
                first_en = False
            glossary_lines.append(GlossaryEntry(source, target, kind, first_vi, first_en,
                parse_boolean(item.get("brackets", False)),
                {str(k): str(v) for k, v in extra.items() if k not in {"type", "first_vi", "first_en", "brackets"}},
                parse_boolean(item.get("extended", False))).serialize())
        data["glossary"] = serialize_glossary(parse_glossary("\n".join(glossary_lines)))
        self._write(path.parent, data)
        result = self.data(project_name)
        result["backup"] = path.with_name(path.name + ".bak").exists()
        return result

    def _save_fields(self, project_name, path, payload):
        fields = payload.get("context_fields")
        if not isinstance(fields, dict):
            raise ValueError("Dữ liệu context không hợp lệ")
        try:
            index = int(fields.get("index", 0))
        except (TypeError, ValueError):
            raise ValueError("Tiến độ chương phải là số nguyên") from None
        raw_count = len(list((path.parent / "raw").glob("*.md")))
        if index < 0 or (raw_count and index > raw_count):
            raise ValueError(f"Tiến độ chương phải nằm trong khoảng 0–{raw_count}")
        glossary_lines = self._glossary_lines(fields.get("glossary", ""))
        data = self._current(path.parent)
        if data.get("glossary") and not glossary_lines:
            raise ValueError("Không thể xóa toàn bộ glossary trong một lần lưu")
        data["index"] = index
        data["glossary"] = "\n".join(glossary_lines)
        data["style_notes"] = str(fields.get("style_notes", "")).strip()
        self._save_prompt_fields(data, fields)
        self._write(path.parent, data)
        result = self.data(project_name)
        result["backup"] = path.with_name(path.name + ".bak").exists()
        return result

    @staticmethod
    def _glossary_lines(value):
        return [entry.serialize() for entry in parse_glossary(str(value))]

    @staticmethod
    def _save_prompt_fields(data, fields):
        prompt_preset = str(
            fields.get("prompt_preset", data.get("prompt_preset", "default"))
        ).strip()
        if prompt_preset not in {*PROMPT_PRESETS, "custom"}:
            raise ValueError("Preset prompt không hợp lệ")
        prompt_role = str(
            fields.get("prompt_role", data.get("prompt_role", DEFAULT_ROLE))
        ).strip()
        prompt_task = str(
            fields.get("prompt_task", data.get("prompt_task", DEFAULT_TASK))
        ).strip()
        if not prompt_role or len(prompt_role) > 100000:
            raise ValueError("Prompt vai trò phải có từ 1 đến 100.000 ký tự")
        if not prompt_task or len(prompt_task) > 100000:
            raise ValueError("Prompt nhiệm vụ phải có từ 1 đến 100.000 ký tự")
        polish_preset = str(
            fields.get(
                "polish_prompt_preset",
                data.get("polish_prompt_preset", "default"),
            )
        ).strip()
        if polish_preset not in {*POLISH_PROMPT_PRESETS, "custom"}:
            raise ValueError("Mẫu prompt hiệu đính không hợp lệ")
        polish_role = str(
            fields.get(
                "polish_prompt_role",
                data.get("polish_prompt_role", DEFAULT_POLISH_ROLE),
            )
        ).strip()
        polish_task = str(
            fields.get(
                "polish_prompt_task",
                data.get("polish_prompt_task", DEFAULT_POLISH_TASK),
            )
        ).strip()
        if not polish_role or len(polish_role) > 100000:
            raise ValueError("Vai trò hiệu đính phải có từ 1 đến 100.000 ký tự")
        if not polish_task or len(polish_task) > 100000:
            raise ValueError("Nhiệm vụ hiệu đính phải có từ 1 đến 100.000 ký tự")
        data.update(
            {
                "prompt_preset": prompt_preset,
                "prompt_role": prompt_role,
                "prompt_task": prompt_task,
                "polish_prompt_preset": polish_preset,
                "polish_prompt_role": polish_role,
                "polish_prompt_task": polish_task,
            }
        )

    def _save_raw(self, project_name, project, payload):
        raw_json = str(payload.get("raw_json", payload.get("raw_yaml", "")))
        try:
            data = json.loads(raw_json) if raw_json.strip() else {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"context.json không hợp lệ: {exc}") from None
        if not isinstance(data, dict):
            raise ValueError("context.json phải là một object")
        self._write(project, data)
        return self.data(project_name)

    def _import_glossary(self, project_name, project, payload):
        incoming = parse_glossary(str(payload.get("glossary_text", "")))
        if not incoming:
            raise ValueError("Chưa có thuật ngữ hợp lệ để nạp")
        data = self._current(project)
        data["glossary"] = serialize_glossary(parse_glossary(str(data.get("glossary", "")) + "\n" + serialize_glossary(incoming)))
        self._write(project, data)
        result = self.data(project_name)
        result["imported"] = len(incoming)
        return result

    @staticmethod
    def _current(project):
        data = load_context(project)
        if not isinstance(data, dict):
            raise ValueError("context.json hiện tại không hợp lệ")
        return data

    @staticmethod
    def _write(project, data):
        save_context(project, data, backup=True)
