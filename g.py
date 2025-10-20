# To send video from pi to server
import asyncio
import time
import cv2
from quart import Quart, request, jsonify
from quart_cors import cors
import numpy as np

from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from picamera2 import Picamera2
from av import VideoFrame

app = Quart(__name__)
app = cors(app, allow_origin="*")

picam2 = Picamera2()
picam2.configure(
    picam2.create_preview_configuration(
        main={"format": "RGB888", "size": (800, 600)}
    )
)

# Control flag for streaming
streaming = False

@app.route("/start_stream", methods=["POST"])
async def start_stream():
    global streaming
    if not streaming:
        picam2.start()
        streaming = True
    return jsonify({"status": "stream started"})

@app.route("/stop_stream", methods=["POST"])
async def stop_stream():
    global streaming
    if streaming:
        picam2.stop()
        streaming = False
    return jsonify({"status": "stream stopped"})

class CameraVideoTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()

    async def recv(self):
        global streaming
        pts, time_base = await self.next_timestamp()

        if not streaming:
            # If not streaming, wait a bit and return black frame or no frame
            await asyncio.sleep(0.1)
            blank_frame = 255 * np.ones((720, 1280, 3), dtype=np.uint8)
            video_frame = VideoFrame.from_ndarray(blank_frame, format="rgb24")
            video_frame.pts = pts
            video_frame.time_base = time_base
            return video_frame

        frame = picam2.capture_array()
        video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
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
