# =============================================================================
# FILE: App/Perception/inference_backend.py
# ROLE: Hardware auto-detection and inference backend selection.
#
# WHAT THIS FILE DOES:
#   Detects the available hardware (GPU, Intel CPU, etc.) and selects
#   the best inference backend for depth estimation:
#   - TensorRT (NVIDIA GPU) — fastest
#   - OpenVINO (Intel CPU/GPU/NPU) — optimized for Intel
#   - ONNX Runtime (general CPU/GPU) — good cross-platform default
#   - PyTorch (fallback) — always available
#
# WHY THIS EXISTS:
#   Different machines have different hardware. This module ensures
#   HaloVision runs optimally on whatever hardware is available,
#   without requiring manual configuration.
#
# WHO CALLS THIS:
#   main.py calls resolve_backend() at startup to pick the best backend.
#   The resolved backend string is then passed to create_depth_estimator().
#
# SELECTION LOGIC (auto mode):
#   1. NVIDIA GPU present → TensorRT (if installed), else ONNX Runtime
#   2. Intel CPU → OpenVINO (if installed), else ONNX Runtime
#   3. General CPU/GPU → ONNX Runtime (if installed), else PyTorch
#
# NOTE: The detection/tracking pipeline (YOLO) always runs on PyTorch/Ultralytics.
# This backend selection only affects depth estimation and any future model slots.
# =============================================================================

import importlib.util
import logging
import os

logger = logging.getLogger(__name__)

# Fallback chain: if a requested backend is unavailable, try these in order
_FALLBACK_CHAIN = ("onnxruntime", "torch")

# ONNX Runtime provider lists for each backend
# These tell ONNX Runtime which hardware accelerators to use
_ORT_PROVIDERS = {
    "onnxruntime": ["CPUExecutionProvider"],
    "openvino": ["OpenVINOExecutionProvider", "CPUExecutionProvider"],
    "tensorrt": ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"],
}


def _installed(module: str) -> bool:
    """Check if a Python module is installed (without importing it)."""
    return importlib.util.find_spec(module) is not None


def is_cuda_available() -> bool:
    """Check if NVIDIA CUDA GPU is available via PyTorch."""
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _detect_hardware_hint() -> str:
    """Detect the hardware type: "gpu" (NVIDIA), "intel" (Intel CPU), or "generic".
    Used by auto-detection to pick the optimal backend."""
    if is_cuda_available():
        return "gpu"
    try:
        import platform
        proc = platform.processor().lower()
        if "intel" in proc or (platform.system().lower() == "windows" and "amd" not in proc):
            return "intel"
    except Exception:
        pass
    return "generic"


def backend_available(backend: str) -> bool:
    """Check if a specific backend is available on this machine."""
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

    This is the main entry point — called once at startup from main.py.

    Input: requested backend string (from env var, system setting, or None)
    Output: resolved backend string (never an unavailable backend)

    Flow:
        "auto" → detect hardware → pick best available → fallback chain
        "tensorrt" → check if available → fallback chain if not
        None → treat as "auto"
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

    # Requested backend is not available — try fallback chain
    logger.warning(f"[Inference] backend '{requested}' unavailable on this machine")
    for fallback in _FALLBACK_CHAIN:
        if backend_available(fallback):
            logger.info(f"[Inference] falling back to '{fallback}'")
            return fallback
    return "torch"


def onnx_providers(backend: str) -> list:
    """Get the ONNX Runtime provider list for a given backend.
    Filters out providers that aren't actually installed on this machine."""
    providers = _ORT_PROVIDERS.get(backend, _ORT_PROVIDERS["onnxruntime"])
    if backend in ("openvino", "tensorrt"):
        import onnxruntime as ort
        available = set(ort.get_available_providers())
        providers = [p for p in providers if p in available] or ["CPUExecutionProvider"]
    return providers


def describe(backend: str) -> str:
    """Human-readable description of a backend (for logging)."""
    labels = {
        "onnxruntime": "ONNX Runtime (general CPU/GPU)",
        "openvino": "OpenVINO (Intel CPU/GPU/NPU)",
        "tensorrt": "TensorRT (NVIDIA GPU)",
        "torch": "PyTorch native",
    }
    return labels.get(backend, backend)
