# Real-Time Accident Detector

Streams 5 FPS from a 511mn HLS feed, classifies frames via Together LLaMA Vision model, and pushes "accident"/"no accident" over a WebSocket.

## Setup

1. **Set your Together API key** in the environment variable `TOGETHER_API_KEY`. Sign up for an API key at [Together.ai](https://together.ai).
2. **Update** `VIDEO_SOURCE` in `accident_detector.py` to your actual `.m3u8` URL from 511mn.org.

## Running Locally

### Without Docker

```bash
# Install dependencies
pip install -r requirements.txt

# Set your API key
export TOGETHER_API_KEY=your_api_key_here

# Run the application
uvicorn main:app --reload
```

### With Docker

```bash
# Build the Docker image
docker build -t accident-detector .

# Run the container
docker run -e TOGETHER_API_KEY=your_api_key_here -p 10000:10000 accident-detector
```

## Testing WebSocket

Open a WebSocket client and connect to `ws://localhost:10000/ws/detections`. You'll receive "accident" or "no accident" messages at 5 FPS.

## Deploy on Render.com

1. Push this repository to GitHub.
2. Sign up or log in to [Render.com](https://render.com).
3. In the Render dashboard, click **New** and select **Web Service**.
4. Connect your GitHub repository.
5. Configure the service:
   - **Name**: accident-detector (or your preferred name)
   - **Environment**: Docker
   - **Dockerfile Path**: Dockerfile
   - **Start Command**: uvicorn main:app --host 0.0.0.0 --port 10000
6. In the **Environment** tab, add:
   - Key: `TOGETHER_API_KEY`
   - Value: Your Together API key
   - Mark as secret
7. Click **Create Web Service**.

Your service will be live at something like `wss://accident-detector.onrender.com/ws/detections`.

## Important Notes

- Make sure to use a valid 511mn HLS stream URL
- This service processes frames at approximately 5 FPS (200ms interval)
- The Together API usage incurs costs based on their pricing tiers



some questions that need to be asnwered

1. Where do 