import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.services.utils.aisuite_llm_client import AISuiteLLMClient


class AISuiteLLMClientTests(unittest.TestCase):
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
        sdk_client.chat.completions.create.assert_called_once_with(
            model="openai:gpt-4o",
            messages=[{"role": "user", "content": "Return JSON."}],
            response_format={"type": "json_object"},
        )

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
