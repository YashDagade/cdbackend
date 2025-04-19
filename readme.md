# Real-Time Multi-Stream Accident Detector 🚗 🔍

A service that monitors multiple traffic camera streams, detects potential accidents using AI, and provides real-time video streaming and accident alerts through modern WebSocket endpoints.

## 🌐 Demo Site

The application is deployed at: [https://cdbackend.onrender.com](https://cdbackend.onrender.com)

## 🔥 Key Features

- **Multi-Stream Support**: Monitor multiple traffic cameras simultaneously
- **Real-time Video Streaming**: 30 FPS video delivery to clients
- **AI-Powered Accident Detection**: Using Together AI's LLaMA-3.2-11B-Vision model 
- **Optimized Dual WebSocket Architecture**:
  - `/ws/stream/{stream_id}` - High-performance 30 FPS video stream
  - `/ws/analyze/{stream_id}` - Dedicated accident alert notifications

## 📊 Architecture Overview

![Architecture](https://i.ibb.co/R3nnVMd/accident-detector-architecture.png)

The system uses a clean, efficient architecture:

1. **Video Processing**: 
   - Background threads extract frames from video streams (HLS/M3U8 format) using ffmpeg
   - Frames are continuously updated at 30 FPS

2. **AI Analysis**:
   - Separate worker threads analyze frames without blocking the video stream
   - Queue-based design prevents analysis bottlenecks
   - Two-step AI process: detection followed by accident description
   - Multi-threaded analysis prevents long AI calls from affecting performance

3. **Client Communication**:
   - Separated endpoints allow clients to connect only to what they need
   - High-performance frame streaming without the detection overhead
   - Targeted accident alerts without constant frame transmission

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- ffmpeg (for HLS stream processing)
- Together AI API key (for accident detection)

### Installation & Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/accident-detector.git
   cd accident-detector
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up your API key:
   ```bash
   # Create a .env file
   echo "TOGETHER_API_KEY=your_api_key_here" > .env
   ```

4. Run the application:
   ```bash
   uvicorn main:app --reload
   ```

5. Open the test client:
   - Navigate to `http://localhost:8000/dual_client_example.html` or open the HTML file directly

### Configuration

Edit `streams_config.py` to add or modify your video streams:

```python
STREAMS = [
    {
        "id": "mn_c550",
        "url": "https://video.dot.state.mn.us/public/C550.stream/chunklist_w780326163.m3u8",
        "location": "MN Hwy 55 at Hwy 100",
        "analysis_fps": 1,  # Check for accidents once per second
    },
    # Add more streams as needed
]
```

## 📖 API Documentation

See [API_ROUTES.md](API_ROUTES.md) for detailed API documentation.

## 📱 Client Integration

Two options for integrating with clients:

### Option 1: Separate Connections (Recommended)

```javascript
// Video stream for real-time display
const frameSocket = new WebSocket(`wss://cdbackend.onrender.com/ws/stream/mn_c550`);
frameSocket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    videoElement.src = `data:image/jpeg;base64,${data.frame}`;
};

// Analysis stream for accident alerts
const analysisSocket = new WebSocket(`wss://cdbackend.onrender.com/ws/analyze/mn_c550`);
analysisSocket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'accident_alert') {
        showAlert(data.description, data.frame);
    }
};
```

### Option 2: Legacy Combined Stream (Not Recommended)

```javascript
const socket = new WebSocket(`wss://cdbackend.onrender.com/ws/combined/mn_c550`);
socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.frame) {
        videoElement.src = `data:image/jpeg;base64,${data.frame}`;
    }
    if (data.detection && data.detection.result === 'accident') {
        showAlert(data.detection.description);
    }
};
```

## 🧪 Example Client

A complete example client implementation is provided in `dual_client_example.html`. This client demonstrates:

- Connecting to both WebSocket endpoints
- Displaying the video stream at 30 FPS
- Showing accident alerts in a dedicated panel
- FPS monitoring
- Connection status indicators

## 📋 License

MIT License

## 🔧 Troubleshooting

- **No frames showing**: Ensure the M3U8 URL is valid and accessible from your server
- **Low frame rate**: Check network conditions and client performance
- **AI detection not working**: Verify your Together AI API key is valid