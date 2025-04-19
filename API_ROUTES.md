# API Routes Documentation

This document outlines all available API endpoints for the Real-Time Multi-Stream Accident Detector service.

## Base URL

- **Local Development**: `http://localhost:8000` (or port specified when running uvicorn)
- **Production (Example)**: `https://your-service-name.onrender.com`

## HTTP Endpoints

### Health Check

- **URL**: `/`
- **Method**: `GET`
- **Description**: Simple health check endpoint to verify the service is running and lists active stream IDs.
- **Success Response (200)**:
  ```json
  {
    "status": "ok",
    "streams_running": ["mn_c550", "another_stream_id"]
  }
  ```
- **Example**:
  ```bash
  curl http://localhost:8000/
  ```

### List Available Streams

- **URL**: `/streams`
- **Method**: `GET`
- **Description**: Returns a list of configured streams with their ID, location, and current status.
- **Success Response (200)**:
  ```json
  {
    "streams": [
      {
        "id": "mn_c550",
        "location": "MN Hwy 55 at Hwy 100",
        "status": "success"
      },
      {
        "id": "fallback_example",
        "location": "Fallback Test Camera",
        "status": "initializing"
      }
    ]
  }
  ```
- **Example**:
  ```bash
  curl http://localhost:8000/streams
  ```

### Get Latest Frame for a Stream

- **URL**: `/stream/{stream_id}/frame`
- **Method**: `GET`
- **Path Parameter**: `stream_id` (string, required) - The ID of the desired stream (e.g., `mn_c550`).
- **Description**: Returns the latest captured frame for the specified stream as a base64 encoded JPEG string.
- **Success Response (200)**:
  ```json
  {
    "stream_id": "mn_c550",
    "frame": "/9j/4AAQSkZJRgABAQE... (base64 encoded image data)"
  }
  ```
- **Success Response (200 - Frame Temporarily Unavailable)**:
  ```json
  {
      "stream_id": "mn_c550",
      "frame": null,
      "message": "Frame currently unavailable"
  }
  ```
- **Error Response (404 - Stream Not Found)**:
  ```json
  {
    "detail": "Stream 'invalid_id' not found."
  }
  ```
- **Error Response (404 - No Frame Yet)**:
  ```json
  {
      "detail": "No frame available yet for stream 'mn_c550'."
  }
  ```
- **Example**:
  ```bash
  curl http://localhost:8000/stream/mn_c550/frame
  ```

### Get Latest Detection for a Stream

- **URL**: `/stream/{stream_id}/detect`
- **Method**: `GET`
- **Path Parameter**: `stream_id` (string, required) - The ID of the desired stream.
- **Description**: Returns the latest accident detection result for the specified stream.
- **Success Response (200)**:
  ```json
  {
    "stream_id": "mn_c550",
    "detection": {
      "status": "success",
      "result": "no_accident", // or "accident"
      "description": null, // or "Brief description of the accident..."
      "timestamp": "2023-10-27T10:30:00.123456+00:00", // ISO 8601 format
      "location": "MN Hwy 55 at Hwy 100"
    }
  }
  ```
- **Error Response (404 - Stream Not Found)**:
  ```json
  {
    "detail": "Stream 'invalid_id' not found."
  }
  ```
- **Example**:
  ```bash
  curl http://localhost:8000/stream/mn_c550/detect
  ```

## WebSocket Endpoint

### Combined Stream Data

- **URL**: `/ws/stream/{stream_id}`
- **WebSocket Protocol**: `ws://` (local) or `wss://` (production)
- **Path Parameter**: `stream_id` (string, required) - The ID of the stream to connect to.
- **Description**: Establishes a WebSocket connection for a specific stream. The server pushes combined data messages containing the latest video frame and the latest detection result at the `stream_fps` defined in the configuration.
- **Message Format (Server -> Client)**: JSON object
  ```json
  {
    "frame": "/9j/4AAQSkZJRgABAQE... (base64 encoded image data or null)",
    "detection": {
      "status": "success", // "initializing", "no_frame", "error"
      "result": "no_accident", // or "accident"
      "description": null, // or "Brief description..."
      "timestamp": "2023-10-27T10:30:00.123456+00:00", // ISO 8601 format of last detection attempt
      "location": "MN Hwy 55 at Hwy 100",
      "error_message": null // or "Details about the error if status is 'error'"
    }
  }
  ```
- **Connection Example**:
  - Browser:
    ```javascript
    const streamId = "mn_c550"; // Or get from user input/config
    const wsUrl = `wss://your-service-name.onrender.com/ws/stream/${streamId}`;
    const socket = new WebSocket(wsUrl);
    const videoElement = document.getElementById('videoFeed'); // Assuming an <img> tag
    const detectionElement = document.getElementById('detectionStatus'); // Assuming a <div> or <p> tag

    socket.onopen = () => {
      console.log(`WebSocket connected to stream: ${streamId}`);
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        // Update video frame
        if (data.frame) {
          videoElement.src = `data:image/jpeg;base64,${data.frame}`;
        } else {
          // Handle missing frame (e.g., show placeholder)
          // videoElement.src = 'placeholder.jpg'; 
        }

        // Update detection status
        if (data.detection) {
           const detection = data.detection;
           let statusText = `Status: ${detection.status}, Result: ${detection.result}`;
           if (detection.result === 'accident' && detection.description) {
               statusText += ` | Desc: ${detection.description}`;
           }
           statusText += ` | Location: ${detection.location}`;
           statusText += ` | Time: ${detection.timestamp}`;
           detectionElement.textContent = statusText;
           // Add visual cues based on detection.result (e.g., change background color)
        }

      } catch (error) {
        console.error("Error parsing WebSocket message:", error);
      }
    };

    socket.onerror = (error) => {
        console.error("WebSocket Error:", error);
    };

    socket.onclose = (event) => {
        console.log("WebSocket closed:", event.code, event.reason);
        // Optionally implement reconnection logic here
    };
    ```

## Implementation Details

- **Configuration**: Stream sources are defined in `streams_config.py`.
- **Processing**: Each stream is handled by a separate `VideoStreamProcessor` instance in background threads.
- **Frame Extraction**: Uses `ffmpeg` for HLS streams or downloads static images for fallback sources.
- **Detection**: Uses Together AI LLaMA Vision model. First classifies ('accident'/'no_accident'), then describes if an accident is found.
- **Timing**: 
    - Video frames are streamed via WebSocket at `stream_fps`.
    - Accident detection/description runs independently at `analysis_fps`.
    - The WebSocket message includes the *latest available* frame and the *latest available* detection result.
- **Logging**: General logs go to console. Detected accidents are logged with details to `logs/accidents.log`.