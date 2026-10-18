#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_vig_basis.py — 反抽水/凯利「基准与标签」校验器（阶段1·检查器①）

为什么存在（2026-10-17 data-2.5.9 单场 26 场批暴露的 P0）
---------------------------------------------------------
calc_match 打印的「竞彩抽水」并非独立采集的竞彩时点数据，而是取自 --eu 传入的
那一行（澳门 / Pinnacle 基线）。三条后果叠加后，F1 变成每场固定的装饰性标签：

  1. 标签名实不符
     26/26 场打印「竞彩抽水 11.5%~12.9%」，而那其实是澳门价
     （同批 Pinnacle 真实抽水只有 2.78%）。读者会误以为竞彩在高价收割。

  2. 反抽水比失去信息量
     反抽水比 = 同一份数字 / 联赛基准 → 26/26 全部「触发 F1(>1.30)」（1.57-1.87x）。
     一个 100% 触发的信号等于没有信号，反而挤占输出位、暗示「本场有异常」。

  3. 联赛基准表实际是空表
     calc_match.LEAGUE_VIG 的键是英文 slug（epl / bundesliga / seriea），
     而调用方传进来的是中文「英超」「德甲」→ 永远走「缺省 6.9%」分支。
     这不是「查表失败」，是**查表根本没发生而无人察觉**。

本校验器不改任何计算，只判定：**打印出来的标签，配不配它背后的数字**。

用法
----
    python scripts/tmp/check_vig_basis.py <输入txt> [--output <calc_all输出txt>]
    python scripts/tmp/check_vig_basis.py --batch <out目录>      # 批级：含 F1 触发率
    python scripts/tmp/check_vig_basis.py ... --json

自洽性检查（--selfcheck）
------------------------------
吸收并取代 v259_consistency.py（原脚本固定指向 batch_v259_today，已无法复用），并补两项：
  SC01  skew 与隐含相符    （报的 skew 应 = 最高隐含 / 次高隐含）
  SC02  λ 与聚合方向一致  （|λh-λa|>0.15 时，λ 主导方向不得与聚合最高向相反）
  SC03  聚合概率和=100    （容差 1.5pp）
  SC04  铁胆与 skew 自洽    （铁胆档所展示的 skew 必须 ≥ TIEDAN_SKEW_MIN）
  SC05  铁胆必带否定声明（防被读成必胜）
三态: 无数据则跳过该项（不计入异常）。

退出码: 0 = 未发现名实不符/自洽性异常; 1 = 存在（FAIL 项）; 2 = 用法错误
"""
import argparse
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# 五大联赛（中文）→ 应能在 LEAGUE_VIG 中命中的英文 slug
TOP5_CN2SLUG = {'英超': 'epl', '西甲': 'laliga', '意甲': 'seriea',
                '德甲': 'bundesliga', '法甲': 'ligue1',
                '英冠': 'championship', '荷甲': 'eredivisie'}

# 五大联赛经验基准（用于判定「6.9% 缺省值」是否离谱）
EXPECTED_BASELINE_MAX = 0.085   # 联赛基准 > 8.5% 就说明取错了源
DEFAULT_VIG = 0.069

ML_SECTION = re.compile(r'【胜平负固定奖金】\s*\n(.*?)(?=\n【|\Z)', re.S)
ROW_RE = re.compile(r'^(\d{4}-\d{2}-\d{2}[ \d:]*),(.+)$', re.M)
KICKOFF_RE = re.compile(r'比赛时间[:：]\s*(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})')
BASE_RE = re.compile(r'机构通道统一基线\s*=\s*\S*?胜平负即盘[:：]\s*([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+)')
PIN_RE = re.compile(r'欧赔\(Pinnacle 即盘[^)]*\)[:：]\s*([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+)')
JC_OFFICIAL_RE = re.compile(r'竞彩官方胜平负即盘[:：]\s*([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+)')
OUT_VIG_RE = re.compile(
    r'竞彩抽水\s*([\d.]+)%\s*·\s*欧盘基准\(([^)]*)\)\s*([\d.]+)%\s*→\s*反抽水比\s*([\d.]+)x')
LEAGUE_RE = re.compile(
    r'赛事[:：][^\n]*?([\u4e00-\u9fa5]{1,4}(?:联|杯|甲|超|乙|冠|K联|职业))')


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def vig_of(h, d, a):
    """欧式赔率 → 抽水率（超额 1 的部分）"""
    if not all([h, d, a]) or min(h, d, a) <= 1.0:
        return None
    return (1.0 / h + 1.0 / d + 1.0 / a) - 1.0


def parse_ml_series(text):
    """【胜平负固定奖金】逐行 → [(ts, h, d, a)]"""
    m = ML_SECTION.search(text)
    if not m:
        return []
    out = []
    for ts, rest in ROW_RE.findall(m.group(1)):
        vals = [_f(x) for x in rest.split(',')[:3]]
        if len(vals) == 3 and all(v is not None and v > 1.0 for v in vals):
            out.append((ts.strip(), vals[0], vals[1], vals[2]))
    return out


def parse_kickoff(text):
    m = KICKOFF_RE.search(text)
    if not m:
        return None
    import datetime
    y, mo, d, hh, mi = (int(x) for x in m.groups())
    try:
        return datetime.datetime(y, mo, d, hh, mi)
    except ValueError:
        return None


def parse_league(text):
    m = LEAGUE_RE.search(text)
    return m.group(1) if m else None


def _near(a, b, tol=0.005):
    return a is not None and b is not None and abs(a - b) <= tol


def check(input_text, out_text=None, eu=None, name=''):
    """→ findings: [dict(level, code, msg, fix)]"""
    F = []

    def add(level, code, msg, fix=''):
        F.append({'level': level, 'code': code, 'msg': msg, 'fix': fix, 'match': name})

    series = parse_ml_series(input_text)
    if not series:
        add('INFO', 'VB00', '输入未含【胜平负固定奖金】数据行 → 本校验器不适用',
            '该文件不提供胜平负赔率时，反抽水维度标「无数据(输入未提供)」')
        return F

    last = series[-1]
    base = BASE_RE.search(input_text)
    base_odds = tuple(_f(x) for x in base.groups()) if base else None
    if base_odds is None and eu:
        try:
            base_odds = tuple(float(x) for x in str(eu).split(','))
        except (TypeError, ValueError):
            base_odds = None

    # ── VB01: 序列是否独立于基线（伪竞彩检测）──
    independent = True
    if base_odds and all(v is not None for v in base_odds):
        independent = not all(_near(last[1 + i], base_odds[i]) for i in range(3))
    if not independent:
        # 数据事实：序列=基线，没有独立竞彩采价。
        # 是否 FAIL 取决于**下游有没有如实披露**——披露了就只是 INFO。
        disclosed = bool(out_text) and (
            '基准价抽水' in out_text or '反抽水比(F1) **不适用' in out_text
            or '反抽水比 不适用' in out_text)
        if disclosed:
            add('INFO', 'VB01',
                '【胜平负】末行 %s 与基线一致 → 本文件无独立竞彩采价；下游已如实披露'
                '（标为基准价抽水 / F1 不适用）' % (last[1:],),
                '')
        else:
            add('FAIL', 'VB01',
                '【胜平负】末行 %s 与声明的机构基线 %s 完全一致 → 该序列不是独立竞彩源，'
                '下游却把它标成「竞彩抽水」' % (last[1:], base_odds),
                '标签须改为「基准价抽水(源:机构基线)」；反抽水比(F1)须显式标「不适用(无独立竞彩源)」')

    # ── VB02: 反抽水比是否退化为恒触发 ──
    if out_text:
        m = OUT_VIG_RE.search(out_text)
        if m:
            printed = _f(m.group(1))
            basis_desc = m.group(2) or ''
            basis_vig = _f(m.group(3))
            ratio = _f(m.group(4))
            measured = vig_of(last[1], last[2], last[3])
            if measured is not None and printed is not None and abs(measured * 100 - printed) > 0.05:
                add('WARN', 'VB02',
                    '打印的抽水 %.2f%% 与按末行赔率实测的 %.2f%% 不符' % (printed, measured * 100),
                    '抽水须由参与该比值的同一组赔率重算，禁跨源混算')
            if basis_vig is not None and basis_vig > EXPECTED_BASELINE_MAX * 100:
                add('WARN', 'VB02', '欧盘基准 %.2f%% 超出联赛经验上限 %.1f%%' % (
                    basis_vig, EXPECTED_BASELINE_MAX * 100), '基准应取低抽水的覆盖机构实测值')

            # VB03: 联赛基准命名空间
            lg = parse_league(input_text)
            if lg in TOP5_CN2SLUG and '缺省' in basis_desc:
                add('FAIL', 'VB03',
                    '联赛「%s」是五大联赛，但打印「欧盘基准(联赛缺省6.9%%)」→ '
                    'LEAGUE_VIG 查表未命中（键是英文 slug「%s」，调用方传中文）'
                    % (lg, TOP5_CN2SLUG[lg]),
                    '参数层做中↔英归一后查表；仍缺则显式标「无数据(该联赛未登记基准)」，'
                    '禁用缺省值冒充查表结果')

            # VB04: 同源同数 → 比值无意义
            if not independent and ratio is not None:
                add('FAIL', 'VB04',
                    '反抽水比 %.2fx 由「基线价 / 联赛基准」算得，分子并非竞彩价 → '
                    '该比值不承载任何信号%s' % (ratio, '（且已触发 F1 标记）' if '触发反抽水' in out_text else ''),
                    '无独立竞彩源时禁输出 F1；F1 触发率若接近 100% 即证明该维度失效')

            # VB05: 输入里存在真实 Pinnacle 价，却没用它做基准
            pin = PIN_RE.search(input_text)
            if pin:
                pv = vig_of(*[_f(x) for x in pin.groups()])
                if pv is not None and basis_vig is not None and abs(pv * 100 - basis_vig) > 2.0:
                    add('WARN', 'VB05',
                        '输入内含 Pinnacle 价（实测抽水 %.2f%%），但基准取 %.2f%%' % (
                            pv * 100, basis_vig),
                        '低抽水覆盖机构应作为欧盘基准；两者差异 >2pp 时须说明取值理由')
    return F


def check_batch(out_dir):
    """批级：统计 F1 触发率与标签一致性 → findings"""
    F = []
    # 双基线交叉校验产物（*.pin.txt）是同一场的第二次运行，不计入比赛场数
    allf = [f for f in sorted(os.listdir(out_dir)) if f.endswith('.txt')]
    files = [f for f in allf if not f.endswith('.pin.txt')]
    n_pin = len(allf) - len(files)
    if not files:
        return [{'level': 'FAIL', 'code': 'VB10', 'msg': '目录内无 .txt 输出: %s' % out_dir,
                 'fix': '', 'match': ''}]
    tot = trig = printed_basis = 0
    sample = []
    for fn in files:
        t = open(os.path.join(out_dir, fn), encoding='utf-8', errors='ignore').read()
        m = OUT_VIG_RE.search(t)
        if not m:
            continue
        tot += 1
        if '触发反抽水' in t:
            trig += 1
        if '缺省' in (m.group(2) or ''):
            printed_basis += 1
        if len(sample) < 3:
            sample.append('%s: %s' % (fn[:38], m.group(0)[:60]))
    if tot:
        rate = trig / tot
        if rate >= 0.5:
            F.append({'level': 'FAIL', 'code': 'VB10',
                      'msg': '批级 F1 触发率 %.0f%% (%d/%d 场·另 %d 份双基线副本已排除) '
                             '—— 阈值 1.30 已失去区分度' % (
                          rate * 100, trig, tot, n_pin),
                      'fix': '先修基础口径（独立竞彩源 / 正确基准），再评估阈值；'
                             '修好前 F1 输出应标「不适用」', 'match': ''})
        if printed_basis == tot:
            F.append({'level': 'FAIL', 'code': 'VB11',
                      'msg': '批级 %d/%d 场欧盘基准均落「缺省6.9%%」→ 联赛基准表整批未命中' % (
                          printed_basis, tot),
                      'fix': '联赛名做中↔英归一后查 LEAGUE_VIG；缺登记须标三态而非缺省',
                      'match': ''})
    return F


# ── 自洽性检查（吸收 v259_consistency）──
RE_DEVIG = re.compile(r'隐含: 主([\d.]+)%/平([\d.]+)%/客([\d.]+)%')
RE_SKEW = re.compile(r'skew精确计算: ([\d.]+)/([\d.]+) = ([\d.]+)%')
RE_LAM = re.compile(r'λ: 主([\d.]+) 客([\d.]+) 总([\d.]+)')
RE_AGG = re.compile(r'聚合: 主([\d.]+)% 平([\d.]+)% 客([\d.]+)%')
RE_TD = re.compile(r'铁胆档: 🔴铁胆\(skew=([\d.]+)')
RE_TD0 = re.compile(r'铁胆档: —\(skew=([\d.]+)<')


def selfcheck_output(text, name=''):
    """输出内部数值自洽性（不查结论对错，只查数字与数字能不能对上）"""
    F2 = []

    def add2(level, code, msg, fix=''):
        F2.append({'level': level, 'code': code, 'msg': msg, 'fix': fix, 'match': name})

    dev = RE_DEVIG.search(text)
    sk = RE_SKEW.search(text)
    lam = RE_LAM.search(text)
    agg = RE_AGG.search(text)

    # SC01 skew = 最高隐含 / 次高隐含
    #   🔴 容差必须覆盖「隐含只保留 1 位小数」带来的舍入误差:
    #   例 拜仁 80.5/11.2 = 718.8，但报 721.0（差 2.2pp）——源数据本就是 1 位小数。
    #   精确阈值: 1 位小数反算的最大相对误差 ≈ (0.05/hi + 0.05/lo)*100pp，取 3% 为安全上界。
    #   超 3% 才是真的口径分叉（如两个不同组的去水结果）。
    if dev and sk:
        vals = [float(x) for x in dev.groups()]
        hi, lo = max(vals), sorted(vals)[-2]
        calc = hi / lo * 100 if lo else None
        rep = float(sk.group(3))
        _rel = abs(calc - rep) / rep * 100 if (calc is not None and rep) else 0
        # 双阈值: 相对 3%（容 1 位小数舍入）**且** 绝对 15pp（容大 skew 的放大效应）
        #   只用相对阈会漏报（999%% vs 真值），只用绝对阈会误报（skew 700 时 3pp 就是常态）
        if calc is not None and _rel > 3.0 and abs(calc - rep) > 15.0:
            add2('FAIL', 'SC01', '隐含%s → skew应为 %.1f%%，但报 %.1f%%（偏差 %.1f%%）' % (vals, calc, rep, _rel),
                 '两者必须同源同口径；skew 禁手算，应由 calc_match 从同一组去水概率直接派生')

    # SC02 λ 与聚合方向
    if lam and agg:
        lh, la = float(lam.group(1)), float(lam.group(2))
        a3 = [float(agg.group(i)) for i in (1, 2, 3)]
        if abs(lh - la) > 0.15:
            lam_dir = 'H' if lh > la else 'A'
            agg_dir = ['H', 'D', 'A'][max(range(3), key=lambda i: a3[i])]
            if lam_dir != agg_dir:
                add2('FAIL', 'SC02', 'λ 主%.2f/客%.2f → %s，但聚合最高为 %s（%.1f/%.1f/%.1f）' % (
                     lh, la, lam_dir, agg_dir, a3[0], a3[1], a3[2]),
                     '泊松λ 与聚合方向背离时，锚与量级会互相矛盾')

    # SC03 聚合概率和
    if agg:
        tot = sum(float(agg.group(i)) for i in (1, 2, 3))
        if abs(tot - 100) > 1.5:
            add2('FAIL', 'SC03', '聚合三向概率和 = %.1f%%（应为 100%%±1.5pp）' % tot,
                 '归一化步骤缺失或某一分支未归一')

    # SC04/SC05 铁胆自洽
    try:
        import calc_v3572 as _CV
        th = _CV.TIEDAN_SKEW_MIN
        td = RE_TD.search(text)
        td0 = RE_TD0.search(text)
        if td and float(td.group(1)) < th:
            add2('FAIL', 'SC04', '判为铁胆但 skew=%.0f < %.0f' % (float(td.group(1)), th),
                 '铁胆与 skew 必须同源（TIEDAN_SKEW_MIN 单一真源）')
        if td0 and float(td0.group(1)) >= th:
            add2('FAIL', 'SC04', '判为非铁胆但 skew=%.0f ≥ %.0f' % (float(td0.group(1)), th), '同上')
        if td and '铁胆 ≠ 100%' not in text:
            add2('FAIL', 'SC05', '铁胆场缺「铁胆 ≠ 100%」声明', '防被读成必胜')
    except Exception:
        pass
    return F2


def _print_selfcheck(a, self_findings):
    if not getattr(a, 'selfcheck', False):
        return
    print()
    print('─' * 72)
    print('数值自洽性检查（SC01-SC05）')
    print('─' * 72)
    if not self_findings:
        print('✅ 全部自洽（隐含/skew/λ/聚合/铁胆 互相对得上）')
    else:
        for f in self_findings:
            print('❌ [%s] %s — %s' % (f['code'], (f['match'] or '')[:40], f['msg']))
            if f.get('fix'):
                print('     ↳ %s' % f['fix'])


def main():
    ap = argparse.ArgumentParser(description='反抽水/凯利基准与标签校验（阶段1·检查器①）')
    ap.add_argument('input', nargs='?', help='输入 txt（标准竞彩格式）')
    ap.add_argument('--output', help='calc_all 输出 txt（用于对照打印值）')
    ap.add_argument('--batch', help='批级模式：calc_all 输出目录')
    ap.add_argument('--eu', help='基线欧赔 主,平,客（输入内无基线行时使用）')
    ap.add_argument('--selfcheck', action='store_true',
                    help='额外跑数值自洽性（SC01-SC05）：隐含/skew/λ/聚合/铁胆 能否互相对上')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    if a.batch:
        findings = check_batch(a.batch)
    elif a.input:
        if not os.path.exists(a.input):
            print('输入不存在: %s' % a.input, file=sys.stderr)
            return 2
        text = open(a.input, encoding='utf-8', errors='ignore').read()
        out = None
        if a.output and os.path.exists(a.output):
            out = open(a.output, encoding='utf-8', errors='ignore').read()
        findings = check(text, out, eu=a.eu, name=os.path.basename(a.input))
    else:
        print(__doc__)
        return 2

    # ── 自洽性（--selfcheck）──
    self_findings = []
    if getattr(a, 'selfcheck', False):
        if a.batch:
            for _fn in sorted(os.listdir(a.batch)):
                if not _fn.endswith('.txt'):
                    continue
                _t = open(os.path.join(a.batch, _fn), encoding='utf-8', errors='ignore').read()
                self_findings += selfcheck_output(_t, _fn)
        elif a.output and os.path.exists(a.output):
            self_findings += selfcheck_output(
                open(a.output, encoding='utf-8', errors='ignore').read(), os.path.basename(a.output))

    if a.json:
        allf = findings + self_findings
        print(json.dumps(allf, ensure_ascii=False, indent=1))
        return 1 if any(f['level'] == 'FAIL' for f in allf) else 0

    print('=' * 72)
    print('check_vig_basis — 反抽水/凯利 基准与标签校验')
    print('=' * 72)
    if not findings:
        print('✅ 未发现名实不符')
        _print_selfcheck(a, self_findings)
        return 1 if any(f['level'] == 'FAIL' for f in self_findings) else 0
    order = {'FAIL': 0, 'WARN': 1, 'INFO': 2}
    for f in sorted(findings, key=lambda x: order.get(x['level'], 9)):
        icon = {'FAIL': '❌', 'WARN': '⚠️', 'INFO': 'ℹ️'}.get(f['level'], '·')
        print('%s [%s] %s' % (icon, f['code'], f['msg']))
        if f.get('fix'):
            print('     ↳ 应改为: %s' % f['fix'])
    _print_selfcheck(a, self_findings)

    allf = findings + self_findings
    fails = sum(1 for f in allf if f['level'] == 'FAIL')
    print('\nFAIL %d · WARN %d · INFO %d' % (
        fails, sum(1 for f in allf if f['level'] == 'WARN'),
        sum(1 for f in allf if f['level'] == 'INFO')))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
