import asyncio
import json
import logging
import time
import datetime  # Add datetime for ISO timestamp generation
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
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
# Similar structure for analysis connections
analysis_connections = defaultdict(set)
# Background broadcast tasks references
stream_broadcast_task = None
analysis_broadcast_task = None

# --- Helper Functions ---
def get_stream_processor(stream_id: str) -> VideoStreamProcessor:
    processor = stream_processors.get(stream_id)
    if not processor:
        raise HTTPException(status_code=404, detail=f"Stream '{stream_id}' not found.")
    return processor

# --- Background Tasks ---
async def stream_broadcast_loop():
    """Continuously broadcast latest frames to connected clients."""
    # For video streaming, we want to maintain ~30 FPS
    interval = 1.0 / 30.0  # 33.3ms interval for ~30 FPS

    logger.info(f"Starting stream broadcast loop with interval: {interval:.3f}s")

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

                # Get the latest frame only
                frame_b64 = processor.get_latest_frame_base64()
                
                # Skip if no frame is available
                if frame_b64 is None:
                    continue
                    
                # Create the frame-only message
                message = json.dumps({
                    "type": "frame",
                    "stream_id": stream_id,
                    "frame": frame_b64,
                    "timestamp": datetime.datetime.utcnow().isoformat()
                })
                
                # Send to all connected clients for this stream
                # Use a copy of the set for safe iteration during removal
                dead_connections = set()
                for connection in list(connections):
                    try:
                        await connection.send_text(message)
                    except Exception as e:
                        dead_connections.add(connection)
                
                # Remove dead connections from the original set
                for dead in dead_connections:
                    connections.discard(dead)
                
                # Clean up stream_id entry if no connections left
                if not connections:
                    del active_connections[stream_id]
                    logger.info(f"No active connections left for stream '{stream_id}', removed from broadcast list.")

            # Sleep to maintain target frame rate
            elapsed = time.monotonic() - start_time
            sleep_time = max(0, interval - elapsed)
            await asyncio.sleep(sleep_time)
            
        except Exception as e:
            logger.error(f"Error in stream broadcast loop: {e}", exc_info=True)
            await asyncio.sleep(1) # Avoid tight loops on major error

async def analysis_broadcast_loop():
    """Continuously check for and broadcast accident alerts to analysis clients."""
    logger.info("Starting analysis broadcast loop...")

    while True:
        try:
            # Check each stream processor for accident alerts in their broadcast queue
            for stream_id, processor in stream_processors.items():
                if stream_id not in analysis_connections or not analysis_connections[stream_id]:
                    # Skip if no analysis clients for this stream
                    continue
                
                # Non-blocking check for messages in the broadcast queue
                if not processor.broadcast_queue.empty():
                    # Get the message from the queue
                    message = processor.broadcast_queue.get_nowait()
                    message_json = json.dumps(message)
                    
                    # Send to all connected analysis clients for this stream
                    dead_connections = set()
                    for connection in list(analysis_connections[stream_id]):
                        try:
                            await connection.send_text(message_json)
                        except Exception as e:
                            dead_connections.add(connection)
                    
                    # Remove dead connections
                    for dead in dead_connections:
                        analysis_connections[stream_id].discard(dead)
                    
                    # Clean up if no connections left
                    if not analysis_connections[stream_id]:
                        del analysis_connections[stream_id]
            
            # Sleep briefly to avoid consuming too many resources
            await asyncio.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Error in analysis broadcast loop: {e}", exc_info=True)
            await asyncio.sleep(1)

# --- Application Lifespan (Startup/Shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Application startup...")
    global stream_processors, stream_broadcast_task, analysis_broadcast_task
    
    # Initialize and start processors for each configured stream
    for config in STREAMS:
        stream_id = config['id']
        logger.info(f"Initializing stream processor for '{stream_id}'")
        processor = VideoStreamProcessor(config)
        stream_processors[stream_id] = processor
        processor.start()
        await asyncio.sleep(0.1) # Stagger startup slightly
        
    # Start the background broadcast tasks
    if stream_processors:
        stream_broadcast_task = asyncio.create_task(stream_broadcast_loop())
        analysis_broadcast_task = asyncio.create_task(analysis_broadcast_loop())
        logger.info("Started background broadcast tasks.")
    else:
        logger.warning("No streams configured, broadcast tasks not started.")

    yield # Application runs here
    
    # Shutdown
    logger.info("Application shutdown...")
    if stream_broadcast_task:
        stream_broadcast_task.cancel()
        try:
            await stream_broadcast_task
        except asyncio.CancelledError:
            logger.info("Stream broadcast task cancelled.")
            
    if analysis_broadcast_task:
        analysis_broadcast_task.cancel()
        try:
            await analysis_broadcast_task
        except asyncio.CancelledError:
            logger.info("Analysis broadcast task cancelled.")
            
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

# --- Add CORS Middleware --- 
# For simpler deployment/testing, allow all origins:
origins = ["*"] 

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

# --- WebSocket Endpoints ---
@app.websocket("/ws/stream/{stream_id}")
async def ws_stream_frames(ws: WebSocket, stream_id: str):
    """WebSocket endpoint for streaming video frames only."""
    # Check if stream_id is valid
    if stream_id not in stream_processors:
        await ws.close(code=1008, reason=f"Unknown stream ID: {stream_id}")
        return
        
    await ws.accept()
    logger.info(f"Stream WebSocket connection established for stream '{stream_id}': {id(ws)}")
    
    # Add to active connections for this stream
    active_connections[stream_id].add(ws)
    
    try:
        # Send initial frame immediately if available
        processor = get_stream_processor(stream_id)
        frame_b64 = processor.get_latest_frame_base64()
        if frame_b64:
            await ws.send_json({
                "type": "frame",
                "stream_id": stream_id,
                "frame": frame_b64,
                "timestamp": datetime.datetime.utcnow().isoformat()
            })
        
        # Keep the connection alive, waiting for messages or disconnect
        while True:
            # Simply wait for client messages or disconnect
            # The stream_broadcast_loop handles sending frames
            await ws.receive_text()
    except WebSocketDisconnect:
        logger.info(f"Stream WebSocket connection closed for stream '{stream_id}': {id(ws)}")
    except Exception as e:
        logger.error(f"Error in stream WebSocket connection for stream '{stream_id}' ({id(ws)}): {e}")
    finally:
        # Remove from active connections
        if stream_id in active_connections:
            active_connections[stream_id].discard(ws)
            if not active_connections[stream_id]:
                del active_connections[stream_id]
        
        # Ensure the connection is closed from server-side
        try:
            await ws.close()
        except Exception:
            pass

@app.websocket("/ws/analyze/{stream_id}")
async def ws_stream_analysis(ws: WebSocket, stream_id: str):
    """WebSocket endpoint for receiving accident alerts only."""
    # Check if stream_id is valid
    if stream_id not in stream_processors:
        await ws.close(code=1008, reason=f"Unknown stream ID: {stream_id}")
        return
        
    await ws.accept()
    logger.info(f"Analysis WebSocket connection established for stream '{stream_id}': {id(ws)}")
    
    # Add to analysis connections for this stream
    analysis_connections[stream_id].add(ws)
    
    try:
        # Send initial status message
        await ws.send_json({
            "type": "status", 
            "stream_id": stream_id,
            "message": "Connected to accident alert stream",
            "timestamp": time.time()
        })
        
        # Keep the connection alive, waiting for messages or disconnect
        while True:
            # Simply wait for client messages or disconnect
            # The analysis_broadcast_loop handles sending alerts
            await ws.receive_text()
    except WebSocketDisconnect:
        logger.info(f"Analysis WebSocket connection closed for stream '{stream_id}': {id(ws)}")
    except Exception as e:
        logger.error(f"Error in analysis WebSocket connection for stream '{stream_id}' ({id(ws)}): {e}")
    finally:
        # Remove from analysis connections
        if stream_id in analysis_connections:
            analysis_connections[stream_id].discard(ws)
            if not analysis_connections[stream_id]:
                del analysis_connections[stream_id]
        
        # Ensure the connection is closed from server-side
        try:
            await ws.close()
        except Exception:
            pass

# --- Legacy WebSocket Endpoint (for backward compatibility) ---
@app.websocket("/ws/combined/{stream_id}")
async def ws_combined_stream(ws: WebSocket, stream_id: str):
    """Legacy WebSocket endpoint that combines frame and detection data."""
    # Check if stream_id is valid
    if stream_id not in stream_processors:
        await ws.close(code=1008, reason=f"Unknown stream ID: {stream_id}")
        return
        
    await ws.accept()
    logger.info(f"Legacy combined WebSocket connection established for stream '{stream_id}': {id(ws)}")
    
    try:
        # Send initial data immediately if available
        processor = get_stream_processor(stream_id)
        initial_data = processor.get_latest_data()
        await ws.send_text(json.dumps(initial_data))
        
        # Manually handle sending updates to this client
        while True:
            # Get latest data
            data = processor.get_latest_data()
            # Send update
            await ws.send_text(json.dumps(data))
            # Sleep to maintain reasonable frame rate (10 FPS)
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        logger.info(f"Legacy WebSocket connection closed for stream '{stream_id}': {id(ws)}")
    except Exception as e:
        logger.error(f"Error in legacy WebSocket connection for stream '{stream_id}' ({id(ws)}): {e}")
    finally:
        # Ensure the connection is closed from server-side
        try:
            await ws.close()
        except Exception:
            pass 