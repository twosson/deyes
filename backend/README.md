# Deyes Backend - Agent Layer MVP

跨境电商数字员工系统 - Agent 编排层

## 项目结构

```
backend/
├── app/
│   ├── agents/          # Agent 实现
│   ├── api/             # FastAPI 路由
│   ├── clients/         # 外部服务客户端
│   ├── core/            # 核心配置和工具
│   ├── db/              # 数据库模型和会话
│   ├── schemas/         # Pydantic schemas
│   ├── services/        # 业务逻辑服务
│   ├── workers/         # Celery 任务
│   └── main.py          # FastAPI 应用入口
├── migrations/          # Alembic 迁移
├── tests/               # 测试
├── Dockerfile
├── pyproject.toml
└── alembic.ini
```

## MVP 功能

实现了 4 个核心 Agent 的产品发现和上架准备流程:

1. **Product Selector Agent** - 发现候选商品
2. **Pricing Analyst Agent** - 计算利润和定价
3. **Risk Controller Agent** - 风险评估和合规检查
4. **Multilingual Copywriter Agent** - 生成多语言文案

## 快速开始

### 本地开发

1. 安装依赖:
```bash
cd backend
pip install -e .
```

2. 配置环境变量:
```bash
cp .env.example .env
# 编辑 .env 文件
```

3. 运行数据库迁移:
```bash
alembic upgrade head
```

4. 启动 API 服务:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

5. 启动 Celery Worker:
```bash
celery -A app.workers.celery_app worker --loglevel=info
```

### Docker / 服务器部署

完整部署请统一参考仓库根目录文档：

```bash
cd ..
cat DEPLOYMENT.md
```

如只需调试 backend，本 README 仅保留本地开发说明。

## API 端点

### 健康检查
- `GET /api/v1/health` - 基础健康检查
- `GET /api/v1/health/ready` - 就绪检查（含依赖验证）

### Agent 运行
- `POST /api/v1/agent-runs` - 创建发现任务
- `GET /api/v1/agent-runs/{run_id}` - 获取运行状态
- `GET /api/v1/agent-runs/{run_id}/results` - 获取结果

### 示例请求

创建发现任务:
```bash
curl -X POST http://localhost:8000/api/v1/agent-runs \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "temu",
    "category": "phone accessories",
    "keywords": ["magsafe", "iphone"],
    "price_min": 10.00,
    "price_max": 40.00,
    "target_languages": ["en", "es", "ja"],
    "max_candidates": 10
  }'
```

查询状态:
```bash
curl http://localhost:8000/api/v1/agent-runs/{run_id}
```

获取结果:
```bash
curl http://localhost:8000/api/v1/agent-runs/{run_id}/results
```

## 测试

运行测试:
```bash
pytest
```

运行测试并查看覆盖率:
```bash
pytest --cov=app --cov-report=html
```

## 架构说明

### Agent 编排

Director Workflow 按顺序执行 4 个 Agent:
1. Product Selector → 发现候选商品并匹配供应商
2. Pricing Analyst → 计算利润和定价
3. Risk Controller → 风险评估
4. Multilingual Copywriter → 生成多语言文案

### 数据流

```
API Request → Celery Task → Director Workflow
                                ↓
                    Product Selector Agent
                                ↓
                    Pricing Analyst Agent
                                ↓
                    Risk Controller Agent
                                ↓
                Multilingual Copywriter Agent
                                ↓
                    Results (ranked by margin)
```

### 服务层

- **PricingService** - 利润计算公式
- **RiskRulesEngine** - 基于规则的风险评估
- **CopywriterService** - SGLang 结构化文案生成
- **SourceAdapter** - 产品数据源接口（当前为 Mock）
- **SupplierMatcherService** - 供应商匹配（当前为 Mock）

## 下一步

MVP 完成后的扩展方向:

1. 添加真实数据源（平台爬虫或 API）
2. 集成 1688 供应商匹配
3. 引入 LangGraph 实现可恢复编排
4. 添加更多 Agent（ERP Manager, QA Agent 等）
5. 集成 ComfyUI 图像生成
6. 添加 RPA 自动上架
7. 构建管理后台

## 技术栈

- **FastAPI** - Web 框架
- **SQLAlchemy 2.0** - ORM
- **Alembic** - 数据库迁移
- **Celery** - 异步任务队列
- **Redis** - 缓存和消息代理
- **PostgreSQL** - 主数据库
- **SGLang** - LLM 推理引擎
- **Pydantic** - 数据验证

## 许可证

内部项目
