# Foreign Whispers Project Report

## Project Goal

The goal of this project is to take an English YouTube video and turn it into a dubbed version in another language using open-source tools. In simple terms, the pipeline is:

English YouTube video -> transcript -> translation -> TTS dubbed audio -> final MP4 with dubbed audio and captions

This is meant to be a local/open-source pipeline, not a paid API workflow. If the full runtime succeeds, the final output should be saved at:

`pipeline_data/api/dubbed_videos/<config>/<title>.mp4`

## Pipeline Overview

The intended pipeline in this repo is:

1. Download
   Downloads the source video and YouTube captions when available.
   Output: `pipeline_data/api/videos/` and `pipeline_data/api/youtube_captions/`

2. Transcribe
   Produces a transcript JSON. If YouTube captions are enabled, the app can use those instead of running Whisper.
   Output: `pipeline_data/api/transcriptions/whisper/`

3. Diarize, optional
   Runs speaker diarization and adds speaker labels back into the transcript.
   Output: `pipeline_data/api/diarizations/`

4. Translate
   Translates the transcript into Spanish or another target language.
   Output: `pipeline_data/api/translations/argos/`

5. TTS
   Generates dubbed speech audio from the translated transcript, with optional alignment and voice selection.
   Output: `pipeline_data/api/tts_audio/chatterbox/`

6. Stitch
   Replaces the original audio with the dubbed audio and produces the final video.
   Output: `pipeline_data/api/dubbed_videos/`

## What I Implemented

The main work I added was around alignment, diarization, TTS wiring, and making the pipeline easier to run from both the API and frontend.

- I implemented duration-aware reranking in `foreign_whispers/reranking.py` so overlong translated segments can be shortened with deterministic rules.
- I implemented speaker assignment in `foreign_whispers/diarization.py`, including max-overlap speaker matching and a default fallback speaker label.
- I added the diarize API route in `api/src/routers/diarize.py`, including caching and merging speaker labels back into the saved transcript JSON.
- I wired the frontend pipeline to support an optional diarize stage in `frontend/src/hooks/use-pipeline.ts` and related UI components.
- I kept and extended TTS/alignment/voice-selection support in the API and service layer.
- I also made Docker/runtime cleanup changes in `Dockerfile` and `.dockerignore` to help with local development on this machine.

## Important Files Changed

### Python library

`foreign_whispers/reranking.py` contains the duration-aware reranking logic. The key function is `get_shorter_translations()`, which generates shorter candidate translations using deterministic text rules instead of an external LLM.

`foreign_whispers/diarization.py` adds diarization support and speaker assignment. The important part here is `assign_speakers()`, which labels transcript segments based on the diarization segment with the biggest time overlap.

`foreign_whispers/alignment.py` is the core timing logic. It computes segment timing estimates, decides whether a segment fits, needs stretch, needs a shorter translation, or fails.

`foreign_whispers/evaluation.py` computes clip-level evaluation metrics like duration error, severe stretch rate, gap shifts, and drift. This is useful for checking alignment quality without needing a full manual review every time.

`foreign_whispers/voice_resolution.py` handles speaker WAV lookup for voice cloning. It tries speaker-specific files first, then language defaults, then a global default.

### API backend

`api/src/routers/diarize.py` adds `/api/diarize/{video_id}`. It extracts audio, runs diarization, caches the result in `pipeline_data/api/diarizations/`, and merges speaker labels into the transcript JSON.

`api/src/routers/tts.py` adds `/api/tts/{video_id}` with config-based caching, alignment flags, and speaker voice-map support. This is where the API passes the translated transcript into the TTS service.

`api/src/services/tts_service.py` is a thin wrapper that keeps the router simple and exposes alignment computation to the API layer.

`api/src/services/tts_engine.py` is where most of the heavy TTS logic lives. It handles segment-wise synthesis, optional alignment, optional reranking for hard segments, time-stretching, and final WAV assembly.

`api/src/core/config.py` centralizes the artifact directories and runtime paths. This is what keeps the pipeline outputs organized under `pipeline_data/api/`.

`api/src/main.py` wires the routers into FastAPI and sets up lazy model loading for the app.

### Frontend

`frontend/src/lib/api.ts` defines the frontend HTTP calls for each pipeline stage, including diarize and TTS alignment options.

`frontend/src/lib/types.ts` defines the pipeline state and settings, including `diarization` and `useYoutubeCaptions`.

`frontend/src/hooks/use-pipeline.ts` is the main frontend pipeline flow. It runs download -> transcribe -> optional diarize -> translate -> tts -> stitch, and it also loops over output variants when more than one config is selected.

`frontend/src/components/pipeline-table.tsx` shows stage-by-stage status, duration, and configuration.

`frontend/src/components/pipeline-cards.tsx` shows summary info like pipeline time, segment count, translation size, and variant count.

`frontend/src/components/pipeline-status-bar.tsx` shows the current stage message while the pipeline is running.

### Runtime / Docker

`Dockerfile` includes the system tools needed for audio/video processing, plus UID/GID handling so Docker-created files are owned by the local user. It also forces CPU-oriented dependency resolution for the API image on this machine.

`.dockerignore` removes big local folders like `.venv`, `.git`, frontend build output, and `pipeline_data/` from the Docker build context. This keeps builds smaller and less messy.

`RUNTIME_STATUS.md` records what I was able to verify locally and what got blocked by the runtime environment. I used that file as part of the evidence for this report.

## Verification

Here is what I could verify honestly from the repo and local checks:

- In my earlier local check, the relevant Python tests for reranking, alignment, and diarization passed. This is documented in `RUNTIME_STATUS.md`.
- In my earlier local check, frontend lint also passed. That is also documented in `RUNTIME_STATUS.md`.
- I checked `pipeline_data/api/` and `pipeline_data/api/dubbed_videos/` in this environment, and no final dubbed MP4 was present.
- The code structure matches the intended pipeline order, including optional diarization in the frontend/API path.
- The full Docker end-to-end run was blocked locally, so I could not honestly say the final MP4 was generated on this Mac.

One extra runtime detail I found while inspecting the code is that the frontend path includes the diarize stage only when selected, and it can run multiple `tts + stitch` passes if more than one config variant is chosen.

## Runtime Issue

The code work is mostly done, but my Mac could not complete the full runtime and generate the final MP4.

The main blockers were:

- low disk space during the earlier local runtime check
- Docker/containerd storage failure, including a metadata database input/output error reported in `RUNTIME_STATUS.md`
- large Torch, Whisper, and TTS dependencies, which make the Docker setup heavy

So the expected final output path is still:

`pipeline_data/api/dubbed_videos/<config>/<title>.mp4`

But in this checked environment, that final MP4 does not exist yet.

## How To Run It On A Healthy Machine

```bash
git clone <repo-url>
cd foreign-whispers
git checkout main
git pull

touch cookies.txt

cat > .env <<ENV
UID=$(id -u)
GID=$(id -g)
FW_HF_TOKEN=
LOGFIRE_TOKEN=
ENV
```

For CPU-only:

```bash
docker compose --profile cpu up -d api frontend
```

For NVIDIA GPU:

```bash
docker compose --profile nvidia up -d
```

Then:

- open the frontend at `http://localhost:8501`
- run the stages from the UI: Download -> Transcribe -> optional Diarize -> Translate -> TTS -> Stitch
- check for the final MP4 under `pipeline_data/api/dubbed_videos/`

## Final Status

The implementation is mostly complete and the main code paths were checked at the code and test level. The missing piece is the real final video output on this machine: the final MP4 still needs to be generated on a healthy Docker machine, ideally with working GPU support if available.
