from evaluation.evaluate_answers import evaluate_answer_record, summarize_answer_records
from evaluation.m2_effectiveness import classify_question


def test_question_slices_are_deterministic() -> None:
    assert classify_question("瓦斯浓度达到1.0%时怎么办？") == "exact"
    assert classify_question("葛泉矿东井的生产能力是多少？") == "exact"
    assert classify_question("瓦斯积聚为什么会导致爆炸？") == "relational"
    assert classify_question("透水事故后应当如何处置？") == "procedural"
    assert classify_question("总结防治水工作的主要要求") == "summary"
    assert classify_question("葛泉矿东井在哪里？") == "other"


def test_answer_metrics_detect_invalid_citations_and_refusal() -> None:
    evaluated = evaluate_answer_record(
        {
            "id": "q1",
            "answer": "应停止作业[#1]，并立即撤人[#9]。",
            "sources": [{"id": 1}],
        }
    )
    assert evaluated["citation_precision"] == 0.5
    assert evaluated["invalid_citation_count"] == 1
    assert evaluated["citation_coverage"] == 1.0

    refusal = evaluate_answer_record(
        {"id": "q2", "answer": "根据现有证据无法回答该问题", "sources": []}
    )
    assert refusal["refused"] is True
    assert refusal["citation_precision"] == 1.0


def test_answer_summary_aggregates_rates() -> None:
    result = summarize_answer_records(
        [
            {"id": "q1", "answer": "结论[#1]。", "sources": [{"id": 1}]},
            {"id": "q2", "answer": "根据现有证据无法回答", "sources": [], "should_refuse": True},
        ]
    )
    assert result["samples"] == 2
    assert result["refusal_rate"] == 0.5
    assert result["citation_precision"] == 1.0
    assert result["citation_required_violation_rate"] == 0.0
    assert result["refusal_accuracy"] == 1.0
