#!/usr/bin/env python3
"""0.28.2 regressions：編號對照表的定位、降階／升回子句、role 註記（skills/status/scripts/）。

本版不動程式行為。這些修正早已在 `v0.28.1` 標記的程式碼裡，但當時版本號沒跟著改，已安裝 0.28.1 的環境
更新不到，所以升一個 patch 版號，並把四項修正鎖成回歸、補上文件登記。

- 修正 1（定位只看形狀）：`ssot_actions_common.glossary_table()` 找第一個第三格寫「主子問題」的表格列，
  往上取最近的標題當節起點，下一個 `^##` 當節尾；沒有這種列回 `(-1, -1, -1, -1)`。
  節號、節名、標題層級與表頭怎麼寫都不影響。→ 規格 1。
- 修正 2（子句不依賴固定句子）：`reassign_question.update_glossary()` 的新子句插在備註裡**最後一個**
  `降為 <編號>` 之後，找不到才附加；對照子句在備註已有「」即指 」時接續，否則另起一句。→ 規格 2。
- 修正 2 續：`promote_question.update_glossary()` 共用同一個定位函式，所以表頭與節名換寫法也找得到列。→ 規格 3。
- 修正 3（role 註記不寫死決策編號）：決策編號只屬於單一專案，工具不能把它寫進別的專案的 plan。→ 規格 4。
- 修正 4（`set_tier.py` 的 reason 規格句與 daily log 區塊標題）→ 規格 5。
- 規格 6（登記）：plugin.json == 0.28.2、CHANGELOG 最上面是 `## 0.28.2`、tests README 與 README 登記本檔。

規格 1～3 直接呼叫函式，不走整條動作鏈（九步由 `run_v0160`／`run_v0161` 負責）；fixture 的編號、名稱與日期
全是編出來的，不對應任何專案。規格 6 精確 pin 當期版號，下一版要照慣例把這兩條改成單調斷言。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
sys.path.insert(0, str(SCRIPTS))

V = '0.28.2'
DATE = '2099-01-01'


def _mods():
    import promote_question as PQ
    import reassign_question as RQ
    import set_tier as ST
    import ssot_actions_common as C
    return C, RQ, PQ, ST


# ---------- 規格 1：glossary_table 只看形狀 ----------

HEAD_A = '| 編號 | 類別 | 備註 |\n|------|------|------|'
HEAD_B = '| 代號 | 分類 | 說明 |\n| :-- | :-- | :-- |'
HEAD_C = '|編號|類別|備註|\n|-|-|-|'


def doc(heading: str, header: str, rows: list[str], *, lead: str = '', tail: str = '') -> str:
    """組一份對照表文件：heading 是表格上方最近的標題，header 是表頭兩行，lead 擺在表格之前。"""
    parts = ['# 名詞', '', '## 說明', '', '一段跟對照表無關的文字。', '']
    if heading:
        parts += [heading, '']
    if lead:
        parts += [lead, '']
    parts += [header, *rows, '']
    if tail:
        parts += [tail, '']
    return '\n'.join(parts)


MAIN_ROW = '| SQ6、SQ7 | 主子問題 | 備註空白 |'
AQ8_ROW = '| AQ8 | 附錄問題 | 附錄甲；列在附錄，不計入主問題覆蓋 |'
AQ7_ROW = '| AQ7 | 附錄問題 | 附錄乙；列在附錄，不計入主問題覆蓋 |'
DID_ROW = '| D-900… | 記錄編號 | 逐條追加 |'


def test_glossary_table() -> None:
    C, _RQ, _PQ, _ST = _mods()
    rows = [MAIN_ROW, AQ8_ROW, AQ7_ROW, DID_ROW]

    # (a) 標題不帶節號、表頭任意寫法、表格前有無關段落與一張無關的兩欄表格，都定位得到
    unrelated = '| 鍵 | 值 |\n| :-- | :-- |\n| a | b |'
    for heading, header in (('#### 對照', HEAD_B), ('## 編號對照', HEAD_A), ('# 一覽', HEAD_C),
                            ('###### 附表', HEAD_B)):
        text = doc(heading, header, rows, lead='這一節列出編號怎麼對應。\n\n' + unrelated, tail='## 其他\n\n文字。')
        lines = text.split('\n')
        sec, sec_end, main_i, last_aq = C.glossary_table(lines)
        assert lines[sec] == heading, (heading, lines[sec])
        assert lines[sec_end] == '## 其他', (heading, lines[sec_end])
        assert lines[main_i] == MAIN_ROW, (heading, lines[main_i])
        # 取最後一個 AQ 列，不是第一個、也不是編號最大的那一個
        assert lines[last_aq] == AQ7_ROW, (heading, lines[last_aq])
        assert sec < main_i < last_aq < sec_end

    # (b) 節尾：`^##` 也吃 `###`／`####`
    for nxt in ('## 其他', '### 其他', '##### 其他'):
        lines = doc('#### 對照', HEAD_B, rows, tail=nxt + '\n\n文字。').split('\n')
        _sec, sec_end, _m, _a = C.glossary_table(lines)
        assert lines[sec_end] == nxt, (nxt, lines[sec_end])
    # 表格是檔尾最後一塊時，節尾＝行數
    lines = doc('#### 對照', HEAD_B, rows).split('\n')
    _sec, sec_end, _m, _a = C.glossary_table(lines)
    assert sec_end == len(lines), (sec_end, len(lines))

    # (c) 表格上方沒有任何標題時，節起點退回第 0 行
    lines = (HEAD_B + '\n' + '\n'.join(rows)).split('\n')
    sec, sec_end, main_i, last_aq = C.glossary_table(lines)
    assert (sec, sec_end) == (0, len(lines)) and lines[main_i] == MAIN_ROW and lines[last_aq] == AQ7_ROW

    # (d) 一個 AQ 列都沒有 → last_aq 回 -1，其餘照常
    lines = doc('#### 對照', HEAD_B, [MAIN_ROW, DID_ROW], tail='## 其他').split('\n')
    sec, _se, main_i, last_aq = C.glossary_table(lines)
    assert lines[main_i] == MAIN_ROW and last_aq == -1 and sec >= 0
    # AQ 像但不完全像的格子不算（`AQ`、`AQ9x`、第二格以外的位置）
    fake = ['| AQ | 附錄問題 | 不帶號 |', '| AQ9x | 附錄問題 | 多了字 |', '| 甲 | AQ9 | 位置不對 |']
    lines = doc('#### 對照', HEAD_B, [MAIN_ROW] + fake, tail='## 其他').split('\n')
    _s, _e, _m, last_aq = C.glossary_table(lines)
    assert last_aq == -1, lines[last_aq]

    # (e) 有表格但沒有「主子問題」那一格 → (-1, -1, -1, -1)
    for rows2 in ([AQ8_ROW, DID_ROW], [], ['| SQ6 | 子問題 | 類別寫法不同 |'], ['| 主子問題 | SQ6 | 欄位順序不對 |']):
        lines = doc('#### 對照', HEAD_B, rows2, tail='## 其他').split('\n')
        assert C.glossary_table(lines) == (-1, -1, -1, -1), rows2
    assert C.glossary_table('# 只有標題\n\n沒有表格。'.split('\n')) == (-1, -1, -1, -1)
    assert C.glossary_table([]) == (-1, -1, -1, -1)

    print('[regression] 規格 1：glossary_table 只看形狀定位（標題無節號／層級不同／表頭任意寫法／表格前有無關內容）、'
          '節尾吃 ### 與檔尾、取最後一個 AQ 列、沒有主子問題列回 (-1, -1, -1, -1): pass')


# ---------- 規格 2：reassign_question.update_glossary ----------

def reassign(text: str, *, src: str = 'SQ7', to: str = 'AQ9', did: str = 'D-900',
             remaining: tuple[str, ...] = ('SQ6',), pm_changed: str = '') -> tuple[str, dict]:
    _C, RQ, _PQ, _ST = _mods()
    return RQ.update_glossary(text, src, to, did, DATE, list(remaining), '問題甲', f'{src}-v1', f'{to}-v1',
                              'M1', ['k1', 'k2'], ['V90'], pm_changed)


def main_row(note: str) -> str:
    return f'| SQ6、SQ7 | 主子問題 | {note} |'


def row_of(text: str, head: str) -> str:
    return next(ln for ln in text.split('\n') if ln.startswith(head))


def test_reassign_update_glossary() -> None:
    _C, _RQ, _PQ, _ST = _mods()
    new_clause = f'SQ7 已依 D-900（{DATE}）降為 AQ9'

    # (a) 備註已有兩個「降為 <編號>」：新子句插在最後一個之後
    note = 'SQ8 已依 D-910 降為 AQ7、SQ9 已依 D-911 降為 AQ8，編號不重用'
    text = doc('#### 對照', HEAD_B, [main_row(note), AQ8_ROW, AQ7_ROW, DID_ROW], tail='## 其他')
    out, info = reassign(text)
    got = row_of(out, '| SQ6 |')
    assert got == ('| SQ6 | 主子問題 | SQ8 已依 D-910 降為 AQ7、SQ9 已依 D-911 降為 AQ8、'
                   f'{new_clause}，編號不重用；舊紀錄的「SQ7」即指 AQ9 |'), got
    assert got.index('降為 AQ8') < got.index('SQ7 已依'), got   # 插在最後一個之後，不是第一個
    assert info['changed'] == ['主子問題列', 'AQ9 列'], info

    # (b) 備註是空的：走附加分支
    text = doc('#### 對照', HEAD_B, [main_row(''), AQ7_ROW], tail='## 其他')
    out, _i = reassign(text)
    got = row_of(out, '| SQ6 |')
    assert got == f'| SQ6 | 主子問題 | {new_clause}，編號不重用；舊紀錄的「SQ7」即指 AQ9 |', got

    # (c) 備註有字但沒有「降為」：附加分支前面補分號
    text = doc('#### 對照', HEAD_B, [main_row('先前沒有降階紀錄'), AQ7_ROW], tail='## 其他')
    out, _i = reassign(text)
    got = row_of(out, '| SQ6 |')
    assert got == ('| SQ6 | 主子問題 | 先前沒有降階紀錄；'
                   f'{new_clause}，編號不重用；舊紀錄的「SQ7」即指 AQ9 |'), got

    # (d) 對照子句兩個分支：備註已有「」即指 」就接續，否則另起
    note = 'SQ8 已依 D-910 降為 AQ7，編號不重用；舊紀錄的「SQ8」即指 AQ7'
    text = doc('#### 對照', HEAD_B, [main_row(note), AQ7_ROW], tail='## 其他')
    out, _i = reassign(text)
    got = row_of(out, '| SQ6 |')
    assert got == ('| SQ6 | 主子問題 | SQ8 已依 D-910 降為 AQ7、'
                   f'{new_clause}，編號不重用；舊紀錄的「SQ8」即指 AQ7、「SQ7」即指 AQ9 |'), got
    assert '舊紀錄的「SQ7」' not in got, got

    # (e) 新列落在最後一個 AQ 列之後（不是表尾、不是第一個 AQ 列之後），而且只差預期的兩行
    rows = [main_row('先前沒有降階紀錄'), AQ8_ROW, AQ7_ROW, DID_ROW]
    text = doc('#### 對照', HEAD_B, rows, tail='## 其他')
    before = text.split('\n')
    out, info = reassign(text)
    after = out.split('\n')
    assert len(after) == len(before) + 1, (len(before), len(after))
    i_main = before.index(main_row('先前沒有降階紀錄'))
    i_ins = before.index(AQ7_ROW) + 1
    assert after[i_ins] == ('| AQ9 | 附錄問題 | 問題甲（原 SQ7；active plan AQ9-v1 supersedes SQ7-v1，'
                            '只改歸屬、primary_model M1 不改；結果鍵 k1／k2，validation item V90）；'
                            '列在附錄，不計入主問題覆蓋 |'), after[i_ins]
    rest = after[:i_ins] + after[i_ins + 1:]
    assert len(rest) == len(before)
    diff = [i for i, (x, y) in enumerate(zip(rest, before)) if x != y]
    assert diff == [i_main], (diff, i_main)

    # (f) 一個 AQ 列都沒有時插在主子問題列之後；remaining 空的話主子問題格寫「（無）」
    text = doc('#### 對照', HEAD_B, [main_row(''), DID_ROW], tail='## 其他')
    out, info = reassign(text, remaining=())
    after = out.split('\n')
    i_main = next(i for i, ln in enumerate(after) if ln.startswith('| （無） |'))
    assert after[i_main + 1].startswith('| AQ9 | 附錄問題 |') and after[i_main + 2] == DID_ROW, after[i_main:i_main + 3]
    assert info['changed'] == ['主子問題列', 'AQ9 列']

    # (g) --primary-model 換過時，新列寫 primary_model 的變動
    text = doc('#### 對照', HEAD_B, [main_row(''), AQ7_ROW], tail='## 其他')
    out, _i = reassign(text, pm_changed='M0')
    assert 'primary_model 由 M0 改為 M1、原 primary 降為敏感度' in row_of(out, '| AQ9 |'), out

    # (h) 沒有對照表就整份原樣回傳
    plain = '# 名詞\n\n## 說明\n\n沒有對照表。\n'
    out, info = reassign(plain)
    assert out == plain and info == {'skipped': '無編號對照表'}, info

    print('[regression] 規格 2：reassign 的新子句插在最後一個「降為」之後／沒有時走附加分支／對照子句兩個分支、'
          '新列落在最後一個 AQ 列之後且只差兩行、沒有對照表回 skipped: pass')


# ---------- 規格 3：promote_question.update_glossary ----------

def test_promote_update_glossary() -> None:
    _C, _RQ, PQ, _ST = _mods()
    note = f'SQ6 已依 D-910（{DATE}）降為 AQ8，編號不重用；舊紀錄的「SQ6」即指 AQ8'
    aq8 = '| AQ8 | 附錄問題 | 問題乙（原 SQ6）；列在附錄，不計入主問題覆蓋 |'
    rows = [f'| SQ7 | 主子問題 | {note} |', aq8, AQ7_ROW, DID_ROW]
    # 表頭與節名換寫法、標題不帶節號，共用同一個定位函式所以照樣找得到列
    text = doc('#### 對照', HEAD_B, rows, tail='## 其他')
    out, info = PQ.update_glossary(text, 'AQ8', 'SQ6', 'D-900', DATE, ['SQ6', 'SQ7'])
    assert info['changed'] == ['主子問題列', 'AQ8 列'], info
    got = row_of(out, '| SQ6、SQ7 |')
    assert got == f'| SQ6、SQ7 | 主子問題 | {note}；AQ8 已依 D-900（{DATE}）升回 SQ6 |', got
    # <from> 那一列註明已升回，而且保留供追溯
    got_aq = row_of(out, '| AQ8 |')
    assert got_aq == ('| AQ8 | 附錄問題 | 問題乙（原 SQ6）；列在附錄，不計入主問題覆蓋'
                      f'（已依 D-900（{DATE}）升回主問題 SQ6，本列保留供追溯） |'), got_aq
    assert out.split('\n').count(got_aq) == 1 and row_of(out, '| AQ7 |') == AQ7_ROW
    assert len(out.split('\n')) == len(text.split('\n'))   # 升回不新增列

    # 備註是空的時候不補分號
    text = doc('## 編號對照', HEAD_A, ['| SQ7 | 主子問題 |  |', aq8], tail='## 其他')
    out, _i = PQ.update_glossary(text, 'AQ8', 'SQ6', 'D-900', DATE, ['SQ6', 'SQ7'])
    assert row_of(out, '| SQ6、SQ7 |') == f'| SQ6、SQ7 | 主子問題 | AQ8 已依 D-900（{DATE}）升回 SQ6 |', out

    # 沒有對照表就整份原樣回傳
    plain = '# 名詞\n\n## 說明\n\n沒有對照表。\n'
    out, info = PQ.update_glossary(plain, 'AQ8', 'SQ6', 'D-900', DATE, ['SQ6'])
    assert out == plain and info == {'skipped': '無編號對照表'}, info

    print('[regression] 規格 3：promote 用同一個定位函式找到主子問題列與 <from> 列、<from> 列註明已升回且保留、'
          '不新增列、沒有對照表回 skipped: pass')


# ---------- 規格 4：工具不寫死決策編號 ----------

ALLOWED_DID = {'D-001', 'D-005'}   # 只准出現在用法範例／參數 metavar／範圍寫法；要加新的先確認是範例不是引用


def test_no_hardcoded_decision_id() -> None:
    # reassign 的 role 註記那一行：決策編號只屬於單一專案，不能由工具寫進別人的 plan
    src = (SCRIPTS / 'reassign_question.py').read_text(encoding='utf-8').split('\n')
    role = [ln for ln in src if '改為 exploratory（' in ln]
    assert len(role) == 1, role
    assert not re.search(r'D-\d{3}', role[0]), role[0]
    assert 'role：由 ' in role[0] and 'exploratory' in role[0], role[0]

    # 通用防線：工具腳本裡的決策編號只能是用法範例裡那幾個
    found: dict[str, list[str]] = {}
    files = sorted(PLUGIN.glob('skills/*/scripts/*.py'))
    assert files, 'skills/*/scripts/*.py 一支都沒掃到'
    for p in files:
        for i, ln in enumerate(p.read_text(encoding='utf-8').split('\n'), 1):
            for m in re.finditer(r'D-\d{3}', ln):
                if m.group(0) not in ALLOWED_DID:
                    found.setdefault(m.group(0), []).append(f'{p.relative_to(PLUGIN)}:{i}')
    assert not found, ('工具裡不要寫死決策編號（決策編號只屬於單一專案，會被寫進別的專案的 SSOT）；'
                       f'新的用法範例要先確認是範例、再加進 ALLOWED_DID：{found}')
    print(f'[regression] 規格 4：role 註記不含決策編號、{len(files)} 支工具腳本的決策編號只有用法範例的 '
          f'{"／".join(sorted(ALLOWED_DID))}: pass')


# ---------- 規格 5：set_tier 的 reason 規格句與 daily log 區塊標題 ----------

def test_set_tier_text() -> None:
    _C, _RQ, _PQ, ST = _mods()
    args = argparse.Namespace(inbox='', reason='', root='')
    ctx = {'changes': {'p:SQ6-v1': 'extended'}, 'labels': {'p:SQ6-v1': '方法甲'}, 'moved': {},
           'inbox': None, 'question': 'SQ6'}
    with tempfile.TemporaryDirectory(prefix='v0282-') as td:
        root = Path(td)
        d = ST.build_decision(root, args, ctx, 'D-900', DATE, 'reviews/x.json', 'backups/x')
        block = ST.daily_log_block(args, ctx, 'D-900', ['analysis/extended-data.yaml'], ['backups/x'],
                                   root, 'reviews/x.json')
    assert ('方法、結果、驗證都可放 Extended Data，問題節點（SQ／AQ）除外；'
            f'只改歸屬標籤，不改數字、結果鍵、plan 或 validation；由 set_tier.py {ST.VERSION} 確定性執行') in d['reason'], d['reason']
    assert d['stage'] == 'figure-design' and d['id'] == 'D-900' and not re.search(r'D-\d{3}', d['rejected'])
    for head in ('### 目的', '### 命令', '### 輸出檔', '### 備份檔', '### 檔案狀態'):
        assert f'\n{head}\n' in block, (head, block)
    assert block.count('### ') == 5, block
    print('[regression] 規格 5：set_tier 的 reason 含規格句、daily log 五個區塊標題（含「### 輸出檔」與'
          '「### 檔案狀態」）: pass')


# ---------- 規格 6：登記 ----------

def test_registration() -> None:
    cl = (PLUGIN / 'CHANGELOG.md').read_text(encoding='utf-8')
    assert cl.startswith(f'# CHANGELOG\n\n## {V}（'), cl[:60]   # 當期精確版號由本檔 pin，下一版改單調斷言
    ver = json.loads((PLUGIN / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))['version']
    assert ver == V, ver
    name = Path(__file__).name
    assert name in (PLUGIN / 'tests/README.md').read_text(encoding='utf-8')
    assert name in (PLUGIN / 'README.md').read_text(encoding='utf-8')
    # 依慣例：前一支回歸測試改為單調斷言，升版不會誤紅
    prev = (PLUGIN / 'tests/run_v0281_regressions.py').read_text(encoding='utf-8')
    assert '(0, 28, 1)' in prev and "cl.startswith(f'# CHANGELOG" not in prev, 'run_v0281 仍精確 pin，升版會誤紅'
    print('[regression] 規格 6：CHANGELOG 最上面是 0.28.2、plugin.json == 0.28.2、tests README 與 README 登記本檔、'
          'run_v0281 已是單調斷言: pass')


def main() -> int:
    test_glossary_table()
    test_reassign_update_glossary()
    test_promote_update_glossary()
    test_no_hardcoded_decision_id()
    test_set_tier_text()
    test_registration()
    print(f'PASS v{V} regressions')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
