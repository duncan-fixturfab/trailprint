import io

import numpy as np
from PIL import Image

from trailprint.config import LabelSpec
from trailprint.dem import choose_zoom, decode_terrarium
from trailprint.label import label_solid, text_mask


def test_terrarium_decode():
    # elevation 1234.5 m -> v = 1234.5 + 32768 = 34002.5 -> R=132, G=210, B=128
    img = Image.new("RGB", (2, 2), (132, 210, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    z = decode_terrarium(buf.getvalue())
    assert np.allclose(z, 1234.5)


def test_choose_zoom_monotonic():
    assert choose_zoom(47.0, 100.0) < choose_zoom(47.0, 10.0)
    assert choose_zoom(47.0, 0.001) == 15


def test_text_mask_has_ink():
    mask = text_mask("Hi", 3.0)
    assert mask.any() and not mask.all()


def test_label_solid_sits_on_front_face():
    spec = LabelSpec(text="Test Hill", height_mm=3.0, depth_mm=0.6, margin_mm=2.0)
    mesh = label_solid(spec, (60.0, 40.0), base_mm=7.0)
    assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume > 0
    lo, hi = mesh.bounds
    assert lo[1] >= -0.6 - 1e-6 and hi[1] <= 0.4 + 1e-6  # proud of y=0 face, embedded 0.4
    assert lo[2] > 0 and hi[2] < 7.0
    assert lo[0] >= 2.0 - 1e-6 and hi[0] <= 58.0 + 1e-6


def test_label_other_sides_are_closed():
    for side in ("north", "east", "west"):
        mesh = label_solid(LabelSpec(text="X", side=side), (60.0, 40.0), base_mm=7.0)
        assert mesh.is_watertight and mesh.volume > 0
