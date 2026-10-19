"""macOS/Linux supervisor: one bot, a managed quick tunnel, and safe recovery."""
from __future__ import annotations
import fcntl
import base64
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values, set_key
import requests
import urllib3
import line_bot_local as bot

LOG = logging.getLogger("line-service")


def owned_tunnel(command, port):
    try:
        args = shlex.split(command)
        target = urlsplit(args[args.index("--url") + 1])
        return (Path(args[0]).name == "cloudflared" and target.hostname in ("127.0.0.1", "localhost")
                and target.port == port and target.scheme == "http" and not target.username
                and not target.password and not target.query and target.path in ("", "/"))
    except (ValueError, IndexError):
        return False


class Service:
    def __init__(self, config, root=ROOT):
        self.config, self.root = dict(config), Path(root)
        self.port = int(config.get("PORT") or "3000")
        if not 1 <= self.port <= 65535:
            raise ValueError("Invalid port")
        self.stop = threading.Event()
        self.child = self.tunnel = None
        self.pid_path = self.root / "data/cloudflared-process.json"
        self.base = (config.get("PUBLIC_BASE_URL") or "").rstrip("/")

    def probe(self, base):
        url = base.rstrip("/") + "/health"
        try:
            response = requests.get(url, timeout=4, allow_redirects=False)
            return response.status_code, response.text.strip()
        except requests.ConnectionError:
            # Some local resolvers cache NXDOMAIN for newly created quick tunnels.
            # Use authenticated HTTPS DNS only for this fixed public service.
            host = urlsplit(base).hostname or ""
            if not re.fullmatch(r"[a-z0-9-]+\.trycloudflare\.com", host):
                return 0, ""
            try:
                answer = requests.get("https://cloudflare-dns.com/dns-query",
                    params={"name": host, "type": "A"}, headers={"Accept": "application/dns-json"}, timeout=4)
                answer.raise_for_status()
                addresses = [item["data"] for item in answer.json().get("Answer", []) if item.get("type") == 1]
                if not addresses or not all(bot.public_ip(ip) for ip in addresses):
                    return 0, ""
                with urllib3.HTTPSConnectionPool(addresses[0], port=443, assert_hostname=host,
                        server_hostname=host, timeout=4, retries=False) as pool:
                    response = pool.urlopen("GET", "/health", headers={"Host": host}, redirect=False)
                    return response.status, response.data[:128].decode("utf-8", errors="replace").strip()
            except Exception:
                return 0, ""
        except requests.RequestException:
            return 0, ""

    def health(self, base):
        status, body = self.probe(base)
        return status == 200 and body == "ok"

    def tunnel_ready(self, base):
        # Origin 502/503 is expected while the local bot has not started yet.
        return self.probe(base)[0] in (200, 502, 503)

    def port_in_use(self):
        with socket.socket() as connection:
            connection.settimeout(1)
            return connection.connect_ex(("127.0.0.1", self.port)) == 0

    def restore_owned_route(self):
        """Recover a previous crash without replacing another application's route."""
        token, backup = self.config.get("LINE_CHANNEL_ACCESS_TOKEN"), self.config.get("W5_WEBHOOK_URL")
        if not token or not backup:
            raise RuntimeError("請先完成 LINE 金鑰與 W5 備援設定。")
        data = json.loads(bot.read_http("https://api.line.me/v2/bot/channel/webhook/endpoint", timeout=8,
            headers={"Authorization": "Bearer " + token}))
        current = data.get("endpoint")
        if current == backup:
            return
        if self.base and current == self.base + "/webhook":
            bot.restore_webhook(token, backup)
            LOG.info("已將上一次本機連線安全交回待辦備援。")
            return
        raise RuntimeError("目前 Webhook 不屬於本專案的本機或備援，已停止，沒有覆寫其他程式。")

    def stop_previous_tunnel(self):
        if not self.pid_path.exists():
            return
        try:
            pid = json.loads(self.pid_path.read_text())["pid"]
            if not isinstance(pid, int) or pid <= 1:
                raise ValueError("Invalid pid")
            result = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=3)
            if result.returncode:
                return
            if not owned_tunnel(result.stdout.strip(), self.port):
                raise RuntimeError("通道程序與本專案不符，已停止，沒有關閉其他程式。")
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            raise RuntimeError("通道紀錄無法確認，已停止，沒有關閉其他程式。") from None

    def open_tunnel(self):
        executable = shutil.which("cloudflared")
        if not executable:
            raise RuntimeError("找不到 cloudflared，請先安裝官方通道工具。")
        self.stop_previous_tunnel()
        log = self.root / "data/managed-tunnel.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("w") as output:
            self.tunnel = subprocess.Popen([executable, "tunnel", "--url", f"http://127.0.0.1:{self.port}", "--no-autoupdate"],
                stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        bot.private_json(self.pid_path, dict(pid=self.tunnel.pid))
        deadline = time.monotonic() + 45
        while not self.stop.is_set() and time.monotonic() < deadline:
            if self.tunnel.poll() is not None:
                raise RuntimeError("HTTPS 通道未能啟動；詳細紀錄僅保存在本機。")
            text = log.read_text()
            urls = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", text)
            if urls and "Registered tunnel connection" in text and self.tunnel_ready(urls[-1]):
                if self.stop.wait(2):
                    raise RuntimeError("通道啟動已取消。")
                self.base = urls[-1]
                self.config["PUBLIC_BASE_URL"] = self.base
                set_key(self.root / ".env", "PUBLIC_BASE_URL", self.base)
                (self.root / ".env").chmod(0o600)
                LOG.info("HTTPS 通道已建立，設定已同步；網址不輸出至日誌。")
                return
            self.stop.wait(0.5)
        raise RuntimeError("HTTPS 通道尚未就緒，沒有切換 LINE Webhook。")

    def start_bot(self):
        environment = dict(os.environ)
        environment.update({k: v for k, v in self.config.items() if v is not None})
        environment.setdefault("ENABLE_REMINDERS", "0")
        self.child = subprocess.Popen([sys.executable, "-u", str(self.root / "line_bot_local.py")],
            cwd=self.root, env=environment, start_new_session=True)
        deadline = time.monotonic() + 25
        while not self.stop.is_set() and time.monotonic() < deadline:
            if self.child.poll() is not None:
                raise RuntimeError("Bot 啟動未完成，請看上方檢查結果。")
            if self.health(f"http://127.0.0.1:{self.port}") and self.health(self.base):
                if self.config.get("APPS_SCRIPT_RELAY_MODE") == "1":
                    stamp = str(int(time.time()))
                    key = self.config.get("APPS_SCRIPT_RELAY_KEY", "")
                    signature = base64.b64encode(hmac.new(key.encode(), (stamp + "\n" + self.base).encode(), hashlib.sha256).digest()).decode()
                    # Apps Script ContentService redirects to its Google content host.
                    response = requests.post(self.config["W5_WEBHOOK_URL"], timeout=(5, 20),
                        json=dict(action="registerLocalRelay", timestamp=stamp, base=self.base, signature=signature))
                    if response.status_code != 200 or response.content.strip() != b"relay registered":
                        raise RuntimeError("Apps Script 未確認通道更新；保留雲端入口，停止本次啟動。")
                    LOG.info("Apps Script 已確認本機轉送通道更新。")
                # The child verifies its Webhook before it starts serving health.
                LOG.info("本機、公開 HTTPS 與 LINE Webhook 均已就緒。")
                return
            self.stop.wait(1)
        raise RuntimeError("Bot 尚未通過本機及公開連線檢查。")

    def stop_children(self):
        if self.child and self.child.poll() is None:
            self.child.send_signal(signal.SIGINT)
            # Give received messages and Webhook restoration time to finish.
            while self.child.poll() is None:
                try:
                    self.child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    LOG.info("正在等待已接收訊息及 Webhook 回復完成；不強制中斷寫入。")
        if self.tunnel and self.tunnel.poll() is None:
            self.tunnel.terminate()
            try:
                self.tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:
                LOG.warning("通道尚在結束中，沒有強制關閉其他程序。")

    def run(self):
        if self.port_in_use():
            raise RuntimeError("連接埠已有程式，請先在原 bot 終端按 Ctrl+C；沒有啟動第二個 bot。")
        failures = 0
        for attempt in range(3):
            if self.stop.is_set():
                return
            try:
                self.restore_owned_route()
                self.open_tunnel()
                self.start_bot()
                failures = 0
                while not self.stop.wait(20):
                    if self.child.poll() is not None or self.tunnel.poll() is not None:
                        raise RuntimeError("Bot 或通道已中斷。")
                    failures = 0 if self.health(self.base) else failures + 1
                    if failures >= 3:
                        raise RuntimeError("公開通道連續三次未通過檢查。")
                return
            except Exception as error:
                if isinstance(error, RuntimeError):
                    LOG.error("%s", error)
                LOG.error("本次連線未就緒，先停止本機並確認備援，再嘗試重建。")
                self.stop_children()
                if self.stop.is_set():
                    return
                if attempt == 2:
                    raise RuntimeError("三次恢復仍未成功，已停止重試；請檢查網路與上方狀態。") from None
                self.stop.wait(5)
            finally:
                self.stop_children()


def main():
    os.chdir(ROOT)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [Service] %(message)s", datefmt="%H:%M:%S")
    try:
        service = Service(dotenv_values(ROOT / ".env"))
    except (ValueError, TypeError):
        LOG.error("設定格式不正確；PORT 請使用 1 到 65535 的整數。")
        return 1
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: service.stop.set())
    (ROOT / "data").mkdir(exist_ok=True)
    with (ROOT / "data/service.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            LOG.error("已有一個連線管理程序，不重複啟動。")
            return 1
        try:
            service.run()
            return 0
        except Exception as error:
            if isinstance(error, RuntimeError):
                LOG.error("%s", error)
            LOG.error("服務尚未就緒；請檢查設定、網路及上方訊息，私人設定不會輸出。")
            return 1
        finally:
            service.stop_children()


if __name__ == "__main__":
    raise SystemExit(main())
