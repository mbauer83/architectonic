"""Entry point shim for arch-mcp-stdio-write."""

from src.infrastructure.mcp.arch_mcp_stdio import main


def main_write(argv: list[str] | None = None) -> None:
    """Bridge that routes to the write MCP server."""
    main(["--server", "write"] + (argv or []))


if __name__ == "__main__":
    main_write()
