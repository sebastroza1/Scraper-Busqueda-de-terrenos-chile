from PIL import Image

from landfinder.images.processor import _average_hash, _make_preview


def test_preview_is_1080_720_without_deformation() -> None:
    source = Image.new("RGB", (400, 400), (10, 20, 30))
    preview = _make_preview(source, mode="contain")
    assert preview.size == (1080, 720)
    assert _average_hash(preview)
