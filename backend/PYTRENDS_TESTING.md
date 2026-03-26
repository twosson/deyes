# pytrends 集成测试指南

## 安装依赖

在运行测试前，需要安装项目依赖：

```bash
cd /Users/twosson/deyes/backend

# 方式 1: 使用 pip 安装项目（推荐）
pip install -e .

# 方式 2: 手动安装核心依赖
pip install pytrends>=4.9.2 structlog>=24.4.0 pydantic>=2.9.2 pydantic-settings>=2.6.0
```

## 运行测试

### 单元测试（不需要网络）

```bash
cd /Users/twosson/deyes/backend

# 运行所有单元测试
pytest tests/test_demand_validator.py -v -m "not integration"

# 运行特定测试类
pytest tests/test_demand_validator.py::TestDemandValidationResult -v

# 运行特定测试方法
pytest tests/test_demand_validator.py::TestDemandValidator::test_region_to_geo -v
```

### 集成测试（需要网络，会调用 Google Trends API）

```bash
cd /Users/twosson/deyes/backend

# 运行集成测试
pytest tests/test_demand_validator.py -v -m integration

# 注意：集成测试会真实调用 Google Trends API
# - 需要网络连接
# - 可能被速率限制
# - 建议不要频繁运行
```

## 测试覆盖

### 已实现的测试

**TestDemandValidationResult** - 验证结果数据类测试
- ✅ `test_passed_with_good_metrics` - 好指标通过验证
- ✅ `test_rejected_low_search_volume` - 低搜索量被拒绝
- ✅ `test_rejected_high_competition` - 高竞争被拒绝
- ✅ `test_rejected_declining_trend` - 下滑趋势被拒绝
- ✅ `test_multiple_rejection_reasons` - 多个拒绝原因
- ✅ `test_to_dict` - 转换为字典

**TestDemandValidator** - 需求验证服务测试
- ✅ `test_init_default` - 默认初始化
- ✅ `test_init_custom` - 自定义初始化
- ✅ `test_init_helium10_without_key` - Helium 10 无 key 回退
- ✅ `test_region_to_geo` - 区域代码转换
- ✅ `test_estimate_search_volume_from_interest` - 搜索量估算
- ✅ `test_classify_trend_direction` - 趋势分类
- ✅ `test_validate_with_mock_pytrends` - 使用 mock 验证
- ✅ `test_validate_batch` - 批量验证

**TestDemandValidatorIntegration** - 集成测试（需要网络）
- ✅ `test_pytrends_real_keyword` - 真实关键词测试
- ✅ `test_pytrends_obscure_keyword` - 冷门关键词测试
- ✅ `test_pytrends_different_regions` - 不同地区测试

**其他测试**
- ✅ `test_pytrends_fallback_on_import_error` - pytrends 未安装时回退

## 手动测试

如果无法运行 pytest，可以使用简单测试脚本：

```bash
cd /Users/twosson/deyes/backend

# 先安装依赖
pip install pytrends structlog pydantic pydantic-settings

# 运行简单测试
python3 test_demand_validator_simple.py
```

## 验证 pytrends 是否正常工作

```python
# 在 Python REPL 中测试
python3

>>> from pytrends.request import TrendReq
>>> pytrends = TrendReq(hl='en-US', tz=360)
>>> pytrends.build_payload(kw_list=['iphone'], timeframe='today 12-m', geo='US')
>>> df = pytrends.interest_over_time()
>>> print(df.head())
>>> print(f"Average interest: {df['iphone'].mean()}")
```

如果能看到数据，说明 pytrends 工作正常。

## 常见问题

### Q1: ModuleNotFoundError: No module named 'pytrends'

**解决方案：**
```bash
pip install pytrends>=4.9.2
```

### Q2: Google Trends 速率限制

**现象：** 频繁请求后返回 429 错误或空数据

**解决方案：**
- 减少请求频率
- 添加请求间隔（sleep）
- 实现 Redis 缓存（推荐）

### Q3: 测试失败：No data returned

**原因：** 关键词太冷门，Google Trends 无数据

**解决方案：** 使用更热门的关键词测试（如 "iphone", "phone case"）

## 下一步

测试通过后，可以继续：

1. **实现 Redis 缓存** - 避免重复请求 Google Trends
2. **实现竞争密度评估** - `_assess_competition_density()` 方法
3. **集成到 ProductSelectorAgent** - 在生产环境启用
4. **监控和优化** - 添加性能监控和错误追踪

## 测试文件位置

- 单元测试：`/Users/twosson/deyes/backend/tests/test_demand_validator.py`
- 简单测试：`/Users/twosson/deyes/backend/test_demand_validator_simple.py`
- 服务实现：`/Users/twosson/deyes/backend/app/services/demand_validator.py`
