"""Runs the transcription backend comparison across every gold-standard case
in eval/gold_audio/.

Each case is a directory under eval/gold_audio/ containing:
  - an audio file (any format under SUPPORTED_AUDIO_FORMATS)
  - gold_transcript.json — see eval/README.md for the schema

Usage:
    uv run python eval/run_eval.py [--model MODEL_SIZE] [--backend BACKEND] [--case CASE_NAME]

Examples:
    uv run python eval/run_eval.py                          # all cases, both backends, medium model
    uv run python eval/run_eval.py --model small             # all cases, both backends, small model
    uv run python eval/run_eval.py --backend mlx --case retro_5min
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from transcribe3.core.audio.transcriber import transcribe_audio  # noqa: E402

GOLD_DIR = Path(__file__).parent / "gold_audio"
RESULTS_DIR = Path(__file__).parent / "results"
BACKENDS = ("whisperx", "mlx")


def _word_error_rate(hypothesis: str, reference: str) -> float:
    """Copied from transcribe3.cli._word_error_rate to avoid importing the CLI module."""
    ref_words = reference.lower().split()
    hyp_words = hypothesis.lower().split()
    n = len(ref_words)
    if n == 0:
        return 0.0 if len(hyp_words) == 0 else 1.0

    r, h = len(ref_words), len(hyp_words)
    dp = [[0] * (h + 1) for _ in range(r + 1)]
    for i in range(r + 1):
        dp[i][0] = i
    for j in range(h + 1):
        dp[0][j] = j
    for i in range(1, r + 1):
        for j in range(1, h + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j - 1], dp[i - 1][j], dp[i][j - 1])
    return dp[r][h] / n


def discover_cases() -> list[Path]:
    if not GOLD_DIR.exists():
        return []
    return sorted(d for d in GOLD_DIR.iterdir() if d.is_dir() and (d / "gold_transcript.json").exists())


def find_audio_file(case_dir: Path, gold: dict) -> Path:
    audio_file = gold.get("audio_file")
    if audio_file:
        path = case_dir / audio_file
        if path.exists():
            return path
    # Fall back: any non-JSON/py/txt file in the case dir.
    for candidate in case_dir.iterdir():
        if candidate.suffix.lower() in {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".mp4"}:
            return candidate
    raise FileNotFoundError(f"No audio file found in {case_dir}")


def run_case(case_dir: Path, model_size: str, backend: str) -> dict:
    gold = json.loads((case_dir / "gold_transcript.json").read_text())
    audio_path = find_audio_file(case_dir, gold)
    reference_text = " ".join(seg["text"] for seg in gold["segments"])

    start = time.monotonic()
    try:
        segments = transcribe_audio(audio_path, model_size, backend)
    except Exception as exc:
        return {"error": str(exc)}
    elapsed = time.monotonic() - start

    hypothesis_text = " ".join(s.get("text", "").strip() for s in segments)
    wer = _word_error_rate(hypothesis_text, reference_text)

    return {
        "elapsed_sec": round(elapsed, 2),
        "num_segments": len(segments),
        "wer": round(wer, 4),
        "hypothesis_text": hypothesis_text,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="medium", help="Whisper model size (default: medium)")
    parser.add_argument("--backend", choices=BACKENDS, help="Run only this backend (default: both)")
    parser.add_argument("--case", help="Run only this case name (default: all cases)")
    args = parser.parse_args()

    cases = discover_cases()
    if args.case:
        cases = [c for c in cases if c.name == args.case]
    if not cases:
        print(f"No gold cases found under {GOLD_DIR}" + (f" matching '{args.case}'" if args.case else ""))
        raise SystemExit(1)

    backends = [args.backend] if args.backend else list(BACKENDS)
    RESULTS_DIR.mkdir(exist_ok=True)

    out_path = RESULTS_DIR / f"results_{args.model}.json"
    all_results: dict[str, dict] = json.loads(out_path.read_text()) if out_path.exists() else {}

    for case_dir in cases:
        case_name = case_dir.name
        print(f"=== case: {case_name} ===")
        all_results.setdefault(case_name, {})
        for backend in backends:
            print(f"  --- {backend} ({args.model}) ---")
            result = run_case(case_dir, args.model, backend)
            all_results[case_name][backend] = result
            if "error" in result:
                print(f"    FAILED: {result['error']}")
            else:
                print(f"    elapsed: {result['elapsed_sec']}s  segments: {result['num_segments']}  WER: {result['wer']}")

    out_path.write_text(json.dumps(all_results, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
