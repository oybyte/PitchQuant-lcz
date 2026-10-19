# -*- coding: utf-8 -*-
"""calc_all → calc_match 参数透传 & 诱阻分类接线 回归测试（2026-10-17 修复批次）。

已复现缺陷（本次 22 场实盘分析发现）:
  D1  calc_all 组 cmd 只拼 txt_path + league，**丢弃了 --eu/--handi/--o25/--u25/--water**
      → calc_match 里所有依赖欧盘的模块恒走降级分支
      → 22/22 场输出「V5跨市场: 未提供欧盘」·C08 必核项脚本侧恒空
  D2  calc_match.trap_classify_output 只有 def、**零调用点**
      → calc_all 打印标题「🔴诱阻分类预计算(...)」后紧跟空行 · C16 恒空
"""
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')
TXT = os.path.join(ROOT, 'tests', 'fixtures', 'lemans-toulouse-F1.txt')
OUTSIDE = os.path.dirname(ROOT)
EU = '2.97,3.48,1.98'


def run_all(extra, timeout=300):
    return subprocess.run(
        [sys.executable, os.path.join(TMP, 'calc_all.py'), TXT, 'F1'] + extra,
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        cwd=OUTSIDE, timeout=timeout)


def run_match(extra, timeout=180):
    return subprocess.run(
        [sys.executable, os.path.join(TMP, 'calc_match.py'), TXT, 'F1'] + extra,
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        cwd=OUTSIDE, timeout=timeout)


# ══════════ D1: --eu 必须到达 calc_match ══════════
def test_calc_all_passes_eu_to_calc_match():
    """calc_all --eu 后，calc_match 段不得再报「未提供欧盘」。"""
    r = run_all(['--eu', EU, '--o25', '2.05', '--handi', '0.25'])
    assert '未提供欧盘' not in r.stdout, (
        "calc_all 未把 --eu 透传给 calc_match（V5 跨市场恒空）:\n"
        + '\n'.join(l for l in r.stdout.splitlines() if 'V5' in l))


def test_calc_all_produces_v5_divergence_block():
    """透传成功后必须真的产出 V5 分歧结论（不是只有标题）。"""
    r = run_all(['--eu', EU, '--o25', '2.05', '--handi', '0.25'])
    hits = [l.strip() for l in r.stdout.splitlines() if 'V5跨市场分歧' in l]
    assert hits, "未产出「V5跨市场分歧」结论行:\n" + r.stdout[-1200:]
    # 必须含有效凯利（跨市场价值判断）
    assert '有效凯利' in hits[0], "V5 行缺有效凯利: " + hits[0]


def test_calc_all_passes_water_to_classifier():
    """--water 经 calc_all 透传后必须影响 match_classifier（低水 1.84 应被识别）。"""
    r = run_all(['--eu', EU, '--o25', '2.05', '--handi', '0.25', '--water', '1.84'])
    assert '低水1.84' in r.stdout, "水位信号未到达 match_classifier: " + r.stdout[-800:]


# ══════════ D2: 诱阻分类必须真的被调用 ══════════
def test_trap_classify_has_real_call_site():
    """trap_classify_output 必须有调用点（存在≠活跃）。"""
    src = open(os.path.join(TMP, 'calc_match.py'), encoding='utf-8').read()
    calls = [m.start() for m in re.finditer(r'trap_classify_output\(', src)]
    assert len(calls) >= 2, (
        "trap_classify_output 仅定义未被调用（def 1 处 = 孤儿函数）·实测调用点数 %d" % len(calls))


def test_trap_block_not_empty_after_header():
    """calc_all 输出中「诱阻分类预计算」标题后不得紧跟空行。"""
    r = run_all(['--eu', EU, '--o25', '2.05', '--handi', '0.25', '--water', '1.99'])
    lines = r.stdout.splitlines()
    for i, l in enumerate(lines):
        if '诱阻分类预计算' in l:
            nxt = [x.strip() for x in lines[i + 1:i + 3] if x.strip()]
            assert nxt and '[trap]' in nxt[0], (
                "诱阻分类块为空（标题后无 [trap] 行）:\n" + '\n'.join(lines[i:i + 3]))
            return
    pytest.fail('未找到诱阻分类预计算块')


def test_trap_single_source_of_truth():
    """诱阻实现必须收敛到一处：calc_match 只做委托，不得再复制一份打分逻辑。"""
    src = open(os.path.join(TMP, 'calc_match.py'), encoding='utf-8').read()
    assert 'from calc_v3572 import match_classifier' in src or \
           'import calc_v3572' in src, "trap_classify_output 应委托 calc_v3572.match_classifier"
    # 不得保留第二份「水位异常」打分（历史双实现漂移点）
    body = src.split('def trap_classify_output')[1].split('\ndef ')[0] if 'def trap_classify_output' in src else ''
    assert 'water < 1.85' not in body and 'water > 2.05' not in body, (
        'trap_classify_output 内仍有独立打分副本（双实现）')


# ══════════ 回归: 既有行为不得破坏 ══════════
def test_calc_all_still_warns_unknown_flag():
    r = run_all(['--eu', EU, '--bogus', '9.9'])
    assert '--bogus' in r.stdout

# ══════════ D3: 亚盘线 vs 体彩让球L · 双轨 ══════════
# 已复现缺陷（本次 22 场实盘分析发现）:
#   calc_match 的 margin_candidates_pool 用 _rq_handicap（= 标题里的体彩 L，固定 −1/0/+1）
#   当唯一依据，亚盘线（--handi，可为 平手/受让0.25/让0.75）**完全没进解析**。
#   实测 23/23 场两者不一致（体彩只有 1 球粒度）。
#   后果：平手场（宫崎/埃弗斯堡/布伦特福德）净胜候选被硬抬成「主让1球」的 1:0/2:1。
def test_calc_match_reports_asia_vs_lottery_handicap():
    """必须显式输出「亚盘线 / 体彩L / 是否一致」。"""
    r = run_match(['--handi', '-0.5'])
    line = [l.strip() for l in r.stdout.splitlines() if '亚盘线' in l and '体彩' in l]
    assert line, "未输出亚盘线/体彩L 对照行:\n" + r.stdout[:1500]
    # fixture 标题为「让球+1」→ 体彩L=+1；亚盘线由 --handi 传入
    assert '+1' in line[0], "应报出体彩L=+1: " + line[0]
    assert '-0.5' in line[0], "应报出亚盘线=-0.5: " + line[0]
    assert '否' in line[0], "两者不一致时必须显式标「否」: " + line[0]


def test_margin_pool_uses_asia_line_not_lottery():
    """平手盘 + 体彩L=+1 → 净胜候选必须按亚盘线 0 取（档位 [0, 1, -1]）。

    🔴 判据看**档位**而不是候选比分——体彩L=+1 与亚盘0 的候选池会撞车（都含 1:1/0:0），
       只有档位能区分依据来源。
    """
    r = run_match(['--handi', '0'])
    pool = [l.strip() for l in r.stdout.splitlines() if '[netmargin]' in l]
    assert pool, "未产出 [netmargin] 行"
    p = pool[0]
    assert '档位[0, 1, -1]' in p, (
        "平手场应按亚盘线0 取档位[0, 1, -1]；实得: " + p +
        "（若为档位[-1, 0] 说明仍在用体彩L=+1）")
    assert '亚盘0' in p or '亚盘0.0' in p, "输出未标明使用的是亚盘线 0: " + p


def test_margin_pool_deep_handicap_unchanged():
    """亚盘 −2.0 时应取深盘档（回归: 不得因改双轨而丢深盘）。"""
    r = run_match(['--handi', '-2.0'])
    pool = [l.strip() for l in r.stdout.splitlines() if '[netmargin]' in l]
    assert pool, "未产出 [netmargin] 行"
    assert '亚盘-2' in pool[0] or '-2.0' in pool[0], "深盘未被采纳: " + pool[0]



# ══════════ S4 初盘位移展示（2026-10-19）══════════
# 注：本仓 pytest 的默认 tmp_path 无写权限（WinError 5），统一落到 data/tmp 下。

def _calc_all_mod():
    if TMP not in sys.path:
        sys.path.insert(0, TMP)
    import calc_all as CA
    return CA


@pytest.fixture
def s4_tmp():
    import shutil
    import tempfile
    base = os.path.join(ROOT, 'data', 'tmp', '_test_s4')
    os.makedirs(base, exist_ok=True)
    d = tempfile.mkdtemp(dir=base)
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _write(d, name, text):
    p = os.path.join(d, name)
    open(p, 'w', encoding='utf-8').write(text)
    return p


def test_s4_block_reads_shift_line(s4_tmp):
    """calc_all 必须回显并标注 S4 位移行，且明确不改方向。"""
    CA = _calc_all_mod()
    p = _write(s4_tmp, 'm.txt',
               '🔴S4初盘位移: 客胜 -7.9pp（初盘 48.5% → 即盘 56.4%）· 热门未变 · 强度档=strong\n')
    joined = '\n'.join(CA._s4_block(p))
    assert 'S4' in joined
    assert 'strong' in joined
    assert ('只加标签' in joined) or ('不改方向' in joined)


def test_s4_block_three_state_when_absent(s4_tmp):
    """没有 S4 行时必须三态标注，不得静默当成『平稳』。"""
    CA = _calc_all_mod()
    p = _write(s4_tmp, 'm.txt', '赛事：x\n')
    joined = '\n'.join(CA._s4_block(p))
    assert 'S4' in joined
    assert '无数据' in joined


def test_checklist_registers_c35():
    CA = _calc_all_mod()
    ids = [c[0] for c in CA.CHECKLIST]
    assert 'C35' in ids

