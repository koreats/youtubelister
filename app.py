
import os
from flask import Flask, request, jsonify, render_template
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import re
from datetime import datetime

# Suppress OAuth 2.0 warnings when using an API key
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

app = Flask(__name__)

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
                if not snippet:
                    continue
                resource_id = snippet.get("resourceId")
                if not resource_id:
                    continue
                video_id = resource_id.get("videoId")
                if not video_id:
                    continue
                if "title" in snippet and "publishedAt" in snippet:
                    videos.append({
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

if __name__ == "__main__":
    app.run(debug=True)
