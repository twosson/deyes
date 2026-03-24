"""ComfyUI API client for image generation.

Provides functionality for:
- Generating product images using FLUX.1-dev
- Style transfer with IPAdapter
- Structure control with ControlNet
- Batch generation
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ComfyUIClient:
    """ComfyUI API client for image generation."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: int | None = None,
    ):
        settings = get_settings()
        self.base_url = base_url or settings.comfyui_base_url
        self.timeout = timeout or settings.comfyui_timeout
        self.logger = get_logger(__name__)

    async def generate_product_image(
        self,
        *,
        prompt: str,
        reference_images: list[str] | None = None,
        style: str = "minimalist",
        width: int = 1024,
        height: int = 1024,
        steps: int = 8,
        cfg_scale: float = 3.5,
        seed: int | None = None,
    ) -> bytes:
        """Generate a product image using FLUX.1-dev.

        Args:
            prompt: Text prompt for generation
            reference_images: URLs of reference images for IPAdapter
            style: Style preset (minimalist, luxury, cute, etc.)
            width: Image width
            height: Image height
            steps: Sampling steps (8 for Turbo LoRA)
            cfg_scale: CFG scale
            seed: Random seed (optional)

        Returns:
            Generated image as bytes
        """
        if seed is None:
            import random
            seed = random.randint(0, 2**32 - 1)

        # Build ComfyUI workflow
        workflow = self._build_workflow(
            prompt=prompt,
            reference_images=reference_images,
            style=style,
            width=width,
            height=height,
            steps=steps,
            cfg_scale=cfg_scale,
            seed=seed,
        )

        # Submit workflow
        prompt_id = await self._queue_prompt(workflow)

        # Wait for completion
        image_data = await self._wait_for_completion(prompt_id)

        return image_data

    async def generate_batch(
        self,
        *,
        prompts: list[str],
        reference_images: list[str] | None = None,
        style: str = "minimalist",
        width: int = 1024,
        height: int = 1024,
    ) -> list[bytes]:
        """Generate multiple images in batch.

        Args:
            prompts: List of text prompts
            reference_images: Shared reference images
            style: Style preset
            width: Image width
            height: Image height

        Returns:
            List of generated images as bytes
        """
        tasks = [
            self.generate_product_image(
                prompt=prompt,
                reference_images=reference_images,
                style=style,
                width=width,
                height=height,
            )
            for prompt in prompts
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        images = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error("batch_generation_failed", index=i, error=str(result))
            else:
                images.append(result)

        return images

    def _build_workflow(
        self,
        *,
        prompt: str,
        reference_images: list[str] | None,
        style: str,
        width: int,
        height: int,
        steps: int,
        cfg_scale: float,
        seed: int,
    ) -> dict[str, Any]:
        """Build ComfyUI workflow JSON.

        This is a simplified workflow. In production, you should load
        the actual workflow from docs/deployment/comfyui-deployment-guide.md
        """
        workflow = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "flux1-dev-fp8.safetensors",
                },
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["1", 1],
                },
            },
            "3": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1,
                },
            },
            "4": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg_scale,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["2", 0],  # Simplified
                    "latent_image": ["3", 0],
                },
            },
            "5": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["4", 0],
                    "vae": ["1", 2],
                },
            },
            "6": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": f"deyes_{style}",
                    "images": ["5", 0],
                },
            },
        }

        # TODO: Add IPAdapter and ControlNet nodes if reference_images provided
        # See docs/deployment/comfyui-deployment-guide.md for full workflow

        return workflow

    async def _queue_prompt(self, workflow: dict[str, Any]) -> str:
        """Queue a prompt to ComfyUI.

        Args:
            workflow: ComfyUI workflow JSON

        Returns:
            Prompt ID
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow},
            )
            response.raise_for_status()
            data = response.json()
            prompt_id = data["prompt_id"]

            self.logger.info("prompt_queued", prompt_id=prompt_id)
            return prompt_id

    async def _wait_for_completion(
        self,
        prompt_id: str,
        poll_interval: float = 1.0,
        max_wait: int = 300,
    ) -> bytes:
        """Wait for prompt completion and retrieve image.

        Args:
            prompt_id: Prompt ID from queue_prompt
            poll_interval: Polling interval in seconds
            max_wait: Maximum wait time in seconds

        Returns:
            Generated image as bytes
        """
        elapsed = 0.0

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            while elapsed < max_wait:
                # Check history
                response = await client.get(f"{self.base_url}/history/{prompt_id}")
                response.raise_for_status()
                history = response.json()

                if prompt_id in history:
                    # Prompt completed
                    outputs = history[prompt_id].get("outputs", {})

                    # Find SaveImage node output
                    for node_id, node_output in outputs.items():
                        if "images" in node_output:
                            images = node_output["images"]
                            if images:
                                # Get first image
                                image_info = images[0]
                                filename = image_info["filename"]
                                subfolder = image_info.get("subfolder", "")
                                image_type = image_info.get("type", "output")

                                # Download image
                                params = {
                                    "filename": filename,
                                    "subfolder": subfolder,
                                    "type": image_type,
                                }
                                img_response = await client.get(
                                    f"{self.base_url}/view",
                                    params=params,
                                )
                                img_response.raise_for_status()

                                self.logger.info(
                                    "image_generated",
                                    prompt_id=prompt_id,
                                    filename=filename,
                                    size=len(img_response.content),
                                )

                                return img_response.content

                # Wait and retry
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

        raise TimeoutError(f"Image generation timed out after {max_wait}s")

    async def health_check(self) -> bool:
        """Check if ComfyUI is healthy.

        Returns:
            True if healthy
        """
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/system_stats")
                return response.status_code == 200
        except Exception as e:
            self.logger.error("health_check_failed", error=str(e))
            return False

    async def get_models(self) -> dict[str, list[str]]:
        """Get available models.

        Returns:
            Dict of model types and their available models
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/object_info")
                response.raise_for_status()
                data = response.json()

                # Extract checkpoint names
                checkpoints = []
                if "CheckpointLoaderSimple" in data:
                    inputs = data["CheckpointLoaderSimple"]["input"]
                    if "required" in inputs and "ckpt_name" in inputs["required"]:
                        checkpoints = inputs["required"]["ckpt_name"][0]

                return {
                    "checkpoints": checkpoints,
                }
        except Exception as e:
            self.logger.error("get_models_failed", error=str(e))
            return {}


# Singleton instance
_comfyui_client: ComfyUIClient | None = None


def get_comfyui_client() -> ComfyUIClient:
    """Get or create ComfyUI client singleton."""
    global _comfyui_client
    if _comfyui_client is None:
        _comfyui_client = ComfyUIClient()
    return _comfyui_client
