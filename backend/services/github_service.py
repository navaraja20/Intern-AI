"""
GitHub Service – fetches repos, READMEs, and profile info via GitHub REST API v3.
Provides a structured summary for LLM injection and ChromaDB indexing.
"""

import httpx
import base64
from typing import Optional
from config import settings


async def fetch_github_profile(github_url_or_username: str) -> dict:
    """
    Main entry: fetch full GitHub profile + top repos.
    Returns structured dict ready for DB storage + LLM injection.
    """
    username = _extract_username(github_url_or_username)
    headers  = _build_headers()

    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        # User profile
        user_resp = await client.get(f"{settings.GITHUB_API_BASE}/users/{username}")
        if user_resp.status_code == 404:
            raise ValueError(f"GitHub user '{username}' not found.")
        user_resp.raise_for_status()
        user_data = user_resp.json()

        # All repos (up to 100)
        repos_resp = await client.get(
            f"{settings.GITHUB_API_BASE}/users/{username}/repos",
            params={"per_page": 100, "sort": "pushed", "type": "owner"},
        )
        repos_resp.raise_for_status()
        raw_repos = repos_resp.json()

    # Filter forks, sort by (stars + recency), take top N
    own_repos = [r for r in raw_repos if not r.get("fork", False)]
    own_repos.sort(
        key=lambda r: (r.get("stargazers_count", 0) * 2 + (1 if r.get("pushed_at") else 0)),
        reverse=True,
    )
    top_repos = own_repos[:settings.GITHUB_MAX_REPOS]

    # Fetch README for top 5 repos
    repos = []
    for repo in top_repos:
        repo_data = _parse_repo(repo)
        # Fetch README for top repos (skip if rate-limited)
        if len(repos) < 5:
            repo_data["readme_text"] = await _fetch_readme(username, repo["name"], headers)
        repos.append(repo_data)

    summary = _build_llm_summary(username, user_data, repos)

    return {
        "username":     username,
        "name":         user_data.get("name") or username,
        "bio":          user_data.get("bio") or "",
        "public_repos": user_data.get("public_repos", 0),
        "profile_url":  f"https://github.com/{username}",
        "repos":        repos,
        "summary":      summary,
    }


async def _fetch_readme(username: str, repo_name: str, headers: dict) -> Optional[str]:
    """Fetch and decode README.md for a repo (max 1500 chars)."""
    try:
        async with httpx.AsyncClient(timeout=10, headers=headers) as client:
            r = await client.get(
                f"{settings.GITHUB_API_BASE}/repos/{username}/{repo_name}/readme"
            )
            if r.status_code == 200:
                content_b64 = r.json().get("content", "")
                # GitHub returns base64 with newlines
                decoded = base64.b64decode(
                    content_b64.replace("\n", "")
                ).decode("utf-8", errors="ignore")
                # Strip markdown syntax for cleaner embedding
                import re
                clean = re.sub(r"[#*`\[\]()!]+", " ", decoded)
                clean = re.sub(r"\s+", " ", clean).strip()
                return clean[:1500]
    except Exception:
        pass
    return None


def _parse_repo(repo: dict) -> dict:
    return {
        "repo_name":    repo["name"],
        "description":  repo.get("description") or "",
        "language":     repo.get("language") or "",
        "stars":        repo.get("stargazers_count", 0),
        "topics":       repo.get("topics", []),
        "html_url":     repo.get("html_url", ""),
        "pushed_at":    repo.get("pushed_at", ""),
        "readme_text":  None,
        # languages_json filled via separate endpoint if needed
        "languages_json": {repo.get("language", "Unknown"): 100} if repo.get("language") else {},
    }


def _build_llm_summary(username: str, user_data: dict, repos: list[dict]) -> str:
    """Build compact text for LLM prompt injection."""
    lines = [f"GitHub Profile: github.com/{username}"]

    if user_data.get("bio"):
        lines.append(f"Bio: {user_data['bio']}")

    # Language stats
    lang_count: dict[str, int] = {}
    for r in repos:
        lang = r.get("language", "")
        if lang:
            lang_count[lang] = lang_count.get(lang, 0) + 1

    if lang_count:
        sorted_langs = sorted(lang_count.items(), key=lambda x: x[1], reverse=True)
        lines.append(f"Languages: {', '.join(f'{l}({c})' for l,c in sorted_langs[:6])}")

    lines.append(f"\nTop {min(len(repos), 10)} Repositories:")
    for repo in repos[:10]:
        parts = [f"  • {repo['repo_name']}"]
        if repo.get("language"):
            parts.append(f"[{repo['language']}]")
        if repo.get("stars", 0) > 0:
            parts.append(f"⭐{repo['stars']}")
        if repo.get("description"):
            parts.append(f"– {repo['description']}")
        if repo.get("topics"):
            parts.append(f"| {', '.join(repo['topics'][:4])}")
        lines.append(" ".join(parts))

    return "\n".join(lines)


def _build_headers() -> dict:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"token {settings.GITHUB_TOKEN}"
    return headers


def _extract_username(url_or_username: str) -> str:
    url = url_or_username.strip().rstrip("/")
    if "github.com/" in url:
        return url.split("github.com/")[-1].split("/")[0]
    return url
