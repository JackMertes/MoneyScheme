from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Union

from PIL import Image

from moneyscheme.capture.screen import capture_region, load_image
from moneyscheme.config import Settings, get_settings
from moneyscheme.models import Opportunity
from moneyscheme.ocr.engine import ocr_image, preprocess_for_ocr
from moneyscheme.ocr.parse import parse_opportunities


def opportunities_from_image(image: Image.Image) -> List[Opportunity]:
    scaled = preprocess_for_ocr(image, scale=1.5)
    tokens = ocr_image(scaled)
    # Scale factor applied: header x positions are in scaled coords; width too.
    return parse_opportunities(tokens, image_width=scaled.size[0])


def opportunities_from_path(path: Union[str, Path]) -> List[Opportunity]:
    return opportunities_from_image(load_image(path))


def capture_screen_image(
    settings: Optional[Settings] = None,
    *,
    save_dir: Union[str, Path] = "fixtures/screenshots",
) -> Tuple[Image.Image, Path]:
    """Capture the configured ROI and always save a PNG copy."""
    settings = settings or get_settings()
    image = capture_region(settings.capture_region())
    out_dir = Path(save_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"live-{ts}.png"
    image.save(path)
    return image, path


def opportunities_from_screen(
    settings: Optional[Settings] = None,
    *,
    save_dir: Union[str, Path] = "fixtures/screenshots",
) -> Tuple[List[Opportunity], Path]:
    image, path = capture_screen_image(settings, save_dir=save_dir)
    return opportunities_from_image(image), path
