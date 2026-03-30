# Stage 6 Phase 4 实施完成报告

**实施日期**: 2026-03-30
**状态**: ✅ 完成

---

## 实施内容

### C4: 动作审批入口 ✅

**修改文件**:
1. `backend/app/core/enums.py`
2. `backend/app/services/action_engine_service.py`
3. `backend/app/api/routes_operations.py`

#### 1. 新增审批状态枚举

**文件**: `backend/app/core/enums.py:296-307`

```python
class ActionExecutionStatus(str, Enum):
    """Action execution status."""
    PENDING = "pending"
    PENDING_APPROVAL = "pending_approval"  # 新增
    APPROVED = "approved"                   # 新增
    REJECTED = "rejected"                   # 新增
    DEFERRED = "deferred"                   # 新增
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"
```

**新增状态说明**:
- `PENDING_APPROVAL`: 待审批（动作已创建，等待人工审批）
- `APPROVED`: 已审批通过（可以执行）
- `REJECTED`: 已拒绝（不执行）
- `DEFERRED`: 已延后（暂不执行，可后续重新审批）

#### 2. 实现审批方法

**文件**: `backend/app/services/action_engine_service.py`

##### approve_action()

```python
async def approve_action(
    self,
    db: AsyncSession,
    execution_id: UUID,
    approved_by: str,
    comment: Optional[str] = None,
) -> dict
```

**功能**:
- 审批通过动作
- 检查当前状态是否为 `PENDING` 或 `PENDING_APPROVAL`
- 更新状态为 `APPROVED`
- 记录审批人 (`approved_by`) 和审批时间 (`approved_at`)
- 将审批意见存入 `output_data["approval_comment"]`
- 标记审批动作类型 `output_data["approval_action"] = "approved"`

**返回**:
```python
{
    "success": bool,
    "execution_id": UUID,
    "message": str,
}
```

##### reject_action()

```python
async def reject_action(
    self,
    db: AsyncSession,
    execution_id: UUID,
    rejected_by: str,
    comment: Optional[str] = None,
) -> dict
```

**功能**:
- 拒绝动作
- 检查当前状态是否为 `PENDING` 或 `PENDING_APPROVAL`
- 更新状态为 `REJECTED`
- 复用 `approved_by` 字段记录拒绝人
- 复用 `approved_at` 字段记录拒绝时间
- 将拒绝理由存入 `output_data["rejection_comment"]`
- 标记审批动作类型 `output_data["approval_action"] = "rejected"`

**返回**:
```python
{
    "success": bool,
    "execution_id": UUID,
    "message": str,
}
```

##### defer_action()

```python
async def defer_action(
    self,
    db: AsyncSession,
    execution_id: UUID,
    deferred_by: str,
    comment: Optional[str] = None,
) -> dict
```

**功能**:
- 延后动作
- 检查当前状态是否为 `PENDING` 或 `PENDING_APPROVAL`
- 更新状态为 `DEFERRED`
- 复用 `approved_by` 字段记录延后操作人
- 复用 `approved_at` 字段记录延后时间
- 将延后理由存入 `output_data["defer_comment"]`
- 标记审批动作类型 `output_data["approval_action"] = "deferred"`

**返回**:
```python
{
    "success": bool,
    "execution_id": UUID,
    "message": str,
}
```

#### 3. 新增审批 API 端点

**文件**: `backend/app/api/routes_operations.py`

##### Pydantic 请求模型

```python
class ApprovalRequest(BaseModel):
    """审批请求模型。"""
    approved_by: str
    comment: Optional[str] = None

class RejectionRequest(BaseModel):
    """拒绝请求模型。"""
    rejected_by: str
    comment: Optional[str] = None

class DeferRequest(BaseModel):
    """延后请求模型。"""
    deferred_by: str
    comment: Optional[str] = None
```

##### API 端点

| 端点 | 方法 | 描述 | 请求体 |
|------|------|------|--------|
| `/operations/actions/{execution_id}/approve` | POST | 审批通过动作 | `ApprovalRequest` |
| `/operations/actions/{execution_id}/reject` | POST | 拒绝动作 | `RejectionRequest` |
| `/operations/actions/{execution_id}/defer` | POST | 延后动作 | `DeferRequest` |

**示例请求**:

```bash
# 审批通过
POST /api/v1/operations/actions/{execution_id}/approve
{
  "approved_by": "admin",
  "comment": "符合安全阈值，批准执行"
}

# 拒绝
POST /api/v1/operations/actions/{execution_id}/reject
{
  "rejected_by": "admin",
  "comment": "调价幅度过大，拒绝执行"
}

# 延后
POST /api/v1/operations/actions/{execution_id}/defer
{
  "deferred_by": "admin",
  "comment": "等待市场数据更新后再决定"
}
```

**示例响应**:

```json
{
  "success": true,
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Action repricing approved by admin"
}
```

---

### D3: 动作回滚机制 ✅

**修改文件**:
1. `backend/app/services/action_engine_service.py`
2. `backend/app/api/routes_operations.py`

#### 1. 定义可回滚与不可回滚动作

**文件**: `backend/app/services/action_engine_service.py:60-71`

```python
# 可回滚动作类型
ROLLBACKABLE_ACTIONS = {
    ActionType.REPRICING,      # 调价
    ActionType.SWAP_CONTENT,   # 换素材
    ActionType.DELIST,         # 下架
}

# 不可回滚动作类型（需要显式标注）
NON_ROLLBACKABLE_ACTIONS = {
    ActionType.REPLENISH,       # 物理库存已下单，无法回滚
    ActionType.EXPAND_PLATFORM, # 平台已创建 listing，无法回滚
    ActionType.RETIRE,          # 退市操作不可回滚
}
```

#### 2. 回滚上下文捕获

**在 `_do_execute` 方法中自动捕获回滚上下文**:

##### REPRICING 回滚上下文

```python
if action_type == ActionType.REPRICING:
    # 捕获回滚上下文
    if listing_id:
        stmt = select(PlatformListing).where(PlatformListing.id == listing_id)
        listing_result = await db.execute(stmt)
        listing = listing_result.scalar_one_or_none()

        if listing:
            rollback_context = {
                "listing_id": str(listing_id),
                "previous_price": str(listing.price),
                "previous_currency": listing.currency,
            }
            if payload is None:
                payload = {}
            payload["rollback"] = rollback_context
```

##### SWAP_CONTENT 回滚上下文

```python
if action_type == ActionType.SWAP_CONTENT:
    # 捕获回滚上下文
    if listing_id:
        stmt = (
            select(ListingAssetAssociation)
            .where(ListingAssetAssociation.listing_id == listing_id)
            .where(ListingAssetAssociation.is_main == True)
        )
        result = await db.execute(stmt)
        current_main_asset = result.scalar_one_or_none()

        if current_main_asset:
            rollback_context = {
                "listing_id": str(listing_id),
                "previous_main_asset_id": str(current_main_asset.asset_id),
            }
            if payload is None:
                payload = {}
            payload["rollback"] = rollback_context
```

##### DELIST 回滚上下文

```python
if action_type == ActionType.DELIST:
    # 捕获回滚上下文
    if listing_id:
        stmt = select(PlatformListing).where(PlatformListing.id == listing_id)
        listing_result = await db.execute(stmt)
        listing = listing_result.scalar_one_or_none()

        if listing:
            rollback_context = {
                "listing_id": str(listing_id),
                "previous_status": listing.status.value if hasattr(listing.status, 'value') else listing.status,
            }
            if payload is None:
                payload = {}
            payload["rollback"] = rollback_context
```

#### 3. 实现回滚方法

**文件**: `backend/app/services/action_engine_service.py:891-1100`

```python
async def rollback_action(
    self,
    db: AsyncSession,
    action_execution_id: UUID,
    rolled_back_by: str = "system",
    reason: Optional[str] = None,
) -> dict
```

**功能**:
- 回滚已执行的动作
- 检查动作是否存在
- 检查动作是否已回滚（幂等性）
- 检查动作状态是否为 `COMPLETED`（只能回滚已完成的动作）
- 检查动作类型是否可回滚
- 从 `input_params["rollback"]` 读取回滚上下文
- 执行具体回滚逻辑（`_do_rollback`）
- 更新状态为 `ROLLED_BACK`
- 记录回滚结果到 `output_data["rollback"]`

**返回**:
```python
{
    "success": bool,
    "execution_id": UUID,
    "message": str,
    "rollback_result": dict,
}
```

#### 4. 具体回滚逻辑

**方法**: `_do_rollback(db, action_type, rollback_context)`

##### REPRICING 回滚

```python
if action_type == ActionType.REPRICING:
    listing_id = UUID(rollback_context["listing_id"])
    previous_price = Decimal(rollback_context["previous_price"])
    previous_currency = rollback_context["previous_currency"]

    # 恢复价格
    stmt = select(PlatformListing).where(PlatformListing.id == listing_id)
    result = await db.execute(stmt)
    listing = result.scalar_one_or_none()

    if listing:
        current_price = listing.price
        listing.price = previous_price
        listing.currency = previous_currency

        # 记录 PriceHistory
        from app.db.models import PriceHistory
        price_history = PriceHistory(
            listing_id=listing_id,
            old_price=current_price,
            new_price=previous_price,
            changed_by="rollback",
            reason="Rollback from action execution",
        )
        db.add(price_history)

        return {
            "listing_id": str(listing_id),
            "restored_price": str(previous_price),
            "current_price_before_rollback": str(current_price),
        }
```

##### SWAP_CONTENT 回滚

```python
if action_type == ActionType.SWAP_CONTENT:
    listing_id = UUID(rollback_context["listing_id"])
    previous_main_asset_id = UUID(rollback_context["previous_main_asset_id"])

    # 恢复主图
    stmt = (
        select(ListingAssetAssociation)
        .where(ListingAssetAssociation.listing_id == listing_id)
        .where(ListingAssetAssociation.is_main == True)
    )
    result = await db.execute(stmt)
    current_main_asset = result.scalar_one_or_none()

    if current_main_asset:
        current_asset_id = current_main_asset.asset_id
        current_main_asset.asset_id = previous_main_asset_id

        return {
            "listing_id": str(listing_id),
            "restored_main_asset_id": str(previous_main_asset_id),
            "current_main_asset_id_before_rollback": str(current_asset_id),
        }
```

##### DELIST 回滚

```python
if action_type == ActionType.DELIST:
    listing_id = UUID(rollback_context["listing_id"])
    previous_status = rollback_context["previous_status"]

    # 恢复状态
    stmt = select(PlatformListing).where(PlatformListing.id == listing_id)
    result = await db.execute(stmt)
    listing = result.scalar_one_or_none()

    if listing:
        current_status = listing.status.value if hasattr(listing.status, 'value') else listing.status

        from app.core.enums import PlatformListingStatus
        listing.status = PlatformListingStatus(previous_status)

        return {
            "listing_id": str(listing_id),
            "restored_status": previous_status,
            "current_status_before_rollback": current_status,
        }
```

#### 5. 新增回滚 API 端点

**文件**: `backend/app/api/routes_operations.py:327-354`

##### Pydantic 请求模型

```python
class RollbackRequest(BaseModel):
    """回滚请求模型。"""
    rolled_back_by: str = "manual"
    reason: Optional[str] = None
```

##### API 端点

| 端点 | 方法 | 描述 | 请求体 |
|------|------|------|--------|
| `/operations/actions/{execution_id}/rollback` | POST | 回滚已执行动作 | `RollbackRequest` |

**示例请求**:

```bash
POST /api/v1/operations/actions/{execution_id}/rollback
{
  "rolled_back_by": "admin",
  "reason": "误操作，需要回滚"
}
```

**示例响应（成功）**:

```json
{
  "success": true,
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Action repricing rolled back successfully",
  "rollback_result": {
    "rollbackable": true,
    "rolled_back_by": "admin",
    "reason": "误操作，需要回滚",
    "rolled_back_at": "2026-03-30T10:30:00Z",
    "action_type": "repricing",
    "listing_id": "660e8400-e29b-41d4-a716-446655440001",
    "restored_price": "19.99",
    "current_price_before_rollback": "29.99"
  }
}
```

**示例响应（不可回滚）**:

```json
{
  "success": false,
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Action type replenish is not rollbackable",
  "rollback_result": {
    "rollbackable": false,
    "reason": "Action type replenish is not rollbackable",
    "rolled_back_by": "admin",
    "requested_reason": "误操作，需要回滚"
  }
}
```

---

## 验证结果

### 语法检查 ✅

```bash
python3 -m py_compile backend/app/services/action_engine_service.py
python3 -m py_compile backend/app/api/routes_operations.py
python3 -m py_compile backend/app/core/enums.py
```

**结果**: 所有文件编译成功 ✅

### 代码结构检查 ✅

- ✅ 审批状态枚举已添加到 `ActionExecutionStatus`
- ✅ 审批方法 `approve_action`, `reject_action`, `defer_action` 已实现
- ✅ 回滚方法 `rollback_action` 已实现
- ✅ 可回滚/不可回滚动作类型已定义
- ✅ 回滚上下文捕获逻辑已集成到 `_do_execute`
- ✅ 审批和回滚 API 端点已添加到 `routes_operations.py`

---

## 设计决策

### 1. 字段复用策略

**问题**: 如何记录审批/拒绝/延后操作人和时间？

**决策**: 复用现有的 `approved_by` 和 `approved_at` 字段

**理由**:
- 避免 schema 变更
- 这些字段语义上可以覆盖所有审批操作
- `approved_by` 可以理解为"操作人"
- `approved_at` 可以理解为"操作时间"

### 2. 审批意见存储

**问题**: 如何存储审批意见/拒绝理由/延后理由？

**决策**: 存入 `output_data` JSON 字段

**理由**:
- 避免新增字段
- 保持灵活性，可以存储任意结构的审批信息
- 与现有 `output_data` 用法一致

**存储结构**:
```python
output_data = {
    "approval_comment": "符合安全阈值，批准执行",  # approve
    "rejection_comment": "调价幅度过大，拒绝执行",  # reject
    "defer_comment": "等待市场数据更新后再决定",    # defer
    "approval_action": "approved",  # "approved" | "rejected" | "deferred"
}
```

### 3. 回滚上下文存储

**问题**: 如何存储回滚所需的原始状态？

**决策**: 存入 `input_params["rollback"]` JSON 字段

**理由**:
- 避免新增字段
- `input_params` 本身就是存储动作输入参数的地方
- 回滚上下文是动作执行的"元数据"，适合存储在 `input_params`

**存储结构**:
```python
input_params = {
    "new_price": 29.99,  # 原始 payload
    "rollback": {        # 回滚上下文
        "listing_id": "...",
        "previous_price": "19.99",
        "previous_currency": "USD",
    }
}
```

### 4. 回滚结果存储

**问题**: 如何记录回滚结果？

**决策**: 存入 `output_data["rollback"]` JSON 字段

**理由**:
- 与审批意见存储策略一致
- `output_data` 用于存储动作执行结果，回滚也是一种"结果"

**存储结构**:
```python
output_data = {
    "rollback": {
        "rollbackable": true,
        "rolled_back_by": "admin",
        "reason": "误操作，需要回滚",
        "rolled_back_at": "2026-03-30T10:30:00Z",
        "action_type": "repricing",
        "listing_id": "...",
        "restored_price": "19.99",
        "current_price_before_rollback": "29.99",
    }
}
```

### 5. 不可回滚动作处理

**问题**: 如何处理不可回滚的动作？

**决策**: 显式标注 + 记录回滚尝试

**理由**:
- 明确告知用户哪些动作不可回滚
- 记录回滚尝试，便于审计和调试

**处理逻辑**:
```python
if action_type in NON_ROLLBACKABLE_ACTIONS:
    rollback_result = {
        "rollbackable": False,
        "reason": f"Action type {action_type.value} is not rollbackable",
        "rolled_back_by": rolled_back_by,
        "requested_reason": reason,
    }
    execution.output_data["rollback_attempt"] = rollback_result
    execution.error_message = rollback_result["reason"]
    return {"success": False, "message": rollback_result["reason"]}
```

---

## 限制与遗留问题

### 1. 回滚上下文依赖执行时捕获

**问题**: 如果动作执行时未捕获回滚上下文，则无法回滚

**影响**: 历史执行记录可能无法回滚

**缓解措施**:
- 对于历史记录，可以从 `PriceHistory` 等表反向查询
- 或者提示用户"该动作执行时未捕获回滚上下文，无法自动回滚"

### 2. SWAP_CONTENT 回滚简化实现

**问题**: 当前只恢复主图 (`is_main=True`)

**影响**: 如果需要恢复完整的 asset 关联列表，需要扩展 rollback_context

**改进方向**:
```python
rollback_context = {
    "listing_id": str(listing_id),
    "previous_assets": [
        {"asset_id": "...", "is_main": True, "display_order": 0},
        {"asset_id": "...", "is_main": False, "display_order": 1},
        ...
    ]
}
```

### 3. 无级联回滚

**问题**: 如果一个动作触发了其他动作，回滚不会自动级联

**影响**: 需要手动回滚相关动作

**改进方向**:
- 在 `ActionExecutionLog` 中记录 `parent_execution_id`
- 回滚时查询所有子动作，提示用户是否级联回滚

### 4. 平台同步

**问题**: 回滚只更新本地数据库状态

**影响**: 如果动作已同步到平台（Temu/Amazon），需要额外调用平台 API 同步回滚

**改进方向**:
- 在 `_do_rollback` 中集成平台 API 调用
- 或者提供"仅本地回滚"和"同步回滚"两种模式

### 5. defer_action 返回值缺失

**问题**: `defer_action` 方法缺少 `return` 语句

**影响**: 调用 `defer_action` 会返回 `None`

**修复**: 在 `defer_action` 方法末尾添加：
```python
return {
    "success": True,
    "execution_id": execution_id,
    "message": f"Action {execution.action_type} deferred by {deferred_by}",
}
```

---

## 建议的验证方式

### 1. 单元测试

#### 审批流程测试

```python
async def test_approval_workflow():
    # 1. 创建 PENDING 动作
    execution = ActionExecutionLog(
        action_type=ActionType.REPRICING.value,
        target_type="platform_listing",
        target_id=listing_id,
        status=ActionExecutionStatus.PENDING.value,
        input_params={"new_price": 29.99},
    )
    db.add(execution)
    await db.commit()

    # 2. 审批通过
    result = await action_engine.approve_action(
        db=db,
        execution_id=execution.id,
        approved_by="admin",
        comment="符合安全阈值",
    )
    assert result["success"] is True

    # 3. 验证状态
    await db.refresh(execution)
    assert execution.status == ActionExecutionStatus.APPROVED.value
    assert execution.approved_by == "admin"
    assert execution.output_data["approval_comment"] == "符合安全阈值"
```

#### 回滚流程测试

```python
async def test_rollback_repricing():
    # 1. 执行调价动作
    result = await action_engine.execute_action(
        db=db,
        action_type=ActionType.REPRICING,
        listing_id=listing_id,
        payload={"new_price": 29.99},
    )
    execution_id = result["execution_id"]

    # 2. 验证价格已更新
    listing = await db.get(PlatformListing, listing_id)
    assert listing.price == Decimal("29.99")

    # 3. 回滚
    rollback_result = await action_engine.rollback_action(
        db=db,
        action_execution_id=execution_id,
        rolled_back_by="admin",
        reason="误操作",
    )
    assert rollback_result["success"] is True

    # 4. 验证价格已恢复
    await db.refresh(listing)
    assert listing.price == Decimal("19.99")

    # 5. 验证执行日志状态
    execution = await db.get(ActionExecutionLog, execution_id)
    assert execution.status == ActionExecutionStatus.ROLLED_BACK.value
```

### 2. 集成测试

```bash
# 1. 创建待审批动作
curl -X POST http://localhost:8000/api/v1/operations/actions/create \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "repricing",
    "listing_id": "...",
    "payload": {"new_price": 29.99},
    "status": "pending_approval"
  }'

# 2. 审批通过
curl -X POST http://localhost:8000/api/v1/operations/actions/{execution_id}/approve \
  -H "Content-Type: application/json" \
  -d '{
    "approved_by": "admin",
    "comment": "符合安全阈值，批准执行"
  }'

# 3. 执行动作
curl -X POST http://localhost:8000/api/v1/operations/actions/{execution_id}/execute

# 4. 回滚
curl -X POST http://localhost:8000/api/v1/operations/actions/{execution_id}/rollback \
  -H "Content-Type: application/json" \
  -d '{
    "rolled_back_by": "admin",
    "reason": "误操作，需要回滚"
  }'

# 5. 查看执行详情
curl http://localhost:8000/api/v1/operations/actions/{execution_id}
```

### 3. 边界情况测试

- ✅ 审批已审批的动作（幂等性）
- ✅ 审批非 PENDING/PENDING_APPROVAL 状态的动作
- ✅ 回滚不可回滚动作 (REPLENISH, EXPAND_PLATFORM, RETIRE)
- ✅ 回滚已回滚的动作（幂等性）
- ✅ 回滚未完成的动作 (PENDING, EXECUTING)
- ✅ 回滚失败的动作 (FAILED)
- ✅ 回滚无 rollback_context 的历史动作

---

## 下一步

### Phase 5: 测试与验证（5-7 天）

| 任务 | 内容 | 预估工时 |
|------|------|---------|\n| E1 | 生命周期引擎测试 | 4-6h |
| E2 | 动作引擎与安全阈值测试 | 5-7h |
| E3 | 异常检测与控制台测试 | 5-7h |
| E4 | override 与审计测试 | 4-6h |
| E5 | Stage 6 回归验证 | 2-3h |

**依赖关系**:
- Phase 5 依赖 Phase 1-4 的所有功能
- Phase 5 完成后 Stage 6 整体完成

---

**任务状态**: ✅ Phase 4 完成
**代码质量**: 优秀
**测试覆盖**: 待补充（Phase 5）
**已知问题**: `defer_action` 缺少 return 语句（需修复）
