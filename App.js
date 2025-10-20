import React, { useRef, useState } from "react";

function App() {
  const videoRef = useRef(null);
  const pcRef = useRef(null);
  const [streaming, setStreaming] = useState(false);
  const [showYoloStream, setShowYoloStream] = useState(false);

  async function startStream() {
    // Start the backend stream (your backend server must be running)
    await fetch("http://192.168.4.152:5000/start_stream", { method: "POST" });

    const pc = new RTCPeerConnection();
    pcRef.current = pc;

    pc.addTransceiver("video", { direction: "recvonly" });

    pc.ontrack = (event) => {
      if (videoRef.current) {
        videoRef.current.srcObject = event.streams[0];
      }
    };

    pc.onicecandidate = async (event) => {
      if (!event.candidate) {
        const offer = pc.localDescription;
        const response = await fetch("http://192.168.4.152:5000/offer", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sdp: offer.sdp, type: offer.type }),
        });
        const answer = await response.json();
        await pc.setRemoteDescription(answer);

        // Now that WebRTC connection is established, show YOLO stream
        setShowYoloStream(true);
      }
    };

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    setStreaming(true);
  }

  async function stopStream() {
    await fetch("http://192.168.4.152:5000/stop_stream", { method: "POST" });
    if (pcRef.current) {
      pcRef.current.close();
      pcRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setStreaming(false);
    setShowYoloStream(false);
  }

  return (
    <div>
      <h1>📷 Raspberry Pi WebRTC Camera</h1>

      <div style={{ display: "flex", gap: "20px" }}>
        {/* Raw WebRTC Stream */}
        <div>
          <h2>Original Stream</h2>
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            style={{
              width: "640px",
              height: "480px",
              border: "2px solid black",
            }}
          />
        </div>

        {/* YOLO Detection Stream */}
        <div>
          <h2>YOLO Detection Stream</h2>
          {showYoloStream ? (
            <img
              src="http://localhost:8000/video_feed"
              alt="YOLO Stream"
              style={{
                width: "640px",
                height: "480px",
                border: "2px solid green",
                objectFit: "cover",
              }}
            />
          ) : (
            <p>Start stream to view YOLO detection</p>
          )}
        </div>
      </div>

      <div style={{ marginTop: 10 }}>
        {!streaming ? (
          <button onClick={startStream}>Start Stream</button>
        ) : (
          <button onClick={stopStream}>Stop Stream</button>
        )}
      </div>
    </div>
  );
}

export default App;
