import { useEffect, useRef, useState } from "react";
import { socketService } from "../services/socket";

type Detection = {
  id: string;
  label: string;
  depth: number;
  bbox: [number, number, number, number];
};

type Props = {
  setDetections: React.Dispatch<React.SetStateAction<any[]>>;
};

export const CameraView = ({ setDetections }: Props) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const [detections, setLocalDetections] = useState<Detection[]>([]);
  const lastSent = useRef(0);

  // 🎥 CAMERA
  useEffect(() => {
    const startCamera = async () => {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480 },
      });

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.onloadedmetadata = () => {
          videoRef.current?.play();
        };
      }
    };

    startCamera();
  }, []);

  // 🔌 SOCKET (FIXED)
  useEffect(() => {
    socketService.connect((data) => {
      // 🔊 AUDIO
      if (data?.event_type === "SPEECH_AUDIO_READY") {
        const audioBase64 = data.payload?.audio_base64;

        if (audioBase64) {
          const audio = new Audio(
            "data:audio/wav;base64," + audioBase64
          );
          audio.play();
        }
        return;
      }

      // 📦 DETECTIONS
      if (data?.type === "detections") {
       const formatted: Detection[] = data.data.map((obj: any) => ({
              id: obj.id,
              label: obj.label,
              depth: obj.depth,
              bbox: obj.bbox,
            }));
        console.log("✅ FORMATTED::", formatted); // debug

        setLocalDetections(formatted);
        setDetections(formatted);
        return;
      }
    });

    return () => socketService.disconnect();
  }, [setDetections]);

  // 📸 FRAME LOOP
  useEffect(() => {
    let animationFrameId: number;

    const sendFrame = () => {
      const now = Date.now();

      if (now - lastSent.current < 100) {
        animationFrameId = requestAnimationFrame(sendFrame);
        return;
      }

      if (!videoRef.current || !canvasRef.current) {
        animationFrameId = requestAnimationFrame(sendFrame);
        return;
      }

      const video = videoRef.current;
      const canvas = canvasRef.current;
      const ctx = canvas.getContext("2d");

      if (!ctx || video.videoWidth === 0) {
        animationFrameId = requestAnimationFrame(sendFrame);
        return;
      }

      lastSent.current = now;

      canvas.width = 640;
      canvas.height = 480;

      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      canvas.toBlob(
        (blob) => {
          if (!blob) return;

          blob.arrayBuffer().then((buffer) => {
            socketService.sendFrame(buffer);
          });
        },
        "image/jpeg",
        0.6
      );

      animationFrameId = requestAnimationFrame(sendFrame);
    };

    sendFrame();

    return () => cancelAnimationFrame(animationFrameId);
  }, []);

  // 📐 DRAW
  const getVideoSize = () => {
  const video = videoRef.current;
  if (!video) return { width: 640, height: 480 };

  return {
    width: video.clientWidth || 640,
    height: video.clientHeight || 480,
  };
};

  return (
    <div style={{ position: "relative" }}>
      <video
        ref={videoRef}
        autoPlay
        playsInline
        style={{ width: "640px", height: "480px" }}  // ✅ ADD THIS
        />

      {detections.map((d) => {
  const { width, height } = getVideoSize();

  const [x1, y1, x2, y2] = d.bbox;

  const boxWidth = x2 - x1;
  const boxHeight = y2 - y1;

  return (
    <div
      key={d.id}
      className="box"
      style={{
        position: "absolute",
        top: `${(y1 / 480) * height}px`,
        left: `${(x1 / 640) * width}px`,
        width: `${(boxWidth / 640) * width}px`,
        height: `${(boxHeight / 480) * height}px`,
        border: "2px solid cyan",
        color: "cyan",
        fontSize: "12px",
        background: "rgba(0,0,0,0.3)",
      }}
    >
      {d.label}
    </div>
  );
})}

      <canvas ref={canvasRef} style={{ display: "none" }} />
    </div>
  );
};