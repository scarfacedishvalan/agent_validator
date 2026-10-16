import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from typing import Any, Sequence
from unittest.mock import patch

from app.services.factor_view_prompts import load_factor_view_output_contract
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
            ),
            redirect_stdout(output),
        ):
            main([])

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

    def test_renders_prompts_and_returns_validated_contract_response(self):
        client = StubLLMClient(self.example)
        tools = [{"type": "function", "function": {"name": "reserved"}}]

        result = generate_factor_views(self.snapshot, llm_client=client, tools=tools)

        self.assertEqual(result, self.example)
        self.assertEqual(len(client.messages), 2)
        system_prompt = client.messages[0]["content"]
        user_prompt = client.messages[1]["content"]
        self.assertIn("OUTPUT_JSON_SCHEMA:", system_prompt)
        self.assertIn('"const": "abstain"', system_prompt)
        self.assertIn('"HML_return_1m": -0.032', user_prompt)
        self.assertEqual(client.tools, tools)

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
