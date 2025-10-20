import asyncio
import cv2
import io
import aiohttp
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from ultralytics import YOLO
from quart import Quart, jsonify, Response
from PIL import Image
from hypercorn.asyncio import serve
from hypercorn.config import Config
from quart_cors import cors  # Added for CORS support

# Load YOLO model
model = YOLO('yolov8n.pt')

app = Quart(__name__)
app = cors(app, allow_origin="*")  # Enable CORS

detections = []
current_frame = None  # Holds latest processed frame for MJPEG streaming

class VideoTrackReceiver(VideoStreamTrack):
    def __init__(self, track):
        super().__init__()
        self.track = track
        self.frame_counter = 0

    async def recv(self):
        global detections, current_frame

        frame = await self.track.recv()
        self.frame_counter += 1

        img = frame.to_ndarray(format="bgr24")

        # Resize for YOLO input & display
        target_width = 640
        scale = target_width / img.shape[1]
        target_height = int(img.shape[0] * scale)
        img_resized = cv2.resize(img, (target_width, target_height))

        # Run YOLO every 2 frames to reduce load
        if self.frame_counter % 2 == 0:
            results = model(img_resized, verbose=False)
            detections.clear()

            boxes = results[0].boxes.xyxy.cpu().numpy()
            scores = results[0].boxes.conf.cpu().numpy()
            classes = results[0].boxes.cls.cpu().numpy().astype(int)

            for box, score, cls in zip(boxes, scores, classes):
                x1, y1, x2, y2 = box.astype(int)
                label = f"{model.names[cls]} {score:.2f}"
                detections.append({
                    "label": model.names[cls],
                    "confidence": float(score),
                    "box": [x1, y1, x2, y2]
                })

                # Draw detection box + label
                cv2.rectangle(img_resized, (x1, y1), (x2, y2), (0, 255, 0), 2)
                (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
                cv2.rectangle(img_resized, (x1, y1 - 20), (x1 + w, y1), (0, 255, 0), -1)
                cv2.putText(img_resized, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)

        current_frame = img_resized  # Save frame for MJPEG stream

        return frame

async def display_frames(track):
    receiver = VideoTrackReceiver(track)
    try:
        while True:
            await receiver.recv()
    except asyncio.CancelledError:
        print("Stopped display task")

async def run_webrtc():
    async with aiohttp.ClientSession() as session:
        start_resp = await session.post("http://raspberrypi.local:5000/start_stream")
        if start_resp.status != 200:
            print("Failed to start stream:", await start_resp.text())
            return
        print("Stream started.")

    pc = RTCPeerConnection()
    pc.addTransceiver("video", direction="recvonly")

    display_task = None

    @pc.on("track")
    def on_track(track):
        print(f"Track received: {track.kind}")
        if track.kind == "video":
            nonlocal display_task
            display_task = asyncio.create_task(display_frames(track))

    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://raspberrypi.local:5000/offer",
            json={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ) as resp:
            if resp.status != 200:
                print("Offer failed:", await resp.text())
                return
            answer_json = await resp.json()

    answer = RTCSessionDescription(sdp=answer_json["sdp"], type=answer_json["type"])
    await pc.setRemoteDescription(answer)

    print("WebRTC connected.")

    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        if display_task:
            display_task.cancel()

@app.route("/detections")
async def get_detections():
    return jsonify(detections)

@app.route("/video_feed")
async def video_feed():
    async def generate():
        global current_frame
        frame_counter = 0
        print("Client connected to /video_feed")
        try:
            while True:
                if current_frame is not None:
                    img_rgb = cv2.cvtColor(current_frame, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(img_rgb)
                    buf = io.BytesIO()
                    pil_img.save(buf, format="JPEG")
                    frame_bytes = buf.getvalue()
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                    )
                else:
                    # No frame yet, send a heartbeat comment
                    yield b"--frame\r\nContent-Type: text/plain\r\n\r\n.\r\n"
                frame_counter += 1
                if frame_counter % 40 == 0:
                    # Periodic heartbeat to keep connection alive
                    yield b"--frame\r\nContent-Type: text/plain\r\n\r\n.\r\n"
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            print("Client disconnected from video_feed")
        except Exception as e:
            print(f"Exception in video_feed generator: {e}")

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


async def main():
    config = Config()
    config.bind = ["0.0.0.0:8000"]

    quart_task = asyncio.create_task(serve(app, config))
    webrtc_task = asyncio.create_task(run_webrtc())

    try:
        await asyncio.gather(quart_task, webrtc_task)
    except asyncio.CancelledError:
        print("Shutting down")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exiting...")
