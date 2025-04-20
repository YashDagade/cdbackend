# Configuration for video streams

# Each stream configuration is a dictionary with the following keys:
# - id: A unique identifier string for the stream (used in API routes).
# - url: The M3U8 URL or 'fallback' to use the static fallback images.
# - location: A human-readable description of the camera location.
# - analysis_fps: How many times per second to run accident *detection* (e.g., 1).
# - stream_fps: Deprecated - all streams now fixed at 30 FPS for optimal viewing.

# STREAMS = [
#     {
#         "id": "mn_c550",
#         "url": "https://video.dot.state.mn.us/public/C550.stream/chunklist_w780326163.m3u8",
#         "location": "MN Hwy 55 at Hwy 100",
#         "analysis_fps": 1,  # Check for accidents once per second
#     },
#     {
#         "id": "mn_c214",
#         "url": "https://video.dot.state.mn.us/public/C214.stream/chunklist_w1490925125.m3u8",
#         "location": "MN Hwy 100 at Duluth St",
#         "analysis_fps": 1,
#     },
#     {
#         "id": "mn_c669",
#         "url": "https://video.dot.state.mn.us/public/C669.stream/chunklist_w107499526.m3u8",
#         "location": "MN I-35W at 50th St",
#         "analysis_fps": 1,
#     },
#     {
#         "id": "mn_c030",
#         "url": "https://video.dot.state.mn.us/public/C030.stream/chunklist_w765268921.m3u8",
#         "location": "MN I-94 at Riverside Ave",
#         "analysis_fps": 1,
#     },
#     # Example fallback stream (uncomment and update if needed)
#     # {
#     #     "id": "fallback_example",
#     #     "url": "fallback",  # Use the static fallback images defined in stream_processor.py
#     #     "location": "Fallback Test Camera",
#     #     "analysis_fps": 1,
#     # },
# ]


# Configuration for video streams

STREAMS = [
    {
        "id": "demo_crash1",
        "url": "https://cdbackend-demo-1v9lrpi39-yashdagades-projects.vercel.app/crash1/crash1.m3u8",
        "location": "Demo Crash Clip 1",
        "analysis_fps": 1,
    },
    # {
    #     "id": "demo_crash2",
    #     "url": "https://cdbackend-demo-1v9lrpi39-yashdagades-projects.vercel.app/crash2/crash2.m3u8",
    #     "location": "Demo Crash Clip 2",
    #     "analysis_fps": 1,
    # },
    # {
    #     "id": "demo_crash3",
    #     "url": "https://cdbackend-demo-1v9lrpi39-yashdagades-projects.vercel.app/crash3/crash3.m3u8",
    #     "location": "Demo Crash Clip 3",
    #     "analysis_fps": 1,
    # },
    {
        "id": "demo_crash4",
        "url": "https://cdbackend-demo-1v9lrpi39-yashdagades-projects.vercel.app/crash4/crash4.m3u8",
        "location": "Demo Crash Clip 4",
        "analysis_fps": 1,
    },
]