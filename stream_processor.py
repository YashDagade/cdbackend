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
from queue import Queue, Empty

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
    "Traffic cameras rarely capture accidents - most views show normal traffic flow. Only identify an accident when there is clear evidence "
    "of a collision, vehicle damage, or unusual positioning of vehicles on the road. "
    "Respond with exactly one word: 'accident' or 'safe'."
)
DESCRIPTION_PROMPT = (
    "An accident has been detected in the attached image. Provide a brief, factual description of the accident scene, "
    "focusing on the vehicles involved and their apparent situation. Include the approximate time based on lighting if possible (e.g., daytime, nighttime). "
    "Limit the description to 1-2 sentences. Example: 'Daytime: A white sedan appears to have rear-ended a blue SUV on the highway shoulder.'"
)

# --- Fallback Sources --- (Used if stream_config['url'] == 'fallback')
FALLBACK_SOURCES = [
    "https://511ev.org/cameras/CAM106/latest.jpg",
    "https://traffic.511mn.org/cameras/CAM108/latest.jpg",
    "https://traffic.511mn.org/cameras/CAM110/latest.jpg",
    "https://traffic.511mn.org/cameras/CAM112/latest.jpg"
]

class VideoStreamProcessor:
    def __init__(self, stream_config):
        self.config = stream_config
        self.stream_id = stream_config['id']
        self.location = stream_config['location']
        self.stream_url = stream_config['url']
        self.analysis_interval = 1.0 / stream_config['analysis_fps']
        # For backward compatibility - stream_fps is now fixed at 30 FPS
        self.stream_interval = 1.0 / 30.0  # Fixed 30 FPS for all streams
        self.frames_dir = Path(f"frames/{self.stream_id}")
        self.current_frame_path = self.frames_dir / "current_frame.jpg"

        self.frames_dir.mkdir(parents=True, exist_ok=True)

        self.latest_frame_base64 = None
        self.latest_frame_time = 0
        
        # For backward compatibility
        self.latest_detection_result = {
            "status": "initializing",
            "result": "safe",
            "description": None,
            "timestamp": None,
            "location": self.location
        }
        
        self.use_fallback_source = (self.stream_url == 'fallback')
        self.fallback_index = 0

        # New queue-based system
        self.analysis_queue = Queue()
        self.broadcast_queue = Queue()
        self.analysis_clients = set()
        self.analyze_threads = []
        
        self._stop_event = threading.Event()
        self._frame_extractor_thread = None
        self._analysis_feed_thread = None
        self._ffmpeg_process = None

    def _validate_m3u8_url(self):
        if self.use_fallback_source:
            return False # No URL to validate for fallback
        try:
            # More lenient validation - just check if URL returns any valid response
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
            }
            response = requests.get(self.stream_url, headers=headers, timeout=5)
            logger.info(f"[{self.stream_id}] M3U8 URL validation status: {response.status_code}")
            # Accept any 2xx or 3xx status code as valid
            return response.status_code < 400
        except Exception as e:
            logger.error(f"[{self.stream_id}] Error validating M3U8 URL '{self.stream_url}': {e}")
            return False

    def _get_fallback_frame(self):
        source = FALLBACK_SOURCES[self.fallback_index % len(FALLBACK_SOURCES)]
        self.fallback_index += 1
        try:
            url = f"{source}?nocache={int(time.time())}"
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
            "-vf", f"fps={30}", # Fixed 30 FPS for stream endpoint
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
            time.sleep(1.0 / 30.0)  # 30 FPS for consistent streaming
        logger.info(f"[{self.stream_id}] Fallback frame loop stopped.")

    def _start_frame_extraction_thread(self):
        # Only use fallback if explicitly configured that way
        if self.use_fallback_source:
            logger.warning(f"[{self.stream_id}] Using fallback image source.")
            self._frame_extractor_thread = threading.Thread(target=self._fallback_loop, daemon=True)
        else:
            # Try ffmpeg directly without validation - let ffmpeg handle connectivity
            logger.info(f"[{self.stream_id}] Using M3U8 stream source: {self.stream_url}")
            self._frame_extractor_thread = threading.Thread(target=self._run_ffmpeg, daemon=True)
        
        self._frame_extractor_thread.start()

    def _periodically_feed_analysis(self):
        """Feed frames to the analysis queue at regular intervals"""
        logger.info(f"[{self.stream_id}] Starting analysis feed loop (interval: {self.analysis_interval:.2f}s).")
        while not self._stop_event.is_set():
            start_time = time.monotonic()
            frame_b64 = self.get_latest_frame_base64()
            if frame_b64:
                # Only add if queue isn't too large to prevent memory issues
                if self.analysis_queue.qsize() < 5:
                    self.analysis_queue.put(frame_b64)
            
            # Calculate sleep time to maintain desired analysis feed rate
            elapsed = time.monotonic() - start_time
            sleep_time = max(0, self.analysis_interval - elapsed)
            time.sleep(sleep_time)
        logger.info(f"[{self.stream_id}] Analysis feed loop stopped.")

    def _analyze_worker(self):
        """Worker thread that processes frames from the analysis queue"""
        logger.info(f"[{self.stream_id}] Starting analysis worker thread.")
        while not self._stop_event.is_set():
            try:
                # Get frame with timeout to allow checking stop_event periodically
                try:
                    frame_b64 = self.analysis_queue.get(timeout=1.0)
                except Empty:
                    continue
                
                # Perform accident detection
                result = self.detect_accident(frame_b64)
                
                # Update legacy detection result for backward compatibility
                current_time = datetime.datetime.utcnow().isoformat()
                self.latest_detection_result = {
                    "status": "success",
                    "result": result,
                    "description": None,
                    "timestamp": current_time,
                    "location": self.location
                }
                
                # If accident detected, get description and broadcast alert
                if result == "accident":
                    description = self.describe_accident(frame_b64)
                    self.latest_detection_result["description"] = description
                    
                    # Create message for analysis clients
                    message = {
                        "type": "accident_alert",
                        "stream_id": self.stream_id,
                        "timestamp": current_time,
                        "location": self.location,
                        "description": description,
                        "frame": frame_b64  # Include the frame that triggered the alert
                    }
                    
                    # Add to broadcast queue
                    self.broadcast_queue.put(message)
                    
                    # Log the accident
                    accident_logger.info(f"Accident Detected - Stream: {self.stream_id}, Location: {self.location}, Time: {current_time}, Description: {description}")
                
            except Exception as e:
                logger.error(f"[{self.stream_id}] Error in analysis worker: {e}", exc_info=True)
        
        logger.info(f"[{self.stream_id}] Analysis worker thread stopped.")

    def detect_accident(self, img_b64):
        """Detect if an accident is present in the image."""
        try:
            response = together_client.chat.completions.create(
                model="meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo",
                messages=[
                    {"role": "user", "content": [
                        {"type": "text", "text": CLASSIFICATION_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                    ]}
                ],
                max_tokens=15,
                temperature=0.1,  # Low temp for classification
                stream=False
            )
            classification_text = response.choices[0].message.content.strip().lower()
            return "safe" if "safe" in classification_text else "accident"
        except Exception as e:
            logger.error(f"[{self.stream_id}] Error during accident detection: {e}")
            return "safe"  # Default to safe on error

    def describe_accident(self, img_b64):
        """Generate a description for a detected accident."""
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
                temperature=0.7,  # Higher temp for creative description
                stream=False
            )
            return desc_response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"[{self.stream_id}] Error getting accident description: {e}")
            return "Error generating description."

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
        """Returns the latest frame and detection data combined (for backward compatibility)."""
        return {
            "frame": self.get_latest_frame_base64(),
            "detection": self.latest_detection_result
        }

    def start_analysis_workers(self, num_threads=2):
        """Start multiple analysis worker threads."""
        for i in range(num_threads):
            thread = threading.Thread(target=self._analyze_worker, daemon=True)
            thread.start()
            self.analyze_threads.append(thread)
            logger.info(f"[{self.stream_id}] Started analysis worker thread #{i+1}")

    def start(self):
        logger.info(f"[{self.stream_id}] Starting video stream processor...")
        self._stop_event.clear()
        
        # Start frame extraction
        self._start_frame_extraction_thread()
        
        # Give frame extractor a moment to start
        time.sleep(1)
        
        # Start analysis feed thread
        self._analysis_feed_thread = threading.Thread(target=self._periodically_feed_analysis, daemon=True)
        self._analysis_feed_thread.start()
        
        # Start analysis worker threads
        self.start_analysis_workers(2)  # Start 2 worker threads
        
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
        
        if self._analysis_feed_thread and self._analysis_feed_thread.is_alive():
            logger.debug(f"[{self.stream_id}] Waiting for analysis feed thread...")
            self._analysis_feed_thread.join(timeout=5)
        
        # Wait for all analysis worker threads
        for i, thread in enumerate(self.analyze_threads):
            if thread.is_alive():
                logger.debug(f"[{self.stream_id}] Waiting for analysis worker thread #{i+1}...")
                thread.join(timeout=5)
        
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