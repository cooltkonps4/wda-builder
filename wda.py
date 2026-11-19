"""Direct WebDriverAgent (WDA) client - no Appium, no Xcode on the PC.

Talks straight to the HTTP server the WDA runner exposes on the iPhone
(port 8100 by default): screenshots, taps, swipes, home button.

Why no Appium: on iOS 26 the Appium XCUITest driver cannot create sessions
(appium/appium#21643), while standalone WDA works. This client only needs
WDA, which is why it runs on Windows.

CLI:
    python wda.py status
    python wda.py size
    python wda.py shot            # -> shots/shot_<timestamp>.png
    python wda.py tap 214 463
    python wda.py swipe 214 800 214 300 0.25
    python wda.py home
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests

DEFAULT_URL = os.environ.get("WDA_URL", "http://127.0.0.1:8100")
SHOTS = Path(__file__).resolve().parent / "shots"


class WDAError(RuntimeError):
    pass


class WDA:
    def __init__(self, url: str = DEFAULT_URL, timeout: float = 20.0) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.session_id: Optional[str] = None

    # ---------------------------------------------------------------- HTTP
    def _call(self, method: str, path: str, payload=None, timeout: Optional[float] = None):
        try:
            resp = requests.request(
                method, self.url + path, json=payload, timeout=timeout or self.timeout
            )
        except requests.RequestException as exc:
            raise WDAError(f"cannot reach WDA at {self.url}: {exc}") from exc
        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text[:400]}
        if resp.status_code >= 400:
            raise WDAError(f"{method} {path} -> HTTP {resp.status_code}: {body}")
        if isinstance(body, dict) and "value" in body:
            return body["value"]
        return body

    # ------------------------------------------------------------- session
    def status(self):
        return self._call("GET", "/status")

    def wait_ready(self, timeout: float = 45.0, interval: float = 0.5):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                st = self.status()
                if st.get("ready") is True or st.get("state") == "success":
                    return st
                last = st
            except WDAError as exc:
                last = exc
            time.sleep(interval)
        raise WDAError(f"WDA did not become ready within {timeout:.0f}s: {last}")

    def new_session(self, bundle_id: Optional[str] = None):
        """Start a WDA session. With no bundle_id WDA attaches without launching an app."""
        always: dict = {
            "platformName": "iOS",
            "appium:automationName": "XCUITest",
            "appium:noReset": True,
        }
        if bundle_id:
            always["bundleId"] = bundle_id
        payload = {"capabilities": {"alwaysMatch": always}}
        try:
            value = self._call("POST", "/session", payload, timeout=90)
        except WDAError:
            # Pre-W3C WDA builds only understand desiredCapabilities.
            value = self._call(
                "POST", "/session", {"desiredCapabilities": always}, timeout=90
            )
        sid = None
        if isinstance(value, dict):
            sid = value.get("sessionId")
            if not sid and isinstance(value.get("value"), dict):
                sid = value["value"].get("sessionId")
        self.session_id = sid
        return value

    def _sid(self) -> str:
        if not self.session_id:
            raise WDAError("no WDA session - call new_session() first")
        return self.session_id

    # ------------------------------------------------------------ the good bit
    def screenshot(self) -> bytes:
        value = self._call("GET", f"/session/{self._sid()}/screenshot", timeout=60)
        if isinstance(value, dict):
            value = value.get("value") or value.get("data") or ""
        if not value:
            raise WDAError("empty screenshot payload from WDA")
        return base64.b64decode(value)

    def window_size(self):
        """Logical screen size in POINTS (taps use points, screenshots use px)."""
        value = self._call("GET", f"/session/{self._sid()}/window/size")
        if isinstance(value, dict) and "width" in value and "height" in value:
            return int(value["width"]), int(value["height"])
        raise WDAError(f"unexpected window size payload: {value}")

    def tap(self, x: float, y: float):
        sid = self._sid()
        try:
            return self._call("POST", f"/session/{sid}/wda/tap/0", {"x": x, "y": y})
        except WDAError:
            return self._actions([("move", x, y), ("down",), ("pause", 60), ("up",)])

    def swipe(self, x1: float, y1: float, x2: float, y2: float, duration: float = 0.25):
        sid = self._sid()
        try:
            return self._call(
                "POST",
                f"/session/{sid}/wda/dragfromtoforduration",
                {"fromX": x1, "fromY": y1, "toX": x2, "toY": y2, "duration": duration},
            )
        except WDAError:
            return self._actions(
                [
                    ("move", x1, y1),
                    ("down",),
                    ("pause", int(duration * 1000)),
                    ("move", x2, y2),
                    ("up",),
                ]
            )

    def home(self):
        return self._call(
            "POST", f"/session/{self._sid()}/wda/pressButton", {"name": "home"}
        )

    def _actions(self, steps):
        actions = []
        for step in steps:
            kind = step[0]
            if kind == "move":
                actions.append({"type": "pointerMove", "duration": 0, "x": step[1], "y": step[2]})
            elif kind == "down":
                actions.append({"type": "pointerDown", "button": 0})
            elif kind == "up":
                actions.append({"type": "pointerUp", "button": 0})
            elif kind == "pause":
                actions.append({"type": "pause", "duration": step[1]})
        body = {
            "actions": [
                {
                    "type": "pointer",
                    "id": "finger1",
                    "parameters": {"pointerType": "touch"},
                    "actions": actions,
                }
            ]
        }
        return self._call("POST", f"/session/{self._sid()}/actions", body)


def connect(url: str = DEFAULT_URL, bundle_id: Optional[str] = None) -> WDA:
    dev = WDA(url)
    dev.wait_ready()
    dev.new_session(bundle_id)
    return dev


# ------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Drive an iPhone through WebDriverAgent.")
    parser.add_argument("--url", default=DEFAULT_URL, help="WDA base URL")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="print WDA status")
    sub.add_parser("size", help="print logical screen size in points")
    sub.add_parser("home", help="press the home button")
    p_shot = sub.add_parser("shot", help="save a screenshot")
    p_shot.add_argument("out", nargs="?", help="output path (default shots/shot_<ts>.png)")
    p_tap = sub.add_parser("tap", help="tap at point coordinates")
    p_tap.add_argument("x", type=float)
    p_tap.add_argument("y", type=float)
    p_swipe = sub.add_parser("swipe", help="swipe between two points")
    p_swipe.add_argument("x1", type=float)
    p_swipe.add_argument("y1", type=float)
    p_swipe.add_argument("x2", type=float)
    p_swipe.add_argument("y2", type=float)
    p_swipe.add_argument("duration", type=float, nargs="?", default=0.25)

    args = parser.parse_args(argv)
    dev = connect(args.url)

    if args.cmd == "status":
        print(dev.status())
    elif args.cmd == "size":
        print(dev.window_size())
    elif args.cmd == "home":
        dev.home()
        print("home")
    elif args.cmd == "shot":
        SHOTS.mkdir(exist_ok=True)
        out = Path(args.out) if args.out else SHOTS / f"shot_{int(time.time())}.png"
        out.write_bytes(dev.screenshot())
        print(out)
    elif args.cmd == "tap":
        dev.tap(args.x, args.y)
        print(f"tap {args.x} {args.y}")
    elif args.cmd == "swipe":
        dev.swipe(args.x1, args.y1, args.x2, args.y2, args.duration)
        print("swipe")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except WDAError as exc:
        print(f"WDA error: {exc}", file=sys.stderr)
        sys.exit(2)
