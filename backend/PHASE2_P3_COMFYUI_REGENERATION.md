# Phase2 P3 实施计划：ComfyUI 重生成与 DirectorWorkflow 预计算

## Context

**Phase2 P1 已完成**（2026-03-29）：
- ✅ AssetDerivationService（resize / format conversion）
- ✅ ContentAssetManagerAgent.generate_platform_assets()
- ✅ PlatformPublisherAgent 集成 select_best_asset() 和按需派生

**Phase2 P2 已完成**（2026-03-29）：
- ✅ TextOverlayService（文字覆盖）
- ✅ AssetDerivationService 集成 overlay_localized_text
- ✅ PlatformAssetAdapter 支持 LOCALIZED 素材优先级

**Phase2 P3 目标**：

1. **ComfyUI 重生成集成**：实现 `regenerate` 动作，当源图片尺寸不足或需要重新生成时，调用 ComfyUI 生成新图片
2. **DirectorWorkflow 预计算**：在工作流中预生成基础素材，减少发布时的等待时间

**核心原则**：
- 只在必要时重生成（源图太小、需要不同风格）
- 优先使用派生（resize/format/text overlay）
- 预计算基础素材，按需派生平台素材

---

## Architecture Design

### 1. ComfyUI 重生成服务

```
ImageRegenerationService
├─ regenerate_with_higher_resolution(base_asset, target_width, target_height) → bytes
│  ├─ 使用 ComfyUI 重新生成更高分辨率的图片
│  ├─ 保持原有风格和内容
│  └─ 使用 IPAdapter 参考原图
│
├─ regenerate_with_style(base_asset, new_style) → bytes
│  ├─ 使用 ComfyUI 生成不同风格的图片
│  └─ 使用 ControlNet 保持结构
│
└─ integrate_with_derivation_service()
   └─ 在 AssetDerivationService 中处理 regenerate 动作
```

### 2. DirectorWorkflow 预计算集成

```
DirectorWorkflow
├─ 现有流程：
│  ├─ 需求验证
│  ├─ 供应商匹配
│  ├─ 定价计算
│  ├─ 风险评估
│  ├─ 候选转 SKU
│  └─ 自动上架决策
│
└─ 新增：基础素材生成（在候选转 SKU 后）
   ├─ 调用 ContentAssetManagerAgent.generate_base_assets()
   ├─ 生成 BASE 素材（无文字、高分辨率）
   └─ 不预生成平台素材（按需派生）
```

---

## Implementation Plan

### Task 1: 实现 ImageRegenerationService

**目标**：创建图像重生成服务，使用 ComfyUI 重新生成图片。

**新建文件**：
- `backend/app/services/image_regeneration_service.py` - 图像重生成服务
- `backend/tests/test_image_regeneration_service.py` - 单元测试

**实现范围**：

```python
class ImageRegenerationService:
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
        # 1. 下载原图作为参考
        # 2. 构建 ComfyUI 提示词（从 generation_params 获取）
        # 3. 调用 ComfyUI 生成更高分辨率图片
        # 4. 返回图片字节流

    async def regenerate_with_style(
        self,
        *,
        base_asset: ContentAsset,
        new_style: str,
        db: AsyncSession,
    ) -> dict:
        """使用 ComfyUI 生成不同风格的图片。

        Args:
            base_asset: 基础素材
            new_style: 新风格（minimalist, luxury, cute等）
            db: 数据库会话

        Returns:
            {
                "status": "success"|"error",
                "image_bytes": bytes (if success),
                "reason": str (if error),
            }
        """
        # 1. 下载原图作为参考
        # 2. 构建新风格的提示词
        # 3. 调用 ComfyUI 生成新风格图片
        # 4. 返回图片字节流
```

**技术选型**：
- 使用现有的 ComfyUIClient
- 使用 IPAdapter 参考原图（保持内容一致性）
- 使用 ControlNet 保持结构（可选）

**验收标准**：
- [ ] 可重新生成更高分辨率的图片
- [ ] 可生成不同风格的图片
- [ ] 正确使用 IPAdapter 参考原图
- [ ] 测试覆盖重生成路径

---

### Task 2: 集成到 AssetDerivationService

**目标**：在 AssetDerivationService 中实现 `regenerate` 动作。

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

    # 处理 regenerate 动作
    if "regenerate" in actions:
        from app.services.image_regeneration_service import ImageRegenerationService

        regeneration_service = ImageRegenerationService()

        # 获取目标规格
        target_spec = suggestion.get("target_spec", {})
        target_width = target_spec.get("width")
        target_height = target_spec.get("height")

        if not target_width or not target_height:
            return {
                "status": "error",
                "reason": "target_dimensions_not_specified",
            }

        # 重新生成更高分辨率图片
        result = await regeneration_service.regenerate_with_higher_resolution(
            base_asset=base_asset,
            target_width=target_width,
            target_height=target_height,
            db=db,
        )

        if result["status"] == "success":
            # 上传到 MinIO
            regenerated_url = await self.minio_client.upload_image(
                image_data=result["image_bytes"],
                product_id=base_asset.candidate_product_id,
                asset_type=f"{base_asset.asset_type.value}_regenerated",
                style_tags=[platform.value],
                filename=f"{platform.value}_regenerated_{uuid4().hex[:8]}.png",
                content_type="image/png",
            )

            # 创建派生素材记录
            derived_asset = await self._create_derived_record(
                base_asset=base_asset,
                platform=platform,
                language=language,
                file_url=regenerated_url,
                spec={
                    "width": target_width,
                    "height": target_height,
                    "format": target_spec.get("format", "png"),
                    "has_text": False,
                    "regenerated": True,
                },
                db=db,
            )

            return {
                "status": "success",
                "asset": derived_asset,
                "actions_performed": ["regenerate"],
            }
        else:
            return result
```

**验收标准**：
- [ ] `regenerate` 动作可正常执行
- [ ] 创建的素材标记为 regenerated
- [ ] 正确设置 parent_asset_id, platform_tags, spec
- [ ] 测试覆盖重生成路径

---

### Task 3: DirectorWorkflow 集成基础素材生成

**目标**：在 DirectorWorkflow 中添加基础素材生成步骤。

**修改文件**：
- `backend/app/agents/director_workflow.py`
- `backend/tests/test_director_workflow_content_integration.py`

**实现**：

```python
async def execute(self, context: AgentContext) -> AgentResult:
    # ... 现有流程 ...

    # 步骤 6: 候选转 SKU（已有）
    if conversion_result.success:
        variant_id = conversion_result.output_data.get("product_variant_id")

        # 步骤 7: 生成基础素材（新增）
        if variant_id:
            await self._generate_base_assets(
                variant_id=variant_id,
                candidate=candidate,
                context=context,
            )

    # 步骤 8: 自动上架决策（已有）
    # ...

async def _generate_base_assets(
    self,
    *,
    variant_id: UUID,
    candidate: CandidateProduct,
    context: AgentContext,
) -> None:
    """生成基础素材。

    Args:
        variant_id: 产品变体 ID
        candidate: 候选产品
        context: Agent 上下文
    """
    try:
        from app.agents.content_asset_manager import ContentAssetManagerAgent

        asset_manager = ContentAssetManagerAgent()

        # 创建素材生成上下文
        asset_context = AgentContext(
            strategy_run_id=context.strategy_run_id,
            db=context.db,
            input_data={
                "action": "generate_base_assets",
                "variant_id": str(variant_id),
                "asset_types": ["main_image"],  # 只生成主图
                "styles": ["minimalist"],  # 默认风格
                "generate_count": 1,
            },
        )

        # 执行素材生成
        result = await asset_manager.execute(asset_context)

        if result.success:
            self.logger.info(
                "base_assets_generated",
                variant_id=str(variant_id),
                assets_created=result.output_data.get("assets_created", 0),
            )
        else:
            self.logger.warning(
                "base_assets_generation_failed",
                variant_id=str(variant_id),
                error=result.error_message,
            )

    except Exception as e:
        self.logger.error(
            "base_assets_generation_error",
            variant_id=str(variant_id),
            error=str(e),
        )
        # 不阻塞主流程，继续执行
```

**验收标准**：
- [ ] DirectorWorkflow 在候选转 SKU 后自动生成基础素材
- [ ] 生成失败不阻塞主流程
- [ ] 测试覆盖素材生成集成

---

### Task 4: 优化 ComfyUIClient（可选）

**目标**：扩展 ComfyUIClient 支持 IPAdapter 和 ControlNet。

**修改文件**：
- `backend/app/services/image_generation/comfyui_client.py`

**实现**：

```python
async def generate_with_reference(
    self,
    *,
    prompt: str,
    reference_image_url: str,
    width: int = 1024,
    height: int = 1024,
    ipadapter_weight: float = 0.8,
) -> bytes:
    """使用参考图生成图片（IPAdapter）。

    Args:
        prompt: 文本提示词
        reference_image_url: 参考图 URL
        width: 目标宽度
        height: 目标高度
        ipadapter_weight: IPAdapter 权重

    Returns:
        生成的图片字节流
    """
    # 1. 下载参考图
    # 2. 构建包含 IPAdapter 的工作流
    # 3. 提交并等待完成
    # 4. 返回图片
```

**验收标准**：
- [ ] 支持 IPAdapter 参考图生成
- [ ] 支持 ControlNet 结构控制（可选）
- [ ] 测试覆盖参考图生成

---

## Implementation Order

1. **Task 3: DirectorWorkflow 集成基础素材生成**（优先，独立）
2. **Task 1: 实现 ImageRegenerationService**（依赖 ComfyUIClient）
3. **Task 2: 集成到 AssetDerivationService**（依赖 Task 1）
4. **Task 4: 优化 ComfyUIClient**（可选，增强功能）

建议顺序：Task 3 → Task 1 → Task 2 → Task 4（可选）

---

## Verification Plan

### 单元测试
```bash
cd backend
pytest tests/test_image_regeneration_service.py -v
pytest tests/test_asset_derivation_service.py -v
pytest tests/test_director_workflow_content_integration.py -v
```

### 集成测试

创建端到端测试验证完整流程：

1. **DirectorWorkflow 素材生成测试**：
   - 运行 DirectorWorkflow
   - 验证候选转 SKU 后自动生成基础素材
   - 验证素材 usage_scope 为 BASE

2. **重生成流程测试**：
   - 创建小尺寸 BASE 素材（800x800）
   - 调用 `generate_platform_assets(platform="amazon")`（需要 1000x1000）
   - 验证触发 regenerate 动作
   - 验证生成新的 PLATFORM_DERIVED 素材

3. **完整发布流程测试**：
   - 运行 DirectorWorkflow（生成 BASE 素材）
   - 调用 PlatformPublisherAgent 发布
   - 验证按需派生平台素材
   - 验证 listing 使用正确的素材

---

## Critical Files

**新建文件**：
- `backend/app/services/image_regeneration_service.py` - 图像重生成服务
- `backend/tests/test_image_regeneration_service.py` - 单元测试

**修改文件**：
- `backend/app/services/asset_derivation_service.py` - 集成 regenerate 动作
- `backend/app/agents/director_workflow.py` - 添加基础素材生成步骤
- `backend/app/services/image_generation/comfyui_client.py` - 扩展 IPAdapter 支持（可选）
- `backend/tests/test_asset_derivation_service.py` - 添加 regenerate 测试
- `backend/tests/test_director_workflow_content_integration.py` - 添加素材生成测试

**关键依赖**：
- `backend/app/services/image_generation/comfyui_client.py` - ComfyUI 客户端（已完成）
- `backend/app/agents/content_asset_manager.py` - 素材管理 Agent（已完成）

---

## Estimated Effort

- Task 1: ImageRegenerationService - 6-8h
- Task 2: AssetDerivationService 集成 - 3-4h
- Task 3: DirectorWorkflow 集成 - 4-5h
- Task 4: ComfyUIClient 优化 - 4-5h（可选）
- 集成测试与验证 - 3-4h

**总计**: 16-21h（约 2-3 天，不含可选优化）

---

## Success Criteria

Phase2 P3 成功标准：

1. ✅ DirectorWorkflow 在候选转 SKU 后自动生成基础素材
2. ✅ AssetDerivationService 支持 `regenerate` 动作
3. ✅ 当源图尺寸不足时，自动触发 ComfyUI 重生成
4. ✅ 重生成的素材正确设置 parent_asset_id, platform_tags, spec
5. ✅ 测试覆盖重生成、DirectorWorkflow 集成完整链路

---

## Deferred to Future

以下功能延后到后续阶段：

1. **A/B 测试素材生成**：
   - 为同一产品生成多个风格的素材
   - 自动 A/B 测试选择最佳素材

2. **详情页生成**：
   - 生成 8 张详情页图片
   - 详情页模板系统

3. **视频生成**：
   - 产品视频生成
   - 视频编辑和剪辑

---

**最后更新**: 2026-03-29
**状态**: 待实施
