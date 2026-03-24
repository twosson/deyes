# Deyes 统一部署指南

> 本文件是仓库唯一的部署说明。
>
> 前端、后端、数据库、缓存、向量库、对象存储、SGLang 与 ComfyUI 统一按本文部署；历史分散部署教程已废弃。

---

## 1. 部署范围

当前仓库默认通过根目录 `docker-compose.yaml` 启动整套服务：

- `postgres`：主数据库
- `redis`：缓存与 Celery broker
- `qdrant`：向量检索
- `minio`：对象存储
- `sglang`：LLM 推理服务
- `comfyui-1`：图像生成服务
- `backend`：FastAPI API
- `worker`：Celery Worker
- `frontend`：Vue 运营中台

这是当前**唯一受支持的完整部署路径**。

---

## 2. 服务器前置条件

推荐环境：

- Ubuntu 22.04
- Docker 24+
- Docker Compose 2+
- NVIDIA Driver 550+
- NVIDIA Container Toolkit
- 8x RTX 4090（当前项目文档的推荐硬件）
- `/data` 至少预留 200GB 可用空间

基础检查：

```bash
uname -a
docker --version
docker compose version
nvidia-smi
```

如 Docker 无法识别 GPU，先安装并验证 NVIDIA Container Toolkit：

```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

---

## 3. 准备代码与目录

在服务器选择一个固定部署目录，例如：

```bash
git clone <your-repo-url> ~/deyes
cd ~/deyes
```

创建运行时目录：

```bash
sudo mkdir -p /data/deyes/{postgres,redis,qdrant,minio}
sudo mkdir -p /data/deyes/models/llm
sudo mkdir -p /data/deyes/comfyui/workspace-1
sudo chown -R $USER:$USER /data/deyes
```

这些目录对应 `docker-compose.yaml` 中的持久化卷。

---

## 4. 准备环境变量

在仓库根目录创建 `.env`：

```bash
cat > .env <<'EOF'
POSTGRES_PASSWORD=change-this-postgres-password
MINIO_PASSWORD=change-this-minio-password
EOF
chmod 600 .env
```

当前 compose 文件直接依赖这两个变量；如果缺失，`docker compose` 启动时会报错。

---

## 5. 准备模型与 AI 依赖

### 5.1 SGLang 模型目录

`sglang` 服务当前固定读取：

```text
/data/deyes/models/llm/Qwen3___5-35B-A3B-FP8
```

请先确保该目录已经存在且模型已下载完成，否则 `sglang` 容器会启动失败。

### 5.2 ComfyUI 工作目录

当前 `comfyui-1` 使用：

```text
/data/deyes/comfyui/workspace-1
```

容器启动后会在该目录下维护工作区与下载内容。首次启动依赖外网访问镜像站，网络不稳定时请优先检查下载日志。

### 5.3 基础连通性

建议在启动前确认：

```bash
ls -la /data/deyes/models/llm
curl -I https://hf-mirror.com
```

---

## 6. 数据库初始化与首次启动

### 6.1 数据库初始化机制

当前仓库使用 Alembic 管理数据库结构，迁移文件位于：

- `backend/migrations/versions/20260321_1200_001_initial.py`
- `backend/migrations/versions/20260321_1300_002_add_strategy_run_region.py`

`backend` 容器的启动命令已经内置：

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

因此**首次启动 backend 时会自动初始化数据库表结构**，后续启动也会自动补齐未执行的迁移。

### 6.2 首次启动推荐顺序

虽然可以直接 `docker compose up -d`，但首次部署建议按下面顺序检查：

```bash
# 1. 先启动基础依赖
docker compose up -d postgres redis qdrant minio

# 2. 确认 PostgreSQL 已 healthy
docker compose ps

# 3. 再启动后端、worker、frontend
docker compose up -d backend worker frontend

# 4. 最后启动 AI 服务
docker compose up -d sglang comfyui-1
```

### 6.3 手动执行数据库迁移

如果你想单独执行或确认迁移状态，可以运行：

```bash
# 执行迁移
docker compose run --rm backend alembic upgrade head

# 查看当前迁移版本
docker compose run --rm backend alembic current

# 查看迁移历史
docker compose run --rm backend alembic history
```

### 6.4 验证数据库表是否已创建

```bash
docker compose exec postgres psql -U deyes -d deyes -c "\dt"
```

也可以检查关键表：

```bash
docker compose exec postgres psql -U deyes -d deyes -c "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"
```

### 6.5 重新初始化数据库（危险操作）

如果这是早期开发阶段，且你明确要清空数据库重新初始化，可以使用：

```bash
# 停止服务
docker compose down

# 删除 PostgreSQL 数据目录内容
sudo rm -rf /data/deyes/postgres/*

# 重新启动数据库与后端
docker compose up -d postgres redis
docker compose up -d backend
```

`backend` 启动时会再次自动执行 `alembic upgrade head` 完成重建。

---

## 7. 启动整套服务

在仓库根目录执行：

```bash
docker compose up -d
```

检查状态：

```bash
docker compose ps
```

查看关键日志：

```bash
docker compose logs -f postgres
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f sglang
docker compose logs -f frontend
```

说明：

- `backend` 容器启动命令中会自动执行 `alembic upgrade head`
- `frontend` 容器会执行 `npm install && npm run dev`
- `backend` 与 `worker` 已通过 `extra_hosts` 兼容 Linux 上的 `host.docker.internal`

---

## 8. 验证部署结果

### 8.1 服务端口

| 服务 | 地址 | 说明 |
|---|---|---|
| Frontend | `http://<server-ip>:5173` | 运营中台 |
| Backend API | `http://<server-ip>:8000` | FastAPI |
| Swagger | `http://<server-ip>:8000/docs` | API 文档 |
| SGLang | `http://<server-ip>:30000/v1/models` | 模型服务 |
| MinIO API | `http://<server-ip>:9000` | 对象存储 API |
| MinIO Console | `http://<server-ip>:9001` | 管理控制台 |
| Qdrant | `http://<server-ip>:6333` | 向量库 |
| ComfyUI | `http://<server-ip>:3000` | 图像服务 |

### 8.2 API 健康检查

```bash
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/health/ready
curl http://127.0.0.1:30000/v1/models
```

### 8.3 前端联通性

浏览器打开：

```text
http://<server-ip>:5173
```

前端在 compose 中已配置：

- `VITE_PROXY_TARGET=http://backend:8000`
- `VITE_API_BASE_URL=/api/v1`

因此页面通过 `/api/*` 即可代理到后端。

### 8.4 任务链路抽样验证

```bash
curl -X POST http://127.0.0.1:8000/api/v1/agent-runs \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "temu",
    "category": "phone accessories",
    "keywords": ["magsafe"],
    "price_min": 10,
    "price_max": 40,
    "target_languages": ["en"],
    "max_candidates": 5
  }'
```

再验证以下接口：

```bash
curl http://127.0.0.1:8000/api/v1/agent-runs
curl http://127.0.0.1:8000/api/v1/content-assets/stats/distribution
curl http://127.0.0.1:8000/api/v1/platform-listings/stats/distribution
```

---

## 9. 常用运维命令

### 9.1 重启服务（源码变更后）

当你修改了挂载目录里的 Python 源码、配置文件或环境变量，只需要重启容器即可生效，不需要重新构建镜像：

```bash
docker compose restart backend
docker compose restart worker
docker compose restart frontend
```

这种方式速度快，适用于日常开发和调试。

### 9.2 重新构建镜像（依赖或镜像层变更后）

当你修改了以下内容时，必须重新构建镜像：

- `backend/Dockerfile`
- `backend/pyproject.toml`（新增或升级 Python 依赖）
- Playwright / Chromium 安装逻辑
- 其他需要进入镜像层的构建文件

首次构建或只想预热共享镜像时，可以先执行：

```bash
docker compose build backend
```

重新构建并启动：

```bash
docker compose up -d --build backend worker
```

说明：
- `backend` 和 `worker` 共享同一个镜像 `deyes-backend-runtime:latest`
- 只需要构建一次，两个服务会自动复用
- 如果只是源码变更，优先使用 `restart` 而不是 `--build`

### 9.3 其他常用命令

停止整套服务：

```bash
docker compose down
```

查看最近日志：

```bash
docker compose logs --tail=200 backend
docker compose logs --tail=200 worker
docker compose logs --tail=200 sglang
```

---

## 10. 常见问题

### 10.1 `.env` 缺失或变量为空

现象：`POSTGRES_PASSWORD` / `MINIO_PASSWORD` 未替换，容器直接启动失败。

处理：

```bash
ls -la .env
cat .env
```

### 10.2 SGLang 启动失败

优先检查模型目录是否存在且名称匹配：

```bash
ls -la /data/deyes/models/llm

docker compose logs --tail=200 sglang
```

### 10.3 前端无法访问后端

先确认 `backend` 正常启动：

```bash
docker compose ps
docker compose logs --tail=200 backend
curl http://127.0.0.1:8000/api/v1/health
```

### 10.4 GPU 容器看不到显卡

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

如果第二条失败，说明 Docker GPU 运行时未配置完成。

### 10.5 持久化目录权限问题

```bash
sudo chown -R $USER:$USER /data/deyes
```

---

## 11. 安全与上线说明

当前仓库中的 compose 更适合**内网环境或受控服务器验证**。如果要直接暴露到公网，至少先处理以下问题：

1. 替换 `.env` 中的数据库和 MinIO 密码
2. 为前端和后端增加反向代理与 TLS
3. 收紧 `5432`、`6379`、`6333`、`9000`、`9001` 等端口暴露策略
4. 将 ComfyUI 访问密码改为外部安全配置，而不是直接写在 compose 文件中
5. 为对象存储和管理端口增加访问控制

---

## 12. 文档边界

为避免出现多份冲突部署教程，规则如下：

- **部署步骤只以本文件为准**
- `backend/README.md` 仅保留 backend 本地开发说明
- 其他文档只允许引用本文件，不再重复维护完整部署步骤
- 历史部署文档已清理，不再保留归档材料

---

**最后更新**: 2026-03-23
**状态**: 当前仓库统一部署入口
