"""Mozkey の Zenz（AI）を Linux で動かすためのつなぎ（一般的な IME との比べ。測るだけ）。

Mozkey の変換は Zenz の問い合わせを UNIX ソケット（/tmp/mozc_zenz_<uid>/scorer.sock）へ送る
（src/session/zenz_unix_socket_client.cc、macOS で使う道）。macOS ではそれを受けるのが
mozc_zenz_scorer（src/zenz_scorer、macOS でしか組めない）で、llama-server に /completion で問い合わせる。
この台本は、その mozc_zenz_scorer と同じことをする:
  - 受け口: src/zenz/zenz_wire_protocol.h の形（ZNZ1、要求の頭 24 バイト、答えの頭 28 バイト）
  - llama-server への問い合わせ: src/zenz_scorer/llama_http_client.cc の BuildJsonBody と同じ中身
    （temperature 0、top_k 1、止める記号 U+EE00〜U+EE0F と改行。n_predict は 64 と出力の上限の小さい方、4 以上）
  - 出力の整え: CleanGeneratedText と同じ（止める記号で切り、前後の空白を除き、上限の文字数に切る）

  python3 mozkey_zenz_bridge.py --url http://127.0.0.1:18080/completion [--log bridge.log]
"""
import argparse
import json
import os
import socket
import struct
import time
import urllib.error
import urllib.request

MAGIC = 0x315A4E5A
VERSION = 1
KIND_REQUEST = 1
KIND_RESPONSE = 2
STATUS_OK, STATUS_ERROR, STATUS_TIMEOUT = 0, 1, 2
REQ = struct.Struct("<IHHIIII")
RESP = struct.Struct("<IHHIIIII")
DEFAULT_N_PREDICT = 64
MAX_N_PREDICT = 256
DEFAULT_MAX_OUTPUT_CHARS = 128
STOPS = [chr(0xEE00 + i) for i in range(16)] + ["<s>", "</s>", "<unk>", "<|endoftext|>", "\r", "\n"]


def clean(text, max_chars):
    end = len(text)
    for m in STOPS:
        i = text.find(m)
        if i >= 0:
            end = min(end, i)
    text = text[:end].strip(" \t\r\n\f\v")
    return text[:max_chars]


def complete(url, prompt, timeout_msec, max_chars):
    n_predict = max(4, min(max(4, min(DEFAULT_N_PREDICT, MAX_N_PREDICT)), max_chars))
    body = {
        "prompt": prompt, "n_predict": n_predict, "temperature": 0.0, "top_k": 1, "top_p": 1.0,
        "stream": False, "cache_prompt": True, "stop": [chr(0xEE00 + i) for i in range(16)] + ["\n", "\r"],
    }
    req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=max(timeout_msec / 1000.0, 0.05)) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
    except (TimeoutError, socket.timeout):
        return STATUS_TIMEOUT, "", "llama_http_timeout"
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), (TimeoutError, socket.timeout)):
            return STATUS_TIMEOUT, "", "llama_http_timeout"
        return STATUS_ERROR, "", f"llama_http_error: {e}"
    except Exception as e:  # noqa: BLE001
        return STATUS_ERROR, "", f"llama_http_error: {e}"
    text = clean(data.get("content", ""), max_chars)
    if not text:
        return STATUS_ERROR, "", "empty_generation"
    return STATUS_OK, text, "ok"


def read_exact(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise EOFError
        buf += chunk
    return buf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:18080/completion")
    ap.add_argument("--log", default="")
    a = ap.parse_args()
    d = f"/tmp/mozc_zenz_{os.geteuid()}"
    os.makedirs(d, mode=0o700, exist_ok=True)
    os.chmod(d, 0o700)
    path = os.path.join(d, "scorer.sock")
    if os.path.exists(path):
        os.unlink(path)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    os.chmod(path, 0o600)
    srv.listen(8)
    log = open(a.log, "a", encoding="utf-8") if a.log else None
    print(f"[bridge] {path} -> {a.url}", flush=True)
    while True:
        conn, _ = srv.accept()
        started = time.perf_counter()
        try:
            magic, version, kind, gen, timeout_msec, max_chars, size = REQ.unpack(read_exact(conn, REQ.size))
            prompt = read_exact(conn, size).decode("utf-8", errors="replace")
            if magic != MAGIC or version != VERSION or kind != KIND_REQUEST:
                status, value, debug = STATUS_ERROR, "", "bad_header"
            else:
                max_chars = max(1, min(max_chars or DEFAULT_MAX_OUTPUT_CHARS, 1024))
                status, value, debug = complete(a.url, prompt, timeout_msec, max_chars)
            ms = int((time.perf_counter() - started) * 1000)
            v, dbg = value.encode("utf-8"), debug.encode("utf-8")
            conn.sendall(RESP.pack(MAGIC, VERSION, KIND_RESPONSE, gen, status, ms, len(v), len(dbg)) + v + dbg)
            if log:
                log.write(json.dumps({"gen": gen, "status": status, "ms": ms, "timeout": timeout_msec,
                                      "debug": debug}, ensure_ascii=False) + "\n")
                log.flush()
        except Exception as e:  # noqa: BLE001
            if log:
                log.write(json.dumps({"error": str(e)}) + "\n")
                log.flush()
        finally:
            conn.close()


if __name__ == "__main__":
    main()
