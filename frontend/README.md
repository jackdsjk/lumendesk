# LumenDesk Frontend

独立 Vue 前端项目，连接 LumenDesk Python 后端并提供可展示的对话、知识库和评测界面。

项目目录：`frontend/`

## 功能

- 连接 Python 后端并展示 `/chat`、监控、知识库和评测结果。
- 统一适配 Python API 的 `conv_id`、`agent_type`、`latency_ms` 等响应字段。
- 支持聊天调试、健康检查、监控摘要、知识库检索、知识库文档导入、文件上传。
- 支持 Docker + Nginx 部署。

## 默认后端地址

| 后端 | 默认地址 |
|------|----------|
| Python | `http://localhost:8000` |

开发模式下，Vite 会代理：

| 前端路径 | 代理到 |
|----------|--------|
| `/api/python` | `http://localhost:8000` |

Docker 模式下，Nginx 会通过运行时注入的地址访问 Python 服务。

## 本地运行

安装依赖：

```bash
npm install
```

启动：

```bash
npm run dev
```

访问：

```text
http://localhost:5173
```

如果后端端口不是默认值，可以启动时覆盖：

```bash
VITE_PYTHON_API_URL=http://localhost:8000 \
npm run dev
```

## Docker 部署

完整服务请从 LumenDesk 项目根目录启动：

```bash
cd ..
docker compose up -d --build
```

访问前端：`http://localhost`。

如果后端已经通过根目录 Compose 启动，也可以单独启动前端：

```bash
docker compose up -d --build
```

单独启动时默认访问 `http://localhost:5174`，通过 `PYTHON_API_URL` 指向宿主机上的后端（默认 `http://localhost:8000`）。

停止：

```bash
docker compose down
```

## 后端启动参考

后端、Redis、ChromaDB 和 Nginx 的配置统一维护在项目根目录；前端不再引用旧的 `../echomind` 路径。
