# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

YouTube video transcription web application that fetches videos from a channel and transcribes them using OpenAI's Whisper model. Built with Flask backend and vanilla JavaScript frontend.

**Tech Stack:**
- Backend: Flask (Python)
- Frontend: Tailwind CSS + vanilla JavaScript
- YouTube API: google-api-python-client
- Transcription: OpenAI Whisper (with CUDA/GPU support)
- Video Download: yt-dlp

**Repository:** https://github.com/koreats/youtubelister

## Development Commands

### Environment Setup
```bash
# Create virtual environment
python3 -m venv venv

# Activate (macOS/Linux)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
python3 -m pip install -r requirements.txt
```

### Running the Application
```bash
# Start Flask development server
python3 app.py

# Access at http://127.0.0.1:8080
```

### System Requirements
- Python 3.8+
- FFmpeg (required for audio extraction via yt-dlp)
- CUDA-compatible GPU (optional, significantly speeds up transcription)

**macOS Installation:**
```bash
brew install python git ffmpeg
```

See `@doc/mac_guide.md` and `@doc/windows_guide.md` for platform-specific setup instructions.

## Architecture & Code Structure

### Single-File Architecture
The application uses a monolithic structure for simplicity:
- **`app.py`**: Complete backend implementation (360 lines)
- **`templates/index.html`**: Complete frontend with embedded JavaScript

### Key Backend Components (`app.py`)

#### 1. YouTube Channel URL Parsing (`get_channel_id_from_url`)
Handles multiple YouTube URL formats:
- Handle format: `/@username` → extracts via `forHandle` API parameter
- Channel ID: `/channel/UC...` → direct channel ID extraction
- Legacy formats: `/c/username` or `/user/username` → search-based resolution
- Raw channel ID input: `UC...` string

**Fallback chain:** forHandle API → channel search → error handling

#### 2. Whisper Model Management
- **Model Caching**: `LOADED_MODELS` dict caches loaded models to avoid reloading
- **GPU Detection**: Auto-detects CUDA availability (`DEVICE = "cuda" or "cpu"`)
- **Memory Estimates**: `MODEL_MEMORY_USAGE_GB` defines memory requirements per model size

**Important:** In parallel mode, each worker process loads its own model instance (cannot share across processes).

#### 3. Transcription Processing Modes

**Sequential Mode** (default):
- Single-threaded processing
- Model loaded once and reused via `get_model()`
- Verbose logging enabled
- Lower memory footprint

**Parallel Mode**:
- Uses `ProcessPoolExecutor` for concurrent transcription
- **Dynamic Worker Calculation:**
  ```python
  optimal_workers = max(1, min(cpu_cores, available_memory_gb // model_memory_gb))
  ```
- Each worker loads its own Whisper model instance
- Results are ordered to match input sequence
- Significantly faster for multiple videos

**Worker optimization considers:**
- Total CPU cores (`os.cpu_count()`)
- Available system memory (`psutil.virtual_memory().available`)
- Model memory requirements (tiny: 1GB, base: 1.5GB, small: 2.5GB, medium: 5GB, large: 10GB)

#### 4. Progress Tracking
Global state variable `TRANSCRIPTION_PROGRESS`:
```python
{"current": int, "total": int, "status": "idle|processing|complete|error"}
```
- Updated after each video completes (both modes)
- Polled by frontend via `/progress` endpoint
- Thread-safe for sequential mode; updated atomically in parallel mode

#### 5. Video Filtering
Videos under 2 minutes (120 seconds) are automatically excluded from the results during the fetch phase:
```python
if duration_in_seconds <= 120:
    continue
```
This reduces clutter from shorts/intros while keeping the payload size manageable.

### Frontend Architecture (`templates/index.html`)

**Key Implementation Details:**
- **YouTube API Key**: Hardcoded in frontend (client-side API calls for video listing)
- **Real-time Progress**: Polls `/progress` every 500ms during transcription
- **Markdown Export**: Formats results with video title headers and transcripts
- **Copy-to-Clipboard**: Single-click copy of all transcriptions
- **Model Selection**: UI for choosing Whisper model size (tiny → large)
- **Processing Mode**: Toggle between sequential/parallel processing

**Important:** The YouTube API key in `templates/index.html` is used for client-side video fetching. For production deployment, move this to environment variables or backend.

## Common Workflows

### Adding a New Whisper Model Size
1. Update `MODEL_MEMORY_USAGE_GB` dict in `app.py` with memory estimate
2. Add option to model selector in `templates/index.html`
3. Test memory calculation with parallel mode

### Modifying Video Filters
The duration threshold (currently 120 seconds) is in the `/fetch-videos` route:
```python
# Line ~234 in app.py
if duration_in_seconds <= 120:
    continue
```

### Debugging Transcription Issues
- **Sequential mode**: Check terminal output (verbose=True shows progress)
- **Parallel mode**: Worker logs appear with `[Task N]` prefix
- Temporary audio files: Named `temp_audio_{index}.mp3` (auto-cleaned after transcription)
- GPU not detected: Check CUDA installation and PyTorch GPU support

### API Error Handling
YouTube API errors are categorized:
- Invalid API key → "Invalid API Key or permissions issue"
- Channel not found → 404 with helpful message
- Rate limiting → Passes through with status code

## Implementation Notes

### Concurrency Considerations
- **Model Loading**: Cannot share Whisper models across processes (pickle limitation)
- **Memory Management**: Parallel mode auto-calculates workers to prevent OOM
- **Progress Updates**: Safe to update global state in parallel mode (atomic counter increment)

### Performance Optimization
- **Model Caching**: Sequential mode reuses loaded model across videos
- **Parallel Processing**: Scales with CPU cores and available memory
- **GPU Acceleration**: ~5-10x speedup with CUDA-compatible GPU
- **Audio Format**: Downloads as MP3 at 192kbps for balance of quality/size

### YouTube API Quota Management
- Fetching videos uses: ~3 quota units per request (channels, playlistItems, videos)
- No server-side API calls for individual video downloads (uses yt-dlp directly)
- Client-side API key visible in frontend source

### Known Limitations
- No database/persistence (stateless web app)
- Transcription progress resets on server restart
- Temporary audio files stored in project root (not /tmp)
- No authentication/authorization (single-user assumption)
- Parallel mode worker count cannot exceed system resources
