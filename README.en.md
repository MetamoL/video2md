# video2md

Turn any YouTube video into an AI-readable Markdown document — audio **and** visuals — powered by the Gemini API.

Primary README (Japanese): [README.md](README.md) / Intro article (Japanese): [Zenn](https://zenn.dev/metamol/articles/5cdf6a649ed1bc)

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

## Use as an MCP server

Register the local MCP server to call video2md directly from a conversation with an AI agent. Replace `C:\path\to\video2md\mcp_server.py` below with the absolute path on your system.

### Claude Code

```powershell
claude mcp add video2md -- python C:\path\to\video2md\mcp_server.py
```

After registration, ask something like “Explain this topic based on the video `https://youtu.be/VIDEO_ID`.” No hosting is required; the only potential cost is the Gemini API used by the local process.

Long videos can take several minutes, so set a sufficiently long timeout in your MCP client (Claude Code uses the `MCP_TIMEOUT` environment variable).

### Codex CLI and apps

Codex CLI, the TUI, the IDE extension, and the ChatGPT desktop app share MCP configuration on the same Codex host.
See the [official MCP documentation](https://learn.chatgpt.com/docs/extend/mcp) for the configuration reference.

Avoid passing a real value to `--env`, because the API key can remain in shell history and Codex configuration; use `env_vars` below to forward the `GEMINI_API_KEY` configured in the previous section instead.

On Windows PowerShell, register the server with:

```powershell
codex mcp add video2md -- python C:\path\to\video2md\mcp_server.py
```

On macOS or Linux, use:

```bash
codex mcp add video2md -- python /absolute/path/to/video2md/mcp_server.py
```

Then add or edit the server entry in the Codex configuration file (Windows: `$env:USERPROFILE\.codex\config.toml`; macOS or Linux: `~/.codex/config.toml`).
`env_vars` forwards only the API key from the environment in which Codex was started.
The Windows example uses `/` as the path separator so the path is a valid TOML string without escaped backslashes.

Windows:

```toml
[mcp_servers.video2md]
command = "python"
args = ["C:/path/to/video2md/mcp_server.py"]
env_vars = ["GEMINI_API_KEY"]
tool_timeout_sec = 1800
```

macOS or Linux:

```toml
[mcp_servers.video2md]
command = "python"
args = ["/absolute/path/to/video2md/mcp_server.py"]
env_vars = ["GEMINI_API_KEY"]
tool_timeout_sec = 1800
```

Codex's default `tool_timeout_sec` is 60 seconds, but video2md can take several minutes for a long video and tens of minutes when retries and the automatic key-points fallback overlap.
The examples use 30 minutes.
Increase `1800` if processing in your environment takes longer.

Check the registration with:

```text
codex mcp list
```

In the Codex TUI or app composer, enter `/mcp` to see connected MCP servers.
If a configuration change is not reflected, restart the TUI or app (for the IDE extension, restart the extension).

Once connected, ask in natural language, for example:

```text
Explain this video based on its content and summarize the key points: https://youtu.be/VIDEO_ID
```

The server exposes one tool named `video_to_markdown`.

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

## Development checks

From the repository root, run:

```bash
python -m unittest discover -s test -q
```

## License

[MIT](LICENSE)
