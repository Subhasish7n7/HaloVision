# =============================================================================
# FILE: App/Perception/depth_estimator.py
# ROLE: Depth estimation backends — converts 2D images into depth maps.
#
# WHAT THIS FILE DOES:
#   Provides multiple depth estimation implementations:
#   1. MiDaSDepthEstimator — PyTorch-based (DPT_Hybrid or MiDaS_small)
#   2. ONNXDepthEstimator — ONNX Runtime-based (MiDaS_small exported to ONNX)
#   3. create_depth_estimator() — factory function that picks the best one
#
# ALL DEPTH ESTIMATORS SHARE THE SAME CONTRACT:
#   predict(frame) → np.ndarray of shape (H, W), float, normalized to 0..1
#   Where 0 = far away, 1 = very close (or vice versa depending on MiDaS output)
#
# WHO CALLS THIS:
#   main.py calls create_depth_estimator() at startup to create a depth model.
#   The returned estimator is passed to DepthUpdater, which calls predict()
#   asynchronously on camera frames.
#
# WHERE THE RESULT GOES:
#   DepthUpdater stores the depth map → PerceptionSystem reads it
#       → _extract_depth() gets per-object depth → ObjectData.depth_norm
#           → ReasoningLayer uses depth for threat evaluation
#               → RuleEngine uses depth for navigation/speech
#
# KEY DESIGN DECISION:
#   MiDaS_small is exported to ONNX for faster inference. The ONNX path
#   avoids PyTorch overhead and can use hardware-specific accelerators
#   (OpenVINO on Intel, TensorRT on NVIDIA).
# =============================================================================

import logging
import os

import cv2
import numpy as np
import torch

from App.Perception.inference_backend import onnx_providers

logger = logging.getLogger(__name__)

# ImageNet normalization constants (used by MiDaS preprocessing)
_MIDAS_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_MIDAS_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
_SMALL_SIZE = 256  # Input resolution for MiDaS_small model
_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")


def _DEFAULT_ONNX_PATH():
    """Default path for the pre-exported MiDaS_small ONNX model file."""
    return os.path.join(_MODEL_DIR, "midas_small.onnx")


def _normalize01(depth: np.ndarray) -> np.ndarray:
    """Normalize a depth map to the 0-1 range.
    MiDaS outputs raw relative depth values; this maps them to a
    consistent 0-1 range for downstream processing."""
    dmin = float(depth.min())
    dmax = float(depth.max())
    if dmax - dmin < 1e-6:
        return np.zeros_like(depth, dtype=np.float32)
    return ((depth - dmin) / (dmax - dmin)).astype(np.float32)


class MiDaSDepthEstimator:
    """Original PyTorch MiDaS estimator using torch hub.

    Supports two model types:
    - DPT_Hybrid: more accurate, slower (default for "balanced" quality)
    - MiDaS_small: faster, less accurate (default for "fast" quality)

    The model is loaded once at startup and reused for every frame.
    """

    def __init__(self, model_type="DPT_Hybrid"):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        # Load model from PyTorch Hub — downloads on first use
        self.model = torch.hub.load("intel-isl/MiDaS", model_type)
        self.model.to(self.device)
        self.model.eval()  # Set to evaluation mode (disables dropout, etc.)

        # Load the appropriate preprocessing transforms for the model type
        transforms = torch.hub.load("intel-isl/MiDaS", "transforms")
        if model_type in ["DPT_Large", "DPT_Hybrid"]:
            self.transform = transforms.dpt_transform
        else:
            self.transform = transforms.small_transform

    def predict(self, frame):
        """Run depth prediction on a single frame.

        Input: OpenCV frame (numpy BGR array)
        Output: depth map (numpy float32, same HxW as input, normalized 0-1)

        Flow:
            BGR frame → RGB conversion → MiDaS transform → model inference
                → resize to original resolution → normalize to 0-1
        """
        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        input_batch = self.transform(img).to(self.device)

        with torch.no_grad():  # No gradient computation needed for inference
            prediction = self.model(input_batch)
            # Resize prediction back to original image dimensions
            prediction = torch.nn.functional.interpolate(
                prediction.unsqueeze(1),
                size=img.shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze()

        depth = prediction.cpu().numpy()
        return _normalize01(depth)


def export_midas_small_onnx(out_path: str):
    """Export MiDaS_small to a fixed 256x256 ONNX model.
    This is a one-time operation — the exported file is reused on subsequent runs.
    The exported graph is the raw network only (input 1x3x256x256 → 1x256x256);
    preprocessing/normalization stays in ONNXDepthEstimator."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    model = torch.hub.load("intel-isl/MiDaS", "MiDaS_small")
    model.eval()

    # Create a dummy input for ONNX export tracing
    dummy = torch.randn(1, 3, _SMALL_SIZE, _SMALL_SIZE)
    torch.onnx.export(
        model,
        dummy,
        out_path,
        input_names=["image"],
        output_names=["depth"],
        opset_version=17,
        dynamic_axes={"image": {0: "batch"}, "depth": {0: "batch"}},
    )
    logger.info(f"[Depth] ONNX exported: {out_path}")
    return out_path


class ONNXDepthEstimator:
    """MiDaS_small via ONNX Runtime — faster than PyTorch for inference.

    Supports multiple execution providers:
    - CPUExecutionProvider: generic CPU (always available)
    - OpenVINOExecutionProvider: Intel-optimized (faster on Intel CPUs)
    - TensorRTExecutionProvider: NVIDIA GPU (fastest on NVIDIA GPUs)

    The provider is determined by inference_backend.py at startup.
    """

    def __init__(self, model_path: str, backend: str = "onnxruntime"):
        import onnxruntime as ort

        # Create ONNX inference session with the appropriate providers
        self.session = ort.InferenceSession(
            model_path,
            providers=onnx_providers(backend),
        )
        self._input_name = self.session.get_inputs()[0].name  # "image"

    def predict(self, frame):
        """Run depth prediction using ONNX Runtime.

        Input: OpenCV frame (numpy BGR array)
        Output: depth map (numpy float32, same HxW as input, normalized 0-1)

        Flow:
            BGR frame → RGB → resize to 256x256 → normalize (ImageNet stats)
                → transpose to CHW format → ONNX inference → resize to original
                → normalize to 0-1
        """
        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (_SMALL_SIZE, _SMALL_SIZE))
        # Normalize with ImageNet stats and reorder to NCHW format for ONNX
        x = img.astype(np.float32) / 255.0
        x = (x - _MIDAS_MEAN) / _MIDAS_STD
        x = np.transpose(x, (2, 0, 1))[None]  # HWC → NCHW (add batch dim)

        out = self.session.run(None, {self._input_name: x})[0][0]  # (256, 256)
        # Resize depth map back to original frame dimensions
        out = cv2.resize(out, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_CUBIC)
        return _normalize01(out)


def create_depth_estimator(backend: str = "onnxruntime", quality: str = "fast",
                           onnx_path: str = None):
    """Factory function: pick the best depth estimator for the current hardware.

    Called once at startup from main.py. Returns an estimator instance
    that will be passed to DepthUpdater.

    Quality modes:
    - "fast" (default): MiDaS_small — smaller model, faster inference
    - "balanced": DPT_Hybrid — larger model, better accuracy

    Backend priority for "fast" quality:
    1. ONNX Runtime (if model file exists) → ONNXDepthEstimator
    2. Export MiDaS_small to ONNX → ONNXDepthEstimator
    3. Fall back to PyTorch MiDaS_small → MiDaSDepthEstimator
    """
    onnx_path = onnx_path or _DEFAULT_ONNX_PATH()
    if quality == "balanced":
        logger.info("[Depth] balanced quality -> MiDaS DPT_Hybrid (torch)")
        return MiDaSDepthEstimator(model_type="DPT_Hybrid")

    if backend == "torch":
        logger.info("[Depth] fast quality + torch backend -> MiDaS_small (torch)")
        return MiDaSDepthEstimator(model_type="MiDaS_small")

    # Try ONNX Runtime first (or OpenVINO/TensorRT via ORT providers)
    if onnx_path and os.path.exists(onnx_path):
        logger.info(f"[Depth] fast quality + {backend} backend -> ONNX {onnx_path}")
        try:
            return ONNXDepthEstimator(onnx_path, backend=backend)
        except Exception as e:
            logger.warning(f"[Depth] ONNX init failed ({e}) - falling back to torch")
    else:
        # Auto-export the ONNX model if it doesn't exist yet
        logger.info("[Depth] ONNX model missing - exporting MiDaS_small")
        try:
            export_midas_small_onnx(onnx_path)
            return ONNXDepthEstimator(onnx_path, backend=backend)
        except Exception as e:
            logger.warning(f"[Depth] ONNX export failed ({e}) - using torch MiDaS_small")

    return MiDaSDepthEstimator(model_type="MiDaS_small")
