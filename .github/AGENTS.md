# GitHub Actions 维护规则

- 本目录只保存 lumendesk 的 CI/CD 工作流和 GitHub 仓库自动化配置。
- 工作流不得写入真实 API Key、用户数据或生产业务凭据；演示 Pages 构建必须使用模拟数据模式。
- 修改工作流后至少执行 YAML 结构检查、前端测试和生产构建；部署目标为 GitHub Pages 时保持静态前端边界，不尝试运行 FastAPI。
- 工作流名称、路径和环境变量应使用 lumendesk 命名；保留旧配置仅用于兼容，不新增旧品牌标识。
