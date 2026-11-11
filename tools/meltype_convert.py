"""Meltype（Linux の配布物）で、ローマ字の文を変換する（一般的な IME との比べ用。測るだけで配らない）。

Meltype の linux/tests/test_daemon.py と同じやり方: 自前の IBus を立て、合成の入力欄にキーを送る。
1 文ごとに: 入力欄を空にする → ローマ字を 1 字ずつ送る → Space → Enter → 確定した文字を読む。
設定は既定のまま（config.json を書かない）。学習は一時の置き場で、組ごとに新しい。

    xvfb-run -a dbus-run-session -- python3 meltype_convert.py PACKAGE in.tsv out.tsv
in.tsv の 1 列目がローマ字。out.tsv は「ローマ字<TAB>出力<TAB>出力」（mine_mistakes.py の形）。
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

package, src, dst = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
root = Path(tempfile.mkdtemp(prefix="meltype-measure-"))
for var, leaf in (("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"), ("XDG_CONFIG_HOME", "config"),
                  ("XDG_RUNTIME_DIR", "runtime"), ("MELTYPE_DATA_DIR", "settings")):
    (root / leaf).mkdir(mode=0o700)
    os.environ[var] = str(root / leaf)
sock = root / "ibus.socket"
os.environ["IBUS_ADDRESS"] = "unix:path=" + str(sock)

import gi  # noqa: E402
gi.require_version("IBus", "1.0")
from gi.repository import GLib, IBus  # noqa: E402

IBus.init()
procs = []
for cmd, log in ((["ibus-daemon", "-s", "-p", "disable", "-c", "disable", "-E", "disable", "-a",
                   os.environ["IBUS_ADDRESS"], "--cache=none", "--timeout=3000"], "daemon.log"),):
    procs.append(subprocess.Popen(cmd, stdout=open(root / log, "wb"), stderr=subprocess.STDOUT, start_new_session=True))
ctx_main = GLib.MainContext.default()


def pump(sec=0.0):
    end = time.monotonic() + sec
    while True:
        for p in procs:
            if p.poll() is not None:
                print((root / "product.log").read_text(errors="replace")[-3000:] if (root / "product.log").exists() else "")
                raise SystemExit(f"止まった: {p.args[0]} {p.returncode}")
        while ctx_main.pending():
            ctx_main.iteration(False)
        if time.monotonic() >= end:
            return
        time.sleep(0.002)


def wait_for(pred, what, timeout=20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        pump(0.01)
    if what:
        raise SystemExit("待ちきれない: " + what)
    return False


wait_for(sock.exists, "IBus の口")
bus = IBus.Bus()
wait_for(bus.is_connected, "IBus への接続")
procs.append(subprocess.Popen([sys.executable, str(package / "ibus-engine-meltype")],
                              stdout=open(root / "product.log", "wb"), stderr=subprocess.STDOUT, start_new_session=True))
context = bus.create_input_context("meltype-measure")
context.set_capabilities(IBus.Capabilite.PREEDIT_TEXT | IBus.Capabilite.AUXILIARY_TEXT |
                         IBus.Capabilite.LOOKUP_TABLE | IBus.Capabilite.FOCUS | IBus.Capabilite.SURROUNDING_TEXT)
st = {"doc": "", "pre": ""}


def committed(_c, text):
    st["doc"] += text.get_text()
    st["pre"] = ""


def preedit(_c, text, _cur, visible, *_m):
    st["pre"] = text.get_text() if visible else ""


context.connect("commit-text", committed)
context.connect("update-preedit-text", preedit)
context.connect("update-preedit-text-with-mode", preedit)
context.connect("hide-preedit-text", lambda _c: st.update(pre=""))
context.focus_in()
pump(0.05)


def select():
    context.set_engine("meltype")
    pump(0.1)
    d = context.get_engine()
    return d is not None and d.get_name() == "meltype"


wait_for(select, "Meltype の登録", 60)
context.focus_in()
pump(0.05)


def key(kv, ch=None):
    used = context.process_key_event(kv, 0, 0)
    pump(0.003)
    if not used and ch is not None:
        st["doc"] += ch
    context.set_surrounding_text(IBus.Text.new_from_string(st["doc"]), len(st["doc"]), len(st["doc"]))


rows = [l.rstrip("\n").split("\t", 1)[0] for l in open(src, encoding="utf-8") if l.strip() and not l.startswith("#")]
t0 = time.monotonic()
with open(dst, "w", encoding="utf-8", newline="\n") as f:
    for i, r in enumerate(rows):
        context.reset()
        pump(0.01)
        st.update(doc="", pre="")
        context.set_surrounding_text(IBus.Text.new_from_string(""), 0, 0)
        for ch in r:
            key(IBus.unicode_to_keyval(ch), ch)
        wait_for(lambda: st["pre"] != "", None, 2)
        before = st["pre"]
        key(IBus.KEY_space)
        wait_for(lambda: st["pre"] != before or st["doc"] != "", None, 3)
        pump(0.05)
        key(IBus.KEY_Return)
        wait_for(lambda: st["pre"] == "", None, 3)
        pump(0.01)
        out = st["doc"]
        f.write(f"{r}\t{out}\t{out}\n")
        if i < 3 or i % 200 == 0:
            print(i, f"{time.monotonic() - t0:.0f}s", repr(out[:30]), flush=True)
for p in reversed(procs):
    try:
        os.killpg(p.pid, 15)
    except ProcessLookupError:
        pass
print("done", len(rows))
