import asyncio
import json
import shutil
import subprocess

import httpx
import websockets
from loguru import logger

_CHROME_CANDIDATES = [
    "google-chrome",
    "google-chrome-stable",
    "chromium-browser",
    "chromium",
]


class CDPConnectionError(Exception):
    pass


class CDPClient:
    """
    Minimal Chrome DevTools Protocol wrapper.
    Used ONLY for page lifecycle management:
      - navigate to URL
      - wait for network idle
      - get current URL / page title

    Never used for DOM inspection, element finding, or clicking.
    """

    def __init__(self, port: int = 9222):
        self.port = port
        self._ws = None
        self._msg_id: int = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._listen_task: asyncio.Task | None = None

    async def connect(self):
        """Connect to Chrome CDP. Auto-launches Chrome if not already running."""
        if not await self._cdp_reachable():
            await self._launch_chrome()
        await self._attach_to_tab()
        logger.info(f"CDP connected on port {self.port}")

    async def _cdp_reachable(self) -> bool:
        try:
            async with httpx.AsyncClient() as c:
                await c.get(
                    f"http://localhost:{self.port}/json/version", timeout=2.0
                )
            return True
        except Exception:
            return False

    async def _launch_chrome(self):
        binary = next(
            (b for b in _CHROME_CANDIDATES if shutil.which(b)), None
        )
        if not binary:
            raise CDPConnectionError(
                "Chrome/Chromium not found. "
                "Install google-chrome or chromium, then retry."
            )

        cmd = [
            binary,
            f"--remote-debugging-port={self.port}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-default-apps",
        ]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info(f"Launching Chrome ({binary}) on port {self.port}...")

        for _ in range(20):
            await asyncio.sleep(0.5)
            if await self._cdp_reachable():
                logger.info("Chrome is ready")
                return

        raise CDPConnectionError(
            "Chrome launched but CDP not responding after 10s"
        )

    async def _attach_to_tab(self):
        async with httpx.AsyncClient() as c:
            tabs = (
                await c.get(f"http://localhost:{self.port}/json", timeout=5.0)
            ).json()

        page_tabs = [t for t in tabs if t.get("type") == "page"]

        if not page_tabs:
            # Ask Chrome to open a blank tab
            async with httpx.AsyncClient() as c:
                tab = (
                    await c.get(
                        f"http://localhost:{self.port}/json/new", timeout=5.0
                    )
                ).json()
        else:
            tab = page_tabs[0]

        ws_url = tab["webSocketDebuggerUrl"]
        self._ws = await websockets.connect(ws_url)
        self._listen_task = asyncio.create_task(self._listen())

    async def _listen(self):
        """Background task: routes CDP responses to waiting futures."""
        try:
            async for raw in self._ws:
                data = json.loads(raw)
                msg_id = data.get("id")
                if msg_id is not None and msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if not fut.done():
                        fut.set_result(data)
        except Exception as e:
            logger.warning(f"CDP listener exited: {e}")

    async def _send(
        self,
        method: str,
        params: dict | None = None,
        timeout: float = 10.0,
    ) -> dict:
        if self._ws is None:
            raise CDPConnectionError("Not connected — call connect() first")

        self._msg_id += 1
        msg_id = self._msg_id
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending[msg_id] = future

        await self._ws.send(
            json.dumps({"id": msg_id, "method": method, "params": params or {}})
        )

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise TimeoutError(f"CDP timeout waiting for response to {method}")

    # ── Public API ──────────────────────────────────────────────────────────

    async def navigate(self, url: str):
        await self._send("Page.navigate", {"url": url})
        await self.wait_for_network_idle()

    async def wait_for_load(self, timeout_ms: int = 10000):
        # Simple fixed wait; event-driven upgrade is a future task
        await asyncio.sleep(min(timeout_ms / 1000, 3.0))

    async def wait_for_network_idle(
        self,
        idle_time_ms: int = 500,
        timeout_ms: int = 10000,  # noqa: ARG002 — reserved for future use
    ):
        await asyncio.sleep(idle_time_ms / 1000)

    async def get_current_url(self) -> str:
        try:
            result = await self._send(
                "Runtime.evaluate", {"expression": "window.location.href"}
            )
            return result.get("result", {}).get("result", {}).get("value", "")
        except Exception as e:
            logger.warning(f"get_current_url failed: {e}")
            return ""

    async def get_page_title(self) -> str:
        try:
            result = await self._send(
                "Runtime.evaluate", {"expression": "document.title"}
            )
            return result.get("result", {}).get("result", {}).get("value", "")
        except Exception as e:
            logger.warning(f"get_page_title failed: {e}")
            return ""

    async def disconnect(self):
        if self._listen_task:
            self._listen_task.cancel()
        if self._ws:
            await self._ws.close()
