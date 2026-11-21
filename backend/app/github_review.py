"""汇总审查证据，并检测查询期间 PR 的版本变化。"""

import httpx

from .github_files import MAX_FILES, _summarize_files
from .github_tools import _SHA, _assess_ci, _build_github_headers, _get_commit_checks, _parse_pr_url


PR_REVIEW_TOOL = {
    "type": "function",
    "function": {
        "name": "get_github_pr_review_context",
        "description": (
            "Read PR metadata, CI and bounded file patches together, checking head/base SHAs before and after. "
            "Use for combined code and CI review. A changed PR returns no review evidence; stable observations "
            "are not an atomic snapshot or merge approval."
        ),
        "parameters": {
            "type": "object",
            "properties": {"pr_url": {"type": "string"}},
            "required": ["pr_url"],
            "additionalProperties": False,
        },
    },
}


def _read_version(data: dict) -> tuple[str, str]:
    # 来源分支和目标分支都可能更新，因此同时检查 head 和 base。
    head, base = data["head"]["sha"], data["base"]["sha"]
    if not all(isinstance(value, str) and _SHA.fullmatch(value) for value in (head, base)):
        raise ValueError("Invalid PR commit SHA.")
    return head, base


async def _collect_review_context(client: httpx.AsyncClient, repo_path: str, number: str) -> dict:
    """传入客户端，便于用假 GitHub 响应验证完整查询流程。"""
    pr_path = f"{repo_path}/pulls/{number}"
    before_response = await client.get(pr_path)
    before_response.raise_for_status()
    before = before_response.json()
    head_sha, base_sha = _read_version(before)

    files_response = await client.get(f"{pr_path}/files", params={"per_page": MAX_FILES})
    files_response.raise_for_status()
    rows = files_response.json()
    if not isinstance(rows, list):
        raise ValueError("Invalid PR files response.")
    files = _summarize_files(rows, "next" in files_response.links)
    # CI 始终使用第一次读到的具体提交，不用会移动的分支名称。
    checks = await _get_commit_checks(client, repo_path, head_sha)

    after_response = await client.get(pr_path)
    after_response.raise_for_status()
    after_version = _read_version(after_response.json())
    if (head_sha, base_sha) != after_version:
        # 一旦观察到变化，不返回 patch 或 CI，避免模型继续使用混合证据。
        # 不自动重试，避免频繁推送时无限查询并消耗 API 配额。
        return {
            "status": "stale",
            "reason": "PR head or base changed during lookup. Query again before reviewing.",
            "before": {"head_sha": head_sha, "base_sha": base_sha},
            "after": {"head_sha": after_version[0], "base_sha": after_version[1]},
        }

    return {
        "status": "ready",
        "version_check": "unchanged_at_observation_boundaries",
        # 两次观察相同不等于事务快照：仍可能有缓存或期间变化后恢复。
        "snapshot_guarantee": "best_effort_not_atomic",
        "head_sha": head_sha,
        "base_sha": base_sha,
        "title": before["title"],
        "state": before["state"],
        "merged": before["merged"],
        "files": files,
        "check_runs": checks,
        "ci_assessment": _assess_ci(checks),
    }


async def get_github_pr_review_context(pr_url: str) -> dict:
    try:
        owner, repo, number = _parse_pr_url(pr_url)
    except ValueError:
        return {"status": "unavailable", "error": "Invalid GitHub PR URL."}
    source_url = f"https://github.com/{owner}/{repo}/pull/{number}"
    try:
        async with httpx.AsyncClient(
            base_url="https://api.github.com", timeout=10, headers=_build_github_headers()
        ) as client:
            result = await _collect_review_context(client, f"/repos/{owner}/{repo}", number)
            return {"source_url": source_url, **result}
    except httpx.HTTPStatusError as exc:
        return {
            "status": "unavailable", "source_url": source_url,
            "error": "GitHub review context lookup failed.", "http_status": exc.response.status_code,
        }
    except (httpx.RequestError, ValueError, KeyError, TypeError):
        return {"status": "unavailable", "source_url": source_url, "error": "Could not read review context."}
