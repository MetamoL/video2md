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

See [examples/](examples/) — including [me-at-the-zoo.en.md](examples/me-at-the-zoo.en.md) (the first video ever uploaded to YouTube) and [python-in-100-seconds.ja.md](examples/python-in-100-seconds.ja.md) (a tech video with on-screen code, read verbatim).

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
python video2md.py <URL> [-o OUTDIR] [--model MODEL] [--lang {ja,en}] [--extra "INSTRUCTION"]
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
| `--extra` | Additional instruction appended to the selected prompt | None |

Files are named after the YouTube title. Existing files are preserved by adding suffixes such as `-2` and `-3`.

## Notes

- Long videos can take several minutes to process.
- For HTTP 429, 500, or 503 responses, video2md waits 20 seconds and retries once.
- If a model name returns HTTP 404 because it is no longer available, use the replacement model named in the API error message with `--model`.

## License

[MIT](LICENSE)
