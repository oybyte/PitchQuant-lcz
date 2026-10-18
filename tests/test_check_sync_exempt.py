# -*- coding: utf-8 -*-
r"""check_sync 精简版豁免边界 回归测试（2026-10-17）。

已复现缺陷:
  精简版判定靠「体量 + 标志小节」**启发式猜测**：
    _is_lite() = AGENTS.md 不含「备份铁则/欧战六项核查表/负载缓解…」任一项
  一旦判为精简版，所有 doc_only 检查缺失都变成 SKIP。

  实测: 从 AGENTS.md 删掉**公开版本应存在**的核心铁律「弱共识」后，
        check_sync 输出「⏭️ SKIP: 公开精简版未收录该小节」，
        FAIL 数 0，退出码 0 —— 真实的规则丢失被静默吞掉。

修复目标:
  · edition: lite 标记显式声明「我是精简版」，不再靠体量猜
  · 豁免项走**白名单**：白名单内缺失 → SKIP；白名单外缺失 → FAIL
"""
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, "scripts", "tmp")
SCRIPT = os.path.join(TMP, "check_sync.py")
AGENTS = os.path.join(ROOT, "AGENTS.md")


def run():
    return subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=ROOT, timeout=240)


def src():
    return open(SCRIPT, encoding="utf-8").read()


# ══════════ 1. edition 标记必须存在且被读取 ══════════
def test_agents_declares_lite_edition():
    """公开版 AGENTS.md 必须显式声明 edition，不再靠体量猜测。"""
    txt = open(AGENTS, encoding="utf-8").read()
    assert "<!-- edition:" in txt, (
        "AGENTS.md 缺 edition 声明；精简版判定仍在靠体量猜，误删小节无法被发现")


def test_check_sync_reads_edition_marker():
    """check_sync 必须读 edition 标记，而不是只按体量猜。"""
    s = src()
    assert "edition" in s.lower(), "check_sync 未读取 edition 标记"


# ══════════ 2. 白名单：白名单外缺失必须 FAIL ══════════
def test_exempt_whitelist_exists():
    """必须存在显式豁免白名单，而不是「任何缺失都放过」。"""
    s = src()
    assert re.search(r"_LITE_EXEMPT|_EXEMPT", s), "缺豁免白名单常量"


# 公开版**真实拥有**的核心规则（删掉必须被抓到）。注意区分:
#   · 「弱共识门限单一真源」= 公开版实有（AGENTS §5 第 11 条）
#   · 「弱共识场平局并列铁律」= 完整版小节全称，公开版从未收录 → 豁免正确
CORE_RULES = [
    ("弱共识门限单一真源", "公开版 AGENTS §5 第 11 条"),
    ("跨机构分歧", "公开版 AGENTS §5 第 12 条"),
]


@pytest.mark.parametrize("rule,where", CORE_RULES)
def test_deleting_core_rule_is_caught(rule, where):
    """删掉公开版应有的核心规则 → 必须 FAIL（盲区的直接判据）。"""
    bak = AGENTS + ".tcbak"
    shutil.copy(AGENTS, bak)
    try:
        txt = open(AGENTS, encoding="utf-8").read()
        assert rule in txt, "前置条件：AGENTS.md 应含「%s」（%s）" % (rule, where)
        open(AGENTS, "w", encoding="utf-8").write(txt.replace(rule, "XX" + rule[2:]))
        r = run()
        fails = [l for l in r.stdout.splitlines() if l.strip().startswith("❌")]
        assert r.returncode != 0 or fails, (
            "删掉核心规则「%s」后仍全绿——盲区未封堵\n" % rule
            + "\n".join(l for l in r.stdout.splitlines() if rule[:4] in l))
    finally:
        shutil.move(bak, AGENTS)


def test_whitelisted_absence_still_skips():
    """白名单内的完整版专属小节缺失 → 仍应 SKIP（不误报为失败）。"""
    r = run()
    assert r.returncode == 0, "白名单内缺失不应导致失败: rc=%d" % r.returncode
    m = re.search(r"⏭️\s*(\d+)", r.stdout)
    assert m and int(m.group(1)) > 0, "白名单内缺失应记 SKIP: " + r.stdout[-500:]


# ══════════ 3. 完整版必须全查 ══════════
def test_full_edition_does_not_skip_on_lite_grounds():
    """若标记改为 full，则不允许出现「精简版未收录」类 SKIP。"""
    bak = AGENTS + ".tfbak"
    shutil.copy(AGENTS, bak)
    try:
        txt = open(AGENTS, encoding="utf-8").read()
        patched = re.sub(r"<!-- edition:\s*\w+\s*-->", "<!-- edition: full -->", txt)
        open(AGENTS, "w", encoding="utf-8").write(patched)
        r = run()
        lite_skips = [l for l in r.stdout.splitlines()
                      if "SKIP" in l and "精简版" in l]
        assert not lite_skips, (
            "标记为 full 时仍出现「精简版未收录」SKIP —— 说明判定没走标记:\n"
            + "\n".join(lite_skips[:5]))
    finally:
        shutil.move(bak, AGENTS)
