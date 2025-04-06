#### v5.0
###  Enhanced with parallel processing and improved console experience
###  Contributors:keegang6705,flame-suwan,Calude

import os
import time
import re
import json
import unicodedata
from tqdm import tqdm
import concurrent.futures
from pytubefix import YouTube, Playlist
from pytubefix.cli import on_progress
from moviepy.audio.io.AudioFileClip import AudioFileClip
import colorama
from colorama import Fore, Style, Back
import threading

# Initialize colorama
colorama.init(autoreset=True)

# Lock for console output synchronization
console_lock = threading.Lock()

def load_config(path='./config.json'):
    if os.path.exists(path):
        with open(path, 'r') as f:
            config = json.load(f)
            return config
    else:
        print(f"{Fore.YELLOW}config.json not found, using default config{Style.RESET_ALL}")
        return {
            "config_version": 3,
            "settings": { 
                "is_playlist": True, 
                "audio_only": True,
                "user_login": False,
                "parallel_threads": 5,
                "max_name_length": 85,
                "max_retry_attempt": 10,
                "truncate_suffix": "...",
            },
            "app_data": {
                "download_path": "C:/Temp/music",
                "single_url": [],
                "playlist_url": []
            }
        }

config = load_config()

class DownloadError(Exception):
    pass

def print_banner():
    banner = f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════╗
║{Fore.YELLOW}             YOUTUBE DOWNLOADER v5.0                      {Fore.CYAN}║
║{Fore.GREEN}         Parallel Downloads & Enhanced Console            {Fore.CYAN}║
╚══════════════════════════════════════════════════════════╝{Style.RESET_ALL}
    """
    print(banner)

def print_config_info():
    settings = config["settings"]
    threads = settings["parallel_threads"]
    mode = "Playlist" if settings["is_playlist"] else "Single Videos"
    format_type = "Audio Only (MP3)" if settings["audio_only"] else "Video"
    
    print(f"{Fore.CYAN}▶ {Fore.WHITE}Parallel threads: {Fore.GREEN}{threads}")
    print(f"{Fore.CYAN}▶ {Fore.WHITE}Download mode: {Fore.GREEN}{mode}")
    print(f"{Fore.CYAN}▶ {Fore.WHITE}Format: {Fore.GREEN}{format_type}")
    print(f"{Fore.CYAN}▶ {Fore.WHITE}Download path: {Fore.GREEN}{config['app_data']['download_path']}")
    print(f"{Fore.CYAN}{'─' * 50}{Style.RESET_ALL}")

def clean_filename(name, max_length=config["settings"]["max_name_length"]):
    name = unicodedata.normalize('NFKC', name)
    
    # Preserve the extension first
    name_parts = os.path.splitext(name)
    base_name = name_parts[0]
    extension = name_parts[1] if len(name_parts) > 1 else '.mp3'
    
    # Clean the base name
    cleaned_base = re.sub(r'[\\/:*?"\'<>|]', '', base_name)
    cleaned_base = ''.join(char for char in cleaned_base if char.isprintable())
    
    # Calculate available length for the base name
    available_length = max_length - len(extension)
    
    if len(cleaned_base) > available_length:
        # Truncate while preserving Unicode characters
        while len(cleaned_base.encode('utf-8')) > available_length:
            cleaned_base = cleaned_base[:-1]
        final_name = f"{cleaned_base}{extension}"
    else:
        final_name = f"{cleaned_base}{extension}"
    
    return final_name

def get_unique_filename(base_path, filename):
    name_parts = os.path.splitext(filename)
    base_name = name_parts[0]
    extension = name_parts[1] if len(name_parts) > 1 else '.mp3'
    counter = 1
    new_filename = filename
    
    # Check for existing files and create unique name
    while os.path.exists(os.path.join(base_path, new_filename)):
        new_name = f"{base_name} ({counter})"
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

def safe_print(message, end='\n'):
    """Thread-safe console printing"""
    with console_lock:
        print(message, end=end)

def download_single_video(link, as_audio=True, download_path=None, progress_callback=None):
    video_title = "Unknown"
    original_title = "Unknown"
    
    try:
        youtubeObject = YouTube(
            url=link, 
            client='WEB', 
            on_progress_callback=on_progress, 
            use_oauth=config["settings"]["user_login"]
        )
        
        original_title = youtubeObject.title
        video_title = clean_filename(original_title)
        download_dir = download_path or os.getcwd()
        video_title = get_unique_filename(download_dir, video_title)
        
        # Check if file already exists before downloading
        final_filename = os.path.splitext(video_title)[0] + '.mp3'
        final_path = os.path.join(download_dir, final_filename)
        
        if os.path.exists(final_path):
            if progress_callback:
                progress_callback(1, f"{Fore.YELLOW}⏭️ Skipped (exists): {original_title[:40]}...")
            return f"{Fore.YELLOW}Skipped: {original_title} (Already exists)"
        
        # Create temporary filename for downloaded file
        temp_filename = os.path.splitext(video_title)[0] + '_temp'
        
        full_path = os.path.join(download_dir, video_title)
        if len(full_path.encode('utf-8')) >= 255:
            video_title = clean_filename(original_title, max_length=100)
            video_title = get_unique_filename(download_dir, video_title)
        
        if progress_callback:
            progress_callback(0, f"{Fore.BLUE}⬇️ Downloading: {original_title[:40]}...")
        
        if as_audio:
            # Download audio stream
            stream = youtubeObject.streams.get_audio_only()
            temp_path = os.path.join(download_dir, temp_filename)
            final_path = os.path.join(download_dir, final_filename)
            
            # Download to temporary file
            stream.download(output_path=download_dir, filename=temp_filename)
            
            if progress_callback:
                progress_callback(0.5, f"{Fore.MAGENTA}🔄 Converting: {original_title[:40]}...")
            # Convert to proper MP3
            convert_to_mp3(temp_path, final_path)
        else:
            stream = youtubeObject.streams.get_highest_resolution()
            stream.download(output_path=download_dir, filename=video_title)
        
        if progress_callback:
            progress_callback(1, f"{Fore.GREEN}✅ Downloaded: {original_title[:40]}")
        
        return f"{Fore.GREEN}✓ Downloaded: {original_title}"
        
    except Exception as e:
        error_msg = f"Error downloading {link}: {str(e)}"
        if progress_callback:
            progress_callback(-1, f"{Fore.RED}❌ Failed: {original_title[:40]}...")
        raise DownloadError(error_msg)

def download_video_worker(args):
    """Worker function for ThreadPoolExecutor to handle video downloads"""
    url, audio_only, path, queue_status, index, total = args
    result = {"url": url, "success": False, "message": "", "index": index}
    
    def update_progress(progress, status_message):
        if queue_status:
            queue_status.update(index, progress, status_message)
    
    for attempt in range(config["settings"]["max_retry_attempt"]):
        try:
            message = download_single_video(url, audio_only, path, update_progress)
            result["success"] = True
            result["message"] = message
            break
        except DownloadError as e:
            if attempt == config["settings"]["max_retry_attempt"] - 1:
                result["message"] = f"{Fore.RED}Failed after {config["settings"]["max_retry_attempt"]} attempts: {str(e)}"
            else:
                update_progress(0, f"{Fore.YELLOW}⚠️ Retry {attempt+1}/{config["settings"]["max_retry_attempt"]}: {str(e)[:40]}...")
                time.sleep(1)  # Wait before retry
    
    return result

class DownloadQueue:
    """Manages the download queue display in the console"""
    def __init__(self, total_items):
        self.total_items = total_items
        self.completed = 0
        self.failed = 0
        self.in_progress = 0
        self.pending = total_items
        self.active_items = {}  # {index: status_message}
        self.pbar = tqdm(
            total=total_items, 
            desc=f"{Fore.CYAN}📥 Overall Progress", 
            bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]',
            leave=True
        )
        self.lock = threading.Lock()
    
    def update(self, index, progress, status_message):
        with self.lock:
            if progress == 1:  # Completed
                if index in self.active_items:
                    self.active_items.pop(index)
                    self.completed += 1
                    self.pending -= 1
                    self.in_progress -= 1
                    self.pbar.update(1)
            elif progress == -1:  # Failed
                if index in self.active_items:
                    self.active_items.pop(index)
                    self.failed += 1
                    self.pending -= 1
                    self.in_progress -= 1
                    self.pbar.update(1)
            else:  # In progress
                if index not in self.active_items:
                    self.in_progress += 1
                    self.pending -= 1
                self.active_items[index] = status_message
            
            # Update status line
            self._refresh_status()
    
    def _refresh_status(self):
        with console_lock:
            # Update the overall progress bar description
            self.pbar.set_description(
                f"{Fore.CYAN}📥 Overall Progress: {Fore.GREEN}{self.completed} ✓ {Fore.RED}{self.failed} ✗ "
                f"{Fore.BLUE}{self.in_progress} ⬇️ {Fore.YELLOW}{self.pending} ⏳"
            )
            
            # Clear all lines below the progress bar
            print("\033[s", end="")  # Save cursor position
            print("\033[J", end="")  # Clear from cursor to end of screen
            
            # Print active downloads (show all)
            if self.active_items:
                print(f"\n{Fore.CYAN}▶ Active Downloads:")
                for index, status in sorted(self.active_items.items()):
                    print(f"  {status}")
            
            # Restore cursor position
            print("\033[u", end="", flush=True)  # Restore cursor position

    def close(self):
        """Cleanly close the progress bar"""
        self.pbar.close()
def download_playlist(playlist_url, as_audio=True, download_path=None):
    results = []
    
    try:
        playlist = Playlist(playlist_url)
        playlist_name = clean_filename(playlist.title)
        
        download_dir = download_path or os.getcwd()
        playlist_folder = os.path.join(download_dir, playlist_name)
        os.makedirs(playlist_folder, exist_ok=True)
        
        total_videos = len(playlist.video_urls)
        safe_print(f'\n{Fore.CYAN}📋 Playlist: "{Fore.YELLOW}{playlist_name}{Fore.CYAN}" - {Fore.GREEN}{total_videos}{Fore.CYAN} videos')
        
        # Create queue manager
        queue = DownloadQueue(total_videos)
        
        # Prepare download tasks
        download_tasks = []
        for i, video_url in enumerate(playlist.video_urls):
            download_tasks.append((video_url, as_audio, playlist_folder, queue, i, total_videos))
        
        # Process downloads in parallel
        max_workers = min(config["settings"]["parallel_threads"], total_videos)
        safe_print(f"{Fore.CYAN}🧵 Using {Fore.GREEN}{max_workers}{Fore.CYAN} parallel threads")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(download_video_worker, task) for task in download_tasks]
            
            # Wait for all futures to complete
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                results.append(result)
        
        # Close the queue
        queue.close()
                
    except Exception as e:
        safe_print(f"{Fore.RED}Playlist error: {str(e)}")
        results.append({
            "url": playlist_url,
            "success": False,
            "message": f"{Fore.RED}Playlist error: {str(e)}"
        })
    
    return results

def download_single_videos(urls, as_audio=True, download_path=None):
    results = []
    
    total_videos = len(urls)
    
    # Create queue manager
    queue = DownloadQueue(total_videos)
    
    # Prepare download tasks
    download_tasks = []
    for i, video_url in enumerate(urls):
        download_tasks.append((video_url, as_audio, download_path, queue, i, total_videos))
    
    # Process downloads in parallel
    max_workers = min(config["settings"]["parallel_threads"], total_videos)
    safe_print(f"{Fore.CYAN}🧵 Using {Fore.GREEN}{max_workers}{Fore.CYAN} parallel threads")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(download_video_worker, task) for task in download_tasks]
        
        # Wait for all futures to complete
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
    
    # Close the queue
    queue.close()
    
    return results

def main():
    script_directory = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_directory)
    
    try:
        print_banner()
        print_config_info()
        
        download_path = config["app_data"]["download_path"]
        is_playlist = config["settings"]["is_playlist"]
        audio_only = config["settings"]["audio_only"]
        
        all_results = []
        
        if is_playlist:
            playlist_links = config["app_data"]["playlist_url"]
            safe_print(f'{Fore.CYAN}📚 Processing {Fore.GREEN}{len(playlist_links)}{Fore.CYAN} playlists')
            
            for idx, playlist_url in enumerate(playlist_links, 1):
                safe_print(f"\n{Fore.CYAN}[{Fore.YELLOW}{idx}/{len(playlist_links)}{Fore.CYAN}] Processing playlist")
                results = download_playlist(playlist_url, audio_only, download_path)
                all_results.extend(results)
        else:
            single_urls = config["app_data"]["single_url"]
            safe_print(f'{Fore.CYAN}🎬 Processing {Fore.GREEN}{len(single_urls)}{Fore.CYAN} videos')
            results = download_single_videos(single_urls, audio_only, download_path)
            all_results.extend(results)
        
        # Print summary
        success_count = sum(1 for r in all_results if r.get("success", False))
        failed_count = len(all_results) - success_count
        
        safe_print(f"\n{Fore.CYAN}{'═' * 50}")
        safe_print(f"{Fore.CYAN}📊 DOWNLOAD SUMMARY")
        safe_print(f"{Fore.CYAN}{'─' * 50}")
        safe_print(f"{Fore.GREEN}✓ Successful: {success_count}")
        safe_print(f"{Fore.RED}✗ Failed: {failed_count}")
        
        if failed_count > 0:
            safe_print(f"\n{Fore.YELLOW}Failed Downloads:")
            for result in all_results:
                if not result.get("success", False):
                    safe_print(f"{Fore.RED}• {result.get('url', 'Unknown URL')}")
                    safe_print(f"  {result.get('message', 'Unknown error')}")
            
    except Exception as e:
        safe_print(f"{Fore.RED}Fatal error: {str(e)}")
        
    safe_print(f"\n{Fore.GREEN}{'═' * 50}")
    safe_print(f"{Fore.CYAN}✨ Download process complete!")
    safe_print(f"{Fore.GREEN}{'═' * 50}{Style.RESET_ALL}")

if __name__ == "__main__":
    main()