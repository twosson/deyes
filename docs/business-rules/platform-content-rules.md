# 平台内容规则矩阵

> 定义各平台的图片规格、文字要求、语言支持等内容合规规则
>
> 版本: v1.0
> 创建时间: 2026-03-29
> 数据来源: `backend/app/db/models.py:424-450`, `backend/tests/test_platform_asset_adapter.py`

---

## 📋 核心概念

### 三层素材体系

#### Layer 1: 基础通用素材（BASE）
- **usage_scope**: `BASE`
- **特点**: 无文字、高分辨率母版、跨平台复用
- **生成时机**: SKU 创建后立即生成
- **典型规格**: 1024x1024 或更高

#### Layer 2: 平台派生素材（PLATFORM_DERIVED）
- **usage_scope**: `PLATFORM_DERIVED`
- **特点**: 按平台规格派生（resize/format/crop）
- **生成时机**: Listing 发布前按需派生
- **典型规格**: 平台特定尺寸（800x800, 1000x1000, 1200x1200）

#### Layer 3: 本地化素材（LOCALIZED）
- **usage_scope**: `LOCALIZED`
- **特点**: 叠加本地化文字/标注
- **生成时机**: 多语言发布时按需生成
- **典型规格**: 平台规格 + 语言文字

---

## 📊 平台内容规则矩阵

### 主图规格

| 平台 | 主图尺寸 | 格式 | 允许文字 | 最大数量 | 必需语言 | 备注 |
|------|---------|------|---------|---------|---------|------|
| **Temu** | 800x800 | JPG/PNG | ✅ 是 | 10 | en, zh | 允许卖点角标 |
| **Amazon** | 1000x1000 | JPG | ❌ 否 | 9 | en | 严格无文字要求 |
| **AliExpress** | 800x800 | JPG/PNG | ✅ 是 | 8 | en, zh, es, ru | 多语言支持 |
| **Ozon** | 1200x1200 | JPG | ✅ 是 | 15 | ru | 俄语必须 |
| **Wildberries** | 900x1200 | JPG | ✅ 是 | 30 | ru | 竖版主图 |
| **Shopee** | 1024x1024 | JPG/PNG | ✅ 是 | 9 | en, zh, th, vi | 东南亚多语言 |
| **Mercado Libre** | 1200x1200 | JPG | ✅ 是 | 12 | es, pt | 拉美西葡语 |
| **TikTok Shop** | 800x800 | JPG/PNG | ✅ 是 | 9 | en, zh | 短视频风格 |
| **eBay** | 1600x1600 | JPG | ✅ 是 | 12 | en | 高清优先 |
| **Walmart** | 2000x2000 | JPG | ❌ 否 | 8 | en | 超高清要求 |
| **Rakuten** | 700x700 | JPG | ✅ 是 | 20 | ja | 日语必须 |
| **Allegro** | 1000x1000 | JPG | ✅ 是 | 16 | pl | 波兰语必须 |

### 详情图规格

| 平台 | 详情图尺寸 | 格式 | 允许文字 | 最大数量 | 备注 |
|------|-----------|------|---------|---------|------|
| **Temu** | 800x1200 | JPG/PNG | ✅ 是 | 8 | 竖版详情页 |
| **Amazon** | 1000x1000 | JPG | ✅ 是 | 7 | 详情图可有文字 |
| **AliExpress** | 800x800 | JPG/PNG | ✅ 是 | 6 | 正方形详情 |
| **Ozon** | 1200x1200 | JPG | ✅ 是 | 15 | 与主图同规格 |
| **Wildberries** | 900x1200 | JPG | ✅ 是 | 30 | 竖版详情 |
| **Shopee** | 1024x1024 | JPG/PNG | ✅ 是 | 8 | 正方形详情 |
| **TikTok Shop** | 800x1200 | JPG/PNG | ✅ 是 | 9 | 竖版视频风格 |

---

## 🎨 素材验证规则

### 文字验证

```python
# 代码位置: backend/app/services/platform_asset_adapter.py:72-76

has_text = spec.get("has_text", False)
if has_text and not rule.allow_text_on_image:
    violations.append("text_not_allowed")
    suggestions.append("regenerate_without_text")
```

**规则**:
- Amazon 主图: ❌ 严格禁止文字
- Walmart 主图: ❌ 严格禁止文字
- 其他平台主图: ✅ 允许文字（卖点、促销标签）
- 所有平台详情图: ✅ 允许文字

### 尺寸验证

```python
# 代码位置: backend/app/services/platform_asset_adapter.py:78-90

if asset_width != required_width or asset_height != required_height:
    violations.append("dimension_mismatch")
    if asset_width >= required_width and asset_height >= required_height:
        suggestions.append("resize")  # 源图够大，可 resize
    else:
        suggestions.append("regenerate_higher_resolution")  # 源图太小，需重生成
```

**规则**:
- 源图 ≥ 目标尺寸: 执行 `resize` 动作（裁切/缩放）
- 源图 < 目标尺寸: 执行 `regenerate` 动作（ComfyUI 重生成）

### 格式验证

```python
# 代码位置: backend/app/services/platform_asset_adapter.py:92-97

if asset_format.lower() != required_format.lower():
    violations.append("format_mismatch")
    suggestions.append("convert_format")
```

**规则**:
- PNG → JPG: 执行 `convert_format` 动作（RGBA → RGB + 白底）
- JPG → PNG: 执行 `convert_format` 动作（直接转换）

### 语言验证

```python
# 代码位置: backend/app/services/platform_asset_adapter.py:99-107

if rule.required_languages:
    missing_languages = [
        lang for lang in rule.required_languages if lang not in asset_languages
    ]
    if missing_languages:
        violations.append("missing_required_languages")
        suggestions.append("create_localized_variant")
```

**规则**:
- 检查 `language_tags` 是否包含平台要求的所有语言
- 缺失语言: 执行 `overlay_localized_text` 动作

---

## 🔄 素材派生动作

### 动作优先级

```python
# 代码位置: backend/app/services/platform_asset_adapter.py:149-163

if validation["valid"]:
    actions.append("reuse")  # 优先级 1: 直接复用
else:
    if "resize" in suggestions:
        actions.append("resize")  # 优先级 2: 尺寸调整
    if "convert_format" in suggestions:
        actions.append("convert_format")  # 优先级 3: 格式转换
    if "create_localized_variant" in suggestions and language:
        actions.append("overlay_localized_text")  # 优先级 4: 文字覆盖
    if "regenerate_without_text" in suggestions or "regenerate_higher_resolution" in suggestions:
        actions.append("regenerate")  # 优先级 5: 重新生成
```

### 动作说明

| 动作 | 触发条件 | 执行服务 | 耗时 | 成本 |
|------|---------|---------|------|------|
| **reuse** | 素材完全合规 | - | 0s | 免费 |
| **resize** | 尺寸不匹配，源图够大 | AssetDerivationService | 1-2s | 低 |
| **convert_format** | 格式不匹配 | AssetDerivationService | 1-2s | 低 |
| **overlay_localized_text** | 缺少语言版本 | TextOverlayService | 2-3s | 低 |
| **regenerate** | 源图太小或需去文字 | ImageRegenerationService | 8-12s | 高 |

---

## 🌍 语言支持矩阵

### 平台语言要求

| 平台 | 必需语言 | 可选语言 | 备注 |
|------|---------|---------|------|
| **Temu** | en, zh | es, fr, de, ja | 英中必须，其他可选 |
| **Amazon** | en | - | 单一市场单一语言 |
| **AliExpress** | en, zh | es, ru, fr, pt | 多语言全球化 |
| **Ozon** | ru | en | 俄语必须 |
| **Wildberries** | ru | - | 仅俄语 |
| **Shopee** | en | zh, th, vi, id, ms | 东南亚多语言 |
| **Mercado Libre** | es, pt | - | 西葡语必须 |
| **TikTok Shop** | en, zh | - | 英中双语 |
| **Rakuten** | ja | en | 日语必须 |
| **Allegro** | pl | en | 波兰语必须 |

### 语言代码标准

```python
# 代码位置: backend/app/core/enums.py:193-200

class ContentLanguage(str, Enum):
    EN = "en"  # English
    ZH = "zh"  # Chinese
    JA = "ja"  # Japanese
    ES = "es"  # Spanish
    DE = "de"  # German
    FR = "fr"  # French
    RU = "ru"  # Russian
    PT = "pt"  # Portuguese
    TH = "th"  # Thai
    VI = "vi"  # Vietnamese
    ID = "id"  # Indonesian
    MS = "ms"  # Malay
    PL = "pl"  # Polish
```

---

## 🎯 素材选择优先级

### select_best_asset 逻辑

```python
# 代码位置: backend/app/services/platform_asset_adapter.py:175-260

# 优先级 1: LOCALIZED + 平台 + 语言精确匹配
if usage_scope == LOCALIZED and platform_tags and language_tags:
    return asset

# 优先级 2: PLATFORM_DERIVED + 平台匹配
if usage_scope == PLATFORM_DERIVED and platform_tags:
    return asset

# 优先级 3: LOCALIZED + 语言匹配（无平台匹配）
if usage_scope == LOCALIZED and language_tags:
    return asset

# 优先级 4: BASE 基础素材（兜底）
if usage_scope == BASE:
    return asset
```

### 选择策略

| 场景 | 优先选择 | 备选 | 兜底 |
|------|---------|------|------|
| Temu US 英语 | LOCALIZED (temu+en) | PLATFORM_DERIVED (temu) | BASE |
| Amazon US | PLATFORM_DERIVED (amazon) | BASE | - |
| Temu JP 日语 | LOCALIZED (temu+ja) | LOCALIZED (ja) | BASE |
| 新平台无派生 | BASE | - | - |

---

## 📐 图片规格设计原则

### 为什么不同平台规格不同？

1. **用户设备差异**
   - 移动端主导（Temu, Shopee）: 800x800 节省流量
   - PC 端主导（Amazon, eBay）: 1000x1000+ 高清展示

2. **平台设计风格**
   - 正方形主图（Amazon, Temu）: 1:1 比例
   - 竖版主图（Wildberries）: 3:4 比例
   - 横版主图（部分详情页）: 16:9 比例

3. **合规要求**
   - Amazon: 严格无文字，突出产品本身
   - Temu: 允许文字，强调卖点促销
   - Ozon: 俄语文字必须，本地化要求

4. **技术限制**
   - 文件大小限制（通常 5MB 以内）
   - 加载速度要求（移动端 < 2s）
   - CDN 缓存策略

---

## 🔧 实现细节

### 数据库模型

```python
# 代码位置: backend/app/db/models.py:424-450

class PlatformContentRule(Base):
    platform: TargetPlatform  # 平台
    asset_type: AssetType  # 素材类型
    image_spec: dict  # {"width": 1000, "height": 1000, "format": "jpg"}
    allow_text_on_image: bool  # 是否允许文字
    max_images: int  # 最大图片数量
    required_languages: list[str]  # 必需语言 ["en", "zh"]
    compliance_requirements: dict  # 其他合规要求
```

### ContentAsset 字段

```python
# 代码位置: backend/app/db/models.py:308-371

class ContentAsset(Base):
    asset_type: AssetType  # MAIN_IMAGE, DETAIL_IMAGE, etc.
    usage_scope: ContentUsageScope  # BASE, PLATFORM_DERIVED, LOCALIZED
    spec: dict  # {"width": 1024, "height": 1024, "format": "png", "has_text": false}
    platform_tags: list[str]  # ["temu", "amazon"]
    language_tags: list[str]  # ["en", "zh"]
    compliance_tags: list[str]  # ["amazon_compliant"]
    parent_asset_id: UUID  # 派生自哪个素材
```

---

## 🎯 使用建议

### 基础素材生成策略
- ✅ 生成 1024x1024 或更高分辨率
- ✅ 无文字母版（方便跨平台复用）
- ✅ PNG 格式（保留透明度，后续可转 JPG）
- ✅ 高质量（ComfyUI steps=8, CFG=3.5）

### 平台派生策略
- ✅ 按需派生（不提前生成所有平台版本）
- ✅ 优先 resize（源图够大时）
- ✅ 必要时 regenerate（源图太小时）
- ✅ 缓存派生结果（避免重复派生）

### 本地化策略
- ✅ 文字单独管理（LocalizationContent 表）
- ✅ 运行时叠加（TextOverlayService）
- ✅ 支持多语言切换（不重新生成视觉）
- ✅ 平台特定文案（Temu 促销 vs Amazon 卖点）

---

## 📚 相关文档

- [平台经营模式矩阵](./platform-mode-matrix.md)
- [SKU 激活规则](./sku-activation-rules.md)
- [双模式经营架构实施计划](../roadmap/dual-mode-operations-plan.md)
- [PlatformAssetAdapter 实现](../../backend/app/services/platform_asset_adapter.py)
- [AssetDerivationService 实现](../../backend/app/services/asset_derivation_service.py)
- [TextOverlayService 实现](../../backend/app/services/text_overlay_service.py)

---

**最后更新**: 2026-03-29
**维护者**: Deyes 研发团队
**数据状态**: 生产环境实际配置
