import asyncio
import websockets
import json
import time

async def test_ws_client():
    """
    Simple test client that connects to the WebSocket server and prints messages.
    """
    uri = "ws://localhost:10000/ws/detections"
    async with websockets.connect(uri) as websocket:
        print(f"Connected to {uri}")
        try:
            while True:
                message = await websocket.recv()
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                print(f"[{timestamp}] Received: {message}")
        except websockets.ConnectionClosed:
            print("Connection closed")

if __name__ == "__main__":
    asyncio.run(test_ws_client()) 