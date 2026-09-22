# Gold Standard Test Set

Each test case is a subdirectory with three files:

| File | Description |
|---|---|
| `input.txt` | Raw transcript as it would arrive — may contain OCR artifacts, misattributions, filler words |
| `expected.json` | Manually corrected `TranscriptSession` JSON — the ground truth |
| `metadata.json` | Source description, correction date, notes |

## Adding a new case

1. Create a subdirectory: `tests/gold/<case_name>/`
2. Add `input.txt` — the raw, uncorrected transcript
3. Run the pipeline manually and correct the output
4. Save the corrected output as `expected.json` (full TranscriptSession JSON)
5. Add `metadata.json`:
   ```json
   {
     "description": "Brief description of the source",
     "corrected_date": "YYYY-MM-DD",
     "corrected_by": "human",
     "notes": "Any relevant notes about edge cases in this sample"
   }
   ```

## Running benchmarks

```bash
uv run transcribe3 benchmark tests/gold/ --model llama3
```

Outputs per-case and aggregate:
- Attribution accuracy (% correct speaker labels)
- WER (Word Error Rate vs expected text)
- Mean confidence calibration
