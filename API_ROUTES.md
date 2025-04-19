# API Routes Documentation

This document outlines all available API endpoints for the Real-Time Accident Detector service.

## Base URL

- **Local Development**: `http://localhost:10000`
- **Production**: `https://cdbackend.onrender.com`

## HTTP Endpoints

### Health Check

- **URL**: `/`
- **Method**: `GET`
- **Description**: Simple health check endpoint to verify the service is running.
- **Response**: 
  ```json
  {
    "status": "ok"
  }
  ```
- **Example**:
  ```bash
  curl https://cdbackend.onrender.com/
  ```

## WebSocket Endpoints

### Real-Time Accident Detections

- **URL**: `/ws/detections`
- **WebSocket Protocol**: `ws://` (local) or `wss://` (production)
- **Description**: Streams accident detection results at approximately 5 FPS.
- **Response Format**: Text message containing either `"accident"` or `"no accident"`.
- **Connection Example**:
  - Browser:
    ```javascript
    const socket = new WebSocket("wss://cdbackend.onrender.com/ws/detections");
    
    socket.onmessage = (event) => {
      console.log("Detection result:", event.data);
    };
    ```
  - Python:
    ```python
    import asyncio
    import websockets
    
    async def connect():
        uri = "wss://cdbackend.onrender.com/ws/detections"
        async with websockets.connect(uri) as websocket:
            while True:
                message = await websocket.recv()
                print(f"Received: {message}")
    
    asyncio.run(connect())
    ```

### Real-Time Video Stream

- **URL**: `/ws/video`
- **WebSocket Protocol**: `ws://` (local) or `wss://` (production)
- **Description**: Streams video frames from the traffic camera at approximately 30 FPS.
- **Response Format**: JSON containing base64-encoded JPEG image.
  ```json
  {
    "frame": "base64EncodedImageData..."
  }
  ```
- **Connection Example**:
  - Browser:
    ```javascript
    const socket = new WebSocket("wss://cdbackend.onrender.com/ws/video");
    const videoElement = document.getElementById('videoFeed');
    
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.frame) {
          videoElement.src = `data:image/jpeg;base64,${data.frame}`;
        }
      } catch (error) {
        console.error("Error parsing video data:", error);
      }
    };
    ```
  - Python:
    ```python
    import asyncio
    import json
    import websockets
    import base64
    from PIL import Image
    import io
    
    async def connect_video():
        uri = "wss://cdbackend.onrender.com/ws/video"
        async with websockets.connect(uri) as websocket:
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                if "frame" in data:
                    # Convert base64 to image
                    image_data = base64.b64decode(data["frame"])
                    image = Image.open(io.BytesIO(image_data))
                    # Process image as needed
                    image.save(f"latest_frame.jpg")
                    print("Received new frame")
    
    asyncio.run(connect_video())
    ```

## Implementation Details

### Technical Architecture

1. **Frame Extraction**: 
   - Uses ffmpeg to extract frames from the HLS stream at 30 FPS for video and 5 FPS for analysis
   - Updates a single JPEG file continuously rather than storing multiple files
   - Runs in a background thread to avoid blocking the main application

2. **Image Classification**:
   - Together LLaMA Vision model classifies each frame as "accident" or "no accident"
   - Only processes new frames when they're available (checks file modification time)
   - Caches the last result to avoid unnecessary processing

3. **WebSocket Broadcast**:
   - Separate WebSocket endpoints for video streaming and accident detection
   - Video stream runs at higher framerate (30 FPS) than accident detection (5 FPS)
   - Efficiently handles connection management and dead connection cleanup

### Performance Considerations

- The video stream runs at approximately 30 frames per second
- The accident detection runs at approximately 5 frames per second (200ms intervals)
- The HLS video stream URL is configured in `accident_detector.py` as `VIDEO_SOURCE`
- No authentication is currently required for accessing the endpoints
- Free tier deployments on Render.com will spin down with inactivity (may cause ~50s delay on first access)

## Testing

A browser-based test client is available in `client_example.html` that connects to both WebSocket endpoints and displays real-time video and detection results. 