import cv2
import time
from ultralytics import YOLO
from picamera2 import Picamera2
import numpy as np

print("Loading YOLO model...")
model = YOLO('yolov8n.pt')
print("Model loaded.")

print("Initializing Picamera2...")
picam2 = Picamera2()
picam2.preview_configuration.main.size = (640, 480)
picam2.preview_configuration.main.format = "RGB888"
picam2.configure("preview")
picam2.start()
time.sleep(1)  # Allow camera to warm up

prev_time = time.time()
fps_smooth = 0.0
alpha = 0.9
frame_count = 0
last_annotated = None
cv2.namedWindow("YOLOv8", cv2.WINDOW_NORMAL)
cv2.resizeWindow("YOLOv8", 320, 240)
print("Starting inference loop. Press 'q' to quit.")

while True:
    frame = picam2.capture_array()
    frame_count += 1

    if frame_count % 2 == 0:
        results = model(frame, imgsz=416, conf=0.5)
        annotated_frame = results[0].plot()
        last_annotated = annotated_frame
    else:
        if last_annotated is not None:
            annotated_frame = last_annotated.copy()
        else:
            annotated_frame = frame.copy()

    curr_time = time.time()
    instant_fps = 1 / (curr_time - prev_time)
    fps_smooth = alpha * fps_smooth + (1 - alpha) * instant_fps
    prev_time = curr_time

    display_frame = annotated_frame.copy()
    cv2.putText(display_frame, f"FPS: {fps_smooth:.2f}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    cv2.imshow("YOLOv8", display_frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("Quitting by user request.")
        break

cv2.destroyAllWindows()
print("Resources released. Exiting.")
