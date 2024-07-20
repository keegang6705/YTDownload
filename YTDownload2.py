import os,json,time,re
from tqdm import tqdm
from pytube import YouTube, Playlist
def clean_file_name(name):
    cleaned_name = re.sub(r'[\/:*?"<>|]', '', name)
    return cleaned_name
def bool2 (input):
    if input == "n" or input == "N":
        return False
    elif input == "y" or input == "Y":
        return True
    else:
        raise ValueError(f"Invalid input: {input}. Only 'y', 'Y', 'n', or 'N' are allowed.")
use_old_settings = bool2(input("use old settings and continue? (Y/N):"))
script_directory = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_directory)
dir_list = [file[:-4] for file in os.listdir(script_directory)]
try:
        def download_single_video(link, as_audio=True, download_path=None):
            try:
                youtubeObject = YouTube(link)
                old_title = youtubeObject.title
                video_title = clean_file_name(old_title)
                download_dir = download_path or os.getcwd()
                print(f"Now downloading: {video_title}")
                print(f"URL: {link}")
                
                if as_audio:
                    audio_stream = youtubeObject.streams.filter(only_audio=True).first()
                    audio_stream.download(output_path=download_dir, filename=video_title)
                    original_file_path = os.path.join(download_dir, video_title)
                    new_file_path = os.path.join(download_dir, f"{video_title}.mp3")
                    os.rename(original_file_path, new_file_path)
                else:
                    video_stream = youtubeObject.streams.get_highest_resolution()
                    video_stream.download(output_path=download_dir)
                print(f"Downloaded video successfully")
                print("-"*30)      
            except Exception as e:
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
                with tqdm(total=playlist_lenght, desc=f"Downloading: {playlist_name}") as pbar:
                    for video_url in playlist.video_urls:    
                        attempt = 0     
                        max_attempt = 3       
                        while attempt < max_attempt:
                            try:
                                print(f"Downloading [{now_video}/{playlist_lenght}] video")
                                download_single_video(video_url, as_audio, download_path=playlist_folder)
                                pbar.update(1)
                                now_video+=1
                                break
                            except:
                                attempt+=1
                                print(f"Error retrying ({attempt}/{max_attempt})")
                                time.sleep(1)
                                continue
                        else:
                            print(f"Error: max retry attempt({max_attempt}/{max_attempt})")
                        
            except Exception as e:
                print(e)

        with open("YTDownloadConfig.json","r") as f:
            config = json.loads(f.read())
            f.close()
        if use_old_settings == False:
            is_playlist = bool2(input("download as playlist? (Y/N):"))
            audio_only = bool2(input("download only audio? (Y/N):"))
            download_path_flag = bool2(input("enter new download path? (Y/N):"))
            if download_path_flag:
                download_path = str(input("download path (str):"))
            single_url_flag = bool2(input("enter new single url? (Y/N):"))
            single_urls = []
            if single_url_flag:
                single_url = str(input("single url (str):"))
                single_urls.append(single_url)
                add_single_url_flag = True
                while add_single_url_flag:
                    add_single_url_flag = bool2(input("enter more single url? (Y/N):"))
                    if add_single_url_flag:
                        single_url = str(input("single url (str):"))
                        single_urls.append(single_url)
                    else:
                        break
                
            playlist_url_flag = bool2(input("enter new playlist url? (Y/N):"))
            playlist_urls = [] 
            if playlist_url_flag:             
                playlist_url = str(input("playlist url (str):"))
                playlist_urls.append(playlist_url)
                add_playlist_url_flag = True
                while add_playlist_url_flag:
                    add_playlist_url_flag = bool2(input("enter more playlist url? (Y/N):"))
                    if add_playlist_url_flag:
                        playlist_url = str(input("playlist url (str):"))
                        playlist_urls.append(playlist_url)
                    else:
                        break


            save_change__flag = bool2(input("save change to config file? (Y/N):"))
            if save_change__flag:
                config["settings"]["is_playlist"] = is_playlist
                config["settings"]["audio_only"] = audio_only
                if download_path_flag:
                    config["app_data"]["download_path"] = download_path
                if single_url_flag:
                    config["app_data"]["single_url"] = single_urls
                if playlist_url_flag:
                    config["app_data"]["playlist_url"] = playlist_urls
                with open("YTDownloadConfig.json","w") as f:
                    json.dump(config,f)
                    f.close()
        
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
        else:
            url = config["app_data"]["single_url"]
            for i in url:
                download_single_video(i, audio_only, download_path)
except Exception as e:
    print(e)

print("\n-------------- Finished download --------------")