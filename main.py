import asyncio
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from accident_detector import detect_frame_accident, get_current_frame

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# List of active connections
detection_connections = set()
video_connections = set()
# Task references to allow cleanup
detection_task = None
video_task = None

# Background task for sending accident detections to all clients
async def detection_broadcast_loop():
    """Continuously detect accidents and broadcast to all connected clients"""
    while True:
        try:
            if detection_connections:  # Only process if there are connections
                # Detect accidents in the current frame
                result = await asyncio.get_event_loop().run_in_executor(
                    None, detect_frame_accident
                )
                
                # Send to all connected clients
                dead_connections = set()
                for connection in detection_connections:
                    try:
                        await connection.send_text(result)
                    except Exception as e:
                        logger.error(f"Failed to send detection to connection: {e}")
                        dead_connections.add(connection)
                
                # Remove dead connections
                for dead in dead_connections:
                    detection_connections.discard(dead)
                    
            # Wait ~200ms (5 FPS)
            await asyncio.sleep(0.2)
            
        except Exception as e:
            logger.error(f"Error in detection broadcast loop: {e}")
            await asyncio.sleep(1)  # Avoid tight loops on error

# Background task for streaming video frames to all clients
async def video_broadcast_loop():
    """Continuously stream video frames to all connected clients"""
    while True:
        try:
            if video_connections:  # Only process if there are connections
                # Get the current frame
                frame_base64 = await asyncio.get_event_loop().run_in_executor(
                    None, get_current_frame
                )
                
                if frame_base64:
                    # Prepare the message with the frame data
                    message = json.dumps({
                        "frame": frame_base64
                    })
                    
                    # Send to all connected clients
                    dead_connections = set()
                    for connection in video_connections:
                        try:
                            await connection.send_text(message)
                        except Exception as e:
                            logger.error(f"Failed to send frame to connection: {e}")
                            dead_connections.add(connection)
                    
                    # Remove dead connections
                    for dead in dead_connections:
                        video_connections.discard(dead)
                
            # Wait ~33ms (30 FPS)
            await asyncio.sleep(1/30)
            
        except Exception as e:
            logger.error(f"Error in video broadcast loop: {e}")
            await asyncio.sleep(0.5)  # Avoid tight loops on error

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create background tasks
    global detection_task, video_task
    detection_task = asyncio.create_task(detection_broadcast_loop())
    video_task = asyncio.create_task(video_broadcast_loop())
    logger.info("Started background tasks")
    
    yield
    
    # Shutdown: cancel tasks
    if detection_task:
        detection_task.cancel()
        try:
            await detection_task
        except asyncio.CancelledError:
            logger.info("Background detection task cancelled")
    
    if video_task:
        video_task.cancel()
        try:
            await video_task
        except asyncio.CancelledError:
            logger.info("Background video task cancelled")

app = FastAPI(
    title="Accident Detector", 
    description="Real-time traffic accident detection with video streaming",
    lifespan=lifespan
)

@app.get("/")
def health_check():
    """Basic health check endpoint"""
    return {"status": "ok"}

@app.websocket("/ws/detections")
async def ws_detections(ws: WebSocket):
    """WebSocket endpoint for real-time accident detections"""
    await ws.accept()
    logger.info(f"Detection WebSocket connection established: {id(ws)}")
    
    # Add to active connections
    detection_connections.add(ws)
    
    try:
        # Keep the connection alive
        while True:
            # Just wait for client messages (if any) to detect disconnection
            await ws.receive_text()
    except WebSocketDisconnect:
        logger.info(f"Detection WebSocket connection closed: {id(ws)}")
    except Exception as e:
        logger.error(f"Error in detection WebSocket connection: {e}")
    finally:
        # Remove from active connections
        detection_connections.discard(ws)
        
        # Ensure the connection is closed properly
        try:
            await ws.close()
        except:
            pass  # Already closed

@app.websocket("/ws/video")
async def ws_video(ws: WebSocket):
    """WebSocket endpoint for real-time video streaming"""
    await ws.accept()
    logger.info(f"Video WebSocket connection established: {id(ws)}")
    
    # Add to active connections
    video_connections.add(ws)
    
    try:
        # Keep the connection alive
        while True:
            # Just wait for client messages (if any) to detect disconnection
            await ws.receive_text()
    except WebSocketDisconnect:
        logger.info(f"Video WebSocket connection closed: {id(ws)}")
    except Exception as e:
        logger.error(f"Error in video WebSocket connection: {e}")
    finally:
        # Remove from active connections
        video_connections.discard(ws)
        
        # Ensure the connection is closed properly
        try:
            await ws.close()
        except:
            pass  # Already closed 