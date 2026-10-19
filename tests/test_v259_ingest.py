# -*- coding: utf-8 -*-
"""阶段2 回归：v259_ingest（快照 → 标准 txt 唯一真源）

锁住三件事，防止未来又分叉出第二份转换器：
  ① 联赛 slug 归一（LEAGUE_VIG 查表命中）
  ② 时点新鲜度进 txt 头部（下游无需重算）
  ③ 抽水标签如实披露（无独立竞彩源时禁称「竞彩抽水」/ F1）
另外锁住：多机构合并去水、O2.5 必走 ou_from_asia、缺行必须报错而非静默降级。
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')
sys.path.insert(0, TMP)

import v259_ingest as ING  # noqa: E402


@pytest.fixture
def tmpdir_repo():
    import shutil
    import tempfile
    base = os.path.join(ROOT, 'data', 'tmp', '_test_ingest')
    os.makedirs(base, exist_ok=True)
    d = tempfile.mkdtemp(dir=base)
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _snapshot(match_dir, *, league='英超', euros=None, asian=None, ou=None,
              euro_timeline=None, fetched='2026-10-17 17:30:10',
              kickoff='2026-10-17 19:30', lottery_handicap=1.0):
    """构造最小可用快照（结构与 titan007 服务端一致）"""
    os.makedirs(match_dir, exist_ok=True)
    if euros is None:
        euros = [
        {'company': '澳*', 'company_en': 'Macauslot', 'company_id': '1',
         'init_home': '2.77', 'init_draw': '3.67', 'init_away': '2.08',
         'live_home': '2.55', 'live_draw': '3.73', 'live_away': '2.20'},
        {'company': 'Pinna*(荷兰)', 'company_en': 'Pinnacle', 'company_id': '177',
         'init_home': '3.08', 'init_draw': '3.71', 'init_away': '2.14',
         'live_home': '3.00', 'live_draw': '3.60', 'live_away': '2.40'},
        {'company': '36*(英国)', 'company_en': 'Bet 365', 'company_id': '2',
         'init_home': '3.10', 'init_draw': '3.50', 'init_away': '2.15',
         'live_home': '2.90', 'live_draw': '3.60', 'live_away': '2.30'},
        {'company': '体彩官方', 'company_en': 'Lottery Official', 'company_id': '1129',
         'init_home': '3.05', 'init_draw': '3.43', 'init_away': '1.96',
         'live_home': '2.94', 'live_draw': '3.40', 'live_away': '2.02'},
        {'company': '体彩官方让球 (+1)', 'company_en': 'Lottery RQ', 'company_id': '1130',
         'init_home': '1.65', 'init_draw': '3.75', 'init_away': '3.90',
             'live_home': '1.61', 'live_draw': '3.85', 'live_away': '4.05'},
        ]
    if asian is None:
        asian = [
            {'company': '澳*', 'company_id': '1', 'init_home': '0.96', 'init_line': '-0/0.5',
             'init_away': '0.88', 'live_home': '0.84', 'live_line': '-0/0.5',
             'live_away': '1.00', 'init_line_value': -0.25, 'live_line_value': -0.25},
        ]
    if ou is None:
        ou = [
            {'company': '澳*', 'company_id': '1', 'init_home': '0.82', 'init_line': '2.5/3',
             'init_away': '0.98', 'live_home': '0.76', 'live_line': '2.5/3',
             'live_away': '1.04', 'init_line_value': 2.75, 'live_line_value': 2.75},
        ]
    data = {
        'schema_version': '2.5.9', 'match_id': '3003912', 'fetched_at': fetched,
        'sport_lottery_serial': '261017-007', 'sport_lottery_handicap': lottery_handicap,
        'detail': {'match_id': '3003912', 'league': league, 'home': '埃弗顿', 'away': '切尔西',
                   'match_time': kickoff, 'euro': euros, 'asian': asian, 'ou': ou,
                   'euro_timeline': euro_timeline or [],
                   'asian_timeline': [], 'ou_timeline': []},
    }
    open(os.path.join(match_dir, '服务端数据.json'), 'w', encoding='utf-8').write(
        json.dumps(data, ensure_ascii=False))
    return match_dir


def _tl(points):
    return [{'time': t, 'home': h, 'line': d, 'away': a} for t, h, d, a in points]


# ══════════ ① 联赛 slug 归一 ══════════

@pytest.mark.parametrize('cn,slug', [
    ('英超', 'epl'), ('德甲', 'bundesliga'), ('意甲', 'seriea'),
    ('西甲', 'laliga'), ('法甲', 'ligue1'), ('英冠', 'championship'),
    ('荷甲', 'eredivisie'), ('日职联', 'japan'),
])
def test_league_slug_is_the_vig_table_key(cn, slug):
    """LEAGUE_VIG 的键是英文 slug；ingest 必须给出 slug 供 calc_all 查表"""
    assert ING.LG_SLUG[cn] == slug


def test_unknown_league_yields_no_slug(tmpdir_repo):
    d = _snapshot(os.path.join(tmpdir_repo, 'm'), league='美职业')
    meta = ING.build(d)['meta']
    assert meta['lg'] == '美职业' and meta['lg_slug'] is None
    assert '该联赛未登记' in ING.build(d)['main']


def test_slug_is_actually_in_calc_match_table():
    """防漂移：ingest 给出的 slug 必须真能在 calc_match.LEAGUE_VIG 里命中

    🔴只读源码正则，**不可 import calc_match** —— 该模块在导入时会执行
       sys.stdout = io.TextIOWrapper(...)，把 pytest 的捕获流换掉，
       导致整个测试文件 teardown 报「I/O operation on closed file」。
    """
    src = open(os.path.join(TMP, 'calc_match.py'), encoding='utf-8').read()
    import re
    blk = re.search(r'LEAGUE_VIG = \{(.*?)\}', src, re.S)
    assert blk, '未找到 LEAGUE_VIG 定义'
    keys = set(re.findall(r"'([a-z0-9]+)':", blk.group(1)))
    for slug in set(ING.LG_SLUG.values()):
        assert slug in keys, 'ingest 的 slug %r 不在 LEAGUE_VIG 中（%s）' % (slug, sorted(keys))


# ══════════ ② 新鲜度 ══════════

def test_freshness_band_thresholds():
    import datetime
    ko = datetime.datetime(2026, 10, 17, 19, 30)
    series = [ko - datetime.timedelta(minutes=m) for m in (30, 120, 400)]
    assert ING.freshness(ko, series) == (30, 'LIVE')
    assert ING.freshness(ko, [ko - datetime.timedelta(minutes=120)]) == (120, 'SEMI')
    assert ING.freshness(ko, [ko - datetime.timedelta(minutes=400)]) == (400, 'STALE')
    assert ING.freshness(ko, []) == (None, 'UNKNOWN')


def test_freshness_written_into_txt_head(tmpdir_repo):
    """下游不该再自己算时点：头部必须写明距开赛分钟数与 V6 可用性"""
    d = _snapshot(os.path.join(tmpdir_repo, 'm'),
                  euro_timeline=_tl([('10-17 17:01', '2.55', '3.73', '2.2'),
                                     ('10-14 12:00', '2.77', '3.67', '2.08')]))
    txt, meta = ING.build(d)['main'], ING.build(d)['meta']
    assert '🔴时点新鲜度' in txt
    assert '距开赛' in txt and '盘口联动(V6)' in txt
    assert meta['minutes_before_ko'] == 149.0
    assert meta['band'] == 'SEMI'


def test_pseudo_series_is_flagged(tmpdir_repo):
    """无时序时用基线补一行 → 必须标 series_is_pseudo，不得冒充真时序"""
    d = _snapshot(os.path.join(tmpdir_repo, 'm'), euro_timeline=[])
    m = ING.build(d)['meta']
    assert m['series_points'] == 1 and m['series_is_pseudo'] is True


# ══════════ ③ 抽水标签如实披露 ══════════

def test_no_independent_lottery_source_is_disclosed(tmpdir_repo):
    """序列=基线 → 必须写明「无独立竞彩采价·F1 不适用」，禁称竞彩抽水"""
    d = _snapshot(os.path.join(tmpdir_repo, 'm'),
                  euro_timeline=_tl([('10-17 17:01', '2.55', '3.73', '2.2')]))
    txt = ING.build(d)['main']
    assert '反抽水比(F1) **不适用' in txt
    assert '禁读作「竞彩抽水」' in txt
    assert ING.build(d)['meta']['series_equals_base'] is True


# ══════════ ④ 多机构合并去水 ══════════

def test_consensus_uses_all_books(tmpdir_repo):
    d = _snapshot(os.path.join(tmpdir_repo, 'm'),
                  euro_timeline=_tl([('10-17 17:01', '2.55', '3.73', '2.2')]))
    c = ING.build(d)['meta']['consensus']
    assert c and c['n_books'] == 5
    assert abs(c['pH'] + c['pD'] + c['pA'] - 1.0) < 1e-3
    assert 0 < c['margin_mean'] < 0.2
    assert 'dir_agree' in c and 0 <= c['dir_agree'] <= c['n_books']


def test_consensus_line_present_in_txt(tmpdir_repo):
    d = _snapshot(os.path.join(tmpdir_repo, 'm'),
                  euro_timeline=_tl([('10-17 17:01', '2.55', '3.73', '2.2')]))
    txt = ING.build(d)['main']
    assert '🔴多机构合并去水' in txt and '等权对照' in txt and '同向' in txt


# ══════════ ⑤ O2.5 唯一真源 ══════════

def test_o25_comes_from_ou_from_asia(tmpdir_repo):
    import ou_from_asia as OA
    d = _snapshot(os.path.join(tmpdir_repo, 'm'),
                  euro_timeline=_tl([('10-17 17:01', '2.55', '3.73', '2.2')]))
    meta = ING.build(d)['meta']
    ref = OA.convert(2.75, 0.76, 1.04)
    assert abs(meta['o25'] - ref['o25']) < 1e-9
    assert abs(meta['lam'] - ref['lambda']) < 1e-9


# ══════════ ⑥ 缺行必须报错，不得静默降级 ══════════

def test_missing_macao_ou_raises(tmpdir_repo):
    d = _snapshot(os.path.join(tmpdir_repo, 'm'), ou=[])
    with pytest.raises(ValueError, match='澳门大小球'):
        ING.build(d)


def test_missing_macao_asian_raises(tmpdir_repo):
    d = _snapshot(os.path.join(tmpdir_repo, 'm'), asian=[])
    with pytest.raises(ValueError, match='澳门亚盘'):
        ING.build(d)


def test_unsupported_ou_line_raises(tmpdir_repo):
    bad = [{'company': '澳*', 'company_id': '1', 'init_home': '0.9', 'init_line': '9.25',
            'init_away': '0.9', 'live_home': '0.9', 'live_line': '9.25',
            'live_away': '0.9', 'init_line_value': 9.25, 'live_line_value': 9.25}]
    d = _snapshot(os.path.join(tmpdir_repo, 'm'), ou=bad)
    with pytest.raises(ValueError, match='O2.5'):
        ING.build(d)


# ══════════ ⑦ 符号与基线切换 ══════════

def test_handi_sign_convention(tmpdir_repo):
    """handi = −(亚盘 line_value)：负=主让 / 正=主受让"""
    d = _snapshot(os.path.join(tmpdir_repo, 'm'),
                  euro_timeline=_tl([('10-17 17:01', '2.55', '3.73', '2.2')]))
    assert ING.build(d)['meta']['handi'] == 0.25          # 主受让 0.25
    asian = [{'company': '澳*', 'company_id': '1', 'init_home': '0.9', 'init_line': '1',
              'init_away': '0.9', 'live_home': '0.9', 'live_line': '1',
              'live_away': '0.9', 'init_line_value': 1.0, 'live_line_value': 1.0}]
    d2 = _snapshot(os.path.join(tmpdir_repo, 'm2'), asian=asian,
                   euro_timeline=_tl([('10-17 17:01', '2.55', '3.73', '2.2')]))
    assert ING.build(d2)['meta']['handi'] == -1.0         # 主让 1


def test_baseline_kind_soft_vs_sharp(tmpdir_repo):
    """软盘/锐盘必须可区分 —— LEAGUE_VIG 是软盘基准，与 Pinnacle 分子不同源"""
    d = _snapshot(os.path.join(tmpdir_repo, 'm'),
                  euro_timeline=_tl([('10-17 17:01', '2.55', '3.73', '2.2')]))
    soft = ING.build(d, baseline='macao')
    sharp = ING.build(d, baseline='pinnacle')
    assert soft['meta']['baseline_kind'] == 'soft'
    assert sharp['meta']['baseline_kind'] == 'sharp'
    assert '🔴基线性质：soft' in soft['main']
    assert '🔴基线性质：sharp' in sharp['main']


def test_sharp_baseline_discloses_incomparable_ratio(tmpdir_repo):
    """Pinnacle 基线：时序虽独立，但分母是软盘基准 → 必须写明「不同源」"""
    # 时序沿用澳门线（≠Pinnacle 基线）→ 序列独立；但基线是锐盘
    d = _snapshot(os.path.join(tmpdir_repo, 'm'),
                  euro_timeline=_tl([('10-17 17:01', '2.55', '3.73', '2.20')]))
    r = ING.build(d, baseline='pinnacle')
    assert r['meta']['series_equals_base'] is False
    assert r['meta']['baseline_kind'] == 'sharp'
    assert '不同源' in r['main']
    assert 'LEAGUE_VIG 是软盘基准' in r['main']


def test_manifest_name_follows_suffix(tmpdir_repo):
    """澳门轮与 Pinnacle 轮不得共用同一个 manifest（否则后者覆盖前者）"""
    import subprocess
    src = os.path.join(tmpdir_repo, 'src')
    _snapshot(os.path.join(src, 'm1'),
              euro_timeline=_tl([('10-17 17:01', '2.55', '3.73', '2.2')]))
    out = os.path.join(tmpdir_repo, 'out')
    for extra in ([], ['--pinnacle', '--suffix', '.pin']):
        r = subprocess.run([sys.executable, os.path.join(TMP, 'v259_ingest.py'),
                            '--src', src, '--out', out] + extra,
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', cwd=ROOT, timeout=180)
        assert r.returncode == 0, r.stdout[-400:] + r.stderr[-400:]
    assert os.path.exists(os.path.join(out, '_manifest.json'))
    assert os.path.exists(os.path.join(out, '_manifest.pin.json'))
    a = json.load(open(os.path.join(out, '_manifest.json'), encoding='utf-8'))
    b = json.load(open(os.path.join(out, '_manifest.pin.json'), encoding='utf-8'))
    assert a[0]['baseline'] == 'macao' and b[0]['baseline'] == 'pinnacle'


def test_pinnacle_baseline_switch(tmpdir_repo):
    d = _snapshot(os.path.join(tmpdir_repo, 'm'),
                  euro_timeline=_tl([('10-17 17:01', '2.55', '3.73', '2.2')]))
    mac = ING.build(d, baseline='macao')['meta']
    pin = ING.build(d, baseline='pinnacle')['meta']
    assert mac['eu'] == '2.55,3.73,2.20'
    assert pin['eu'] == '3.00,3.60,2.40'
    assert mac['base_tag'] == '澳门' and pin['base_tag'] == 'Pinnacle'


# ══════════ ⑧ CLI ══════════

def test_cli_check_mode_does_not_write(tmpdir_repo):
    import subprocess
    src = os.path.join(tmpdir_repo, 'src')
    _snapshot(os.path.join(src, 'm1'), euro_timeline=_tl([('10-17 17:01', '2.55', '3.73', '2.2')]))
    out = os.path.join(tmpdir_repo, 'out')
    r = subprocess.run([sys.executable, os.path.join(TMP, 'v259_ingest.py'),
                        '--src', src, '--out', out, '--check'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace',
                       cwd=ROOT, timeout=180)
    assert r.returncode == 0, r.stdout[-400:] + r.stderr[-400:]
    assert not os.path.exists(out), '--check 不得落盘'



# ══════════ ⑨ S4 初盘位移（2026-10-19）══════════

def test_ingest_writes_s4_shift_line(tmpdir_repo):
    """v259_ingest 必须把「初盘→即盘位移」写进 txt 头（S4）。

    口径: base_init / base_live 已是本函数内的真初盘与即盘，直接复用。
    本用例的初盘 2.77/3.67/2.08 → 即盘 2.55/3.73/2.20：
      初盘热门=客胜(2.08) → 即盘客胜 2.20，1/2.20-1/2.08 = -2.62pp → 位移 <3 → flat
    """
    import subprocess
    src = os.path.join(tmpdir_repo, 'src')
    _snapshot(os.path.join(src, 'm1'),
              euro_timeline=_tl([('10-17 17:01', '2.55', '3.73', '2.2')]))
    out = os.path.join(tmpdir_repo, 'out')
    r = subprocess.run([sys.executable, os.path.join(TMP, 'v259_ingest.py'),
                        '--src', src, '--out', out],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', cwd=ROOT, timeout=180)
    assert r.returncode == 0, r.stdout[-400:] + r.stderr[-400:]
    txts = [f for f in os.listdir(out) if f.endswith('.txt')]
    assert txts, 'no txt produced'
    head = open(os.path.join(out, txts[0]), encoding='utf-8').read()
    assert '🔴S4初盘位移' in head
    assert '强度档=flat' in head



def test_missing_init_fields_yields_three_state_not_crash(tmpdir_repo):
    """I4: 快照缺 init_* 时必须三态「无数据」，不得抛 TypeError。

    回归（2026-10-19 评审）：v259_ingest 用 '... (初盘 %g / %g / %g)' 格式化 base_init，
    None 时先抛 TypeError，S4 那行根本执行不到 → 整场被 main() 计为「无法转换」，
    把「上游缺字段」误报成「数据源损坏」。
    """
    import subprocess
    src = os.path.join(tmpdir_repo, 'src')
    # 澳门行只有 live_*，没有 init_*
    euros = [
        {'company': '澳*', 'company_en': 'Macauslot', 'company_id': '1',
         'live_home': '2.55', 'live_draw': '3.73', 'live_away': '2.20'},
        {'company': 'Pinnacle', 'company_en': 'Pinnacle', 'company_id': '2',
         'init_home': '3.00', 'init_draw': '3.60', 'init_away': '2.40',
         'live_home': '3.00', 'live_draw': '3.60', 'live_away': '2.40'},
    ]
    _snapshot(os.path.join(src, 'm1'), euros=euros,
              euro_timeline=_tl([('10-17 17:01', '2.55', '3.73', '2.2')]))
    out = os.path.join(tmpdir_repo, 'out')
    r = subprocess.run([sys.executable, os.path.join(TMP, 'v259_ingest.py'),
                        '--src', src, '--out', out],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', cwd=ROOT, timeout=180)
    assert r.returncode == 0, r.stdout[-600:] + r.stderr[-600:]
    txts = [f for f in os.listdir(out) if f.endswith('.txt')]
    assert txts, 'no txt produced'
    head = open(os.path.join(out, txts[0]), encoding='utf-8').read()
    assert '🔴S4初盘位移' in head
    assert '无数据' in head
