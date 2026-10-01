#!/usr/bin/env python3
"""Minimal ACP v1 JSON-RPC client for `dsh --profile acp` over stdio.

Transport: newline-delimited JSON (one JSON-RPC object per line).

Usage:
    python3 acp_client.py <cwd> "<prompt>"
Spawns the dsh ACP server, creates a session in <cwd>, sends the prompt,
auto-allows permission requests, prints agent updates, and exits with the
final stop reason.
"""
import json
import os
import subprocess
import sys
import threading

PATCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "acp-model-patch.yml")


class AcpClient:
    def __init__(self, proc):
        self.proc = proc
        self._id = 0
        self._lock = threading.Lock()
        self._pending = {}
        threading.Thread(target=self._reader, daemon=True).start()

    def _send(self, obj):
        with self._lock:
            self.proc.stdin.write(json.dumps(obj) + "\n")
            self.proc.stdin.flush()

    def request(self, method, params, timeout=900):
        with self._lock:
            self._id += 1
            rid = self._id
        ev = threading.Event()
        self._pending[rid] = [ev, None]
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        if not ev.wait(timeout):
            raise TimeoutError(f"request {method} timed out")
        _ev, result = self._pending.pop(rid)
        if isinstance(result, dict) and "error" in result:
            raise RuntimeError(f"{method} error: {result['error']}")
        return result.get("result")

    def _reader(self):
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in msg and ("result" in msg or "error" in msg):
                rid = msg["id"]
                if rid in self._pending:
                    self._pending[rid][1] = msg
                    self._pending[rid][0].set()
                continue
            self._handle_incoming(msg)

    def _handle_incoming(self, msg):
        method = msg.get("method", "")
        params = msg.get("params", {}) or {}
        if method == "session/update":
            upd = params.get("update", {})
            kind = upd.get("sessionUpdate", "")
            if kind == "agent_message_chunk":
                content = upd.get("content", {})
                if content.get("type") == "text":
                    print(content.get("text", ""), end="", flush=True)
            elif kind == "agent_thought_chunk":
                pass
            elif kind == "tool_call":
                print(f"\n[tool] {upd.get('kind', '')} {upd.get('title', '')}", flush=True)
            elif kind == "tool_call_update":
                if upd.get("status") in ("completed", "failed"):
                    print(f"[tool {upd['status']}]", flush=True)
        elif method == "session/request_permission":
            options = params.get("options", [])
            chosen = next(
                (o for o in options if str(o.get("kind", "")).startswith("allow")),
                options[0] if options else None,
            )
            print(f"\n[permission auto-allowed: {params.get('title', '')}]", flush=True)
            if chosen:
                result = {"outcome": {"outcome": "selected", "optionId": chosen["optionId"]}}
            else:
                result = {"outcome": {"outcome": "cancelled"}}
            self._send({"jsonrpc": "2.0", "id": msg["id"], "result": result})


def main():
    if len(sys.argv) != 3:
        print("usage: acp_client.py <cwd> <prompt>", file=sys.stderr)
        sys.exit(2)
    cwd, prompt = sys.argv[1], sys.argv[2]
    os.makedirs(cwd, exist_ok=True)
    env = dict(os.environ)
    if "OPENCODE_GO_KEY" not in env:
        auth = json.load(open(os.path.expanduser("~/.local/share/opencode/auth.json")))
        env["OPENCODE_GO_KEY"] = auth["opencode-go"]["key"]
    cmd = ["dsh", "--profile", "acp"]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=sys.stderr, cwd=cwd, env=env,
                            bufsize=1, text=True)
    client = AcpClient(proc)
    init = client.request("initialize", {
        "protocolVersion": 1,
        "clientCapabilities": {"fs": {"readTextFile": True, "writeTextFile": True}, "terminal": False},
        "clientInfo": {"name": "muse-acp-client", "version": "1.0"},
    })
    print(f"[connected]", flush=True)
    sess = client.request("session/new", {"cwd": os.path.abspath(cwd), "mcpServers": []})
    session_id = sess["sessionId"]
    print(f"[session {session_id}]", flush=True)
    result = client.request("session/prompt", {
        "sessionId": session_id,
        "prompt": [{"type": "text", "text": prompt}],
    })
    print(f"\n[done: stopReason={result.get('stopReason')}]", flush=True)
    try:
        client.request("session/close", {"sessionId": session_id}, timeout=60)
    except Exception:
        pass
    proc.terminate()


if __name__ == "__main__":
    main()
