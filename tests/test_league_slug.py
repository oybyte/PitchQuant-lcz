# -*- coding: utf-8 -*-
"""联赛 slug 映射完整性回归（2026-10-18·重跑审计发现）

缺陷：韩K联 被映射到 `china`（中超）的抽水基准。
  · LEAGUE_VIG 只有 japan / china，没有韩国项
  · 两国联赛盘口特征不同，借用中超基准属语义错误
  · 该错误在 26 场批次从未暴露（无韩K联），29 场批次才出现

正确做法：不映射 → 走「未登记」三态，显式标无数据。
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')
BATCH = os.path.join(ROOT, 'data', 'tmp', 'batch_v259V')
sys.path.insert(0, TMP)


def test_korean_league_not_mapped_to_china():
    """韩K联 不得映射到 china（语义错误）"""
    import v259_ingest as M
    assert M.LG_SLUG.get("韩K联") is None, "韩K联 仍被映射到 %r" % M.LG_SLUG.get("韩K联")
    # 中超/日职仍应正常映射（防修坏）
    assert M.LG_SLUG.get("中超") == "china"
    assert M.LG_SLUG.get("日职联") == "japan"


def test_calc_match_alias_has_no_korean():
    """calc_match 内部的 _SLUG_ALIAS 也不得有韩K联"""
    src = open(os.path.join(TMP, 'calc_match.py'), encoding='utf-8').read()
    assert "'韩K联': 'china'" not in src, "calc_match 仍把韩K联映射到 china"


def test_all_slugs_resolve_to_a_vig_key():
    """凡给出 slug 的联赛，该 slug 必须真在 LEAGUE_VIG 中（防悬空映射）"""
    import re
    import v259_ingest as M
    src = open(os.path.join(TMP, 'calc_match.py'), encoding='utf-8').read()
    blk = re.search(r'LEAGUE_VIG = \{(.*?)\}', src, re.S)
    assert blk, '未找到 LEAGUE_VIG'
    keys = set(re.findall(r"'([a-z0-9]+)':", blk.group(1)))
    for cn, slug in M.LG_SLUG.items():
        assert slug in keys, "%s → %s 不在 LEAGUE_VIG 中（悬空映射）" % (cn, slug)


@pytest.mark.skipif(not os.path.isdir(BATCH), reason="需 data/tmp/batch_v259V")
def test_unmapped_league_says_no_data_not_borrowed_baseline():
    """未登记联赛必须标「无数据」，不得借用其他联赛基准"""
    import json
    man = json.load(open(os.path.join(BATCH, '_manifest.json'), encoding='utf-8'))
    kors = [m for m in man if "韩K联" in m["name"]]
    if not kors:
        pytest.skip("本批无韩K联")
    m = kors[0]
    lg = m.get("lg_slug") or m["lg"]
    base = m["name"].replace(" ", "_").replace("(", "").replace(")", "")
    out = subprocess.run(
        [sys.executable, os.path.join(TMP, "calc_all.py"),
         os.path.join(BATCH, base + ".txt"), lg,
         "--eu", m["eu"], "--handi", "%g" % m["handi"],
         "--o25", "%.3f" % m["o25"], "--u25", "%.3f" % m["u25"],
         "--water", "%.3f" % m["water"]],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", cwd=ROOT, timeout=300).stdout
    assert "该联赛未登记" in out, out[-800:]
    assert "反抽水比 不适用(无基准)" in out, out[-800:]