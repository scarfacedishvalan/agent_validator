from __future__ import annotations

import os
from typing import Any, Mapping, Sequence


Message = Mapping[str, str]
Tool = Mapping[str, Any]


class AISuiteLLMClient:
    """Small AISuite chat client configured for OpenAI JSON responses."""

    def __init__(self, model: str = "openai:gpt-4o") -> None:
        if not os.environ.get("OPENAI_API_KEY", "").strip():
            raise RuntimeError("Set the OPENAI_API_KEY environment variable before calling the LLM.")

        import aisuite as ai

        self._client = ai.Client()
        self._model = model

    def complete(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Tool] | None = None,
    ) -> str:
        """Return the assistant's JSON-mode response content.

        `tools` is reserved for a future tool-calling implementation and is not sent.
        """
        del tools
        response = self._client.chat.completions.create(
            model=self._model,
            messages=list(messages),
            response_format={"type": "json_object"},
        )
        choices = getattr(response, "choices", None)
        if not choices:
            raise ValueError("AISuite returned no completion choices.")

        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise ValueError("AISuite returned an empty or non-text completion.")
        return content


if __name__ == "__main__":
    client = AISuiteLLMClient()
    print(client.complete([{"role": "user", "content": "Return an example json object"}]))