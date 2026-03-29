"""文字覆盖服务 - 在图片上渲染本地化文字。

提供功能：
- 在图片上绘制文字（支持中英日文）
- 支持多种位置（top-left, top-right, bottom-left, bottom-right, center）
- 支持自定义字体大小、颜色、背景色、阴影
- 从 LocalizationContent 获取文字配置
- 完整的文字覆盖流程
"""
from __future__ import annotations

import io
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from PIL import Image, ImageDraw, ImageFont

from app.core.enums import ContentUsageScope, LocalizationType, TargetPlatform
from app.core.logging import get_logger
from app.services.storage.minio_client import MinIOClient, get_minio_client

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models import ContentAsset

logger = get_logger(__name__)


class TextOverlayService:
    """文字覆盖服务。"""

    # 位置映射（相对位置，实际坐标在运行时计算）
    POSITION_PRESETS = {
        "top-left",
        "top-right",
        "bottom-left",
        "bottom-right",
        "center",
    }

    def __init__(self, *, minio_client: MinIOClient | None = None):
        self.minio_client = minio_client or get_minio_client()

    async def render_text_on_image(
        self,
        image_bytes: bytes,
        text_config: dict,
    ) -> bytes:
        """在图片上渲染文字。

        Args:
            image_bytes: 源图片字节流
            text_config: 文字配置
                {
                    "text": "Free Shipping",
                    "position": "top-left",  # 或 {"x": 20, "y": 20}
                    "font_size": 24,
                    "font_color": "#FFFFFF",
                    "background_color": "#FF0000",  # 可选
                    "padding": 10,  # 可选
                    "shadow": True,  # 可选
                }

        Returns:
            渲染后的图片字节流
        """
        try:
            # 加载图片
            image = Image.open(io.BytesIO(image_bytes))
            width, height = image.size

            # 确保是 RGB 模式
            if image.mode != "RGB":
                image = image.convert("RGB")

            # 创建绘图对象
            draw = ImageDraw.Draw(image)

            # 解析配置
            text = text_config.get("text", "")
            if not text:
                logger.warning("empty_text_in_config")
                return image_bytes

            font_size = text_config.get("font_size", 24)
            font_color = text_config.get("font_color", "#FFFFFF")
            background_color = text_config.get("background_color")
            padding = text_config.get("padding", 10)
            shadow = text_config.get("shadow", False)

            # 加载字体（使用默认字体）
            try:
                # 尝试使用 TrueType 字体
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
            except Exception:
                # 回退到默认字体
                font = ImageFont.load_default()
                logger.warning("using_default_font")

            # 计算文字尺寸
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            # 计算文字位置
            position = text_config.get("position", "top-left")
            if isinstance(position, dict):
                # 自定义坐标
                x = position.get("x", 20)
                y = position.get("y", 20)
            elif position in self.POSITION_PRESETS:
                # 预设位置
                x, y = self._calculate_position(
                    position, width, height, text_width, text_height, padding
                )
            else:
                # 默认左上角
                x, y = padding, padding

            # 绘制背景（如果指定）
            if background_color:
                bg_bbox = [
                    x - padding,
                    y - padding,
                    x + text_width + padding,
                    y + text_height + padding,
                ]
                draw.rectangle(bg_bbox, fill=background_color)

            # 绘制阴影（如果指定）
            if shadow:
                shadow_offset = 2
                draw.text(
                    (x + shadow_offset, y + shadow_offset),
                    text,
                    font=font,
                    fill="#000000",
                )

            # 绘制文字
            draw.text((x, y), text, font=font, fill=font_color)

            # 转换为字节流
            output = io.BytesIO()
            image.save(output, format=image.format or "PNG")
            rendered_bytes = output.getvalue()

            logger.info(
                "text_rendered_on_image",
                text=text[:20],
                position=position,
                output_size=len(rendered_bytes),
            )

            return rendered_bytes

        except Exception as e:
            logger.error("text_rendering_failed", error=str(e))
            raise

    def _calculate_position(
        self,
        position: str,
        image_width: int,
        image_height: int,
        text_width: int,
        text_height: int,
        padding: int,
    ) -> tuple[int, int]:
        """计算文字位置坐标。"""
        if position == "top-left":
            return padding, padding
        elif position == "top-right":
            return image_width - text_width - padding, padding
        elif position == "bottom-left":
            return padding, image_height - text_height - padding
        elif position == "bottom-right":
            return (
                image_width - text_width - padding,
                image_height - text_height - padding,
            )
        elif position == "center":
            return (
                (image_width - text_width) // 2,
                (image_height - text_height) // 2,
            )
        else:
            return padding, padding

    async def get_localization_text(
        self,
        variant_id: UUID,
        language: str,
        content_type: LocalizationType,
        platform: Optional[TargetPlatform] = None,
        db: AsyncSession = None,
    ) -> dict | None:
        """获取本地化文字配置。

        Args:
            variant_id: 产品变体 ID
            language: 语言代码
            content_type: 内容类型
            platform: 目标平台（可选）
            db: 数据库会话

        Returns:
            文字配置字典，如果未找到返回 None
        """
        from sqlalchemy import select

        from app.db.models import LocalizationContent

        try:
            stmt = select(LocalizationContent).where(
                LocalizationContent.variant_id == variant_id,
                LocalizationContent.language == language,
                LocalizationContent.content_type == content_type,
            )

            if platform:
                stmt = stmt.where(
                    LocalizationContent.platform_tags.contains([platform.value])
                )

            result = await db.execute(stmt)
            localization = result.scalar_one_or_none()

            if localization:
                logger.info(
                    "localization_text_found",
                    variant_id=str(variant_id),
                    language=language,
                    content_type=content_type.value,
                )
                return localization.content
            else:
                logger.warning(
                    "localization_text_not_found",
                    variant_id=str(variant_id),
                    language=language,
                    content_type=content_type.value,
                )
                return None

        except Exception as e:
            logger.error(
                "get_localization_text_failed",
                error=str(e),
                variant_id=str(variant_id),
            )
            return None

    async def overlay_localized_text(
        self,
        *,
        base_asset: ContentAsset,
        platform: TargetPlatform,
        language: str,
        db: AsyncSession,
    ) -> dict:
        """完整的文字覆盖流程。

        Args:
            base_asset: 基础素材
            platform: 目标平台
            language: 语言代码
            db: 数据库会话

        Returns:
            {
                "status": "success"|"error"|"no_text_found",
                "asset": ContentAsset (if success),
                "reason": str (if error),
            }
        """
        try:
            logger.info(
                "text_overlay_started",
                base_asset_id=str(base_asset.id),
                platform=platform.value,
                language=language,
            )

            # 1. 获取本地化文字配置
            text_config = await self.get_localization_text(
                variant_id=base_asset.product_variant_id,
                language=language,
                content_type=LocalizationType.IMAGE_TEXT,
                platform=platform,
                db=db,
            )

            if not text_config:
                return {
                    "status": "no_text_found",
                    "reason": "no_localization_text_configured",
                }

            # 2. 下载基础图片
            image_bytes = await self.minio_client.download_image(base_asset.file_url)

            # 3. 渲染文字到图片
            rendered_bytes = await self.render_text_on_image(image_bytes, text_config)

            # 4. 上传到 MinIO
            file_extension = base_asset.format or "png"
            localized_url = await self.minio_client.upload_image(
                image_data=rendered_bytes,
                product_id=base_asset.candidate_product_id,
                asset_type=f"{base_asset.asset_type.value}_localized",
                style_tags=[platform.value, language],
                filename=f"{platform.value}_{language}_{uuid4().hex[:8]}.{file_extension}",
                content_type=f"image/{file_extension}",
            )

            # 5. 创建 LOCALIZED 素材记录
            localized_asset = await self._create_localized_record(
                base_asset=base_asset,
                platform=platform,
                language=language,
                file_url=localized_url,
                text_config=text_config,
                db=db,
            )

            logger.info(
                "text_overlay_completed",
                base_asset_id=str(base_asset.id),
                localized_asset_id=str(localized_asset.id),
            )

            return {
                "status": "success",
                "asset": localized_asset,
            }

        except Exception as e:
            logger.error(
                "text_overlay_failed",
                base_asset_id=str(base_asset.id),
                error=str(e),
            )
            return {
                "status": "error",
                "reason": str(e),
            }

    async def _create_localized_record(
        self,
        *,
        base_asset: ContentAsset,
        platform: TargetPlatform,
        language: str,
        file_url: str,
        text_config: dict,
        db: AsyncSession,
    ) -> ContentAsset:
        """创建本地化素材记录。"""
        from app.db.models import ContentAsset

        localized_asset = ContentAsset(
            id=uuid4(),
            candidate_product_id=base_asset.candidate_product_id,
            product_variant_id=base_asset.product_variant_id,
            asset_type=base_asset.asset_type,
            usage_scope=ContentUsageScope.LOCALIZED,
            parent_asset_id=base_asset.id,
            file_url=file_url,
            spec=base_asset.spec or {},
            format=base_asset.format,
            dimensions=base_asset.dimensions,
            platform_tags=[platform.value],
            language_tags=[language],
            style_tags=base_asset.style_tags,
            region_tags=base_asset.region_tags,
            generation_params={
                "derived_from": str(base_asset.id),
                "platform": platform.value,
                "language": language,
                "text_overlay": text_config,
            },
            human_approved=False,
            usage_count=0,
            version=1,
        )

        db.add(localized_asset)
        await db.flush()

        return localized_asset
