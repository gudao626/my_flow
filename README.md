<<<<<<< HEAD
# My Git Flow

研发协作工作台。前端复用 DeerFlow 及其研发协作页面，后端与 Agent 在此项目中独立实现。当前目录包含前端源码、依赖锁文件和许可证。

## 预览前端

在 PowerShell 中运行以下命令。根页面提供任务卡片，提交任务需要接入后端。

```powershell
Set-Location D:\Codex_code\my_git_flow\frontend
npx --yes pnpm@10.26.2 install --frozen-lockfile
npx --yes pnpm@10.26.2 run dev
```

打开 http://localhost:3000。联调时可参考 `docker/nginx/nginx.local.conf`，它将前端、Gateway 和 LangGraph 分别转发到 3000、8001 和 2024，并对外提供 2026 端口。

## 从零开发后端

1. 新建自己的 `backend/`。先实现 FastAPI 的健康检查和模型列表，随后接入现有前端的模型选择。
2. 实现一个最小 LangGraph 对话图，接通新会话、消息提交和流式响应。先发一条简单消息确认链路。
3. 加一个 GitHub PR 只读查询工具，返回 PR 标题、当前提交和来源链接。写离线测试，再让模型调用它。
4. 增加按提交查询 CI、并行取证和报告生成。用固定用例验证旧提交的检查结果不会被用来判断新提交。

前端接口的参考入口在 `frontend/src/core/config/index.ts`、`frontend/src/core/threads/hooks.ts` 和 `frontend/src/core/models/hooks.ts`。现有聊天界面使用 LangGraph SDK。如果你选择自定义聊天协议，需要同时修改前端的会话与流式请求代码。首页任务模板位于 `frontend/src/core/rd-tasks.ts`，其中的工具名是后续联调约定。

前端来源为 [DeerFlow](https://github.com/bytedance/deer-flow) 和 [DeerFlow 2.0 Enhanced](https://github.com/stophobia/deerflow2.0-enhanced)。许可见 [LICENSE](LICENSE)。
=======
# my_flow
学习测试myflow
>>>>>>> 56dae8ebc4918a4be32ccf591c31584a8d749473
