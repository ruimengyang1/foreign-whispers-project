# tests/test_diarization.py
import pytest
from foreign_whispers.diarization import assign_speakers, diarize_audio


def test_returns_empty_without_token():
    result = diarize_audio("/any/path.wav", hf_token=None)
    assert result == []


def test_returns_empty_with_empty_token():
    result = diarize_audio("/any/path.wav", hf_token="")
    assert result == []


def test_returns_empty_when_pyannote_absent(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "pyannote.audio", None)
    result = diarize_audio("/any/path.wav", hf_token="fake-token")
    assert result == []


def test_assign_speakers_uses_greatest_temporal_overlap():
    segments = [
        {"id": 0, "start": 0.0, "end": 1.0, "text": "hola"},
        {"id": 1, "start": 1.0, "end": 2.0, "text": "adios"},
    ]
    diarization = [
        {"start_s": 0.0, "end_s": 0.4, "speaker": "SPEAKER_00"},
        {"start_s": 0.3, "end_s": 1.2, "speaker": "SPEAKER_01"},
        {"start_s": 1.1, "end_s": 2.0, "speaker": "SPEAKER_02"},
    ]

    labeled = assign_speakers(segments, diarization)

    assert labeled[0]["speaker"] == "SPEAKER_01"
    assert labeled[1]["speaker"] == "SPEAKER_02"


def test_assign_speakers_falls_back_to_default_without_overlap():
    segments = [{"id": 0, "start": 3.0, "end": 4.0, "text": "sin solape"}]
    diarization = [{"start_s": 0.0, "end_s": 1.0, "speaker": "SPEAKER_09"}]

    labeled = assign_speakers(segments, diarization)

    assert labeled[0]["speaker"] == "SPEAKER_00"
    assert "speaker" not in segments[0]


@pytest.mark.requires_pyannote
def test_real_diarization_returns_speaker_labels(tmp_path):
    """Integration test — requires pyannote.audio and FW_HF_TOKEN env var."""
    import os
    token = os.environ.get("FW_HF_TOKEN")
    if not token:
        pytest.skip("FW_HF_TOKEN not set")
    result = diarize_audio("/path/to/sample.wav", hf_token=token)
    assert isinstance(result, list)
    for r in result:
        assert "start_s" in r and "end_s" in r and "speaker" in r
