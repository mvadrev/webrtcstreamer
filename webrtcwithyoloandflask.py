import asyncio
import time
import cv2
import numpy as np
from quart import Quart, request, jsonify
from quart_cors import cors

from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from picamera2 import Picamera2
from av import VideoFrame
from ultralytics import YOLO  # Make sure ultralytics is installed: pip install ultralytics

# Constants
INFERENCE_EVERY_N_FRAMES = 5

# Initialize app
app = Quart(__name__)
app = cors(app, allow_origin="*")

# Initialize Picamera2
picam2 = Picamera2()
picam2.configure(
    picam2.create_preview_configuration(
        main={"format": "RGB888", "size": (1280, 720)}
    )
)
picam2.start()
time.sleep(1)  # Allow camera to warm up

# Load YOLOv8n model
model = YOLO("yolov8n.pt")  # You can replace with another model path

# Video stream track
class CameraVideoTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.frame_count = 0
        self.last_result = None

    async def recv(self):
        self.frame_count += 1
        pts, time_base = await self.next_timestamp()

        # Capture frame
        frame = picam2.capture_array()

        # Convert to BGR for OpenCV
        bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        # Perform inference every N frames
        if self.frame_count % INFERENCE_EVERY_N_FRAMES == 0:
            results = model(bgr_frame, verbose=False)
            self.last_result = results[0]

        # Draw results if available
        if self.last_result:
            for box in self.last_result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                cls = int(box.cls[0])
                label = model.names[cls]

                cv2.rectangle(bgr_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    bgr_frame,
                    f"{label} {conf:.2f}",
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    1,
                )

        # Convert back to RGB
        rgb_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)

        # Create VideoFrame
        video_frame = VideoFrame.from_ndarray(rgb_frame, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base

        return video_frame

pcs = set()

@app.route("/offer", methods=["POST"])
async def offer():
    params = await request.get_json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print("Connection state is", pc.connectionState)
        if pc.connectionState in ["failed", "closed"]:
            await pc.close()
            pcs.discard(pc)

    pc.addTrack(CameraVideoTrack())

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return jsonify({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})

if __name__ == "__main__":
    import hypercorn.asyncio
    from hypercorn.config import Config

    config = Config()
    config.bind = ["0.0.0.0:5000"]
    asyncio.run(hypercorn.asyncio.serve(app, config))
