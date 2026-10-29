# LumenDesk Python 项目协作规则

## 范围与用途

- 本仓库只维护 lumendesk 的 Python 实现；可展示前端位于本仓库的 `frontend/`。
- HTTP 入口位于 `api/`，核心编排位于 `agents/` 与 `core/`，工具接入位于 `tooling/`，记忆与评测分别位于 `memory/`、`evaluation/`。
- 修改符号、调用链或跨模块流程前，优先使用仓库内 `.codegraph/` 索引定位影响范围。

## 编辑边界

- 保持 API、编排、工具、记忆和评测模块的依赖方向清晰，不把外部服务调用直接写入核心业务逻辑。
- 环境差异和密钥只通过环境变量及 `.env.example` 说明；禁止提交 `.env`、真实令牌、运行数据或日志。
- `wiki/` 面向使用者和维护者；接口、配置、运行方式或架构发生长期变化时同步更新相应文档。

## 运行与验证

- 开发环境使用 Python 3.12：`python -m pip install -r requirements.txt`。
- 测试依赖：`python -m pip install -r requirements-dev.txt`。
- 默认回归命令：`python -m pytest -q`。
- 本地 API：`python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload`。
- Docker 验证以 `docker compose up -d --build` 和 `/health` 健康检查为准。

## 提交与维护

- 提交前检查 `git status` 和必要的 `git diff`，不得混入同级项目或本地生成物。
- 新增配置时提供安全默认值、校验和 `.env.example` 说明；新增行为时补对应测试。
- `.codegraph/` 只提交其 `.gitignore`，数据库、WAL、socket 和日志均保持本地化。
