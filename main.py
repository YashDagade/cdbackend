import asyncio
import os
from fastapi import FastAPI, WebSocket
from accident_detector import detect_frame_accident
from together import Together

app = FastAPI()

# Update Together API key from environment
from accident_detector import together_client
together_client.api_key = os.environ.get("TOGETHER_API_KEY", "")

@app.get("/")
def health_check():
    return {"status": "ok"}

@app.websocket("/ws/detections")
async def ws_detections(ws: WebSocket):
    await ws.accept()
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
    except Exception as e:
        print(f"WebSocket error: {e}")
        await ws.close()
    
@app.on_event("startup")
async def startup_event():
    # Ensure API key is set
    if not together_client.api_key:
        print("WARNING: TOGETHER_API_KEY not set. API calls will fail.")
        
@app.on_event("shutdown")
async def shutdown_event():
    # Release the video capture
    from accident_detector import cap
    cap.release() 