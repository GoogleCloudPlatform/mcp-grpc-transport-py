"""Shared fixtures for tests."""

import socket
from contextlib import closing
import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def find_free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("localhost", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


@pytest.fixture
def free_port():
    return find_free_port()
