"""Tests for server creation."""

import threading
import time

import anyio
from mcp_grpc_transport.server import FastMCPGrpc
from mcp_grpc_transport.server import GrpcTransportSettings

from tests import test_utils


def test_server_creation_and_run():
  """Tests server creation and run."""
  port = test_utils.find_free_port()
  target = f'localhost:{port}'

  mcp_grpc_server = FastMCPGrpc(
      target=target,
      name='test-server',
      description='this is a sample test server',
  )

  assert mcp_grpc_server.name == 'test-server'
  assert mcp_grpc_server.description == 'this is a sample test server'
  assert mcp_grpc_server.target == target

  run_thread = threading.Thread(target=mcp_grpc_server.run, daemon=True)
  run_thread.start()

  time.sleep(0.2)

  anyio.run(mcp_grpc_server.stop_grpc_server, 0.5)
  run_thread.join(timeout=5)  # 5 seconds timeout to join

  assert not run_thread.is_alive(), 'mcp.run() thread did not terminate'


def test_server_creation_and_run_grpc_async():
  """Tests server creation and run_grpc_async."""
  port = test_utils.find_free_port()
  target = f'localhost:{port}'

  mcp_grpc_server = FastMCPGrpc(
      target=target,
      name='test-server',
      description='this is a sample test server',
  )

  assert mcp_grpc_server.name == 'test-server'
  assert mcp_grpc_server.description == 'this is a sample test server'
  assert mcp_grpc_server.target == target

  anyio.run(test_utils.run_server_for_test, mcp_grpc_server)
