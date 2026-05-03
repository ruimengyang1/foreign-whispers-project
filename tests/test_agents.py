# tests/test_agents.py — renamed module is now foreign_whispers.reranking
from foreign_whispers.reranking import (
    get_shorter_translations,
    analyze_failures,
    TranslationCandidate,
    FailureAnalysis,
)


def test_get_shorter_returns_empty_stub():
    """No candidates are needed when the baseline already fits the duration budget."""
    result = get_shorter_translations("hello", "hola", 1.0)
    assert result == []


def test_get_shorter_translations_returns_shorter_spanish_candidates():
    baseline = "En este momento, esto es realmente muy complicado, debido a la situacion"

    result = get_shorter_translations(
        "At this moment, this is really very complicated because of the situation",
        baseline,
        2.5,
    )

    assert result
    assert all(isinstance(candidate, TranslationCandidate) for candidate in result)
    assert result[0].char_count < len(baseline)
    assert all(candidate.text != baseline for candidate in result)


def test_get_shorter_translations_is_deterministic():
    baseline = "En este momento, esto es realmente muy complicado, debido a la situacion"

    first = get_shorter_translations(
        "At this moment, this is really very complicated because of the situation",
        baseline,
        2.5,
    )
    second = get_shorter_translations(
        "At this moment, this is really very complicated because of the situation",
        baseline,
        2.5,
    )

    assert first == second


def test_analyze_failures_returns_dataclass():
    result = analyze_failures({"mean_abs_duration_error_s": 0.5})
    assert isinstance(result, FailureAnalysis)
    assert result.failure_category == "ok"


def test_analyze_failures_detects_overflow():
    result = analyze_failures({"pct_severe_stretch": 30})
    assert result.failure_category == "duration_overflow"


def test_analyze_failures_detects_drift():
    result = analyze_failures({"total_cumulative_drift_s": 5.0})
    assert result.failure_category == "cumulative_drift"


def test_analyze_failures_detects_stretch_quality():
    result = analyze_failures({"mean_abs_duration_error_s": 1.2})
    assert result.failure_category == "stretch_quality"
