from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

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


def opportunities_from_screen(settings: Optional[Settings] = None) -> List[Opportunity]:
    settings = settings or get_settings()
    image = capture_region(settings.capture_region())
    return opportunities_from_image(image)
