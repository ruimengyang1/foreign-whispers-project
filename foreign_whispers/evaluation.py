"""Clip-level alignment quality metrics.

Extracted from notebooks/foreign_whispers_pipeline.ipynb (M8-align).
Imports from foreign_whispers.alignment — no other dependencies.
"""
import statistics as _stats
import re

from foreign_whispers.alignment import (
    AlignAction,
    AlignedSegment,
    SegmentMetrics,
    decide_action,
)


def clip_evaluation_report(
    metrics: list[SegmentMetrics],
    aligned: list[AlignedSegment],
) -> dict:
    """Return a summary dict of alignment quality metrics for one clip.

    Keys:
        mean_abs_duration_error_s: Mean |predicted_tts_s - source_duration_s| per segment.
        pct_severe_stretch: % of aligned segments with stretch_factor > 1.4.
        n_gap_shifts: Number of segments resolved via gap-shift.
        n_translation_retries: Number of segments that required re-ranking.
        total_cumulative_drift_s: End-to-end drift introduced by gap-shifts.
    """
    if not metrics:
        return {
            "mean_abs_duration_error_s": 0.0,
            "pct_severe_stretch":        0.0,
            "n_gap_shifts":              0,
            "n_translation_retries":     0,
            "total_cumulative_drift_s":  0.0,
        }

    errors    = [abs(m.predicted_tts_s - m.source_duration_s) for m in metrics]
    n_severe  = sum(1 for a in aligned if a.stretch_factor > 1.4)
    n_shifted = sum(1 for a in aligned if a.action == AlignAction.GAP_SHIFT)
    n_retry   = sum(1 for m in metrics if decide_action(m) == AlignAction.REQUEST_SHORTER)
    drift     = (
        aligned[-1].scheduled_end - aligned[-1].original_end
        if aligned else 0.0
    )

    return {
        "mean_abs_duration_error_s": round(_stats.mean(errors), 3),
        "pct_severe_stretch":        round(100 * n_severe / max(len(metrics), 1), 1),
        "n_gap_shifts":              n_shifted,
        "n_translation_retries":     n_retry,
        "total_cumulative_drift_s":  round(drift, 3),
    }


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-zÀ-ÿ0-9]+(?:['-][A-Za-zÀ-ÿ0-9]+)?", text))


def _token_error_rate(reference: str, hypothesis: str) -> float:
    ref = reference.split()
    hyp = hypothesis.split()
    if not ref:
        return 0.0 if not hyp else 1.0

    dp = [[0] * (len(hyp) + 1) for _ in range(len(ref) + 1)]
    for i in range(len(ref) + 1):
        dp[i][0] = i
    for j in range(len(hyp) + 1):
        dp[0][j] = j

    for i in range(1, len(ref) + 1):
        for j in range(1, len(hyp) + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j],
                    dp[i][j - 1],
                    dp[i - 1][j - 1],
                )

    return dp[-1][-1] / max(len(ref), 1)


def dubbing_scorecard(
    metrics: list[SegmentMetrics],
    aligned_segments: list[AlignedSegment],
    align_report: dict | None = None,
    *,
    roundtrip_texts: list[str] | None = None,
    backtranslated_texts: list[str] | None = None,
) -> dict:
    """Return a multi-dimensional dubbing quality scorecard.

    When richer signals such as STT round-trip or back-translation are absent,
    the scorecard falls back to deterministic text and timing proxies.
    """
    report = align_report or clip_evaluation_report(metrics, aligned_segments)

    if not metrics:
        return {
            "timing_accuracy": {"score": 1.0},
            "overlap_control": {"score": 1.0, "total_overlap_s": 0.0},
            "speaking_rate_naturalness": {"score": 1.0},
            "text_fidelity": {"score": 1.0, "method": "empty"},
            "intelligibility": {"score": 1.0, "method": "empty"},
            "overall_score": 1.0,
        }

    overlaps = []
    for prev, cur in zip(aligned_segments, aligned_segments[1:]):
        overlaps.append(max(0.0, prev.scheduled_end - cur.scheduled_start))
    total_overlap_s = round(sum(overlaps), 3)

    duration_error = report.get("mean_abs_duration_error_s", 0.0)
    severe_stretch = report.get("pct_severe_stretch", 0.0) / 100.0
    drift = abs(report.get("total_cumulative_drift_s", 0.0))

    timing_score = _clamp01(
        1.0
        - (duration_error / 1.5) * 0.5
        - severe_stretch * 0.3
        - min(drift / 6.0, 1.0) * 0.2
    )

    overlap_score = _clamp01(1.0 - min(total_overlap_s / max(len(metrics), 1), 1.0))

    speaking_rates = []
    for m in metrics:
        words = _word_count(m.translated_text)
        if m.predicted_tts_s > 0:
            speaking_rates.append(words / m.predicted_tts_s)

    rate_mean = _stats.mean(speaking_rates) if speaking_rates else 0.0
    rate_stdev = _stats.pstdev(speaking_rates) if len(speaking_rates) > 1 else 0.0
    rate_cv = (rate_stdev / rate_mean) if rate_mean > 0 else 0.0
    naturalness_score = _clamp01(1.0 - min(rate_cv / 0.6, 1.0))

    ratios = []
    punctuation_match = []
    for m in metrics:
        if m.src_char_count > 0:
            ratios.append(m.tgt_char_count / m.src_char_count)
        punctuation_match.append(
            1.0 if any(ch in m.translated_text for ch in ",.!?;:") == any(ch in m.source_text for ch in ",.!?;:") else 0.7
        )
    avg_ratio = _stats.mean(ratios) if ratios else 1.0
    ratio_score = _clamp01(1.0 - min(abs(avg_ratio - 1.1) / 0.9, 1.0))
    text_fidelity_score = round((ratio_score * 0.7) + ((_stats.mean(punctuation_match) if punctuation_match else 1.0) * 0.3), 3)

    if roundtrip_texts is not None and len(roundtrip_texts) == len(metrics):
        roundtrip_errors = [
            _token_error_rate(m.translated_text, roundtrip)
            for m, roundtrip in zip(metrics, roundtrip_texts)
        ]
        intelligibility_method = "roundtrip_wer"
        intelligibility_score = _clamp01(1.0 - _stats.mean(roundtrip_errors))
    elif backtranslated_texts is not None and len(backtranslated_texts) == len(metrics):
        backtranslation_errors = [
            _token_error_rate(m.source_text, backtranslated)
            for m, backtranslated in zip(metrics, backtranslated_texts)
        ]
        intelligibility_method = "backtranslation_proxy"
        intelligibility_score = _clamp01(1.0 - _stats.mean(backtranslation_errors))
    else:
        intelligibility_method = "timing_rate_proxy"
        intelligibility_score = round((timing_score * 0.6) + (naturalness_score * 0.4), 3)

    overall_score = round(_stats.mean([
        timing_score,
        overlap_score,
        naturalness_score,
        text_fidelity_score,
        intelligibility_score,
    ]), 3)

    return {
        "timing_accuracy": {
            "score": round(timing_score, 3),
            "mean_abs_duration_error_s": round(duration_error, 3),
            "pct_severe_stretch": round(report.get("pct_severe_stretch", 0.0), 1),
            "total_cumulative_drift_s": round(report.get("total_cumulative_drift_s", 0.0), 3),
        },
        "overlap_control": {
            "score": round(overlap_score, 3),
            "total_overlap_s": total_overlap_s,
            "overlap_segments": sum(1 for overlap in overlaps if overlap > 0),
        },
        "speaking_rate_naturalness": {
            "score": round(naturalness_score, 3),
            "mean_words_per_second": round(rate_mean, 3),
            "rate_stddev": round(rate_stdev, 3),
        },
        "text_fidelity": {
            "score": text_fidelity_score,
            "method": "length_punctuation_proxy",
            "avg_target_to_source_ratio": round(avg_ratio, 3),
        },
        "intelligibility": {
            "score": round(intelligibility_score, 3),
            "method": intelligibility_method,
        },
        "overall_score": overall_score,
    }
