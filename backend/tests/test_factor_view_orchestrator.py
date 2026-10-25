import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from typing import Any, Sequence
from unittest.mock import patch

from app.services.factor_view_prompts import (
    DEFAULT_PERSONALITY_KEY,
    PERSONALITIES_PATH,
    load_agent_personality,
    load_factor_view_output_contract,
)
from app.services.orchestrators.factor_view_orchestrator import (
    DEFAULT_SNAPSHOT_PATH,
    generate_factor_views,
    main,
)
from app.services.utils.aisuite_llm_client import Message, Tool


class StubLLMClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.messages: Sequence[Message] = []
        self.tools: Sequence[Tool] | None = None

    def complete(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Tool] | None = None,
    ) -> str:
        self.messages = list(messages)
        self.tools = list(tools) if tools is not None else None
        return json.dumps(self.response)


class FactorViewOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads(DEFAULT_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        self.example = load_factor_view_output_contract()["example"]

    def test_cli_prints_only_p_and_q(self):
        output = StringIO()
        with (
            patch(
                "app.services.orchestrators.factor_view_orchestrator.generate_factor_views",
                return_value=self.example,
            ) as generate,
            redirect_stdout(output),
        ):
            main(["--model", "openai:gpt-4o"])

        generate.assert_called_once_with(
            self.snapshot, personality_key=DEFAULT_PERSONALITY_KEY, model="openai:gpt-4o"
        )
        self.assertEqual(
            json.loads(output.getvalue()),
            {"P": self.example["P"], "Q": self.example["Q"]},
        )
        self.assertEqual(
            output.getvalue(),
            '{\n  "P": [\n    [1, 0, 0],\n    [0, 1, 0],\n    [0, 0, 1]\n  ],\n'
            '  "Q": [[0.04], [0.02], [0.03]]\n}\n',
        )

    def test_cli_displays_empty_matrices(self):
        output = StringIO()
        with (
            patch(
                "app.services.orchestrators.factor_view_orchestrator.generate_factor_views",
                return_value={"P": [], "Q": []},
            ),
            redirect_stdout(output),
        ):
            main([])

        self.assertEqual(output.getvalue(), '{\n  "P": [],\n  "Q": []\n}\n')

    def test_cli_forwards_selected_personality(self):
        key = "Contrarian Mean-Reversion Analyst"
        with (
            patch(
                "app.services.orchestrators.factor_view_orchestrator.generate_factor_views",
                return_value=self.example,
            ) as generate,
            redirect_stdout(StringIO()),
        ):
            main(["--personality", key, "--model", "openai:test-model"])
        generate.assert_called_once_with(
            self.snapshot, personality_key=key, model="openai:test-model"
        )

    def test_renders_prompts_and_returns_validated_contract_response(self):
        client = StubLLMClient(self.example)
        tools = [{"type": "function", "function": {"name": "reserved"}}]

        result = generate_factor_views(self.snapshot, llm_client=client, tools=tools)

        self.assertEqual(result, self.example)
        self.assertEqual(len(client.messages), 2)
        system_prompt = client.messages[0]["content"]
        user_prompt = client.messages[1]["content"]
        self.assertIn("OUTPUT_JSON_SCHEMA:", system_prompt)
        self.assertIn("SHARED FINANCIAL GROUNDING POLICY", system_prompt)
        self.assertNotIn("{shared_financial_grounding_policy}", system_prompt)
        self.assertIn('"const": "abstain"', system_prompt)
        self.assertIn('"HML_return_1m": -0.032', user_prompt)
        self.assertIn(load_agent_personality(DEFAULT_PERSONALITY_KEY), user_prompt)
        self.assertNotIn("{agent_personality}", user_prompt)
        self.assertEqual(client.tools, tools)

    def test_each_personality_reaches_user_prompt_without_changing_system_prompt(self):
        personalities = json.loads(PERSONALITIES_PATH.read_text(encoding="utf-8"))
        system_prompts = []
        for key, sentences in personalities.items():
            with self.subTest(personality_key=key):
                client = StubLLMClient(self.example)
                result = generate_factor_views(
                    self.snapshot, personality_key=key, llm_client=client
                )
                self.assertEqual(result, self.example)
                self.assertIn(key, client.messages[1]["content"])
                self.assertIn("\n".join(sentences), client.messages[1]["content"])
                self.assertNotIn("{agent_personality}", client.messages[1]["content"])
                system_prompts.append(client.messages[0]["content"])
        self.assertTrue(all(prompt == system_prompts[0] for prompt in system_prompts))

    def test_unknown_personality_fails_before_llm_call(self):
        client = StubLLMClient(self.example)
        with self.assertRaisesRegex(ValueError, "Unknown personality key"):
            generate_factor_views(
                self.snapshot, personality_key="unknown", llm_client=client
            )
        self.assertEqual(client.messages, [])

    def test_rejects_inconsistent_p_and_q(self):
        invalid_response = json.loads(json.dumps(self.example))
        invalid_response["P"][0] = [0, 1, 0]

        with self.assertRaisesRegex(ValueError, "one-hot row per active factor"):
            generate_factor_views(self.snapshot, llm_client=StubLLMClient(invalid_response))

    def test_rejects_invalid_json_from_llm(self):
        class InvalidJSONClient:
            def complete(
                self,
                messages: Sequence[Message],
                *,
                tools: Sequence[Tool] | None = None,
            ) -> str:
                del messages, tools
                return "not JSON"

        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            generate_factor_views(self.snapshot, llm_client=InvalidJSONClient())


if __name__ == "__main__":
    unittest.main()
