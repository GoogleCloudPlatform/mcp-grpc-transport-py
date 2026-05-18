"""End-to-end tests for MCP server-client examples."""

import os
import socket
import subprocess
import sys
import time
from absl import logging
from absl.testing import absltest
from absl.testing import parameterized
from tests import test_utils


class ExampleE2ETest(parameterized.TestCase):
  """End-to-end tests for MCP server-client examples."""

  def _wait_for_port(self, port: int, timeout: float = 10.0) -> bool:
    """Waits for a port to be open on localhost."""
    start_time = time.time()
    while time.time() - start_time < timeout:
      try:
        # Try connecting to the port to see if the server is up before running
        # the client.
        with socket.create_connection(("localhost", port), timeout=1):
          return True
      except (socket.timeout, ConnectionRefusedError, OSError):
        time.sleep(0.5)
    return False

  @parameterized.named_parameters(
      ("simple_tool", "simple_tool"),
      ("simple_resource", "simple_resource"),
  )
  def test_example(self, example_dir: str):
    """Runs a server-client example and verifies it exits successfully."""
    port = test_utils.find_free_port()
    logging.info("Testing example in %s on port %d", example_dir, port)

    # Data dependencies are accessible via relative paths
    # from the test file's directory within the runfiles.
    test_dir = os.path.dirname(os.path.abspath(__file__))
    examples_base = os.path.join(test_dir, "..", "examples")

    # sys.executable is None when the interpreter is not available (eg. when
    # running via Bazel). So use this as a condition to check if the test is
    # running in OSS
    sys_executable = [] if sys.executable is None else [sys.executable]
    if sys.executable is None:
      server_bin = "server"
      client_bin = "client"
    else:
      server_bin = "server.py"
      client_bin = "client.py"

    server_path = os.path.abspath(
        os.path.join(examples_base, example_dir, server_bin)
    )
    client_path = os.path.abspath(
        os.path.join(examples_base, example_dir, client_bin)
    )

    logging.info("Resolved server path: %s", server_path)
    if not os.path.exists(server_path):
      self.fail(f"Server binary not found at {server_path}")

    server_process = subprocess.Popen(
        sys_executable + [server_path, f"--port={port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
      # Wait for server to start and bind to the port
      if not self._wait_for_port(port):
        # Server failed to start or didn't bind in time.
        # Check if it crashed immediately.
        retcode = server_process.poll()
        stdout, stderr = "", ""
        if retcode is not None:
          stdout, stderr = server_process.communicate()
        self.fail(
            f"Server failed to start on port {port} in {example_dir}.\n"
            f"Return code: {retcode}\n"
            f"Stdout: {stdout}\nStderr: {stderr}"
        )

      # Run client
      client_args = sys_executable + [
          client_path,
          "--server_host=localhost",
          f"--server_port={port}",
      ]

      logging.info("Running client: %s", " ".join(client_args))

      client_result = subprocess.run(
          client_args,
          check=True,
          stdout=subprocess.PIPE,
          stderr=subprocess.PIPE,
          text=True,
          timeout=20,
      )

      logging.info("Client stdout: %s", client_result.stdout)
      if client_result.returncode != 0:
        logging.error("Client stderr: %s", client_result.stderr)
        # Also capture server logs on failure
        server_process.terminate()
        server_stdout, server_stderr = server_process.communicate()
        self.fail(
            f"Client for {example_dir} failed with return code"
            f" {client_result.returncode}.\nClient Stderr:"
            f" {client_result.stderr}\nServer Stderr: {server_stderr}\n"
            f"Server Stdout: {server_stdout}"
        )

    finally:
      # Clean up server streams to prevent ResourceWarning
      if server_process.stdout:
        server_process.stdout.close()
      if server_process.stderr:
        server_process.stderr.close()

      # Clean up server
      if server_process.poll() is None:
        server_process.terminate()
        try:
          server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
          server_process.kill()


if __name__ == "__main__":
  absltest.main()
