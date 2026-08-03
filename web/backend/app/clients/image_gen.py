"""Stage: text prompt -> reference image."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod

IMAGE_PROMPT_TEMPLATE = (
    "A single {user_object}, photographed as a real object (not a toy or "
    "building-block model), centered in frame, isolated on a plain flat "
    "light-grey background, straight-on front view, full object visible "
    "with no cropping, evenly lit from all sides like inside a photo light "
    "box, no visible cast shadow or contact shadow beneath or around the "
    "object -- it should appear to float in empty space with no ground or "
    "supporting surface visible, no strong specular highlights or "
    "reflections, no other objects or background elements, no text or "
    "watermarks, clean flat-colored surfaces per part, true-to-life "
    "material colors, simple uncluttered silhouette"
)
# Deliberately does not name any trademarked brand (see CLAUDE.md's
# "Product constraints" section) -- this pipeline's own brickforge stage is
# what turns the reconstructed shape into bricks, so the reference image
# should look like the real object, not a pre-built brick model. Asking
# for stud bumps/brick seams here would only give TRELLIS a noisier
# surface to reconstruct and add fake shading for the color-projection
# stage (reference_color.py) to mis-sample -- see that module's docstring.
#
# "No cast/contact shadow, appears to float" is doing double duty, per a
# real user-traced pair of symptoms in the same session: (1) a cast
# shadow's dark pixels get projected onto bricks directly beneath the
# object by reference_color.py, showing up as wrong, muddy colors there;
# (2) mesh_conditioning.py::strip_base_slab exists because TRELLIS
# reconstructed a literal flat floor slab under a real generated object --
# a contact shadow in the reference photo is a very plausible cause (a
# single-image shape model reading "shadow beneath object" as "there is a
# surface here"). Not fully verified against a live regeneration yet, but
# both symptoms point the same direction, and removing shadow cues can
# only reduce the color/geometry noise, not add any.


def build_image_prompt(user_description: str) -> str:
    return IMAGE_PROMPT_TEMPLATE.format(user_object=user_description.strip())


class ImageGenClient(ABC):
    @abstractmethod
    def generate(self, prompt: str, out_path: str) -> str:
        raise NotImplementedError


class StubImageGenClient(ImageGenClient):
    def generate(self, prompt: str, out_path: str) -> str:
        raise NotImplementedError(
            "No image generation provider configured. Set IMAGE_GEN_PROVIDER "
            "and the matching API key env var."
        )


class OpenAIImageClient(ImageGenClient):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def generate(self, prompt: str, out_path: str) -> str:
        import base64
        import requests

        response = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": "gpt-image-1",
                "prompt": prompt,
                "size": "1024x1024",
                "n": 1,
            },
            timeout=120,
        )
        if not response.ok:
            raise RuntimeError(
                f"OpenAI image generation failed ({response.status_code}): {response.text}"
            )
        data = response.json()
        b64 = data["data"][0]["b64_json"]
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(b64))
        return out_path


def get_image_client() -> ImageGenClient:
    provider = os.environ.get("IMAGE_GEN_PROVIDER", "").strip().lower()

    if not provider:
        return StubImageGenClient()

    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("IMAGE_GEN_API_KEY")
        if not api_key:
            raise RuntimeError(
                "IMAGE_GEN_PROVIDER is set to 'openai', but OPENAI_API_KEY/IMAGE_GEN_API_KEY is missing."
            )
        return OpenAIImageClient(api_key=api_key)

    raise ValueError(f"Unknown IMAGE_GEN_PROVIDER: {provider!r}")
