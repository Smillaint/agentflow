# -*- coding: utf-8 -*-
"""Minimal MCP StreamableHTTP client used by TraceFlow to call TraceRAG tools.

The MCP client API is asynchronous, but TraceFlow's :class:`ToolRegistry`
handlers are synchronous (they run inside FastAPI's worker thread pool for
the web service, or plain CLI for ``main.py``). This module bridges that gap
by running each call in a fresh event loop via :func:`asyncio.run`.

Each call opens a short-lived connection, performs ``initialize`` + one
``call_tool``, then closes. This keeps the client stateless and avoids
session-lifecycle complexity, which is fine for the low request rate of a
RAG retrieval call (the heavy reranker on the server side dominates latency).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class MCPClient:
    """Stateless MCP client that calls remote tools synchronously."""

    def __init__(self, server_url: str, timeout_seconds: float = 120.0):
        self.server_url = server_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call a remote MCP tool and return its decoded payload.

        Returns a dict. On any failure returns ``{"error": "<message>"}``
        so callers (tool handlers) can surface it as a ToolResult error
        instead of crashing the agent.
        """
        try:
            return asyncio.run(self._call_tool(name, arguments or {}))
        except RuntimeError as exc:
            if "cannot be called from a running event loop" not in str(exc):
                return {"error": f"{type(exc).__name__}: {exc}"}
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self._call_tool(name, arguments or {}))
            finally:
                loop.close()
        except BaseExceptionGroup as exc:
            return {"error": self._unwrap_group(exc)}
        except Exception as exc:  # noqa: BLE001 - keep the agent alive on transport errors.
            logger.exception("MCP call_tool('%s') failed", name)
            return {"error": f"{type(exc).__name__}: {exc}"}

    @staticmethod
    def _unwrap_group(exc: BaseExceptionGroup) -> str:
        """Flatten an ExceptionGroup into a human-readable error string."""
        causes: list[str] = []
        for sub in exc.exceptions:
            if isinstance(sub, BaseExceptionGroup):
                causes.append(MCPClient._unwrap_group(sub))
            else:
                causes.append(f"{type(sub).__name__}: {sub}")
        return "; ".join(causes) if causes else str(exc)

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(self.server_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    name,
                    arguments,
                    read_timeout_seconds=self.timeout_seconds,
                )
                return self._extract(result)

    @staticmethod
    def _extract(result: Any) -> dict[str, Any]:
        """Decode the first text content block of a CallToolResult as JSON."""
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            if not text:
                continue
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return {"text": text}
        if getattr(result, "isError", False):
            return {"error": "remote tool reported an error with no text content."}
        return {}

    def list_tools(self) -> list[dict[str, Any]]:
        """List the names and descriptions of tools exposed by the server."""
        try:
            return asyncio.run(self._list_tools())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self._list_tools())
            finally:
                loop.close()
        except Exception as exc:  # noqa: BLE001
            logger.exception("MCP list_tools() failed")
            return []

    async def _list_tools(self) -> list[dict[str, Any]]:
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(self.server_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listing = await session.list_tools()
                return [
                    {"name": t.name, "description": t.description}
                    for t in getattr(listing, "tools", []) or []
                ]
