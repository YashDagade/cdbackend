# Real‑Time Accident Detector

Streams 5 FPS from a 511mn HLS feed, classifies frames via Together LLaMA Vision model, and pushes "accident"/"no accident" over a WebSocket.

## Setup

1. **Set your Together API key** in the env var `TOGETHER_API_KEY`.
2. **Update** `VIDEO_SOURCE` in `accident_detector.py` to your actual `.m3u8` URL.

## Running Locally (Docker)

```bash
docker build -t accident-detector .
docker run -e TOGETHER_API_KEY=$TOGETHER_API_KEY -p 10000:10000 accident-detector
```

Open `ws://localhost:10000/ws/detections` in your client.

## Deploy on Render.com

1. Push this repo to GitHub.
2. On Render.com, New → Web Service.
3. Environment: Docker
4. Dockerfile Path: Dockerfile
5. Start Command: `uvicorn main:app --host 0.0.0.0 --port 10000`
6. In Environment tab, add:
   - `TOGETHER_API_KEY` → your API key (mark as secret)
7. Click Create Web Service → it will build & deploy.

Your service will be live at:
```
wss://cdbackend.onrender.com/ws/detections
```



some questions that need to be asnwered

1. Where do 