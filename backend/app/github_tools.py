import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import load_dotenv

# 固定从 backend/.env 加载；系统环境变量优先于文件中的配置。
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


def _build_github_headers() -> dict[str, str]:
    """构建工具请求头；凭证只用于后端请求，不进入模型上下文。"""
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN", "").strip()
    # 留空时允许匿名访问；避免发送无效的空 Bearer 请求头。
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

PR_TOOL = {
    "type": "function",
    "function": {
        "name": "get_github_pr",
        "description": "Read public GitHub PR metadata and CI check runs for its current head commit.",
        "parameters": {
            "type": "object",
            "properties": {"pr_url": {"type": "string", "description": "Full GitHub pull request URL"}},
            "required": ["pr_url"],
            "additionalProperties": False,
        },
    },
}

_PR_PATH = re.compile(r"/([a-zA-Z0-9-]+)/([a-zA-Z0-9_.-]+)/pull/([1-9][0-9]{0,18})/?")
_SHA = re.compile(r"[0-9a-fA-F]{40}")
_FAILED_CONCLUSIONS = {"failure", "timed_out", "startup_failure"}
_PENDING_STATUSES = {"queued", "in_progress", "requested", "waiting", "pending"}


def _parse_pr_url(pr_url: str) -> tuple[str, str, str]:
    """所有 PR 工具共用地址校验，避免不同工具的访问规则不一致。"""
    url = urlsplit(pr_url.strip())
    match = _PR_PATH.fullmatch(url.path)
    if url.scheme != "https" or url.netloc.lower() != "github.com" or not match or match[2] in {".", ".."}:
        raise ValueError("Expected https://github.com/owner/repo/pull/123.")
    return match.groups()


def _assess_ci(check_runs: dict) -> str:
    # 先判断已有证据能证明什么。即使列表不完整，一个已完成的失败项也足以确认有失败。
    items = check_runs.get("items", [])
    if any(item["status"] == "completed" and item["conclusion"] in _FAILED_CONCLUSIONS for item in items):
        return "failed"
    if any(item["status"] in _PENDING_STATUSES for item in items):
        return "pending"

    # 只有读到了完整结果，且每项明确成功，才报告本次查询覆盖的检查都成功。
    # 空列表、取消、跳过和未知结论都不足以判定成功。
    if check_runs["status"] == "available" and items and all(
        item["status"] == "completed" and item["conclusion"] == "success" for item in items
    ):
        return "observed_success"
    return "insufficient_evidence"


async def _get_commit_checks(client: httpx.AsyncClient, repo_path: str, sha: str) -> dict:
    # 用具体提交的 SHA 查询，避免使用分支上其他提交的检查。
    try:
        response = await client.get(f"{repo_path}/commits/{sha}/check-runs", params={"per_page": 30})
        response.raise_for_status()
        data = response.json()
        runs = data["check_runs"]
        total = data["total_count"]
        if not isinstance(runs, list) or type(total) is not int or total < len(runs):
            raise ValueError("Invalid check runs response.")
        # 再核对每条记录的 SHA，并保留检查状态和来源链接。
        checks = [
            {key: run.get(key) for key in ("name", "status", "conclusion", "html_url", "details_url")}
            for run in runs
            if isinstance(run, dict) and run.get("head_sha") == sha
        ]
        # 首版读取一页。被截断或过滤的结果不能用来断言检查全部通过。
        incomplete = total > len(runs) or len(checks) != len(runs) or "next" in response.links
        return {"status": "incomplete" if incomplete else "available" if checks else "empty", "items": checks}
    except httpx.HTTPStatusError as exc:
        return {"status": "unavailable", "http_status": exc.response.status_code}
    except (httpx.RequestError, ValueError, KeyError, TypeError):
        # CI 读取失败时保留已经拿到的 PR 信息。
        return {"status": "unavailable"}


async def get_github_pr(pr_url: str) -> dict:
    # 只提取仓库和 PR 编号。HTTP 请求始终发往代码指定的 GitHub API。
    try:
        owner, repo, number = _parse_pr_url(pr_url)
    except ValueError:
        return {"error": "Invalid GitHub PR URL."}
    repo_path = f"/repos/{owner}/{repo}"
    try:
        async with httpx.AsyncClient(
            base_url="https://api.github.com",
            timeout=10,
            # PR 与 CI 查询共用这个客户端，因此两次请求都会使用认证头。
            headers=_build_github_headers(),
        ) as client:
            response = await client.get(f"{repo_path}/pulls/{number}")
            response.raise_for_status()
            data = response.json()
            # SHA 来自 GitHub 响应，由后端校验后用于下一次查询。
            sha = data["head"]["sha"]
            if not isinstance(sha, str) or not _SHA.fullmatch(sha):
                return {"error": "GitHub returned an invalid PR head SHA."}
            check_runs = await _get_commit_checks(client, repo_path, sha)
            return {
                "title": data["title"],
                "state": data["state"],
                "merged": data["merged"],
                "head_sha": sha,
                "source_url": f"https://github.com/{owner}/{repo}/pull/{number}",
                "check_runs": check_runs,
                "ci_assessment": _assess_ci(check_runs),
            }
    except httpx.HTTPStatusError as exc:
        return {"error": "GitHub PR lookup failed.", "http_status": exc.response.status_code}
    except (httpx.RequestError, ValueError, KeyError, TypeError):
        return {"error": "Could not read GitHub PR metadata."}
