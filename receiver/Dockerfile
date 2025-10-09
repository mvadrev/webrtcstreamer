# Use Ultralytics prebuilt image (this image has YOLO, PyTorch, and CUDA preinstalled)
FROM ultralytics/ultralytics:latest

# Set working directory
WORKDIR /app

# Install OpenCV and other necessary libraries
RUN pip install --no-cache-dir opencv-python aiortc av

# Copy the receiver script and YOLO model into the container
COPY receiver.py /app/
COPY model.pt /app/

# Set the default command
CMD ["python3", "receiver.py"]
