from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageOps
from tenacity import retry, stop_after_attempt, wait_exponential_jitter


@dataclass(frozen=True)
class ProcessedImage:
    source_url: str
    original_path: Path
    preview_path: Path
    sha256: str
    perceptual_hash: str
    mime_type: str


class ImageProcessor:
    def __init__(self, data_dir: str | Path, *, max_bytes: int = 8 * 1024 * 1024) -> None:
        self.data_dir = Path(data_dir)
        self.max_bytes = max_bytes

    async def process_first(
        self,
        *,
        property_id: str,
        image_urls: list[str],
        mode: str = "contain",
    ) -> ProcessedImage | None:
        if not image_urls:
            return None
        try:
            return await self.process_url(property_id=property_id, url=image_urls[0], mode=mode)
        except Exception:
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=0.4, max=4))
    async def process_url(
        self, *, property_id: str, url: str, mode: str = "contain"
    ) -> ProcessedImage:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").split(";")[0].lower()
            content = response.content

        if len(content) > self.max_bytes:
            raise ValueError("image exceeds maximum configured size")
        if content_type and not content_type.startswith("image/"):
            raise ValueError(f"unexpected image MIME type: {content_type}")

        sha256 = hashlib.sha256(content).hexdigest()
        image = Image.open(BytesIO(content))
        image.verify()
        image = Image.open(BytesIO(content)).convert("RGB")
        mime_type = Image.MIME.get(image.format, content_type or "image/jpeg")

        original_dir = self.data_dir / "images" / property_id / "original"
        preview_dir = self.data_dir / "images" / property_id / "preview"
        original_dir.mkdir(parents=True, exist_ok=True)
        preview_dir.mkdir(parents=True, exist_ok=True)

        extension = _extension_for_mime(mime_type)
        original_path = original_dir / f"{sha256}{extension}"
        preview_path = preview_dir / f"{sha256}.jpg"
        if not original_path.exists():
            original_path.write_bytes(content)

        preview = _make_preview(image, mode=mode)
        preview.save(preview_path, format="JPEG", quality=82, optimize=True, exif=b"")

        return ProcessedImage(
            source_url=url,
            original_path=original_path,
            preview_path=preview_path,
            sha256=sha256,
            perceptual_hash=_average_hash(preview),
            mime_type=mime_type,
        )


def _make_preview(image: Image.Image, *, mode: str) -> Image.Image:
    target = (1080, 720)
    if mode == "crop":
        return ImageOps.fit(image, target, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))

    preview = ImageOps.contain(image, target, method=Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", target, (245, 245, 245))
    x = (target[0] - preview.width) // 2
    y = (target[1] - preview.height) // 2
    canvas.paste(preview, (x, y))
    return canvas


def _average_hash(image: Image.Image) -> str:
    small = image.convert("L").resize((8, 8), Image.Resampling.LANCZOS)
    pixels = list(small.getdata())
    average = sum(pixels) / len(pixels)
    bits = "".join("1" if pixel >= average else "0" for pixel in pixels)
    return f"{int(bits, 2):016x}"


def _extension_for_mime(mime_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(mime_type, ".img")
