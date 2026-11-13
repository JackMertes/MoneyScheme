from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import mss
import numpy as np
from PIL import Image


def capture_region(region: Optional[dict[str, int]] = None) -> Image.Image:
    """Grab the screen (or a ROI) and return a PIL RGB image."""
    with mss.mss() as sct:
        monitor = region if region is not None else sct.monitors[1]
        shot = sct.grab(monitor)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        return img


def load_image(path: Union[str, Path]) -> Image.Image:
    """Load a fixture or saved screenshot as RGB."""
    return Image.open(path).convert("RGB")


def image_to_bgr(image: Image.Image) -> np.ndarray:
    """PIL RGB → OpenCV BGR ndarray."""
    rgb = np.array(image)
    return rgb[:, :, ::-1].copy()
