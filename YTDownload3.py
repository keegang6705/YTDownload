#### v3.0.0 
###  tested 100% pass
###  Unoptimized
###  Contributors:keegang6705,flame-suwan
import os,json,time,re
from tqdm import tqdm
from pytubefix import YouTube, Playlist
from pytubefix.cli import on_progress

config = {
  "config_version": 0,
  "settings": { "is_playlist": True, "audio_only": True },
  "app_data": {
    "download_path": "/home/music",
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
cached_err = {}


def clean_file_name(name):
    cleaned_name = re.sub(r'[\\/:*?"\'<>|]', '', name)
    return cleaned_name

script_directory = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_directory)
dir_list = [file[:-4] for file in os.listdir(script_directory)]
try:
        def download_single_video(link, as_audio=True, download_path=None):
            try:
                youtubeObject = YouTube(link, on_progress_callback = on_progress)
                old_title = youtubeObject.title
                video_title = clean_file_name(old_title)
                download_dir = download_path or os.getcwd()
                print(f"Now downloading: {video_title}")
                print(f"URL: {link}")
                
                if as_audio:
                    audio_stream = youtubeObject.streams.get_audio_only()
                    audio_stream.download(output_path=download_dir, filename=video_title,mp3=True)
                else:
                    video_stream = youtubeObject.streams.get_highest_resolution()
                    video_stream.download(output_path=download_dir)
                print(f"Downloaded video successfully")
                print("-"*30)      
            except Exception as e:
                if '[WinError 183]' in str(e):
                    print("this name already exist creating new name...")    
                    try:
                        youtubeObject = YouTube(link, on_progress_callback = on_progress)
                        old_title = youtubeObject.title
                        video_title = clean_file_name(old_title)+"(1)"
                        download_dir = download_path or os.getcwd()
                        print(f"Now downloading: {video_title}")
                        print(f"URL: {link}")
                        
                        if as_audio:
                            audio_stream = youtubeObject.streams.get_audio_only()
                            audio_stream.download(output_path=download_dir, filename=video_title,mp3=True)
                        else:
                            video_stream = youtubeObject.streams.get_highest_resolution()
                            video_stream.download(output_path=download_dir)
                        print(f"Downloaded video successfully")
                        print("-"*30)        
                    except Exception as e:
                        print(e)
                        raise
                else:
                    print(e)
                    raise

        def download_playlist(playlist, as_audio=True, download_path=None):
            try:
                playlist = Playlist(playlist)
                playlist_name = playlist.title

                download_dir = download_path or os.getcwd()
                playlist_folder = os.path.join(download_dir, playlist_name)
                os.makedirs(playlist_folder, exist_ok=True)
                playlist_lenght = len(playlist.video_urls)

                print(f'Number of videos in playlist "{playlist_name}": {playlist_lenght}')

                now_video = 1
                with tqdm(total=playlist_lenght, desc=f"Downloading: {playlist_name} ") as pbar:
                    for video_url in playlist.video_urls:    
                        attempt = 0     
                        max_attempt = 10       
                        while attempt < max_attempt:
                            try:
                                print("\n")
                                download_single_video(video_url, as_audio, download_path=playlist_folder)
                                pbar.update(1)
                                now_video+=1
                                break
                            except:
                                print("\n")
                                attempt+=1
                                print(f"Error retrying ({attempt}/{max_attempt})")
                                time.sleep(1)
                                continue
                        else:
                            print("\n")
                            pbar.update(1)
                            print(f"Error: max retry attempt({max_attempt}/{max_attempt})")
                            cached_err[video_url] = "max retry attempt"
                        
            except Exception as e:
                print(e)

       
        print("-"*30)
        print(json.dumps(config,indent=1))
        print("-"*30)
        download_path = config["app_data"]["download_path"]
        is_playlist = config["settings"]["is_playlist"]
        audio_only = config["settings"]["audio_only"]
        if is_playlist:
            playlist_links = config["app_data"]["playlist_url"]
            print(f'Number of playlist : {len(playlist_links)}')
            now_playlist = 1
            for i in playlist_links:
                print(f"Downloading [{now_playlist}/{len(playlist_links)}] playlist")
                download_playlist(i, audio_only, download_path)
                now_playlist+=1
            print("printing cached error...\n")
            print("-"*30)
            print(json.dumps(cached_err,indent=1))
            print("-"*30)
        else:
            url = config["app_data"]["single_url"]
            for i in url:
                download_single_video(i, audio_only, download_path)

except Exception as e:
    print(e)

print("\n-------------- Finished download --------------")
