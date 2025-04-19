# Configuration for video streams

# Each stream configuration is a dictionary with the following keys:
# - id: A unique identifier string for the stream (used in API routes).
# - url: The M3U8 URL or 'fallback' to use the static fallback images.
# - location: A human-readable description of the camera location.
# - analysis_fps: How many times per second to run accident *detection* (e.g., 5).
# - stream_fps: How many times per second to *stream* video frames (e.g., 10).

STREAMS = [
    {
        "id": "mn_c550",
        "url": "https://video.dot.state.mn.us/public/C550.stream/chunklist_w780326163.m3u8",
        "location": "MN Hwy 55 at Hwy 100",
        "analysis_fps": 5,  # Analyze 5 times per second
        "stream_fps": 10    # Stream video at 10 FPS
    },
    # {
    #     "id": "fallback_example",
    #     "url": "fallback", # Use the static fallback images defined in stream_processor.py
    #     "location": "Fallback Test Camera",
    #     "analysis_fps": 1,
    #     "stream_fps": 1
    # },
    # Add more stream configurations here if needed
] 