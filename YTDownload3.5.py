#### v3.5.1 
###  tested 100% pass
###  Optimized
###  Contributors:keegang6705,flame-suwan,Calude

import os
import time
import re
from tqdm import tqdm
from pytubefix import YouTube, Playlist
from pytubefix.cli import on_progress
import unicodedata

# Configuration dictionary (keeping your existing config)
config = {
    "config_version": 0,
    "settings": {
        "is_playlist": True,
        "audio_only": True
    },
    "app_data": {
        "download_path": "/home/keegang/files/YTDownload/music",
        "single_url": [],
        "playlist_url": [
            "https://youtube.com/playlist?list=PLqMiAjqcD9xwpbKqxM-aBpyNBaL9a2XqH&si=WTrJBeUAVk29w4yH",
            # ... other playlist URLs ...
        ]
    }
}

MAX_FILENAME_LENGTH = 180  # Reduced to account for path length and safety margin
MAX_RETRY_ATTEMPTS = 10
TRUNCATE_SUFFIX = "..."

class DownloadError(Exception):
    """Custom exception for download-related errors"""
    pass

def clean_filename(name, max_length=MAX_FILENAME_LENGTH):
    """
    Clean and truncate filename to be compatible with both Windows and Linux,
    with improved handling of UTF-8 characters.
    
    Args:
        name (str): Original filename
        max_length (int): Maximum allowed filename length
        
    Returns:
        str: Cleaned and truncated filename
    """
    # Normalize unicode characters
    name = unicodedata.normalize('NFKC', name)
    
    # Remove invalid characters for both Windows and Linux
    cleaned_name = re.sub(r'[\\/:*?"\'<>|]', '', name)
    
    # Replace spaces and other whitespace with underscores
    cleaned_name = re.sub(r'\s+', '_', cleaned_name)
    
    # Remove any non-printable characters
    cleaned_name = ''.join(char for char in cleaned_name if char.isprintable())
    
    # Get name parts
    name_parts = os.path.splitext(cleaned_name)
    extension = name_parts[1] if len(name_parts) > 1 else '.mp3'
    
    # Calculate available length for base name
    available_length = max_length - len(extension) - len(TRUNCATE_SUFFIX)
    
    if len(cleaned_name) > max_length:
        # Get the first part of the filename (trying to keep meaningful content)
        base_name = name_parts[0][:available_length]
        
        # Remove any partial UTF-8 characters at the end
        while len(base_name.encode('utf-8')) > available_length:
            base_name = base_name[:-1]
        
        # Create final filename
        truncated_name = base_name + TRUNCATE_SUFFIX + extension
        return truncated_name
    
    return cleaned_name

def get_unique_filename(base_path, filename):
    """
    Generate a unique filename if the original already exists.
    
    Args:
        base_path (str): Directory path
        filename (str): Original filename
        
    Returns:
        str: Unique filename
    """
    name_parts = os.path.splitext(filename)
    base_name = name_parts[0]
    extension = name_parts[1] if len(name_parts) > 1 else '.mp3'
    counter = 1
    new_filename = filename
    
    while os.path.exists(os.path.join(base_path, new_filename)):
        new_name = f"{base_name}_{counter}"
        # Make sure the new filename with counter doesn't exceed max length
        if len(new_name) > MAX_FILENAME_LENGTH - len(extension):
            new_name = new_name[:MAX_FILENAME_LENGTH - len(extension) - 3] + "..."
        new_filename = f"{new_name}{extension}"
        counter += 1
    
    return new_filename

def download_single_video(link, as_audio=True, download_path=None):
    """
    Download a single video with improved error handling.
    
    Args:
        link (str): YouTube video URL
        as_audio (bool): Whether to download as audio only
        download_path (str): Download directory path
        
    Raises:
        DownloadError: If download fails after maximum retries
    """
    try:
        youtubeObject = YouTube(link, on_progress_callback=on_progress)
        original_title = youtubeObject.title
        
        # Clean and truncate filename
        video_title = clean_filename(original_title)
        download_dir = download_path or os.getcwd()
        
        # Get unique filename
        video_title = get_unique_filename(download_dir, video_title)
        
        # Final length check including full path
        full_path = os.path.join(download_dir, video_title)
        if len(full_path.encode('utf-8')) >= 255:  # Max path length
            video_title = clean_filename(original_title, max_length=100)  # Use shorter length
            video_title = get_unique_filename(download_dir, video_title)
        
        print(f"\nNow downloading: {original_title}")
        print(f"Saving as: {video_title}")
        print(f"URL: {link}")
        
        if as_audio:
            stream = youtubeObject.streams.get_audio_only()
            stream.download(output_path=download_dir, filename=video_title, mp3=True)
        else:
            stream = youtubeObject.streams.get_highest_resolution()
            stream.download(output_path=download_dir, filename=video_title)
            
        print("Downloaded successfully")
        print("-" * 30)
        
    except Exception as e:
        error_msg = f"Error downloading {link}: {str(e)}"
        print(error_msg)
        raise DownloadError(error_msg)

def download_playlist(playlist_url, as_audio=True, download_path=None):
    """
    Download a playlist with progress tracking and error handling.
    
    Args:
        playlist_url (str): YouTube playlist URL
        as_audio (bool): Whether to download as audio only
        download_path (str): Base download directory path
        
    Returns:
        dict: Dictionary of errors encountered during download
    """
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
    """Main execution function"""
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
