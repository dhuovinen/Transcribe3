# Transcribe3 — Testing Strategy

## Overview

Testing is a first-class requirement. Accuracy must be measurable, not assumed. Tests are written alongside implementation — not after.

---

## Test Layers

### Unit Tests — `tests/unit/`

Target: `src/transcribe3/core/`

- Coverage target: **≥ 80%** for all `core/` modules.
- The LLM backend is always injected, so unit tests use a mock backend that returns deterministic responses. No live model calls in unit tests.
- No file I/O in unit tests — `data/` layer is mocked at the interface boundary.
- No hardcoded file paths or secrets.
- Fast: each unit test should run in milliseconds.

### Integration Tests — `tests/integration/`

Target: CLI end-to-end and FastAPI handlers end-to-end.

- CLI integration tests invoke `transcribe3` commands against fixture inputs and assert on exit codes, stdout structure, and output files.
- API integration tests use FastAPI's `TestClient` to exercise handler routes end-to-end.
- These tests may perform real file I/O against `tests/fixtures/` but must not call live LLM endpoints.

---

## Fixtures — `tests/fixtures/`

- Sample raw transcripts (plain text, OCR-style, loosely formatted) for parsing and cleaning tests.
- Sample audio files (short, synthetic or license-cleared) for Phase 2+ audio pipeline tests.
- No real personal or sensitive content in fixtures.
- No hardcoded absolute paths — fixtures are loaded relative to the test file or via a `conftest.py` helper.

---

## Gold Standard Test Set — `tests/gold/`

The gold standard test set is used exclusively for accuracy benchmarking, not for regular pytest runs.

- Manually corrected transcripts serve as ground truth.
- Minimum viable gold set: one fully corrected two-party interview with paired audio where available.
- Gold files are not modified by the pipeline — they are read-only reference data.
- Stored as JSON in the canonical `TranscriptSegment` format.

---

## Running Tests

```bash
# Run all tests
uv run pytest

# Run unit tests only
uv run pytest tests/unit/

# Run integration tests only
uv run pytest tests/integration/

# Run with coverage report
uv run pytest --cov=src

# Run with coverage and enforce threshold
uv run pytest --cov=src --cov-fail-under=80
```

---

## Benchmarking

Benchmarking is separate from the test suite and runs against the gold standard test set.

```bash
# Run the full benchmarking pipeline against the gold set
uv run transcribe3 benchmark tests/gold/
```

The `benchmark` command:
1. Runs the full pipeline against each gold set entry for the configured LLM backend.
2. Computes and reports:
   - **WER (Word Error Rate)** — transcription accuracy vs. ground truth
   - **Attribution accuracy** — percentage of segments with correct speaker label
   - **Confidence calibration** — correlation between confidence scores and actual accuracy
   - **Cleaning precision/recall** — correct vs. over/under-cleaning decisions
3. Stores results as JSON for comparison across runs and model backends.

To compare two models:

```bash
uv run transcribe3 benchmark tests/gold/ --model llama3
uv run transcribe3 benchmark tests/gold/ --model mistral
```

Results files are written to a `benchmark-results/` directory and can be diffed or analyzed programmatically.

---

## Test Hygiene Rules

- No hardcoded file paths — use `pathlib.Path(__file__).parent` or `conftest.py` fixtures.
- No secrets or API keys in test files or fixtures.
- No live network calls in `pytest` runs — mock all LLM backends and external services.
- Tests must pass before any task is marked complete.
- Broken tests are never committed to `main`.
