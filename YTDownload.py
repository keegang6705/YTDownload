#!/usr/bin/env python3
"""YTDownload 5.0 - a modern YouTube / YouTube Music downloader.

The original engine (pytubefix + moviepy) has been replaced by **yt-dlp +
ffmpeg**:

* yt-dlp owns extraction, signature handling, playlist pagination and the
  download itself. It is actively maintained and is not broken by every
  YouTube front-end change (unlike pytubefix).
* ffmpeg extracts / remuxes the audio stream directly, so Opus downloads are a
  container remux rather than a full lossy re-encode (moviepy used to decode
  everything to PCM and re-encode it to MP3 - slow *and* lossy).
* Metadata and cover art are embedded into the file's own tags, so players show
  artist / title / artwork without any sidecar files.

Compared with the old scripts this version also fixes:

* **Duplicate titles.** Tracks are identified by YouTube video id, not by
  title. Two different songs called "Intro" no longer overwrite or skip each
  other - they become ``Intro.opus`` and ``Intro (1).opus``.
* **Rate limiting / bot checks.** Requests are paced, retries use exponential
  backoff with jitter instead of hammering YouTube every second, and cookie
  auth is supported for the "Sign in to confirm you're not a bot" case.

Run it with ``uv run YTDownload.py`` (or the GUI: ``uv run UI.py``).
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import random
import re
import shutil
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError as YtDlpDownloadError

__version__ = "5.0.0"

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

CONFIG_PATH = Path(__file__).with_name("config.json")
CONFIG_VERSION = 5

AUDIO_FORMATS = ("opus", "mp3", "m4a", "aac", "flac", "wav", "vorbis", "alac")
LOSSY_FORMATS = {"opus", "mp3", "m4a", "aac", "vorbis"}

DEFAULT_CONFIG = {
    "config_version": CONFIG_VERSION,
    "settings": {
        # what to download
        "is_playlist": True,
        "audio_only": True,
        # output
        "audio_format": "opus",
        "audio_quality": "192",
        "embed_metadata": True,
        "embed_thumbnail": True,
        # True keeps a loose .webp/.jpg next to each track. The cover art is
        # embedded in the audio file either way, so False just avoids clutter.
        "keep_thumbnail": False,
        "max_name_length": 120,
        # reliability / pacing
        "max_retry_attempt": 3,
        "retry_backoff": 30,
        "sleep_between_downloads": 2.0,
        "sleep_jitter": 1.0,
        "sleep_between_requests": 1.0,
        "ratelimit": "5M",
        "parallel_threads": 4,
        "save_archive": True,
        # yt-dlp 2026 needs the EJS challenge-solver script for YouTube
        "remote_components": ["ejs:github"],
        # auth (fixes "Sign in to confirm you're not a bot")
        "cookies_from_browser": None,
        "cookie_file": None,
        "proxy": None,
        # JavaScript runtime used to solve YouTube's player challenges.
        # Empty list = auto-detect (deno, node, bun, quickjs).
        "js_runtimes": [],
    },
    "app_data": {
        "download_path": "R:/Download/music",
        "single_url": [],
        "playlist_url": [],
    },
}

# config_version 3 shipped these keys; keep users' values on upgrade.
_LEGACY_KEYS = ("is_playlist", "audio_only", "user_login", "parallel_threads",
                "max_name_length", "max_retry_attempt")


class ConfigError(Exception):
    """Raised when config.json cannot be read or is not valid JSON."""


class DownloadError(Exception):
    """Raised when a URL could not be downloaded."""


def _deep_merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def migrate_config(raw: dict) -> dict:
    """Bring an old config up to the current schema without losing values."""
    config = _deep_merge(DEFAULT_CONFIG, raw)
    settings = config.setdefault("settings", {})

    # v3 -> v5: "user_login" only ever meant "use my account"; cookies replace it.
    if raw.get("settings", {}).get("user_login") and not settings.get("cookies_from_browser"):
        settings["cookies_from_browser"] = "chrome"

    # v3 stored parallel_threads; keep it, it still maps to fragment downloads.
    for key in _LEGACY_KEYS:
        if key in raw.get("settings", {}) and key in settings:
            settings[key] = raw["settings"][key]

    config["config_version"] = CONFIG_VERSION
    config["settings"]["audio_format"] = normalise_format(settings.get("audio_format") or "opus")
    return config


def load_config(path: os.PathLike | str = CONFIG_PATH) -> dict:
    path = Path(path)
    if not path.exists():
        config = copy.deepcopy(DEFAULT_CONFIG)
        save_config(config, path)
        return config
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a JSON object")
    return migrate_config(raw)


def save_config(config: dict, path: os.PathLike | str = CONFIG_PATH) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=4, ensure_ascii=False), encoding="utf-8")
    return path


def normalise_format(value: str) -> str:
    value = (value or "opus").strip().lower()
    aliases = {"webm": "opus", "ogg": "opus", "oga": "opus", "mpeg": "mp3"}
    value = aliases.get(value, value)
    if value not in AUDIO_FORMATS:
        raise ConfigError(
            f"unsupported audio format {value!r}; choose one of {', '.join(AUDIO_FORMATS)}"
        )
    return value


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


def human_bytes(num: float | None) -> str:
    if not num:
        return ""
    for unit in ("B", "KiB", "MiB", "GiB"):
        if num < 1024 or unit == "GiB":
            return f"{num:.1f}{unit}" if unit != "B" else f"{int(num)}B"
        num /= 1024
    return ""


def human_speed(num: float | None) -> str:
    return f"{human_bytes(num)}/s" if num else ""


def human_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return ""
    seconds = int(seconds)
    if seconds >= 3600:
        return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"
    if seconds >= 60:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds}s"


def clean_filename(name: str, max_length: int = 120) -> str:
    """Windows-safe, length-limited filename (kept for API compatibility)."""
    name = unicodedata.normalize("NFKC", name or "")
    stem, ext = os.path.splitext(name)
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", stem)
    stem = "".join(ch for ch in stem if ch.isprintable()).strip(" .") or "download"
    limit = max(1, max_length - len(ext))
    if len(stem) > limit:
        stem = stem[:limit].rstrip(" .")
    return stem + ext


def find_ffmpeg() -> str | None:
    """Locate a usable ffmpeg binary (PATH first, then imageio-ffmpeg)."""
    candidate = shutil.which("ffmpeg")
    if candidate:
        return candidate
    try:  # optional fallback, only if it happens to be installed
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


JS_RUNTIME_ORDER = ("deno", "node", "bun", "quickjs")


def detect_js_runtimes(preferred: Iterable[str] | None = None) -> dict[str, dict]:
    """Find a JavaScript runtime for yt-dlp's YouTube challenge solver.

    yt-dlp 2026 only enables ``deno`` by default; if it is missing, extraction
    degrades to "This video is unavailable" or missing formats. Node/Bun are
    perfectly good substitutes, so detect whatever is actually installed.
    """
    wanted = [name.strip().lower() for name in (preferred or []) if str(name).strip()]
    candidates = wanted or list(JS_RUNTIME_ORDER)
    found: dict[str, dict] = {}
    for name in candidates:
        if name not in JS_RUNTIME_ORDER:
            continue
        path = shutil.which(name)
        if path:
            found[name] = {"path": path}
    return found


def looks_like_playlist(url: str) -> bool:
    url = url or ""
    return "list=" in url and "/watch?" not in url


def _backoff(attempt: int, base: float = 30.0, cap: float = 900.0) -> float:
    """Exponential backoff with jitter - never retry a block within seconds."""
    delay = min(base * (2 ** max(0, attempt - 1)), cap)
    return delay + random.uniform(0, max(1.0, delay * 0.25))


def parse_ratelimit(value) -> float | None:
    """Turn "5M" / "500K" / 1000000 into bytes-per-second.

    yt-dlp's Python API wants a number here (the CLI parses the string), so
    passing the raw config string makes the downloader compare str to float.
    """
    if value in (None, "", 0, "0"):
        return None
    if isinstance(value, (int, float)):
        return float(value) or None
    match = re.match(r"^\s*([\d.]+)\s*([kmg]?)(?:i?b)?(?:/s)?\s*$", str(value), re.IGNORECASE)
    if not match:
        return None
    amount = float(match.group(1))
    multiplier = {"": 1, "k": 1000, "m": 1000 ** 2, "g": 1000 ** 3}[match.group(2).lower()]
    speed = amount * multiplier
    return speed or None


RATE_LIMIT_MARKERS = (
    "sign in to confirm",
    "confirm you're not a bot",
    "confirm you’re not a bot",
    "not a bot",
    "http error 429",
    "too many requests",
    "this content isn't available, try again later",
    "unusual traffic",
)


def is_rate_limited(message: str) -> bool:
    lowered = (message or "").lower()
    return any(marker in lowered for marker in RATE_LIMIT_MARKERS)


# --------------------------------------------------------------------------- #
# Filename registry - makes duplicate titles impossible
# --------------------------------------------------------------------------- #

class FilenameRegistry:
    """Remembers which video id owns which filename stem.

    YouTube titles are not unique. Keying names off the title alone (what the
    old engine did) means the second "Intro" is either skipped or overwrites the
    first. This registry lets us answer "has this exact video already been saved,
    and under what name?" while still giving a *different* video with the same
    title its own ``(1)``, ``(2)`` suffix.
    """

    def __init__(self, path: os.PathLike | str | None):
        self.path = Path(path) if path else None
        self.data: dict[str, str] = {}
        self._dir_cache: dict[str, dict[str, str]] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(loaded, dict):
            self.data = {str(k): str(v) for k, v in loaded.items() if isinstance(v, str)}

    def save(self) -> None:
        if not self.path or not self._dirty:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
            self._dirty = False
        except OSError:
            pass

    def get(self, video_id: str | None) -> str | None:
        return self.data.get(str(video_id)) if video_id else None

    def record(self, video_id: str | None, stem_path: str) -> None:
        if not video_id:
            return
        stem, _ = os.path.splitext(os.path.abspath(stem_path))
        if self.data.get(str(video_id)) != stem:
            self.data[str(video_id)] = stem
            self._dirty = True
        self.invalidate(os.path.dirname(stem))

    def invalidate(self, directory: str | None = None) -> None:
        if directory is None:
            self._dir_cache.clear()
            return
        self._dir_cache.pop(os.path.normcase(os.path.abspath(directory)), None)

    def files_in(self, directory: str) -> dict[str, str]:
        key = os.path.normcase(os.path.abspath(directory))
        cached = self._dir_cache.get(key)
        if cached is None:
            try:
                names = os.listdir(directory)
            except OSError:
                names = []
            cached = {}
            for name in names:
                stem, ext = os.path.splitext(name)
                if ext.lower() in (".part", ".ytdl", ".temp", ".tmp"):
                    continue
                cached.setdefault(stem.lower(), name)
            self._dir_cache[key] = cached
        return cached


class UniqueYoutubeDL(YoutubeDL):
    """YoutubeDL that never lets two different videos share a filename."""

    def __init__(self, params=None, *, registry: FilenameRegistry | None = None):
        super().__init__(params)
        self.registry = registry

    def prepare_filename(self, info_dict, dir_type="", **kwargs):  # noqa: D102
        path = super().prepare_filename(info_dict, dir_type, **kwargs)
        if not path or dir_type or self.registry is None:
            return path
        if info_dict.get("_type") not in (None, "video"):
            return path

        directory = os.path.dirname(path) or os.getcwd()
        stem, ext = os.path.splitext(os.path.basename(path))
        video_id = info_dict.get("id")

        # Same video already on disk under a known name -> hand back that name so
        # yt-dlp recognises it as present instead of downloading it again.
        recorded = self.registry.get(video_id)
        if recorded:
            rec_dir = os.path.dirname(recorded)
            existing = self.registry.files_in(rec_dir).get(os.path.basename(recorded).lower())
            if existing:
                return os.path.join(rec_dir, existing)

        # Different video, same title -> pick the next free "(n)" suffix.
        taken = self.registry.files_in(directory)
        if stem.lower() not in taken:
            return path
        counter = 1
        while f"{stem.lower()} ({counter})" in taken:
            counter += 1
        return os.path.join(directory, f"{stem} ({counter}){ext}")


# --------------------------------------------------------------------------- #
# Progress events
# --------------------------------------------------------------------------- #

@dataclass
class ProgressEvent:
    status: str = "downloading"          # downloading | converting | done | error
    url: str = ""
    title: str = ""
    video_id: str = ""
    index: int | None = None             # 1-based position inside a playlist
    total: int | None = None             # playlist length
    percent: float | None = None         # 0-100 for the current file
    speed: float | None = None
    eta: float | None = None
    postprocessor: str = ""
    message: str = ""


class _YdlLogger:
    """Route yt-dlp's log through our callback, minus the noise."""

    _INTERESTING = ("already been downloaded", "already been recorded",
                    "skipping", "destination", "does not exist")

    def __init__(self, sink: Callable[[str], None]):
        self._sink = sink

    def debug(self, msg: str) -> None:
        msg = strip_ansi(msg)
        if not msg or msg.startswith("[debug] "):
            return
        lowered = msg.lower()
        if any(token in lowered for token in self._INTERESTING):
            self._sink(msg)

    def info(self, msg: str) -> None:
        self.debug(msg)

    def warning(self, msg: str) -> None:
        self._sink(f"warning: {strip_ansi(msg)}")

    def error(self, msg: str) -> None:
        self._sink(f"error: {strip_ansi(msg)}")


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #

class DownloadEngine:
    """Downloads one URL (a track or a whole playlist) at a time."""

    def __init__(
        self,
        settings: dict | None = None,
        download_path: str | os.PathLike | None = None,
        *,
        on_event: Callable[[ProgressEvent], None] | None = None,
        on_log: Callable[[str], None] | None = None,
    ):
        self.settings = _deep_merge(DEFAULT_CONFIG["settings"], settings or {})
        self.download_path = str(download_path or DEFAULT_CONFIG["app_data"]["download_path"])
        self.on_event = on_event or (lambda event: None)
        self.on_log = on_log or (lambda message: None)

        self.audio_format = normalise_format(self.settings.get("audio_format", "opus"))
        self.ffmpeg_path = find_ffmpeg()
        self.js_runtimes = detect_js_runtimes(self.settings.get("js_runtimes") or None)
        self.registry = FilenameRegistry(
            os.path.join(self.download_path, ".ytdownload-index.json")
            if self.settings.get("save_archive", True) else None
        )
        self.downloaded: set[str] = set()
        self.skipped: set[str] = set()
        self._last_download_at = 0.0
        self._context: tuple[int, int] | None = None

    # -- options ----------------------------------------------------------- #

    def _build_opts(self, subdir: str | None = None) -> dict:
        s = self.settings
        audio_only = bool(s.get("audio_only", True))
        fmt = self.audio_format
        max_name = int(s.get("max_name_length") or 120)

        if subdir:
            outtmpl = os.path.join(self.download_path, subdir, "%(title)s.%(ext)s")
        else:
            outtmpl = os.path.join(self.download_path, "%(title)s.%(ext)s")

        postprocessors: list[dict] = []
        if audio_only:
            # yt-dlp copies the stream when the source codec already matches the
            # target (Opus from YouTube is the common case), so this costs one
            # fast remux instead of a decode + re-encode.
            quality = str(s.get("audio_quality") or "192")
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": fmt,
                "preferredquality": quality if fmt in LOSSY_FORMATS else "0",
            })
        if s.get("embed_metadata", True):
            postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": True})
        if audio_only and s.get("embed_thumbnail", True):
            # EmbedThumbnail converts webp->png itself when needed.
            # already_have_thumbnail=True keeps the image file next to the track;
            # False deletes it after it has been embedded into the tags.
            postprocessors.append({
                "key": "EmbedThumbnail",
                "already_have_thumbnail": bool(s.get("keep_thumbnail", True)),
            })

        retries = max(1, int(s.get("max_retry_attempt", 3)))
        base = float(s.get("retry_backoff", 30) or 30)

        def sleep_http(attempt: int) -> float:
            return _backoff(attempt, base=min(base, 30), cap=300)

        def sleep_extractor(attempt: int) -> float:
            return _backoff(attempt, base=base, cap=900)

        pause = max(0.0, float(s.get("sleep_between_downloads", 2.0) or 0.0))
        jitter = max(0.0, float(s.get("sleep_jitter", 1.0) or 0.0))

        opts: dict = {
            "format": "bestaudio/best" if audio_only else "bestvideo*+bestaudio/best",
            "outtmpl": {"default": outtmpl},
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "consoletitle": False,
            "logger": _YdlLogger(self.on_log),
            "progress_hooks": [self._progress_hook],
            "postprocessor_hooks": [self._postprocessor_hook],
            # retry / pacing -------------------------------------------------
            "retries": 10,
            "fragment_retries": 10,
            "extractor_retries": max(retries, 3),
            "retry_sleep_functions": {
                "http": sleep_http,
                "fragment": sleep_http,
                "extractor": sleep_extractor,
            },
            "sleep_interval": pause,
            "max_sleep_interval": pause + jitter,
            "sleep_interval_requests": max(0.0, float(s.get("sleep_between_requests", 1.0) or 0.0)),
            "concurrent_fragment_downloads": max(1, int(s.get("parallel_threads", 4) or 4)),
            # files ----------------------------------------------------------
            "windowsfilenames": True,
            "trim_file_name": max_name,
            "overwrites": False,
            "continuedl": True,
            "postprocessors": postprocessors,
            "writethumbnail": bool(audio_only and s.get("embed_thumbnail", True)),
            "merge_output_format": "mp4" if not audio_only else None,
            "ignoreerrors": False,
            "nocheckcertificate": False,
            "cachedir": False,
        }

        ratelimit = parse_ratelimit(s.get("ratelimit"))
        if ratelimit:
            opts["ratelimit"] = ratelimit

        remote_components = s.get("remote_components") or []
        if remote_components:
            opts["remote_components"] = set(remote_components)

        cookies_browser = (s.get("cookies_from_browser") or "").strip()
        if cookies_browser:
            opts["cookiesfrombrowser"] = (cookies_browser,)
        cookie_file = (s.get("cookie_file") or "").strip()
        if cookie_file:
            opts["cookiefile"] = cookie_file
        proxy = (s.get("proxy") or "").strip()
        if proxy:
            opts["proxy"] = proxy

        if self.ffmpeg_path:
            opts["ffmpeg_location"] = os.path.dirname(self.ffmpeg_path) or self.ffmpeg_path

        if self.js_runtimes:
            opts["js_runtimes"] = self.js_runtimes

        if s.get("save_archive", True):
            opts["download_archive"] = os.path.join(self.download_path, ".ytdownload-archive.txt")

        # Clean falsy values that yt-dlp would otherwise misread.
        return {key: value for key, value in opts.items() if value is not None}

    # -- hooks -------------------------------------------------------------- #

    def _progress_hook(self, data: dict) -> None:
        info = data.get("info_dict") or {}
        status = data.get("status")
        title = info.get("title") or ""
        video_id = str(info.get("id") or "")
        index = info.get("playlist_index")
        total = info.get("n_entries") or info.get("playlist_count")

        if status == "downloading":
            downloaded = data.get("downloaded_bytes") or 0
            total_bytes = data.get("total_bytes") or data.get("total_bytes_estimate")
            percent = (downloaded / total_bytes * 100) if total_bytes else None
            self._emit(ProgressEvent(
                status="downloading", url=info.get("webpage_url", ""),
                title=title, video_id=video_id, index=index, total=total,
                percent=percent, speed=data.get("speed"), eta=data.get("eta"),
            ))
        elif status == "finished":
            # The stem never changes during post-processing (Song.webm -> Song.opus),
            # so recording it here is enough to recognise this video later.
            filename = data.get("filename")
            if filename:
                stem = os.path.splitext(filename)[0]
                self.registry.record(video_id, stem)
                self.registry.save()
            if video_id:
                self.downloaded.add(video_id)
            self._emit(ProgressEvent(
                status="converting", url=info.get("webpage_url", ""), title=title,
                video_id=video_id, index=index, total=total, percent=100.0,
            ))
        elif status == "error":
            if video_id:
                self.skipped.add(video_id)
            self._emit(ProgressEvent(
                status="error", title=title, video_id=video_id,
                index=index, total=total, message="download failed",
            ))

    def _emit(self, event: ProgressEvent) -> None:
        """Attach playlist position when downloading item-by-item."""
        if self._context and event.index is None:
            event.index, event.total = self._context
        self.on_event(event)

    def _postprocessor_hook(self, data: dict) -> None:
        if data.get("status") != "finished":
            return
        info = data.get("info_dict") or {}
        self._emit(ProgressEvent(
            status="done",
            url=info.get("webpage_url", ""),
            title=info.get("title") or "",
            video_id=str(info.get("id") or ""),
            index=info.get("playlist_index"),
            total=info.get("n_entries") or info.get("playlist_count"),
            percent=100.0,
            postprocessor=data.get("postprocessor", ""),
        ))

    # -- public API --------------------------------------------------------- #

    def download(self, url: str, playlist: bool | None = None) -> dict[str, str]:
        """Download a track or a whole playlist.

        Returns ``{item_url: error}`` for individual failures. Playlist entries
        are fetched one at a time on purpose: a deleted or region-locked video
        must not abort the other several hundred tracks.
        """
        url = (url or "").strip()
        if not url:
            raise DownloadError("empty URL")
        if playlist is None:
            playlist = bool(self.settings.get("is_playlist", True))

        if self.settings.get("audio_only", True) and not self.ffmpeg_path:
            raise DownloadError(
                "ffmpeg was not found on PATH - required for audio extraction. "
                "Install it (winget install Gyan.FFmpeg) and try again."
            )

        if playlist:
            return self._download_playlist(url)
        self._download_item(url, None)
        return {}

    def _download_item(self, url: str, subdir: str | None) -> None:
        """Download a single track, retrying with backoff. Raises DownloadError."""
        self._pace()

        attempts = max(1, int(self.settings.get("max_retry_attempt", 3)))
        base = float(self.settings.get("retry_backoff", 30) or 30)
        last_error = "unknown error"

        for attempt in range(1, attempts + 1):
            try:
                with UniqueYoutubeDL(self._build_opts(subdir), registry=self.registry) as ydl:
                    ydl.download([url])
                self.registry.save()
                return
            except YtDlpDownloadError as exc:
                last_error = strip_ansi(str(exc)).strip() or "download failed"
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001 - surface anything as a download error
                last_error = f"{type(exc).__name__}: {exc}"

            if attempt >= attempts:
                break

            if is_rate_limited(last_error):
                delay = _backoff(attempt, base=max(base, 60), cap=1800)
                self.on_log(
                    f"YouTube is throttling or asking for a sign-in - backing off "
                    f"{int(delay)}s before retry {attempt}/{attempts - 1}. "
                    "(Set cookies_from_browser in config.json if this keeps happening.)"
                )
            else:
                delay = _backoff(attempt, base=base, cap=300)
                self.on_log(f"retry {attempt}/{attempts - 1} in {int(delay)}s - {last_error}")
            time.sleep(delay)

        raise DownloadError(f"{last_error} (gave up after {attempts} attempts)")

    def _expand_playlist(self, url: str) -> tuple[str, list[tuple[str, str]]]:
        """Read a playlist's track list without downloading anything."""
        opts = self._build_opts(None)
        opts.update({
            "extract_flat": "in_playlist",
            "skip_download": True,
            "ignoreerrors": True,
            "noplaylist": False,
            "postprocessors": [],
            "writethumbnail": False,
            "progress_hooks": [],
            "postprocessor_hooks": [],
        })
        with UniqueYoutubeDL(opts, registry=self.registry) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            raise DownloadError("playlist could not be read (private, deleted or blocked)")

        title = info.get("title") or info.get("id") or "Playlist"
        entries: list[tuple[str, str]] = []
        for entry in info.get("entries") or []:
            if not entry:
                continue  # yt-dlp yields None for unavailable entries
            item_url = entry.get("webpage_url") or entry.get("url")
            if not item_url and entry.get("id"):
                item_url = f"https://www.youtube.com/watch?v={entry['id']}"
            if not item_url:
                continue
            if not str(item_url).startswith("http"):
                item_url = f"https://www.youtube.com/watch?v={item_url}"
            entries.append((item_url, entry.get("title") or ""))
        return title, entries

    def _download_playlist(self, url: str) -> dict[str, str]:
        title, entries = self._expand_playlist(url)
        if not entries:
            raise DownloadError(f'playlist "{title}" has no playable entries')

        folder = clean_filename(title, max_length=80)
        total = len(entries)
        failures: dict[str, str] = {}
        rate_limit_streak = 0

        self.on_log(f'playlist "{title}": {total} track(s) -> {folder}')

        for index, (item_url, item_title) in enumerate(entries, 1):
            self._context = (index, total)
            try:
                self._download_item(item_url, folder)
                rate_limit_streak = 0
            except DownloadError as exc:
                failures[item_url] = str(exc)
                self.on_log(f"[{index}/{total}] skipped {item_title or item_url}: {exc}")
                # Let the UI move past a failed track instead of freezing on it.
                self._emit(ProgressEvent(
                    status="error", url=item_url, title=item_title,
                    index=index, total=total, message=str(exc),
                ))
                # A block affects every following track, so stop instead of
                # burning through hundreds of guaranteed failures.
                if is_rate_limited(str(exc)):
                    rate_limit_streak += 1
                    if rate_limit_streak >= 3:
                        raise DownloadError(
                            f"YouTube appears to be blocking this IP ({rate_limit_streak} "
                            f"consecutive failures). Stopped playlist after {index}/{total} "
                            "tracks. Wait a while, or set cookies_from_browser."
                        ) from exc
            finally:
                self._context = None

        self.registry.save()
        if failures:
            self.on_log(f'{len(failures)} of {total} track(s) failed in "{title}"')
        return failures

    def _pace(self) -> None:
        """Space out separate downloads so we do not look like a scraper."""
        pause = max(0.0, float(self.settings.get("sleep_between_downloads", 2.0) or 0.0))
        jitter = max(0.0, float(self.settings.get("sleep_jitter", 1.0) or 0.0))
        if not pause:
            return
        elapsed = time.monotonic() - self._last_download_at
        delay = pause + random.uniform(0, jitter) - elapsed
        if self._last_download_at and delay > 0:
            time.sleep(delay)
        self._last_download_at = time.monotonic()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def collect_targets(config: dict) -> list[tuple[str, bool]]:
    """Return ``(url, is_playlist)`` pairs from the config, in a stable order."""
    app = config.get("app_data", {})
    targets: list[tuple[str, bool]] = []
    for url in app.get("playlist_url") or []:
        if url:
            targets.append((str(url), True))
    for url in app.get("single_url") or []:
        if url:
            targets.append((str(url), False))
    return targets


class RichReporter:
    """Paints yt-dlp progress events into a rich progress bar."""

    def __init__(self, progress, console):
        self.progress = progress
        self.console = console
        self.task = None

    def reset(self) -> None:
        self.task = None

    def log(self, message: str) -> None:
        message = strip_ansi(message).strip()
        if message:
            self.console.print(f"[dim]{message}[/dim]", highlight=False)

    def __call__(self, event: ProgressEvent) -> None:
        title = event.title or event.url or "download"
        if self.task is None:
            self.task = self.progress.add_task(f"[cyan]{title}[/cyan]", total=1, detail="")

        total_units = event.total or 1
        percent = (event.percent or 0.0) / 100.0
        if event.index:
            completed = (event.index - 1) + percent
        else:
            completed = percent

        detail = ""
        if event.status == "downloading":
            detail = " ".join(part for part in (human_speed(event.speed), human_eta(event.eta)) if part)
        elif event.status == "converting":
            detail = "converting"
        elif event.status == "done":
            detail = "done"
            if event.index:
                completed = event.index
        elif event.status == "error":
            detail = "[red]error[/red]"
            if event.index:
                completed = event.index

        label = title
        if event.index and event.total:
            label = f"{event.index}/{event.total} {title}"
        if event.status == "converting":
            label = f"converting - {title}"

        self.progress.update(
            self.task,
            total=total_units,
            completed=max(0.0, min(float(total_units), completed)),
            description=f"[cyan]{label}[/cyan]",
            detail=detail,
        )


def pretty_print_config(config: dict, console) -> None:
    from rich import box
    from rich.table import Table

    table = Table(title="Configuration", box=box.SIMPLE_HEAVY, title_style="bold cyan")
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value", style="green", overflow="fold")
    for section, items in config.items():
        if isinstance(items, dict):
            for key, value in items.items():
                if isinstance(value, list):
                    shown = f"{len(value)} item(s)" if value else "-"
                elif value is None:
                    shown = "-"
                else:
                    shown = str(value)
                table.add_row(f"{section}.{key}", shown)
        else:
            table.add_row(section, str(items))
    console.print(table)


def run_downloads(config: dict, console) -> dict[str, str]:
    from rich.progress import (
        BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeRemainingColumn,
    )

    settings = config["settings"]
    app = config["app_data"]
    targets = collect_targets(config)
    errors: dict[str, str] = {}

    if not targets:
        console.print("[yellow]Nothing to do: playlist_url and single_url are both empty.[/yellow]")
        return errors

    os.makedirs(app["download_path"], exist_ok=True)
    engine = DownloadEngine(settings, app["download_path"])

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[detail]}[/dim]"),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    )
    reporter = RichReporter(progress, console)
    engine.on_event = reporter
    engine.on_log = reporter.log

    with progress:
        for position, (url, is_playlist) in enumerate(targets, 1):
            kind = "playlist" if is_playlist else "track"
            console.print(f"[blue]▶ [{position}/{len(targets)}] {kind}:[/blue] {url}")
            reporter.reset()
            try:
                failures = engine.download(url, playlist=is_playlist)
                errors.update(failures or {})
            except DownloadError as exc:
                errors[url] = str(exc)
                console.print(f"[red]✗ failed:[/red] {exc}")
            except KeyboardInterrupt:
                console.print("[yellow]Interrupted - stopping.[/yellow]")
                errors[url] = "interrupted"
                break

    if engine.downloaded:
        console.print(f"[green]Completed {len(engine.downloaded)} item(s).[/green]")

    if errors:
        from rich import box
        from rich.table import Table

        table = Table(title="Errors", box=box.MINIMAL_DOUBLE_HEAD, title_style="bold red")
        table.add_column("URL", style="red", overflow="fold")
        table.add_column("Error", style="white", overflow="fold")
        for url, message in errors.items():
            table.add_row(url, message)
        console.print(table)
    return errors


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="YTDownload",
        description="Download music/video from YouTube with yt-dlp.",
    )
    parser.add_argument("urls", nargs="*", help="URLs to download (override config)")
    parser.add_argument("-c", "--config", default=str(CONFIG_PATH), help="path to config.json")
    parser.add_argument("-p", "--path", help="download directory")
    parser.add_argument("-f", "--format", choices=AUDIO_FORMATS, help="audio format")
    parser.add_argument("--playlist", action=argparse.BooleanOptionalAction, default=None,
                        help="treat given URLs as playlists")
    parser.add_argument("--video", action="store_true", help="download full video instead of audio")
    parser.add_argument("--cookies-from-browser", metavar="BROWSER",
                        help="use cookies from a browser (chrome, firefox, edge...)")
    parser.add_argument("--save-config", action="store_true",
                        help="persist CLI overrides back into config.json")
    parser.add_argument("--version", action="version", version=f"YTDownload {__version__}")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    args = parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        console.print(Panel(f"[bold red]{exc}[/bold red]", title="Config error", border_style="red"))
        return 2

    settings = config["settings"]
    app_data = config["app_data"]

    if args.path:
        app_data["download_path"] = args.path
    if args.format:
        settings["audio_format"] = args.format
    if args.video:
        settings["audio_only"] = False
    if args.cookies_from_browser:
        settings["cookies_from_browser"] = args.cookies_from_browser

    if args.urls:
        playlists, singles = [], []
        for url in args.urls:
            is_playlist = args.playlist if args.playlist is not None else looks_like_playlist(url)
            (playlists if is_playlist else singles).append(url)
        app_data["playlist_url"] = playlists
        app_data["single_url"] = singles

    if args.save_config:
        save_config(config, args.config)

    console.rule("[bold blue]YTDownload")
    import yt_dlp

    runtimes = ", ".join(detect_js_runtimes(settings.get("js_runtimes") or None)) or "NONE (install node/deno)"
    console.print(
        f"[dim]yt-dlp {yt_dlp.version.__version__} | ffmpeg: {find_ffmpeg() or 'MISSING'} | "
        f"js: {runtimes} | output: {app_data['download_path']}[/dim]"
    )
    pretty_print_config(config, console)

    errors = run_downloads(config, console)

    ok = not errors
    console.print(Panel(
        "[bold green]All downloads finished[/bold green]" if ok
        else f"[bold yellow]Finished with {len(errors)} failed URL(s)[/bold yellow]",
        border_style="green" if ok else "yellow",
    ))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
