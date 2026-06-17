# Testing Guidelines (tests/AGENTS.md)

Guidelines for writing and running tests in this repository.

## Test Environment

*   **Framework:** Use **`pytest`** to execute the test suite. Run with `uv run pytest`.
*   **Asynchronous Engine:** Use **`anyio`** for all asynchronous tests.
    *   Tests must specify the backend fixture:
        ```python
        @pytest.fixture
        def anyio_backend():
            return "asyncio"
        ```
    *   Annotate async tests with `@pytest.mark.anyio`.

---

## Test Structuring

*   **No Prefix Classes:** Do not group test functions in `Test` classes. Write plain, top-level `test_*` functions instead.
*   **Type Safety over `type: ignore`:** In tests, do not use `# type: ignore` to suppress type warnings. Instead, use explicit typing or `assert isinstance(x, T)` to narrow types.
*   **Keep Tests Fast & Deterministic:**
    *   Avoid using fixed sleep durations (`anyio.sleep(1.0)`) to wait for asynchronous conditions.
    *   Instead, use synchronization primitives like `anyio.Event` or read directly from streams where relevant.

---

## Loopback Integration Testing Patterns

When writing end-to-end integration tests (like those in `tests/test_integration.py`):

1.  **Port Allocation:** Use `find_free_port()` (which binds to port `0` and immediately closes the socket) to find a dynamically available local port.
2.  **Managed vs Unmanaged Modes:**
    *   **Managed Server:** Use the context manager to automatically start and stop both the gRPC server and the runner loop:
        ```python
        async with McpGrpcServer(server, address=address):
             # Client execution...
        ```
    *   **Unmanaged Server:** If you need to manage the gRPC server separately (e.g., to test what happens when the runner is stopped but the server stays alive):
        *   Instantiate `McpGrpcServer` **first** (which registers the servicer).
        *   Bind the port and call `await grpc_server.start()`.
        *   Then enter the `McpGrpcServer` context to drive the runner:
            ```python
            app = McpGrpcServer(server, server=grpc_server) # Registers servicer
            grpc_server.add_insecure_port(address)
            await grpc_server.start()
            
            async with app:
                # Runner is active...
            ```
        *   This registration order is critical to avoid `UNIMPLEMENTED` (Method not found) gRPC errors.
