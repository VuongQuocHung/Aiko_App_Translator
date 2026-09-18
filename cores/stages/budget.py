"""Conservative configurable context estimates; never silently truncate prose."""

import math
import re

from cores.context.glossary import filter_glossary
from cores.translation.request import PromptText


class ContextBudgetError(ValueError):
    pass


def estimate_tokens(text):
    # Language-independent conservative estimate, not a provider token counter.
    return math.ceil(len(str(text).encode("utf-8")) / 2)


def fit_request(prompt, attachments, *, context_tokens, output_tokens):
    documents = sum(estimate_tokens(d.get("content", "")) for d in attachments)
    def fits(value):
        return estimate_tokens(value) + documents + output_tokens + 512 <= context_tokens
    if fits(prompt):
        return prompt
    if isinstance(prompt, PromptText) and prompt.glossary:
        relevant = filter_glossary(prompt.glossary, prompt.relevance)
        user = prompt.user.replace(prompt.glossary, relevant, 1)
        filtered = prompt.with_user(user, glossary=relevant)
        if fits(filtered):
            print("[CONTEXT] Ước lượng vượt giới hạn; gửi glossary liên quan và các alias.")
            return filtered
    raise ContextBudgetError("Nội dung và prompt vượt ngân sách context; cần chia chương hoặc tăng giới hạn đúng với model. Không cắt nguồn.")


def split_source(text):
    """Bisect at paragraphs/sentence boundaries, preserving every character."""
    midpoint = len(text) // 2
    for pattern in (r"\n\s*\n", r"[.!?。！？][\s]+", r"\s+"):
        boundaries = [m.end() for m in re.finditer(pattern, text) if len(text) // 5 < m.end() < len(text) * 4 // 5]
        if boundaries:
            cut = min(boundaries, key=lambda position: abs(position - midpoint))
            return text[:cut], text[cut:]
    raise ContextBudgetError("Không tìm thấy ranh giới an toàn để chia nguồn quá dài; hãy tăng context hoặc chia chương tại đoạn văn.")


def stage_limits(stage, provider, get_option):
    def positive(name, default):
        try:
            return max(1, int(get_option(name, default) or default))
        except (TypeError, ValueError):
            return default
    context = positive(f"{stage}_context_tokens", 128000)
    output_key = "gpt_api_max_output_tokens" if provider == "openai-api" else "gemini_api_max_output_tokens"
    return context, positive(output_key, 30000)
