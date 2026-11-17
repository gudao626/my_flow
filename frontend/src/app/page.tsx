import { ArrowRight, CircleAlert, GitPullRequest, ListChecks, NotebookText, Rocket, Workflow } from "lucide-react";
import Link from "next/link";

import { rdTasks } from "@/core/rd-tasks";

const taskIcons = {
  repository: Workflow,
  pr: GitPullRequest,
  issue: CircleAlert,
  ci: ListChecks,
  brief: NotebookText,
  release: Rocket,
};

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#0d131d] text-slate-100">
      <header className="border-b border-white/10">
        <nav className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-5">
          <Link href="/" className="flex items-center gap-3 font-semibold">
            <Workflow className="size-6 text-teal-300" aria-hidden />
            研发协作
          </Link>
          <Link href="/workspace/chats" className="text-sm text-slate-300 hover:text-white">
            会话历史
          </Link>
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-12 sm:py-20">
        <div className="rounded-3xl border border-teal-200/20 bg-linear-to-br from-[#172d34] to-[#141d2b] p-7 sm:p-12">
          <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">研发协作工作台</h1>
          <p className="mt-4 max-w-xl text-base leading-relaxed text-slate-300">
            从 GitHub 仓库、Issue、PR 和 CI 获取证据，整理检查结论与后续行动。
          </p>
          <Link href="/workspace" className="mt-7 inline-flex items-center gap-2 rounded-lg bg-teal-200 px-4 py-2.5 font-medium text-slate-950 hover:bg-teal-100">
            新建分析 <ArrowRight className="size-4" aria-hidden />
          </Link>
        </div>
        <section className="mt-10" aria-labelledby="task-heading">
          <h2 id="task-heading" className="text-xl font-semibold">选择任务</h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {rdTasks.map((task) => {
              const Icon = taskIcons[task.id];
              return (
                <Link
                  key={task.id}
                  href={`/workspace/chats/new?task=${task.id}`}
                  className="group rounded-xl border border-white/10 bg-[#141d2b] p-5 transition hover:border-teal-200/60 hover:bg-[#192735] focus-visible:outline-2 focus-visible:outline-teal-200"
                >
                  <div className="flex items-center justify-between text-teal-300">
                    <Icon className="size-5" aria-hidden />
                    <ArrowRight className="size-4 text-slate-400 group-hover:text-teal-300" aria-hidden />
                  </div>
                  <h3 className="mt-4 font-semibold">{task.title}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-slate-300">{task.description}</p>
                </Link>
              );
            })}
          </div>
        </section>
      </main>
    </div>
  );
}
