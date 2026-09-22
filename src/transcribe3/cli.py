from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

load_dotenv()

from transcribe3.shared.types import (
    CleaningConfig,
    CleaningMode,
    FillerWordBehavior,
    LLMProviderConfig,
    OutputFormat,
    SegmentFlag,
    TranscriptSession,
)
from transcribe3.shared.constants import DEFAULT_LLM_MODEL, DEFAULT_LOW_CONFIDENCE_THRESHOLD
from transcribe3.core.cleaner import clean_transcript
from transcribe3.core.attributor import attribute_speakers
from transcribe3.core.llm.client import build_llm_client, LLMUnavailableError
from transcribe3.data.secrets import resolve_provider_api_key
from transcribe3.data.parsers import parse_transcript
from transcribe3.data.session import SessionRepository
from transcribe3.data.settings import SettingsRepository
from transcribe3.data.exporters import export

app = typer.Typer(name="transcribe3", help="Transcript validation and enrichment pipeline.")
sessions_app = typer.Typer(help="Manage sessions.")
app.add_typer(sessions_app, name="sessions")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_tty() -> bool:
    return sys.stdout.isatty()


def _sessions_dir_default() -> Path:
    env = os.environ.get("TRANSCRIBE3_SESSIONS_DIR")
    return Path(env) if env else Path("sessions")


def _config_dir_default() -> Path:
    env = os.environ.get("TRANSCRIBE3_CONFIG_DIR")
    return Path(env) if env else Path("config")


def _output_path(sessions_dir: Path, session_id: str, fmt: OutputFormat) -> Path:
    return sessions_dir / session_id / f"output.{fmt.value}"


def _resolve_provider(sessions_dir: Path, provider_id: str) -> LLMProviderConfig:
    """Resolve --provider against llm_providers in settings.json, exiting with a clear
    error (and the list of configured ids) if it doesn't match one.

    `sessions_dir` is only consulted as the legacy location settings.json used to
    live in — see SettingsRepository.load — the file itself now lives under
    _config_dir_default()."""
    settings = SettingsRepository.load(_config_dir_default(), sessions_dir)
    provider = settings.find_provider(provider_id)
    if provider is None:
        known = [p.id for p in settings.llm_providers]
        msg = f"Unknown LLM provider {provider_id!r}. Configured providers: {known}"
        if _is_tty():
            typer.echo(f"Error: {msg}", err=True)
        else:
            typer.echo(json.dumps({"error": msg}))
        raise typer.Exit(2)
    return provider


def _build_client(provider: LLMProviderConfig):
    """Build an LLM client for `provider`, including its bearer token if one is
    configured in the environment (TRANSCRIBE3_LLM_API_KEY_<ID>, or the variable
    named by the provider's api_key_env)."""
    return build_llm_client(provider, api_key=resolve_provider_api_key(provider))


def _confidence_summary(
    segments: list,
    threshold: float,
) -> dict:
    total = len(segments)
    low_conf = sum(
        1 for s in segments if SegmentFlag.LOW_CONFIDENCE in s.flags
    )
    mean_conf = (
        sum(s.confidence for s in segments) / total if total else 0.0
    )
    return {
        "total_segments": total,
        "low_confidence_count": low_conf,
        "mean_confidence": round(mean_conf, 4),
    }


def _print_confidence_summary(
    summary: dict, output_file: Optional[Path], quiet: bool
) -> None:
    if quiet:
        return
    typer.echo(f"Segments:          {summary['total_segments']}")
    typer.echo(f"Low-confidence:    {summary['low_confidence_count']}")
    typer.echo(f"Mean confidence:   {summary['mean_confidence']:.4f}")
    if output_file is not None:
        typer.echo(f"Output:            {output_file}")


# ---------------------------------------------------------------------------
# clean command
# ---------------------------------------------------------------------------

@app.command()
def clean(
    transcript_file: Path = typer.Argument(..., help="Path to the transcript file to process."),
    model: str = typer.Option(DEFAULT_LLM_MODEL, "--model", help="LLM model name."),
    provider: str = typer.Option("ollama", "--provider", help="LLM provider id from settings.json llm_providers."),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="Directory to store sessions."),
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format."),
    filler_words: FillerWordBehavior = typer.Option(
        FillerWordBehavior.OFF, "--filler-words", help="Filler word behaviour."
    ),
    remove_false_starts: bool = typer.Option(False, "--remove-false-starts", is_flag=True, help="Remove false starts."),
    verbatim: bool = typer.Option(False, "--verbatim", is_flag=True, help="Verbatim mode — no cleaning."),
    confidence_threshold: float = typer.Option(
        DEFAULT_LOW_CONFIDENCE_THRESHOLD,
        "--confidence-threshold",
        help="Low-confidence threshold (0.0–1.0).",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", is_flag=True, help="Plan without writing files."),
    quiet: bool = typer.Option(False, "--quiet", is_flag=True, help="Suppress progress output."),
    verbose: bool = typer.Option(False, "--verbose", is_flag=True, help="Show per-segment details."),
) -> None:
    """Parse, clean, and attribute speakers in a transcript file."""
    sessions_dir = output_dir if output_dir is not None else _sessions_dir_default()
    provider_config = _resolve_provider(sessions_dir, provider)

    # Step 1: Validate file exists and format is supported
    if not transcript_file.exists():
        msg = f"File not found: {transcript_file}"
        if _is_tty():
            typer.echo(f"Error: {msg}", err=True)
        else:
            typer.echo(json.dumps({"error": msg}))
        raise typer.Exit(1)

    supported = [".txt", ".srt", ".vtt", ".json"]
    if transcript_file.suffix.lower() not in supported:
        msg = f"Unsupported format: {transcript_file.suffix!r}. Supported: {supported}"
        if _is_tty():
            typer.echo(f"Error: {msg}", err=True)
        else:
            typer.echo(json.dumps({"error": msg}))
        raise typer.Exit(1)

    # Step 2: Parse
    if not quiet:
        typer.echo(f"Parsing {transcript_file}...")
    try:
        segments = parse_transcript(transcript_file)
    except Exception as exc:
        msg = f"Failed to parse transcript: {exc}"
        if _is_tty():
            typer.echo(f"Error: {msg}", err=True)
        else:
            typer.echo(json.dumps({"error": msg}))
        raise typer.Exit(2)

    # Step 3: Build CleaningConfig
    mode = CleaningMode.VERBATIM if verbatim else CleaningMode.STANDARD
    config = CleaningConfig(
        mode=mode,
        filler_words=filler_words,
        remove_false_starts=remove_false_starts,
        low_confidence_threshold=confidence_threshold,
        llm_model=model,
        llm_provider_id=provider_config.id,
    )

    if dry_run:
        # Dry-run: show what would happen without writing
        session_id_placeholder = "<new-uuid>"
        planned_session_dir = sessions_dir / session_id_placeholder
        planned_output = planned_session_dir / f"output.{format.value}"
        if _is_tty():
            typer.echo("[dry-run] Would create session:")
            typer.echo(f"  Session dir:  {planned_session_dir}")
            typer.echo(f"  Output file:  {planned_output}")
            typer.echo(f"  Segments:     {len(segments)}")
            typer.echo(f"  Mode:         {mode.value}")
        else:
            typer.echo(json.dumps({
                "dry_run": True,
                "planned_session_dir": str(planned_session_dir),
                "planned_output_file": str(planned_output),
                "segment_count": len(segments),
                "mode": mode.value,
            }))
        return

    # Step 4: Create session
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session = SessionRepository.create(transcript_file, sessions_dir)
    if not quiet:
        typer.echo(f"Session created: {session.session_id[:8]}...")

    # Step 5: Clean
    if not quiet:
        typer.echo("Cleaning transcript...")
    cleaned_segments = clean_transcript(segments, config)

    # Step 6: Attribute speakers
    if not quiet:
        typer.echo("Attributing speakers...")
    try:
        attributed_segments = attribute_speakers(cleaned_segments, config, _build_client(provider_config), model)
    except LLMUnavailableError as exc:
        # Only suggest starting the server when nothing answered; a status code means
        # it is running and refused the request (e.g. 401 for a missing bearer token).
        hint = "" if exc.status_code else f" Ensure {provider_config.label} is running."
        msg = f"LLM unavailable: {exc}.{hint}"
        if _is_tty():
            typer.echo(f"Error: {msg}", err=True)
        else:
            typer.echo(json.dumps({"error": msg}))
        raise typer.Exit(2)

    # Step 7: Update session segments
    session = session.model_copy(update={"segments": attributed_segments})

    # Step 8: Save session
    SessionRepository.save(session, sessions_dir)
    if not quiet:
        typer.echo("Session saved.")

    # Step 9: Export
    output_file = _output_path(sessions_dir, session.session_id, format)
    exported_path = export(session, format, output_file)
    if not quiet:
        typer.echo(f"Exported to {exported_path}")

    # Step 10: Confidence summary / verbose output
    if verbose and not quiet:
        for seg in attributed_segments:
            flags_str = ",".join(f.value for f in seg.flags) if seg.flags else "none"
            typer.echo(
                f"  [{seg.id[:8]}] {seg.speaker.display_name!r:20s} "
                f"conf={seg.confidence:.3f} flags={flags_str} | {seg.text[:60]}"
            )

    summary = _confidence_summary(attributed_segments, confidence_threshold)

    if _is_tty():
        _print_confidence_summary(summary, exported_path, quiet)
    else:
        typer.echo(json.dumps({
            **summary,
            "session_id": session.session_id,
            "output_file": str(exported_path),
        }))


# ---------------------------------------------------------------------------
# export command
# ---------------------------------------------------------------------------

@app.command("export")
def export_cmd(
    session_id: str = typer.Argument(..., help="Session ID to export."),
    format: OutputFormat = typer.Option(..., "--format", help="Output format."),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="Sessions directory."),
    out: Optional[Path] = typer.Option(None, "--out", help="Custom output file path."),
) -> None:
    """Export an existing session to a specific format."""
    sessions_dir = output_dir if output_dir is not None else _sessions_dir_default()

    try:
        session = SessionRepository.load(session_id, sessions_dir)
    except FileNotFoundError as exc:
        msg = str(exc)
        if _is_tty():
            typer.echo(f"Error: {msg}", err=True)
        else:
            typer.echo(json.dumps({"error": msg}))
        raise typer.Exit(1)

    output_file = out if out is not None else _output_path(sessions_dir, session_id, format)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        exported_path = export(session, format, output_file)
    except Exception as exc:
        msg = f"Export failed: {exc}"
        if _is_tty():
            typer.echo(f"Error: {msg}", err=True)
        else:
            typer.echo(json.dumps({"error": msg}))
        raise typer.Exit(2)

    if _is_tty():
        typer.echo(str(exported_path))
    else:
        typer.echo(json.dumps({"output_file": str(exported_path)}))


# ---------------------------------------------------------------------------
# sessions list command
# ---------------------------------------------------------------------------

@sessions_app.command("list")
def sessions_list(
    sessions_dir: Optional[Path] = typer.Option(None, "--sessions-dir", help="Sessions directory."),
    json_output: bool = typer.Option(False, "--json", is_flag=True, help="Output as JSON array."),
) -> None:
    """List all sessions."""
    dir_ = sessions_dir if sessions_dir is not None else _sessions_dir_default()

    if not dir_.exists():
        if json_output or not _is_tty():
            typer.echo(json.dumps([]))
        else:
            typer.echo("No sessions found (directory does not exist).")
        return

    sessions = SessionRepository.list_sessions(dir_)

    if json_output or not _is_tty():
        output = [
            {
                "session_id": s.session_id,
                "source_file": s.source_file,
                "created_at": s.created_at.isoformat(),
                "segment_count": len(s.segments),
                "low_confidence_count": sum(
                    1 for seg in s.segments if SegmentFlag.LOW_CONFIDENCE in seg.flags
                ),
            }
            for s in sessions
        ]
        typer.echo(json.dumps(output, indent=2))
        return

    if not sessions:
        typer.echo("No sessions found.")
        return

    # Human-readable table
    col_id = 8
    col_file = 30
    col_created = 19
    col_segs = 8
    col_low = 13

    header = (
        f"{'ID':<{col_id}}  "
        f"{'Source File':<{col_file}}  "
        f"{'Created':<{col_created}}  "
        f"{'Segments':>{col_segs}}  "
        f"{'Low-Confidence':>{col_low}}"
    )
    typer.echo(header)
    typer.echo("-" * len(header))

    for s in sessions:
        low = sum(1 for seg in s.segments if SegmentFlag.LOW_CONFIDENCE in seg.flags)
        created_str = s.created_at.strftime("%Y-%m-%d %H:%M:%S")
        source = s.source_file[:col_file]
        typer.echo(
            f"{s.session_id[:col_id]:<{col_id}}  "
            f"{source:<{col_file}}  "
            f"{created_str:<{col_created}}  "
            f"{len(s.segments):>{col_segs}}  "
            f"{low:>{col_low}}"
        )


# ---------------------------------------------------------------------------
# sessions show command
# ---------------------------------------------------------------------------

@sessions_app.command("show")
def sessions_show(
    session_id: str = typer.Argument(..., help="Session ID to show."),
    sessions_dir: Optional[Path] = typer.Option(None, "--sessions-dir", help="Sessions directory."),
    json_output: bool = typer.Option(False, "--json", is_flag=True, help="Output full session as JSON."),
) -> None:
    """Show details of a single session."""
    dir_ = sessions_dir if sessions_dir is not None else _sessions_dir_default()

    try:
        session = SessionRepository.load(session_id, dir_)
    except FileNotFoundError as exc:
        msg = str(exc)
        if json_output or not _is_tty():
            typer.echo(json.dumps({"error": msg}))
        else:
            typer.echo(f"Error: {msg}", err=True)
        raise typer.Exit(1)

    if json_output or not _is_tty():
        typer.echo(json.dumps(session.model_dump(mode="json"), indent=2, default=str))
        return

    low_conf = sum(1 for seg in session.segments if SegmentFlag.LOW_CONFIDENCE in seg.flags)
    mean_conf = (
        sum(seg.confidence for seg in session.segments) / len(session.segments)
        if session.segments
        else 0.0
    )

    typer.echo(f"Session ID:      {session.session_id}")
    typer.echo(f"Source file:     {session.source_file}")
    typer.echo(f"Created at:      {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    typer.echo(f"Segments:        {len(session.segments)}")
    typer.echo(f"Low-confidence:  {low_conf}")
    typer.echo(f"Mean confidence: {mean_conf:.4f}")
    if session.speaker_map:
        typer.echo("Speaker map:")
        for anon, name in session.speaker_map.items():
            typer.echo(f"  {anon} -> {name}")
    else:
        typer.echo("Speaker map:     (empty)")


# ---------------------------------------------------------------------------
# benchmark command
# ---------------------------------------------------------------------------

def _word_error_rate(hypothesis: str, reference: str) -> float:
    """Compute word error rate using dynamic programming (S + D + I) / N."""
    ref_words = reference.lower().split()
    hyp_words = hypothesis.lower().split()
    n = len(ref_words)
    if n == 0:
        return 0.0 if len(hyp_words) == 0 else 1.0

    r = len(ref_words)
    h = len(hyp_words)

    # dp[i][j] = edit distance between ref[:i] and hyp[:j]
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
                dp[i][j] = 1 + min(
                    dp[i - 1][j - 1],  # substitution
                    dp[i - 1][j],      # deletion
                    dp[i][j - 1],      # insertion
                )

    return dp[r][h] / n


@app.command()
def benchmark(
    gold_dir: Path = typer.Argument(..., help="Directory of gold-standard test cases."),
    model: str = typer.Option(DEFAULT_LLM_MODEL, "--model", help="LLM model name."),
    provider: str = typer.Option("ollama", "--provider", help="LLM provider id from settings.json llm_providers."),
    sessions_dir: Optional[Path] = typer.Option(None, "--sessions-dir", help="Sessions directory."),
    json_output: bool = typer.Option(False, "--json", is_flag=True, help="Output results as JSON."),
) -> None:
    """Run benchmark against gold-standard cases in gold_dir."""
    dir_ = sessions_dir if sessions_dir is not None else _sessions_dir_default()
    provider_config = _resolve_provider(dir_, provider)

    if not gold_dir.exists() or not gold_dir.is_dir():
        msg = f"gold_dir not found or not a directory: {gold_dir}"
        if _is_tty():
            typer.echo(f"Error: {msg}", err=True)
        else:
            typer.echo(json.dumps({"error": msg}))
        raise typer.Exit(1)

    cases = [
        d for d in sorted(gold_dir.iterdir())
        if d.is_dir() and (d / "input.txt").exists() and (d / "expected.json").exists()
    ]

    if not cases:
        msg = f"No valid benchmark cases found in {gold_dir} (each needs input.txt + expected.json)"
        if _is_tty():
            typer.echo(msg)
        else:
            typer.echo(json.dumps({"error": msg}))
        raise typer.Exit(1)

    results = []

    for case_dir in cases:
        input_path = case_dir / "input.txt"
        expected_path = case_dir / "expected.json"
        case_name = case_dir.name

        if not json_output and _is_tty():
            typer.echo(f"Running case: {case_name}...")

        # Load expected data
        try:
            expected_raw = json.loads(expected_path.read_text(encoding="utf-8"))
            if isinstance(expected_raw, list):
                expected_segments = expected_raw
            elif isinstance(expected_raw, dict) and "segments" in expected_raw:
                expected_segments = expected_raw["segments"]
            else:
                expected_segments = []
        except Exception as exc:
            results.append({
                "case": case_name,
                "error": f"Failed to load expected.json: {exc}",
            })
            continue

        # Run the clean pipeline
        try:
            segments = parse_transcript(input_path)
        except Exception as exc:
            results.append({"case": case_name, "error": f"Parse failed: {exc}"})
            continue

        config = CleaningConfig(
            mode=CleaningMode.STANDARD,
            llm_model=model,
            llm_provider_id=provider_config.id,
        )
        dir_.mkdir(parents=True, exist_ok=True)
        session = SessionRepository.create(input_path, dir_)

        try:
            cleaned = clean_transcript(segments, config)
            attributed = attribute_speakers(cleaned, config, _build_client(provider_config), model)
        except LLMUnavailableError as exc:
            results.append({"case": case_name, "error": f"LLM unavailable: {exc}"})
            continue
        except Exception as exc:
            results.append({"case": case_name, "error": f"Processing failed: {exc}"})
            continue

        session = session.model_copy(update={"segments": attributed})
        SessionRepository.save(session, dir_)

        # Compute attribution accuracy
        correct = 0
        comparable = min(len(attributed), len(expected_segments))
        for pred_seg, exp_seg in zip(attributed, expected_segments):
            exp_speaker = (
                exp_seg.get("speaker", {}).get("anonymous_id", "")
                if isinstance(exp_seg, dict)
                else ""
            )
            if pred_seg.speaker.anonymous_id == exp_speaker:
                correct += 1
        attribution_accuracy = correct / comparable if comparable else 0.0

        # Compute WER
        pred_text = " ".join(s.text for s in attributed)
        ref_text = " ".join(
            (s.get("text", "") if isinstance(s, dict) else "")
            for s in expected_segments
        )
        wer = _word_error_rate(pred_text, ref_text)

        results.append({
            "case": case_name,
            "attribution_accuracy": round(attribution_accuracy, 4),
            "wer": round(wer, 4),
            "predicted_segments": len(attributed),
            "expected_segments": len(expected_segments),
        })

        if not json_output and _is_tty():
            typer.echo(
                f"  Attribution accuracy: {attribution_accuracy:.1%}  "
                f"WER: {wer:.4f}"
            )

    # Aggregate
    valid = [r for r in results if "error" not in r]
    agg = {}
    if valid:
        agg["mean_attribution_accuracy"] = round(
            sum(r["attribution_accuracy"] for r in valid) / len(valid), 4
        )
        agg["mean_wer"] = round(sum(r["wer"] for r in valid) / len(valid), 4)
        agg["cases_run"] = len(valid)
        agg["cases_errored"] = len(results) - len(valid)

    if json_output or not _is_tty():
        typer.echo(json.dumps({"results": results, "aggregate": agg}, indent=2))
        return

    typer.echo("")
    typer.echo("=== Aggregate ===")
    if valid:
        typer.echo(f"Cases run:               {agg['cases_run']}")
        typer.echo(f"Cases errored:           {agg['cases_errored']}")
        typer.echo(f"Mean attribution acc:    {agg['mean_attribution_accuracy']:.1%}")
        typer.echo(f"Mean WER:                {agg['mean_wer']:.4f}")
    else:
        typer.echo("No valid cases completed.")


# ---------------------------------------------------------------------------
# transcribe command (Phase 2 — audio pipeline)
# ---------------------------------------------------------------------------

@app.command()
def transcribe(
    audio_file: Path = typer.Argument(..., help="Path to the audio file to transcribe."),
    whisper_model: str = typer.Option("base", "--whisper-model", help="WhisperX model size (tiny/base/small/medium/large-v2)."),
    backend: str = typer.Option("whisperx", "--backend", help="Transcription backend: 'whisperx' (CPU) or 'mlx' (Apple Silicon GPU, requires uv sync --extra mlx)."),
    model: str = typer.Option(DEFAULT_LLM_MODEL, "--model", help="LLM model for cleaning and attribution."),
    llm_provider: str = typer.Option(
        "ollama", "--llm-provider", help="LLM provider id from settings.json llm_providers for cleaning and attribution."
    ),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="Directory to store sessions."),
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", help="Output format."),
    dry_run: bool = typer.Option(False, "--dry-run", is_flag=True, help="Plan without writing files."),
    quiet: bool = typer.Option(False, "--quiet", is_flag=True, help="Suppress progress output."),
) -> None:
    """Transcribe and diarize an audio file (Phase 2 — requires whisperx and pyannote.audio)."""
    sessions_dir = output_dir if output_dir is not None else _sessions_dir_default()
    provider_config = _resolve_provider(sessions_dir, llm_provider)

    if not audio_file.exists():
        msg = f"File not found: {audio_file}"
        if _is_tty():
            typer.echo(f"Error: {msg}", err=True)
        else:
            typer.echo(json.dumps({"error": msg}))
        raise typer.Exit(1)

    from transcribe3.shared.constants import SUPPORTED_AUDIO_FORMATS
    if audio_file.suffix.lower() not in SUPPORTED_AUDIO_FORMATS:
        msg = f"Unsupported format: {audio_file.suffix!r}. Supported: {SUPPORTED_AUDIO_FORMATS}"
        if _is_tty():
            typer.echo(f"Error: {msg}", err=True)
        else:
            typer.echo(json.dumps({"error": msg}))
        raise typer.Exit(1)

    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        msg = "HF_TOKEN not set. Add HF_TOKEN=hf_... to your .env file."
        if _is_tty():
            typer.echo(f"Error: {msg}", err=True)
        else:
            typer.echo(json.dumps({"error": msg}))
        raise typer.Exit(1)

    if dry_run:
        if _is_tty():
            typer.echo(f"[dry-run] Would transcribe: {audio_file}")
            typer.echo(f"  WhisperX model: {whisper_model}")
            typer.echo(f"  Backend:        {backend}")
            typer.echo(f"  HF_TOKEN:       set")
        else:
            typer.echo(json.dumps({
                "dry_run": True,
                "audio_file": str(audio_file),
                "whisper_model": whisper_model,
                "backend": backend,
            }))
        return

    try:
        from transcribe3.core.audio.pipeline import run_audio_pipeline
    except ImportError as exc:
        msg = f"Audio dependencies not installed: {exc}. Run: uv sync --extra audio"
        if _is_tty():
            typer.echo(f"Error: {msg}", err=True)
        else:
            typer.echo(json.dumps({"error": msg}))
        raise typer.Exit(1)

    if not quiet:
        typer.echo(f"Transcribing {audio_file} with {backend} ({whisper_model})…")

    try:
        segments = run_audio_pipeline(audio_file, hf_token, whisper_model, backend)
    except RuntimeError as exc:
        msg = str(exc)
        if _is_tty():
            typer.echo(f"Error: {msg}", err=True)
        else:
            typer.echo(json.dumps({"error": msg}))
        raise typer.Exit(2)

    if not quiet:
        typer.echo(f"Got {len(segments)} segments. Running cleaning + attribution…")

    # Chain the Phase 1 quality layer, same as transcript input
    config = CleaningConfig(llm_model=model, llm_provider_id=provider_config.id)
    warning = None
    segments = clean_transcript(segments, config)
    try:
        segments = attribute_speakers(segments, config, _build_client(provider_config), model)
    except LLMUnavailableError:
        warning = f"LLM attribution skipped — {provider_config.label} is not running. Diarization labels are unvalidated."
        if not quiet and _is_tty():
            typer.echo(f"Warning: {warning}", err=True)
    except Exception as exc:
        warning = f"LLM attribution failed ({exc}) — diarization labels are unvalidated."
        if not quiet and _is_tty():
            typer.echo(f"Warning: {warning}", err=True)

    sessions_dir.mkdir(parents=True, exist_ok=True)
    session = SessionRepository.create(audio_file, sessions_dir)
    session = session.model_copy(update={
        "segments": segments,
        "audio_file": audio_file.name,
        "warning": warning,
    })
    SessionRepository.save(session, sessions_dir)

    output_file = _output_path(sessions_dir, session.session_id, format)
    exported_path = export(session, format, output_file)

    summary = _confidence_summary(segments, 0.6)

    if _is_tty():
        _print_confidence_summary(summary, exported_path, quiet)
    else:
        typer.echo(json.dumps({
            **summary,
            "session_id": session.session_id,
            "output_file": str(exported_path),
        }))
