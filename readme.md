# Real‑Time Multi-Stream Accident Detector

Streams video from configured sources (e.g., 511mn HLS feeds), classifies frames for accidents using a Vision model (Together AI LLaMA), generates descriptions for detected accidents, and pushes combined frame/detection data over WebSockets.

## Features

- **Multiple Stream Support**: Configure and process multiple video streams simultaneously.
- **Real-time Detection**: Classifies frames as 'accident' or 'no_accident'.
- **Accident Description**: Generates a brief description if an accident is detected.
- **Combined WebSocket Stream**: Provides a single endpoint per stream (`/ws/stream/{stream_id}`) sending both video frames and detection results.
- **Accident Logging**: Logs detected accidents with timestamp, location, and description to `logs/accidents.log`.
- **REST API**: Endpoints to list streams and get latest frame/detection data.

## Setup

1.  **Configure Streams**: 
    - Edit `streams_config.py`.
    - Define each video source with a unique `id`, `url` (M3U8 or 'fallback'), `location` description, `analysis_fps`, and `stream_fps`.
2.  **Set API Key**: 
    - Set your Together API key as an environment variable: `TOGETHER_API_KEY`.
    - You can create a `.env` file (add it to `.gitignore`!) with `TOGETHER_API_KEY=your_key_here` for local development.
3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Running Locally

```bash
# Ensure TOGETHER_API_KEY is set in your environment or .env file
uvicorn main:app --reload --port 8000 
```

Connect your WebSocket client to `ws://localhost:8000/ws/stream/{stream_id}` (e.g., `ws://localhost:8000/ws/stream/mn_c550`).

## Running with Docker

```bash
docker build -t multi-stream-detector . 
docker run -e TOGETHER_API_KEY=$TOGETHER_API_KEY -p 10000:8000 multi-stream-detector
```

*(Note: Dockerfile maps internal port 8000 to external port 10000)*
Connect WebSocket clients to `ws://localhost:10000/ws/stream/{stream_id}`.

## Deploy on Render.com

1.  Push this repo (including `streams_config.py`) to GitHub.
2.  On Render.com, create a New → Web Service.
3.  Connect your GitHub repository.
4.  **Environment**: Python (Render might auto-detect, otherwise select Python 3).
5.  **Build Command**: `pip install -r requirements.txt`
6.  **Start Command**: `uvicorn main:app --host 0.0.0.0 --port 8000`
7.  **Environment Variables** (under Environment tab):
    - Add `TOGETHER_API_KEY` → your API key (mark as secret).
    - Set `PYTHON_VERSION` to `3.11` (or match your local version).
8.  Click Create Web Service.

Your service will be live at `your-service-name.onrender.com`. Connect WebSockets to `wss://your-service-name.onrender.com/ws/stream/{stream_id}`.

*(Note: The free tier spins down with inactivity, causing a delay on first access.)*

## API Documentation

For detailed information on all available endpoints and data formats, see [API_ROUTES.md](API_ROUTES.md).

## Testing

A basic browser-based test client is included in `client_example.html`. You'll need to modify it to connect to the new `/ws/stream/{stream_id}` endpoint and handle the combined JSON data format.