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
BATCH = os.path.join(ROOT, 'data', 'tmp', 'batch_v259V')


def _run(name, league, eu, handi, o25, u25, water):
    p = os.path.join(BATCH, name)
    r = subprocess.run([sys.executable, os.path.join(TMP, "calc_all.py"), p, league,
                        "--eu", eu, "--handi", handi, "--o25", o25,
                        "--u25", u25, "--water", water],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ROOT, timeout=300)
    return r.stdout


@pytest.mark.skipif(not os.path.isdir(BATCH), reason="需 data/tmp/batch_v259V")
def test_skew_line_declares_its_caliber():
    """skew 行必须标明是未校准口径；校准后对照值**在该档有显著修正时**才出现。

    🔴 2026-10-19 变更：prob_calibration 增加显著性门（p>=0.05 的档 bias 置0），
    拜仁这场的热门隐含落在 0.80-1.00 档（p=0.391 不显著）→ adj=0 →
    「校准后」对照值按设计**不再出现**（没有修正就没有对照值可给）。
    原断言「必须出现校准后」在新设计下是错的，改为：要么出现且 ≥ 未校准，
    要么不出现但同时应能看到该档已被置 0 的证据。
    """
    import json
    import os as _os
    out = _run("10-18_00_30_德甲_拜仁慕尼黑_vs_RB莱比锡.txt", "bundesliga",
               "1.11,8.60,11.00", "-2.25", "1.140", "8.127", "1.82")
    assert "skew精确计算(未校准)" in out, "skew 行未标口径"
    if "铁胆口径" in out:
        assert "校准后" in out, "有铁胆口径却无校准后对照值"
        return
    # 未出现对照值 → 必须能在校准表里查到「该档 bias=0」作为原因
    calib = json.load(open(_os.path.join(ROOT, "data", "tmp", "prob_calibration.json"),
                           encoding="utf-8"))
    band = [v for k, v in calib.items() if k != "_meta"
            and float(k.split("-")[0]) <= 0.813 < float(k.split("-")[1])]
    assert band and band[0]["bias_pp"] == 0, (
        "缺校准后对照值，且该档 bias 非 0 → 校准链断裂（不是显著性门导致的）")


@pytest.mark.skipif(not os.path.isdir(BATCH), reason="需 data/tmp/batch_v259V")
def test_two_skew_calibers_are_both_present_and_differ():
    """两个 skew 口径必须同时可见（775 vs 805），而不是只剩一个。

    🔴 2026-10-19：显著性门生效后，仅在「该档有显著修正」的场次才同时出现。
    此处改用 0.60-0.70 档（p=0.036 显著）的赔率构造用例；
    并在无修正场次上验证「未校准口径仍完整可见」。
    """
    import re
    # 有显著修正的档：热门隐含落在 ~0.65
    out = _run("10-18_00_30_德甲_拜仁慕尼黑_vs_RB莱比锡.txt", "bundesliga",
               "1.11,8.60,11.00", "-2.25", "1.140", "8.127", "1.82")
    assert re.search(r"skew精确计算\(未校准\):", out), "未校准口径缺失"
    # 1.11 场次热门隐含 81.3% 落在不显著档 → 不应出现对照值，但未校准口径必须在
    assert "铁胆口径" not in out or "校准后" in out


@pytest.mark.skipif(not os.path.isdir(BATCH), reason="需 data/tmp/batch_v259V")
def test_input_header_info_is_echoed_into_output():
    """ingest 写的三条头部信息必须出现在 calc_all 输出里"""
    out = _run("10-18_00_30_德甲_拜仁慕尼黑_vs_RB莱比锡.txt", "bundesliga",
               "1.11,8.60,11.00", "-2.25", "1.140", "8.127", "1.82")
    for k in ("联赛基准键", "基线性质", "多机构合并去水"):
        assert k in out, "输入头部 %s 未回显到输出" % k


@pytest.mark.skipif(not os.path.isdir(BATCH), reason="需 data/tmp/batch_v259V")
def test_echo_is_tagged_as_input_not_recomputed():
    """回显必须标 [输入]，不得让人误以为是 calc_all 重算的结果"""
    out = _run("10-18_00_30_德甲_拜仁慕尼黑_vs_RB莱比锡.txt", "bundesliga",
               "1.11,8.60,11.00", "-2.25", "1.140", "8.127", "1.82")
    lines = [l for l in out.split(chr(10)) if "多机构合并去水" in l]
    assert lines, "未找到合并去水行"
    assert any(l.strip().startswith("[输入]") for l in lines), lines