import asyncio
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from accident_detector import detect_frame_accident

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Accident Detector", description="Real-time traffic accident detection")

@app.get("/")
def health_check():
    return {"status": "ok"}

@app.websocket("/ws/detections")
async def ws_detections(ws: WebSocket):
    await ws.accept()
    logger.info("WebSocket connection established")
    try:
        while True:
            # 1) Classify one frame
            result = await asyncio.get_event_loop().run_in_executor(
                None, detect_frame_accident
            )
            # 2) Send result to client
            await ws.send_text(result)
            # 3) Wait ~200ms for ~5 FPS
            await asyncio.sleep(0.2)
    except WebSocketDisconnect:
        logger.info("WebSocket connection closed")
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {e}")
    finally:
        # Ensure the connection is closed properly
        try:
            await ws.close()
        except:
            pass  # Already closed 