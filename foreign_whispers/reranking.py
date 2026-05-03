"""Deterministic failure analysis and translation re-ranking stubs.

The failure analysis function uses simple threshold rules derived from
SegmentMetrics.  The translation re-ranking function is a **student assignment**
— see the docstring for inputs, outputs, and implementation guidance.
"""

import dataclasses
import logging
import re

from foreign_whispers.alignment import _estimate_duration

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class TranslationCandidate:
    """A candidate translation that fits a duration budget.

    Attributes:
        text: The translated text.
        char_count: Number of characters in *text*.
        brevity_rationale: Short explanation of what was shortened.
    """
    text: str
    char_count: int
    brevity_rationale: str = ""


@dataclasses.dataclass
class FailureAnalysis:
    """Diagnostic summary of the dominant failure mode in a clip.

    Attributes:
        failure_category: One of "duration_overflow", "cumulative_drift",
            "stretch_quality", or "ok".
        likely_root_cause: One-sentence description.
        suggested_change: Most impactful next action.
    """
    failure_category: str
    likely_root_cause: str
    suggested_change: str


def analyze_failures(report: dict) -> FailureAnalysis:
    """Classify the dominant failure mode from a clip evaluation report.

    Pure heuristic — no LLM needed.  The thresholds below match the policy
    bands defined in ``alignment.decide_action``.

    Args:
        report: Dict returned by ``clip_evaluation_report()``.  Expected keys:
            ``mean_abs_duration_error_s``, ``pct_severe_stretch``,
            ``total_cumulative_drift_s``, ``n_translation_retries``.

    Returns:
        A ``FailureAnalysis`` dataclass.
    """
    mean_err = report.get("mean_abs_duration_error_s", 0.0)
    pct_severe = report.get("pct_severe_stretch", 0.0)
    drift = abs(report.get("total_cumulative_drift_s", 0.0))
    retries = report.get("n_translation_retries", 0)

    if pct_severe > 20:
        return FailureAnalysis(
            failure_category="duration_overflow",
            likely_root_cause=(
                f"{pct_severe:.0f}% of segments exceed the 1.4x stretch threshold — "
                "translated text is consistently too long for the available time window."
            ),
            suggested_change="Implement duration-aware translation re-ranking (P8).",
        )

    if drift > 3.0:
        return FailureAnalysis(
            failure_category="cumulative_drift",
            likely_root_cause=(
                f"Total drift is {drift:.1f}s — small per-segment overflows "
                "accumulate because gaps between segments are not being reclaimed."
            ),
            suggested_change="Enable gap_shift in the global alignment optimizer (P9).",
        )

    if mean_err > 0.8:
        return FailureAnalysis(
            failure_category="stretch_quality",
            likely_root_cause=(
                f"Mean duration error is {mean_err:.2f}s — segments fit within "
                "stretch limits but the stretch distorts audio quality."
            ),
            suggested_change="Lower the mild_stretch ceiling or shorten translations.",
        )

    return FailureAnalysis(
        failure_category="ok",
        likely_root_cause="No dominant failure mode detected.",
        suggested_change="Review individual outlier segments if any remain.",
    )


def get_shorter_translations(
    source_text: str,
    baseline_es: str,
    target_duration_s: float,
    context_prev: str = "",
    context_next: str = "",
) -> list[TranslationCandidate]:
    """Return shorter translation candidates that fit *target_duration_s*.

    .. admonition:: Student Assignment — Duration-Aware Translation Re-ranking

       This function is intentionally a **stub that returns an empty list**.
       Your task is to implement a strategy that produces shorter
       target-language translations when the baseline translation is too long
       for the time budget.

       **Inputs**

       ============== ======== ==================================================
       Parameter      Type     Description
       ============== ======== ==================================================
       source_text    str      Original source-language segment text
       baseline_es    str      Baseline target-language translation (from argostranslate)
       target_duration_s float Time budget in seconds for this segment
       context_prev   str      Text of the preceding segment (for coherence)
       context_next   str      Text of the following segment (for coherence)
       ============== ======== ==================================================

       **Outputs**

       A list of ``TranslationCandidate`` objects, sorted shortest first.
       Each candidate has:

       - ``text``: the shortened target-language translation
       - ``char_count``: ``len(text)``
       - ``brevity_rationale``: short note on what was changed

       **Duration heuristic**: target-language TTS produces ~15 characters/second
       (or ~4.5 syllables/second for Romance languages).  So a 3-second budget
       ≈ 45 characters.

       **Approaches to consider** (pick one or combine):

       1. **Rule-based shortening** — strip filler words, use shorter synonyms
          from a lookup table, contract common phrases
          (e.g. "en este momento" → "ahora").
       2. **Multiple translation backends** — call argostranslate with
          paraphrased input, or use a second translation model, then pick
          the shortest output that preserves meaning.
       3. **LLM re-ranking** — use an LLM (e.g. via an API) to generate
          condensed alternatives.  This was the previous approach but adds
          latency, cost, and a runtime dependency.
       4. **Hybrid** — rule-based first, fall back to LLM only for segments
          that still exceed the budget.

       **Evaluation criteria**: the caller selects the candidate whose
       ``len(text) / 15.0`` is closest to ``target_duration_s``.

    Returns:
        Empty list (stub).  Implement to return ``TranslationCandidate`` items.
    """
    baseline = re.sub(r"\s+", " ", baseline_es).strip()
    if not baseline:
        return []

    max_chars = max(1, int(target_duration_s * 15.0))
    if _estimate_duration(baseline) <= target_duration_s * 1.05:
        return []

    candidates: list[TranslationCandidate] = []
    seen = {baseline}

    def _normalize(text: str) -> str:
        text = re.sub(r"\s+", " ", text).strip(" ,;:")
        return re.sub(r"\s+([,.;:!?])", r"\1", text)

    def _replace_phrase(text: str, old: str, new: str) -> str:
        pattern = re.compile(rf"\b{re.escape(old)}\b", flags=re.IGNORECASE)

        def _repl(match: re.Match) -> str:
            if match.group(0)[:1].isupper() and new:
                return new[:1].upper() + new[1:]
            return new

        return pattern.sub(_repl, text)

    def _add_candidate(text: str, rationale: str) -> None:
        text = _normalize(text)
        if not text or len(text) >= len(baseline) or text in seen:
            return
        seen.add(text)
        candidates.append(
            TranslationCandidate(
                text=text,
                char_count=len(text),
                brevity_rationale=rationale,
            )
        )

    phrase_replacements = [
        ("en este momento", "ahora"),
        ("en este instante", "ahora"),
        ("por lo tanto", "asi que"),
        ("sin embargo", "pero"),
        ("debido a", "por"),
        ("a causa de", "por"),
        ("con el fin de", "para"),
        ("para poder", "para"),
        ("de hecho", ""),
    ]
    filler_pattern = re.compile(
        r"^(?:bueno|pues|entonces|la verdad|en realidad),?\s+",
        flags=re.IGNORECASE,
    )
    soft_words = re.compile(
        r"\b(?:realmente|simplemente|basicamente|literalmente|muy)\b",
        flags=re.IGNORECASE,
    )
    clause_break = re.compile(r"\s*(?:,|;|:)\s*")

    shortened = baseline
    changed = False
    for old, new in phrase_replacements:
        updated = _replace_phrase(shortened, old, new)
        if updated != shortened:
            shortened = updated
            changed = True
    if changed:
        _add_candidate(shortened, "shorter phrasing")

    without_filler = filler_pattern.sub("", baseline)
    if without_filler != baseline:
        _add_candidate(without_filler, "removed filler opening")

    tighter = filler_pattern.sub("", shortened if changed else baseline)
    tighter = soft_words.sub("", tighter)
    _add_candidate(tighter, "removed filler words")

    parts = clause_break.split(baseline)
    if len(parts) > 1:
        for keep in range(len(parts) - 1, 0, -1):
            trimmed = ", ".join(parts[:keep])
            _add_candidate(trimmed, "trimmed trailing clause")

    if len(baseline.split()) > 8:
        _add_candidate(" ".join(baseline.split()[:-2]), "trimmed final words")

    ordered = [c for c in candidates if _estimate_duration(c.text) <= target_duration_s * 1.05]
    if not ordered:
        ordered = candidates
    ordered.sort(
        key=lambda c: (
            abs(_estimate_duration(c.text) - target_duration_s),
            c.char_count,
            c.text,
        )
    )

    logger.info(
        "get_shorter_translations produced %d candidates for %.1fs budget "
        "(%d chars baseline, %d char target).",
        len(ordered),
        target_duration_s,
        len(baseline),
        max_chars,
    )
    return ordered
