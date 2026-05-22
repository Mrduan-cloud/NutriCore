# NutriCore 部署指南

> 本文档涵盖两类部署场景：
> 1. **个人电脑（开发 / 调试 / 面试演示）** — Windows / macOS / Linux 均可
> 2. **企业私有化服务器（生产 / 内网试点）** — 推荐 Ubuntu 22.04 LTS

> 阅读顺序：先看 [§1 端口与依赖映射](#1-端口与依赖映射)，再按你的场景跳到 §2 或 §3。

---

## 1. 端口与依赖映射

| 服务      | 端口      | 用途                             | 必装   |
| --------- | --------- | -------------------------------- | ------ |
| api       | 8000      | FastAPI / Swagger / 业务接口     | 是     |
| mysql     | 3306      | 业务库（用户 / 方案 / 摄入数据） | 是     |
| redis     | 6379      | 会话缓存 / 限流                  | 是     |
| milvus    | 19530     | 向量库（gRPC）                   | 是     |
| milvus    | 9091      | Milvus 健康检查 HTTP             | 是     |
| minio     | 9000      | S3 兼容对象存储（PDF 报告归档）  | 是     |
| minio     | 9001      | MinIO Web 控制台                 | 否     |
| etcd      | (内部)    | Milvus 元数据存储                | 是     |
| **vLLM**  | **8001**  | **Qwen2.5-32B-AWQ on 2× RTX 4090** | **是** |
| Dify      | 8080      | 数据洞察可视化编排               | 可选   |
| Prometheus / Grafana | 9090/3000 | 可观测性               | 推荐   |

> **关键依赖**：Docker 24+、Docker Compose v2、Python 3.11+（仅本地开发非容器化跑 API 时用）。

---

## 2. 个人电脑部署（开发 / 测试）

### 2.1 推荐硬件配置（本地全栈跑起来）

| 资源     | 最低           | 推荐                | 说明                                                       |
| -------- | -------------- | ------------------- | ---------------------------------------------------------- |
| CPU      | 4 核           | 8 核+               | RAG / Embedding 计算密集                                   |
| 内存     | 16 GB          | **32 GB**           | BGE 模型 + Milvus + LLM 推理常驻；少于 16G 几乎跑不动     |
| 磁盘     | 50 GB SSD      | 100 GB+ SSD         | 含模型权重 ~10G + 数据卷                                   |
| 显卡     | 不需要         | 可选 (NVIDIA 12G+)  | 本机跑 32B-AWQ 需要 2× 24GB；否则连远程 LLM 或本地 Ollama |
| 网络     | -              | -                   | 首次下载 ~15G 镜像 + 模型权重                              |

> **开发机不需要 4090**：默认 `.env.example` 已经配好远程 LLM URL；本地没卡的话注释打开末尾的 Ollama 替代方案块即可秒切到 `qwen2.5:7b-instruct`。详见 §2.5。

### 2.2 操作系统建议

| 系统               | 备注                                                                   |
| ------------------ | ---------------------------------------------------------------------- |
| **Windows 10/11** | 必须开启 WSL2 + Docker Desktop。本工程已用 `host.docker.internal` 适配 |
| **macOS 14+**     | Apple Silicon (M1/M2/M3) 完全兼容，Docker Desktop 装好即可             |
| **Linux**         | Ubuntu 22.04 / 24.04 LTS 推荐，原生 Docker 性能最佳                    |

### 2.3 Windows 上一步步部署（最详细，其他系统类似）

```powershell
# 1. 装 Docker Desktop (https://docs.docker.com/desktop/install/windows-install/)
#    安装时勾选 "Use WSL 2 instead of Hyper-V"

# 2. 装 Python 3.11+ (https://www.python.org/downloads/) — 仅当你想在容器外跑 API 调试

# 3. 装 Git (https://git-scm.com/download/win)

# 4. 克隆仓库
git clone https://github.com/Mrduan-cloud/NutriCore.git
cd NutriCore

# 5. 准备 .env
copy .env.example .env
# 用记事本打开 .env，至少改三个：
#   JWT_SECRET_KEY=自己生成的长随机串
#   MYSQL_PASSWORD=自己设置
#   LLM_BASE_URL=你的 LLM 服务地址（见 §2.5）

# 6. 启动栈
docker compose up -d
# 第一次会拉镜像，预计 5-15 分钟

# 7. 等所有服务 healthy
docker compose ps
# 看到 mysql / redis / minio / milvus / api 都是 (healthy)

# 8. 初始化数据 (建表 / Milvus 集合 / 灌知识库 / Demo 用户)
docker compose exec api python -m scripts.seed

# 9. 验证
#   - Swagger:  http://localhost:8000/docs
#   - 健康:     http://localhost:8000/ready
#   - MinIO:    http://localhost:9001 (账号 minioadmin/minioadmin)
#   - Metrics:  http://localhost:8000/metrics

# 10. 跑端到端 demo
docker compose exec api python -m scripts.demo
```

### 2.4 macOS / Linux 步骤（同上，命令略改）

```bash
git clone https://github.com/Mrduan-cloud/NutriCore.git && cd NutriCore
cp .env.example .env
nano .env                       # 改密码 / token / LLM_BASE_URL
docker compose up -d
docker compose ps
docker compose exec api python -m scripts.seed
docker compose exec api python -m scripts.demo
```

### 2.5 LLM 选哪个？(本地开发场景)

本工程通过 OpenAI 兼容协议调用。生产默认是 **vLLM + Qwen2.5-32B-Instruct-AWQ + 2× RTX 4090 + TP=2**，开发机按硬件灵活降级：

**① 生产同款（有 2× RTX 4090 24G 或更高）— vLLM + 32B AWQ + TP=2**
```bash
pip install vllm

# 启动推理服务（约 5-10 分钟下载模型权重 ~17GB）
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-32B-Instruct-AWQ \
  --tensor-parallel-size 2 \
  --gpu-memory-utilization 0.9 \
  --max-model-len 8192 \
  --host 0.0.0.0 --port 8001

# .env 保持默认即可：
# LLM_BASE_URL=http://host.docker.internal:8001/v1
# LLM_MODEL=Qwen/Qwen2.5-32B-Instruct-AWQ
```

技术要点：
- **AWQ Int4 量化**：32B 模型显存 ~64GB → ~20GB，让消费级双 4090 能跑
- **Tensor Parallel TP=2**：vLLM 自动把权重切到 2 张卡，前向跨卡 all-reduce
- **显存预算**：单卡 24GB ≈ 10GB(模型分片) + 12GB(KV cache) + 2GB(余量)

**② 没有 4090（开发机常态）— Ollama 跑 7B 凑合用**
```bash
# https://ollama.com/download
ollama pull qwen2.5:7b-instruct
ollama serve

# .env 末尾的注释块取消注释：
# LLM_BASE_URL=http://host.docker.internal:11434/v1
# LLM_API_KEY=ollama
# LLM_MODEL=qwen2.5:7b-instruct
```

**③ 单 4090 / 16GB 显卡 — vLLM + 14B AWQ（折中）**
```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-14B-Instruct-AWQ \
  --gpu-memory-utilization 0.9 --max-model-len 4096 --host 0.0.0.0 --port 8001
```

**④ 调用第三方 OpenAI 兼容服务**（DeepSeek / 智谱 / 阿里通义等）
```bash
# .env:
# LLM_BASE_URL=https://api.deepseek.com/v1
# LLM_API_KEY=sk-xxxxxxx
# LLM_MODEL=deepseek-chat
```

### 2.6 常见坑（开发机）

| 现象                                                | 原因 / 解决                                                                         |
| --------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `docker compose up` 卡在 Milvus pulling             | 镜像 5 GB+，换国内镜像源（阿里云/腾讯云加速器）                                     |
| `api` 启动后 `/ready` 返回 milvus=false             | 等 Milvus 第一次起来要 60-90s，多等会儿。或 `docker compose logs milvus` 看是否报错 |
| BGE 第一次推理慢（30s+）                            | 首次会下载 ~1.5G 模型权重到 `model_cache` 卷；下载完后秒级                          |
| Win 上 `host.docker.internal` 解析不到              | Docker Desktop 升级到最新版；或在 compose 里用 `extra_hosts` 显式映射               |
| 内存爆掉（OOM）                                     | Docker Desktop → Settings → Resources，分配内存到 ≥ 12 GB                           |
| LLM 调用超时                                        | 检查 `LLM_BASE_URL` 是不是 `host.docker.internal:port`（容器访问宿主机），不是 `localhost` |

---

## 3. 企业私有化服务器部署（生产）

### 3.1 服务器配置建议

> NutriCore 是 RAG + 多 Agent + 私有化 LLM 的典型 AI 工作负载。**推荐拆 2 台机器：业务服务器 + GPU 推理服务器**。如果只能单机，按"单机一体部署"配置。
>
> 不同公司阶段的硬件选型 / 成本 / ROI 对照表见 [`docs/HARDWARE.md`](HARDWARE.md)。

#### 方案 A：小公司私有化（默认推荐 ⭐）

| 角色           | 用途                                | CPU      | 内存       | 磁盘            | GPU                                              | 整机预算       |
| -------------- | ----------------------------------- | -------- | ---------- | --------------- | ------------------------------------------------ | -------------- |
| 业务服务器     | API / MySQL / Redis / Milvus / MinIO | 16 核   | **64 GB**  | 500 GB SSD     | 不需要                                           | ~1.5 万 RMB    |
| 推理服务器     | vLLM + Embedding + Reranker         | 16 核   | 64 GB      | 200 GB SSD     | **2× RTX 4090 24G**（Qwen2.5-32B-AWQ + TP=2）   | **~5–7 万 RMB** |

- **为什么选 4090**：AWQ Int4 + Tensor Parallel 让 32B 模型显存压到 ~20GB，消费级双卡能跑；整机预算约是 A100 方案的 1/5
- **限制**：4090 不支持 NVLink，跨卡通信走 PCIe（实测影响 <10% 吞吐）；不适合 fp16 70B 大模型

#### 方案 B：中型企业（需要更高并发 / 更大模型）

| 角色           | 配置                                                  | 适用场景                          |
| -------------- | ----------------------------------------------------- | --------------------------------- |
| 推理服务器     | 2× L40S 48G 或 2× A100 80G                            | 32B FP16 / 70B AWQ / >50 并发     |
| 业务服务器     | 同上方案 A 但内存提到 128 GB                          | 多客户、长会话                    |

整机预算约 **20–40 万 RMB**（L40S）或 **30–40 万 RMB**（A100）。

#### 方案 C：单机一体（POC / 单一客户私有化）

| 资源 | 配置                                                                       |
| ---- | -------------------------------------------------------------------------- |
| CPU  | 16-32 核                                                                   |
| 内存 | **128 GB**                                                                 |
| 磁盘 | 1 TB NVMe SSD                                                              |
| GPU  | 2× RTX 4090 24G（同方案 A 推理机配置，但把业务服务也塞进同一台）           |

### 3.2 操作系统选择

| 系统                  | 推荐度      | 备注                                                          |
| --------------------- | ----------- | ------------------------------------------------------------- |
| **Ubuntu 22.04 LTS** | ★★★★★      | 首选，社区文档最全，NVIDIA 驱动支持成熟                       |
| Ubuntu 24.04 LTS     | ★★★★       | 24.04 部分企业镜像仓 / 内核驱动还在适配中                     |
| Debian 12            | ★★★★       | 服务器场景同样稳，但 NVIDIA 工具链生态稍少                    |
| RHEL 9 / Rocky 9     | ★★★         | 国企 / 金融客户常用；NVIDIA 驱动需要额外配置 SELinux            |
| OpenEuler 24.03      | ★★★         | 国产化路径；社区 Docker 包配置稍麻烦                          |
| Kylin V10 / UOS      | ★★          | 信创要求场景；需要厂商提供 Docker 与 NVIDIA 适配               |

### 3.3 Ubuntu 22.04 完整部署命令（生产）

```bash
# ============== 0. 预检 ==============
lsb_release -a            # 确认 22.04
nproc && free -h && df -h # 看配置
nvidia-smi                # GPU 机器跑这条，确认驱动

# ============== 1. 装 Docker ==============
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker $USER
newgrp docker   # 当前会话生效

# ============== 2. (GPU 机器) 装 NVIDIA Container Toolkit ==============
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi  # 验证

# ============== 3. 系统调优（强烈建议） ==============
# 3.1 文件描述符
sudo bash -c 'cat >> /etc/security/limits.conf <<EOF
* soft nofile 65535
* hard nofile 65535
EOF'

# 3.2 内核参数（Milvus / Redis）
sudo bash -c 'cat >> /etc/sysctl.conf <<EOF
vm.max_map_count=262144
vm.overcommit_memory=1
net.core.somaxconn=4096
EOF'
sudo sysctl -p

# 3.3 关闭 swap（Milvus 不喜欢）
sudo swapoff -a
sudo sed -i '/ swap / s/^/#/' /etc/fstab

# 3.4 时区
sudo timedatectl set-timezone Asia/Shanghai

# ============== 4. 拉代码 ==============
sudo mkdir -p /opt/nutricore && sudo chown $USER /opt/nutricore
cd /opt/nutricore
git clone https://github.com/Mrduan-cloud/NutriCore.git .

# ============== 5. 配 .env (生产化) ==============
cp .env.example .env
# 必改项：
#   APP_ENV=prod
#   LOG_JSON=true
#   JWT_SECRET_KEY=$(openssl rand -hex 32)
#   MYSQL_ROOT_PASSWORD=$(openssl rand -hex 16)
#   MYSQL_PASSWORD=$(openssl rand -hex 16)
#   MINIO_ACCESS_KEY=$(openssl rand -hex 16)
#   MINIO_SECRET_KEY=$(openssl rand -hex 32)
#   CORS_ORIGINS=["https://nutricore.your-company.com"]
#   LLM_BASE_URL=http://10.0.x.x:8001/v1   # 推理服务器内网 IP
nano .env

# ============== 6. 启动 ==============
docker compose pull
docker compose up -d

# 等 60-120s 让所有服务 healthy
watch -n 3 'docker compose ps'

# ============== 7. 初始化数据 ==============
docker compose exec api python -m scripts.seed

# ============== 8. 反向代理 + HTTPS (nginx + Let's Encrypt) ==============
sudo apt install -y nginx certbot python3-certbot-nginx
sudo tee /etc/nginx/sites-available/nutricore <<'EOF'
server {
    server_name nutricore.your-company.com;
    client_max_body_size 50M;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
    location /metrics {
        # 仅内网放行
        allow 10.0.0.0/8;
        deny all;
        proxy_pass http://127.0.0.1:8000/metrics;
    }
}
EOF
sudo ln -sf /etc/nginx/sites-available/nutricore /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d nutricore.your-company.com   # 内网无外网时跳过这步

# ============== 9. 设置开机自启 ==============
# docker compose 已带 restart: unless-stopped；docker.service 默认 enabled
sudo systemctl enable docker
```

### 3.4 在推理服务器单独跑 vLLM（2× RTX 4090 + Qwen2.5-32B-AWQ + TP=2）

```bash
# 仅在 GPU 机器执行（需要 2× RTX 4090 24G + nvidia-container-toolkit）
docker run -d --name vllm --gpus all --restart unless-stopped \
  --ipc=host \
  -p 8001:8000 \
  -v /opt/models:/root/.cache/huggingface \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen2.5-32B-Instruct-AWQ \
  --tensor-parallel-size 2 \
  --gpu-memory-utilization 0.9 \
  --max-model-len 8192 \
  --served-model-name Qwen2.5-32B-Instruct-AWQ

# 验证
curl http://localhost:8001/v1/models
curl http://localhost:8001/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"Qwen2.5-32B-Instruct-AWQ","messages":[{"role":"user","content":"hello"}]}'

# 业务机的 .env：LLM_BASE_URL=http://<推理机内网IP>:8001/v1
```

**关键参数解释**：
- `--tensor-parallel-size 2`：vLLM 自动把权重切到 2 张卡，前向 all-reduce
- `--ipc=host`：vLLM 多进程间共享内存必需
- `--max-model-len 8192`：上下文窗口；KV cache 显存占用 ~ batch × max_len × hidden × layers，调小可省显存
- `--gpu-memory-utilization 0.9`：用 90% 显存，留 ~2GB 给系统

**显存占用实测**（2× RTX 4090 24G）：
- 模型权重分片：单卡 ~10 GB
- KV cache（max_len 8192, batch 8）：单卡 ~10 GB
- 余量：~3 GB
- 单卡总占用：~22.5 GB（90% × 24GB = 21.6 GB 跑得动）

如果显存吃紧可以把 `--max-model-len` 降到 4096，或用 `--max-num-seqs 4` 限制并发。

### 3.5 生产化检查清单

- [ ] `.env` 所有密码 / SECRET 都已改为随机长串
- [ ] `JWT_SECRET_KEY` ≥ 32 位
- [ ] `APP_ENV=prod` + `LOG_JSON=true`（便于采集到 ELK / Loki）
- [ ] `CORS_ORIGINS` 设置为前端真实域名，不再是 `["*"]`
- [ ] MinIO 凭证不再是默认 `minioadmin`
- [ ] MySQL `root` 密码已改
- [ ] 防火墙：仅放行 80/443（业务端），其他端口（3306/6379/9000/19530）**仅内网可达**
- [ ] 备份：MySQL 每日 dump → MinIO 异地桶；MinIO 启用版本化
- [ ] 监控：Prometheus 抓 `:8000/metrics`，Grafana 看 LLM QPS / RAG 延迟 / Agent 失败率
- [ ] 日志：`docker compose logs -f api` → fluent-bit → Loki / ELK
- [ ] 限流：建议在 nginx 加 `limit_req_zone` 或上 API 网关（Kong / APISIX）
- [ ] 数据库迁移：上线前在测试环境 `python -m scripts.seed` 确认无 schema 冲突

### 3.6 信创 / 国产化环境特别说明

- **OpenEuler / Kylin V10**：Docker 改用厂商提供的兼容包（`docker-ce` 在某些版本上有依赖冲突）；如果用 podman，把 `docker compose` 替换为 `podman compose` 即可
- **昇腾 / 华为 ATLAS / 寒武纪等国产 NPU**：把 vLLM 替换为对应厂商的推理框架（MindIE / Triton），保持 OpenAI 兼容协议，业务端无感知
- **离线安装**：在能联网的同版本机器 `docker save` 所有镜像 → scp 到目标机 `docker load`；同时把 BGE / Reranker / LLM 模型权重打包随系统盘一起交付

---

## 4. 升级与运维

```bash
# 拉新代码
cd /opt/nutricore && git pull
docker compose pull
docker compose up -d --build

# 看健康
curl -s http://localhost:8000/ready | jq

# 备份 MySQL
docker compose exec mysql mysqldump -uroot -p$MYSQL_ROOT_PASSWORD nutricore | gzip > backup-$(date +%F).sql.gz

# 备份 MinIO（用 mc 工具镜像同步）
docker run --rm --network host minio/mc \
  alias set local http://localhost:9000 minioadmin minioadmin
docker run --rm --network host -v $(pwd)/minio-backup:/backup minio/mc \
  mirror local/nutricore /backup

# 滚动重启 api（不停依赖）
docker compose restart api
```

---

## 5. 故障速查

| 症状                            | 排查命令                                                       |
| ------------------------------- | -------------------------------------------------------------- |
| API 503 / 启动后立刻退出        | `docker compose logs --tail=200 api`                           |
| Milvus 无法建集合               | `docker compose logs milvus` 看 etcd 是否就绪；`/ready` 接口   |
| LLM 调用全部超时                | `curl $LLM_BASE_URL/models` 在容器里测；查防火墙               |
| 知识库检索空                    | 没跑 `scripts.seed`；或 BM25 缓存目录权限不对                  |
| 磁盘满                          | `du -sh /var/lib/docker/volumes/*` 找最大；清 `model_cache`    |
| 内存爆 OOM                      | `dmesg \| grep -i kill` 看是谁；通常是 BGE / Milvus 没分够     |

---

> 如需进一步压测、灾备双活、k8s 化部署，请参考 `docs/ARCHITECTURE.md` 并联系维护者。
