"""Utility functions for testing."""

import anyio
import socket
from contextlib import closing


def find_free_port():
  """Finds a free port."""
  with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
    s.bind(('localhost', 0))
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return s.getsockname()[1]


async def run_server_for_test(mcp_grpc_server):
  async with anyio.create_task_group() as tg:
    tg.start_soon(mcp_grpc_server.run_grpc_async)
    await anyio.sleep(0.2)
    await mcp_grpc_server.stop_grpc_server(0.5)
