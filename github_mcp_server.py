import os
import json
from datetime import datetime, timedelta

import requests
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
from pydantic import Field

mcp = FastMCP("GitHubCareerBot", log_level="ERROR")

GITHUB_API = "https://api.github.com"
TOKEN = os.getenv("GITHUB_TOKEN", "")
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"

# In-memory cache — powers the @username / @owner/repo autocomplete
recent_profiles: dict[str, str] = {}  # username -> display name
recent_repos: dict[str, str] = {}     # "owner/repo" -> description


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _get(url: str, params: dict = None) -> dict:
    resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _cache_repos(items: list[dict]):
    for item in items:
        recent_repos[item["full_name"]] = item.get("description", "") or ""


# ──────────────────────────────────────────────
# Tools
# ──────────────────────────────────────────────

@mcp.tool(
    name="search_repositories",
    description=(
        "Search GitHub repositories by keywords, language, and minimum stars. "
        "Returns repo names, descriptions, stars, topics, and URLs."
    ),
)
def search_repositories(
    query: str = Field(description="Search keywords, e.g. 'fastapi REST API', 'react dashboard'"),
    language: str = Field(default="", description="Filter by language, e.g. 'python', 'typescript'"),
    min_stars: int = Field(default=50, description="Minimum stars filter"),
    limit: int = Field(default=8, description="Number of results (max 20)"),
) -> str:
    q = query
    if language:
        q += f" language:{language}"
    if min_stars:
        q += f" stars:>={min_stars}"

    data = _get(
        f"{GITHUB_API}/search/repositories",
        params={"q": q, "sort": "stars", "order": "desc", "per_page": min(limit, 20)},
    )

    results = []
    for item in data.get("items", []):
        results.append({
            "full_name": item["full_name"],
            "description": item.get("description") or "No description",
            "stars": item["stargazers_count"],
            "language": item.get("language") or "Unknown",
            "topics": item.get("topics", []),
            "url": item["html_url"],
        })
    _cache_repos(data.get("items", []))
    return json.dumps(results, indent=2)


@mcp.tool(
    name="get_user_profile",
    description=(
        "Get a GitHub user's full profile: bio, follower count, top languages, "
        "and their most popular repositories."
    ),
)
def get_user_profile(
    username: str = Field(description="GitHub username, e.g. 'torvalds', 'gvanrossum'"),
) -> str:
    user = _get(f"{GITHUB_API}/users/{username}")
    repos = _get(
        f"{GITHUB_API}/users/{username}/repos",
        params={"sort": "stars", "per_page": 10},
    )

    # Weighted language breakdown (by stars)
    lang_stars: dict[str, int] = {}
    for repo in repos:
        lang = repo.get("language")
        if lang:
            lang_stars[lang] = lang_stars.get(lang, 0) + repo.get("stargazers_count", 1)

    top_langs = [lang for lang, _ in sorted(lang_stars.items(), key=lambda x: x[1], reverse=True)[:6]]
    top_repos = [
        {
            "name": r["name"],
            "description": r.get("description") or "",
            "stars": r["stargazers_count"],
            "language": r.get("language") or "",
            "topics": r.get("topics", []),
        }
        for r in sorted(repos, key=lambda r: r["stargazers_count"], reverse=True)[:5]
    ]

    profile = {
        "username": username,
        "name": user.get("name") or username,
        "bio": user.get("bio") or "",
        "location": user.get("location") or "",
        "company": user.get("company") or "",
        "followers": user.get("followers", 0),
        "public_repos": user.get("public_repos", 0),
        "top_languages": top_langs,
        "top_repos": top_repos,
        "github_url": user.get("html_url", ""),
        "blog": user.get("blog") or "",
    }

    recent_profiles[username] = user.get("name") or username
    _cache_repos(repos)
    return json.dumps(profile, indent=2)


@mcp.tool(
    name="get_repo_details",
    description=(
        "Get detailed information about a specific GitHub repository: description, "
        "stars, forks, language breakdown, topics, license, and top contributors."
    ),
)
def get_repo_details(
    owner: str = Field(description="Repository owner username"),
    repo: str = Field(description="Repository name"),
) -> str:
    data = _get(f"{GITHUB_API}/repos/{owner}/{repo}")

    try:
        languages = _get(f"{GITHUB_API}/repos/{owner}/{repo}/languages")
    except Exception:
        languages = {}

    try:
        contribs = _get(
            f"{GITHUB_API}/repos/{owner}/{repo}/contributors",
            params={"per_page": 5},
        )
        top_contributors = [c["login"] for c in contribs[:5]]
    except Exception:
        top_contributors = []

    result = {
        "full_name": data["full_name"],
        "description": data.get("description") or "",
        "stars": data["stargazers_count"],
        "forks": data["forks_count"],
        "open_issues": data["open_issues_count"],
        "primary_language": data.get("language") or "",
        "languages_breakdown": languages,
        "topics": data.get("topics", []),
        "license": data.get("license", {}).get("name") if data.get("license") else "None",
        "created_at": data["created_at"][:10],
        "last_updated": data["updated_at"][:10],
        "top_contributors": top_contributors,
        "homepage": data.get("homepage") or "",
        "url": data["html_url"],
    }

    recent_repos[f"{owner}/{repo}"] = data.get("description") or ""
    return json.dumps(result, indent=2)


@mcp.tool(
    name="get_trending_repos",
    description=(
        "Get trending GitHub repositories — most starred repos created recently "
        "for a given language or topic."
    ),
)
def get_trending_repos(
    language: str = Field(default="", description="Programming language, e.g. 'python', 'rust', 'go'"),
    since: str = Field(default="weekly", description="Time range: 'daily', 'weekly', or 'monthly'"),
    topic: str = Field(default="", description="Topic filter, e.g. 'llm', 'ai', 'devops', 'web'"),
    limit: int = Field(default=8, description="Number of results (max 20)"),
) -> str:
    days = {"daily": 1, "weekly": 7, "monthly": 30}.get(since, 7)
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    q = f"created:>{since_date}"
    if language:
        q += f" language:{language}"
    if topic:
        q += f" topic:{topic}"

    data = _get(
        f"{GITHUB_API}/search/repositories",
        params={"q": q, "sort": "stars", "order": "desc", "per_page": min(limit, 20)},
    )

    results = []
    for item in data.get("items", []):
        results.append({
            "full_name": item["full_name"],
            "description": item.get("description") or "",
            "stars": item["stargazers_count"],
            "language": item.get("language") or "",
            "topics": item.get("topics", []),
            "created_at": item["created_at"][:10],
            "url": item["html_url"],
        })
    _cache_repos(data.get("items", []))
    return json.dumps(results, indent=2)


@mcp.tool(
    name="analyze_skill_gap",
    description=(
        "Compare a GitHub user's tech stack against trending technologies in a domain "
        "to surface skill gaps and growth opportunities."
    ),
)
def analyze_skill_gap(
    username: str = Field(description="GitHub username to analyze"),
    domain: str = Field(
        description="Target domain, e.g. 'machine-learning', 'web-development', 'devops', 'mobile'"
    ),
) -> str:
    repos = _get(
        f"{GITHUB_API}/users/{username}/repos",
        params={"sort": "stars", "per_page": 30},
    )

    user_langs: dict[str, int] = {}
    user_topics: set[str] = set()
    for repo in repos:
        lang = repo.get("language")
        if lang:
            user_langs[lang] = user_langs.get(lang, 0) + 1
        user_topics.update(repo.get("topics", []))

    since_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    q = f"topic:{domain} created:>{since_date}"
    trending_data = _get(
        f"{GITHUB_API}/search/repositories",
        params={"q": q, "sort": "stars", "order": "desc", "per_page": 20},
    )

    trending_langs: dict[str, int] = {}
    trending_topics: dict[str, int] = {}
    for item in trending_data.get("items", []):
        lang = item.get("language")
        if lang:
            trending_langs[lang] = trending_langs.get(lang, 0) + 1
        for t in item.get("topics", []):
            trending_topics[t] = trending_topics.get(t, 0) + 1

    top_trending_langs = [l for l, _ in sorted(trending_langs.items(), key=lambda x: x[1], reverse=True)[:8]]
    top_trending_topics = [t for t, _ in sorted(trending_topics.items(), key=lambda x: x[1], reverse=True)[:10]]

    result = {
        "username": username,
        "domain": domain,
        "user_languages": sorted(user_langs.items(), key=lambda x: x[1], reverse=True)[:8],
        "user_topics": sorted(user_topics)[:15],
        "trending_languages_in_domain": top_trending_langs,
        "trending_topics_in_domain": top_trending_topics,
        "languages_to_explore": [l for l in top_trending_langs if l not in user_langs][:5],
        "topics_to_explore": [t for t in top_trending_topics if t not in user_topics][:5],
    }

    recent_profiles[username] = username
    return json.dumps(result, indent=2)


# ──────────────────────────────────────────────
# Resources (power @username / @owner/repo autocomplete)
# ──────────────────────────────────────────────

@mcp.resource("github://recent/users", mime_type="application/json")
def list_recent_users() -> list[str]:
    return list(recent_profiles.keys())


@mcp.resource("github://recent/users/{username}", mime_type="application/json")
def get_cached_user(username: str) -> str:
    return recent_profiles.get(username, "")


@mcp.resource("github://recent/repos", mime_type="application/json")
def list_recent_repos_resource() -> list[str]:
    return list(recent_repos.keys())


@mcp.resource("github://recent/repos/{owner}/{repo}", mime_type="application/json")
def get_cached_repo(owner: str, repo: str) -> str:
    return recent_repos.get(f"{owner}/{repo}", "")


# ──────────────────────────────────────────────
# Prompts
# ──────────────────────────────────────────────

@mcp.prompt(
    name="linkedin_post",
    description="Generate a compelling LinkedIn post showcasing a GitHub repository.",
)
def linkedin_post_prompt(
    repo_full_name: str = Field(description="Full repo name like 'owner/repo'"),
) -> list[base.Message]:
    parts = repo_full_name.split("/", 1)
    owner = parts[0]
    repo = parts[1] if len(parts) == 2 else parts[0]

    return [base.UserMessage(f"""
Write an engaging LinkedIn post for the GitHub repository '{repo_full_name}'.

Steps:
1. Use the 'get_repo_details' tool to fetch full details about '{owner}' / '{repo}'
2. Write a post that:
   - Opens with a strong hook (problem it solves or achievement)
   - Explains what the project does in plain language
   - Highlights the tech stack
   - Mentions key metrics (stars, contributors, activity)
   - Ends with a call to action (check it out, star it, contribute)
   - Uses 4-6 relevant hashtags
   - Is 150-250 words total
   - Reads authentic, not salesy

Output the post ready to copy-paste directly to LinkedIn.
""")]


@mcp.prompt(
    name="career_analysis",
    description="Deep career analysis of a GitHub profile with actionable recommendations.",
)
def career_analysis_prompt(
    username: str = Field(description="GitHub username to analyze"),
) -> list[base.Message]:
    return [base.UserMessage(f"""
Perform a thorough career analysis for GitHub user '{username}'.

Steps:
1. Use 'get_user_profile' to get their full profile and top repos
2. Use 'get_trending_repos' to see what's hot in their primary language right now
3. Provide a structured report with:
   - **Strengths**: What they clearly excel at based on their repos
   - **Tech Stack Summary**: Their core technologies in plain language
   - **Market Positioning**: How their skills align with current demand
   - **Top 3 Growth Opportunities**: Specific technologies to learn next
   - **Portfolio Gaps**: What project types are missing that employers want
   - **LinkedIn Headline**: A compelling, specific headline based on their actual skills

Be specific, honest, and data-driven. Reference actual repos and languages you found.
""")]


@mcp.prompt(
    name="skill_gap",
    description="Find skill gaps between a developer's current stack and what's demanded for a target role.",
)
def skill_gap_prompt(
    username: str = Field(description="GitHub username"),
    target_role: str = Field(
        description="Target job role, e.g. 'ML engineer', 'backend engineer', 'DevOps engineer'"
    ),
) -> list[base.Message]:
    domain = target_role.lower().replace(" ", "-")
    return [base.UserMessage(f"""
Analyze the skill gap for GitHub user '{username}' targeting a '{target_role}' role.

Steps:
1. Use 'get_user_profile' to understand their current skills
2. Use 'analyze_skill_gap' with username='{username}' and domain='{domain}'
3. Use 'get_trending_repos' with a relevant topic to see what's being built for this role
4. Provide:
   - **Where They Stand Now**: Current skill level summary
   - **Already Relevant**: Skills they have that apply to this role
   - **Critical Gaps**: Top 3-5 missing skills — be specific (e.g. "Kubernetes, not just Docker")
   - **Learning Roadmap**: Ordered steps to close the gaps with concrete resources or project types
   - **Portfolio Projects**: 2-3 specific project ideas that directly demonstrate missing skills
   - **Realistic Timeline**: Honest estimate to be interview-ready

Name actual technologies, frameworks, and tools throughout.
""")]


if __name__ == "__main__":
    mcp.run(transport="stdio")
