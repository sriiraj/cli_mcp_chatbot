# GitHub Career Intelligence Bot

A CLI-based AI assistant powered by **Claude** and the **Model Context Protocol (MCP)** that gives developers real-time GitHub insights for career growth.

Built on the MCP architecture from Anthropic's official MCP course — extended into a fully functional career intelligence tool with live GitHub API data.

---

## What It Does

Ask it anything about GitHub — it fetches live data, reasons over it, and gives you actionable answers:

```
> What are the most trending Python AI repos this week?
> Analyze the GitHub profile of torvalds
> What skill gaps do I have if I want to become an ML engineer?
> /linkedin_post microsoft/vscode
> /career_analysis gvanrossum
> /skill_gap yourname
```

---

## Features

- **Trending Repos** — Find what's gaining stars right now, filtered by language or topic
- **Developer Profile Analysis** — Tech stack breakdown, top projects, follower count
- **Repo Deep Dive** — Language breakdown, contributors, license, activity
- **Skill Gap Analysis** — Compare your GitHub stack to trending tech in any domain
- **LinkedIn Post Generator** — One command generates a ready-to-post LinkedIn showcase
- **Career Analysis** — Strengths, market positioning, growth recommendations
- **`@username` autocomplete** — Type `@` to tab-complete recently fetched profiles
- **`/command` autocomplete** — Type `/` to tab-complete available prompt templates

---

## Architecture

```
┌─────────────────────────────────────────────┐
│                  main.py                    │
│   (bootstraps Claude + MCP servers)         │
└──────────────┬──────────────────────────────┘
               │
       ┌───────▼────────┐
       │   CliApp        │  prompt-toolkit terminal UI
       │   CliChat       │  query preprocessing (@refs, /commands)
       │   Chat          │  agentic loop (Claude <-> tools)
       └───────┬────────┘
               │ MCP stdio transport
       ┌───────▼────────────────┐
       │  github_mcp_server.py  │
       │                        │
       │  Tools:                │
       │  - search_repositories │
       │  - get_user_profile    │──► GitHub REST API
       │  - get_repo_details    │
       │  - get_trending_repos  │
       │  - analyze_skill_gap   │
       │                        │
       │  Prompts:              │
       │  - /linkedin_post      │
       │  - /career_analysis    │
       │  - /skill_gap          │
       └────────────────────────┘
```

**How the agentic loop works:**
1. User types a query
2. Claude receives the query + all available MCP tools
3. Claude decides which tools to call (often chaining multiple in sequence)
4. Tool results (live GitHub data) are fed back to Claude
5. Claude reasons over the data and responds

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Claude (Anthropic SDK) |
| MCP Framework | FastMCP (`mcp[cli]`) |
| Terminal UI | prompt-toolkit |
| GitHub Data | GitHub REST API |
| Runtime | Python 3.10+ / asyncio |

---

## Setup

**1. Clone and install**
```bash
git clone https://github.com/yourusername/github-career-bot
cd github-career-bot
uv pip install -e .
```

**2. Create `.env`**
```env
ANTHROPIC_API_KEY="sk-ant-api03-..."     # get free credits at console.anthropic.com
CLAUDE_MODEL="claude-haiku-4-5-20251001"
USE_UV=1
GITHUB_TOKEN="ghp_..."                   # optional — raises GitHub rate limit from 60 to 5000 req/hr
```

**3. Run**
```bash
python main.py
```

---

## Example Session

```
> What Python repos are trending this week in AI?

Here are the top trending Python AI repositories this week:

1. instructor (8,234 stars) — Structured outputs for LLMs using Pydantic
2. litellm (12,100 stars) — Call all LLM APIs using the OpenAI format
3. open-webui (38,000 stars) — User-friendly web UI for running local LLMs

> /career_analysis torvalds

Strengths: Dominates low-level systems programming (C, kernel development)
Market Positioning: Highly specialized in OS/kernel space
Top 3 Growth Opportunities: Rust (already trending in kernel), WebAssembly, eBPF
Suggested LinkedIn Headline: "Creator of Linux & Git | Systems Programming Expert"
```

---

## Project Structure

```
├── github_mcp_server.py   # MCP server — GitHub API tools, prompts, resources
├── mcp_client.py          # Async MCP stdio client
├── main.py                # Entry point, wires Claude + MCP
├── core/
│   ├── claude.py          # Anthropic API wrapper
│   ├── chat.py            # Agentic tool-use loop
│   ├── cli_chat.py        # @ref and /command preprocessing
│   ├── cli.py             # Terminal UI with autocomplete
│   └── tools.py           # Multi-server tool aggregation
└── mcp_server.py          # Reference: original course document MCP server
```

---

## Extending It

Plug in any additional MCP server at runtime — no code changes needed:

```bash
python main.py your_new_server.py
```

Its tools are automatically discovered and made available to Claude alongside the GitHub tools.

---

## References

- [Model Context Protocol](https://modelcontextprotocol.io)
- [Anthropic MCP Course](https://anthropic.com)
- [GitHub REST API](https://docs.github.com/en/rest)
- [prompt-toolkit](https://python-prompt-toolkit.readthedocs.io)
