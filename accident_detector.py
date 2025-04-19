import os
import subprocess
import base64
import time
import threading
from together import Together
from pathlib import Path

# Your HLS URL (master or media playlist)
VIDEO_SOURCE = "https://511mn.org/path/to/your/chunklist_w872956871.m3u8"

# Initialize Together client once
together_client = Together(api_key=os.environ.get("TOGETHER_API_KEY", "00cc911924ea837d3ce1d2209d6c03de690ce4757edb8edabff68bbf681b42a6"))
PROMPT = (
    "You are a police detective. "
    "Classify the attached image as exactly one word: 'accident' or 'no accident'."
)

# Frame extraction settings
ANALYSIS_FPS = 5  # Rate for accident detection
VIDEO_FPS = 30    # Rate for video streaming
FRAMES_DIR = "frames"

# Create frames directory
os.makedirs(FRAMES_DIR, exist_ok=True)
CURRENT_FRAME_PATH = f"{FRAMES_DIR}/current_frame.jpg"

# Flag to track if frame extraction is running
extraction_running = False
last_frame_time = 0
last_result = "no accident"
last_frame_data = None
last_frame_base64 = None

def start_frame_extraction():
    """
    Start ffmpeg process to continuously extract frames from the stream
    """
    global extraction_running
    
    if extraction_running:
        return
    
    extraction_running = True
    
    # Use ffmpeg to continuously update a single image file at high FPS
    cmd = [
        "ffmpeg",
        "-i", VIDEO_SOURCE,
        "-vf", f"fps={VIDEO_FPS}",
        "-q:v", "2",  # JPEG quality (2 is high quality)
        "-update", "1",
        "-y", CURRENT_FRAME_PATH
    ]
    
    # Run in a separate thread to not block the main process
    def run_ffmpeg():
        try:
            subprocess.run(cmd, stderr=subprocess.PIPE)
        except Exception as e:
            print(f"Error in frame extraction: {e}")
        finally:
            global extraction_running
            extraction_running = False
    
    threading.Thread(target=run_ffmpeg, daemon=True).start()
    print(f"Started frame extraction from {VIDEO_SOURCE} at {VIDEO_FPS} FPS")

def get_current_frame():
    """
    Get the current frame as base64 for streaming purposes
    """
    global last_frame_data, last_frame_base64
    
    try:
        frame_path = Path(CURRENT_FRAME_PATH)
        
        if not frame_path.exists():
            if last_frame_base64:
                return last_frame_base64
            return None
        
        # Get the modification time of the frame file
        mod_time = frame_path.stat().st_mtime
        
        # If we already have the latest frame, return the cached version
        if last_frame_data and mod_time <= last_frame_time:
            return last_frame_base64
        
        # Read the new frame and update cache
        with open(CURRENT_FRAME_PATH, "rb") as img_file:
            last_frame_data = img_file.read()
            last_frame_base64 = base64.b64encode(last_frame_data).decode('utf-8')
            last_frame_time = mod_time
            return last_frame_base64
            
    except Exception as e:
        print(f"Error getting current frame: {e}")
        return last_frame_base64

def detect_frame_accident():
    """
    Read the current frame, send to Together, return 'accident' or 'no accident'.
    """
    global last_result
    
    # Start frame extraction if not already running
    if not extraction_running:
        start_frame_extraction()
        # Give ffmpeg a moment to start producing frames
        time.sleep(1)
    
    # Get latest frame as base64
    img_b64 = get_current_frame()
    if not img_b64:
        print("No frame available yet")
        return last_result
    
    try:
        # Call the Together Vision model (sync)
        response = together_client.chat.completions.create(
            model="meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo",
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                ]}
            ],
            stream=False
        )
        
        # Extract and normalize reply
        text = response.choices[0].message.content.strip().lower()
        last_result = text if text in ("accident", "no accident") else "no accident"
        return last_result
        
    except Exception as e:
        print(f"Error processing frame: {e}")
        return last_result 
