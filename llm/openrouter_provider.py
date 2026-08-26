import logging

from openai import APIStatusError, OpenAI

from exceptions import LLMProviderError

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

logger = logging.getLogger(__name__)


class OpenRouterProvider:
    def __init__(self, api_key, models):
        self.client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
        self.models = models if isinstance(models, list) else [models]

    def complete(self, system, user, max_tokens):
        last_error = None
        for model in self.models:
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
            except APIStatusError as exc:
                last_error = exc
                logger.warning("model=%s failed (%s), trying next fallback", model, exc)
                continue
            choice = response.choices[0]
            return {
                "text": choice.message.content,
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
                "finish_reason": choice.finish_reason,
                "model": model,
            }
        raise LLMProviderError(f"All models failed: {self.models} -- last error: {last_error}")
