# Foreign Whispers Submission Report

# Output
https://drive.google.com/drive/folders/1Ujcsrcg-ZJGwsovj0tEZMt-o_byUqpRh?usp=sharing

# Members:
Ruimeng Yang ry2468@nyu.edu
Teije Koolenbrander txk203@nyu.edu

Run on Windows 11 and RTX3060/4070

---

## 1. Project Goal

Foreign Whispers takes an English YouTube video and produces a target-language
(Spanish by default) dubbed version of the same video. The full intended flow:

1. Pull the video and any closed captions from YouTube.
2. Transcribe the English audio with Whisper.
3. Translate the transcript into the target language with `argostranslate`
   (offline, open-source — no paid translation API).
4. Synthesize target-language speech with Chatterbox TTS, time-aligned to the
   original Whisper timestamps.
5. Stitch the dubbed audio (and a target-language caption track) back onto the
   original MP4.

The whole pipeline is local / open source. There is no OpenAI, no DeepL, no
paid translation service in the loop.

---

## 2. Overall Pipeline Design

| # | Stage | What it does | Artifact path under `pipeline_data/api/` |
|---|---|---|---|
| 1 | **Download** | `yt-dlp` pulls the MP4 + JSON captions for each entry in `video_registry.yml`. | `videos/<title>.mp4` and `youtube_captions/<title>.json` |
| 2 | **Transcribe** | Whisper produces a per-segment transcript with start/end timestamps. | `transcriptions/whisper/<title>.json` |
| 3 | **Diarize (optional)** | `pyannote.audio` 3.1 produces speaker-labeled intervals; `assign_speakers` merges those labels back onto each Whisper segment by max temporal overlap. | `diarizations/<title>.json` (+ `.wav` for the extracted mono audio) |
| 4 | **Translate** | `argostranslate` translates each segment EN→ES and re-emits the same `{segments: [...]}` shape so timestamps survive. | `translations/argos/<title>.json` |
| 5 | **TTS** | Chatterbox synthesizes each segment, optionally with a per-speaker reference WAV. The duration-aware path (`FW_ALIGNMENT=on`, default) time-stretches each clip with `pyrubberband` to fit its window, and writes a `*.align.json` sidecar with the per-segment decisions. | `tts_audio/chatterbox/<config>/<title>.wav` (+ `.align.json`) |
| 6 | **Stitch** | `ffmpeg`/`moviepy` swaps the original audio for the dubbed WAV; the dubbed VTT is written next to it. | `dubbed_captions/<title>.vtt` and `dubbed_videos/<config>/<title>.mp4` (final output) |

`config` is a 7-hex-char tag (e.g. `c-fb1074a`) that namespaces TTS/dubbed
output by the parameter set used (baseline vs. aligned, speaker map, etc.).

---

## 3. Implementation Approach

This branch is a small, deliberately-narrow follow-up to the notebook 3 / 4
work that was already on `main`. I tried to keep the scope tight:

- **Duration-aware translation reranking** — the `get_shorter_translations`
  stub in `foreign_whispers/reranking.py` is now implemented with deterministic
  rules (phrase swaps like *"en este momento"* → *"ahora"*, filler-word
  removal, soft-word removal, trailing-clause trimming, final-word trimming).
  Candidates are scored against the `4.5 syllables/second` budget from
  `_estimate_duration` and returned shortest-first.
- **Beam-search global alignment** — added `global_align_dp` next to the
  existing greedy `global_align`, so we can compare the greedy schedule against
  one that trades a small extra stretch now for less cumulative drift later.
- **Dubbing scorecard** — `evaluation.dubbing_scorecard` adds a multi-dimension
  quality summary on top of the existing `clip_evaluation_report`.
- **TTS multi-speaker support** — the TTS router now resolves a per-speaker
  reference WAV when the transcript carries `speaker` labels (from the
  diarize step), and threads `voice_map` through the engine.
- **TTS rerank loop** — when alignment marks a segment `REQUEST_SHORTER`, the
  engine calls `get_shorter_translations` and uses the top candidate before
  synthesizing.
- **Speaker-resolution helper** — `voice_resolution.resolve_speaker_wav`
  centralises the `<lang>/<speaker>.wav` → `<lang>/default.wav` →
  `default.wav` fallback chain.
- **Docker networking** — `docker-compose.yml` was switched off
  `network_mode: host` and over to explicit `ports:` + container-DNS URLs
  (`http://chatterbox-gpu:8020`, `http://whisper-gpu:8000`) so the API
  container can reach the GPU sidecars on Windows / non-Linux Docker. Also
  pinned `FW_TTS_WORKERS=1` to keep memory predictable.

I intentionally did **not** touch `frontend/`, `Dockerfile`, `.dockerignore`,
`api/src/routers/diarize.py` or `foreign_whispers/diarization.py` on this
branch — those landed earlier (commit `3de89fc` and earlier) and the
documentation here is just describing what's there, not claiming I wrote it
this round.

---

## 4. Files Changed and What Each File Does

The table below covers exactly what this branch contributes
(`git diff origin/main...HEAD` = 14 files, +530 / −71). Files outside this
list (frontend, Dockerfile, diarize.py, etc.) are real and used by the
project, but they are inherited from `main` rather than introduced here.

| File | What changed | Why it was needed | Related notebook/task |
|---|---|---|---|
| `foreign_whispers/reranking.py` | Implemented `get_shorter_translations` (was a returns-empty-list stub). Added phrase-replacement table, filler-opening regex, soft-word regex, clause trimming, final-word trimming. Sorts by closeness to `target_duration_s * 15 chars/s`. | Notebook task: deterministic, no-LLM duration-aware translation reranking. | NB4 — duration-aware dubbing |
| `foreign_whispers/alignment.py` | Added `_estimate_duration` helper (vowel-cluster syllable counter + word/pause/digit adjustments). Added `global_align_dp` beam-search optimizer alongside the greedy `global_align`. Kept `decide_action`, `SegmentMetrics`, `AlignedSegment` API stable. | Notebook task: optimizer that can avoid greedy drift. Helper is shared by `reranking.py` so the two stay consistent. | NB3 — alignment policy & global schedule |
| `foreign_whispers/evaluation.py` | Added `dubbing_scorecard` (timing accuracy, overlap control, speaking-rate naturalness, text fidelity, intelligibility). `clip_evaluation_report` left alone. | Notebook task: a richer scorecard than the single `clip_evaluation_report` summary. | NB3 — evaluation |
| `foreign_whispers/voice_resolution.py` | Added `resolve_speaker_wav(speakers_dir, language, speaker_id)` with the `<lang>/<speaker>.wav` → `<lang>/default.wav` → `default.wav` fallback. | Centralises the path resolution that the TTS router now needs in three places. | NB4 — multi-speaker TTS |
| `foreign_whispers/__init__.py` | Re-exports for `dubbing_scorecard`, `global_align_dp`, `analyze_failures`, `TranslationCandidate`, `FailureAnalysis`. | Keep the public API in one place so tests + notebooks import from `foreign_whispers`. | NB3/NB4 |
| `api/src/routers/tts.py` | New `_build_voice_map` helper — when the source transcript carries `speaker` labels (i.e. diarize was run), maps each speaker to a reference WAV via `resolve_speaker_wav`, then passes the map plus a default `speaker_wav` into the service. New `speaker_wav` query parameter. | Lets a single TTS request render multiple voices when diarization is available, while still falling back to a default voice. | NB4 — multi-speaker TTS endpoint |
| `api/src/services/tts_service.py` | `text_file_to_speech` now forwards `alignment`, `speaker_wav`, and `voice_map` kwargs to the engine. Added `compute_alignment` facade. | Plumbing for the router changes above. | NB3/NB4 |
| `api/src/services/tts_engine.py` | Added per-speaker dispatch in the GPU-synth phase (`voice_map.get(speaker, default)`), `_shorten_segment_text` that calls `get_shorter_translations` when alignment marks a segment `REQUEST_SHORTER`, `_write_align_report` sidecar, `_compute_speech_offset` to align Whisper timestamps with YouTube caption start, and a `ChatterboxClient._synthesize_with_voice` upload path for voice cloning. Existing `_synthesize_raw`/`_postprocess_segment` split kept. | Wires the new alignment + reranking + diarize features into the actual TTS run. | NB4 — duration-aware TTS, multi-speaker |
| `api/src/services/translation_engine.py` | Small adjustments to keep segment shape stable for the new TTS path. | Required by the engine changes above. | NB3 |
| `api/src/services/translation_service.py` | Same — minor service-layer tweaks. | Same as above. | NB3 |
| `api/src/services/download_service.py` | Minor cleanup so the download artifact path matches the rest of the layered config. | Bug-adjacent: keeps `videos_dir` and `youtube_captions_dir` consistent with `Settings`. | NB3 |
| `api/src/services/stitch_service.py` | Added `stitch_audio_only` that swaps audio without burning subtitles. | Allows the pipeline to stop after the audio-replace step when the user doesn't want hard-burned captions. | NB4 |
| `api/src/core/config.py` | Added a couple of settings + property accessors so paths like `tts_audio_dir`, `dubbed_videos_dir`, `speakers_dir` are addressable from one place. | Removes hardcoded paths from the new TTS code. | NB3/NB4 |
| `docker-compose.yml` | API + frontend services switched from `network_mode: host` to explicit `ports:` (`8080:8080`, `8501:8501`); env vars updated to use container DNS (`http://chatterbox-gpu:8020`, `http://whisper-gpu:8000`); `FW_TTS_WORKERS=1`; `YT_COOKIES_FILE` made non-fatal. | Required to run the stack on Windows / non-Linux Docker, where `network_mode: host` doesn't work. | Runtime fix |

Files **not** changed on this branch but referenced in this report (already
on `main`):

- `foreign_whispers/diarization.py` — `diarize_audio` (pyannote) +
  `assign_speakers` (max-overlap label assignment). Last touched in
  commit `3de89fc` / `fa40930`.
- `api/src/routers/diarize.py` — POST `/api/diarize/{video_id}`, runs
  ffmpeg → pyannote, caches `diarizations/<title>.json`, merges speaker
  labels back into the saved transcription JSON.
- `frontend/src/hooks/use-pipeline.ts`, `frontend/src/components/pipeline-*.tsx`,
  `frontend/src/lib/api.ts`, `frontend/src/lib/types.ts` — UI for the
  Download → Transcribe → (Diarize) → Translate → TTS → Stitch flow,
  with the diarize stage skippable.
- `Dockerfile`, `.dockerignore` — single-image API build with `uv`,
  non-root `appuser`, and a small `.dockerignore` that keeps `.venv/`,
  `.git/`, `__pycache__/`, etc. out of the build context.

---

## 5. Requirement Alignment

- **Duration-aware translation reranking**
  - Status: implemented (deterministic, no LLM).
  - Evidence: `foreign_whispers/reranking.py:102` (`get_shorter_translations`),
    plus `_shorten_segment_text` call site at
    `api/src/services/tts_engine.py:345`.

- **Speaker assignment**
  - Status: implemented (already on `main`, exercised by this branch via
    the new `_build_voice_map` path).
  - Evidence: `foreign_whispers/diarization.py:48` (`assign_speakers` —
    max-overlap label, default `SPEAKER_00`), used at
    `api/src/routers/diarize.py:20` (`_merge_speakers_into_transcript`)
    and at `api/src/routers/tts.py:25` (`_build_voice_map`).

- **Diarize API**
  - Status: implemented; structurally inspected this run, runtime not
    re-verified end-to-end this session.
  - Evidence: `api/src/routers/diarize.py` (POST `/api/diarize/{video_id}`,
    ffmpeg extraction, pyannote pipeline, JSON caching, transcript merge).
    Cached artifact present at
    `pipeline_data/api/diarizations/Strait of Hormuz disruption threatens to shake global economy.json`
    and `.wav`.

- **Frontend pipeline integration**
  - Status: present on `main`; not modified this branch.
  - Evidence: `frontend/src/hooks/use-pipeline.ts`,
    `frontend/src/components/pipeline-table.tsx`,
    `frontend/src/components/pipeline-cards.tsx`,
    `frontend/src/components/pipeline-status-bar.tsx`.

- **TTS / voice selection**
  - Status: implemented this branch.
  - Evidence: `api/src/routers/tts.py:25` (`_build_voice_map`),
    `foreign_whispers/voice_resolution.py:11` (`resolve_speaker_wav`),
    `api/src/services/tts_engine.py:512` (per-speaker WAV dispatch in the
    concurrent synth pool). Risk: requires a real Chatterbox container
    reachable at `CHATTERBOX_API_URL`; without it, falls back to local
    Coqui TTS, which is much slower on CPU.

- **End-to-end final MP4**
  - Status: **Not generated for the Military Drones video on this machine.**
  - Due to us only having access to an NVIDIA 3060 graphics card with 4GB of VRAM, we were unable to finish the TTS stage for the Military Drones video. However, the TTS capabilities are shown in the other videos.

---

## 6. Tests and Verification Results

| Check | Result | Notes |
|---|---|---|
| `git status` | clean | Branch `test` up to date with `origin/test`. |
| `git log --oneline -8` | 8 commits visible | Top two (`4c911b7 test`, `80b83dd Complete alignment and TTS notebook backend tasks`) are this branch's contribution. |
| `git diff --stat origin/main...HEAD` | 14 files, +530 / −71 | Matches §4. |
| Pipeline-data inventory (`ls pipeline_data/api/...`) | All stages 1–5 produced artifacts; stage 6 (dubbed_videos) **missing** | See §7 for the file list. |
| `pytest` (this session) | **not re-run this session** | Listed under `tests/` are 30+ test files including `test_alignment.py`, `test_evaluation.py`, `test_diarization.py`, `test_services.py`, `test_stitch_router.py`. A previous audit reported "32 passed, 1 skipped"; I am **not** re-asserting that number this session. |
| Frontend lint | **not re-run this session** | Previous audit reported lint clean; not re-verified here. |
| `npm run build` (frontend) | **not re-run this session** | Previous audit noted Google Fonts fetch can fail in restricted networks; not re-verified here. |
| `docker compose --profile nvidia up` | **not re-run this session** | The current pipeline-data layout shows the stack ran at some earlier point and produced everything except the final stitched MP4. |
| Final MP4 existence | **present** | `pipeline_data/api/dubbed_videos/`|

---

## 7. Runtime Result and Final Artifact Status

`pipeline_data/` exists. What is on disk right now (one video, *Strait of
Hormuz disruption threatens to shake global economy*):


```
pipeline_data/api/
├── videos/                    Strait of Hormuz...mp4              (download OK)
├── youtube_captions/          (directory present)
├── transcriptions/whisper/    Strait of Hormuz...json             (transcribe OK)
├── diarizations/              Strait of Hormuz...json + .wav      (diarize OK)
├── dubbed_videos/             Strait of Hormuz...mp4              (video OK)
├── translations/argos/        Strait of Hormuz...json             (translate OK)
├── tts_audio/chatterbox/c-fb1074a/
│   ├── Strait of Hormuz...wav                                     (TTS OK)
│   └── Strait of Hormuz...align.json                              (alignment sidecar OK)
└── dubbed_captions/           Strait of Hormuz...vtt              (captions OK)
```


Expected final output path:

```
pipeline_data/api/dubbed_videos/<config>/<title>.mp4
```



## 8. Known Limitations / Risks

- **Chatterbox + Whisper sidecars are heavy** — they pull large model
  weights on first run and need a reachable GPU container; on a fresh
  machine the first dubbing run may take a long time.
- **CPU-only fallback exists but is slow** — `tts_engine.py` falls back
  to local Coqui TTS if Chatterbox is unreachable, and Coqui on CPU is
  not realistic for full-length videos.
- **Diarization needs a Hugging Face token + accepted licence** for
  `pyannote/speaker-diarization-3.1`. Without `FW_HF_TOKEN`, `diarize_audio`
  returns `[]` and `assign_speakers` defaults every segment to `SPEAKER_00`.
- **`pyrubberband` requires `rubberband-cli`** at the system level for
  real time-stretch; the Dockerfile installs it, but a host run without
  it falls back to the un-stretched WAV.
- **Frontend production build** can fail when Google Fonts cannot be
  fetched in a restricted network.
- **Greedy alignment is greedy.** `global_align` does not look ahead;
  `global_align_dp` is the beam-search alternative, but neither is a true
  globally-optimal solver.
- **Reranking is rule-based.** `get_shorter_translations` works for
  Spanish-style phrasing — other target languages would need their own
  phrase tables.

---

## 9. How To Reproduce On A Healthy Machine

```bash
git clone <repo-url>
cd foreign-whispers
git checkout test
git pull

mkdir -p pipeline_data
touch cookies.txt

cat > .env <<'ENV'
UID=1000
GID=1000
FW_HF_TOKEN=
LOGFIRE_TOKEN=
ENV
# On Linux/macOS, prefer:
#   echo "UID=$(id -u)"  >> .env
#   echo "GID=$(id -g)" >> .env

# Optional: free disk before pulling the GPU sidecar images
docker system prune -af --volumes

# NVIDIA GPU host (this repo is built for this case):
docker compose --profile nvidia up -d

# CPU-only host (much slower, Coqui fallback):
docker compose --profile cpu up -d api frontend
```

Then:

1. Open the frontend at <http://localhost:8501>.
2. Pick a video from the registry and run, in order:
   **Download → Transcribe → (optional) Diarize → Translate → TTS → Stitch**.
3. Confirm the final MP4 exists at
   `pipeline_data/api/dubbed_videos/<config>/<title>.mp4`.

Useful commands during a run:

```bash
docker compose --profile nvidia logs -f api
docker compose --profile nvidia logs -f chatterbox-gpu
docker compose --profile nvidia logs -f whisper-gpu
```

---

## 10. Final Submission Summary

- The notebook 3 / 4 code work is implemented on the `test` branch:
  duration-aware reranking, beam-search alignment, dubbing scorecard,
  multi-speaker TTS plumbing, and the Docker networking fix.
- Inspection of the repo and the on-disk pipeline artifacts shows that
  every stage from Download through TTS + dubbed-captions has produced a
  real output file for the *Strait of Hormuz* and *Alysa Liu* sample.
- A reviewer running this branch on a healthy Docker + NVIDIA GPU host
  should be able to produce the final MP4 by stepping the pipeline
  through to the Stitch stage.
