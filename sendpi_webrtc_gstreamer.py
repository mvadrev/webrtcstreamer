#!/usr/bin/env python3

import sys
import gi
import cv2

gi.require_version("Gst", "1.0")
from gi.repository import Gst

# Initialize GStreamer
Gst.init(None)

print("GStreamer version:", Gst.version_string())

# Define GStreamer pipeline string for the camera
pipeline_str = (
    "libcamerasrc camera-name=/base/axi/pcie@1000120000/rp1/i2c@80000/imx500@1a ! "
    "videoconvert ! queue ! "
    "video/x-raw, pixel-aspect-ratio=1/1, format=YUY2, width=640, height=640, framerate=30/1 ! "
    "queue ! videoconvert ! appsink"
)

# Open the video capture using the pipeline string
cap = cv2.VideoCapture(pipeline_str, cv2.CAP_GSTREAMER)

if not cap.isOpened():
    print("Failed to open camera pipeline")
    sys.exit(1)

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to get frame")
        break

    cv2.imshow("Camera", frame)
    
    # Exit on 'q' key
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
