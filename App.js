import React, { useRef, useState } from "react";

function App() {
  const yoloVideoRef = useRef(null);
  const piVideoRef = useRef(null);
  const yoloPcRef = useRef(null);
  const piPcRef = useRef(null);
  const [streaming, setStreaming] = useState(false);

  // YOLO WebRTC stream
async function startYoloStream() {
  const pc = new RTCPeerConnection({
    iceServers: [{ urls: ["stun:stun.l.google.com:19302"] }],
  });
  yoloPcRef.current = pc;

  pc.ontrack = (event) => {
    console.log("✅ Track received from YOLO:", event.streams[0]);
    if (yoloVideoRef.current) {
      yoloVideoRef.current.srcObject = event.streams[0];
    }
  };

  pc.oniceconnectionstatechange = () => {
    console.log("ICE state:", pc.iceConnectionState);
  };

  pc.addTransceiver("video", { direction: "recvonly" });

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  console.log("📤 Sending offer to YOLO server...");
  const response = await fetch("http://localhost:8000/offer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sdp: offer.sdp, type: offer.type }),
  });

  const answer = await response.json();
  console.log("📥 Received answer from YOLO server.");
  await pc.setRemoteDescription(answer);
}


  // Pi WebRTC stream
  async function startPiStream() {
    const pc = new RTCPeerConnection();
    piPcRef.current = pc;

    pc.ontrack = (event) => {
      if (piVideoRef.current) {
        piVideoRef.current.srcObject = event.streams[0];
      }
    };
    pc.addTransceiver("video", { direction: "recvonly" });
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    const response = await fetch("http://192.168.4.117:5000/offer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sdp: offer.sdp, type: offer.type }),
    });

    const answer = await response.json();
    await pc.setRemoteDescription(answer);
  }

  async function startStream() {
    await startPiStream();
    await startYoloStream();
    setStreaming(true);
  }

  async function stopStream() {
    if (yoloPcRef.current) yoloPcRef.current.close();
    if (piPcRef.current) piPcRef.current.close();
    if (yoloVideoRef.current) yoloVideoRef.current.srcObject = null;
    if (piVideoRef.current) piVideoRef.current.srcObject = null;
    setStreaming(false);
  }

  return (
    <div>
      <h1>📷 YOLO & Pi WebRTC Streams</h1>
      <div style={{ display: "flex", gap: "10px" }}>
        <div>
          <h3>Pi Camera</h3>
          <video ref={piVideoRef} autoPlay playsInline muted width={320} height={240} />
        </div>
        <div>
          <h3>YOLO Processed</h3>
          <video ref={yoloVideoRef} autoPlay playsInline muted width={320} height={240} />
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
