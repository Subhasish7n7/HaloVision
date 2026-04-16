import { useEffect, useRef, useState } from "react";
import { socketService } from "../services/socket";

type Detection = {
  id: string;
  label: string;
  depth: number;
  bbox: [number, number, number, number];
  lastSeen?: number;
};

type Props = {
  setDetections: React.Dispatch<React.SetStateAction<any[]>>;
};

export const CameraView = ({ setDetections }: Props) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const [detections, setLocalDetections] = useState<Detection[]>([]);
  const lastSent = useRef(0);

  // 🎥 CAMERA START
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

  // 🔌 SOCKET CONNECTION
  useEffect(() => {
    socketService.connect((data) => {
      // 🔊 AUDIO RESPONSE
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

      // 📦 DETECTIONS (FIXED TRACKING)
      if (data?.type === "detections") {
        const now = Date.now();

        // 🔥 LOCAL STATE (BOX DRAWING)
        setLocalDetections((prev) => {
          const updated: Record<string, Detection> = {};

          // keep previous
          prev.forEach((d) => {
            updated[d.id] = d;
          });

          // update new
          data.data.forEach((obj: any) => {
            updated[obj.id] = {
              id: obj.id,
              label: obj.label,
              depth: obj.depth,
              bbox: obj.bbox,
              lastSeen: now,
            };
          });

          // remove old (not seen recently)
          return Object.values(updated).filter(
            (d) => now - (d.lastSeen || now) < 500
          );
        });

        // 🔥 GLOBAL STATE (RIGHT PANEL)
        setDetections((prev: any[]) => {
          const updated: Record<string, any> = {};

          prev.forEach((d) => {
            updated[d.id] = d;
          });

          data.data.forEach((obj: any) => {
            updated[obj.id] = {
              ...obj,
              lastSeen: now,
            };
          });

          return Object.values(updated).filter(
            (d: any) => now - (d.lastSeen || now) < 500
          );
        });

        return;
      }
    });

    return () => socketService.disconnect();
  }, [setDetections]);

  // 📸 FRAME SENDER LOOP
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

  // 📐 GET VIDEO SIZE
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
        style={{ width: "640px", height: "480px" }}
      />

      {/* 📦 DRAW BOXES */}
      {detections.map((d) => {
        const { width, height } = getVideoSize();
        const [x1, y1, x2, y2] = d.bbox;

        const boxWidth = x2 - x1;
        const boxHeight = y2 - y1;

        return (
          <div
            key={d.id}
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
              display: "flex",
              alignItems: "flex-start",
              padding: "2px",
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