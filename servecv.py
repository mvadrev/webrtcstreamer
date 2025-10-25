import asyncio
import time
import cv2
import numpy as np
from quart import Quart, request, jsonify
from quart_cors import cors
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
    RTCConfiguration,
    RTCIceServer,
)
from av import VideoFrame
from hypercorn.asyncio import serve
from hypercorn.config import Config

# -------------------------
# Initialize Quart app
# -------------------------
print(f"[{time.strftime('%H:%M:%S')}] Initializing Quart app...")
app = Quart(__name__)
app = cors(app, allow_origin="*", allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type"])
print(f"[{time.strftime('%H:%M:%S')}] Setup complete.")

# -------------------------
# Globals
# -------------------------
cap = None
streaming = False
pcs = set()


# -------------------------
# Helper: open camera safely
# -------------------------
def get_camera():
    global cap
    if cap is None or not cap.isOpened():
        t0 = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] Opening camera...")
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            raise RuntimeError("Failed to open camera")
        print(f"[{time.strftime('%H:%M:%S')}] Camera opened in {time.time() - t0:.2f}s")
    return cap


# -------------------------
# Custom Video Track
# -------------------------
class CameraVideoTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        print(f"[{time.strftime('%H:%M:%S')}] CameraVideoTrack initialized")

    async def recv(self):
        global streaming
        pts, time_base = await self.next_timestamp()
        camera = get_camera()

        if not streaming:
            await asyncio.sleep(0.1)
            blank = 255 * np.ones((480, 640, 3), dtype=np.uint8)
            frame = VideoFrame.from_ndarray(blank, format="bgr24")
            frame.pts = pts
            frame.time_base = time_base
            return frame

        ret, img = camera.read()
        if not ret:
            blank = 255 * np.ones((480, 640, 3), dtype=np.uint8)
            frame = VideoFrame.from_ndarray(blank, format="bgr24")
        else:
            img = cv2.resize(img, (640, 480))
            frame = VideoFrame.from_ndarray(img, format="bgr24")

        frame.pts = pts
        frame.time_base = time_base
        await asyncio.sleep(0.02)
        return frame


# -------------------------
# Stream control endpoints
# -------------------------
@app.route("/start_stream", methods=["POST"])
async def start_stream():
    global streaming
    streaming = True
    print(f"[{time.strftime('%H:%M:%S')}] Stream started.")
    get_camera()
    return jsonify({"status": "stream started"})


@app.route("/stop_stream", methods=["POST"])
async def stop_stream():
    global streaming
    streaming = False
    print(f"[{time.strftime('%H:%M:%S')}] Stream stopped.")
    return jsonify({"status": "stream stopped"})


# -------------------------
# WebRTC Offer / Answer
# -------------------------
@app.route("/offer", methods=["POST"])
async def offer():
    global streaming
    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] Received /offer request")

    params = await request.get_json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    rtc_config = RTCConfiguration(
        iceServers=[
            RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
            RTCIceServer(
                urls=["turn:global.relay.metered.ca:80"],
                username="openai",
                credential="openai",
            ),
        ]
    )

    pc = RTCPeerConnection(configuration=rtc_config)
    pcs.add(pc)
    print(f"[{time.strftime('%H:%M:%S')}] Created RTCPeerConnection")

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print(f"[{time.strftime('%H:%M:%S')}] Connection state: {pc.connectionState}")
        if pc.connectionState in ["failed", "closed", "disconnected"]:
            await pc.close()
            pcs.discard(pc)
            print(f"[{time.strftime('%H:%M:%S')}] Peer connection closed.")

    # Auto-start camera if not running
    if not streaming:
        streaming = True
        print(f"[{time.strftime('%H:%M:%S')}] Auto-starting camera for new client...")

    pc.addTrack(CameraVideoTrack())
    print(f"[{time.strftime('%H:%M:%S')}] Added CameraVideoTrack to connection")

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    print(f"[{time.strftime('%H:%M:%S')}] /offer processed in {time.time() - t0:.2f}s")
    return jsonify({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})


# -------------------------
# Server entry point
# -------------------------
if __name__ == "__main__":
    config = Config()
    config.bind = ["0.0.0.0:5000"]

    # Pre-warm camera once on startup
    print(f"[{time.strftime('%H:%M:%S')}] Starting WebRTC server on port 5000...")
    get_camera()

    try:
        asyncio.run(serve(app, config))
    finally:
        if cap and cap.isOpened():
            cap.release()
        cv2.destroyAllWindows()
