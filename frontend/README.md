# LumenDesk Frontend

独立 Vue 前端项目，连接 LumenDesk Python 后端并提供可展示的对话、知识库和评测界面。

项目目录：

```text
./EchoMindFrontend
```

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

先配置 `../echomind/.env`，再启动完整服务：

```bash
docker compose up -d --build
```

前提是 `EchoMindFrontend` 的父目录下有这三个目录：

```text
../echomind
./
```

访问前端：

```text
http://localhost
```

如果只想暴露前端端口，可改 `FRONTEND_PORT`，默认仍可通过 `80` 统一入口访问。

停止：

```bash
docker compose down
```

## 后端启动参考

Python 版默认：

```text
http://localhost:8000
```

后端 Compose 服务通过 `env_file` 自动读取 Python 项目的 `.env`，普通启动不再需要额外 `--env-file`。
共享 Redis 的密码和前端端口仍由前端目录的 `.env`、shell 或显式 `--env-file` 提供；
Compose 中的 Redis 连接配置会覆盖后端文件内的 Redis 设置，保证应用连接同一个服务。
Python 文件中的 `EVAL_JUDGE_MODEL`、`EVAL_JUDGE_MAX_TOKENS` 等配置也会完整传入容器。
健康检查失败不会覆盖已有页面状态，旧请求也不能覆盖新页面的状态或回复。
