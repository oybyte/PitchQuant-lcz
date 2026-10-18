# -*- coding: utf-8 -*-
"""输出可观测性回归（2026-10-18·重跑审计发现）

两个真实缺陷：
  ① **同名不同口径的 skew**：calc_match 报「skew精确计算」是未校准去水比，
     铁胆档的 skew 来自 direction_full 且已过 prob_calibration。
     实测拜仁 775% vs 805%，读者会以为有一个错了。
  ② **ingest 写入的三条头部信息静默丢失**：联赛基准键 / 基线性质 / 多机构合并去水
     写进了输入 txt，但 calc_all 输出里完全没有 → 下游代理看不到。
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')
BATCH = os.path.join(ROOT, 'data', 'tmp', 'batch_v259C')


def _run(name, league, eu, handi, o25, u25, water):
    p = os.path.join(BATCH, name)
    r = subprocess.run([sys.executable, os.path.join(TMP, "calc_all.py"), p, league,
                        "--eu", eu, "--handi", handi, "--o25", o25,
                        "--u25", u25, "--water", water],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ROOT, timeout=300)
    return r.stdout


@pytest.mark.skipif(not os.path.isdir(BATCH), reason="需 data/tmp/batch_v259C")
def test_skew_line_declares_its_caliber():
    """skew 行必须标明是未校准口径，并给出校准后对照值"""
    out = _run("10-18_00_30_德甲_拜仁慕尼黑_vs_RB莱比锡.txt", "bundesliga",
               "1.11,8.60,11.00", "-2.25", "1.140", "8.127", "1.82")
    assert "skew精确计算(未校准)" in out, "skew 行未标口径"
    assert "校准后" in out and "铁胆口径" in out, "缺校准后对照值"


@pytest.mark.skipif(not os.path.isdir(BATCH), reason="需 data/tmp/batch_v259C")
def test_two_skew_calibers_are_both_present_and_differ():
    """两个 skew 口径必须同时可见（775 vs 805），而不是只剩一个"""
    import re
    out = _run("10-18_00_30_德甲_拜仁慕尼黑_vs_RB莱比锡.txt", "bundesliga",
               "1.11,8.60,11.00", "-2.25", "1.140", "8.127", "1.82")
    m1 = re.search(r"skew精确计算\(未校准\):.*?= (\d+)%", out)
    m2 = re.search(r"校准后 (\d+)%·铁胆口径", out)
    assert m1 and m2, (m1, m2)
    # 校准后应当不低于未校准（热门低估修正为正向）
    assert int(m2.group(1)) >= int(m1.group(1)), "校准后反低于未校准，修正方向可疑"


@pytest.mark.skipif(not os.path.isdir(BATCH), reason="需 data/tmp/batch_v259C")
def test_input_header_info_is_echoed_into_output():
    """ingest 写的三条头部信息必须出现在 calc_all 输出里"""
    out = _run("10-18_00_30_德甲_拜仁慕尼黑_vs_RB莱比锡.txt", "bundesliga",
               "1.11,8.60,11.00", "-2.25", "1.140", "8.127", "1.82")
    for k in ("联赛基准键", "基线性质", "多机构合并去水"):
        assert k in out, "输入头部 %s 未回显到输出" % k


@pytest.mark.skipif(not os.path.isdir(BATCH), reason="需 data/tmp/batch_v259C")
def test_echo_is_tagged_as_input_not_recomputed():
    """回显必须标 [输入]，不得让人误以为是 calc_all 重算的结果"""
    out = _run("10-18_00_30_德甲_拜仁慕尼黑_vs_RB莱比锡.txt", "bundesliga",
               "1.11,8.60,11.00", "-2.25", "1.140", "8.127", "1.82")
    lines = [l for l in out.split(chr(10)) if "多机构合并去水" in l]
    assert lines, "未找到合并去水行"
    assert any(l.strip().startswith("[输入]") for l in lines), lines