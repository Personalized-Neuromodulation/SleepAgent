import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent import PaperAgent


class AgentResilienceTests(unittest.TestCase):
    def _agent_with_config(self, text):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
        tmp.write(text)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return PaperAgent(config_path=tmp.name)

    def test_ollama_502_retries_with_backoff(self):
        agent = self._agent_with_config("""
MAIN_LLM_MODEL: qwen3:14b
OLLAMA_HOST: http://localhost:11434
LLM_MAX_RETRIES: 2
LLM_RETRY_BASE_DELAY_SECONDS: 0.01
LLM_MAX_TOKENS: 64
""")

        class Client:
            def __init__(self):
                self.calls = 0
                self.unloads = 0

            def chat(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("502 Bad Gateway")
                return {"message": {"content": "OK"}}

            def generate(self, **kwargs):
                self.unloads += 1
                return {}

        client = Client()
        agent.client = client

        with patch("agent.time.sleep") as sleep:
            result = agent._call_ollama_with_retry([{"role": "user", "content": "x"}])

        self.assertEqual(result, "OK")
        self.assertEqual(client.calls, 2)
        self.assertEqual(client.unloads, 0)
        sleep.assert_called_once()

    def test_ollama_chat_keeps_model_loaded_until_close(self):
        agent = self._agent_with_config("""
MAIN_LLM_MODEL: qwen3:14b
OLLAMA_HOST: http://localhost:11434
OLLAMA_KEEP_ALIVE: "-1"
LLM_MAX_RETRIES: 1
LLM_MAX_TOKENS: 64
""")
        captured = {}

        class Client:
            def chat(self, **kwargs):
                captured.update(kwargs)
                return {"message": {"content": "OK"}}

            def generate(self, **kwargs):
                captured["unload"] = kwargs
                return {}

        agent.client = Client()

        result = agent._call_ollama_with_retry([{"role": "user", "content": "x"}])

        self.assertEqual(result, "OK")
        self.assertEqual(captured["keep_alive"], "-1")
        self.assertNotIn("unload", captured)

        agent.close()
        self.assertEqual(captured["unload"]["keep_alive"], 0)

    def test_qwen3_thinking_is_disabled_with_no_think_prefix(self):
        agent = self._agent_with_config("""
MAIN_LLM_MODEL: qwen3:14b
OLLAMA_HOST: http://localhost:11434
OLLAMA_DISABLE_THINKING: true
LLM_MAX_RETRIES: 1
LLM_MAX_TOKENS: 64
""")
        captured = {}

        class Client:
            def chat(self, **kwargs):
                captured.update(kwargs)
                return {"message": {"content": "OK"}}

            def generate(self, **kwargs):
                return {}

        agent.client = Client()

        result = agent._call_ollama_with_retry([
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user prompt"},
        ])

        self.assertEqual(result, "OK")
        self.assertTrue(captured["messages"][0]["content"].startswith("/no_think\n"))

    def test_prompt_input_is_clipped_before_llm_call(self):
        agent = self._agent_with_config("""
MAIN_LLM_MODEL: qwen3:14b
OLLAMA_HOST: http://localhost:11434
LLM_BATCH_SIZE: 1
LLM_MAX_TITLE_CHARS: 10
LLM_MAX_ABSTRACT_CHARS: 20
LLM_MAX_TOKENS: 64
""")
        captured = {}

        def call(messages, temperature=0.2, max_tokens=None):
            captured["prompt"] = messages[-1]["content"]
            return """
<result>
<id>1</id>
<judgment>Related</judgment>
<explanation>ok</explanation>
</result>
"""

        agent._call_ollama_with_retry = call

        result = agent.analyze_batch_papers_with_id([{
            "id": "1",
            "title": "T" * 100,
            "abstract": "A" * 100,
        }])

        self.assertEqual(result[0]["id"], "1")
        self.assertIn("TTTTTTTTTT ...", captured["prompt"])
        self.assertIn("AAAAAAAAAAAAAAAAAAAA ...", captured["prompt"])


if __name__ == "__main__":
    unittest.main()
