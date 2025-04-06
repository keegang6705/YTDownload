import os, time, re, json, unicodedata
from pytubefix import YouTube, Playlist
from pytubefix.cli import on_progress
from moviepy.audio.io.AudioFileClip import AudioFileClip
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.table import Table
from rich import box

console = Console()

def load_config(path='./config.json'):
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    else:
        console.print("[yellow]config.json not found, using default config[/]")
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

def clean_filename(name, max_length=config["settings"]["max_name_length"]):
    name = unicodedata.normalize('NFKC', name)
    name_parts = os.path.splitext(name)
    base_name = name_parts[0]
    extension = name_parts[1] if len(name_parts) > 1 else '.mp3'
    cleaned_base = re.sub(r'[\\/:*?"\'<>|]', '', base_name)
    cleaned_base = ''.join(char for char in cleaned_base if char.isprintable())
    available_length = max_length - len(extension)
    if len(cleaned_base) > available_length:
        while len(cleaned_base.encode('utf-8')) > available_length:
            cleaned_base = cleaned_base[:-1]
    final_name = f"{cleaned_base}{extension}"
    return final_name

def get_unique_filename(base_path, filename):
    name_parts = os.path.splitext(filename)
    base_name = name_parts[0]
    extension = name_parts[1] if len(name_parts) > 1 else '.mp3'
    counter = 1
    new_filename = filename
    while os.path.exists(os.path.join(base_path, new_filename)):
        new_name = f"{base_name} ({counter})"
        new_filename = f"{new_name}{extension}"
        counter += 1
    return new_filename

def convert_to_mp3(input_path, output_path):
    try:
        audio = AudioFileClip(input_path)
        audio.write_audiofile(output_path, logger=None)
        audio.close()
        os.remove(input_path)
    except Exception as e:
        raise DownloadError(f"Error converting to MP3: {str(e)}")

def download_single_video(link, as_audio=True, download_path=None):
    try:
        youtubeObject = YouTube(url=link, client='WEB', on_progress_callback=on_progress, use_oauth=config["settings"]["user_login"])
        original_title = youtubeObject.title
        video_title = clean_filename(original_title)
        download_dir = download_path or os.getcwd()
        video_title = get_unique_filename(download_dir, video_title)
        final_filename = os.path.splitext(video_title)[0] + '.mp3'
        final_path = os.path.join(download_dir, final_filename)

        if os.path.exists(final_path):
            console.print(f"[yellow]Skipping: {original_title}[/] (already exists)")
            return

        temp_filename = os.path.splitext(video_title)[0] + '_temp'
        full_path = os.path.join(download_dir, video_title)
        if len(full_path.encode('utf-8')) >= 255:
            video_title = clean_filename(original_title, max_length=100)
            video_title = get_unique_filename(download_dir, video_title)

        console.print(f"\n[bold blue]Now downloading:[/] {original_title}")
        console.print(f"Saving as: {final_filename}")
        console.print(f"URL: {link}")

        if as_audio:
            stream = youtubeObject.streams.get_audio_only()
            temp_path = os.path.join(download_dir, temp_filename)
            final_path = os.path.join(download_dir, final_filename)
            stream.download(output_path=download_dir, filename=temp_filename)
            console.print("Converting to MP3...")
            convert_to_mp3(temp_path, final_path)
        else:
            stream = youtubeObject.streams.get_highest_resolution()
            stream.download(output_path=download_dir, filename=video_title)

        console.print("[green]Downloaded and converted successfully[/]")

    except Exception as e:
        error_msg = f"Error downloading {link}: {str(e)}"
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

        console.print(f'\n[bold magenta]Playlist:[/] {playlist_name}')
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeRemainingColumn(),
            transient=True,
            console=console
        ) as progress:
            task = progress.add_task(f"[cyan]Downloading videos...", total=total_videos)
            for video_url in playlist.video_urls:
                for attempt in range(config["settings"]["max_retry_attempt"]):
                    try:
                        download_single_video(video_url, as_audio, download_path=playlist_folder)
                        break
                    except DownloadError as e:
                        if attempt == config["settings"]["max_retry_attempt"] - 1:
                            errors[video_url] = str(e)
                            console.print(f"[red]Max retries reached for:[/] {video_url}")
                        else:
                            console.print(f"[yellow]Retrying ({attempt + 1}/{config['settings']['max_retry_attempt']})...[/]")
                            time.sleep(1)
                progress.update(task, advance=1)
    except Exception as e:
        console.print(f"[red]Playlist error:[/] {str(e)}")
        errors[playlist_url] = str(e)
    return errors

def pretty_print_config(config):
    table = Table(title="Configuration Loaded", box=box.SIMPLE_HEAVY)
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    for section, items in config.items():
        if isinstance(items, dict):
            for key, value in items.items():
                table.add_row(f"{section}.{key}", str(value))
        elif isinstance(items, list):
            table.add_row(section, ", ".join(items))
        else:
            table.add_row(section, str(items))
    console.print(table)

def main():
    script_directory = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_directory)
    try:
        console.rule("[bold blue]YouTube Downloader Started")
        pretty_print_config(config)
        console.rule()

        download_path = config["app_data"]["download_path"]
        is_playlist = config["settings"]["is_playlist"]
        audio_only = config["settings"]["audio_only"]
        all_errors = {}

        if is_playlist:
            playlist_links = config["app_data"]["playlist_url"]
            console.print(f'[bold]Number of playlists:[/] {len(playlist_links)}')
            for idx, playlist_url in enumerate(playlist_links, 1):
                console.print(f"\n[blue]▶ Downloading playlist [{idx}/{len(playlist_links)}][/]")
                errors = download_playlist(playlist_url, audio_only, download_path)
                if errors:
                    all_errors.update(errors)
        else:
            for url in config["app_data"]["single_url"]:
                try:
                    download_single_video(url, audio_only, download_path)
                except DownloadError as e:
                    all_errors[url] = str(e)

        if all_errors:
            error_table = Table(title="Errors Encountered", box=box.MINIMAL_DOUBLE_HEAD)
            error_table.add_column("URL", style="red")
            error_table.add_column("Error", style="white")
            for url, err in all_errors.items():
                error_table.add_row(url, err)
            console.print(error_table)

    except Exception as e:
        console.print(Panel(f"[bold red]{str(e)}[/]", title="Fatal Error", border_style="red"))

    console.print(Panel("🎉 [bold green]All downloads finished![/]", title="Complete", border_style="green"))

if __name__ == "__main__":
    main()