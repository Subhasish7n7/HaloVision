"""Inference backend abstraction for HaloVision.

Supported backends (interchangeable, resolved once at startup):

    INFERENCE_BACKEND=onnxruntime   -> ONNX Runtime (CPU / GPU EP)
    INFERENCE_BACKEND=openvino      -> OpenVINO (Intel CPU/GPU/NPU) via ORT provider
    INFERENCE_BACKEND=tensorrt      -> TensorRT (NVIDIA GPU) via ORT provider
    INFERENCE_BACKEND=torch         -> PyTorch native execution
    INFERENCE_BACKEND=auto          -> hardware-aware selection (default)

Selection rules (auto):
    1. NVIDIA GPU present  -> tensorrt (if the provider is installed), else onnxruntime
    2. Intel CPU           -> openvino (if installed), else onnxruntime
    3. General CPU/GPU     -> onnxruntime (if installed), else torch

The detection/tracking pipeline stays on ultralytics (torch) — ByteTrack
identity stability is preserved; depth estimation and any future model slot
consume this factory so switching runtimes never rewrites the pipeline.
"""

import importlib.util
import logging
import os

logger = logging.getLogger(__name__)

# Order of preference when a requested backend is unavailable.
_FALLBACK_CHAIN = ("onnxruntime", "torch")

# Provider lists handed to onnxruntime.InferenceSession per backend.
_ORT_PROVIDERS = {
    "onnxruntime": ["CPUExecutionProvider"],
    "openvino": ["OpenVINOExecutionProvider", "CPUExecutionProvider"],
    "tensorrt": ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"],
}


def _installed(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def is_cuda_available() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _detect_hardware_hint() -> str:
    if is_cuda_available():
        return "gpu"
    try:
        import platform
        proc = platform.processor().lower()
        if "intel" in proc or platform.system().lower() == "windows" and "amd" not in proc:
            return "intel"
    except Exception:
        pass
    return "generic"


def backend_available(backend: str) -> bool:
    if backend == "onnxruntime":
        return _installed("onnxruntime")
    if backend == "openvino":
        return _installed("openvino")
    if backend == "tensorrt":
        return _installed("tensorrt") and is_cuda_available()
    if backend == "torch":
        return _installed("torch")
    return False


def resolve_backend(requested: str = None) -> str:
    """Pick the active inference backend.

    `requested` may come from the INFERENCE_BACKEND env var, a system
    setting, or None for auto-detection. Never returns an unavailable
    backend — it degrades through the fallback chain with a warning.
    """
    requested = (requested or os.getenv("INFERENCE_BACKEND") or "auto").strip().lower()

    if requested == "auto":
        hint = _detect_hardware_hint()
        logger.info(f"[Inference] auto-detection hint={hint}")
        if hint == "gpu" and backend_available("tensorrt"):
            return "tensorrt"
        if hint == "intel" and backend_available("openvino"):
            return "openvino"
        if backend_available("onnxruntime"):
            return "onnxruntime"
        return "torch"

    if requested not in ("onnxruntime", "openvino", "tensorrt", "torch"):
        logger.warning(f"[Inference] unknown backend '{requested}' - using auto")
        return resolve_backend(None)

    if backend_available(requested):
        return requested

    logger.warning(f"[Inference] backend '{requested}' unavailable on this machine")
    for fallback in _FALLBACK_CHAIN:
        if backend_available(fallback):
            logger.info(f"[Inference] falling back to '{fallback}'")
            return fallback
    return "torch"


def onnx_providers(backend: str) -> list:
    """Providers to hand to onnxruntime for a given resolved backend."""
    providers = _ORT_PROVIDERS.get(backend, _ORT_PROVIDERS["onnxruntime"])
    if backend in ("openvino", "tensorrt"):
        import onnxruntime as ort
        available = set(ort.get_available_providers())
        providers = [p for p in providers if p in available] or ["CPUExecutionProvider"]
    return providers


def describe(backend: str) -> str:
    labels = {
        "onnxruntime": "ONNX Runtime (general CPU/GPU)",
        "openvino": "OpenVINO (Intel CPU/GPU/NPU)",
        "tensorrt": "TensorRT (NVIDIA GPU)",
        "torch": "PyTorch native",
    }
    return labels.get(backend, backend)