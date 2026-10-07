"""Drive the installed headless Chrome over the DevTools pipe using only the standard library (plan 02-12).

No browser-automation package may be added (D-20), so this speaks the Chrome DevTools Protocol itself:
Chrome is launched with ``--remote-debugging-pipe``; it reads commands on file descriptor 3 and writes
replies and events on file descriptor 4, each message a JSON document terminated by a NUL byte.

Chrome insists on exactly descriptors 3 and 4, so the pipe ends are duplicated onto them inside
``preexec_fn`` and 3 and 4 are also listed in ``pass_fds``. Passing other descriptor numbers makes Chrome
report "Remote debugging pipe file descriptors are not open".

Waiting uses ``test.helpers.wait.wait_until``, the only permitted polling site; there are no fixed delays here.
"""
from __future__ import annotations

import fcntl
import json
import os
import select
import shutil
import signal
import subprocess
import tempfile
from types import TracebackType
from typing import Any

from test.helpers.wait import wait_until

CHROME_BIN = "google-chrome"
_HIGH_FD = 10  # park our pipe ends above 4 so dup2 onto 3 and 4 can never clobber a source descriptor


class ChromeError(RuntimeError):
    """A DevTools command failed or the page raised; the message never contains page cookies or tokens."""


def chrome_path() -> str | None:
    return shutil.which(CHROME_BIN)


def _park(fd: int) -> int:
    """Duplicate ``fd`` to a descriptor >= 10 and close the original."""
    parked = fcntl.fcntl(fd, fcntl.F_DUPFD, _HIGH_FD)
    os.close(fd)
    return parked


class ChromeSession:
    """Context manager owning one headless Chrome process and one attached page."""

    def __init__(self, chrome: str | None = None) -> None:
        self._chrome = chrome or chrome_path()
        if not self._chrome:
            raise ChromeError("google-chrome is not installed")
        self._proc: subprocess.Popen[bytes] | None = None
        self._profile: str | None = None
        self._to_chrome = -1
        self._from_chrome = -1
        self._buffer = b""
        self._next_id = 0
        self._responses: dict[int, dict[str, Any]] = {}
        self._events: list[dict[str, Any]] = []
        self._session_id: str | None = None

    # -- lifecycle -----------------------------------------------------------------------------

    def __enter__(self) -> ChromeSession:
        assert self._chrome is not None
        cmd_r, cmd_w = os.pipe()
        rep_r, rep_w = os.pipe()
        chrome_reads, we_write = _park(cmd_r), _park(cmd_w)
        we_read, chrome_writes = _park(rep_r), _park(rep_w)
        self._profile = tempfile.mkdtemp(prefix="devrag-chrome-")

        def _install_pipe_fds() -> None:
            os.dup2(chrome_reads, 3)
            os.dup2(chrome_writes, 4)

        try:
            self._proc = subprocess.Popen(  # noqa: S603
                [
                    self._chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run",
                    "--disable-extensions", "--disable-background-networking", "--remote-debugging-pipe",
                    f"--user-data-dir={self._profile}", "about:blank",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=_install_pipe_fds,  # noqa: PLW1509 - the only way to land the pipe on descriptors 3 and 4
                pass_fds=(3, 4),
                start_new_session=True,
            )
        except BaseException:
            os.close(we_write)
            os.close(we_read)
            shutil.rmtree(self._profile, ignore_errors=True)
            raise
        finally:
            os.close(chrome_reads)
            os.close(chrome_writes)
        self._to_chrome, self._from_chrome = we_write, we_read
        try:
            self._attach()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            if proc.poll() is None:
                try:
                    self._send({"id": self._take_id(), "method": "Browser.close"})
                    proc.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)  # the session leader: Chrome and every helper it spawned
                except OSError:
                    pass
                proc.wait(timeout=10)
            else:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)  # reap stragglers of a clean exit
                except OSError:
                    pass
        for fd in (self._to_chrome, self._from_chrome):
            if fd >= 0:
                os.close(fd)
        self._to_chrome = self._from_chrome = -1
        if self._profile:
            shutil.rmtree(self._profile, ignore_errors=True)
            self._profile = None

    # -- transport -----------------------------------------------------------------------------

    def _take_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _send(self, message: dict[str, Any]) -> None:
        os.write(self._to_chrome, json.dumps(message).encode() + b"\0")

    def _pump(self, timeout: float = 0.0) -> None:
        """Read whatever Chrome has written, dispatching replies and events."""
        ready, _, _ = select.select([self._from_chrome], [], [], timeout)
        if not ready:
            return
        chunk = os.read(self._from_chrome, 1 << 16)
        if not chunk:
            raise ChromeError("Chrome closed the DevTools pipe")
        self._buffer += chunk
        while b"\0" in self._buffer:
            raw, self._buffer = self._buffer.split(b"\0", 1)
            if not raw:
                continue
            message = json.loads(raw)
            if "id" in message:
                self._responses[message["id"]] = message
            else:
                self._events.append(message)

    def call(self, method: str, params: dict[str, Any] | None = None, *, timeout: float = 30.0, session: bool = True) -> dict[str, Any]:
        """Send one DevTools command and return its ``result``; raise ChromeError on a protocol error."""
        ident = self._take_id()
        message: dict[str, Any] = {"id": ident, "method": method, "params": params or {}}
        if session and self._session_id:
            message["sessionId"] = self._session_id
        self._send(message)
        wait_until(lambda: self._reply_ready(ident), timeout=timeout, interval=0.01, describe=lambda: f"reply to {method}")
        reply = self._responses.pop(ident)
        if "error" in reply:
            raise ChromeError(f"{method} failed: {reply['error'].get('message', 'unknown error')}")
        return reply.get("result", {})

    def _reply_ready(self, ident: int) -> bool:
        self._pump(0.05)
        return ident in self._responses

    def _attach(self) -> None:
        wait_until(lambda: self._proc is not None and self._proc.poll() is None, timeout=15, interval=0.05)
        target = self.call("Target.createTarget", {"url": "about:blank"}, session=False)["targetId"]
        attached = self.call("Target.attachToTarget", {"targetId": target, "flatten": True}, session=False)
        self._session_id = attached["sessionId"]
        self.call("Page.enable")
        self.call("Runtime.enable")

    # -- page API ------------------------------------------------------------------------------

    def navigate(self, url: str, *, timeout: float = 30.0) -> None:
        """Navigate and wait for the document's load event (an SPA may redirect afterwards; use wait_for)."""
        self._events.clear()
        result = self.call("Page.navigate", {"url": url}, timeout=timeout)
        if result.get("errorText"):
            raise ChromeError(f"navigation to {url} failed: {result['errorText']}")
        wait_until(self._loaded, timeout=timeout, interval=0.02, describe=lambda: f"load event for {url}")

    def _loaded(self) -> bool:
        self._pump(0.05)
        return any(event.get("method") == "Page.loadEventFired" for event in self._events)

    def evaluate(self, expression: str, *, timeout: float = 30.0) -> Any:
        """Evaluate JavaScript in the page and return the JSON-serialisable result."""
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
            timeout=timeout,
        )
        if "exceptionDetails" in result:
            text = result["exceptionDetails"].get("exception", {}).get("description") or result["exceptionDetails"].get("text", "")
            raise ChromeError(f"page script raised: {text[:200]}")
        return result.get("result", {}).get("value")

    def wait_for(self, expression: str, describe: str, timeout: float = 30.0) -> Any:
        """Poll a page expression until it is truthy and return its value."""

        def _probe() -> Any:
            try:
                return self.evaluate(expression, timeout=5)
            except (ChromeError, TimeoutError):
                return None  # the document is mid-navigation; try again

        return wait_until(_probe, timeout=timeout, interval=0.1, describe=lambda: describe)
