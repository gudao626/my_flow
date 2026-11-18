"""读取 PR 文件差异，为 Agent 的代码审查提供证据。"""

import httpx

from .github_tools import _build_github_headers, _parse_pr_url

MAX_FILES = 20
MAX_PATCH_CHARS = 4000

PR_FILES_TOOL = {
    "type": "function",
    "function": {
        "name": "get_github_pr_files",
        "description": "Read changed file names and bounded diff patches for a GitHub PR. Report coverage limitations.",
        "parameters": {
            "type": "object",
            "properties": {"pr_url": {"type": "string"}},
            "required": ["pr_url"],
            "additionalProperties": False,
        },
    },
}


def _summarize_files(rows: list, has_next_page: bool) -> dict:
    """限制提供给模型的内容，并显式说明哪些证据没有读取。"""
    items = []
    for row in rows[:MAX_FILES]:
        if not isinstance(row, dict) or not isinstance(row.get("filename"), str):
            raise ValueError("Invalid file record.")
        patch = row.get("patch")
        available = isinstance(patch, str)
        items.append({
            "filename": row["filename"],
            "previous_filename": row.get("previous_filename"),
            "status": row.get("status"),
            "additions": row.get("additions"),
            "deletions": row.get("deletions"),
            # GitHub 未提供 patch 时不能把它当作“没有改动”。
            "patch": patch[:MAX_PATCH_CHARS] if available else None,
            "patch_status": (
                "unavailable" if not available else
                "truncated" if len(patch) > MAX_PATCH_CHARS else "provided"
            ),
        })
    return {
        # 文件列表完整程度与单个文件 patch 完整程度分别表达。
        "status": "incomplete" if has_next_page or len(rows) > MAX_FILES else "available" if items else "empty",
        "returned_files": len(items),
        "items": items,
    }


async def get_github_pr_files(pr_url: str) -> dict:
    try:
        owner, repo, number = _parse_pr_url(pr_url)
    except ValueError:
        return {"error": "Invalid GitHub PR URL."}

    path = f"/repos/{owner}/{repo}/pulls/{number}"
    try:
        async with httpx.AsyncClient(
            base_url="https://api.github.com", timeout=10, headers=_build_github_headers()
        ) as client:
            # 首版只读取一页，防止大型 PR 无限制消耗模型上下文。
            response = await client.get(f"{path}/files", params={"per_page": MAX_FILES})
            response.raise_for_status()
            rows = response.json()
            if not isinstance(rows, list):
                raise ValueError("Invalid files response.")
            return {
                "source_url": f"https://github.com/{owner}/{repo}/pull/{number}/files",
                # 这个接口读取查询时的 PR 差异，尚不提供固定 SHA 的一致性保证。
                "snapshot": "live_pr_diff_not_pinned_to_sha",
                **_summarize_files(rows, "next" in response.links),
            }
    except httpx.HTTPStatusError as exc:
        return {"error": "GitHub PR files lookup failed.", "http_status": exc.response.status_code}
    except (httpx.RequestError, ValueError, KeyError, TypeError):
        return {"error": "Could not read GitHub PR files."}
