"""把依赖的轮子（wheel）先下载到本地 wheels/ 目录，再离线安装。

为什么需要它？
    有些网络环境（公司代理、国内镜像、离线机器）里 `pip install` 会卡住或失败。
    先手动下载再离线安装，成功率最高，也方便把 wheels/ 拷到别的机器上复用。

用法：
    python scripts/fetch_wheels.py              # 下载 requirements.txt 里的全部轮子
    python scripts/fetch_wheels.py jieba numpy  # 只下载指定包
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
ROOT = Path(__file__).resolve().parent.parent
WHEELS = ROOT / "wheels"

PURE_TAGS = ("py3-none-any", "py2.py3-none-any")
BIN_TAG_RE = re.compile(r"cp312-(?:cp312-)?win_amd64")
VERSION_RE = re.compile(r"-(\d+(?:\.\d+)*)")


def _version_key(name: str) -> tuple[int, ...]:
    m = VERSION_RE.search(name)
    return tuple(int(x) for x in m.group(1).split(".")) if m else (0,)


def fetch(pkg: str, out_dir: Path = WHEELS) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    index_url = f"{MIRROR}/{pkg}/"
    with urllib.request.urlopen(index_url, timeout=30) as resp:
        page = resp.read().decode("utf-8", "ignore")

    links = re.findall(r'href="([^"]+)"[^>]*>([^<]+)</a>', page)
    candidates: list[tuple[str, str]] = []
    for href, text in links:
        href = href.split("#")[0]
        name = html.unescape(text.strip())
        if not name.endswith((".whl", ".tar.gz", ".zip")):
            continue
        candidates.append((name, urljoin(index_url, href)))

    if not candidates:
        print(f"  x {pkg}: 索引里没有可用文件")
        return None

    # 优先级：本机二进制轮子 > 纯 Python 轮子 > 源码包；同级取版本最高的
    binaries = [c for c in candidates if c[0].endswith(".whl") and BIN_TAG_RE.search(c[0])]
    pure = [c for c in candidates if c[0].endswith(".whl") and any(t in c[0] for t in PURE_TAGS)]
    sources = [c for c in candidates if not c[0].endswith(".whl")]
    pool = binaries or pure or sources
    if not pool:
        print(f"  x {pkg}: 没有适合本机的包")
        return None

    name, url = max(pool, key=lambda c: _version_key(c[0]))
    dst = out_dir / name
    if dst.exists() and dst.stat().st_size > 0:
        print(f"  = {name} 已存在")
        return dst
    print(f"  v {name}")
    urllib.request.urlretrieve(url, dst)
    return dst


def _requirement_names() -> list[str]:
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    names = []
    for line in req.splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        names.append(re.split(r"[<>=!~\[ ]", line)[0])
    return names


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument("packages", nargs="*", help="包名，留空则读 requirements.txt")
    args = parser.parse_args()
    packages = args.packages or _requirement_names()

    print(f"目标目录：{WHEELS}")
    for pkg in packages:
        try:
            fetch(pkg)
        except Exception as exc:  # noqa: BLE001
            print(f"  x {pkg}: {exc}")
    print("\n完成。离线安装命令：")
    print(f'  .venv\\Scripts\\python -m pip install --no-index --find-links "{WHEELS}" -r requirements.txt')
    return 0


if __name__ == "__main__":
    sys.exit(main())
