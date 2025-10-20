import asyncio
import aiohttp
import cv2
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack

class VideoTrackReceiver(VideoStreamTrack):
    def __init__(self, track):
        super().__init__()  # Initialize VideoStreamTrack base class
        self.track = track

    async def recv(self):
        frame = await self.track.recv()
        img = frame.to_ndarray(format="bgr24")
        cv2.imshow("Received Video", img)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Exiting video display")
            cv2.destroyAllWindows()
            raise asyncio.CancelledError()

        return frame

async def display_frames(track):
    """
    Coroutine that repeatedly pulls frames from the VideoTrackReceiver
    to trigger OpenCV display.
    """
    receiver = VideoTrackReceiver(track)
    try:
        while True:
            await receiver.recv()
    except asyncio.CancelledError:
        print("Display frames cancelled")

async def run():
    async with aiohttp.ClientSession() as session:
        start_resp = await session.post("http://raspberrypi.local:5000/start_stream")
        if start_resp.status != 200:
            print("Failed to start stream:", await start_resp.text())
            return
        print("Stream started on server")

    pc = RTCPeerConnection()
    pc.addTransceiver("video", direction="recvonly")

    display_task = None

    @pc.on("track")
    def on_track(track):
        print(f"Track received: kind={track.kind}")
        if track.kind == "video":
            nonlocal display_task
            print("Starting frame display task")
            display_task = asyncio.create_task(display_frames(track))

    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://raspberrypi.local:5000/offer",
            json={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type},
        ) as resp:
            if resp.status != 200:
                print("Failed to get answer from server:", await resp.text())
                return
            answer_json = await resp.json()

    answer = RTCSessionDescription(sdp=answer_json["sdp"], type=answer_json["type"])
    await pc.setRemoteDescription(answer)

    print("Connection established, displaying video...")

    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        if display_task:
            display_task.cancel()
        print("Cancelled, cleaning up")

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("Program interrupted and exiting.")
    finally:
        cv2.destroyAllWindows()
