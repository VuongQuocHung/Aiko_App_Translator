"""OpenAI API provider adapter."""

from providers.base import ProviderAdapter, ProviderResponse


class OpenAiApiProvider(ProviderAdapter):
    id = "openai-api"
    label = "OpenAI API"

    def generate(self, request):
        text = self._generate(
            request.prompt,
            model=request.model,
            reasoning_effort=request.thinking,
            stage=request.stage,
            documents=list(request.attachments) or None,
            **({"system_instruction": request.system_instruction} if request.system_instruction else {}),
            **request.options,
        )
        return ProviderResponse(str(text or ""), self.id, request.model)
