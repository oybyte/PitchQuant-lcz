# -*- coding: utf-8 -*-
"""校准作用方向回归（2026-10-18·重跑审计发现）

缺陷：prob_calibration 表的语义是「热门方向低估修正」（按隐含概率分档），
但原实现写死 `ph = prob.get("胜", 0)` —— 只对**主胜**做校准。

后果：当**客胜/平局是热门**时（本批 12/26 场），校准对象错位
（拿主胜的 20% 去查表），真正的热门方向完全未修正。
"""
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')
BATCH = os.path.join(ROOT, 'data', 'tmp', 'batch_v259V')


def _run(name, league, eu, handi, o25, u25, water):
    r = subprocess.run([sys.executable, os.path.join(TMP, "calc_all.py"),
                        os.path.join(BATCH, name), league,
                        "--eu", eu, "--handi", handi, "--o25", o25,
                        "--u25", u25, "--water", water],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ROOT, timeout=300)
    return r.stdout


@pytest.mark.skipif(not os.path.isdir(BATCH), reason="需 data/tmp/batch_v259V")
def test_calibration_labels_the_actual_hottest_direction():
    """校准行必须写明它作用在哪个方向，而不是恒说「主胜」"""
    out = _run("10-17_19_30_英超_埃弗顿_vs_切尔西.txt", "epl",
               "2.55,3.73,2.20", "0.25", "1.623", "2.606", "1.84")
    m = re.search(r"校准后热门方向\((\S+?)\)概率", out)
    assert m, "校准行缺少方向标注: " + out[-600:]
    # 该场客胜隐含 40.8% 为最高 → 应标（负）
    assert m.group(1) == "负", "热门方向应为客胜(负)，实得 %s" % m.group(1)


@pytest.mark.skipif(not os.path.isdir(BATCH), reason="需 data/tmp/batch_v259V")
def test_home_favorite_still_calibrated():
    """主胜为热门时照常校准（防修坏）"""
    out = _run("10-18_00_30_德甲_拜仁慕尼黑_vs_RB莱比锡.txt", "bundesliga",
               "1.11,8.60,11.00", "-2.25", "1.140", "8.127", "1.82")
    m = re.search(r"校准后热门方向\((\S+?)\)概率", out)
    assert m and m.group(1) == "胜", out[-600:]


@pytest.mark.skipif(not os.path.isdir(BATCH), reason="需 data/tmp/batch_v259V")
def test_calibration_present_for_every_match():
    """26/26 场都要有校准行（原先客胜热门场次整段缺失）"""
    files = [f for f in sorted(os.listdir(BATCH))
             if f.endswith(".txt") and not f.endswith(".pin.txt")]
    assert files
    missing = []
    for f in files:
        t = open(os.path.join(BATCH, f), encoding="utf-8").read()
        if "校准后热门方向" not in t:
            missing.append(f)
    # 输入 txt 本身不含校准行（由 calc_all 产出），故这里查 out 目录
    out_dir = os.path.join(BATCH, "out")
    if not os.path.isdir(out_dir):
        pytest.skip("缺 out 目录")
    missing = []
    for f in files:
        t = open(os.path.join(out_dir, f), encoding="utf-8").read()
        if "校准后热门方向" not in t:
            missing.append(f)
    assert not missing, "缺校准行: %s" % missing[:3]