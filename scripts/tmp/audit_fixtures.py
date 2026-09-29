# -*- coding: utf-8 -*-
"""A1⑭ 提取函数真实样例回归（2026-09-28·对照 SK-audit A/B 更新方案）

对 data/tmp/_audit_fixtures/ 下每份真实 txt 跑全部 parse/extract 函数，
断言主客名/轮次非空且正确。任一回 None/空 = P0（本次 P0-2/P0-4 的漏网点）。

用法:  python data/tmp/audit_fixtures.py     # 全过 → exit 0；任一失败 → exit 1
接入:  check_sync 第 ⑯ 区自动跑（防复发）
"""
import glob
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_audit_fixtures')
FAIL = []

# fixture → 期望 (主队, 客队, 轮次|None=不校验)
EXPECT = {
    'txt_nl_standard.txt': ('荷兰', '德国', 3),
    'txt_nl_variant.txt': ('塞尔维亚', '荷兰', 1),
    'txt_league_seriea.txt': ('亚特兰大', '卡利亚里', None),
    'txt_league_epl.txt': ('阿斯顿维拉', '诺丁汉森林', None),
    'txt_league_oddorder.txt': ('马竞', '奥萨苏纳', None),
}


def _chk(name, ok, detail=''):
    print('  %s %-44s %s' % ('✅' if ok else '❌', name, detail))
    if not ok:
        FAIL.append(name)


def main():
    from nl_model import extract_nl_teams, parse_matchday
    files = sorted(glob.glob(os.path.join(FIX, '*.txt')))
    if not files:
        print('❌ fixture 目录为空或不存在: %s' % FIX)
        return 1
    print('════ A1⑭ fixture 回归（%d 份）════' % len(files))
    for p in files:
        b = os.path.basename(p)
        try:
            txt = io.open(p, encoding='utf-8').read()
        except Exception as e:
            _chk('%s 可读' % b, False, str(e)[:40]); continue
        h, a = extract_nl_teams(txt)
        md = parse_matchday(txt)
        exp = EXPECT.get(b)
        if exp:
            _chk('%s 队名' % b, h == exp[0] and a == exp[1],
                 '→ %s/%s (期望 %s/%s)' % (h, a, exp[0], exp[1]))
            if exp[2] is not None:
                _chk('%s 轮次' % b, md == exp[2], '→ %s (期望 %s)' % (md, exp[2]))
            else:
                _chk('%s 队名非空' % b, bool(h and a), '')
        else:
            _chk('%s 队名非空(未登记期望)' % b, bool(h and a), '→ %s/%s' % (h, a))
        _chk('%s 主客不同' % b, bool(h) and bool(a) and h != a)
    print()
    if FAIL:
        print('🔴 fixture 回归失败 %d 项: %s' % (len(FAIL), FAIL[:6]))
        return 1
    print('🟢 fixture 回归全过（%d 份）' % len(files))
    return 0


if __name__ == '__main__':
    sys.exit(main())
