#### v3.5.0 
###  tested 100% pass
###  Optimized
###  Contributors:keegang6705,flame-suwan,Calude

import os
import time
import re
from tqdm import tqdm
from pytubefix import YouTube, Playlist
from pytubefix.cli import on_progress

# Configuration dictionary
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
            "https://youtube.com/playlist?list=PLqMiAjqcD9xzTEcUUBk-fDQwjCoxHPo4K&si=F1VjiqwteDk0ZiES",
            "https://youtube.com/playlist?list=PLqMiAjqcD9xz1gaw0tvdd0WnQ_eKqT96z&si=WRlHZEA5bhuK1kxh",
            "https://youtube.com/playlist?list=PLqMiAjqcD9xwdqiE-cvsKVll0bqWLN0do&si=QcFIQwFBmyWe93US",
            "https://youtube.com/playlist?list=PLqMiAjqcD9xwXRm6TWPQuPd9K23jSCbdu&si=F-ovJRr6dHfFNTsu",
            "https://youtube.com/playlist?list=PLqMiAjqcD9xysMokP0H735xtUnFxMfh_n&si=NFl_78VyzFcV_rFv",
            "https://youtube.com/playlist?list=PLqMiAjqcD9xxOPsGK58E2pG8qgZJasc7q&si=5dq1LDRl0Hxc4yhf"
        ]
    }
}

MAX_FILENAME_LENGTH = 255  # Maximum filename length for most filesystems
MAX_RETRY_ATTEMPTS = 10
TRUNCATE_SUFFIX = "..."

class DownloadError(Exception):
    """Custom exception for download-related errors"""
    pass

def clean_filename(name, max_length=MAX_FILENAME_LENGTH):
    """
    Clean and truncate filename to be compatible with both Windows and Linux.
    
    Args:
        name (str): Original filename
        max_length (int): Maximum allowed filename length
        
    Returns:
        str: Cleaned and truncated filename
    """
    # Remove invalid characters for both Windows and Linux
    cleaned_name = re.sub(r'[\\/:*?"\'<>|]', '', name)
    
    # Replace spaces with underscores for better compatibility
    cleaned_name = cleaned_name.replace(' ', '_')
    
    # Truncate if filename is too long, preserving file extension
    name_parts = os.path.splitext(cleaned_name)
    if len(cleaned_name) > max_length:
        # Reserve space for extension and truncation indicator
        max_base_length = max_length - len(name_parts[1]) - len(TRUNCATE_SUFFIX)
        truncated_name = name_parts[0][:max_base_length] + TRUNCATE_SUFFIX + name_parts[1]
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
    counter = 1
    new_filename = filename
    
    while os.path.exists(os.path.join(base_path, new_filename)):
        new_filename = f"{name_parts[0]}_{counter}{name_parts[1]}"
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
        video_title = clean_filename(original_title)
        download_dir = download_path or os.getcwd()
        
        # Ensure unique filename
        video_title = get_unique_filename(download_dir, video_title)
        
        print(f"\nNow downloading: {video_title}")
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
