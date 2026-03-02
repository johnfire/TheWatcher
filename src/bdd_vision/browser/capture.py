from datetime import datetime
from pathlib import Path

import mss
from loguru import logger
from PIL import Image


class ScreenCapture:
    """
    Fast screenshot capture via mss.
    On failure, returns the last successful screenshot rather than raising.
    """

    def __init__(self, session_dir: Path, monitor: int = 1):
        self.session_dir = session_dir
        self.monitor_index = monitor
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._last: Image.Image | None = None

    def capture(self, label: str = "") -> tuple[Image.Image, Path]:
        """
        Capture screenshot. Returns (PIL Image, saved file path).
        Never raises — on failure logs and returns last known good screenshot.
        """
        try:
            with mss.mss() as sct:
                # monitor_index 0 = all monitors combined; 1+ = individual monitors
                monitors = sct.monitors
                if self.monitor_index >= len(monitors):
                    logger.warning(
                        f"Monitor {self.monitor_index} not found, falling back to monitor 1"
                    )
                    monitor = monitors[1]
                else:
                    monitor = monitors[self.monitor_index]

                raw = sct.grab(monitor)
                # mss returns BGRA; convert to RGB for Pillow
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            slug = f"_{label}" if label else ""
            path = self.session_dir / f"{timestamp}{slug}.png"
            img.save(path)
            self._last = img
            logger.debug(f"Screenshot saved: {path}")
            return img, path

        except Exception as e:
            logger.error(f"Screenshot capture failed: {e}")
            if self._last is not None:
                logger.warning("Using last successful screenshot as fallback")
                return self._last, Path("/dev/null")
            # Absolute last resort: grey placeholder
            img = Image.new("RGB", (1280, 900), color=(128, 128, 128))
            return img, Path("/dev/null")
