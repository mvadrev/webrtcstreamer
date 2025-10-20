# Update package lists
sudo apt update
sudo apt upgrade -y

# Install Python3 and pip
sudo apt install -y python3 python3-pip python3-gi python3-gi-cairo gir1.2-gst-1.0 gir1.2-gobject-2.0

# Install OpenCV (with GStreamer support)
# Raspberry Pi OS OpenCV package usually comes with GStreamer enabled
sudo apt install -y python3-opencv

# Install GStreamer core and plugins (base, good, bad, ugly)
sudo apt install -y \
  gstreamer1.0-tools \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly \
  gstreamer1.0-libav

# Install libcamera tools (libcamerasrc depends on this)
sudo apt install -y libcamera-apps libcamera-tools

# (Optional) Install development headers if you want to build anything
sudo apt install -y libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev

# Verify GStreamer installation
gst-inspect-1.0 libcamerasrc
