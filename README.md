# YTDownload 5

Download music (or video) from YouTube and YouTube Music — playlists, albums and
single tracks — as tagged audio files.

This started life as a small `pytubefix` script. Version 5 replaces that engine
with **[yt-dlp](https://github.com/yt-dlp/yt-dlp) + ffmpeg**, which is what
actually makes it work reliably today.

## Why the rewrite

| | Old (v4 and earlier) | Now (v5) |
|---|---|---|
| Engine | `pytubefix`, breaks whenever YouTube changes | `yt-dlp`, released constantly, handles signatures/challenges |
| Audio conversion | `moviepy`: decode to PCM → re-encode MP3 | ffmpeg stream copy (`webm`→`opus` is a remux, not a re-encode) |
| Duplicate titles | second track skipped or overwritten | tracked by video id → `Song.opus`, `Song (1).opus` |
| Rate limiting | retried every second → made blocks worse | paced requests, exponential backoff, cookie auth |
| Metadata | none | title/artist/album/date/genre + embedded cover art |
| Re-runs | re-downloaded everything | `.ytdownload-archive.txt` skips finished tracks |
| Structure | 3 copies of the same logic | one engine, CLI + GUI are thin layers |

## Requirements

- **[uv](https://docs.astral.sh/uv/)** (installs the venv and dependencies)
- **ffmpeg** on `PATH` — `winget install Gyan.FFmpeg`
- **A JavaScript runtime** — `deno`, `node`, `bun` or `quickjs`. yt-dlp 2026
  needs one to solve YouTube's player challenges; without it you get
  *"This video is unavailable"* or missing formats. Node.js is fine.

## Setup

```bash
uv sync              # core (CLI)
uv sync --extra gui  # also install PySide6 for the desktop app
```

## Usage

```bash
uv run YTDownload.py                          # use config.json as-is
uv run YTDownload.py <url> [<url> ...]        # ad-hoc URLs
uv run YTDownload.py -f mp3 --path D:/Music <url>
uv run YTDownload.py --cookies-from-browser chrome <url>
uv run UI.py                                  # desktop GUI
```

`YTDownload+.py` still works — it is now a thin alias for `YTDownload.py`.

## config.json

`config.json` sits next to the scripts and is created with defaults on first run
(and migrated automatically from old versions).

```jsonc
{
  "config_version": 5,
  "settings": {
    "is_playlist": true,          // default mode for bare CLI URLs
    "audio_only": true,           // false = download the video
    "audio_format": "opus",       // opus | mp3 | m4a | aac | flac | wav | vorbis | alac
    "audio_quality": "192",       // kbps, only used when a re-encode is unavoidable
    "embed_metadata": true,       // tags: title/artist/album/date/genre
    "embed_thumbnail": true,      // cover art inside the file
    "keep_thumbnail": false,      // true = also keep a loose .jpg/.webp next to the track
    "max_name_length": 120,

    "max_retry_attempt": 3,       // per URL
    "retry_backoff": 30,          // seconds, grows exponentially
    "sleep_between_downloads": 2, // pause per track
    "sleep_jitter": 1,            // random extra pause
    "sleep_between_requests": 1,  // pause between playlist/API requests
    "ratelimit": "5M",            // bandwidth cap, e.g. "5M", "800K", null
    "parallel_threads": 4,        // parallel DASH fragments
    "save_archive": true,         // remember finished videos

    "cookies_from_browser": null, // "chrome" / "firefox" / "edge" / "brave" ...
    "cookie_file": null,          // or a Netscape cookies.txt
    "proxy": null,
    "js_runtimes": [],            // [] = auto-detect deno/node/bun/quickjs
    "remote_components": ["ejs:github"]
  },
  "app_data": {
    "download_path": "R:/Download/music",
    "single_url": [],
    "playlist_url": []
  }
}
```

Both URL lists are always processed: `playlist_url` entries as playlists,
`single_url` entries as individual tracks.

## Output layout

```
music/
├── english music/
│   ├── Circles.opus          # cover art is embedded in the tags
│   └── Circles.webp          # only if keep_thumbnail: true
├── japanese music/
│   └── 群青.opus
├── .ytdownload-archive.txt   # ids already downloaded
└── .ytdownload-index.json    # video id -> filename
```

## Troubleshooting

**"Sign in to confirm you're not a bot" / HTTP 429**
YouTube is throttling your IP. Don't hammer retry. Either wait, or hand yt-dlp
your browser session:

```bash
uv run YTDownload.py --cookies-from-browser chrome <url>
```

or set `"cookies_from_browser": "chrome"` in `config.json`.

**"This video is unavailable" / "Requested format is not available"**
Usually a missing JavaScript runtime. Install Node.js or deno and confirm with
`uv run YTDownload.py --version` (it prints the detected runtime).

**"ffmpeg was not found on PATH"**
Install ffmpeg and reopen the terminal.

**A track was skipped**
It is in `.ytdownload-archive.txt` (already downloaded) or got its own
`(1)` suffix because a different video has the same title. Delete the archive
file to force a full re-download.
