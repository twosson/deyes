# Phase2 P2 实施计划：本地化文字覆盖

## Context

**Phase2 P1 已完成**（2026-03-29）：
- ✅ AssetDerivationService（resize / format conversion）
- ✅ ContentAssetManagerAgent.generate_platform_assets()
- ✅ PlatformPublisherAgent 集成 select_best_asset() 和按需派生
- ✅ 完整测试套件

**Phase2 P2 目标**：

实现本地化文字覆盖功能，让同一张基础图片可以根据不同语言/平台添加文字标注，避免为每种语言重新生成整个图像。

**核心原则**：
- 基础图片保持无文字（clean base）
- 文字内容存储在 LocalizationContent 表
- 运行时或预生成时叠加文字到图片上
- 支持多语言、多平台规则

---

## Architecture Design

### 1. 数据模型（已完成）

**LocalizationContent** - 本地化内容表（已存在）
```python
# backend/app/db/models.py:390-422
class LocalizationContent:
    variant_id: UUID
    language: str  # "en", "zh", "ja"
    content_type: LocalizationType  # TITLE, DESCRIPTION, IMAGE_TEXT
    content: dict  # {"text": "...", "position": "...", "style": "..."}
    platform_tags: list[str]  # ["temu", "amazon"]
    region_tags: list[str]  # ["us", "jp"]
```

**LocalizationType** - 本地化类型枚举
```python
# backend/app/core/enums.py
class LocalizationType(str, Enum):
    TITLE = "title"
    DESCRIPTION = "description"
    IMAGE_TEXT = "image_text"  # 图片上的文字
    BULLET_POINTS = "bullet_points"
    KEYWORDS = "keywords"
```

### 2. 文字覆盖服务架构

```
TextOverlayService
├─ render_text_on_image(image_bytes, text_config) → bytes
│  ├─ 使用 Pillow 在图片上绘制文字
│  ├─ 支持位置、字体、颜色、大小、阴影
│  └─ 支持多行文字、自动换行
│
├─ get_localization_text(variant_id, language, content_type) → dict
│  ├─ 从 LocalizationContent 表查询
│  └─ 返回文字内容和样式配置
│
└─ overlay_localized_text(base_asset, platform, language) → ContentAsset
   ├─ 下载基础图片
   ├─ 获取本地化文字
   ├─ 渲染文字到图片
   ├─ 上传到 MinIO
   └─ 创建 LOCALIZED 素材记录
```

### 3. 集成点

**AssetDerivationService** - 扩展 derive_asset()
```python
# backend/app/services/asset_derivation_service.py
async def derive_asset(...):
    # 现有逻辑...

    # 新增：处理 overlay_localized_text 动作
    if "overlay_localized_text" in actions:
        text_overlay_service = TextOverlayService()
        result = await text_overlay_service.overlay_localized_text(
            base_asset=base_asset,
            platform=platform,
            language=language,
            db=db,
        )
        return result
```

**LocalizationService** - 扩展 CRUD
```python
# backend/app/services/localization_service.py
# 已有基础 CRUD，需要添加：
async def create_image_text_localization(
    variant_id: UUID,
    language: str,
    text_config: dict,  # {"text": "...", "position": "top-left", "font_size": 24}
    platform_tags: list[str],
    db: AsyncSession,
) -> LocalizationContent
```

---

## Implementation Plan

### Task 1: 实现 TextOverlayService

**目标**：创建文字覆盖服务，使用 Pillow 在图片上绘制文字。

**新建文件**：
- `backend/app/services/text_overlay_service.py` - 文字覆盖服务
- `backend/tests/test_text_overlay_service.py` - 单元测试

**实现范围**：

```python
class TextOverlayService:
    async def render_text_on_image(
        self,
        image_bytes: bytes,
        text_config: dict,
    ) -> bytes:
        """在图片上渲染文字。

        text_config 格式：
        {
            "text": "Free Shipping",
            "position": "top-left",  # top-left, top-right, bottom-left, bottom-right, center
            "font_size": 24,
            "font_color": "#FFFFFF",
            "background_color": "#FF0000",  # 可选背景色
            "padding": 10,
            "shadow": True,  # 可选阴影
        }
        """

    async def get_localization_text(
        self,
        variant_id: UUID,
        language: str,
        content_type: LocalizationType,
        db: AsyncSession,
    ) -> dict | None:
        """获取本地化文字配置。"""

    async def overlay_localized_text(
        self,
        base_asset: ContentAsset,
        platform: TargetPlatform,
        language: str,
        db: AsyncSession,
    ) -> dict:
        """完整的文字覆盖流程。

        Returns:
            {
                "status": "success"|"error"|"no_text_found",
                "asset": ContentAsset (if success),
                "reason": str (if error),
            }
        """
```

**技术选型**：
- 使用 **Pillow** 的 `ImageDraw` 和 `ImageFont`
- 字体文件：使用系统字体或内置字体
- 支持中文、日文等多语言字体

**文字位置映射**：
```python
POSITION_MAP = {
    "top-left": (20, 20),
    "top-right": (width - text_width - 20, 20),
    "bottom-left": (20, height - text_height - 20),
    "bottom-right": (width - text_width - 20, height - text_height - 20),
    "center": ((width - text_width) // 2, (height - text_height) // 2),
}
```

**验收标准**：
- [ ] 可在图片上绘制文字（支持中英日文）
- [ ] 支持 5 种位置（top-left, top-right, bottom-left, bottom-right, center）
- [ ] 支持自定义字体大小、颜色
- [ ] 支持可选背景色和阴影
- [ ] 测试覆盖所有文字渲染路径

---

### Task 2: 扩展 LocalizationService

**目标**：添加 IMAGE_TEXT 类型的本地化内容管理。

**修改文件**：
- `backend/app/services/localization_service.py`
- `backend/tests/test_localization_service.py`

**实现**：

```python
async def create_image_text_localization(
    self,
    *,
    variant_id: UUID,
    language: str,
    text_config: dict,
    platform_tags: list[str] | None = None,
    region_tags: list[str] | None = None,
    db: AsyncSession,
) -> LocalizationContent:
    """创建图片文字本地化内容。

    text_config 示例：
    {
        "text": "Free Shipping",
        "position": "top-left",
        "font_size": 24,
        "font_color": "#FFFFFF",
        "background_color": "#FF0000",
    }
    """
    localization = LocalizationContent(
        id=uuid4(),
        variant_id=variant_id,
        language=language,
        content_type=LocalizationType.IMAGE_TEXT,
        content=text_config,
        platform_tags=platform_tags,
        region_tags=region_tags,
    )
    db.add(localization)
    await db.flush()
    return localization

async def get_image_text_localization(
    self,
    *,
    variant_id: UUID,
    language: str,
    platform: TargetPlatform | None = None,
    db: AsyncSession,
) -> LocalizationContent | None:
    """获取图片文字本地化内容。"""
    stmt = select(LocalizationContent).where(
        LocalizationContent.variant_id == variant_id,
        LocalizationContent.language == language,
        LocalizationContent.content_type == LocalizationType.IMAGE_TEXT,
    )

    if platform:
        stmt = stmt.where(
            LocalizationContent.platform_tags.contains([platform.value])
        )

    result = await db.execute(stmt)
    return result.scalar_one_or_none()
```

**验收标准**：
- [ ] 可创建 IMAGE_TEXT 类型的本地化内容
- [ ] 可按 variant_id + language + platform 查询
- [ ] 可更新和删除本地化内容
- [ ] 测试覆盖 CRUD 操作

---

### Task 3: 集成到 AssetDerivationService

**目标**：在 AssetDerivationService 中实现 `overlay_localized_text` 动作。

**修改文件**：
- `backend/app/services/asset_derivation_service.py`
- `backend/tests/test_asset_derivation_service.py`

**实现**：

```python
async def derive_asset(
    self,
    *,
    base_asset: ContentAsset,
    platform: TargetPlatform,
    db: AsyncSession,
    language: Optional[str] = None,
) -> dict:
    # ... 现有逻辑 ...

    # 处理 overlay_localized_text 动作
    if "overlay_localized_text" in actions:
        if not language:
            return {
                "status": "deferred",
                "reason": "language_required_for_text_overlay",
            }

        text_overlay_service = TextOverlayService()
        result = await text_overlay_service.overlay_localized_text(
            base_asset=base_asset,
            platform=platform,
            language=language,
            db=db,
        )

        if result["status"] == "success":
            return {
                "status": "success",
                "asset": result["asset"],
                "actions_performed": ["overlay_localized_text"],
            }
        elif result["status"] == "no_text_found":
            # 没有找到本地化文字，回退到 reuse 或其他动作
            logger.warning("no_localization_text_found", variant_id=base_asset.product_variant_id)
            # 继续处理其他动作...
        else:
            return result
```

**验收标准**：
- [ ] `overlay_localized_text` 动作可正常执行
- [ ] 创建的素材 usage_scope 为 LOCALIZED
- [ ] 正确设置 parent_asset_id, language_tags, platform_tags
- [ ] 没有本地化文字时优雅降级
- [ ] 测试覆盖文字覆盖路径

---

### Task 4: 更新 PlatformAssetAdapter

**目标**：更新资产选择优先级，支持 LOCALIZED 素材。

**修改文件**：
- `backend/app/services/platform_asset_adapter.py`
- `backend/tests/test_platform_asset_adapter.py`

**实现**：

```python
async def select_best_asset(
    self,
    *,
    variant_id: UUID,
    platform: TargetPlatform,
    asset_type: AssetType,
    db: AsyncSession,
    language: Optional[str] = None,
) -> Optional[ContentAsset]:
    """选择最佳素材。

    优先级（更新）：
    1. LOCALIZED 素材（匹配 platform + language）
    2. PLATFORM_DERIVED 素材（匹配 platform）
    3. BASE 素材
    """
    stmt = select(ContentAsset).where(
        ContentAsset.product_variant_id == variant_id,
        ContentAsset.asset_type == asset_type,
        ContentAsset.archived == False,
    )
    result = await db.execute(stmt)
    assets = list(result.scalars().all())

    if not assets:
        return None

    # Priority 1: LOCALIZED 素材（精确匹配 platform + language）
    if language:
        for asset in assets:
            if (
                asset.usage_scope == ContentUsageScope.LOCALIZED
                and asset.platform_tags
                and platform.value in asset.platform_tags
                and asset.language_tags
                and language in asset.language_tags
            ):
                return asset

    # Priority 2: PLATFORM_DERIVED 素材
    for asset in assets:
        if (
            asset.usage_scope == ContentUsageScope.PLATFORM_DERIVED
            and asset.platform_tags
            and platform.value in asset.platform_tags
        ):
            if language:
                if asset.language_tags and language in asset.language_tags:
                    return asset
            else:
                return asset

    # Priority 3: BASE 素材
    for asset in assets:
        if asset.usage_scope == ContentUsageScope.BASE:
            return asset

    # Fallback
    return assets[0]
```

**验收标准**：
- [ ] LOCALIZED 素材优先级最高
- [ ] 正确匹配 platform + language
- [ ] 测试覆盖新的优先级逻辑

---

### Task 5: 创建本地化内容管理 API（可选）

**目标**：提供 API 让用户管理本地化文字内容。

**新建文件**：
- `backend/app/api/routes_localization.py` - 本地化内容 API
- `backend/tests/test_localization_api.py` - API 测试

**实现范围**：

```python
# POST /variants/{variant_id}/localizations
async def create_localization(
    variant_id: UUID,
    localization: LocalizationCreate,
    db: AsyncSession,
):
    """创建本地化内容。"""

# GET /variants/{variant_id}/localizations
async def list_localizations(
    variant_id: UUID,
    language: str | None = None,
    content_type: LocalizationType | None = None,
    db: AsyncSession,
):
    """列出本地化内容。"""

# PUT /localizations/{localization_id}
async def update_localization(
    localization_id: UUID,
    localization: LocalizationUpdate,
    db: AsyncSession,
):
    """更新本地化内容。"""

# DELETE /localizations/{localization_id}
async def delete_localization(
    localization_id: UUID,
    db: AsyncSession,
):
    """删除本地化内容。"""
```

**验收标准**：
- [ ] 可通过 API 创建/查询/更新/删除本地化内容
- [ ] 支持 IMAGE_TEXT 类型
- [ ] 测试覆盖所有 API 端点

---

## Implementation Order

1. **Task 1: 实现 TextOverlayService**（独立，无依赖）
2. **Task 2: 扩展 LocalizationService**（独立，无依赖）
3. **Task 3: 集成到 AssetDerivationService**（依赖 Task 1, 2）
4. **Task 4: 更新 PlatformAssetAdapter**（依赖 Task 3）
5. **Task 5: 创建本地化内容管理 API**（可选，依赖 Task 2）

建议顺序：Task 1 → Task 2 → Task 3 → Task 4 → Task 5

---

## Verification Plan

### 单元测试
```bash
cd backend
pytest tests/test_text_overlay_service.py -v
pytest tests/test_localization_service.py -v
pytest tests/test_asset_derivation_service.py -v
pytest tests/test_platform_asset_adapter.py -v
```

### 集成测试

创建端到端测试验证完整流程：

1. **文字覆盖流程测试**：
   - 创建 BASE 素材（1024x1024 PNG）
   - 创建 IMAGE_TEXT 本地化内容（"Free Shipping"）
   - 调用 `generate_platform_assets(platform="temu", language="en")`
   - 验证生成 LOCALIZED 素材
   - 验证图片上有文字

2. **发布流程测试**：
   - 创建 BASE 素材 + IMAGE_TEXT 本地化内容
   - 调用 PlatformPublisherAgent 发布到 Temu US
   - 验证自动触发文字覆盖
   - 验证 listing 使用 LOCALIZED 素材

3. **选择优先级测试**：
   - 创建 BASE + PLATFORM_DERIVED + LOCALIZED 素材
   - 调用 `select_best_asset(platform="temu", language="en")`
   - 验证优先返回 LOCALIZED

---

## Critical Files

**新建文件**：
- `backend/app/services/text_overlay_service.py` - 文字覆盖服务
- `backend/tests/test_text_overlay_service.py` - 单元测试
- `backend/app/api/routes_localization.py` - 本地化内容 API（可选）
- `backend/tests/test_localization_api.py` - API 测试（可选）

**修改文件**：
- `backend/app/services/asset_derivation_service.py` - 集成文字覆盖
- `backend/app/services/localization_service.py` - 扩展 IMAGE_TEXT CRUD
- `backend/app/services/platform_asset_adapter.py` - 更新选择优先级
- `backend/tests/test_asset_derivation_service.py` - 添加文字覆盖测试
- `backend/tests/test_localization_service.py` - 添加 IMAGE_TEXT 测试
- `backend/tests/test_platform_asset_adapter.py` - 添加 LOCALIZED 优先级测试

**关键依赖**：
- `backend/app/db/models.py` - LocalizationContent 模型（已完成）
- `backend/app/core/enums.py` - LocalizationType 枚举（已完成）
- Pillow 库（已添加到 pyproject.toml）

---

## Estimated Effort

- Task 1: TextOverlayService - 8-10h
- Task 2: LocalizationService 扩展 - 3-4h
- Task 3: AssetDerivationService 集成 - 4-5h
- Task 4: PlatformAssetAdapter 更新 - 2-3h
- Task 5: 本地化内容管理 API - 4-5h（可选）
- 集成测试与验证 - 3-4h

**总计**: 24-31h（约 3-4 天，不含可选 API）

---

## Success Criteria

Phase2 P2 成功标准：

1. ✅ 可在图片上渲染本地化文字（支持中英日文）
2. ✅ 可创建和管理 IMAGE_TEXT 类型的本地化内容
3. ✅ AssetDerivationService 支持 `overlay_localized_text` 动作
4. ✅ PlatformAssetAdapter 优先选择 LOCALIZED 素材
5. ✅ 发布时若有本地化文字，自动触发文字覆盖
6. ✅ 测试覆盖文字覆盖、选择、发布完整链路

---

## Next Steps (Phase2 P3)

Phase2 P2 完成后，下一步是 **Phase2 P3: ComfyUI 重生成**：

1. **ComfyUI 集成**：
   - 实现 `regenerate` 动作
   - IPAdapter / ControlNet 集成
   - FLUX Fill 局部编辑

2. **DirectorWorkflow 预计算**：
   - 在工作流中预生成平台素材
   - 减少发布时的等待时间

---

**最后更新**: 2026-03-29
**状态**: 待实施
