# -*- coding: utf-8 -*-
"""阶段1 检查器回归测试（2026-10-17·data-2.5.9 单场批暴露的口径缺陷）

覆盖三个检查器：
  check_vig_basis      ① 反抽水/凯利「基准与标签」校验
  check_silent_degrade ② 静默降级检测
  check_freshness      ③ 时点新鲜度门

设计原则：全部用合成 fixture，不依赖 data/tmp 下的真实批次（那会随时间漂移）。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')
sys.path.insert(0, TMP)


@pytest.fixture
def tmpdir_repo():
    """工作区内临时目录（本环境的系统 TEMP 不可写，pytest tmp_path 会 PermissionError）"""
    import shutil
    import tempfile
    base = os.path.join(ROOT, 'data', 'tmp', '_test_checkers')
    os.makedirs(base, exist_ok=True)
    d = tempfile.mkdtemp(dir=base)
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════
# ① check_vig_basis
# ══════════════════════════════════════════════════════════════════

def _input_txt(series, baseline=(2.55, 3.73, 2.20), league='英超', pin=None):
    """构造最小标准输入 txt"""
    lines = ['赛事：261017-007-3003912 %s 埃弗顿(主) VS 切尔西(客)' % league,
             '比赛时间：10-17 19:30 2026/2027赛季',
             '抓取时间：2026-10-17 17:30:10', '']
    lines.append('🔴机构通道统一基线 = 澳门胜平负即盘：%g / %g / %g (初盘 %g / %g / %g)'
                 % (baseline + baseline))
    if pin:
        lines.append('欧赔(Pinnacle 即盘·交叉校验源)：%g / %g / %g' % pin)
    lines.append('')
    lines.append('【胜平负固定奖金】')
    lines.append('发布时间,胜,平,负')
    for ts, h, d, a in series:
        lines.append('%s,%s,%s,%s' % (ts, h, d, a))
    return '\n'.join(lines) + '\n'


def test_vig_of_matches_known_value():
    """抽水率 = Σ(1/赔率) − 1；Pinnacle 3.00/3.60/2.40 实测 2.78%"""
    import check_vig_basis as V
    assert abs(V.vig_of(3.00, 3.60, 2.40) * 100 - 2.78) < 0.02
    assert abs(V.vig_of(2.55, 3.73, 2.20) * 100 - 11.48) < 0.02
    assert V.vig_of(0, 0, 0) is None


def test_vb01_fires_when_series_is_just_the_baseline():
    """序列末行与声明基线完全一致 → 不是独立竞彩源 → VB01 必须 FAIL"""
    import check_vig_basis as V
    txt = _input_txt([('2026-10-17 17:01:00', 2.55, 3.73, 2.20)])
    codes = [f['code'] for f in V.check(txt) if f['level'] == 'FAIL']
    assert 'VB01' in codes, [f['code'] for f in V.check(txt)]


def test_vb01_silent_when_series_is_independent():
    """序列与基线不同 → 有独立源 → 不应报 VB01"""
    import check_vig_basis as V
    txt = _input_txt([('2026-10-17 17:01:00', 2.94, 3.40, 2.02)])
    codes = [f['code'] for f in V.check(txt)]
    assert 'VB01' not in codes, codes


def test_vb03_fires_for_top5_league_with_default_basis():
    """五大联赛却打印「缺省6.9%」→ 查表未命中（英文 slug vs 中文键）→ VB03"""
    import check_vig_basis as V
    txt = _input_txt([('2026-10-17 17:01:00', 2.94, 3.40, 2.02)])
    out = ('  去抽水率: 12.00% → 隐含: 主30.0%/平26.0%/客44.0%\n'
           '  竞彩抽水 12.00% · 欧盘基准(联赛缺省6.9%) 6.90% → 反抽水比 1.74x 🔴触发反抽水(>1.30)\n')
    codes = [f['code'] for f in V.check(txt, out) if f['level'] == 'FAIL']
    assert 'VB03' in codes, [f['code'] for f in V.check(txt, out)]


def test_vb03_silent_when_basis_hit_the_table():
    """基准来自查表（非缺省）→ 不报 VB03"""
    import check_vig_basis as V
    txt = _input_txt([('2026-10-17 17:01:00', 2.94, 3.40, 2.02)])
    out = '  竞彩抽水 12.00% · 欧盘基准(联赛查表) 5.61% → 反抽水比 2.14x\n'
    codes = [f['code'] for f in V.check(txt, out)]
    assert 'VB03' not in codes, codes


def test_vb04_flags_ratio_built_on_non_lottery_prices():
    """分子不是竞彩价时，反抽水比不承载信号 → VB04"""
    import check_vig_basis as V
    txt = _input_txt([('2026-10-17 17:01:00', 2.55, 3.73, 2.20)])
    out = '  竞彩抽水 11.48% · 欧盘基准(联赛缺省6.9%) 6.90% → 反抽水比 1.66x 🔴触发反抽水(>1.30)\n'
    codes = [f['code'] for f in V.check(txt, out) if f['level'] == 'FAIL']
    assert 'VB04' in codes, [f['code'] for f in V.check(txt, out)]


def test_vb05_flags_missing_pinnacle_basis():
    """输入含 Pinnacle 价（2.78%）却把基准取 6.90% → VB05 WARN"""
    import check_vig_basis as V
    txt = _input_txt([('2026-10-17 17:01:00', 2.55, 3.73, 2.20)],
                     pin=(3.00, 3.60, 2.40))
    out = '  竞彩抽水 11.48% · 欧盘基准(联赛查表) 6.90% → 反抽水比 1.66x\n'
    codes = [f['code'] for f in V.check(txt, out) if f['level'] == 'WARN']
    assert 'VB05' in codes, [f['code'] for f in V.check(txt, out)]


def test_vig_batch_excludes_pin_duplicates(tmpdir_repo):
    """批级统计不得把 *.pin.txt 双基线副本重复计场"""
    import check_vig_basis as V
    body = ('  竞彩抽水 11.48% · 欧盘基准(联赛缺省6.9%) 6.90% → 反抽水比 1.66x '
            '🔴触发反抽水(>1.30)\n')
    for n in ('a.txt', 'a.pin.txt', 'b.txt', 'b.pin.txt'):
        open(os.path.join(tmpdir_repo, n), 'w', encoding='utf-8').write(body)
    fs = V.check_batch(tmpdir_repo)
    vb10 = [f for f in fs if f['code'] == 'VB10']
    assert vb10 and '(2/2' in vb10[0]['msg'], vb10


# ══════════════════════════════════════════════════════════════════
# ② check_silent_degrade
# ══════════════════════════════════════════════════════════════════

def test_sd01_fires_on_bare_degrade_line():
    """宣告降级却不给原因 → 静默降级（违反三态铁律）"""
    import check_silent_degrade as D
    res = D.scan_text('  V5跨市场分歧: 未提供欧盘\n')
    assert any(r['level'] == 'FAIL' and r['code'] == 'SD01' for r in res), res


def test_sd00_ok_when_reason_on_same_line():
    """同行给出原因 → 合规三态"""
    import check_silent_degrade as D
    res = D.scan_text('  🔴HAF: 不可用(原因: 队伍不在档案内)\n')
    assert res and all(r['level'] == 'OK' for r in res), res


def test_sd_ignores_pure_three_state_lines():
    """「无数据(原因:…)」不含降级词 → 不进入扫描（避免噪音）"""
    import check_silent_degrade as D
    assert D.scan_text('  🔴HAF: 无数据(原因: 队伍不在档案内)\n') == []


def test_sd00_ok_when_reason_in_context_window():
    """原因在相邻行 → 合规"""
    import check_silent_degrade as D
    txt = ('  🔴xG(SK-xg-depth): ⚠️ 不可用\n'
           '     ↳ 原因: 该联赛不在 understat 覆盖域\n')
    res = D.scan_text(txt, context=2)
    assert res and all(r['level'] == 'OK' for r in res), res


def test_sd_whitelist_prevents_false_positive():
    """学科/提示语里的「降级」不得误报"""
    import check_silent_degrade as D
    for line in ('  [D1升赔误排除] D1升赔硬降级仅可降置信度·禁用于排除方向',
                 '  → 正常(无盘面猫腻·默认按档位正常事件判定)',
                 '  C25 … → 降级 understat_xg (按三态标注)'):
        res = D.scan_text(line + '\n')
        assert not any(r['level'] == 'FAIL' for r in res), (line, res)


def test_sd_ignores_separator_lines():
    import check_silent_degrade as D
    assert D.scan_text('=' * 70 + '\n') == []


# ══════════════════════════════════════════════════════════════════
# ③ check_freshness
# ══════════════════════════════════════════════════════════════════

def test_freshness_bands_at_boundaries():
    """阈值与 V6 条文一致：≤90 临场 / 90-180 次临场 / >180 非临场"""
    import check_freshness as F
    assert F.classify(90) == 'LIVE'
    assert F.classify(90.1) == 'SEMI'
    assert F.classify(180) == 'SEMI'
    assert F.classify(180.1) == 'STALE'
    assert F.classify(None) == 'UNKNOWN'


def _fresh_txt(ko='19:30', series=('2026-10-17 18:10:00',), ymd=True):
    head = '赛事：261017-007-3003912 英超 埃弗顿(主) VS 切尔西(客)\n'
    head += ('比赛时间：%s %s 2026/2027赛季\n'
             % ('2026-10-17' if ymd else '10-17', ko))
    head += '数据来源：... 抓取 2026-10-17 17:30:10\n\n'
    body = '【胜平负固定奖金】\n发布时间,胜,平,负\n'
    body += '\n'.join('%s,2.55,3.73,2.20' % ts for ts in series) + '\n'
    return head + body


def test_freshness_uses_only_the_real_series_channel():
    """【让球】等单行市场的时间戳是抓取时刻，不得当作最新市场时点"""
    import check_freshness as F
    txt = _fresh_txt(series=('2026-10-17 15:00:00',))
    txt += '【让球胜平负固定奖金｜让球+1】\n发布时间,胜,平,负\n2026-10-17 17:30:10,1.61,3.85,4.05\n'
    ko, fetched, per = F.parse_times(txt)
    assert len(per['胜平负固定奖金']) == 1
    # 末点为 15:00，距 19:30 = 270 分钟 → STALE（若误用让球行 17:30 则只有 120 分钟）
    latest = max(per['胜平负固定奖金'])
    mins = (ko - latest).total_seconds() / 60
    assert round(mins) == 270
    assert F.classify(mins) == 'STALE'


def test_freshness_flags_stale_claiming_v6(tmpdir_repo):
    """非临场却出现 V6 结论 → FAIL"""
    import check_freshness as F
    p = os.path.join(tmpdir_repo, 'm.txt')
    open(p, 'w', encoding='utf-8').write(
        _fresh_txt(series=('2026-10-17 12:00:00',)) + '\nV6 四象限: 深+大球强 → 主 67.7%\n')
    r = F.check_file(p)
    assert r['band'] == 'STALE'
    assert r['level'] == 'FAIL', r


def test_freshness_ok_when_stale_and_declared(tmpdir_repo):
    """非临场但显式声明「非临场」→ 不拦截"""
    import check_freshness as F
    p = os.path.join(tmpdir_repo, 'm.txt')
    open(p, 'w', encoding='utf-8').write(
        _fresh_txt(series=('2026-10-17 12:00:00',)) +
        '\n无临场数据·不触发(原因: 末点距开赛 450 分钟)\n')
    r = F.check_file(p)
    assert r['level'] == 'OK', r


def test_freshness_infers_missing_year_from_fetch(tmpdir_repo):
    """输入模板只给 MM-DD HH:MM → 以抓取年份补齐（跨年 +1）"""
    import check_freshness as F
    p = os.path.join(tmpdir_repo, 'm.txt')
    open(p, 'w', encoding='utf-8').write(_fresh_txt(series=('2026-10-17 18:10:00',), ymd=False))
    r = F.check_file(p)
    assert r['kickoff'] == '2026-10-17 19:30', r
    assert r['band'] == 'LIVE', r


# ══════════════════════════════════════════════════════════════════
# ③b 硬门（阶段3）：V6 引用检测 + 下游合规
# ══════════════════════════════════════════════════════════════════

def test_v6_claim_detected_for_real_use():
    """真引用（无否定语境）必须被算作引用"""
    import check_freshness as F
    assert F.find_v6_claims('V6 四象限: 深+大球强 → 主 67.7%') == ['V6 四象限']
    assert F.find_v6_claims('剪刀差 0.12 → 强信号') == ['剪刀差']


def test_v6_claim_ignores_warning_context():
    """「禁与V6四象限同档引用」「经验公式·未回测」属警示语，不是引用"""
    import check_freshness as F
    for line in ('⚠️ 净胜期望档来源: 经验公式·未回测 —— 禁与「V6 四象限 22.7 万场」同档引用',
                 '🔴仅作约束提示·禁引用 V6 四象限',
                 '四象限结论不适用(原因:非临场)'):
        assert F.find_v6_claims(line) == [], (line, F.find_v6_claims(line))


def test_v6_claim_ignores_gate_own_refusal_line():
    """硬门自己的拒绝行会把 V6 子项列一遍，那是拒绝不是引用"""
    import check_freshness as F
    line = '     ↳ 结论: V6 四象限/剪刀差/卡位/退盘 **一律不得引用**'
    assert F.find_v6_claims(line) == [], F.find_v6_claims(line)


def test_gate_fails_when_stale_output_claims_v6(tmpdir_repo):
    """非临场 + 输出引用 V6 → FAIL"""
    import check_freshness as F
    inp = _fresh_txt(series=('2026-10-17 12:00:00',))
    row = {'file': 'a.txt', 'band': 'STALE', 'minutes_before_ko': 450.0}
    outdir = os.path.join(tmpdir_repo, 'out')
    os.makedirs(outdir)
    open(os.path.join(outdir, 'a.txt'), 'w', encoding='utf-8').write('V6 四象限: 主 67.7%\n')
    fs = F.check_output_dir(outdir, [row])
    assert any(f['level'] == 'FAIL' and 'V6 结论' in f['msg'] for f in fs), fs


def test_gate_fails_when_stale_output_lacks_refusal(tmpdir_repo):
    """非临场但输出里没有硬门拒绝行 → 无法证明被阻断 → FAIL"""
    import check_freshness as F
    row = {'file': 'a.txt', 'band': 'STALE', 'minutes_before_ko': 450.0}
    outdir = os.path.join(tmpdir_repo, 'out')
    os.makedirs(outdir)
    open(os.path.join(outdir, 'a.txt'), 'w', encoding='utf-8').write('随便什么输出\n')
    fs = F.check_output_dir(outdir, [row])
    assert any('硬门拒绝行' in f['msg'] for f in fs), fs


def test_gate_passes_when_stale_output_has_refusal(tmpdir_repo):
    """非临场 + 有硬门拒绝行 + 不引用 V6 → 通过"""
    import check_freshness as F
    row = {'file': 'a.txt', 'band': 'STALE', 'minutes_before_ko': 450.0}
    outdir = os.path.join(tmpdir_repo, 'out')
    os.makedirs(outdir)
    open(os.path.join(outdir, 'a.txt'), 'w', encoding='utf-8').write(
        '🔴盘口联动(V6): 🚫 硬门拒绝 — 末点距开赛 450 分钟(>180) → 非临场\n'
        '     ↳ 结论: V6 四象限/剪刀差/卡位/退盘 **一律不得引用**\n')
    assert F.check_output_dir(outdir, [row]) == []


def test_gate_warns_when_semi_live_claims_v6(tmpdir_repo):
    """次临场引用 V6 → WARN（可弱参考，不得当强信号）"""
    import check_freshness as F
    row = {'file': 'a.txt', 'band': 'SEMI', 'minutes_before_ko': 120.0}
    outdir = os.path.join(tmpdir_repo, 'out')
    os.makedirs(outdir)
    open(os.path.join(outdir, 'a.txt'), 'w', encoding='utf-8').write('V6 四象限: 主 67.7%\n')
    fs = F.check_output_dir(outdir, [row])
    assert fs and all(f['level'] == 'WARN' for f in fs), fs


def test_freshness_cli_directory_mode(tmpdir_repo):
    """目录模式：跳过 *.pin.txt 副本，返回退出码语义正确"""
    import subprocess
    body = _fresh_txt(series=('2026-10-17 19:00:00',))
    for n in ('a.txt', 'a.pin.txt'):
        open(os.path.join(tmpdir_repo, n), 'w', encoding='utf-8').write(body)
    r = subprocess.run([sys.executable, os.path.join(TMP, 'check_freshness.py'), tmpdir_repo, '--json'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace',
                       cwd=ROOT, timeout=120)
    assert r.returncode == 0, r.stdout[-400:] + r.stderr[-400:]
    import json as _j
    data = _j.loads(r.stdout)
    # --json 现返回 {inputs, output_findings} 结构
    rows = data['inputs'] if isinstance(data, dict) else data
    assert len(rows) == 1, [d.get('file') for d in rows]
    assert rows[0]['file'] == 'a.txt'
