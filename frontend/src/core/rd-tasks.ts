export const rdTasks = [
  { id: "repository", title: "仓库概览", description: "查看近期 PR、Issue 和工作流运行。", prompt: "请调用 inspect_github_repository，整理 [GitHub 仓库链接] 的近期研发活动，附上来源链接。" },
  { id: "pr", title: "PR 检查", description: "核对当前提交与 CI 检查结果。", prompt: "请调用 inspect_github_pr，检查 [GitHub PR 链接] 的当前提交及其 CI 状态，列出阻塞项、待确认项和证据链接。" },
  { id: "issue", title: "Issue 分诊", description: "梳理问题、补充信息和下一步。", prompt: "请调用 inspect_github_issue，对 [GitHub Issue 链接] 做分诊，给出问题类型、优先级建议、缺失信息和证据链接。" },
  { id: "ci", title: "CI 排障", description: "定位失败的任务和步骤。", prompt: "请调用 inspect_github_ci，分析 [GitHub Actions 运行链接] 中失败的任务和步骤，附证据。缺少日志时，请明确哪些原因需要核实。" },
  { id: "brief", title: "研发简报", description: "整理近期变更和未完成事项。", prompt: "请调用 inspect_github_repository，为 [GitHub 仓库链接] 整理近期研发简报，列出重要变更、待跟进事项、失败运行和来源链接，说明采样范围。" },
  { id: "release", title: "发布前检查", description: "并行收集 PR、Issue 和 CI 的发布证据。", prompt: "请调用 review_github_release 检查 [GitHub PR 链接]。如果我提供了关联 Issue 和 Actions 运行链接，一并检查。列出阻塞项、证据冲突和待确认项，并生成 Markdown 报告。" },
] as const;
