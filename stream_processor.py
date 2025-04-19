import os
import subprocess
import base64
import time
import threading
import requests
import json
import logging
import datetime
from pathlib import Path
import urllib.request
import random
from together import Together

# --- Logging Setup ---
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Console Handler (for general logs)
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

# File Handler (for accident logs)
os.makedirs("logs", exist_ok=True)
accident_log_handler = logging.FileHandler("logs/accidents.log")
accident_log_handler.setFormatter(log_formatter)

# Main logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(console_handler)
logger.propagate = False # Prevent double logging in root logger

# Specific logger for accidents
accident_logger = logging.getLogger("AccidentLog")
accident_logger.setLevel(logging.INFO)
accident_logger.addHandler(accident_log_handler)
accident_logger.addHandler(console_handler) # Also log accidents to console
accident_logger.propagate = False

# --- Together AI Client & Prompts ---
together_client = Together(api_key=os.environ.get("TOGETHER_API_KEY"))

CLASSIFICATION_PROMPT = (
    "You are an automated traffic monitoring system. Classify the attached image based ONLY on whether a vehicle accident is visible. "
    "Respond with exactly one word: 'accident' or 'no_accident'."
)
DESCRIPTION_PROMPT = (
    "An accident has been detected in the attached image. Provide a brief, factual description of the accident scene, "
    "focusing on the vehicles involved and their apparent situation. Include the approximate time based on lighting if possible (e.g., daytime, nighttime). "
    "Limit the description to 1-2 sentences. Example: 'Daytime: A white sedan appears to have rear-ended a blue SUV on the highway shoulder.'"
)

# --- Fallback Sources --- (Used if stream_config['url'] == 'fallback')
FALLBACK_SOURCES = [
    "https://511ev.org/cameras/latest/R1_167_St_Louis_River.jpg",
    "https://511ev.org/cameras/latest/R1_21_Thompson_Hill.jpg",
    "https://511ev.org/cameras/latest/R1_13_Mesaba.jpg",
    "https://511ev.org/cameras/latest/R1_172_North_Shore.jpg"
]

class VideoStreamProcessor:
    def __init__(self, stream_config):
        self.config = stream_config
        self.stream_id = stream_config['id']
        self.location = stream_config['location']
        self.stream_url = stream_config['url']
        self.analysis_interval = 1.0 / stream_config['analysis_fps']
        self.stream_interval = 1.0 / stream_config['stream_fps']
        self.frames_dir = Path(f"frames/{self.stream_id}")
        self.current_frame_path = self.frames_dir / "current_frame.jpg"

        self.frames_dir.mkdir(parents=True, exist_ok=True)

        self.latest_frame_base64 = None
        self.latest_frame_time = 0
        self.latest_detection_result = {
            "status": "initializing",
            "result": "no_accident",
            "description": None,
            "timestamp": None,
            "location": self.location
        }
        self.use_fallback_source = (self.stream_url == 'fallback')
        self.fallback_index = 0

        self._stop_event = threading.Event()
        self._frame_extractor_thread = None
        self._detector_thread = None
        self._ffmpeg_process = None

    def _validate_m3u8_url(self):
        if self.use_fallback_source:
            return False # No URL to validate for fallback
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
            }
            response = requests.head(self.stream_url, headers=headers, timeout=5)
            logger.info(f"[{self.stream_id}] M3U8 URL validation status: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"[{self.stream_id}] Error validating M3U8 URL '{self.stream_url}': {e}")
            return False

    def _get_fallback_frame(self):
        source = FALLBACK_SOURCES[self.fallback_index % len(FALLBACK_SOURCES)]
        self.fallback_index += 1
        try:
            url = f"{source}?nocache={int(time.time())}"
            #logger.debug(f"[{self.stream_id}] Downloading fallback frame from: {url}")
            urllib.request.urlretrieve(url, self.current_frame_path)
            return True
        except Exception as e:
            logger.error(f"[{self.stream_id}] Error downloading fallback frame: {e}")
            return False

    def _run_ffmpeg(self):
        cmd = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "error", # Reduce verbosity
            "-headers", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "-protocol_whitelist", "file,http,https,tcp,tls",
            "-i", self.stream_url,
            "-vf", f"fps={self.config['stream_fps']}", # Use stream_fps for output
            "-q:v", "2",
            "-update", "1",
            "-y", str(self.current_frame_path)
        ]
        logger.info(f"[{self.stream_id}] Starting ffmpeg: {' '.join(cmd)}")
        try:
            # Start the process without waiting for it to complete
            self._ffmpeg_process = subprocess.Popen(cmd, stderr=subprocess.PIPE)

            # Monitor the process in case it exits unexpectedly
            stderr_output = self._ffmpeg_process.communicate()[1] # Wait and get stderr
            if self._ffmpeg_process.returncode != 0 and not self._stop_event.is_set():
                 logger.error(f"[{self.stream_id}] ffmpeg process exited unexpectedly with code {self._ffmpeg_process.returncode}. Error: {stderr_output.decode('utf-8', errors='ignore')}")
                 self.use_fallback_source = True # Attempt to switch to fallback
            elif not self._stop_event.is_set():
                logger.warning(f"[{self.stream_id}] ffmpeg process exited cleanly but unexpectedly.")
        except Exception as e:
            logger.error(f"[{self.stream_id}] Failed to start or run ffmpeg: {e}")
            self.use_fallback_source = True # Switch to fallback if ffmpeg fails to start
        finally:
             self._ffmpeg_process = None # Clear process handle
             logger.info(f"[{self.stream_id}] ffmpeg process stopped.")

    def _fallback_loop(self):
        logger.info(f"[{self.stream_id}] Starting fallback frame loop.")
        while not self._stop_event.is_set():
            if not self._get_fallback_frame():
                logger.warning(f"[{self.stream_id}] Failed to get fallback frame, retrying...")
            time.sleep(self.stream_interval) # Sleep according to stream FPS
        logger.info(f"[{self.stream_id}] Fallback frame loop stopped.")

    def _start_frame_extraction_thread(self):
        if self.use_fallback_source or not self._validate_m3u8_url():
            logger.warning(f"[{self.stream_id}] Using fallback image source.")
            self.use_fallback_source = True
            self._frame_extractor_thread = threading.Thread(target=self._fallback_loop, daemon=True)
        else:
            logger.info(f"[{self.stream_id}] Using M3U8 stream source: {self.stream_url}")
            self._frame_extractor_thread = threading.Thread(target=self._run_ffmpeg, daemon=True)
        
        self._frame_extractor_thread.start()

    def _detect_loop(self):
        logger.info(f"[{self.stream_id}] Starting detection loop (interval: {self.analysis_interval:.2f}s)." )
        while not self._stop_event.is_set():
            start_time = time.monotonic()
            frame_b64 = self.get_latest_frame_base64()
            if frame_b64:
                self._run_detection(frame_b64)
            else:
                 self.latest_detection_result['status'] = "no_frame"
                 # logger.warning(f"[{self.stream_id}] No frame available for detection.")
                 pass # Keep status as is if no frame

            # Calculate sleep time to maintain desired analysis FPS
            elapsed = time.monotonic() - start_time
            sleep_time = max(0, self.analysis_interval - elapsed)
            time.sleep(sleep_time)
        logger.info(f"[{self.stream_id}] Detection loop stopped.")

    def _run_detection(self, img_b64):
        current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            # --- Step 1: Classification --- 
            response = together_client.chat.completions.create(
                model="meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo",
                messages=[
                    {"role": "user", "content": [
                        {"type": "text", "text": CLASSIFICATION_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                    ]}
                ],
                max_tokens=10,
                temperature=0.1, # Low temp for classification
                stream=False
            )
            classification_text = response.choices[0].message.content.strip().lower()
            result = "accident" if "accident" in classification_text else "no_accident"
            
            # Update status immediately after classification
            self.latest_detection_result = {
                "status": "success",
                "result": result,
                "description": None, # Reset description
                "timestamp": current_time,
                "location": self.location
            }

            # --- Step 2: Description (if accident) --- 
            if result == "accident":
                try:
                    desc_response = together_client.chat.completions.create(
                        model="meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo",
                        messages=[
                            {"role": "user", "content": [
                                {"type": "text", "text": DESCRIPTION_PROMPT},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                            ]}
                        ],
                         max_tokens=100,
                         temperature=0.7, # Higher temp for creative description
                         stream=False
                    )
                    description = desc_response.choices[0].message.content.strip()
                    self.latest_detection_result["description"] = description
                    
                    # Log the accident details
                    accident_logger.info(f"Accident Detected - Stream: {self.stream_id}, Location: {self.location}, Time: {current_time}, Description: {description}")
                
                except Exception as desc_e:
                    logger.error(f"[{self.stream_id}] Error getting accident description: {desc_e}")
                    self.latest_detection_result["description"] = "Error generating description."
                    # Still log the accident was detected
                    accident_logger.warning(f"Accident Detected - Stream: {self.stream_id}, Location: {self.location}, Time: {current_time}, Description: <Error> - {desc_e}")

            # logger.debug(f"[{self.stream_id}] Detection result: {self.latest_detection_result['result']}")

        except Exception as e:
            logger.error(f"[{self.stream_id}] Error during Together AI call: {e}")
            self.latest_detection_result = {
                 "status": "error",
                 "result": "no_accident", # Default to no_accident on error
                 "description": None,
                 "timestamp": current_time,
                 "location": self.location,
                 "error_message": str(e)
            }

    def get_latest_frame_base64(self):
        try:
            if not self.current_frame_path.exists():
                # Return last known frame if current doesn't exist yet
                return self.latest_frame_base64 

            mod_time = self.current_frame_path.stat().st_mtime

            # Check if frame is new
            if mod_time > self.latest_frame_time:
                with open(self.current_frame_path, "rb") as img_file:
                    frame_data = img_file.read()
                    self.latest_frame_base64 = base64.b64encode(frame_data).decode('utf-8')
                    self.latest_frame_time = mod_time
            
            # Return the latest frame (could be old or new)
            return self.latest_frame_base64

        except FileNotFoundError:
             logger.warning(f"[{self.stream_id}] Frame file not found: {self.current_frame_path}")
             return self.latest_frame_base64 # Return last known frame
        except Exception as e:
            logger.error(f"[{self.stream_id}] Error getting current frame: {e}")
            return self.latest_frame_base64 # Return last known frame

    def get_latest_data(self):
        """Returns the latest frame and detection data combined."""
        return {
            "frame": self.get_latest_frame_base64(),
            "detection": self.latest_detection_result
        }

    def start(self):
        logger.info(f"[{self.stream_id}] Starting video stream processor...")
        self._stop_event.clear()
        self._start_frame_extraction_thread()
        # Give frame extractor a moment to start
        time.sleep(1)
        self._detector_thread = threading.Thread(target=self._detect_loop, daemon=True)
        self._detector_thread.start()
        logger.info(f"[{self.stream_id}] Video stream processor started.")

    def stop(self):
        logger.info(f"[{self.stream_id}] Stopping video stream processor...")
        self._stop_event.set()

        # Stop ffmpeg process if running
        if self._ffmpeg_process:
            try:
                logger.info(f"[{self.stream_id}] Terminating ffmpeg process...")
                self._ffmpeg_process.terminate() # Send SIGTERM
                self._ffmpeg_process.wait(timeout=5) # Wait a bit for clean exit
            except subprocess.TimeoutExpired:
                logger.warning(f"[{self.stream_id}] ffmpeg did not terminate gracefully, killing...")
                self._ffmpeg_process.kill() # Force kill
            except Exception as e:
                 logger.error(f"[{self.stream_id}] Error stopping ffmpeg: {e}")
            finally:
                 self._ffmpeg_process = None

        # Wait for threads to finish
        if self._frame_extractor_thread and self._frame_extractor_thread.is_alive():
            logger.debug(f"[{self.stream_id}] Waiting for frame extractor thread...")
            self._frame_extractor_thread.join(timeout=5)
        if self._detector_thread and self._detector_thread.is_alive():
            logger.debug(f"[{self.stream_id}] Waiting for detector thread...")
            self._detector_thread.join(timeout=5)
        
        logger.info(f"[{self.stream_id}] Video stream processor stopped.")

# Cleanup function to delete old frame directories (optional)
def cleanup_frame_dirs(base_dir="frames"):
     base_path = Path(base_dir)
     if base_path.exists():
         for item in base_path.iterdir():
             if item.is_dir():
                 try:
                     # Basic cleanup: remove the directory and its contents
                     # In a real scenario, might want more sophisticated cleanup
                     # shutil.rmtree(item)
                     logger.info(f"Would delete frame directory: {item}") # Placeholder
                 except Exception as e:
                     logger.error(f"Error cleaning up directory {item}: {e}") 