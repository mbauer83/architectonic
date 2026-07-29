"""STDIO bridges for the assurance MCP endpoints.

Two thin HTTP-proxy bridges connecting MCP clients to the backend-mounted
assurance endpoints at /mcp/assurance-read and /mcp/assurance-write.
"""

from __future__ import annotations

from src.infrastructure.mcp.arch_mcp_stdio import main


def main_read(argv: list[str] | None = None) -> None:
    main(["--server", "assurance-read"] + (argv or []))


def main_write(argv: list[str] | None = None) -> None:
    main(["--server", "assurance-write"] + (argv or []))


if __name__ == "__main__":
    main_read()
