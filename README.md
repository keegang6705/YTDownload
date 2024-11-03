# YouTube Downloader

This project is a script for downloading videos from YouTube using Python, supporting both audio and video formats, as well as playlist downloads.

## Prerequisites

- Python 3.x
- Required libraries:
  - `pytubefix`
  - `tqdm`
  - `moviepy`

You can install the necessary libraries using the following command:
```bash
pip install pytubefix tqdm moviepy
```
## usage
You can customize various settings in the config by modifying the values in config varriable
```bash
python3 YTDownload3.5.py
```
## Features
- Supports downloading both audio and video.
- Supports downloading from playlists.
- Provides progress notifications using tqdm.
- Error handling during the download process.
In case of an error during downloading, the script will attempt to retry the download a specified number of times. If it still fails, the link that could not be downloaded will be recorded in the cached_err variable andr print out after program end.
