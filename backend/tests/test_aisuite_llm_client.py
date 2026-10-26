import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from openai.types.completion_usage import CompletionUsage

from app.services.utils.aisuite_llm_client import AISuiteLLMClient


class AISuiteLLMClientTests(unittest.TestCase):
    def test_captures_provider_usage_and_clears_it_after_a_request_error(self):
        sdk_client = Mock()
        sdk_client.chat.completions.create.side_effect = [
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
                id="completion-1", model="gpt-4o-snapshot",
                usage=CompletionUsage(
                    prompt_tokens=100, completion_tokens=30, total_tokens=130,
                    prompt_tokens_details={"cached_tokens": 50},
                    completion_tokens_details={"reasoning_tokens": 20},
                ),
            ),
            RuntimeError("provider unavailable"),
        ]
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
            patch.dict(sys.modules, {"aisuite": SimpleNamespace(Client=Mock(return_value=sdk_client))}),
        ):
            client = AISuiteLLMClient(model="openai:gpt-4o")
            client.complete([{"role": "user", "content": "Return JSON."}])
            metadata = client.last_completion_metadata
            self.assertEqual(metadata["requestedModel"], "openai:gpt-4o")
            self.assertEqual(metadata["responseModel"], "gpt-4o-snapshot")
            self.assertEqual(metadata["responseId"], "completion-1")
            self.assertEqual(metadata["usage"]["total_tokens"], 130)
            self.assertEqual(metadata["usage"]["completion_tokens_details"]["reasoning_tokens"], 20)
            self.assertEqual(metadata["usage"]["prompt_tokens_details"]["cached_tokens"], 50)
            with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
                client.complete([{"role": "user", "content": "Return JSON."}])
            self.assertIsNone(client.last_completion_metadata)

    def test_complete_requests_json_and_does_not_forward_reserved_tools(self):
        sdk_client = Mock()
        sdk_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))]
        )
        fake_aisuite = SimpleNamespace(Client=Mock(return_value=sdk_client))

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
            patch.dict(sys.modules, {"aisuite": fake_aisuite}),
        ):
            client = AISuiteLLMClient(model="openai:gpt-4o")
            result = client.complete(
                [{"role": "user", "content": "Return JSON."}],
                tools=[{"type": "function", "function": {"name": "unused"}}],
            )

        self.assertEqual(result, '{"ok": true}')
        self.assertIsNone(client.last_completion_metadata["usage"])
        fake_aisuite.Client.assert_called_once_with(
            provider_configs={"openai": {"timeout": 120.0, "max_retries": 0}}
        )
        sdk_client.chat.completions.create.assert_called_once_with(
            model="openai:gpt-4o",
            messages=[{"role": "user", "content": "Return JSON."}],
            response_format={"type": "json_object"},
        )

    def test_forwards_configured_temperature(self):
        sdk_client = Mock()
        sdk_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))]
        )
        fake_aisuite = SimpleNamespace(Client=Mock(return_value=sdk_client))

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
            patch.dict(sys.modules, {"aisuite": fake_aisuite}),
        ):
            AISuiteLLMClient(model="openai:gpt-4o", temperature=0.2).complete(
                [{"role": "user", "content": "Return JSON."}]
            )

        self.assertEqual(sdk_client.chat.completions.create.call_args.kwargs["temperature"], 0.2)

    def test_requires_openai_api_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                AISuiteLLMClient()

    def test_rejects_empty_response(self):
        sdk_client = Mock()
        sdk_client.chat.completions.create.return_value = SimpleNamespace(choices=[])
        fake_aisuite = SimpleNamespace(Client=Mock(return_value=sdk_client))

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
            patch.dict(sys.modules, {"aisuite": fake_aisuite}),
        ):
            client = AISuiteLLMClient()
            with self.assertRaisesRegex(ValueError, "no completion choices"):
                client.complete([{"role": "user", "content": "Return JSON."}])


if __name__ == "__main__":
    unittest.main()
