# perception/depth_estimator.py
"""Depth estimation backends.

- ``MiDaSDepthEstimator``  - the original PyTorch path (DPT_Hybrid / MiDaS_small)
- ``ONNXDepthEstimator``   - MiDaS_small exported to ONNX, run via any
                             onnxruntime provider (CPU / OpenVINO / TensorRT)
- ``create_depth_estimator`` - factory honouring the resolved inference backend

All estimators share the same contract: ``predict(frame) -> np.ndarray`` of
shape (H, W), float, normalized to 0..1 (unchanged downstream behaviour).
"""

import logging
import os

import cv2
import numpy as np
import torch

from App.Perception.inference_backend import onnx_providers

logger = logging.getLogger(__name__)

_MIDAS_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_MIDAS_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
_SMALL_SIZE = 256
_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")


def _DEFAULT_ONNX_PATH():
    return os.path.join(_MODEL_DIR, "midas_small.onnx")


def _normalize01(depth: np.ndarray) -> np.ndarray:
    dmin = float(depth.min())
    dmax = float(depth.max())
    if dmax - dmin < 1e-6:
        return np.zeros_like(depth, dtype=np.float32)
    return ((depth - dmin) / (dmax - dmin)).astype(np.float32)


class MiDaSDepthEstimator:
    """Original PyTorch MiDaS estimator (torch hub)."""

    def __init__(self, model_type="DPT_Hybrid"):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = torch.hub.load("intel-isl/MiDaS", model_type)
        self.model.to(self.device)
        self.model.eval()

        transforms = torch.hub.load("intel-isl/MiDaS", "transforms")
        if model_type in ["DPT_Large", "DPT_Hybrid"]:
            self.transform = transforms.dpt_transform
        else:
            self.transform = transforms.small_transform

    def predict(self, frame):
        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        input_batch = self.transform(img).to(self.device)

        with torch.no_grad():
            prediction = self.model(input_batch)
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

    The exported graph is the raw network only (input 1x3x256x256 →
    1x256x256); preprocessing/normalization stays in ONNXDepthEstimator and
    mirrors the torch small transform exactly.
    """
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    model = torch.hub.load("intel-isl/MiDaS", "MiDaS_small")
    model.eval()

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
    """MiDaS_small via ONNX Runtime (CPU / OpenVINO / TensorRT providers)."""

    def __init__(self, model_path: str, backend: str = "onnxruntime"):
        import onnxruntime as ort

        self.session = ort.InferenceSession(
            model_path,
            providers=onnx_providers(backend),
        )
        self._input_name = self.session.get_inputs()[0].name

    def predict(self, frame):
        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (_SMALL_SIZE, _SMALL_SIZE))
        x = img.astype(np.float32) / 255.0
        x = (x - _MIDAS_MEAN) / _MIDAS_STD
        x = np.transpose(x, (2, 0, 1))[None]

        out = self.session.run(None, {self._input_name: x})[0][0]  # (256, 256)
        out = cv2.resize(out, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_CUBIC)
        return _normalize01(out)


def create_depth_estimator(backend: str = "onnxruntime", quality: str = "fast",
                           onnx_path: str = None):
    """Factory used by the app: pick a fast (MiDaS_small) or balanced
    (DPT_Hybrid) estimator, executed on the resolved inference backend.

    quality: "fast" -> MiDaS_small (torch or ONNX), "balanced" -> DPT_Hybrid (torch)
    """
    onnx_path = onnx_path or _DEFAULT_ONNX_PATH()
    if quality == "balanced":
        logger.info("[Depth] balanced quality -> MiDaS DPT_Hybrid (torch)")
        return MiDaSDepthEstimator(model_type="DPT_Hybrid")

    if backend == "torch":
        logger.info("[Depth] fast quality + torch backend -> MiDaS_small (torch)")
        return MiDaSDepthEstimator(model_type="MiDaS_small")

    # ONNX Runtime (or OpenVINO/TensorRT via ORT providers).
    if onnx_path and os.path.exists(onnx_path):
        logger.info(f"[Depth] fast quality + {backend} backend -> ONNX {onnx_path}")
        try:
            return ONNXDepthEstimator(onnx_path, backend=backend)
        except Exception as e:
            logger.warning(f"[Depth] ONNX init failed ({e}) - falling back to torch")
    else:
        logger.info("[Depth] ONNX model missing - exporting MiDaS_small")
        try:
            export_midas_small_onnx(onnx_path)
            return ONNXDepthEstimator(onnx_path, backend=backend)
        except Exception as e:
            logger.warning(f"[Depth] ONNX export failed ({e}) - using torch MiDaS_small")

    return MiDaSDepthEstimator(model_type="MiDaS_small")