"""jieba 兜底安装：某些环境里 pip 编译不了 jieba 的源码包，用这个脚本直接解压安装。

用法：
    .venv\\Scripts\\python scripts\\install_jieba.py

它做三件事：
    1. 在 wheels/ 里找 jieba 的源码包，没有就下载；
    2. 把压缩包里的 jieba/ 目录解压到虚拟环境的 site-packages；
    3. 写一个最小 dist-info，让 pip 认为它已经装好了。
"""

from __future__ import annotations

import html
import re
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
ROOT = Path(__file__).resolve().parent.parent
WHEELS = ROOT / "wheels"


def download_sdist() -> Path:
    WHEELS.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(f"{MIRROR}/jieba/", timeout=30) as resp:
        page = resp.read().decode("utf-8", "ignore")
    links = re.findall(r'href="([^"]+\.tar\.gz)(?:#[^"]*)?"', page)
    if not links:
        raise RuntimeError("镜像里没找到 jieba 的源码包")
    url = links[-1]
    if url.startswith("../"):
        url = MIRROR.rsplit("/simple", 1)[0] + url[2:]
    elif url.startswith("/"):
        url = MIRROR.split("/simple")[0] + url
    name = html.unescape(url.rsplit("/", 1)[-1].split("#")[0])
    dst = WHEELS / name
    if not dst.exists():
        print(f"下载 {name} ...")
        urllib.request.urlretrieve(url, dst)
    return dst


def main() -> int:
    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    if not site_packages.exists():
        print(f"x 找不到 site-packages：{site_packages}")
        print("  请用虚拟环境里的 python 运行本脚本：.venv\\Scripts\\python scripts\\install_jieba.py")
        return 1

    sdist = next(iter(WHEELS.glob("jieba-*.tar.gz")), None) or download_sdist()
    print(f"使用源码包：{sdist.name}")

    dst = site_packages / "jieba"
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir()

    count = 0
    with tarfile.open(sdist) as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            parts = member.name.split("/")
            # 只取 <jieba-x.y>/jieba/... 里面的文件
            if len(parts) < 3 or parts[1] != "jieba":
                continue
            target = dst.joinpath(*parts[2:])
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as src, target.open("wb") as out:  # type: ignore[union-attr]
                shutil.copyfileobj(src, out)
            count += 1

    version = sdist.name.split("-")[1].replace(".tar.gz", "")
    dist_info = site_packages / f"jieba-{version}.dist-info"
    dist_info.mkdir(exist_ok=True)
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: jieba\nVersion: {version}\n", encoding="utf-8"
    )
    (dist_info / "INSTALLER").write_text("manual\n", encoding="utf-8")

    print(f"✅ 已安装 jieba {version}：{count} 个文件 -> {dst}")
    print("   验证：.venv\\Scripts\\python -c \"import jieba; print(jieba.__version__)\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
