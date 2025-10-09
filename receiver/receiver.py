import asyncio
import cv2
import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.signaling import TcpSocketSignaling
from av import VideoFrame
from datetime import datetime, timedelta
from ultralytics import YOLO
import torch
print(torch.cuda.is_available())
print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else "No GPU")

model = YOLO('yolov8n.pt')

frame_count = 0
last_annotated = None
fps_smooth = 0.0


class VideoReceiver:
    def __init__(self):
        self.track = None

    async def handle_track(self, track):
        print("Inside handle track")
        self.track = track
        frame_count = 0
        while True:
            try:
                print("Waiting for frame...")
                frame = await asyncio.wait_for(track.recv(), timeout=5.0)
                frame_count += 1
                print(f"Received frame {frame_count}")
                
                if isinstance(frame, VideoFrame):
                    print(f"Frame type: VideoFrame, pts: {frame.pts}, time_base: {frame.time_base}")
                    frame = frame.to_ndarray(format="bgr24")

                    if frame_count % 3 == 0:
                        results = model(frame, imgsz=416, conf=0.5)
                        annotated_frame = results[0].plot()
                        last_annotated = annotated_frame

                elif isinstance(frame, np.ndarray):
                    print(f"Frame type: numpy array")
                else:
                    print(f"Unexpected frame type: {type(frame)}")
                    continue
              
                 # Add timestamp to the frame
                current_time = datetime.now()
                new_time = current_time - timedelta( seconds=55)
                timestamp = new_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                cv2.putText(frame, timestamp, (10, frame.shape[0] - 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
                print(f"Saved frame {frame_count} to file")

                display_frame = annotated_frame.copy()
                cv2.imshow("Frame", display_frame)
    
                # Exit on 'q' key press
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            except asyncio.TimeoutError:
                print("Timeout waiting for frame, continuing...")
            except Exception as e:
                print(f"Error in handle_track: {str(e)}")
                if "Connection" in str(e):
                    break
        print("Exiting handle_track")
async def run(pc, signaling):
    await signaling.connect()

    @pc.on("track")
    def on_track(track):
        if isinstance(track, MediaStreamTrack):
            print(f"Receiving {track.kind} track")
            asyncio.ensure_future(video_receiver.handle_track(track))

    @pc.on("datachannel")
    def on_datachannel(channel):
        print(f"Data channel established: {channel.label}")

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print(f"Connection state is {pc.connectionState}")
        if pc.connectionState == "connected":
            print("WebRTC connection established successfully")

    print("Waiting for offer from sender...")
    offer = await signaling.receive()
    print("Offer received")
    await pc.setRemoteDescription(offer)
    print("Remote description set")

    answer = await pc.createAnswer()
    print("Answer created")
    await pc.setLocalDescription(answer)
    print("Local description set")

    await signaling.send(pc.localDescription)
    print("Answer sent to sender")

    print("Waiting for connection to be established...")
    while pc.connectionState != "connected":
        await asyncio.sleep(0.1)

    print("Connection established, waiting for frames...")
    await asyncio.sleep(100)  # Wait for 35 seconds to receive frames

    print("Closing connection")

async def main():
    signaling = TcpSocketSignaling("localhost", 9999)
    pc = RTCPeerConnection()
    
    global video_receiver
    video_receiver = VideoReceiver()

    try:
        await run(pc, signaling)
    except Exception as e:
        print(f"Error in main: {str(e)}")
    finally:
        print("Closing peer connection")
        await pc.close()

if __name__ == "__main__":
    asyncio.run(main())