#!/usr/bin/env python3
"""Build a checksum-paired offline 1401 from the matching official app source.

用法（在 src/ 里跑，build-out/ 已由 package-experiment.py 产出配对包）：
    python3 ci/package-test-app.py --tag v2.6.3 [--expect-commit <sha>]

1401 的源码 commit 默认从 ci/1401-pins.json 里按 tag 查；没有记录时用当前
HEAD 并在输出里提示，方便第一次构建某个 tag 后把 commit 补进 pins。
"""
import argparse
import hashlib
import json
from pathlib import Path
import os
import re
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
out = root / "build-out"
app = root / ".deps/1401"

parser = argparse.ArgumentParser()
parser.add_argument("--tag", default=None, help="上游 tag，默认读 ci/upstream-tag")
parser.add_argument("--expect-commit", default=None, help="1401 源码应处的 commit")
args = parser.parse_args()

tag = args.tag or (root / "ci/upstream-tag").read_text().strip()
ver = tag.lstrip("v")

actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=app, text=True).strip()
pins_file = root / "ci/1401-pins.json"
pins = json.loads(pins_file.read_text()) if pins_file.is_file() else {}
expect = args.expect_commit or pins.get(tag)
if expect and actual != expect:
    raise SystemExit(f"Installer source commit mismatch: {actual} != {expect}")
if not expect:
    print(f"note: {tag} 未固定 1401 commit，本次用 {actual}（建议写入 ci/1401-pins.json）")

packages = sorted(out.glob(f"nullmoth-{ver}-*.tar.gz"))
if len(packages) != 1:
    raise SystemExit(f"expected exactly one packaged driver for {ver}, found {len(packages)}")
package = packages[0]
sha = hashlib.sha256(package.read_bytes()).hexdigest()

main = app / "mac/Sources/main.swift"
source = main.read_text()

# 1) 包名：官方的 nullmoth-nvidia-<ver>.tar.gz → 我们打出来的包名
old_name = f'static let name = "nullmoth-nvidia-{ver}.tar.gz"'
assert source.count(old_name) == 1, f"package name literal not found: {old_name}"
source = source.replace(old_name, f'static let name = "{package.name}"')

# 2) 校验和：官方包 sha256 → 我们的包 sha256
m = re.search(r'static let sha256 = "([0-9a-f]{64})"', source)
assert m, "sha256 literal not found"
source = source[:m.start(1)] + sha + source[m.end(1):]

# 3) 标题标出这是 preflight 测试版
source = source.replace('window.title = "1401";',
                        f'window.title = "1401 - BAR Preflight TEST {ver}";', 1)

# 4) 除了 Downloads，也从 app 同级目录找配对包
needle = '        c.append(fm.urls(for: .downloadsDirectory, in: .userDomainMask)[0].appendingPathComponent(Package.name))'
assert source.count(needle) == 1
source = source.replace(needle, needle + '\n        c.append(Bundle.main.bundleURL.deletingLastPathComponent().appendingPathComponent(Package.name))')

# 5) 关掉联网更新：这个 app 只装本地配对包
for old, new in [
    ('case "checkUpdate": checkUpdate()', 'case "checkUpdate": send("upd", ["state": "error", "why": "Offline BAR preflight test: use this paired package; official updates are disabled in the test app."])'),
    ('case "updateDriver": updateDriver(efi: b["efi"] as? String ?? "auto")', 'case "updateDriver": send("upd", ["state": "error", "why": "Use Install the driver with the paired local test archive."])'),
    ('case "updateApp": updateApp()', 'case "updateApp": send("upd", ["state": "error", "why": "This test app does not update itself."])'),
    ('case "download": download()', 'case "download": send("dl", ["state": "error", "why": "Put the paired test tar.gz beside this app or in Downloads, then reopen the app."])'),
]:
    assert source.count(old) == 1, old
    source = source.replace(old, new)
main.write_text(source)


def parallel_swift():
    """让 1401 的整模块优化编译并行跑。

    build.sh 用一次 `swiftc -O <17 个文件>` 编完整个 app，默认是单线程 IRGen，
    在 4 核 runner 上实测占掉这一步 135 秒里的绝大部分。加 -num-threads N 后
    swiftc 会并行生成 IR，产物字节数不变（本机对同一份源码两种方式编出来都是
    14696 字节）。改的是克隆下来的副本，上游仓库不动。
    """
    script = app / "mac/build.sh"
    text = script.read_text()
    if "-num-threads" in text:
        return
    threads = os.cpu_count() or 2
    patched = text.replace("xcrun swiftc -O ", f"xcrun swiftc -O -num-threads {threads} ")
    if patched == text:
        print("note: build.sh 里没有预期的 `xcrun swiftc -O` 调用，跳过 -num-threads")
        return
    script.write_text(patched)
    print(f"note: 1401 用 -num-threads {threads} 并行编译")


def bash_for_build():
    """1401's mac/build.sh needs bash >= 4.4.

    2.6.3 added `RUN=(); [ arm64 ] && RUN=(arch -x86_64)` and then expands
    "${RUN[@]}". On an Intel host RUN stays empty, and bash 3.2 -- the
    /bin/bash every macOS still ships -- treats that as an unbound variable
    under `set -u`, so the build dies at the EFI rule test. Bash 4.4 and
    later expand an empty array to nothing, which is what the author
    intended. Homebrew bash is preferred over the system one for that
    reason; failing loudly beats silently building nothing.
    """
    for candidate in ("/usr/local/bin/bash", "/opt/homebrew/bin/bash", shutil.which("bash"), "/bin/bash"):
        if not candidate or not Path(candidate).is_file():
            continue
        try:
            version = subprocess.check_output([candidate, "-c", "echo ${BASH_VERSION}"], text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            continue
        parts = version.split(".")[:2]
        if len(parts) == 2 and all(p.isdigit() for p in parts) and tuple(map(int, parts)) >= (4, 4):
            print(f"note: building 1401 with {candidate} (bash {version})")
            return candidate
    raise SystemExit(
        "1401 needs bash >= 4.4: /bin/bash on macOS is 3.2 and rejects the empty "
        'array expansion in mac/build.sh under `set -u`. Install one with `brew install bash`.'
    )


parallel_swift()
subprocess.run([bash_for_build(), "mac/build.sh", str(root / "app-build")], cwd=app, check=True)
old_bundle = root / "app-build/1401.app"
bundle = old_bundle.with_name("1401-BAR-Preflight-Test.app")
old_bundle.rename(bundle)
subprocess.run(["codesign", "--verify", "--deep", "--strict", str(bundle)], check=True)
subprocess.run(["xcrun", "lipo", str(bundle / "Contents/MacOS/1401"), "-verify_arch", "x86_64"], check=True)

# 不把不同的 setup/uninstall 助手藏在官方 app 的界面下
for name in ("nullmoth-setup.sh", "nullmoth-uninstall.sh", "NullMothSafe.efi"):
    upstream = subprocess.check_output(["git", "show", f"{actual}:mac/Resources/{name}"], cwd=app)
    assert upstream == (bundle / "Contents/Resources" / name).read_bytes(), name

zipfile = out / f"1401-Mac-{ver}-BAR-Preflight-Test.zip"
subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(bundle), str(zipfile)], check=True)
with (out / "SHA256SUMS.txt").open("a") as sums:
    sums.write(f"{hashlib.sha256(zipfile.read_bytes()).hexdigest()}  {zipfile.name}\n")
(out / "installer-proof.json").write_text(json.dumps({
    "source_commit": actual, "package_sha256": sha,
    "package_name": package.name, "offline_test_app": zipfile.name,
    "official_setup_uninstall_and_efi_helper_preserved": True,
    "hardware_tested": False,
}, indent=2) + "\n")
print(f"Paired offline App built for {tag}; official setup/uninstall helpers preserved.")
