interface Props {
  onClose: () => void
}

export default function HelpModal({ onClose }: Props) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 style={{ margin: 0 }}>Transcribe3 — Help</h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <div className="modal-body">
          <h3>What is this?</h3>
          <p>
            Transcribe3 is a local transcript validation and enrichment pipeline.
            It takes raw transcripts (or audio in Phase 2) and produces clean,
            speaker-attributed output — with confidence scores on every decision.
            All processing runs on your machine. Nothing leaves it.
          </p>

          <h3>Phase 1 — Transcript cleaning (current)</h3>
          <ol>
            <li>Upload a raw transcript (.txt, .srt, .vtt, or .json)</li>
            <li>The pipeline normalises formatting, removes OCR artifacts, and uses a local LLM to validate speaker attribution</li>
            <li>Low-confidence segments are highlighted for your review</li>
            <li>Assign real names to anonymous speaker IDs, override any misattributions, then export</li>
          </ol>

          <h3>Supported input formats</h3>
          <table className="help-table">
            <thead><tr><th>Format</th><th>Notes</th></tr></thead>
            <tbody>
              <tr><td><code>.txt</code></td><td>Plain text with speaker labels (e.g. <code>JANE: …</code> or <code>[Jane] …</code>)</td></tr>
              <tr><td><code>.srt</code></td><td>SubRip subtitle format — timecodes preserved</td></tr>
              <tr><td><code>.vtt</code></td><td>WebVTT format — timecodes preserved</td></tr>
              <tr><td><code>.json</code></td><td>Transcribe3 JSON session format</td></tr>
            </tbody>
          </table>

          <h3>WhisperX model performance</h3>
          <p>
            When transcribing audio, larger Whisper models are more accurate but slower.
            The table below is a practical comparison built from OpenAI's published Whisper
            benchmarks. Accuracy values are approximate — OpenAI presents the model-size
            results graphically across 12 English datasets rather than as a precise table.
          </p>
          <table className="help-table">
            <thead>
              <tr>
                <th>Model</th>
                <th>Parameters</th>
                <th>Approx. English WER</th>
                <th>Approx. word accuracy*</th>
                <th>Relative transcription speed</th>
                <th>Relative processing time</th>
              </tr>
            </thead>
            <tbody>
              <tr><td><code>tiny</code></td><td>39M</td><td>~18–19%</td><td>~81–82%</td><td>~10×</td><td>~10% of large</td></tr>
              <tr><td><code>base</code></td><td>74M</td><td>~14–15%</td><td>~85–86%</td><td>~7×</td><td>~14% of large</td></tr>
              <tr><td><code>small</code></td><td>244M</td><td>~11%</td><td>~89%</td><td>~4×</td><td>~25% of large</td></tr>
              <tr><td><code>medium</code></td><td>769M</td><td>~9–10%</td><td>~90–91%</td><td>~2×</td><td>~50% of large</td></tr>
              <tr><td><code>large-v2</code></td><td>1.55B</td><td>~8.5–9%</td><td>~91–92%</td><td>1× baseline</td><td>100%</td></tr>
              <tr><td><code>large-v3</code></td><td>1.55B</td><td>Generally better than large-v2</td><td>Typically the highest of these models</td><td>Approximately 1×</td><td>Approximately 100%</td></tr>
            </tbody>
          </table>
          <p style={{ fontSize: 12, color: '#6b7280' }}>
            *"Word accuracy" is shown simply as 100% − WER to make the results easier to
            interpret. WER remains the more appropriate technical measure.
            <br />
            Source:{' '}
            <a href="https://cdn.openai.com/papers/whisper.pdf" target="_blank" rel="noopener noreferrer">
              https://cdn.openai.com/papers/whisper.pdf
            </a>
          </p>

          <h3>Benchmarking &amp; gold evals</h3>
          <p>
            Transcription backends (WhisperX vs mlx-whisper) can be compared for
            speed and accuracy using a gold-standard eval harness in the repo —
            useful before switching a default, or after a model/library upgrade.
          </p>
          <table className="help-table">
            <thead><tr><th>Thing</th><th>Where</th></tr></thead>
            <tbody>
              <tr><td>Gold audio + transcript pairs</td><td><code>eval/gold_audio/&lt;case_name&gt;/</code></td></tr>
              <tr><td>How to add a new gold case</td><td><code>eval/README.md</code></td></tr>
              <tr><td>Run the comparison</td><td><code>eval/run_eval.py</code></td></tr>
              <tr><td>Past write-ups</td><td><code>docs/evaluations/</code></td></tr>
            </tbody>
          </table>
          <p>Run an eval from a terminal in the project root:</p>
          <pre className="code-block">{`uv sync --extra mlx                                # one-time setup, enables the mlx backend
uv run python eval/run_eval.py                     # all gold cases, both backends, medium model
uv run python eval/run_eval.py --model small        # try a different model size
uv run python eval/run_eval.py --case retro_5min     # just one case
uv run python eval/run_eval.py --backend mlx          # just one backend`}</pre>
          <p>
            Results (elapsed time, segment count, Word Error Rate against the gold
            transcript) are written to <code>eval/results/results_&lt;model&gt;.json</code>.
          </p>
          <p>
            <strong>Adding your own gold case:</strong> either generate a synthetic
            clip from a script via macOS <code>say</code> (fast, exact ground
            truth, no privacy concerns — see <code>eval/gold_audio/retro_5min/generate.py</code>{' '}
            for a template), or add a real recording and manually verify its
            transcript word-for-word against the audio before treating it as gold.
            Full instructions, the <code>gold_transcript.json</code> schema, and the
            tradeoffs of each approach are in <code>eval/README.md</code>.
          </p>

          <h3>Export formats</h3>
          <table className="help-table">
            <thead><tr><th>Format</th><th>Best for</th></tr></thead>
            <tbody>
              <tr><td><code>JSON</code></td><td>Downstream AI pipelines — full metadata preserved</td></tr>
              <tr><td><code>SRT</code></td><td>Video captions and subtitles</td></tr>
              <tr><td><code>VTT</code></td><td>Web video captions (HTML5)</td></tr>
              <tr><td><code>TXT</code></td><td>Plain human-readable text</td></tr>
            </tbody>
          </table>

          <h3>Cleaning options</h3>
          <table className="help-table">
            <thead><tr><th>Option</th><th>What it does</th></tr></thead>
            <tbody>
              <tr><td>Verbatim mode</td><td>Disables all cleaning — exact speech record (for legal or journalism)</td></tr>
              <tr><td>Filler words: Off</td><td>No action on um, uh, you know, etc.</td></tr>
              <tr><td>Filler words: Flag</td><td>Marks them but keeps text intact</td></tr>
              <tr><td>Filler words: Strip</td><td>Removes them from the text</td></tr>
              <tr><td>Remove false starts</td><td>Strips fragments before — or … restarts</td></tr>
            </tbody>
          </table>

          <h3>Confidence scores</h3>
          <p>
            Every speaker attribution carries a score from 0.0 to 1.0.
            Segments below the threshold (default 0.6, configurable in Settings)
            are highlighted in amber and queued for review.
            The confidence summary panel shows the overall quality of the session.
          </p>

          <h3>CLI usage</h3>
          <p>Transcribe3 also runs as a command-line tool, useful for automation and agent workflows:</p>
          <pre className="code-block">{`uv run transcribe3 clean transcript.txt --format srt
uv run transcribe3 sessions list
uv run transcribe3 export <session-id> --format json
uv run transcribe3 benchmark tests/gold/`}</pre>

          <h3>Settings</h3>
          <p>
            Click the gear icon to configure LLM providers, the default model,
            timeout (increase if you see timeout errors with large models), and
            confidence threshold. Settings are saved in <code>sessions/settings.json</code>;
            a provider's bearer token, if it needs one, is read from the environment
            variable named on its row, not from that file.
          </p>

          <h3>Turning off pipeline stages</h3>
          <p>
            Settings has switches for the two optional stages. <strong>Clean transcript
            text</strong> handles filler words, false starts and crosstalk; it is
            rule-based and takes about a second. <strong>Validate speaker attribution
            with the LLM</strong> makes one call per 10-segment window, so on a long
            recording it is usually the whole runtime — switching it off returns a
            transcript in seconds, keeps the diarization speaker labels as they are, and
            leaves segment confidence unscored (shown as "not scored" rather than a
            percentage). Admin shows where the time actually went, per stage and averaged
            across recent runs.
          </p>

          <h3>LLM provider required</h3>
          <p>
            The LLM attribution step requires one of your configured LLM providers
            running. Add providers in Settings — anything speaking the Ollama
            native API or the OpenAI v1 protocol works (Ollama, olmx, LM Studio,
            vLLM, llama.cpp server, a hosted API, ...), pick a "default" provider
            there, and override it per upload from the form. If you see a
            connection error, check that the provider's process is running and
            that its base URL in Settings is correct — for Ollama specifically,
            that means running <code>ollama serve</code>. Available models are
            populated from whichever provider is selected.
          </p>
        </div>
      </div>
    </div>
  )
}
