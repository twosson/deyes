"""MinIO object storage client for content assets.

Provides functionality for:
- Uploading images/videos to MinIO
- Generating presigned URLs for access
- Organizing assets by product/platform
- Content type detection
"""
from __future__ import annotations

import io
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx

try:
    from minio import Minio
    from minio.error import S3Error
except Exception:  # pragma: no cover - optional dependency fallback for test environments
    Minio = None  # type: ignore[assignment]

    class S3Error(Exception):
        """Fallback S3 error when the MinIO dependency is unavailable."""

from app.core.config import get_settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.db.models import ContentAsset

logger = get_logger(__name__)


class MinIOClient:
    """MinIO object storage client."""

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket_name: str | None = None,
        secure: bool | None = None,
    ):
        settings = get_settings()
        self.endpoint = endpoint or settings.minio_endpoint or "localhost:9000"
        self.access_key = access_key or settings.minio_access_key or "minioadmin"
        self.secret_key = secret_key or settings.minio_secret_key or "minioadmin"
        self.bucket_name = bucket_name or settings.minio_bucket_name or "deyes-assets"
        self.secure = secure if secure is not None else settings.minio_secure

        self.logger = get_logger(__name__)
        self._client: Any | None = None

    @property
    def client(self) -> Minio:
        """Get or create MinIO client."""
        if Minio is None:
            raise RuntimeError("minio dependency is not installed")
        if self._client is None:
            self._client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )
        return self._client

    async def ensure_bucket_exists(self) -> None:
        """Ensure the bucket exists, create if not."""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                self.logger.info("bucket_created", bucket=self.bucket_name)
        except S3Error as e:
            self.logger.error("bucket_creation_failed", error=str(e))
            raise

    async def upload_image(
        self,
        *,
        image_data: bytes,
        product_id: UUID,
        asset_type: str,
        style_tags: list[str] | None = None,
        filename: str | None = None,
        content_type: str = "image/png",
    ) -> str:
        """Upload an image to MinIO.

        Args:
            image_data: Raw image bytes
            product_id: Product UUID
            asset_type: Type of asset (main_image, detail_image, etc.)
            style_tags: Style tags for organizing
            filename: Custom filename (optional)
            content_type: MIME type

        Returns:
            MinIO object URL
        """
        await self.ensure_bucket_exists()

        # Generate object path
        # Format: products/{product_id}/{asset_type}/{style}/{filename}
        style_part = "_".join(style_tags[:2]) if style_tags else "default"
        if filename is None:
            import uuid
            filename = f"{uuid.uuid4().hex[:12]}.png"

        object_name = f"products/{product_id}/{asset_type}/{style_part}/{filename}"

        try:
            # Upload to MinIO
            self.client.put_object(
                self.bucket_name,
                object_name,
                io.BytesIO(image_data),
                len(image_data),
                content_type=content_type,
                metadata={
                    "product-id": str(product_id),
                    "asset-type": asset_type,
                    "style-tags": ",".join(style_tags) if style_tags else "",
                },
            )

            url = f"http://{self.endpoint}/{self.bucket_name}/{object_name}"
            self.logger.info(
                "image_uploaded",
                object_name=object_name,
                product_id=str(product_id),
                size=len(image_data),
            )

            return url

        except S3Error as e:
            self.logger.error("upload_failed", error=str(e), object_name=object_name)
            raise

    async def upload_from_url(
        self,
        *,
        url: str,
        product_id: UUID,
        asset_type: str,
        style_tags: list[str] | None = None,
        filename: str | None = None,
    ) -> str:
        """Download from URL and upload to MinIO.

        Args:
            url: Source URL to download from
            product_id: Product UUID
            asset_type: Type of asset
            style_tags: Style tags for organizing
            filename: Custom filename (optional)

        Returns:
            MinIO object URL
        """
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url)
            response.raise_for_status()

            # Detect content type
            content_type = response.headers.get("content-type", "image/png")

            return await self.upload_image(
                image_data=response.content,
                product_id=product_id,
                asset_type=asset_type,
                style_tags=style_tags,
                filename=filename,
                content_type=content_type,
            )

    async def get_presigned_url(
        self,
        object_name: str,
        expires: timedelta = timedelta(hours=24),
    ) -> str:
        """Generate a presigned URL for temporary access.

        Args:
            object_name: MinIO object name
            expires: URL expiration time

        Returns:
            Presigned URL
        """
        try:
            url = self.client.presigned_get_object(
                self.bucket_name,
                object_name,
                expires=expires,
            )
            return url
        except S3Error as e:
            self.logger.error("presigned_url_failed", error=str(e), object_name=object_name)
            raise

    async def delete_object(self, object_name: str) -> bool:
        """Delete an object from MinIO.

        Args:
            object_name: MinIO object name

        Returns:
            True if deleted successfully
        """
        try:
            self.client.remove_object(self.bucket_name, object_name)
            self.logger.info("object_deleted", object_name=object_name)
            return True
        except S3Error as e:
            self.logger.error("delete_failed", error=str(e), object_name=object_name)
            return False

    async def get_object_info(self, object_name: str) -> dict | None:
        """Get object metadata.

        Args:
            object_name: MinIO object name

        Returns:
            Object metadata or None if not found
        """
        try:
            stat = self.client.stat_object(self.bucket_name, object_name)
            return {
                "size": stat.size,
                "content_type": stat.content_type,
                "last_modified": stat.last_modified,
                "metadata": stat.metadata,
            }
        except S3Error as e:
            self.logger.warning("object_not_found", object_name=object_name, error=str(e))
            return None

    async def list_product_assets(
        self,
        product_id: UUID,
        asset_type: str | None = None,
    ) -> list[str]:
        """List all assets for a product.

        Args:
            product_id: Product UUID
            asset_type: Optional filter by asset type

        Returns:
            List of object names
        """
        prefix = f"products/{product_id}/"
        if asset_type:
            prefix += f"{asset_type}/"

        try:
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=prefix,
                recursive=True,
            )
            return [obj.object_name for obj in objects]
        except S3Error as e:
            self.logger.error("list_objects_failed", error=str(e), prefix=prefix)
            return []

    def parse_object_name_from_url(self, url: str) -> str | None:
        """Parse object name from MinIO URL.

        Args:
            url: Full MinIO URL

        Returns:
            Object name or None
        """
        try:
            # Format: http://endpoint/bucket/object_name
            parts = url.split(f"/{self.bucket_name}/")
            if len(parts) == 2:
                return parts[1]
        except Exception:
            pass
        return None

    async def copy_asset(
        self,
        source_object_name: str,
        dest_product_id: UUID,
        dest_asset_type: str,
        dest_style_tags: list[str] | None = None,
    ) -> str:
        """Copy an asset to a new location.

        Args:
            source_object_name: Source object name
            dest_product_id: Destination product ID
            dest_asset_type: Destination asset type
            dest_style_tags: Destination style tags

        Returns:
            New object URL
        """
        # Get source object
        try:
            source_obj = self.client.stat_object(self.bucket_name, source_object_name)
            content_type = source_obj.content_type
        except S3Error as e:
            self.logger.error("source_object_not_found", object_name=source_object_name, error=str(e))
            raise

        # Generate destination path
        style_part = "_".join(dest_style_tags[:2]) if dest_style_tags else "default"
        import uuid
        filename = f"{uuid.uuid4().hex[:12]}_{Path(source_object_name).name}"
        dest_object_name = f"products/{dest_product_id}/{dest_asset_type}/{style_part}/{filename}"

        # Copy object
        from minio.commonconfig import CopySource

        try:
            self.client.copy_object(
                self.bucket_name,
                dest_object_name,
                CopySource(self.bucket_name, source_object_name),
            )

            url = f"http://{self.endpoint}/{self.bucket_name}/{dest_object_name}"
            self.logger.info(
                "asset_copied",
                source=source_object_name,
                dest=dest_object_name,
            )
            return url

        except S3Error as e:
            self.logger.error("copy_failed", error=str(e), source=source_object_name)
            raise


# Singleton instance
_minio_client: MinIOClient | None = None


def get_minio_client() -> MinIOClient:
    """Get or create MinIO client singleton."""
    global _minio_client
    if _minio_client is None:
        _minio_client = MinIOClient()
    return _minio_client
