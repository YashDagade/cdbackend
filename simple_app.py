import asyncio
from fastapi import FastAPI, WebSocket
from mock_detector import mock_detect_accident

app = FastAPI()

@app.get("/")
def health_check():
    return {"status": "ok"}

@app.websocket("/ws/detections")
async def ws_detections(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            # Use the mock detector for testing
            result = mock_detect_accident()
            
            # Send result to client
            await ws.send_text(result)
            
            # Wait ~200ms for ~5 FPS
            await asyncio.sleep(0.2)
    except Exception as e:
        print(f"WebSocket error: {e}")
        await ws.close() 