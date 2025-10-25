import asyncio
import cv2
import numpy as np
import torch
from aiortc import RTCPeerConnection, VideoStreamTrack, RTCSessionDescription, RTCConfiguration, RTCIceServer, RTCRtpSender
from aiortc.mediastreams import MediaStreamError
from quart import Quart, request, jsonify
from quart_cors import cors
import av
from ultralytics import YOLO
from hypercorn.asyncio import serve
from hypercorn.config import Config
import aiohttp

app = Quart(__name__)
app = cors(app, allow_origin="*")

# ----------------------------
# Globals
# ----------------------------
latest_raw_frame = None
latest_processed_frame = None
frame_lock = asyncio.Lock()

FRAME_WIDTH, FRAME_HEIGHT = 640, 480
blank_frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
cv2.putText(blank_frame, "Waiting for YOLO...", (50, FRAME_HEIGHT // 2),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

# ----------------------------
# CUDA check and YOLO model
# ----------------------------
cuda_available = torch.cuda.is_available()
device = 'cuda' if cuda_available else 'cpu'
print("Hello world from YOLO Ingest!")
print(f"🌟 CUDA Available: {cuda_available}, Using device: {device}")

model = YOLO("yolov8n.pt")
model.to(device)
print("✅ YOLO model loaded")

# ----------------------------
# ICE config for remote connectivity
# ----------------------------
ice_config = RTCConfiguration(
    iceServers=[
        RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
        RTCIceServer(
            urls=["turn:global.relay.metered.ca:80"],
            username="openai",
            credential="openai"
        )
    ]
)

# ----------------------------
# YOLO Worker
# ----------------------------
async def yolo_worker():
    global latest_raw_frame, latest_processed_frame
    print("🎯 YOLO worker started")
    frame_count = 0
    while True:
        frame_to_process = None
        async with frame_lock:
            if latest_raw_frame is not None:
                frame_to_process = latest_raw_frame
                latest_raw_frame = None

        if frame_to_process is not None:
            print(f"🖼️ Processing frame {frame_count}")
            with torch.inference_mode():
                results = await asyncio.to_thread(model.predict, frame_to_process, device=device, verbose=False)

            img = frame_to_process.copy()  # keep original shape
            for det in results[0].boxes:
                x1, y1, x2, y2 = map(int, det.xyxy[0])
                cls_id = int(det.cls[0])
                conf = float(det.conf[0])
                label = f"{model.names[cls_id]} {conf:.2f}"
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(img, label, (x1, y1 - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)

            async with frame_lock:
                latest_processed_frame = img
            print(f"✅ Frame {frame_count} processed")
            frame_count += 1
        else:
            await asyncio.sleep(0.005)

# ----------------------------
# WebRTC Track for React
# ----------------------------
class YOLOProcessedTrack(VideoStreamTrack):
    async def recv(self):
        pts, time_base = await self.next_timestamp()
        await asyncio.sleep(1/30)  # ~30 FPS for Docker

        async with frame_lock:
            img = latest_processed_frame.copy() if latest_processed_frame is not None else blank_frame

        frame = av.VideoFrame.from_ndarray(img, format="bgr24")
        frame.pts = pts
        frame.time_base = time_base
        print(f"📡 Sending frame to client")
        return frame

# ----------------------------
# Connect to Pi
# ----------------------------
async def connect_to_pi():
    global latest_raw_frame
    while True:
        print("🔌 Connecting to Pi...")
        pc = RTCPeerConnection(configuration=ice_config)

        @pc.on("track")
        async def on_track(track):
            global latest_raw_frame
            print("✅ Pi video track received")
            frame_count = 0
            try:
                while True:
                    frame = await track.recv()
                    img = frame.to_ndarray(format="bgr24")
                    async with frame_lock:
                        latest_raw_frame = img
                    frame_count += 1
                    if frame_count % 10 == 0:
                        print(f"🎥 Received {frame_count} frames from Pi")
            except MediaStreamError:
                print("⚠️ Stream ended")
            except Exception as e:
                print(f"⚠️ Track error: {e}")
            finally:
                await pc.close()
                print("🔁 Reconnecting in 5s...")

        try:
            pc.addTransceiver("video", direction="recvonly")
            offer = await pc.createOffer()
            await pc.setLocalDescription(offer)

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://192.168.4.117:5000/offer",
                    json={"sdp": pc.localDescription.sdp,
                          "type": pc.localDescription.type},
                ) as resp:
                    answer = await resp.json()

            await pc.setRemoteDescription(
                RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
            )
            print("✅ Connected to Pi")
            break
        except Exception as e:
            print(f"❌ Failed to connect: {e}")
            await pc.close()
            await asyncio.sleep(5)

# ----------------------------
# Offer endpoint for React client
# ----------------------------
@app.route("/offer", methods=["POST"])
async def offer():
    print("🌐 React client connected — generating WebRTC answer...")
    params = await request.get_json()
    pc = RTCPeerConnection(configuration=ice_config)

    @pc.on("connectionstatechange")
    async def on_state_change():
        print("🔁 Connection state:", pc.connectionState)

    @pc.on("iceconnectionstatechange")
    async def on_ice_state_change():
        print("❄️ ICE state:", pc.iceConnectionState)

    pc.addTrack(YOLOProcessedTrack())

    # Force VP8 codec
    for transceiver in pc.getTransceivers():
        if transceiver.kind == "video":
            transceiver.setCodecPreferences(
                [c for c in RTCRtpSender.getCapabilities("video").codecs
                 if c.mimeType == "video/VP8"]
            )

    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    print("📞 Offer received from React client, answer sent (with VP8 codec)")
    return jsonify({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})

# ----------------------------
# Main entry
# ----------------------------
async def main():
    asyncio.create_task(connect_to_pi())
    asyncio.create_task(yolo_worker())

    config = Config()
    config.bind = ["0.0.0.0:8000"]
    print("🚀 Server starting on 0.0.0.0:8000")
    await serve(app, config)

if __name__ == "__main__":
    asyncio.run(main())
