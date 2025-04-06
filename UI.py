import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QCheckBox, QProgressBar, QTextEdit, QFileDialog
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QFont

# Import your existing code
from YTDownload import load_config, download_single_video, download_playlist, DownloadError

class DownloadWorker(QThread):
    progress = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, url, is_playlist, audio_only, download_path):
        super().__init__()
        self.url = url
        self.is_playlist = is_playlist
        self.audio_only = audio_only
        self.download_path = download_path

    def run(self):
        try:
            if self.is_playlist:
                errors = download_playlist(self.url, self.audio_only, self.download_path)
                if errors:
                    for url, error in errors.items():
                        self.progress.emit(f"Error for {url}: {error}")
            else:
                download_single_video(self.url, self.audio_only, self.download_path)
            self.finished.emit()
        except DownloadError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"Unexpected error: {str(e)}")

class YouTubeDownloaderUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.download_path = self.config["app_data"]["download_path"]
        self.initUI()

    def initUI(self):
        self.setWindowTitle('YouTube Downloader')
        self.setGeometry(100, 100, 800, 600)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # URL Input
        url_layout = QHBoxLayout()
        url_label = QLabel('Enter URL:')
        url_label.setFont(QFont('Arial', 12))
        self.url_input = QLineEdit()
        self.url_input.setFont(QFont('Arial', 12))
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)

        # Options
        options_layout = QHBoxLayout()
        self.playlist_check = QCheckBox('Is Playlist')
        self.audio_only_check = QCheckBox('Audio Only')
        self.playlist_check.setChecked(self.config["settings"]["is_playlist"])
        self.audio_only_check.setChecked(self.config["settings"]["audio_only"])
        options_layout.addWidget(self.playlist_check)
        options_layout.addWidget(self.audio_only_check)

        # Download Path
        path_layout = QHBoxLayout()
        path_label = QLabel('Download Path:')
        path_label.setFont(QFont('Arial', 12))
        self.path_input = QLineEdit(self.download_path)
        self.path_input.setFont(QFont('Arial', 12))
        browse_button = QPushButton('Browse')
        browse_button.clicked.connect(self.browse_path)
        path_layout.addWidget(path_label)
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(browse_button)

        # Buttons
        button_layout = QHBoxLayout()
        download_button = QPushButton('Download')
        download_button.clicked.connect(self.start_download)
        clear_button = QPushButton('Clear')
        clear_button.clicked.connect(self.clear_input)
        button_layout.addWidget(download_button)
        button_layout.addWidget(clear_button)

        # Progress and Log
        self.progress_bar = QProgressBar()
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)

        # Add to main layout
        layout.addLayout(url_layout)
        layout.addLayout(options_layout)
        layout.addLayout(path_layout)
        layout.addLayout(button_layout)
        layout.addWidget(self.progress_bar)
        layout.addWidget(QLabel('Download Log:'))
        layout.addWidget(self.log_output)

        self.setLayout(layout)

    def browse_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Download Directory")
        if folder:
            self.path_input.setText(folder)
            self.download_path = folder

    def start_download(self):
        url = self.url_input.text().strip()
        if not url:
            self.log_output.append("Please enter a URL")
            return

        is_playlist = self.playlist_check.isChecked()
        audio_only = self.audio_only_check.isChecked()
        download_path = self.path_input.text() or self.download_path

        self.worker = DownloadWorker(url, is_playlist, audio_only, download_path)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.download_finished)
        self.worker.error.connect(self.show_error)
        self.worker.start()

    def update_progress(self, message):
        self.log_output.append(message)

    def download_finished(self):
        self.log_output.append("Download completed!")

    def show_error(self, error):
        self.log_output.append(f"Error: {error}")

    def clear_input(self):
        self.url_input.clear()
        self.log_output.clear()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = YouTubeDownloaderUI()
    ex.show()
    sys.exit(app.exec())