
import os
from flask import Flask, request, jsonify, render_template
import re
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import yt_dlp
import whisper
import concurrent.futures

# --- Helper function to parse ISO 8601 duration ---
def parse_iso8601_duration(duration_str):
    # PnYnMnDTnHnMnS 형식의 문자열을 파싱하여 총 초와 포맷팅된 문자열을 반환
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str).groups()
    hours = int(match[0]) if match[0] else 0
    minutes = int(match[1]) if match[1] else 0
    seconds = int(match[2]) if match[2] else 0
    total_seconds = hours * 3600 + minutes * 60 + seconds
    
    if hours > 0:
        formatted_duration = f'{hours:02d}:{minutes:02d}:{seconds:02d}'
    else:
        formatted_duration = f'{minutes:02d}:{seconds:02d}'
        
    return total_seconds, formatted_duration

import torch

# --- 기본 설정 ---
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
app = Flask(__name__)

# --- GPU 확인 및 Whisper 모델 로딩 ---
print("Loading Whisper model...")
if torch.cuda.is_available():
    print("\n*** NVIDIA GPU(CUDA)가 감지되었습니다! GPU를 사용하여 텍스트 추출 속도를 높입니다. ***\n")
else:
    print("\n--- NVIDIA GPU가 감지되지 않았습니다. CPU를 사용하여 텍스트를 추출합니다. ---\n")
whisper_model = whisper.load_model("base")
print("Whisper model loaded.")


# --- 병렬 처리를 위한 단일 작업 함수 ---
def process_video_task(args):
    index, url = args
    print(f"[Task {index+1}] Starting for URL: {url}")
    try:
        # 1. Download Audio using yt-dlp
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': f'temp_audio_{index}.%(ext)s',
            'quiet': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            video_info = ydl.extract_info(url, download=True)
            audio_filename = f"temp_audio_{index}.mp3"
            video_title = video_info.get('title', '제목 없음')

        print(f"[Task {index+1}] Audio downloaded: {audio_filename}")

        # 2. Transcribe with Whisper
        print(f"[Task {index+1}] Transcribing with Whisper...")
        transcription_result = whisper_model.transcribe(audio_filename)
        transcript_text = transcription_result.get('text', '')
        print(f"[Task {index+1}] Transcription complete.")
        
        # 3. Clean up the downloaded file
        os.remove(audio_filename)
        print(f"[Task {index+1}] Cleanup complete.")

        return {"title": video_title, "transcript": transcript_text}

    except Exception as e:
        print(f"[Task {index+1}] !!! ERROR processing {url}: {e}")
        return {"title": f"오류 발생 (URL: {url})", "transcript": str(e)}

def get_channel_id_from_url(url):
    """Extracts a tuple of (identifier, type) from various YouTube URL formats."""
    # type can be 'id', 'handle', 'search_term'
    
    # Handle: @ (e.g., /@productibe)
    match = re.search(r'youtube\.com/(@[a-zA-Z0-9_.-]+)', url)
    if match:
        # forHandle API parameter does not take the '@', so we strip it.
        return (match.group(1).lstrip('@'), 'handle')

    # Channel ID: /channel/UC...
    match = re.search(r'youtube\.com/channel/(UC[a-zA-Z0-9_-]{22}[a-zA-Z0-9_-])', url)
    if match:
        return (match.group(1), 'id')

    # Legacy custom URL: /c/ or /user/
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

        # 1. Check if the input string itself is a raw Channel ID
        if re.fullmatch(r'UC[a-zA-Z0-9_-]{22}[a-zA-Z0-9_-]', channel_url):
            identifier = channel_url
            id_type = 'id'
        else:
            # 2. If not a raw ID, parse it as a URL
            identifier, id_type = get_channel_id_from_url(channel_url)

        if not identifier:
            return jsonify({"error": "오류: 유효한 채널 ID 또는 URL을 파싱할 수 없습니다."}), 400

        channel_id = None

        # 3. Find the actual channel_id using the identifier and its type
        if id_type == 'id':
            channel_id = identifier
        
        if id_type == 'handle':
            try:
                # Use the modern `forHandle` parameter for precise matching.
                channel_request = youtube.channels().list(part="id", forHandle=identifier)
                response = channel_request.execute()
                if response.get("items"):
                    channel_id = response["items"][0]["id"]
            except HttpError:
                # Fallback to search if forHandle fails (e.g., old API key)
                pass
        
        # 4. Fallback to a general search for legacy URLs or if other methods fail
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

        # 5. With a definitive channel_id, get the uploads playlist.
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

            video_ids = [item['snippet']['resourceId']['videoId'] for item in playlist_response.get("items", [])]
            
            if not video_ids:
                break

            video_details_request = youtube.videos().list(
                part="contentDetails",
                id=",".join(video_ids)
            )
            video_details_response = video_details_request.execute()
            durations = {item['id']: parse_iso8601_duration(item['contentDetails']['duration']) for item in video_details_response.get("items", [])}

            for item in playlist_response.get("items", []):
                snippet = item.get("snippet")
                if not snippet:
                    continue

                video_id = snippet.get("resourceId", {}).get("videoId")
                if not video_id:
                    continue

                duration_in_seconds, formatted_duration = durations.get(video_id, (0, "00:00"))

                # 영상 길이가 2분(120초) 이하인 경우 목록에 추가하지 않음
                if duration_in_seconds <= 120:
                    continue

                if "title" in snippet and "publishedAt" in snippet:
                    videos.append({
                        "videoId": video_id,
                        "title": snippet["title"],
                        "publishedAt": snippet["publishedAt"],
                        "duration": formatted_duration,
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

@app.route("/transcribe_multiple", methods=["POST"])
def transcribe_multiple():
    data = request.get_json()
    urls = data.get('urls', [])
    results = []
    print(f"\n--- Received {len(urls)} URLs for transcription ---")

    # 병렬 처리를 위해 ProcessPoolExecutor 사용
    with concurrent.futures.ProcessPoolExecutor() as executor:
        # enumerate를 사용하여 각 URL에 인덱스를 부여하고, 이를 map에 전달
        # executor.map은 작업을 제출한 순서대로 결과를 반환합니다.
        results = list(executor.map(process_video_task, enumerate(urls)))

    print(f"--- Transcription finished. Returning {len(results)} results. ---")
    return jsonify({"results": results})


if __name__ == "__main__":
    app.run(debug=True, port=8080)