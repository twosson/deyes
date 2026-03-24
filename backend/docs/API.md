# Phase 1 最小中台 API 文档

## 概述

Phase 1 提供了完整的 RESTful API，用于管理商品、内容资产和平台发布。

**Base URL**: `http://localhost:8000/api/v1`

---

## 1. 商品管理 API (`/products`)

### 1.1 列出所有商品

```http
GET /api/v1/products
```

**查询参数**:
- `lifecycle_status` (可选): 生命周期状态过滤 (draft, ready_to_publish, published)
- `status` (可选): 候选状态过滤 (discovered, priced, etc.)
- `category` (可选): 类目过滤
- `search` (可选): 标题搜索
- `limit` (可选): 每页结果数 (默认: 50, 最大: 500)
- `offset` (可选): 分页偏移量 (默认: 0)

**响应示例**:
```json
{
  "total": 150,
  "products": [
    {
      "id": "uuid",
      "internal_sku": "DEY-PH-001",
      "title": "iPhone 15 Pro Phone Case",
      "category": "phone accessories",
      "source_platform": "alibaba_1688",
      "source_product_id": "123456",
      "platform_price": 5.50,
      "lifecycle_status": "ready_to_publish",
      "status": "discovered",
      "created_at": "2026-03-22T10:00:00Z",
      "updated_at": "2026-03-22T11:00:00Z",
      "assets_count": 3,
      "listings_count": 2
    }
  ]
}
```

### 1.2 获取商品详情

```http
GET /api/v1/products/{product_id}
```

**响应示例**:
```json
{
  "id": "uuid",
  "internal_sku": "DEY-PH-001",
  "title": "iPhone 15 Pro Phone Case",
  "category": "phone accessories",
  "source_platform": "alibaba_1688",
  "source_product_id": "123456",
  "source_url": "https://detail.1688.com/offer/123456.html",
  "platform_price": 5.50,
  "sales_count": 1200,
  "rating": 4.8,
  "main_image_url": "https://example.com/image.jpg",
  "lifecycle_status": "ready_to_publish",
  "status": "discovered",
  "created_at": "2026-03-22T10:00:00Z",
  "updated_at": "2026-03-22T11:00:00Z",
  "assets": [
    {
      "id": "uuid",
      "asset_type": "main_image",
      "file_url": "https://minio.example.com/...",
      "style_tags": ["minimalist"],
      "human_approved": true
    }
  ],
  "listings": [
    {
      "id": "uuid",
      "platform": "temu",
      "region": "us",
      "platform_listing_id": "TEMU-ABC123",
      "price": 12.99,
      "currency": "USD",
      "inventory": 50,
      "status": "active"
    }
  ],
  "supplier_matches": [
    {
      "id": "uuid",
      "supplier_name": "深圳某某电子",
      "supplier_price": 5.50,
      "moq": 10,
      "selected": true
    }
  ]
}
```

### 1.3 更新商品生命周期

```http
PATCH /api/v1/products/{product_id}/lifecycle
```

**请求体**:
```json
{
  "lifecycle_status": "ready_to_publish"
}
```

### 1.4 获取商品统计

```http
GET /api/v1/products/stats/overview
```

**响应示例**:
```json
{
  "total_products": 150,
  "by_lifecycle": {
    "draft": 50,
    "content_generating": 20,
    "ready_to_publish": 30,
    "published": 50
  },
  "by_status": {
    "discovered": 100,
    "priced": 50
  },
  "total_assets": 450,
  "total_listings": 100,
  "total_published": 50
}
```

### 1.5 删除商品

```http
DELETE /api/v1/products/{product_id}
```

---

## 2. 内容资产 API (`/content-assets`)

### 2.1 生成内容资产

```http
POST /api/v1/content-assets/generate
```

**请求体**:
```json
{
  "candidate_product_id": "uuid",
  "asset_types": ["main_image", "detail_image"],
  "styles": ["minimalist", "luxury"],
  "reference_images": ["https://example.com/ref1.jpg"],
  "generate_count": 2,
  "platforms": ["temu", "amazon"],
  "regions": ["us", "uk"]
}
```

**响应示例**:
```json
{
  "success": true,
  "candidate_product_id": "uuid",
  "assets_created": 4,
  "asset_ids": ["uuid1", "uuid2", "uuid3", "uuid4"],
  "lifecycle_status": "ready_to_publish"
}
```

### 2.2 列出商品的资产

```http
GET /api/v1/content-assets/products/{product_id}
```

**查询参数**:
- `asset_type` (可选): 资产类型过滤 (main_image, detail_image)
- `style` (可选): 风格标签过滤
- `platform` (可选): 平台标签过滤
- `approved_only` (可选): 只显示已审核的 (默认: false)

**响应示例**:
```json
{
  "total": 4,
  "assets": [
    {
      "id": "uuid",
      "candidate_product_id": "uuid",
      "asset_type": "main_image",
      "style_tags": ["minimalist"],
      "platform_tags": ["temu", "amazon"],
      "region_tags": ["us", "uk"],
      "file_url": "https://minio.example.com/...",
      "file_size": 512000,
      "dimensions": "1024x1024",
      "format": "png",
      "ai_quality_score": 9.2,
      "human_approved": true,
      "usage_count": 2,
      "version": 1,
      "created_at": "2026-03-22T10:00:00Z"
    }
  ]
}
```

### 2.3 获取单个资产

```http
GET /api/v1/content-assets/{asset_id}
```

### 2.4 审核资产

```http
POST /api/v1/content-assets/{asset_id}/approve
```

**请求体**:
```json
{
  "notes": "Quality looks good"
}
```

### 2.5 拒绝资产

```http
POST /api/v1/content-assets/{asset_id}/reject
```

### 2.6 删除资产

```http
DELETE /api/v1/content-assets/{asset_id}
```

### 2.7 获取最佳资产

```http
GET /api/v1/content-assets/products/{product_id}/best
```

**查询参数**:
- `asset_type` (默认: main_image)
- `platform` (可选)

---

## 3. 平台发布 API (`/platform-listings`)

### 3.1 发布到平台

```http
POST /api/v1/platform-listings/publish
```

**请求体**:
```json
{
  "candidate_product_id": "uuid",
  "target_platforms": [
    {"platform": "temu", "region": "us"},
    {"platform": "temu", "region": "uk"},
    {"platform": "amazon", "region": "us"}
  ],
  "pricing_strategy": "standard",
  "auto_approve": false
}
```

**定价策略**:
- `standard`: 2.5x markup, 25% margin
- `aggressive`: 2.0x markup, 20% margin
- `premium`: 3.0x markup, 30% margin

**响应示例**:
```json
{
  "success": true,
  "candidate_product_id": "uuid",
  "published_count": 3,
  "failed_count": 0,
  "listing_ids": ["uuid1", "uuid2", "uuid3"],
  "failed_platforms": []
}
```

### 3.2 列出商品的平台发布

```http
GET /api/v1/platform-listings/products/{product_id}
```

**查询参数**:
- `platform` (可选): 平台过滤
- `region` (可选): 地区过滤
- `status` (可选): 状态过滤

**响应示例**:
```json
{
  "total": 3,
  "listings": [
    {
      "id": "uuid",
      "candidate_product_id": "uuid",
      "platform": "temu",
      "region": "us",
      "platform_listing_id": "TEMU-ABC123",
      "platform_url": "https://www.temu.com/product-123.html",
      "price": 12.99,
      "currency": "USD",
      "inventory": 50,
      "status": "active",
      "total_sales": 25,
      "total_revenue": 324.75,
      "created_at": "2026-03-22T10:00:00Z",
      "last_synced_at": "2026-03-22T12:00:00Z"
    }
  ]
}
```

### 3.3 获取单个发布

```http
GET /api/v1/platform-listings/{listing_id}
```

### 3.4 更新发布

```http
PATCH /api/v1/platform-listings/{listing_id}
```

**请求体**:
```json
{
  "price": 14.99,
  "inventory": 100,
  "status": "active"
}
```

### 3.5 同步库存

```http
POST /api/v1/platform-listings/sync-inventory
```

**请求体**:
```json
{
  "platform_listing_ids": ["uuid1", "uuid2"]
}
```

如果不提供 `platform_listing_ids`，将同步所有活跃的发布。

**响应示例**:
```json
{
  "success": true,
  "synced_count": 2,
  "failed_count": 0
}
```

### 3.6 暂停发布

```http
POST /api/v1/platform-listings/{listing_id}/pause
```

### 3.7 恢复发布

```http
POST /api/v1/platform-listings/{listing_id}/resume
```

### 3.8 下架商品

```http
DELETE /api/v1/platform-listings/{listing_id}
```

### 3.9 列出所有发布

```http
GET /api/v1/platform-listings/
```

**查询参数**:
- `platform` (可选)
- `region` (可选)
- `status` (可选)
- `limit` (默认: 50)
- `offset` (默认: 0)

---

## 完整工作流示例

### 场景: 从选品到发布的完整流程

#### 1. 选品（已有商品）
假设 `IntelligentProductSelector` 已经创建了商品，ID 为 `product-uuid-123`

#### 2. 生成内容资产

```bash
curl -X POST http://localhost:8000/api/v1/content-assets/generate \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_product_id": "product-uuid-123",
    "asset_types": ["main_image", "detail_image"],
    "styles": ["minimalist"],
    "generate_count": 1,
    "platforms": ["temu"],
    "regions": ["us"]
  }'
```

#### 3. 查看生成的资产

```bash
curl http://localhost:8000/api/v1/content-assets/products/product-uuid-123
```

#### 4. 审核资产

```bash
curl -X POST http://localhost:8000/api/v1/content-assets/{asset-id}/approve \
  -H "Content-Type: application/json" \
  -d '{"notes": "Looks good"}'
```

#### 5. 发布到 Temu

```bash
curl -X POST http://localhost:8000/api/v1/platform-listings/publish \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_product_id": "product-uuid-123",
    "target_platforms": [
      {"platform": "temu", "region": "us"}
    ],
    "pricing_strategy": "standard",
    "auto_approve": true
  }'
```

#### 6. 查看发布状态

```bash
curl http://localhost:8000/api/v1/platform-listings/products/product-uuid-123
```

#### 7. 更新库存

```bash
curl -X PATCH http://localhost:8000/api/v1/platform-listings/{listing-id} \
  -H "Content-Type: application/json" \
  -d '{"inventory": 100}'
```

#### 8. 查看商品完整信息

```bash
curl http://localhost:8000/api/v1/products/product-uuid-123
```

---

## 错误响应

所有 API 在出错时返回标准错误格式:

```json
{
  "detail": "Error message here"
}
```

**常见 HTTP 状态码**:
- `200 OK`: 成功
- `404 Not Found`: 资源不存在
- `422 Unprocessable Entity`: 请求参数验证失败
- `500 Internal Server Error`: 服务器内部错误

---

## 认证

当前版本不需要认证。生产环境应添加 JWT 或 API Key 认证。

---

## 速率限制

当前版本无速率限制。生产环境建议添加。

---

## Swagger 文档

启动服务后访问:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json
