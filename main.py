import asyncio
import sys
import os
from dotenv import load_dotenv
from contextlib import AsyncExitStack

from mcp_client import MCPClient
from core.claude import Claude
from core.cli_chat import CliChat
from core.cli import CliApp

load_dotenv()

claude_model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")

assert claude_model, "Error: CLAUDE_MODEL cannot be empty. Update .env"
assert anthropic_api_key, "Error: ANTHROPIC_API_KEY cannot be empty. Update .env"


SYSTEM_PROMPT = """You are a GitHub Career Intelligence assistant. You help developers:
- Discover trending repositories and technologies
- Analyze developer profiles and portfolios
- Find skill gaps for target job roles
- Generate LinkedIn posts and career content

Always use the available GitHub tools to fetch real data before answering.
When a user mentions a GitHub username, use get_user_profile.
When asked about trends, use get_trending_repos.
Be specific, data-driven, and actionable in your responses."""


async def main():
    claude_service = Claude(model=claude_model)

    server_scripts = sys.argv[1:]
    clients = {}

    command, args = (
        ("uv", ["run", "github_mcp_server.py"])
        if os.getenv("USE_UV", "0") == "1"
        else ("python", ["github_mcp_server.py"])
    )

    async with AsyncExitStack() as stack:
        doc_client = await stack.enter_async_context(
            MCPClient(command=command, args=args)
        )
        clients["doc_client"] = doc_client

        for i, server_script in enumerate(server_scripts):
            client_id = f"client_{i}_{server_script}"
            client = await stack.enter_async_context(
                MCPClient(command="uv", args=["run", server_script])
            )
            clients[client_id] = client

        chat = CliChat(
            doc_client=doc_client,
            clients=clients,
            claude_service=claude_service,
            system_prompt=SYSTEM_PROMPT,
            resource_list_uri="github://recent/users",
            resource_item_uri_fmt="github://recent/users/{id}",
            prompt_arg_key="username",
        )

        cli = CliApp(chat)
        await cli.initialize()
        await cli.run()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
