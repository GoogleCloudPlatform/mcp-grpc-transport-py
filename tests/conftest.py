"""Shared fixtures for tests."""

import socket
from contextlib import closing

import grpc
import pytest

from mcp_grpc_transport import errors


@pytest.fixture
def anyio_backend():
    return "asyncio"


def find_free_port() -> int:
    """Bind to port 0 to ask the OS for a free port, then release it."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("localhost", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


@pytest.fixture
def free_port() -> int:
    return find_free_port()


class FakeAioRpcError(grpc.aio.AioRpcError):
    """Test double for grpc.aio.AioRpcError.

    The real AioRpcError requires internal gRPC state to construct; this
    subclass lets tests synthesise errors with whatever code, details, and
    trailing metadata they need.
    """

    def __init__(
        self,
        code: grpc.StatusCode,
        details: str = "",
        trailing_metadata: tuple[tuple[str, str], ...] = (),
    ):
        self._code = code
        self._details = details
        self._trailing = trailing_metadata

    def code(self) -> grpc.StatusCode:
        return self._code

    def details(self) -> str:
        return self._details

    def trailing_metadata(self):
        return self._trailing

    def __repr__(self) -> str:
        return f"FakeAioRpcError(code={self._code}, details={self._details!r})"


@pytest.fixture
def fake_aio_rpc_error():
    """Factory for FakeAioRpcError instances, optionally carrying an MCP code."""

    def _make(
        code: grpc.StatusCode,
        details: str = "",
        mcp_code: int | None = None,
    ) -> FakeAioRpcError:
        trailing: tuple[tuple[str, str], ...] = ()
        if mcp_code is not None:
            trailing = ((errors.MCP_CODE_METADATA_KEY, str(mcp_code)),)
        return FakeAioRpcError(code, details, trailing)

    return _make
