import os
from flask import Flask, request, jsonify, render_template
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import re
from datetime import datetime

# --- NEW IMPORTS for Transcription ---
import yt_dlp
import whisper
import time # To simulate long tasks if needed

# --- Suppress OAuth 2.0 warnings ---
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

app = Flask(__name__)

# --- NEW: Load Whisper Model ---
# This loads the model into memory once when the application starts.
# This avoids reloading the model on every request, which is very slow.
# "base" is fast. For higher accuracy, you can use "small" or "medium",
# but they are slower and require more memory.
print("Loading Whisper model...")
whisper_model = whisper.load_model("base")
print("Whisper model loaded.")


# --- EXISTING CODE (No changes needed below) ---

def get_channel_id_from_url(url):
    """Extracts a tuple of (identifier, type) from various YouTube URL formats."""
    match = re.search(r'youtube\.com/(@[a-zA-Z0-9_.-]+)', url)
    if match:
        return (match.group(1).lstrip('@'), 'handle')

    match = re.search(r'youtube\.com/channel/(UC[a-zA-Z0-9_-]{22}[a-zA-Z0-9_-])', url)
    if match:
        return (match.group(1), 'id')

    match = re.search(r'youtube\.com/(?:c|user)/([a-zA-Z0-9_.-]+)', url)
    if match:
        return (match.group(1), 'search_term')

    return (None, None)

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/fetch-videos", methods=["POST"])
def fetch_videos():
    data = request.get_json()
    channel_url = data.get("channel_url", "").strip()
    api_key = data.get("api_key")

    if not channel_url or not api_key:
        return jsonify({"error": "Channel URL and API Key are required."}), 400

    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        
        identifier = None
        id_type = None

        if re.fullmatch(r'UC[a-zA-Z0-9_-]{22}[a-zA-Z0-9_-]', channel_url):
            identifier = channel_url
            id_type = 'id'
        else:
            identifier, id_type = get_channel_id_from_url(channel_url)

        if not identifier:
            return jsonify({"error": "오류: 유효한 채널 ID 또는 URL을 파싱할 수 없습니다."}), 400

        channel_id = None

        if id_type == 'id':
            channel_id = identifier
        
        if id_type == 'handle':
            try:
                channel_request = youtube.channels().list(part="id", forHandle=identifier)
                response = channel_request.execute()
                if response.get("items"):
                    channel_id = response["items"][0]["id"]
            except HttpError:
                pass
        
        if not channel_id:
            try:
                search_request = youtube.search().list(part="id", q=identifier, type="channel", maxResults=1)
                search_response = search_request.execute()
                if search_response.get("items"):
                    channel_id = search_response["items"][0]["id"]["channelId"]
            except HttpError:
                pass

        if not channel_id:
            return jsonify({"error": "오류: 유튜브 채널을 찾을 수 없습니다. URL을 확인하거나 공개된 채널인지 확인하세요."}), 404

        channel_details_response = youtube.channels().list(
            part="contentDetails",
            id=channel_id
        ).execute()

        if not channel_details_response.get("items"):
            return jsonify({"error": "오류: 채널 ID를 찾은 후 세부 정보를 가져올 수 없습니다."}), 500

        uploads_playlist_id = channel_details_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

        videos = []
        next_page_token = None
        while True:
            playlist_request = youtube.playlistItems().list(
                part="snippet",
                playlistId=uploads_playlist_id,
                maxResults=50,
                pageToken=next_page_token
            )
            playlist_response = playlist_request.execute()

            for item in playlist_response.get("items", []):
                snippet = item.get("snippet")
                if not snippet: continue
                resource_id = snippet.get("resourceId")
                if not resource_id: continue
                video_id = resource_id.get("videoId")
                if not video_id: continue
                if "title" in snippet and "publishedAt" in snippet:
                    videos.append({
                        "videoId": video_id,
                        "title": snippet["title"],
                        "publishedAt": snippet["publishedAt"],
                        "url": f"https://www.youtube.com/watch?v={video_id}"
                    })

            next_page_token = playlist_response.get("nextPageToken")
            if not next_page_token:
                break
        
        sorted_videos = sorted(videos, key=lambda v: v["publishedAt"], reverse=True)
        return jsonify({"videos": sorted_videos})

    except HttpError as e:
        error_message = f"An API error occurred: {e.resp.status} {e.reason}"
        if "invalid" in str(e).lower() or "key" in str(e).lower():
            error_message = "Invalid API Key or permissions issue."
        return jsonify({"error": error_message}), e.resp.status
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


# --- NEW: API Endpoint for Transcription ---

@app.route("/transcribe_multiple", methods=["POST"])
def transcribe_multiple():
    data = request.get_json()
    urls = data.get('urls', [])
    results = []
    print(f"\n--- Received {len(urls)} URLs for transcription ---")

    for i, url in enumerate(urls):
        print(f"\n[Video {i+1}/{len(urls)}] Processing URL: {url}")
        try:
            # 1. Download Audio using yt-dlp
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': f'temp_audio_{i}.%(ext)s',
                'quiet': False, # Show yt-dlp logs
            }
            
            audio_filename = f"temp_audio_{i}.mp3"
            video_title = "제목 없음"

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                video_info = ydl.extract_info(url, download=True)
                video_title = video_info.get('title', '제목 없음')
            
            print(f" -> Audio downloaded: {audio_filename}")

            # 2. Transcribe with Whisper
            print(f" -> Transcribing with Whisper...")
            transcription_result = whisper_model.transcribe(audio_filename, verbose=True)
            transcript_text = transcription_result['text']
            print(f" -> Transcription complete. Text length: {len(transcript_text)}")
            
            results.append({
                "title": video_title,
                "transcript": transcript_text
            })

            # 3. Clean up the downloaded file
            print(f" -> Removing temporary file: {audio_filename}")
            os.remove(audio_filename)

        except Exception as e:
            print(f" !!! ERROR processing {url}: {e}")
            # If one video fails, add an error message for it and continue
            results.append({
                "title": f"오류 발생 (URL: {url})",
                "transcript": str(e)
            })
            # Clean up if file exists even after error
            if 'audio_filename' in locals() and os.path.exists(audio_filename):
                os.remove(audio_filename)
            continue

    print(f"--- Transcription finished. Returning {len(results)} results. ---")
    return jsonify({"results": results})


# --- EXISTING CODE ---
if __name__ == "__main__":
    app.run(debug=True)
