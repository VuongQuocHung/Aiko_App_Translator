"""Provider-independent generation for pipeline stages."""

from providers import ProviderRequest, create_provider
from cores.translation.request import PromptText


def generate_for_stage(
    provider_id,
    stage,
    prompt,
    model,
    thinking,
    transports,
    attachments=(),
    options=None,
):
    try:
        transport = transports[provider_id]
    except KeyError as error:
        raise ValueError(f"Chưa cấu hình transport cho provider {provider_id}") from error
    provider = create_provider(provider_id, transport, stage)
    system = prompt.system if isinstance(prompt, PromptText) else ""
    # Browser providers have one message field; API providers expose system instructions.
    user = prompt.user if isinstance(prompt, PromptText) and provider_id in {"openai-api", "gemini-api"} else str(prompt)
    request = ProviderRequest(
        stage=stage,
        prompt=user,
        system_instruction=system,
        model=model,
        thinking=thinking,
        attachments=tuple(attachments or ()),
        options=dict(options or {}),
    )
    return provider.generate(request)
