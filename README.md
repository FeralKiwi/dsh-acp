# dsh-acp

Minimal Python ACP v1 JSON-RPC client for driving the DeepSeek Harness (`dsh`) agent without a browser.

## Transport

Newline-delimited JSON over stdio — one JSON-RPC object per line. (Content-Length framing gives parse errors from the dsh ACP server.)

## Usage

```
python3 acp_client.py <cwd> "<prompt>"
```

Spawns `dsh --profile acp`, runs `initialize` → `session/new` → `session/prompt`, auto-allows `session/request_permission` requests (prefers allow-style options), prints agent message chunks and tool-call updates, then closes the session.

## Config

`acp-model-patch.yml` — id-targeted profile patch selecting the model/provider for the `acp` profile.

The client reads the API key from the `OPENCODE_GO_KEY` environment variable, falling back to the opencode auth file at `~/.local/share/opencode/auth.json`.

## Verified

End-to-end run: the agent wrote and executed a file via its own tools in ~8s, `stopReason=end_turn`.
