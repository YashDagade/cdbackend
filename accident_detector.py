import os
import subprocess
import base64
import time
import threading
import requests
from together import Together
from pathlib import Path
import urllib.request
import random
import json

# Your HLS URL from Minnesota DOT
VIDEO_SOURCE = "https://video.dot.state.mn.us/public/C550.stream/chunklist_w780326163.m3u8"

# Fallback video sources (public traffic cameras for testing)
FALLBACK_SOURCES = [
    "https://511ev.org/cameras/latest/R1_167_St_Louis_River.jpg",
    "https://511ev.org/cameras/latest/R1_21_Thompson_Hill.jpg",
    "https://511ev.org/cameras/latest/R1_13_Mesaba.jpg",
    "https://511ev.org/cameras/latest/R1_172_North_Shore.jpg"
]

# Initialize Together client once
together_client = Together(api_key=os.environ.get("TOGETHER_API_KEY", "00cc911924ea837d3ce1d2209d6c03de690ce4757edb8edabff68bbf681b42a6"))
PROMPT = (
    "You are a police detective. "
    "Classify the attached image as exactly one word: 'accident' or 'no accident'."
)

# Frame extraction settings
ANALYSIS_FPS = 5  # Rate for accident detection
VIDEO_FPS = 10    # Rate for video streaming (reduced to conserve bandwidth)
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
use_fallback = False
fallback_index = 0

def validate_m3u8_url():
    """
    Validate that the M3U8 URL is accessible
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
        }
        response = requests.head(VIDEO_SOURCE, headers=headers, timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"Error validating M3U8 URL: {e}")
        return False

def get_fallback_frame():
    """
    Download a frame from fallback source when HLS stream is unavailable
    """
    global fallback_index
    
    # Rotate through fallback sources
    source = FALLBACK_SOURCES[fallback_index % len(FALLBACK_SOURCES)]
    fallback_index += 1
    
    try:
        # Add a random parameter to avoid caching
        url = f"{source}?nocache={int(time.time())}"
        print(f"Downloading fallback frame from: {url}")
        
        # Download the image
        urllib.request.urlretrieve(url, CURRENT_FRAME_PATH)
        return True
    except Exception as e:
        print(f"Error downloading fallback frame: {e}")
        return False

def start_frame_extraction():
    """
    Start ffmpeg process to continuously extract frames from the stream
    """
    global extraction_running, use_fallback
    
    if extraction_running:
        return
    
    extraction_running = True
    
    # Check if the M3U8 URL is valid
    if not use_fallback and validate_m3u8_url():
        try:
            # Use ffmpeg to continuously update a single image file at high FPS
            cmd = [
                "ffmpeg",
                "-headers", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "-protocol_whitelist", "file,http,https,tcp,tls",
                "-i", VIDEO_SOURCE,
                "-vf", f"fps={VIDEO_FPS}",
                "-q:v", "2",  # JPEG quality (2 is high quality)
                "-update", "1",
                "-y", CURRENT_FRAME_PATH
            ]
            
            # Run in a separate thread to not block the main process
            def run_ffmpeg():
                try:
                    print(f"Starting ffmpeg with command: {' '.join(cmd)}")
                    result = subprocess.run(cmd, stderr=subprocess.PIPE)
                    # If ffmpeg fails, switch to fallback
                    if result.returncode != 0:
                        global use_fallback
                        use_fallback = True
                        print(f"ffmpeg failed, switching to fallback. Error: {result.stderr.decode('utf-8')}")
                except Exception as e:
                    print(f"Error in frame extraction: {e}")
                    use_fallback = True
                finally:
                    global extraction_running
                    extraction_running = False
            
            threading.Thread(target=run_ffmpeg, daemon=True).start()
            print(f"Started frame extraction from {VIDEO_SOURCE} at {VIDEO_FPS} FPS")
            return
        except Exception as e:
            print(f"Failed to start ffmpeg: {e}")
            use_fallback = True
    else:
        use_fallback = True
    
    # If we're here, use the fallback method
    if use_fallback:
        def fallback_loop():
            try:
                while True:
                    success = get_fallback_frame()
                    if not success:
                        print("Failed to get fallback frame, retrying...")
                    time.sleep(1.0 / VIDEO_FPS)  # Maintain requested FPS
            except Exception as e:
                print(f"Error in fallback loop: {e}")
            finally:
                global extraction_running
                extraction_running = False
        
        threading.Thread(target=fallback_loop, daemon=True).start()
        print(f"Started fallback frame extraction at {VIDEO_FPS} FPS")

def get_current_frame():
    """
    Get the current frame as base64 for streaming purposes
    """
    global last_frame_data, last_frame_base64, last_frame_time
    
    try:
        frame_path = Path(CURRENT_FRAME_PATH)
        
        if not frame_path.exists():
            if last_frame_base64:
                return last_frame_base64
            
            # Try to get a fallback frame since none exists
            if get_fallback_frame():
                # Continue with the newly created file
                if not frame_path.exists():
                    return None
            else:
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
        # Give it a moment to start producing frames
        time.sleep(1)
    
    # Get latest frame as base64
    img_b64 = get_current_frame()
    if not img_b64:
        print("No frame available yet")
        return json.dumps({"status": "error", "message": "No frame available", "result": last_result})
    
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
        result = "accident" if "accident" in text and "no accident" not in text else "no accident"
        last_result = result
        
        return json.dumps({
            "status": "success",
            "result": result,
            "original_response": text
        })
        
    except Exception as e:
        print(f"Error processing frame: {e}")
        return json.dumps({
            "status": "error",
            "message": str(e),
            "result": last_result
        }) 
