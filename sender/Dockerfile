# Use the official Python 3.9 slim image as the base
FROM python:3.9-slim

# Set the working directory for the application
WORKDIR /app

# Install system dependencies needed by ffmpeg, OpenCV, etc.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies using pip
RUN pip install --no-cache-dir \
    opencv-python \
    requests

# Copy the sender.py script into the container's working directory
COPY sender.py /app/

# Define the command to run the application when the container starts
CMD ["python3", "sender.py"]
