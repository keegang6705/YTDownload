#!/usr/bin/env python3
"""Desktop front-end for YTDownload 5.

The window is a thin layer over :class:`YTDownload.DownloadEngine`; all the
download logic (yt-dlp, pacing, duplicate-title handling) lives in the engine so
the CLI and the GUI always behave identically.
"""

import sys
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QProgressBar, QPushButton, QTextEdit, QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QUrl

from YTDownload import (
    AUDIO_FORMATS, ConfigError, DownloadEngine, DownloadError, collect_targets,
    load_config, looks_like_playlist, save_config,
)

CONFIG_PATH = Path(__file__).with_name("config.json")


class DownloadWorker(QThread):
    """Runs the engine off the GUI thread and forwards its events as signals."""

    event = Signal(object)
    log = Signal(str)
    succeeded = Signal()
    failed = Signal(str)

    def __init__(self, config, targets, parent=None):
        super().__init__(parent)
        self.config = config
        self.targets = targets

    def run(self):
        settings = self.config["settings"]
        download_path = self.config["app_data"]["download_path"]
        engine = DownloadEngine(
            settings,
            download_path,
            on_event=self.event.emit,
            on_log=self.log.emit,
        )
        errors = {}
        for url, is_playlist in self.targets:
            if self.isInterruptionRequested():
                break
            try:
                failures = engine.download(url, playlist=is_playlist)
                errors.update(failures or {})
            except DownloadError as exc:
                errors[url] = str(exc)
                self.log.emit(f"✗ {url}: {exc}")
        if errors:
            self.failed.emit("\n".join(f"{url}: {msg}" for url, msg in errors.items()))
        else:
            self.succeeded.emit()


class YouTubeDownloaderUI(QMainWindow):
    def __init__(self):
        super().__init__()
        try:
            self.config = load_config(CONFIG_PATH)
        except ConfigError as exc:
            self.config = None
            self._config_error = str(exc)
        else:
            self._config_error = ""
        self.worker = None
        self.initUI()

    # -- construction ------------------------------------------------------ #

    def initUI(self):
        self.setWindowTitle("YTDownload 5 - YouTube / Music")
        self.resize(860, 640)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        settings = (self.config or {}).get("settings", {})
        app_data = (self.config or {}).get("app_data", {})
        self.download_path = app_data.get("download_path", str(Path.home() / "Music" / "YTDownload"))

        # URL row
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("URL:"))
        self.url_input = QLineEdit()
        self.url_input.setFont(QFont("Segoe UI", 11))
        self.url_input.setPlaceholderText("https://www.youtube.com/playlist?list=...  or a single video")
        self.url_input.returnPressed.connect(self.start_download)
        url_layout.addWidget(self.url_input, 1)
        layout.addLayout(url_layout)

        # Options row
        options_layout = QHBoxLayout()
        self.playlist_check = QCheckBox("Playlist")
        self.playlist_check.setChecked(bool(settings.get("is_playlist", True)))
        self.audio_only_check = QCheckBox("Audio only")
        self.audio_only_check.setChecked(bool(settings.get("audio_only", True)))
        self.audio_only_check.toggled.connect(self._sync_format_enabled)

        self.format_combo = QComboBox()
        self.format_combo.addItems(list(AUDIO_FORMATS))
        self.format_combo.setCurrentText(settings.get("audio_format", "opus"))

        options_layout.addWidget(self.playlist_check)
        options_layout.addWidget(self.audio_only_check)
        options_layout.addSpacing(8)
        options_layout.addWidget(QLabel("Format:"))
        options_layout.addWidget(self.format_combo, 1)
        layout.addLayout(options_layout)
        self._sync_format_enabled(self.audio_only_check.isChecked())

        # Destination row
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Save to:"))
        self.path_input = QLineEdit(self.download_path)
        path_layout.addWidget(self.path_input, 1)
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self.browse_path)
        path_layout.addWidget(browse_button)
        open_button = QPushButton("Open folder")
        open_button.clicked.connect(self.open_folder)
        path_layout.addWidget(open_button)
        layout.addLayout(path_layout)

        # Action row
        button_layout = QHBoxLayout()
        self.download_button = QPushButton("Download URL")
        self.download_button.setDefault(True)
        self.download_button.clicked.connect(self.start_download)
        self.queue_button = QPushButton("Download config queue")
        self.queue_button.setToolTip("Download everything listed in config.json")
        self.queue_button.clicked.connect(self.start_queue)
        clear_button = QPushButton("Clear log")
        clear_button.clicked.connect(self.clear_input)
        button_layout.addWidget(self.download_button)
        button_layout.addWidget(self.queue_button)
        button_layout.addStretch(1)
        button_layout.addWidget(clear_button)
        layout.addLayout(button_layout)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #777;")
        layout.addWidget(self.status_label)

        # Log
        layout.addWidget(QLabel("Log:"))
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_output, 1)

        if self._config_error:
            self.append_log(f"Config error: {self._config_error}")

    # -- helpers ----------------------------------------------------------- #

    def _sync_format_enabled(self, enabled: bool) -> None:
        self.format_combo.setEnabled(enabled)

    def append_log(self, message: str) -> None:
        self.log_output.append(message)

    def browse_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Select download directory", self.download_path)
        if folder:
            self.path_input.setText(folder)
            self.download_path = folder

    def open_folder(self):
        folder = Path(self.path_input.text().strip() or self.download_path)
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _current_config(self) -> dict:
        if self.config is None:
            self.config = load_config(CONFIG_PATH)
        settings = self.config["settings"]
        settings["is_playlist"] = self.playlist_check.isChecked()
        settings["audio_only"] = self.audio_only_check.isChecked()
        settings["audio_format"] = self.format_combo.currentText()
        self.config["app_data"]["download_path"] = self.path_input.text().strip() or self.download_path
        return self.config

    def _start_worker(self, targets):
        self.download_button.setEnabled(False)
        self.queue_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.worker = DownloadWorker(self._current_config(), targets, self)
        self.worker.event.connect(self.on_event)
        self.worker.log.connect(self.append_log)
        self.worker.succeeded.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(self._reenable)
        self.worker.start()

    def _reenable(self):
        self.download_button.setEnabled(True)
        self.queue_button.setEnabled(True)

    # -- actions ----------------------------------------------------------- #

    def start_download(self):
        if self.worker and self.worker.isRunning():
            return
        url = self.url_input.text().strip()
        if not url:
            self.append_log("Please enter a URL.")
            return
        is_playlist = self.playlist_check.isChecked() or looks_like_playlist(url)
        self.append_log(f"↓ {url}")
        self._start_worker([(url, is_playlist)])

    def start_queue(self):
        if self.worker and self.worker.isRunning():
            return
        config = self._current_config()
        targets = collect_targets(config)
        if not targets:
            self.append_log("Config queue is empty - add playlist_url or single_url to config.json.")
            return
        self.append_log(f"↓ config queue: {len(targets)} URL(s)")
        self._start_worker(targets)

    # -- worker callbacks -------------------------------------------------- #

    def on_event(self, event):
        total = event.total or 1
        percent = (event.percent or 0.0) / 100.0
        if event.index:
            overall = ((event.index - 1) + percent) / total
        else:
            overall = percent
        self.progress_bar.setValue(int(max(0.0, min(1.0, overall)) * 1000))

        label = event.title or ""
        if event.index and event.total:
            label = f"[{event.index}/{event.total}] {label}"
        self.status_label.setText(f"{event.status}: {label}")

    def on_finished(self):
        self.progress_bar.setValue(1000)
        self.status_label.setText("Finished")
        self.append_log("✓ Download finished")
        self.url_input.clear()

    def on_failed(self, message):
        self.status_label.setText("Finished with errors")
        self.append_log(f"Finished with errors:\n{message}")

    def clear_input(self):
        self.url_input.clear()
        self.log_output.clear()
        self.progress_bar.setValue(0)
        self.status_label.setText("Ready")

    def closeEvent(self, event):  # noqa: N802 - Qt naming
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(3000)
        try:
            save_config(self.config, CONFIG_PATH)
        except Exception:
            pass
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("YTDownload")
    window = YouTubeDownloaderUI()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
