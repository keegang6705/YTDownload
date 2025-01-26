#### v4.0 beta
###  tested 100% pass
###  Contributors:keegang6705,flame-suwan,Calude

### moviepy==1.0.3
import os
import time
import re
from tqdm import tqdm
from pytubefix import YouTube, Playlist
from pytubefix.cli import on_progress
import unicodedata
from moviepy.editor import AudioFileClip
import shutil
from PIL import Image
from io import BytesIO
import requests

config = {
    "config_version": 1,
    "settings": { 
        "is_playlist": True, 
        "audio_only": True,
        "user_login": False,
        "metadata": True 
    },
    "app_data": {
        "download_path": "C:\Temp\\test",
        "single_url": [],
        "playlist_url": [
            "https://youtube.com/playlist?list=PLqMiAjqcD9xwpbKqxM-aBpyNBaL9a2XqH&si=WTrJBeUAVk29w4yH",
            "https://youtube.com/playlist?list=PLqMiAjqcD9xzTEcUUBk-fDQwjCoxHPo4K&si=F1VjiqwteDk0ZiES",
            "https://youtube.com/playlist?list=PLqMiAjqcD9xz1gaw0tvdd0WnQ_eKqT96z&si=WRlHZEA5bhuK1kxh",
            "https://youtube.com/playlist?list=PLqMiAjqcD9xwdqiE-cvsKVll0bqWLN0do&si=QcFIQwFBmyWe93US",
            "https://youtube.com/playlist?list=PLqMiAjqcD9xwXRm6TWPQuPd9K23jSCbdu&si=F-ovJRr6dHfFNTsu",
            "https://youtube.com/playlist?list=PLqMiAjqcD9xysMokP0H735xtUnFxMfh_n&si=NFl_78VyzFcV_rFv",
            "https://youtube.com/playlist?list=PLqMiAjqcD9xxOPsGK58E2pG8qgZJasc7q&si=5dq1LDRl0Hxc4yhf"
        ]
    }
}

MAX_FILENAME_LENGTH = 85
MAX_RETRY_ATTEMPTS = 10
TRUNCATE_SUFFIX = "..."

class DownloadError(Exception):
    pass

def clean_filename(name, max_length=MAX_FILENAME_LENGTH):
    name = unicodedata.normalize('NFKC', name)
    cleaned_name = re.sub(r'[\\/:*?"\'<>|]', '', name)
    cleaned_name = ''.join(char for char in cleaned_name if char.isprintable())
    name_parts = os.path.splitext(cleaned_name)
    extension = name_parts[1] if len(name_parts) > 1 else '.mp3'
    available_length = max_length - len(extension) - len(TRUNCATE_SUFFIX)
    
    if len(cleaned_name) > max_length:
        base_name = name_parts[0][:available_length]
        while len(base_name.encode('utf-8')) > available_length:
            base_name = base_name[:-1]
        truncated_name = base_name + TRUNCATE_SUFFIX + extension
        return truncated_name
    
    return cleaned_name

def get_unique_filename(base_path, filename):
    name_parts = os.path.splitext(filename)
    base_name = name_parts[0]
    extension = name_parts[1] if len(name_parts) > 1 else '.mp3'
    counter = 1
    new_filename = filename
    
    while os.path.exists(os.path.join(base_path, new_filename)):
        new_name = f"{base_name}_{counter}"
        if len(new_name) > MAX_FILENAME_LENGTH - len(extension):
            new_name = new_name[:MAX_FILENAME_LENGTH - len(extension) - 3] + "..."
        new_filename = f"{new_name}{extension}"
        counter += 1
    
    return new_filename

def convert_to_mp3(input_path, output_path):
    """Convert video/audio file to MP3 format."""
    try:
        audio = AudioFileClip(input_path)
        audio.write_audiofile(output_path, logger=None)
        audio.close()
        # Remove the original file after conversion
        os.remove(input_path)
    except Exception as e:
        raise DownloadError(f"Error converting to MP3: {str(e)}")

class VideoMetadata:
    def __init__(self, yt):
        self.title = yt.title
        self.author = yt.author
        self.thumbnail_url = yt.thumbnail_url
        self.description = yt.description
        self.upload_date = yt.publish_date
        self.duration = yt.length
        
    def save_thumbnail(self, download_path, filename):
        if not self.thumbnail_url:
            return None
            
        thumbnail_dir = os.path.join(download_path, "thumbnails")
        os.makedirs(thumbnail_dir, exist_ok=True)
        
        response = requests.get(self.thumbnail_url)
        img = Image.open(BytesIO(response.content))
        
        thumb_path = os.path.join(thumbnail_dir, f"{filename}.jpg")
        img.save(thumb_path, "JPEG")
        return thumb_path
        
    def __str__(self):
        return f"Title: {self.title}\nAuthor: {self.author}\nDuration: {self.duration}s"

def download_single_video(link, as_audio=True, download_path=None):
    try:
        youtubeObject = YouTube(url=link, client = 'WEB', on_progress_callback=on_progress, use_oauth=config["settings"]["user_login"])
        
        # Get metadata if enabled
        if config["settings"]["metadata"]:
            metadata = VideoMetadata(youtubeObject)
            print(f"\nAuthor: {metadata.author}")
        
        original_title = youtubeObject.title
        video_title = clean_filename(original_title)
        download_dir = download_path or os.getcwd()
        video_title = get_unique_filename(download_dir, video_title)
        
        # Create temporary filename for downloaded file
        temp_filename = os.path.splitext(video_title)[0] + '_temp'
        final_filename = os.path.splitext(video_title)[0] + '.mp3'
        
        full_path = os.path.join(download_dir, video_title)
        if len(full_path.encode('utf-8')) >= 255:
            video_title = clean_filename(original_title, max_length=100)
            video_title = get_unique_filename(download_dir, video_title)
        
        print(f"\nNow downloading: {original_title}")
        print(f"Saving as: {final_filename}")
        print(f"URL: {link}")
        
        if as_audio:
            # Download audio stream
            stream = youtubeObject.streams.get_audio_only()
            temp_path = os.path.join(download_dir, temp_filename)
            final_path = os.path.join(download_dir, final_filename)
            
            # Download to temporary file
            stream.download(output_path=download_dir, filename=temp_filename)
            
            print("Converting to MP3...")
            # Convert to proper MP3
            convert_to_mp3(temp_path, final_path)
            
            # Download thumbnail if enabled
            if config["settings"]["metadata"] and as_audio:
                thumbnail_path = metadata.save_thumbnail(
                    download_dir,
                    os.path.splitext(final_filename)[0]
                )
                if thumbnail_path:
                    print(f"Thumbnail saved: {thumbnail_path}")
        else:
            stream = youtubeObject.streams.get_highest_resolution()
            stream.download(output_path=download_dir, filename=video_title)
            
        print("Downloaded and converted successfully")
        print("-" * 30)
        
    except Exception as e:
        error_msg = f"Error downloading {link}: {str(e)}"
        print(error_msg)
        raise DownloadError(error_msg)

def download_playlist(playlist_url, as_audio=True, download_path=None):
    errors = {}
    
    try:
        playlist = Playlist(playlist_url)
        playlist_name = clean_filename(playlist.title)
        
        download_dir = download_path or os.getcwd()
        playlist_folder = os.path.join(download_dir, playlist_name)
        os.makedirs(playlist_folder, exist_ok=True)
        
        total_videos = len(playlist.video_urls)
        print(f'\nNumber of videos in playlist "{playlist_name}": {total_videos}')
        
        with tqdm(total=total_videos, desc=f"Downloading: {playlist_name}") as pbar:
            for video_url in playlist.video_urls:
                for attempt in range(MAX_RETRY_ATTEMPTS):
                    try:
                        download_single_video(video_url, as_audio, download_path=playlist_folder)
                        break
                    except DownloadError as e:
                        if attempt == MAX_RETRY_ATTEMPTS - 1:
                            errors[video_url] = str(e)
                            print(f"\nError: max retry attempts ({MAX_RETRY_ATTEMPTS}) reached")
                        else:
                            print(f"\nRetrying ({attempt + 1}/{MAX_RETRY_ATTEMPTS})")
                            time.sleep(1)
                pbar.update(1)
                
    except Exception as e:
        print(f"Playlist error: {str(e)}")
        errors[playlist_url] = str(e)
    
    return errors

def main():
    script_directory = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_directory)
    
    try:
        print("-" * 30)
        print("Configuration:")
        for key, value in config.items():
            print(f"{key}: {value}")
        print("-" * 30)
        
        download_path = config["app_data"]["download_path"]
        is_playlist = config["settings"]["is_playlist"]
        audio_only = config["settings"]["audio_only"]
        
        all_errors = {}
        
        if is_playlist:
            playlist_links = config["app_data"]["playlist_url"]
            print(f'Number of playlists: {len(playlist_links)}')
            
            for idx, playlist_url in enumerate(playlist_links, 1):
                print(f"\nDownloading playlist [{idx}/{len(playlist_links)}]")
                errors = download_playlist(playlist_url, audio_only, download_path)
                if errors:
                    all_errors.update(errors)
                    
            if all_errors:
                print("\nEncountered errors:")
                print("-" * 30)
                for url, error in all_errors.items():
                    print(f"URL: {url}")
                    print(f"Error: {error}")
                print("-" * 30)
                
        else:
            for url in config["app_data"]["single_url"]:
                try:
                    download_single_video(url, audio_only, download_path)
                except DownloadError as e:
                    all_errors[url] = str(e)
                    
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        
    print("\n-------------- Download finished --------------")

if __name__ == "__main__":
    main()
