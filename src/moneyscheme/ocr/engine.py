from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import List

import numpy as np
from PIL import Image


@dataclass
class OcrToken:
    text: str
    conf: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@lru_cache(maxsize=1)
def _get_engine():
    from rapidocr import RapidOCR

    return RapidOCR()


def ocr_image(image: Image.Image) -> List[OcrToken]:
    """Run OCR and return positioned tokens."""
    engine = _get_engine()
    # RapidOCR accepts RGB/BGR ndarray; pass RGB from PIL.
    rgb = np.array(image.convert("RGB"))
    output = engine(rgb)

    tokens: List[OcrToken] = []
    boxes = getattr(output, "boxes", None)
    txts = getattr(output, "txts", None)
    scores = getattr(output, "scores", None)
    if boxes is None or txts is None:
        return tokens

    for box, text, score in zip(boxes, txts, scores or [1.0] * len(txts)):
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        tokens.append(
            OcrToken(
                text=str(text).strip(),
                conf=float(score),
                x0=min(xs),
                y0=min(ys),
                x1=max(xs),
                y1=max(ys),
            )
        )
    return tokens


def preprocess_for_ocr(image: Image.Image, scale: float = 1.5) -> Image.Image:
    """Upscale dark UI slightly for cleaner OCR."""
    if scale == 1.0:
        return image
    w, h = image.size
    return image.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
