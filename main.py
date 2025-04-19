import asyncio
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from accident_detector import detect_frame_accident

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Accident Detector", description="Real-time traffic accident detection")

# List of active connections
active_connections = set()

# Background task for sending updates to all clients
async def detection_broadcast_loop():
    """Continuously detect accidents and broadcast to all connected clients"""
    while True:
        try:
            if active_connections:  # Only process if there are connections
                # Detect accidents in the current frame
                result = await asyncio.get_event_loop().run_in_executor(
                    None, detect_frame_accident
                )
                
                # Send to all connected clients
                dead_connections = set()
                for connection in active_connections:
                    try:
                        await connection.send_text(result)
                    except Exception as e:
                        logger.error(f"Failed to send to connection: {e}")
                        dead_connections.add(connection)
                
                # Remove dead connections
                for dead in dead_connections:
                    active_connections.remove(dead)
                    
            # Wait ~200ms (5 FPS)
            await asyncio.sleep(0.2)
            
        except Exception as e:
            logger.error(f"Error in broadcast loop: {e}")
            await asyncio.sleep(1)  # Avoid tight loops on error

@app.on_event("startup")
async def startup_event():
    """Start the detection background task when application starts"""
    asyncio.create_task(detection_broadcast_loop())
    logger.info("Started background detection loop")

@app.get("/")
def health_check():
    """Basic health check endpoint"""
    return {"status": "ok"}

@app.websocket("/ws/detections")
async def ws_detections(ws: WebSocket):
    """WebSocket endpoint for real-time accident detections"""
    await ws.accept()
    logger.info(f"WebSocket connection established: {id(ws)}")
    
    # Add to active connections
    active_connections.add(ws)
    
    try:
        # Keep the connection alive
        while True:
            # Just wait for client messages (if any) to detect disconnection
            await ws.receive_text()
    except WebSocketDisconnect:
        logger.info(f"WebSocket connection closed: {id(ws)}")
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {e}")
    finally:
        # Remove from active connections
        active_connections.discard(ws)
        
        # Ensure the connection is closed properly
        try:
            await ws.close()
        except:
            pass  # Already closed 