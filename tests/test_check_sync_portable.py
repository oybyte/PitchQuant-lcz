# -*- coding: utf-8 -*-
r"""check_sync.py 公开版可运行性 回归测试（2026-10-17 修复批次）。

已复现缺陷:
  D1 脚本第 31 行就 `open(".reasonix/skills/...")` → FileNotFoundError 崩栈，
     196 条校验中后续 194 条**一条都没跑**。
  D2 `VER = "V3.5.74"` 但 `VER_RE = r"V3\.5\.72"` —— 版本号写死不一致，
     导致「AGENTS.md 含 V3.5.74」恒报 ❌（纯代码 bug，与运行环境无关）。
  D3 存在硬编码本机用户目录 `~/Desktop/足球分析模型.txt`，本身不该入库。
  D4 私有资源缺失时直接抛异常，而不是如实标注「公开版未分发」。

修复目标:
  · 公开版跑得起来，不因缺资源崩栈
  · 输出区分 OK / WARN / FAIL / SKIP 四态，SKIP 必须写原因
  · 退出码：有 FAIL → 1；仅 SKIP → 0
"""
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, "scripts", "tmp")
SCRIPT = os.path.join(TMP, "check_sync.py")
OUTSIDE = os.path.dirname(ROOT)


def run(timeout=180):
    return subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=OUTSIDE,
                          timeout=timeout)


def src():
    return open(SCRIPT, encoding="utf-8").read()


# ══════════ D1: 不得崩栈 ══════════
def test_does_not_crash():
    """公开版（无 .reasonix / 无私有数据）必须跑完，不得 Traceback。"""
    r = run()
    assert "Traceback" not in (r.stdout + r.stderr), (
        "仍崩栈:\n" + (r.stdout + r.stderr)[-900:])
    assert "总结果" in r.stdout, "未跑到总结果（中途退出）:\n" + r.stdout[-900:]


def test_runs_majority_of_checks():
    """崩溃前只有 1-2 条能跑；修复后应执行绝大多数校验。"""
    r = run()
    m = re.search(r"总结果\(含全部校验\): .*?✅\s*(\d+).*?⚠️\s*(\d+).*?❌\s*(\d+)(?:.*?⏭️\s*(\d+))?",
                  r.stdout)
    assert m, "未找到总结果行: " + r.stdout[-500:]
    ok, warn, fail = int(m.group(1)), int(m.group(2)), int(m.group(3))
    skip = int(m.group(4)) if m.group(4) else 0
    assert ok + warn + fail + skip >= 150, (
        "实际执行校验数仅 %d（应 ≥150）——多数校验仍未跑到" % (ok + warn + fail + skip))


# ══════════ D4: SKIP 必须显式且写原因 ══════════
def test_skip_reason_reported():
    """私有资源缺失时应计入 SKIP 并给出原因，而不是失败或静默。"""
    r = run()
    assert "SKIP" in r.stdout or "跳过" in r.stdout, (
        "未区分「公开版未分发」与「真失败」:\n" + r.stdout[-700:])


# ══════════ D2: VER_RE 必须跟随 VER ══════════
def test_version_regex_matches_version_constant():
    """VER 与 VER_RE 不得写死不一致（历史 bug: VER=V3.5.74 而正则写 V3.5.72）。

    行为判据：把脚本里的 VER 与 VER_RE 分别取出来，正则必须匹配 VER 本身。
    """
    code = (
        "import re, sys" + chr(10) +
        "sys.path.insert(0, %r)" % TMP + chr(10) +
        "src = open(%r, encoding='utf-8').read()" % SCRIPT + chr(10) +
        "ns = {}" + chr(10) +
        "for line in src.splitlines():" + chr(10) +
        "    line = line.strip()" + chr(10) +
        "    if line.startswith('VER =') or line.startswith('VER_RE ='):" + chr(10) +
        "        exec(line, {'re': re}, ns)" + chr(10) +
        "print('VER', ns.get('VER'))" + chr(10) +
        "print('MATCH', bool(ns['VER_RE'].search(ns['VER'])))" + chr(10))
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=ROOT, env=env, timeout=120)
    assert "MATCH True" in r.stdout, (
        "VER_RE 匹配不到 VER 自身 → 版本校验必然恒失败: " + r.stdout + r.stderr)


def test_version_check_passes_on_agents():
    """AGENTS.md 确实含 V3.5.74，该条校验不应报 ❌。"""
    s = open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8").read()
    m = re.search(r"VER\s*=\s*['\"](V[\d.]+)['\"]", src())
    if not m:
        pytest.skip("无 VER 常量")
    assert m.group(1) in s, "AGENTS.md 不含 %s，校验失败另有原因" % m.group(1)
    r = run()
    line = [l for l in r.stdout.splitlines() if "AGENTS.md 含" in l]
    assert line, "未输出 AGENTS 版本校验行"
    assert "❌" not in line[0], "AGENTS.md 确实含该版本，不应报失败: " + line[0]


# ══════════ D3: 不得硬编码本机用户目录 ══════════
def test_no_hardcoded_home_directory():
    """`~/Desktop/...` 不得作为**可执行代码**出现（注释里复盘历史是允许的）。"""
    import io
    import tokenize
    parts = []
    with open(SCRIPT, "rb") as f:
        for tok in tokenize.tokenize(f.readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING, tokenize.NL, tokenize.NEWLINE):
                continue
            parts.append(tok.string)
    code = "".join(parts)
    assert "Desktop" not in code, "活代码里仍硬编码本机用户目录"
    assert "expanduser" not in code, "仍使用 expanduser 解析本机路径"


# ══════════ 退出码语义 ══════════
def test_exit_code_zero_when_only_skip():
    """仅有 SKIP（公开版缺资源）时退出码应为 0，不阻塞 CI。"""
    r = run()
    m = re.search(r"❌\s*(\d+)", r.stdout[r.stdout.find("总结果"):]) if "总结果" in r.stdout else None
    fails = int(m.group(1)) if m else 0
    if fails == 0:
        assert r.returncode == 0, "无 FAIL 但退出码非 0: %d" % r.returncode
    else:
        assert r.returncode == 1, "有 FAIL 时退出码应为 1，实得 %d" % r.returncode
