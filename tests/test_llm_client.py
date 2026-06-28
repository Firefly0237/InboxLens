from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from inbox_lens.llm.openai_compatible import LLMError, OpenAICompatibleClient


def _client() -> OpenAICompatibleClient:
    return OpenAICompatibleClient(base_url="http://llm.local/v1", api_key="k", model="m")


class _FakeResponse(io.BytesIO):
    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _response_with(content: object) -> _FakeResponse:
    body = json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")
    return _FakeResponse(body)


class LLMClientTests(unittest.TestCase):
    def test_null_content_raises_llm_error_not_attribute_error(self) -> None:
        with patch("urllib.request.urlopen", return_value=_response_with(None)):
            with self.assertRaises(LLMError):
                _client().complete_json([{"role": "user", "content": "hi"}])

    def test_list_content_blocks_raise_llm_error(self) -> None:
        with patch("urllib.request.urlopen", return_value=_response_with([{"type": "text"}])):
            with self.assertRaises(LLMError):
                _client().complete_json([{"role": "user", "content": "hi"}])

    def test_valid_json_content_is_parsed(self) -> None:
        with patch("urllib.request.urlopen", return_value=_response_with('{"category": "x"}')):
            result = _client().complete_json([{"role": "user", "content": "hi"}])
        self.assertEqual(result, {"category": "x"})

    def test_non_json_body_raises_llm_error(self) -> None:
        with patch("urllib.request.urlopen", return_value=_FakeResponse(b"<html>502 Bad Gateway</html>")):
            with self.assertRaises(LLMError):
                _client().complete_json([{"role": "user", "content": "hi"}])


if __name__ == "__main__":
    unittest.main()
