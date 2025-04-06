import os
import re
import json
from pathlib import Path
from pytubefix import YouTube, Playlist
from pydub import AudioSegment


CONFIG_PATH = './config.json'


def load_config(path=CONFIG_PATH):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        return {
            "config_version": 3,
            "settings": {
                "is_playlist": True,
                "audio_only": True,
                "user_login": False,
                "parallel_threads": 3,
                "max_name_length": 50,
                "max_retry_attempt": 10,
                "truncate_suffix": "..."
            },
            "app_data": {
                "download_path": "D:/Files/Music",
                "single_url": [],
                "playlist_url": []
            }
        }


class DownloadError(Exception):
    pass


def clean_filename(name, max_length):
    name = re.sub(r'[\n\r]+', '', name.strip())
    name = re.sub(r'[\\/:*?"<>|]', '', name)
    base, ext = os.path.splitext(name)
    if len(base) > max_length:
        base = base[:max_length] + '...'
    return base + ext


def get_unique_filename(base_path, filename):
    filepath = os.path.join(base_path, filename)
    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(filepath):
        filepath = os.path.join(base_path, f"{base}_{counter}{ext}")
        counter += 1
    return filepath


def convert_to_mp3(input_path, output_path):
    try:
        audio = AudioSegment.from_file(input_path)
        audio.export(output_path, format="mp3")
        os.remove(input_path)
    except Exception as e:
        raise DownloadError(f"Error converting to MP3: {e}")


def download_single_video(link, as_audio, download_path, max_length):
    try:
        yt = YouTube(link)
        title = clean_filename(yt.title, max_length)
        if as_audio:
            stream = yt.streams.filter(only_audio=True).first()
            temp_path = stream.download(output_path=download_path, filename=title + ".webm")
            final_path = get_unique_filename(download_path, title + ".mp3")
            convert_to_mp3(temp_path, final_path)
        else:
            stream = yt.streams.get_highest_resolution()
            final_path = get_unique_filename(download_path, title + ".mp4")
            stream.download(output_path=download_path, filename=os.path.basename(final_path))
    except Exception as e:
        raise DownloadError(f"Download failed for {link}: {e}")


def download_playlist(playlist_url, as_audio, download_path, max_length, max_attempts):
    errors = []
    try:
        pl = Playlist(playlist_url)
        playlist_folder = os.path.join(download_path, clean_filename(pl.title, max_length))
        os.makedirs(playlist_folder, exist_ok=True)
        for video_url in pl.video_urls:
            for attempt in range(max_attempts):
                try:
                    download_single_video(video_url, as_audio, playlist_folder, max_length)
                    break
                except DownloadError as e:
                    if attempt == max_attempts - 1:
                        errors.append((video_url, str(e)))
    except Exception as e:
        errors.append((playlist_url, str(e)))
    return errors


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    config = load_config()
    settings = config['settings']
    app_data = config['app_data']

    is_playlist = settings['is_playlist']
    audio_only = settings['audio_only']
    max_length = settings['max_name_length']
    max_attempts = settings['max_retry_attempt']
    download_path = app_data['download_path']

    errors = []

    if is_playlist:
        for url in app_data['playlist_url']:
            errs = download_playlist(url, audio_only, download_path, max_length, max_attempts)
            errors.extend(errs)
    else:
        for url in app_data['single_url']:
            try:
                download_single_video(url, audio_only, download_path, max_length)
            except DownloadError as e:
                errors.append((url, str(e)))

    if errors:
        print("\nErrors occurred:")
        for err in errors:
            print(f"- {err[0]}: {err[1]}")
    else:
        print("\nAll downloads completed successfully.")


if __name__ == '__main__':
    main()