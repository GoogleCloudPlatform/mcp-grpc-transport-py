# Testing Guidelines (tests/AGENTS.md)

Guidelines for writing and running tests in this repository.

## Test Environment

*   **Framework:**
    *   Sync tests: `absl.testing.absltest.TestCase`.
    *   Async tests: inherit from **both** `absltest.TestCase` and `unittest.IsolatedAsyncioTestCase` (e.g. `class T(absltest.TestCase, IsolatedAsyncioTestCase)`). Absl gives us the richer assertions (`assertLen`, etc.); `IsolatedAsyncioTestCase` provides `async def test_*` / `asyncSetUp` / `asyncTearDown` since absl ships no async-aware TestCase.
    *   No `pytest`. Do not add `pytest.mark`, `pytest.fixture`, `pytest.raises`, etc.
*   **Runner:** `uv run python -m unittest discover -s tests -v`. Each test file ends with `if __name__ == "__main__": absltest.main()` so it can also be run standalone.
*   **Shared helpers** live in [tests/helpers.py](helpers.py) (e.g. `find_free_port`, `FakeAioRpcError`, `make_fake_aio_rpc_error`).

---

## Test Structuring

*   **Group related tests in TestCase classes.** Inheriting from `absltest.TestCase` (sync) or `unittest.IsolatedAsyncioTestCase` (async) is required for setup/teardown and assertion methods.
*   **Use unittest assertions** (`self.assertEqual`, `self.assertRaises`, `self.assertIn`, `self.assertRaisesRegex`, etc.). Plain `assert` works but loses diff output on failure.
*   **Type Safety over `type: ignore`:** Do not use `# type: ignore` to suppress type warnings. Use explicit typing or `assertIsInstance` to narrow types.
*   **Keep Tests Fast & Deterministic:**
    *   Avoid fixed sleep durations to wait for asynchronous conditions. Use `anyio.Event` or stream signalling.
    *   The one accepted exception is the timeout test in `test_conformance.py`, where a sleep is the point of the test.

---

## Loopback Integration Testing Patterns

When writing end-to-end integration tests (see `tests/test_integration.py`):

1.  **Port Allocation:** Call `find_free_port()` from `tests.helpers` (binds to port `0` and immediately closes the socket).
2.  **Managed vs Unmanaged Modes:**
    *   **Managed Server:** Use the context manager to automatically start and stop both the gRPC server and the runner loop:
        ```python
        async with McpGrpcServer(server, address=address):
             # client execution...
        ```
    *   **Unmanaged Server:** If you need to manage the gRPC server separately (e.g. to test what happens when the runner is stopped but the server stays alive):
        *   Instantiate `McpGrpcServer` **first** (which registers the servicer).
        *   Bind the port and call `await grpc_server.start()`.
        *   Then enter the `McpGrpcServer` context to drive the runner:
            ```python
            app = McpGrpcServer(server, server=grpc_server)  # registers servicer
            grpc_server.add_insecure_port(address)
            await grpc_server.start()

            async with app:
                # runner is active...
            ```
        *   This registration order is critical to avoid `UNIMPLEMENTED` (Method not found) gRPC errors.
