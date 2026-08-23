"""Provider-neutral image generation tool with media-store integration.

Built-in providers: DALL-E (OpenAI), Imagen (Google), SDXL (Stability AI), Midjourney (via API).
"""

from __future__ import annotations

import base64
import inspect
import json
import os
from typing import Any, Protocol

import aiohttp

from alcyoneus.core.state.message_block import MediaRef
from alcyoneus.utils.decorators import tool


class ImageProvider(Protocol):
    """Application/provider contract consumed by ``generate_image``."""

    def __call__(self, request: dict[str, Any]) -> Any:
        """Return image bytes, URLs, MediaRefs, or dictionaries."""


def create_image_generator(provider: ImageProvider, media_store: Any | None = None):
    """Create a configured generator with optional media persistence."""

    async def _generate(request: dict[str, Any]) -> Any:
        result = provider(request)
        return await result if inspect.isawaitable(result) else result

    return _generate


async def _openai_dalle(request: dict[str, Any]) -> list[dict]:
    """DALL-E 2/3 via OpenAI API."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    model = request.get("model", "dall-e-3")
    size = request.get("size", "1024x1024")
    count = min(request.get("count", 1), 10)
    quality = request.get("quality", "standard")
    style = request.get("style", "vivid")
    async with aiohttp.ClientSession() as sess, sess.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "prompt": request["prompt"],
            "n": count,
            "size": size,
            "quality": quality,
            "style": style,
        },
        timeout=aiohttp.ClientTimeout(total=120),
    ) as resp:
        data = await resp.json()
    outputs = []
    for item in data.get("data", []):
        url = item.get("url")
        b64 = item.get("b64_json")
        outputs.append(
            url if url else {"kind": "data", "mime_type": "image/png", "data_base64": b64}
        )
    return outputs


async def _google_imagen(request: dict[str, Any]) -> list[dict]:
    """Imagen via Google Vertex AI."""
    try:
        from google.cloud import aiplatform  # noqa: F401
        from vertexai.preview.vision_models import ImageGenerationModel
    except ImportError:
        raise RuntimeError("google-cloud-aiplatform and vertexai required")
    model_name = request.get("model", "imagegeneration@005")
    model = ImageGenerationModel.from_pretrained(model_name)
    images = model.generate_images(
        prompt=request["prompt"],
        number_of_images=min(request.get("count", 1), 4),
        aspect_ratio=request.get("aspect_ratio", "1:1"),
        safety_filter_level="block_some",
        person_generation="allow_adult",
    )
    outputs = []
    for img in images:
        outputs.append(
            {
                "kind": "data",
                "mime_type": "image/png",
                "data_base64": base64.b64encode(img._image_bytes).decode(),
            }
        )
    return outputs


async def _stability_sdxl(request: dict[str, Any]) -> list[dict]:
    """SDXL via Stability AI API."""
    api_key = os.getenv("STABILITY_API_KEY")
    if not api_key:
        raise RuntimeError("STABILITY_API_KEY not set")
    async with (
        aiohttp.ClientSession() as sess,
        sess.post(
            "https://api.stability.ai/v2beta/stable-image/generate/sdxl",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "image/*"},
            data={
                "prompt": request["prompt"],
                "aspect_ratio": request.get("aspect_ratio", "1:1"),
                "seed": request.get("seed", 0),
                "output_format": "png",
            },
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp,
    ):
        if resp.status != 200:
            raise RuntimeError(f"Stability AI error: {await resp.text()}")
        img_bytes = await resp.read()
    return [
        {
            "kind": "data",
            "mime_type": "image/png",
            "data_base64": base64.b64encode(img_bytes).decode(),
        }
    ]


async def _midjourney(request: dict[str, Any]) -> list[dict]:
    """Midjourney via unofficial API (requires proxy service)."""
    api_key = os.getenv("MIDJOURNEY_API_KEY")
    api_url = os.getenv("MIDJOURNEY_API_URL", "https://api.midjourney.com")
    if not api_key:
        raise RuntimeError("MIDJOURNEY_API_KEY not set")
    async with (
        aiohttp.ClientSession() as sess,
        sess.post(
            f"{api_url}/imagine",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"prompt": request["prompt"], "aspect_ratio": request.get("aspect_ratio", "1:1")},
            timeout=aiohttp.ClientTimeout(total=180),
        ) as resp,
    ):
        data = await resp.json()
    # Assuming response has image URLs
    outputs = []
    for url in data.get("image_urls", []):
        outputs.append(url)
    return outputs


async def _provider_generator(request: dict[str, Any], config: dict[str, Any]) -> Any:
    """Use an explicitly supplied provider client when no custom callback exists."""
    provider = str(config.get("image_provider") or "").lower()
    client = config.get("image_client")
    if client is None:
        # Built-in provider selection
        if provider == "openai":
            return await _openai_dalle(request)
        if provider == "google":
            return await _google_imagen(request)
        if provider == "stability":
            return await _stability_sdxl(request)
        if provider == "midjourney":
            return await _midjourney(request)
        raise RuntimeError(
            "image_provider must be 'openai', 'google', 'stability', 'midjourney' or provide image_client"  # noqa: E501
        )
    # Custom client path
    if provider == "google":
        generator = getattr(client, "aio", client).models.generate_images
        response = generator(
            model=config.get("image_model"),
            prompt=request["prompt"],
            config={"number_of_images": request["count"], "aspect_ratio": request["aspect_ratio"]},
        )
        return await response if inspect.isawaitable(response) else response
    if provider == "openai":
        response = client.images.generate(
            model=config.get("image_model"),
            prompt=request["prompt"],
            size=request["size"] or "1024x1024",
            n=request["count"],
        )
        response = await response if inspect.isawaitable(response) else response
        outputs = []
        for item in response.data:
            url = getattr(item, "url", None)
            b64 = getattr(item, "b64_json", None)
            outputs.append(
                url if url else {"kind": "data", "mime_type": "image/png", "data_base64": b64}
            )
        return outputs
    raise RuntimeError("unsupported image_provider with custom client")


@tool(
    name="generate_image",
    description="Generate or edit an image through the configured image provider.",
    tags=["image", "multimodal", "generation"],
    capabilities=["generate_images", "write_media"],
)
async def generate_image(
    prompt: str,
    size: str | None = None,
    aspect_ratio: str | None = None,
    count: int = 1,
    reference_images: list[dict[str, Any]] | None = None,
    mask: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> str:
    """Call a configured provider and persist returned bytes when possible."""
    if not prompt.strip():
        return json.dumps({"error": "prompt is required", "tool": "generate_image"})
    cfg = config or {}
    generator = cfg.get("image_generator")
    if generator is None:

        def generator(request: dict[str, Any]) -> Any:
            return _provider_generator(request, cfg)

    request = {
        "prompt": prompt,
        "size": size,
        "aspect_ratio": aspect_ratio,
        "count": max(1, min(int(count), 16)),
        "reference_images": reference_images or [],
        "mask": mask,
        "model": cfg.get("image_model"),
        "quality": cfg.get("quality", "standard"),
        "style": cfg.get("style", "vivid"),
        "seed": cfg.get("seed"),
    }
    result = generator(request)
    if inspect.isawaitable(result):
        result = await result
    values = result if isinstance(result, list) else [result]
    store = cfg.get("media_store")
    outputs: list[dict[str, Any]] = []
    for value in values:
        if isinstance(value, MediaRef):
            outputs.append(value.model_dump())
            continue
        if isinstance(value, str):
            outputs.append(MediaRef(kind="url", url=value, mime_type="image/png").model_dump())
            continue
        if isinstance(value, dict):
            outputs.append(value)
            continue
        if isinstance(value, bytes):
            if store is not None:
                key = await store.store(value, "image/png", {"prompt": prompt})
                outputs.append(store.to_media_ref(key, "image/png").model_dump())
            else:
                outputs.append(
                    {
                        "kind": "data",
                        "mime_type": "image/png",
                        "data_base64": base64.b64encode(value).decode(),
                    }
                )
            continue
        raise TypeError(f"unsupported image provider result: {type(value).__name__}")
    return json.dumps({"status": "generated", "images": outputs}, default=str)


# Convenience tool wrappers for each provider
@tool(
    name="dalle_generate",
    description="Generate images with OpenAI DALL-E 2/3.",
    tags=["image", "dalle"],
    capabilities=["generate_images"],
)
async def dalle_generate(
    prompt: str,
    model: str = "dall-e-3",
    size: str = "1024x1024",
    count: int = 1,
    quality: str = "standard",
    style: str = "vivid",
) -> str:
    result = await _openai_dalle(
        {
            "prompt": prompt,
            "model": model,
            "size": size,
            "count": count,
            "quality": quality,
            "style": style,
        }
    )
    return json.dumps({"status": "generated", "images": result})


@tool(
    name="imagen_generate",
    description="Generate images with Google Imagen.",
    tags=["image", "imagen"],
    capabilities=["generate_images"],
)
async def imagen_generate(
    prompt: str, model: str = "imagegeneration@005", aspect_ratio: str = "1:1", count: int = 1
) -> str:
    result = await _google_imagen(
        {"prompt": prompt, "model": model, "aspect_ratio": aspect_ratio, "count": count}
    )
    return json.dumps({"status": "generated", "images": result})


@tool(
    name="sdxl_generate",
    description="Generate images with Stability AI SDXL.",
    tags=["image", "sdxl"],
    capabilities=["generate_images"],
)
async def sdxl_generate(prompt: str, aspect_ratio: str = "1:1", seed: int = 0) -> str:
    result = await _stability_sdxl({"prompt": prompt, "aspect_ratio": aspect_ratio, "seed": seed})
    return json.dumps({"status": "generated", "images": result})


@tool(
    name="midjourney_generate",
    description="Generate images with Midjourney.",
    tags=["image", "midjourney"],
    capabilities=["generate_images"],
)
async def midjourney_generate(prompt: str, aspect_ratio: str = "1:1") -> str:
    result = await _midjourney({"prompt": prompt, "aspect_ratio": aspect_ratio})
    return json.dumps({"status": "generated", "images": result})
