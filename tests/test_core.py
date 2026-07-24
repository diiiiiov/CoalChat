import unittest

from backend_fastapi.model_client import ModelClient, ModelClientConfig
from backend_fastapi.index_tools import split_text
from backend_fastapi.storage import StateStore
from backend_fastapi.text_utils import normalize_citations


class CitationTests(unittest.TestCase):
    def test_normalizes_and_removes_invalid_citations(self):
        answer = "撤离[1]，启动预案[＃2]，忽略无效来源[#9]。"
        self.assertEqual(
            normalize_citations(answer, 2),
            "撤离[#1]，启动预案[#2]，忽略无效来源。",
        )

    def test_text_splitter_keeps_overlap(self):
        chunks = split_text("甲" * 500, chunk_size=200, overlap=40)
        self.assertGreaterEqual(len(chunks), 3)
        self.assertEqual(chunks[0][-40:], chunks[1][:40])


class ModelClientTests(unittest.TestCase):
    def test_chat_payload(self):
        client = ModelClient(
            ModelClientConfig(
                api_url="https://example.test/v1/chat/completions",
                api_style="auto",
                default_model="test-model",
            )
        )
        payload = client.build_payload("问题", None, 0.2, True)
        self.assertEqual(payload["messages"][0]["content"], "问题")
        self.assertNotIn("prompt", payload)
        self.assertTrue(payload["stream"])

    def test_extracts_completion_and_chat_tokens(self):
        self.assertEqual(
            ModelClient.extract_token({"choices": [{"text": "A"}]}), "A"
        )
        self.assertEqual(
            ModelClient.extract_token(
                {"choices": [{"delta": {"content": "B"}}]}
            ),
            "B",
        )


class StorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_evidence_and_retrieval_cache(self):
        store = StateStore(redis_url="", evidence_ttl=60, cache_ttl=60)
        await store.save_evidence("request-1", {1: {"content": "证据"}})
        self.assertEqual(
            await store.get_evidence("request-1", 1), {"content": "证据"}
        )

        cache_key = store.retrieval_cache_key({"query": "透水"})
        documents = [{"content": "应急处置"}]
        await store.save_retrieval(cache_key, documents)
        self.assertEqual(await store.get_retrieval(cache_key), documents)


if __name__ == "__main__":
    unittest.main()
