import asyncio
from pathlib import Path

import pyautogui
from loguru import logger
from PIL import Image

from .capture import ScreenCapture
from .cdp import CDPClient

# Stop pyautogui moving mouse to corner to raise exception
pyautogui.FAILSAFE = True
# Reduce default pause between pyautogui calls (we manage timing ourselves)
pyautogui.PAUSE = 0.0


class BrowserController:
    """
    All mouse and keyboard actions.
    Every action captures a before screenshot, executes, waits for network
    idle via CDP, then captures an after screenshot.
    Failures are caught and logged — they never propagate silently.

    Note on text input: pyautogui.write() handles printable ASCII only.
    Unicode input via clipboard (pyperclip) is a future enhancement.
    """

    def __init__(
        self,
        capture: ScreenCapture,
        cdp: CDPClient,
        action_delay_ms: int = 200,
        fallback_wait_ms: int = 2000,
    ):
        self.capture = capture
        self.cdp = cdp
        self.action_delay_ms = action_delay_ms
        self.fallback_wait_ms = fallback_wait_ms

    # ── Internals ───────────────────────────────────────────────────────────

    async def _pre(self, label: str) -> tuple[Image.Image, Path]:
        return self.capture.capture(f"before_{label}")

    async def _post(self, label: str) -> tuple[Image.Image, Path]:
        try:
            await self.cdp.wait_for_network_idle()
        except Exception as e:
            logger.warning(
                f"CDP idle check failed ({e}) — falling back to "
                f"{self.fallback_wait_ms}ms sleep"
            )
            await asyncio.sleep(self.fallback_wait_ms / 1000)
        return self.capture.capture(f"after_{label}")

    async def _delay(self):
        await asyncio.sleep(self.action_delay_ms / 1000)

    def _action_result(self, action: str, before: Path, after: Path, **extra) -> dict:
        return {"action": action, "before": str(before), "after": str(after), **extra}

    # ── Public actions ───────────────────────────────────────────────────────

    async def click(self, x: int, y: int, button: str = "left") -> dict:
        _, before = await self._pre("click")
        try:
            pyautogui.click(x, y, button=button)
            logger.debug(f"click({x}, {y}, button={button})")
        except Exception as e:
            logger.error(f"click({x}, {y}) failed: {e}")
        await self._delay()
        _, after = await self._post("click")
        return self._action_result("click", before, after, x=x, y=y, button=button)

    async def double_click(self, x: int, y: int) -> dict:
        _, before = await self._pre("dbl_click")
        try:
            pyautogui.doubleClick(x, y)
            logger.debug(f"double_click({x}, {y})")
        except Exception as e:
            logger.error(f"double_click({x}, {y}) failed: {e}")
        await self._delay()
        _, after = await self._post("dbl_click")
        return self._action_result("double_click", before, after, x=x, y=y)

    async def right_click(self, x: int, y: int) -> dict:
        return await self.click(x, y, button="right")

    async def type_text(self, text: str, interval_ms: int = 50) -> dict:
        _, before = await self._pre("type")
        try:
            pyautogui.write(text, interval=interval_ms / 1000)
            logger.debug(f"type_text({text!r})")
        except Exception as e:
            logger.error(f"type_text failed: {e}")
        await self._delay()
        _, after = await self._post("type")
        return self._action_result("type_text", before, after, text=text)

    async def press_key(self, key: str) -> dict:
        _, before = await self._pre("key")
        try:
            pyautogui.press(key)
            logger.debug(f"press_key({key})")
        except Exception as e:
            logger.error(f"press_key({key}) failed: {e}")
        await self._delay()
        _, after = await self._post("key")
        return self._action_result("press_key", before, after, key=key)

    async def scroll(self, x: int, y: int, clicks: int) -> dict:
        _, before = await self._pre("scroll")
        try:
            pyautogui.scroll(clicks, x=x, y=y)
            logger.debug(f"scroll({x}, {y}, clicks={clicks})")
        except Exception as e:
            logger.error(f"scroll({x}, {y}) failed: {e}")
        await self._delay()
        _, after = await self._post("scroll")
        return self._action_result("scroll", before, after, x=x, y=y, clicks=clicks)

    async def hover(self, x: int, y: int) -> dict:
        _, before = await self._pre("hover")
        try:
            pyautogui.moveTo(x, y)
            logger.debug(f"hover({x}, {y})")
        except Exception as e:
            logger.error(f"hover({x}, {y}) failed: {e}")
        await self._delay()
        _, after = await self._post("hover")
        return self._action_result("hover", before, after, x=x, y=y)

    async def drag(self, x1: int, y1: int, x2: int, y2: int) -> dict:
        _, before = await self._pre("drag")
        try:
            pyautogui.moveTo(x1, y1)
            pyautogui.dragTo(x2, y2, button="left", duration=0.3)
            logger.debug(f"drag({x1},{y1}) -> ({x2},{y2})")
        except Exception as e:
            logger.error(f"drag failed: {e}")
        await self._delay()
        _, after = await self._post("drag")
        return self._action_result(
            "drag", before, after, from_xy=(x1, y1), to_xy=(x2, y2)
        )
