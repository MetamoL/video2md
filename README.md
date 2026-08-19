# video2md

Turn any YouTube video into an AI-readable Markdown document — audio **and** visuals — powered by the Gemini API.

日本語版: [README.ja.md](README.ja.md)

## What it does

video2md sends a YouTube video directly to Gemini and saves a structured Markdown document with:

- **Summary** — a concise overview of the entire video.
- **Visuals** — timestamped descriptions of slides, charts, demos, code, captions, scenery, and other on-screen information.
- **Transcript** — a timestamped transcript in the original spoken language.

Unlike Whisper-based transcription tools, video2md also reads the visual content of the video.

## Example output

See [examples/](examples/) — including [me-at-the-zoo.en.md](examples/me-at-the-zoo.en.md) (the first video ever uploaded to YouTube), [python-in-100-seconds.ja.md](examples/python-in-100-seconds.ja.md) (a tech video with on-screen code, read verbatim), and [neural-network-19min.ja.md](examples/neural-network-19min.ja.md) (a 19-minute video saved via the automatic key-points fallback).

## Requirements

- Python 3.12 or later
- A Gemini API key
- No third-party Python packages

The tool can run with the Gemini API free tier, subject to its current availability and quota limits.

## Setup

Create an API key in [Google AI Studio](https://aistudio.google.com/apikey), then set it as `GEMINI_API_KEY`.

Windows PowerShell:

```powershell
setx GEMINI_API_KEY "your-api-key"
```

Open a new terminal after running `setx`. On Windows, video2md also checks the current user's stored environment variables when the key has not yet reached the running process.

macOS or Linux:

```bash
export GEMINI_API_KEY="your-api-key"
```

Add the `export` command to your shell profile if you want it to persist across terminal sessions.

## Usage

```text
python video2md.py <URL> [-o OUTDIR] [--model MODEL] [--lang {ja,en}] [--digest] [--extra "INSTRUCTION"]
```

Example:

```bash
python video2md.py "https://youtu.be/jNQXAC9IVRw" --lang en
```

| Option | Description | Default |
| --- | --- | --- |
| `-o`, `--outdir` | Output directory | `out` next to `video2md.py` |
| `--model` | Gemini model name | `gemini-3.6-flash` |
| `--lang` | Output language: `ja` or `en` | `ja` |
| `--digest` | Summarize speech as timestamped key points instead of a verbatim transcript | Off |
| `--extra` | Additional instruction appended to the selected prompt | None |

Files are named after the YouTube title. Existing files are preserved by adding suffixes such as `-2` and `-3`.

## Notes

- Long videos can take several minutes to process.
- For HTTP 429, 500, 502, 503, or 504 responses, video2md waits 20 seconds and retries once. Connection failures are retried once as well.
- With a retry and automatic digest fallback, a single run can take tens of minutes in the worst case.
- CLI progress, warnings, and error messages are in Japanese. `--lang` controls the generated document, not CLI messages.

## Troubleshooting

### RECITATION or an empty transcript

Gemini can reject verbatim transcription of a long video with `finishReason: RECITATION`. video2md automatically retries once using the key-points prompt. You can select that mode from the start with `--digest`:

```bash
python video2md.py "https://youtu.be/VIDEO_ID" --digest
```

### HTTP 404 for the model

Gemini model names change between generations. If the current model returns HTTP 404, use the replacement model named in the API error message:

```bash
python video2md.py "https://youtu.be/VIDEO_ID" --model NEW_MODEL_NAME
```

### Output streams and exit codes

On exit code 0, stdout contains exactly one machine-readable line: the absolute path of the saved file. All progress, retry notices, warnings, and errors go to stderr. If saving fails with exit code 1, stdout contains the recovered Markdown document instead of a path. Therefore, stdout is machine-readable as a path only when the exit code is 0.

| Code | Meaning |
| --- | --- |
| 0 | Success, including success with warnings; stdout is the absolute output path |
| 1 | Saving failed; stdout is the full Markdown document |
| 2 | Invalid arguments or YouTube URL |
| 3 | API key missing or malformed |
| 4 | Gemini API or network failure |
| 5 | Model refusal, including RECITATION when no body can be recovered |
| 130 | Interrupted by the user |

## License

[MIT](LICENSE)
