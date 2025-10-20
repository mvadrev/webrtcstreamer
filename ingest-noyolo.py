# works in react both sterams
import asyncio
import cv2
import io
import aiohttp
from aiortc import RTCPeerConnection, VideoStreamTrack, RTCSessionDescription
from quart import Quart, Response
from PIL import Image
from hypercorn.asyncio import serve
from hypercorn.config import Config
from quart_cors import cors  # CORS support

app = Quart(__name__)
app = cors(app, allow_origin="*")  # Allow all origins

current_frame = None  # latest frame for MJPEG stream

class VideoTrackReceiver(VideoStreamTrack):
    def __init__(self, track):
        super().__init__()
        self.track = track

    async def recv(self):
        global current_frame
        frame = await self.track.recv()
        img = frame.to_ndarray(format="bgr24")

        # Resize for consistent display
        target_width = 640
        scale = target_width / img.shape[1]
        target_height = int(img.shape[0] * scale)
        img_resized = cv2.resize(img, (target_width, target_height))

        current_frame = img_resized
        return frame

async def display_frames(track):
    receiver = VideoTrackReceiver(track)
    try:
        while True:
            await receiver.recv()
    except asyncio.CancelledError:
        pass

async def run_webrtc():
    async with aiohttp.ClientSession() as session:
        # Start Pi stream
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

# Optional MJPEG stream for React or browser
@app.route("/video_feed")
async def video_feed():
    async def generate():
        global current_frame
        try:
            while True:
                if current_frame is not None:
                    img_rgb = cv2.cvtColor(current_frame, cv2.COLOR_BGR2RGB)
                    buf = io.BytesIO()
                    Image.fromarray(img_rgb).save(buf, format="JPEG")
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.getvalue() + b"\r\n"
                else:
                    yield b"--frame\r\nContent-Type: text/plain\r\n\r\n.\r\n"
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

async def main():
    config = Config()
    config.bind = ["0.0.0.0:8000"]

    quart_task = asyncio.create_task(serve(app, config))
    webrtc_task = asyncio.create_task(run_webrtc())

    await asyncio.gather(quart_task, webrtc_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exiting...")
