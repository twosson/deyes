"""图像重生成服务

当源图片尺寸不足时，使用 ComfyUI 重新生成更高分辨率的图片。
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import ContentAsset
from app.services.image_generation.comfyui_client import ComfyUIClient, get_comfyui_client

logger = get_logger(__name__)


class ImageRegenerationService:
    """图像重生成服务"""

    def __init__(self, *, comfyui_client: ComfyUIClient | None = None):
        self.comfyui_client = comfyui_client or get_comfyui_client()

    async def regenerate_with_higher_resolution(
        self,
        *,
        base_asset: ContentAsset,
        target_width: int,
        target_height: int,
        db: AsyncSession,
    ) -> dict:
        """使用 ComfyUI 重新生成更高分辨率的图片。

        Args:
            base_asset: 基础素材
            target_width: 目标宽度
            target_height: 目标高度
            db: 数据库会话

        Returns:
            {
                "status": "success"|"error",
                "image_bytes": bytes (if success),
                "reason": str (if error),
            }
        """
        try:
            # 1. 从 generation_params 获取原始提示词
            generation_params = base_asset.generation_params or {}
            original_prompt = generation_params.get("prompt", "")
            style = generation_params.get("style", "minimalist")

            if not original_prompt:
                # 如果没有原始提示词，使用候选产品标题
                from app.db.models import CandidateProduct

                candidate = await db.get(
                    CandidateProduct, base_asset.candidate_product_id
                )
                if candidate:
                    original_prompt = candidate.title
                else:
                    logger.error(
                        "regeneration_failed",
                        reason="no_prompt_or_candidate",
                        base_asset_id=str(base_asset.id),
                    )
                    return {
                        "status": "error",
                        "reason": "no_prompt_or_candidate",
                    }

            # 2. 调用 ComfyUI 生成更高分辨率图片
            image_bytes = await self.comfyui_client.generate_product_image(
                prompt=original_prompt,
                style=style,
                width=target_width,
                height=target_height,
            )

            logger.info(
                "image_regenerated",
                base_asset_id=str(base_asset.id),
                target_size=f"{target_width}x{target_height}",
                output_size=len(image_bytes),
            )

            return {
                "status": "success",
                "image_bytes": image_bytes,
            }

        except Exception as e:
            logger.error(
                "image_regeneration_failed",
                base_asset_id=str(base_asset.id),
                error=str(e),
            )
            return {
                "status": "error",
                "reason": str(e),
            }
