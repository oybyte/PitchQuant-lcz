# -*- coding: utf-8 -*-
"""阶段3 回归：V6 硬门（新鲜度门槛的真实阻断）

锁住的三档语义（与 calc_match / calc_all / check_freshness 三处必须一致）：
  ≤90min   LIVE  ✅ 可判定
  90-180   SEMI  ⚠️ 仅弱参考
  >180     STALE 🚫 硬门拒绝·禁引用
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, 'scripts', 'tmp')


def _input(tmp_name, minutes, write=True):
    """构造一份带「时点新鲜度」行的标准输入 txt"""
    import datetime
    ko = datetime.datetime(2026, 10, 17, 19, 30)
    last = ko - datetime.timedelta(minutes=minutes)
    band = '临场' if minutes <= 90 else ('次临场' if minutes <= 180 else '非临场')
    v6 = {'临场': '✅ 可判定', '次临场': '⚠️ 仅弱参考', '非临场': '❌ 不适用(原因:非临场)'}[band]
    txt = ('赛事：261017-007-3003912 英超 埃弗顿(主) VS 切尔西(客)\n'
           '比赛时间：10-17 19:30 2026/2027赛季\n'
           '抓取时间：2026-10-17 17:30:10\n\n'
           '🔴机构通道统一基线 = 澳门胜平负即盘：2.55 / 3.73 / 2.20 (初盘 2.55 / 3.73 / 2.20)\n'
           '🔴时点新鲜度：【胜平负】4 个时点 · 末点 %s · 距开赛 %.0f 分钟 → %s ｜ 盘口联动(V6): %s\n'
           % (last.strftime('%%Y-%%m-%%d %%H:%%M:00'), minutes, band, v6))
    txt += '\n【胜平负固定奖金】\n发布时间,胜,平,负\n%s,2.55,3.73,2.20\n' % last.strftime('%Y-%m-%d %H:%M:%S')
    txt += '\n【让球胜平负固定奖金｜让球+1】\n发布时间,胜,平,负\n2026-10-17 17:30:10,1.61,3.85,4.05\n'
    return txt


def _run_calc_all(tmp_name, minutes):
    import subprocess
    p = os.path.join(TMP, '_tmp_' + tmp_name)
    open(p, 'w', encoding='utf-8').write(_input(tmp_name, minutes))
    try:
        r = subprocess.run([sys.executable, os.path.join(TMP, 'calc_all.py'), p, 'epl',
                            '--eu', '2.55,3.73,2.20', '--handi', '0.25',
                            '--o25', '1.623', '--u25', '2.606', '--water', '1.84'],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', cwd=ROOT, timeout=300)
        return r.stdout
    finally:
        try:
            os.remove(p)
        except OSError:
            pass


def test_stale_refuses_v6_in_calc_match():
    out = _run_calc_all('stale.txt', 505)
    assert '🚫 硬门拒绝' in out, out[-1500:]
    assert '505 分钟' in out
    assert '一律不得引用' in out


def test_live_allows_v6():
    out = _run_calc_all('live.txt', 31)
    assert '✅ 可判定' in out
    assert '🚫 硬门拒绝' not in out


def test_semi_is_weak_only():
    out = _run_calc_all('semi.txt', 149)
    assert '⚠️ 弱门' in out
    assert '仅可作弱参考' in out
    assert '🚫 硬门拒绝' not in out


def test_checklist_c09_not_marked_must_do_when_stale():
    """非临场时 C09 不得再打「必做」——否则执行者会为凑清单编造 V6"""
    out = _run_calc_all('cl.txt', 505)
    line = next((l for l in out.split('\n') if 'C09' in l), '')
    assert line, '未找到 C09 行'
    assert '硬门拒绝' in line, line
    assert '必做' not in line, line


def test_checklist_c09_marked_live_when_fresh():
    out = _run_calc_all('cl2.txt', 31)
    line = next((l for l in out.split('\n') if 'C09' in l), '')
    assert '临场' in line and '可判定' in line, line


def test_missing_freshness_line_is_not_silently_passed():
    """输入没声明新鲜度 → 必须三态标注，不得当作可判定"""
    import subprocess
    p = os.path.join(TMP, '_tmp_nofresh.txt')
    open(p, 'w', encoding='utf-8').write(
        '赛事：261017-007-3003912 英超 埃弗顿(主) VS 切尔西(客)\n'
        '比赛时间：10-17 19:30 2026/2027赛季\n\n'
        '🔴机构通道统一基线 = 澳门胜平负即盘：2.55 / 3.73 / 2.20 (初盘 2.55 / 3.73 / 2.20)\n'
        '\n【胜平负固定奖金】\n发布时间,胜,平,负\n2026-10-17 17:01:00,2.55,3.73,2.20\n'
        '\n【让球胜平负固定奖金｜让球+1】\n发布时间,胜,平,负\n2026-10-17 17:30:10,1.61,3.85,4.05\n')
    try:
        r = subprocess.run([sys.executable, os.path.join(TMP, 'calc_all.py'), p, 'epl',
                            '--eu', '2.55,3.73,2.20', '--handi', '0.25',
                            '--o25', '1.623', '--u25', '2.606', '--water', '1.84'],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', cwd=ROOT, timeout=300)
        out = r.stdout
    finally:
        try:
            os.remove(p)
        except OSError:
            pass
    assert '不触发(原因: 输入未声明时点新鲜度' in out, out[-1200:]
