"""AOSP LatinIME の C++ 本体（native/jni）が登録する Java の native 宣言だけの殻を作る（比べの計測用）。

  python3 gen_stubs.py <LatinIME/native/jni> <出力の java フォルダ>
本体は読み込まれたときに 4 つのクラスへ関数を登録し、宣言が欠けると読み込みに失敗する。
登録の表（sMethods）から名前と型を読み、static native の宣言を書く。
"""
import re
import sys
from pathlib import Path

JNI = Path(sys.argv[1])
OUT = Path(sys.argv[2])


def java_type(sig, i):
    dims = 0
    while sig[i] == "[":
        dims += 1
        i += 1
    c = sig[i]
    if c == "L":
        j = sig.index(";", i)
        base = sig[i + 1:j].replace("/", ".")
        i = j + 1
    else:
        base = {"I": "int", "J": "long", "Z": "boolean", "F": "float", "V": "void", "B": "byte",
                "S": "short", "C": "char", "D": "double"}[c]
        i += 1
    return base + "[]" * dims, i


def decl(name, sig):
    args, i, n = [], 1, 0
    while sig[i] != ")":
        t, i = java_type(sig, i)
        args.append(f"{t} a{n}")
        n += 1
    ret, _ = java_type(sig, i + 1)
    return f"    public static native {ret} {name}({', '.join(args)});"


for cpp in sorted(JNI.glob("com_android_inputmethod_*.cpp")):
    t = cpp.read_text(encoding="utf-8")
    cls = re.search(r'kClassPathName = "([^"]+)"', t).group(1)
    methods = re.findall(r'const_cast<char \*>\("(\w+)"\),\s*const_cast<char \*>\("([^"]+)"\)', t)
    pkg, _, name = cls.rpartition("/")
    d = OUT / pkg
    d.mkdir(parents=True, exist_ok=True)
    body = "\n".join(decl(m, s) for m, s in methods)
    (d / f"{name}.java").write_text(f"package {pkg.replace('/', '.')};\n\npublic final class {name} {{\n{body}\n}}\n",
                                    encoding="utf-8")
    print(cls, len(methods))
