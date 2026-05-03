# Runtime Status

Date checked: 2026-05-03
Project: Foreign Whispers

## What Was Verified

- The codebase structure matches the intended pipeline:
  `Download -> Transcribe -> optional Diarize -> Translate -> TTS -> Stitch`
- Duration-aware reranking is implemented in `foreign_whispers/reranking.py` with deterministic, local rule-based shortening.
- Speaker assignment is implemented in `foreign_whispers/diarization.py` by temporal overlap, with `SPEAKER_00` fallback when a segment has no overlap.
- The diarize route is wired into FastAPI in `api/src/main.py` and `api/src/routers/diarize.py`.
- The frontend includes a diarize stage and now skips it cleanly when diarization is not selected.
- Relevant pure-Python tests for reranking, alignment, and diarization passed locally.
- Frontend lint passed locally.

## What Failed Or Could Not Be Fully Verified

- Full FastAPI/router runtime was not fully exercised in the current local venv because some declared dependencies were missing from the environment during smoke checks, including `fastapi` and `pydub`.
- Frontend production build was not verified in this environment because `next/font` attempted to fetch Google Fonts and the network-restricted environment could not reach `fonts.googleapis.com`.
- Docker runtime health is currently bad enough that end-to-end container validation was not attempted.

## Exact Docker And Disk Blocker

- `df -h` showed only about `625Mi` free on the main macOS volume.
- `docker system df` failed with a Docker/containerd storage error instead of returning normal usage data:

```text
Error response from daemon: failed to retrieve image list: rpc error: code = Unknown desc = blob sha256:8cce947c4c8d8ce6e72b8ff7b03af900f537dd6e0787ed8982c915ad877fceba expected at /var/lib/desktop-containerd/daemon/io.containerd.content.v1.content/blobs/sha256/8cce947c4c8d8ce6e72b8ff7b03af900f537dd6e0787ed8982c915ad877fceba: open /var/lib/desktop-containerd/daemon/io.containerd.content.v1.content/blobs/sha256/8cce947c4c8d8ce6e72b8ff7b03af900f537dd6e0787ed8982c915ad877fceba: input/output error
```

Because of those two issues, full Docker builds and final video generation were intentionally not forced.

## Final MP4 Status

- `pipeline_data/` exists as a directory tree.
- No final dubbed MP4 was found during verification.
- Expected final output path:
  `pipeline_data/api/dubbed_videos/<config>/<title>.mp4`

## Environment Needed To Finish Video Generation

To finish end-to-end dubbed video generation honestly, the project needs:

- a machine with substantially more free disk space than the current `~625Mi`
- healthy Docker Desktop / containerd storage with no blob I/O errors
- the declared Python dependencies installed for the active runtime
- network access where required for allowed model/package/font downloads, or a fully prepopulated offline environment

Until those runtime blockers are fixed, the code can be submitted as an implementation-focused project, but the final MP4 should not be claimed as generated.
