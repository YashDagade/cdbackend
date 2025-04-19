import cv2
import base64
from together import Together

# Your HLS URL (master or media playlist)
VIDEO_SOURCE = "https://511mn.org/path/to/your/chunklist_w872956871.m3u8"

# Initialize Together client once
together_client = Together(api_key="")  # Set via environment variable
PROMPT = (
    "You are a police detective. "
    "Classify the attached image as exactly one word: 'accident' or 'no accident'."
)

# OpenCV video capture (HLS)
cap = cv2.VideoCapture(VIDEO_SOURCE)

def detect_frame_accident():
    """
    Grab one frame from the stream, send to Together, return 'accident' or 'no accident'.
    """
    # 1) Read next frame
    ret, frame = cap.read()
    if not ret:
        return "no accident"  # fallback if stream hiccups

    # 2) Encode frame to JPEG + Base64
    _, buffer = cv2.imencode('.jpg', frame)
    img_b64 = base64.b64encode(buffer).decode('utf-8')

    # 3) Call the Together Vision model (sync)
    response = together_client.chat.completions.create(
        model="meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo",
        messages=[
            {"role": "user", "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
            ]}
        ],
        stream=False
    )

    # 4) Extract and normalize reply
    text = response.choices[0].message.content.strip().lower()
    return text if text in ("accident", "no accident") else "no accident" 