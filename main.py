import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from collections import defaultdict

# Import configurations and the processor
from streams_config import STREAMS
from stream_processor import VideoStreamProcessor

# --- Logging Setup ---
# Basic logging setup (can be enhanced)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Global State ---
# Dictionary to hold stream processor instances, keyed by stream_id
stream_processors = {}
# Dictionary to hold active WebSocket connections for each stream_id
# Structure: {stream_id: {websocket1, websocket2, ...}}
active_connections = defaultdict(set)
# Background broadcast task reference
broadcast_task = None

# --- Helper Functions ---
def get_stream_processor(stream_id: str) -> VideoStreamProcessor:
    processor = stream_processors.get(stream_id)
    if not processor:
        raise HTTPException(status_code=404, detail=f"Stream '{stream_id}' not found.")
    return processor

# --- Background Task ---
async def stream_broadcast_loop():
    """Continuously broadcast latest data for all streams to subscribed clients."""
    # Determine the fastest stream interval needed for the loop timing
    min_interval = 0.1 # Default minimum interval (10 FPS)
    if stream_processors:
        min_interval = min(p.stream_interval for p in stream_processors.values() if p.stream_interval > 0)
        min_interval = max(0.03, min_interval) # Cap minimum sleep at ~33 FPS

    logger.info(f"Starting broadcast loop with minimum interval: {min_interval:.3f}s")

    while True:
        start_time = time.monotonic()
        try:
            # Iterate through streams that have active connections
            for stream_id, connections in list(active_connections.items()):
                if not connections: # Skip if no connections for this stream
                    continue
                    
                processor = stream_processors.get(stream_id)
                if not processor:
                    logger.warning(f"Processor for stream '{stream_id}' not found during broadcast.")
                    continue

                # Get the latest combined data (frame + detection)
                data = processor.get_latest_data()
                
                # Avoid sending if frame is missing (unless it's the first time)
                if data['frame'] is None and processor.latest_frame_time > 0:
                    # logger.debug(f"[{stream_id}] Skipping broadcast, no new frame.")
                    continue
                    
                message = json.dumps(data)
                
                # Send to all connected clients for this stream
                # Use a copy of the set for safe iteration during removal
                dead_connections = set()
                for connection in list(connections):
                    try:
                        await connection.send_text(message)
                    except Exception as e:
                        #logger.error(f"Failed to send data to connection {id(connection)} for stream '{stream_id}': {e}")
                        dead_connections.add(connection)
                
                # Remove dead connections from the original set
                for dead in dead_connections:
                    connections.discard(dead)
                    # logger.info(f"Removed dead connection {id(dead)} for stream '{stream_id}'. Total: {len(connections)}")
                
                # Clean up stream_id entry if no connections left
                if not connections:
                     del active_connections[stream_id]
                     logger.info(f"No active connections left for stream '{stream_id}', removed from broadcast list.")

            # Sleep based on the minimum required interval
            elapsed = time.monotonic() - start_time
            sleep_time = max(0, min_interval - elapsed)
            await asyncio.sleep(sleep_time)
            
        except Exception as e:
            logger.error(f"Error in broadcast loop: {e}", exc_info=True)
            await asyncio.sleep(1) # Avoid tight loops on major error

# --- Application Lifespan (Startup/Shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Application startup...")
    global stream_processors, broadcast_task
    
    # Initialize and start processors for each configured stream
    for config in STREAMS:
        stream_id = config['id']
        logger.info(f"Initializing stream processor for '{stream_id}'")
        processor = VideoStreamProcessor(config)
        stream_processors[stream_id] = processor
        processor.start()
        await asyncio.sleep(0.1) # Stagger startup slightly
        
    # Start the background broadcast task
    if stream_processors:
        broadcast_task = asyncio.create_task(stream_broadcast_loop())
        logger.info("Started background broadcast task.")
    else:
        logger.warning("No streams configured, broadcast task not started.")

    yield # Application runs here
    
    # Shutdown
    logger.info("Application shutdown...")
    if broadcast_task:
        broadcast_task.cancel()
        try:
            await broadcast_task
        except asyncio.CancelledError:
            logger.info("Background broadcast task cancelled.")
            
    # Stop all stream processors
    for stream_id, processor in stream_processors.items():
        logger.info(f"Stopping stream processor for '{stream_id}'")
        processor.stop()
    
    logger.info("Application shutdown complete.")

# --- FastAPI Application ---
app = FastAPI(
    title="Multi-Stream Accident Detector", 
    description="Real-time traffic accident detection and video streaming for multiple sources.",
    lifespan=lifespan
)

# --- REST Endpoints ---
@app.get("/")
def health_check():
    """Basic health check endpoint."""
    return {"status": "ok", "streams_running": list(stream_processors.keys())}

@app.get("/streams")
def list_streams():
    """List available video streams."""
    return {
        "streams": [
            {"id": p.stream_id, "location": p.location, "status": p.latest_detection_result.get('status', 'unknown')} 
            for p in stream_processors.values()
        ]
    }

@app.get("/stream/{stream_id}/frame")
def get_latest_frame(stream_id: str):
    """Get the latest frame for a specific stream as base64."""
    processor = get_stream_processor(stream_id)
    frame_base64 = processor.get_latest_frame_base64()
    if frame_base64:
        return {"stream_id": stream_id, "frame": frame_base64}
    else:
        # Return 404 if no frame has ever been captured
         if processor.latest_frame_time == 0:
              raise HTTPException(status_code=404, detail=f"No frame available yet for stream '{stream_id}'.")
         else: # Return 200 with null frame if frames were captured previously but not now
             return {"stream_id": stream_id, "frame": None, "message": "Frame currently unavailable"}
        

@app.get("/stream/{stream_id}/detect")
def get_latest_detection(stream_id: str):
    """Get the latest accident detection result for a specific stream."""
    processor = get_stream_processor(stream_id)
    return {"stream_id": stream_id, "detection": processor.latest_detection_result}

# --- WebSocket Endpoint ---
@app.websocket("/ws/stream/{stream_id}")
async def ws_stream(ws: WebSocket, stream_id: str):
    """WebSocket endpoint for a specific video stream."""
    # Check if stream_id is valid
    if stream_id not in stream_processors:
        await ws.close(code=1008, reason=f"Unknown stream ID: {stream_id}")
        return
        
    await ws.accept()
    logger.info(f"WebSocket connection established for stream '{stream_id}': {id(ws)}")
    
    # Add to active connections for this stream
    active_connections[stream_id].add(ws)
    
    try:
        # Send initial data immediately if available
        processor = get_stream_processor(stream_id)
        initial_data = processor.get_latest_data()
        await ws.send_text(json.dumps(initial_data))
        
        # Keep the connection alive, waiting for messages or disconnect
        while True:
            # The broadcast loop handles sending data.
            # We just wait here to detect client disconnect.
            await ws.receive_text() # This will raise WebSocketDisconnect if client closes
    except WebSocketDisconnect:
        logger.info(f"WebSocket connection closed for stream '{stream_id}': {id(ws)}")
    except Exception as e:
        logger.error(f"Error in WebSocket connection for stream '{stream_id}' ({id(ws)}): {e}")
    finally:
        # Remove from active connections
        if stream_id in active_connections:
            active_connections[stream_id].discard(ws)
            # If this was the last connection for the stream, remove the stream_id key
            if not active_connections[stream_id]:
                del active_connections[stream_id]
                logger.info(f"Last WebSocket connection closed for stream '{stream_id}', removed from broadcast list.")
        
        # Ensure the connection is closed from server-side
        try:
            await ws.close()
        except Exception:
            pass # Already closed or error during close 