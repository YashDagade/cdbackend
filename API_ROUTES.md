# API Routes Documentation

This document outlines all available API endpoints for the Real-Time Multi-Stream Accident Detector service.

## Base URL

- **Local Development**: `http://localhost:8000` (or port specified when running uvicorn)
- **Production**: `https://cdbackend.onrender.com`

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
  curl https://cdbackend.onrender.com/
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
  curl https://cdbackend.onrender.com/streams
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
  curl https://cdbackend.onrender.com/stream/mn_c550/frame
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
      "result": "safe", // or "accident"
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
  curl https://cdbackend.onrender.com/stream/mn_c550/detect
  ```

## WebSocket Endpoints

### Frame Stream Endpoint (Video Only)

- **URL**: `/ws/stream/{stream_id}`
- **WebSocket Protocol**: `ws://` (local) or `wss://` (production)
- **Path Parameter**: `stream_id` (string, required) - The ID of the stream to connect to.
- **Description**: Establishes a WebSocket connection for receiving video frames only. The server pushes frames at approximately 30 FPS without any accident detection data.
- **Message Format (Server -> Client)**: JSON object
  ```json
  {
    "type": "frame",
    "stream_id": "mn_c550",
    "frame": "/9j/4AAQSkZJRgABAQE... (base64 encoded image data)"
  }
  ```
- **Use Case**: High-performance video display without the overhead of detection data. Perfect for real-time monitoring displays.

### Accident Analysis Endpoint (Alerts Only)

- **URL**: `/ws/analyze/{stream_id}`
- **WebSocket Protocol**: `ws://` (local) or `wss://` (production)
- **Path Parameter**: `stream_id` (string, required) - The ID of the stream to connect to.
- **Description**: Establishes a WebSocket connection for receiving accident alerts only. The server only pushes a message when an accident is detected.
- **Message Format (Server -> Client)**: JSON object
  ```json
  // Initial connection status message
  {
    "type": "status",
    "stream_id": "mn_c550",
    "message": "Connected to accident alert stream",
    "timestamp": 1698408778.123
  }
  
  // Accident alert message
  {
    "type": "accident_alert",
    "stream_id": "mn_c550",
    "timestamp": "2023-10-27T10:30:00.123456+00:00",
    "location": "MN Hwy 55 at Hwy 100",
    "description": "Daytime: A white sedan appears to have rear-ended a blue SUV on the highway shoulder.",
    "frame": "/9j/4AAQSkZJRgABAQE... (base64 encoded image of the accident)"
  }
  ```
- **Use Case**: Receiving accident notifications only, without the overhead of constant video frames. Perfect for alerting systems, dashboard displays, or mobile notifications.

### Legacy Combined Stream Endpoint (For Backward Compatibility)

- **URL**: `/ws/combined/{stream_id}`
- **WebSocket Protocol**: `ws://` (local) or `wss://` (production)
- **Path Parameter**: `stream_id` (string, required) - The ID of the stream to connect to.
- **Description**: The original WebSocket endpoint that combines both video frames and detection results in each message. Maintained for backward compatibility.
- **Message Format (Server -> Client)**: JSON object
  ```json
  {
    "frame": "/9j/4AAQSkZJRgABAQE... (base64 encoded image data or null)",
    "detection": {
      "status": "success", // "initializing", "no_frame", "error"
      "result": "safe", // or "accident"
      "description": null, // or "Brief description..."
      "timestamp": "2023-10-27T10:30:00.123456+00:00", // ISO 8601 format of last detection attempt
      "location": "MN Hwy 55 at Hwy 100",
      "error_message": null // or "Details about the error if status is 'error'"
    }
  }
  ```
- **Note**: This endpoint runs at approximately 10 FPS rather than the full 30 FPS of the dedicated frame stream endpoint.

## Client Implementation Example

For an example of how to implement both WebSocket endpoints simultaneously, see the `dual_client_example.html` file in the repository.

## Implementation Details

- **Configuration**: Stream sources are defined in `streams_config.py`.
- **Processing**: Each stream is handled by a separate `VideoStreamProcessor` instance in background threads.
- **Frame Extraction**: Uses `ffmpeg` for HLS streams or downloads static images for fallback sources.
- **Detection**: Uses Together AI LLaMA Vision model. First classifies ('accident'/'safe'), then describes if an accident is found.
- **Analysis Architecture**: 
    - Each processor uses a queue with multiple worker threads to analyze frames without blocking.
    - Frames are fed into the analysis queue periodically (according to configured `analysis_fps`).
    - When an accident is detected, it's added to a broadcast queue for notification.
- **Timing**: 
    - Video frames are streamed via `/ws/stream` at 30 FPS.
    - Accident detection runs at the configured `analysis_fps` in the background.
    - Accident alerts are sent on `/ws/analyze` only when an accident is detected.
- **Logging**: General logs go to console. Detected accidents are logged with details to `logs/accidents.log`.