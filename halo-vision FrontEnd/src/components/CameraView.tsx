import { useEffect, useRef } from "react";
import { socketService } from "../services/socket";

type Props = {
  detections: any[];
  active: boolean;
};

export const CameraView = ({ detections, active }: Props) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const lastSent = useRef(0);

  // CAMERA
  useEffect(() => {
    if (!active) return;

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
  }, [active]);

  // SEND FRAMES
  useEffect(() => {
    if (!active) return;

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
  }, [active]);

  // 🔥 THREAT COLOR
  const threatLevel = detections.length;
  let color = "cyan";

  if (threatLevel >= 3) color = "red";
  else if (threatLevel === 2) color = "yellow";

  return (
    <div style={{ position: "relative" }}>
      <video
        ref={videoRef}
        autoPlay
        playsInline
        style={{ width: "640px", height: "480px" }}
      />

      {detections.map((d: any) => {
        const [x1, y1, x2, y2] = d.bbox;

        return (
          <div
            key={d.id}
            style={{
              position: "absolute",
              top: `${y1}px`,
              left: `${x1}px`,
              width: `${x2 - x1}px`,
              height: `${y2 - y1}px`,
              border: `3px solid ${color}`,
              backgroundColor:
                color === "red"
                  ? "rgba(255,0,0,0.2)"
                  : color === "yellow"
                  ? "rgba(255,255,0,0.2)"
                  : "rgba(0,255,255,0.2)",
              color: "white",
              fontSize: "12px",
              zIndex: 9999,
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