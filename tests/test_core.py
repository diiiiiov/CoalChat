import unittest
from unittest.mock import patch

from backend_fastapi.model_client import ModelClient, ModelClientConfig
from backend_fastapi.index_tools import split_text
from backend_fastapi.storage import StateStore
from backend_fastapi.text_utils import normalize_citations
from backend_fastapi.query_context import compact_history, should_rewrite
from backend_fastapi.retrieval import analyze_query, should_use_reranker


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


class QueryContextTests(unittest.TestCase):
    def test_removes_current_turn_duplicate_from_frontend_history(self):
        history = compact_history(
            [
                {"role": "user", "content": "瓦斯浓度达到1%怎么办"},
                {"role": "assistant", "content": "请检查通风"},
                {"role": "user", "content": "那超过这个值以后呢"},
            ],
            "那超过这个值以后呢",
        )
        self.assertEqual(len(history), 2)
        self.assertTrue(should_rewrite("那超过这个值以后呢", history))

    def test_short_standalone_query_does_not_rewrite_without_history(self):
        self.assertFalse(should_rewrite("怎么办", []))


class RetrievalRoutingTests(unittest.TestCase):
    def test_exact_numeric_query_uses_sparse_without_reranker(self):
        strategy = analyze_query("瓦斯浓度达到1.5%时如何处理")
        self.assertEqual(strategy.mode, "exact")
        self.assertEqual(strategy.dense_weight, 0.0)
        self.assertFalse(should_use_reranker(strategy))

    def test_relational_query_keeps_dense_and_reranker(self):
        strategy = analyze_query("瓦斯积聚为什么会导致爆炸")
        self.assertEqual(strategy.mode, "relational")
        self.assertGreater(strategy.dense_weight, strategy.sparse_weight)
        self.assertTrue(should_use_reranker(strategy))

    def test_reranker_policy_can_override_route(self):
        strategy = analyze_query("煤矿安全规程第十二条是什么")
        with patch.dict("os.environ", {"RERANKER_POLICY": "always"}):
            self.assertTrue(should_use_reranker(strategy))

    def test_agreeing_retrievers_skip_reranker_in_auto_mode(self):
        strategy = analyze_query("瓦斯超限应该如何处理")
        self.assertFalse(
            should_use_reranker(strategy, dense=[1, 2, 3], sparse=[2, 1, 8])
        )
        self.assertTrue(
            should_use_reranker(strategy, dense=[1, 2, 3], sparse=[8, 9, 10])
        )


if __name__ == "__main__":
    unittest.main()
