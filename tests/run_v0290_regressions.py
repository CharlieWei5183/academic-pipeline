#!/usr/bin/env python3
"""0.29.0 regressions：動作鏈的檔案格式假設與靜默寫錯、全專案關卡只擋新增、每個專案都有 GLOSSARY.md。

0.28.2 的動作鏈把 SSOT 檔的「位元組長相」寫死在文字層——`analysis/results.json` 必須以 2 空白縮排寫出、
`project.yaml` 的 mapping 必須 2／4／6 空白且序列項必須縮排且 `id` 必須是第一欄、`decisions.yaml` 的序列項必須縮排、
`links:` 必須是單行流式清單。這些都是合法 YAML／JSON 的一種寫法而不是唯一寫法，所以換一套排版就整鏈跑不完；
另有五處是「寫下去了、沒有護欄比對」的靜默寫錯。本檔把兩類問題都釘住。

修法的一句話：縮排與排版一律從檔案本身量（JSON 走結構掃描、YAML 走行層級 helper，都在
`skills/status/scripts/ssot_text_format.py`），處理不了的寫法（流式集合）明確中止並說是哪個檔的哪一段，
不准靜默跳過。

規格：
- 規格 1（格式矩陣）：同語意不同格式的 SSOT 共 24 個變體，配對 11 個動作（每個變體至少一個動作、
  11 個動作每支至少一個變體）跑 `--apply`，結果的語意（`safe_load`／`json.loads` 攤平）與控制組逐鍵相同。
  流式集合的兩個變體要明確中止、訊息指出檔名與段落、且所有 SSOT 檔逐位元還原。
- 規格 2（JSON 結構掃描）：縮排 1／2／4／TAB／一行式都定位得到；只替換值那一段，其餘位元組不動
  （`1.50`、`1E2` 這類數字寫法不得被正規化）；`role` 不存在時照該物件既有的分隔補成員，`id` 在最後一欄也可。
- 規格 3（YAML 行層級 helper）：mapping 縮排任意、序列項縮排任意（含不縮排）、`id` 不必是第一欄、
  欄位縮排從該項目的 dash 行量；`decisions.yaml` append 沿用該檔既有的縮排。
- 規格 4（靜默寫錯 1：行尾註解）：`set_block_field` 改既有欄位時保留行尾註解，與 `set_block_status` 一致。
- 規格 5（靜默寫錯 2：rerun 重登）：`update_rerun_state` 先用語意判斷。不是 waived／沒有 rerun 才回 skipped；
  語意上是 waived 但文字層定位不到，丟 ChainError，不會出現「決策寫了、rerun 沒重登」。
  `state.analysis.validation` 的指紋同理。
- 規格 6（靜默寫錯 3：狀態註解）：`add_state_comment` 認任意位數的 D#、沒有 `state:` 時留下可見提示、
  註解縮排沿用原檔。
- 規格 7（靜默寫錯 4：WARNING 要看得到）：鏈裡的 WARNING note 會印到 stdout 的摘要，不只埋在 run log。
- 規格 8（靜默寫錯 5：換行）：CRLF 的 SSOT 檔被動作改過之後仍是 CRLF，不會整份變成 LF。
- 規格 9（links 與區塊純量）：`links:` 流式與區塊序列都讀得到，寫回時沿用原寫法；
  `status_reason` 是 `|-`／`>-` 區塊純量時舊值不會掉。
- 規格 10（後綴字母 id）：`SQ6b`／`AQ7b` 這種帶後綴字母的問題 id 在 `--from`／`--to` 驗證、`Q_ID_RE`、
  `next_question_id` 與各處 `[SA]Q\\d+` 比對裡都通得過，自動配號不會因此撞號。
- 規格 11（成本線性）：頂層鍵很多、又要改一半的 `results.json`，retag 整段限時完成；
  成員查詢走索引、替換走一次 join，兩者任一退回原本的寫法都會超時。替換區間真的重疊時明確中止。
- 規格 12（行尾註解三態）：值的第一個非空白字元決定看法——引號字串、流式集合、純量。
  純量裡的撇號不開啟字串（`don't know  # note` 的註解不會被吃掉）、`#` 前面不是空白就不是註解。
- 規格 13（決策條目的縮排與位置）：區塊純量內容裡的 `- …` 不算欄位內清單；
  `decisions:` 後面還有別的頂層鍵時，新條目插在該區塊尾端而不是檔尾（否則整檔解析不出來）；
  後面只剩空行或註解時輸出逐位元不變。
- 規格 14（收件匣縮排）：收件匣的 dash 與欄位縮排一律從檔案量，不縮排的序列、縮排 4、`id` 在最後一欄都能結案。
- 規格 15（批次摘要帶 WARNING）：子步驟的 WARNING 印在摘要最後面，批次層的節錄一定要帶出來。
- 規格 16（壞檔是 BLOCKER）：SSOT 檔不是合法 YAML／JSON 時，每個動作都印 `BLOCKER <檔名> 無法解析：…`、
  回傳碼非 0、輸出裡沒有 traceback（含被截成尾段的堆疊行）。
- 規格 17（後綴字母 id 的其餘比對）：plan id、決策的 question／links 檢核、時間軸 section 排序也放行後綴字母；
  帶後綴字母的 plan 改 Extended Data 歸屬時，決策的 question 欄要認出那個問題而不是退成 main（規格 17b）。

全專案關卡只擋這次新增的：
- 規格 18（既有項目不擋）：帶既有問題的專案——protocol 未 confirmed、validation item blocker、
  非終態問題、三種 TAMPER、決策舊條目 schema 問題——八個動作 `--dry-run` 與 `--apply` 都 rc=0；
  既有項目全部列進 stdout 摘要、決策的 known_consequences 與步驟紀錄，動作後仍報得出來，
  快照沒有代替使用者確認既有的未確認改動。
- 規格 19（牙齒）：本次動作新造成的問題一定要擋。用影子複本注入三組錯誤（retag 少改一鍵、
  item 的 plan_id 沒改、順手改另一題的 question），乾淨 fixture 與帶既有問題的 fixture 各跑一輪，
  每組都 rc≠0、已還原、SSOT 逐位元回到動作前。
- 規格 20（比對規則）：訊息正規化（指紋、ISO 日期）、id 對照只換完整 token、multiset 只算多出來的那筆、
  關卡自己當掉記成 CRASH 而不是當沒事。
- 規格 21（快照三方合併）：baseline 有 TAMPER 時不走 `--update-snapshot`，改三方合併——
  被搬移的問題帶 TAMPER 時舊值留著、其他題的既有「新增」與「被移除」也保留。
- 規格 22（編號不重用）：自動配號避開快照裡還留著的舊號；明確指到那個號會被拒並說明原因。
- 規格 23（乾淨專案不變）：乾淨 fixture 的語意與控制組相同（規格 1 的格式矩陣一併涵蓋）。
- 規格 24（check_decisions）：舊決策條目有 schema 問題時，只跑 check_decisions 的三個動作照樣完成，
  而且不多跑別的全專案關卡；但本次 D# 自己出 WARNING 仍然擋（「只擋新增」不等於放行本次條目）。

關卡呈現與測試補洞：
- 規格 25（既有項目怎麼呈現）：同一支腳本的同一筆只記一次（不同參數、一條鏈裡封兩次版都算），
  真正重複的訊息按 multiset 保留筆數；呈現用關卡輸出的原行而不是遮過指紋／日期的正規化字串；
  「既有且仍在」與「動作前有、動作後沒有」在決策紀錄裡分兩段、後者不得寫成「與本次動作無關」；
  關卡印了幾行 BLOCKER 才丟 traceback 也要記一筆 CRASH。
- 規格 26（步驟紀錄的順序）：關卡判出本次新增而中止時，步驟紀錄不得留下「本次新增 0 筆」；
  通過時那句的筆數等於實際記下的筆數。
- 規格 27（check_decisions baseline）：append 前的基準真的有取——既有的不擋、append 後新造成的仍擋。
- 規格 28（封兩次版與 `--sq`）：一條鏈裡同一支關卡跑多次，既有發現在 stdout、決策、步驟紀錄都只出現
  一次；`check_plan --sq <目標問題>` 只查那一題，不得把別題的既有發現記成「動作前有、動作後沒有」；
  真的被動作解決掉的既有 blocker 要記成 gone 並請使用者確認。
- 規格 29（暫存空 bib）：check_coverage 用的空 bib 一個 process 只建一個、結束時刪掉，
  動作鏈跑完暫存目錄裡 0 個 `empty-*.bib`。
- 規格 30（佔位 plan 節點）：validation item 的 plan_id 指到不存在的 plan 時，佔位節點要有合法 subtype、
  多出一筆指名是哪個 item 的 WARNING，IR 驗證照過、整頁畫得出來。
- 規格 31（工作區連結的指紋）：dry-run 工作區替原檔擺的檔案層級 symlink（環境鎖定檔、
  `analysis/data-manifest.yaml`、宣告的 inputs）算進指紋，工作區與原根的指紋相同；
  沒有工作區標記檔的根，專案自己的絕對 symlink 照舊跳過。

沒有 `analysis/results.json` 的專案：
- 規格 47（不需要結果鍵的動作照常完成）：沒有 `analysis/results.json` 時——(a) study-design 形狀
  （plan 都封版、沒有 validation.yaml、`state.analysis` 兩區都空）、(b) project-init 剛建好的形狀
  （沒有 plans index、`analysis/plans/` 底下沒有檔）、(c1) 沒有 results.json 卻留著 validation.yaml、
  (c2) `state.analysis.rerun` 留著指紋欄位與 waiver 決策——`reorder_questions`、`reassign_question`、
  `promote_question`、`move_plan`、`demote_plan` 的 dry-run 零寫入、`--apply` 完成（rc=0），
  不建出 results.json／validation.yaml、`state.analysis` 逐字未變；決策、`known_consequences`、stdout、
  步驟紀錄都照實寫「尚無正式結果」，不出現指紋值、「頂層指紋」、「量不到」、沒有「未」前綴的「重接」、
  沒有前綴的「重登」、「retag N 鍵」，也不給「重跑 rerun_all 或另立 waiver」那套建議；
  (a)(b) 是正常階段、0 個提到 results.json 的 WARNING，(c1)(c2) 各剛好一行照實的 WARNING。
- 規格 48（搬結果鍵的三支照舊拒絕）：`move_result`、`move_sensitivity`、`nest_result` 在前置條件就
  拒絕（exit 2、第一次寫檔之前），dry-run 與 apply 都一樣、一個位元都不改，訊息說沒有結果鍵可搬。
- 規格 49（關卡缺檔不變瞎）：`check_plan`、`check_plan --require-confirmed`、`check_validation`、
  `check_coverage`、`check_decisions` 在缺檔時都不丟 traceback、不被記成 CRASH、也不只回報
  「找不到 results」（前後都有就等於沒在看）；`check_coverage` 的 results 是位置參數，少傳一個會被
  當成 bib 而 usage exit 2，所以缺檔也照傳專案裡那個路徑（`check_coverage` 自己認得結果檔不存在），
  `plan_results` 與 `decisions` 則是檔案存在才帶 `--results`；空 bib 的暫存檔跑完 0 個。
- 規格 50（說法只有一個來源）：「尚無正式結果」的旗標跟著 `StalePolicy`／`Carry`／`WaiverState` 走
  （`Carry.copy()` 不得把它丟掉），指紋與 waiver 的每個文字 helper 都照實、不印指紋值也不印佔位標記；
  一致的新專案形狀不印 WARNING。
- 規格 51（waiver 說法與重複句）：尚無正式結果時 waiver 的說法依有沒有 waiver 決策分兩種——沒有就
  每一處都寫「無 waiver 決策」、不得用「本次不重登」「不重登 waiver」；有就寫出那筆決策編號。另外
  同一行（stdout 的一行、步驟紀錄的一則、決策的一個編號項目、檔頭的一行）「尚無正式結果」最多一次、
  「不重登／未重登」最多一次，validation.yaml 本次寫入的檔頭區塊裡同一整句最多一次。
- 規格 52（check_coverage 那一句照實）：那一句由 `coverage_text()` 依 `step_coverage` 記下的實況
  產生（8 支動作共用、不各自寫死）；正常形狀逐字沿用原句（控制組逐位元比保證），動作前就有 TAMPER
  時說出既有筆數與三方合併、不寫「0 tamper」「--update-snapshot」，動作前沒有快照時說出沒有快照與
  本動作做了什麼、不寫「快照不變」「TAMPER 只有」。
- 規格 53（results links 的訊息照實）：沒有 `analysis/results.json` 時 `check_coverage.py` 把它當成
  沒有結果、link 訊息照實說結果檔不存在（不寫成「無鍵」），`coverage_argv` 改回傳專案裡那個路徑。

編號對照表的定位與決策第 (7) 項：
- 規格 58（定位只看形狀）：`glossary_rows()` 認的主子問題列是「第三格剛好是主子問題、第二格是 SQ 編號
  清單或（無）」，AQ 錨點列是「第二格完全是一個 AQ 編號、第三格以附錄問題開頭」；code fence 裡的範例列
  與註解一行都不算、setext 標題與任意層級的節尾都認、編號收後綴字母、只有 AQ 列的表以 AQ 錨點定位
  （主子問題列回 -1）、主子問題列不只一列就不猜要改哪一列（兩種略過原因分開寫）。
- 規格 59（第 (7) 項照實寫）：兩支動作的決策第 (7) 項由 `glossary_decision_text()` 依第 7 步的實際結果
  組出來——兩部分都改到時與原本那句逐位元相同，只改到一部分就只寫那一部分，專案沒有 `GLOSSARY.md`
  或定位不到就寫未更新（原因字串與步驟紀錄同一個）、不留備份，決策與第 7 步的步驟紀錄說同一件事。

每個專案都有 `GLOSSARY.md`：
- 規格 60（三種現況）：`init_glossary.py` 依專案現況走三條路——沒有這個檔就照範本建（四段、編號對照表
  列 goals 的編號）、有檔而對照表還沒有任何編號列就只在檔尾追加那一節（既有內容逐位元保留）、
  已經有編號列就零寫入零決策（所以重跑第二次什麼都不會發生）。`{{ID_ROWS}}` 收後綴字母編號、
  把 `question` 壓成單行並轉義 `|`、goals 空時寫「（無）」、goals 以外的頂層鍵一律不寫。
- 規格 61（護欄）：`--dry-run` 整棵樹零寫入；`--expect-token` 不符 exit 2 且不寫檔；`GLOSSARY.md`
  不在 `TOKEN_FILES`，所以 dry-run 之後才冒出來的檔由「重新判斷檔案現況」擋住（入口與鏈各一層），
  不會被蓋掉；鏈中失敗時新建的檔刪掉、既有檔逐位元還原。
- 規格 62（新專案形狀）：project-init 剛建好（有快照與沒快照）與連 `decisions.yaml` 都還沒有的專案都
  rc=0——建出檔、記一筆決策、`check_decisions` 乾淨；量得到指紋的專案前後相同，量不到的前後都量不到；
  決策、stdout 與步驟紀錄不提 fingerprint、指紋、waiver、reaffirmed 與「尚無正式結果」。
- 規格 63（端到端）：`init_glossary.py` 自己產的表，`reassign_question.py` 與 `promote_question.py`
  都定位得到並改對那兩列（決策第 (7) 項是「兩部分都改到」那一種）；有結果與尚無正式結果兩種專案各一輪。
- 規格 64（建檔提示）：沒有 `GLOSSARY.md` 時第 7 步的 note 與決策第 (7) 項各多一句建檔提示，說法由
  `ssot_actions_common.py` 一處給（兩支動作不自己拼）；其他三種實況一個字都不提。
- 規格 65（promote 跳過 fence）：`promote_question.update_glossary()` 找來源列時與 `glossary_rows`
  用同一個 fence 判斷——fence 內外都有同編號時只改 fence 外那列，只有 fence 裡有時一列都不改。
- 規格 66（範本與文件）：範本四段齊全、只有一個代換記號、寫明與 `project.yaml` 的 `glossary` 的分工；
  用得到它的 skill、agent 與 README 各自都寫了。

寫進專案的說法、判斷順序、首次建檔的檔頭、步驟紀錄的 baseline 形式：
- 規格 67（理由與決策的說法）：沒給 `--reason` 時理由第一段是「使用者裁定建立 GLOSSARY.md（未附理由）」
  （與其他動作同一種寫法，不宣稱使用者做過別的裁定）；決策第 (1) 項建立那一種寫「縮寫、變數、方法三段
  只有表頭」（編號對照表已經依 goals 填了編號，不能說成四段都空）。建立與追加 × 有無 `--reason` 四組的
  reason 完整字串與兩段順序都釘住；project-init 第 7 步的命令帶 `--reason`，新專案帳本裡的理由才照實。
- 規格 68（判斷順序）：① 沒有這個檔 → 建立；② `glossary_rows` 認得任何一列 → 不寫不記決策；
  ③ 檔裡已有一個標題文字恰為「編號對照表」（ATX 任一層級或 setext；fence 裡的不算）→ 同樣不寫不記決策，
  說明寫出「第 7 步會略過、編號要寫成 SQ／AQ 加數字」；④ 其他 → 檔尾追加。②③ 的順序不得調換，
  ③ 那一種不接「之後由那兩支維護」（與第 7 步會略過矛盾）；`### 編號對照` 這種不同寫法的標題不算。
- 規格 69（建表自檢）：建立與追加都在寫檔前用 `glossary_rows` 量新內容——主子問題列不是恰好一列、或認得的
  AQ 錨點列數不等於 goals 的附錄問題數時不中止，照常寫檔，但 stdout 與步驟紀錄各多一行 WARNING 列出不是
  SQ／AQ 加數字的編號、決策第 (1) 項照實補一句；編號都合格式而只是列數對不上時不得說成格式不對。
- 規格 70（首次建檔的檔頭）：`decisions.yaml` 不存在或空檔時的檔頭取 `method` 開頭的腳本名，
  不寫死某兩支；取不到就用通稱。已經存在的檔頭一個位元都不動。
- 規格 71（baseline 形式）：步驟紀錄的 `gate_baseline` 存當次輸出的原行，不存比對用的正規化鍵
  （路徑裡的指紋與日期被遮成 `<FP>`／`<DATE>` 時紀錄看起來像壞掉）；比對鍵與比對語意不變。

版號、CHANGELOG 與文件登記：
- 規格 72（登記）：CHANGELOG 最上面就是 `## 0.29.0`、`plugin.json` 恰為 0.29.0、`tests/README.md` 與
  `README.md` 都登記本檔，且 `run_v0282_regressions.py` 已照慣例改成單調斷言（當期精確版號改由本檔 pin）。
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / 'skills/status/scripts'
sys.path.insert(0, str(PLUGIN / 'tests'))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(PLUGIN / 'skills/submission-prep/scripts'))

import yaml  # noqa: E402

import run_v0161_regressions as T1  # noqa: E402
import ssot_actions_common as C  # noqa: E402
import ssot_text_format as TF  # noqa: E402

V = '0.29.0'
DATE = '2099-01-01'
BATCH_ENV = C.BATCH_STEP_ENV      # =1：略過動作自己的工作區 dry-run，只跑一次鏈（測試才這樣用）


# ======================================================================
# 共用：fixture、執行、快照
# ======================================================================

_BASE: Path | None = None


def base_fixture(tmp: Path) -> Path:
    global _BASE
    if _BASE is None:
        _BASE = tmp / '_base'
        T1.build_fixture(_BASE)
    return _BASE


def copy_fixture(tmp: Path, name: str) -> Path:
    dst = tmp / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(base_fixture(tmp), dst)
    return dst


SSOT = ('project.yaml', 'decisions.yaml', 'analysis/results.json', 'analysis/validation.yaml',
        'analysis/plans/index.yaml', 'analysis/figures/manifest.json', 'analysis/extended-data.yaml',
        'submission/package.yaml')


def run_action(script: str, root: Path, *args: str, plugin: Path | None = None,
               dry: bool = False, env_extra: dict[str, str] | None = None) -> tuple[int, str]:
    """對 root 直接 apply 一次（BATCH=1 省掉工作區 dry-run），回 (rc, 輸出)。

    plugin：改跑影子複本裡的腳本（注入錯誤驗牙用）。dry：改跑 --dry-run（動作自己開工作區）。
    env_extra：只加在子行程的環境變數（例如把 TMPDIR 指到自己的資料夾，數暫存檔）。
    """
    base = plugin or PLUGIN
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', **(env_extra or {}))
    if not dry:
        env[BATCH_ENV] = '1'
    sub = 'skills/submission-prep/scripts' if script == 'package_edit.py' else 'skills/status/scripts'
    proc = subprocess.run([sys.executable, '-B', str(base / sub / script), str(root), *args,
                           '--dry-run' if dry else '--apply', '--date', DATE],
                          capture_output=True, text=True, encoding='utf-8', env=env, cwd='/tmp')
    return proc.returncode, (proc.stdout or '') + (proc.stderr or '')


def run_dry(script: str, root: Path, *args: str) -> tuple[int, str]:
    return run_action(script, root, *args, dry=True)


def flat(obj, p: str = '') -> dict[str, object]:
    if isinstance(obj, dict):
        out: dict[str, object] = {}
        for k, v in obj.items():
            out.update(flat(v, f'{p}.{k}'))
        return out
    if isinstance(obj, list):
        out = {}
        for i, v in enumerate(obj):
            out.update(flat(v, f'{p}[{i}]'))
        return out
    return {p: obj}


SKIP = ('fingerprint', 'content_hash', 'reaffirmed_', 'token', 'confirmed_at', 'sealed')
FP_RE = re.compile(r'\b[0-9a-f]{20}\b')


def mask(value):
    """字串裡內嵌的 20 位 hex（指紋／封版雜湊）換成佔位符。

    動作鏈寫進 `decisions.yaml` 散文的「舊指紋 → 新指紋」本來就隨變體改動的位元組而不同，
    那是合理差異；雜湊本身的鍵已被 SKIP 排掉，散文裡的要在這裡遮掉。
    """
    return FP_RE.sub('<fp>', value) if isinstance(value, str) else value


def semantics(root: Path) -> dict[str, dict[str, object]]:
    """每個 SSOT 檔的語意（攤平）；指紋、封版雜湊與 reaffirmed 標記排除——變體改了位元組，這些本來就會不同。"""
    snap: dict[str, dict[str, object]] = {}
    rels = list(SSOT) + ['analysis/plans/' + x.name for x in sorted((root / 'analysis/plans').glob('*.yaml'))]
    for rel in rels:
        path = root / rel
        if not path.is_file():
            continue
        raw = path.read_text(encoding='utf-8')
        doc = json.loads(raw) if rel.endswith('.json') else yaml.safe_load(raw)
        snap[rel] = {k: mask(v) for k, v in flat(doc).items() if not any(s in k for s in SKIP)}
    return snap


def bytes_of(root: Path) -> dict[str, bytes]:
    out = {}
    for rel in SSOT:
        path = root / rel
        if path.is_file():
            out[rel] = path.read_bytes()
    return out


# ======================================================================
# 規格 1 的格式變體
# ======================================================================

class _IndentDumper(yaml.SafeDumper):
    """序列項比父鍵縮排（PyYAML 預設不縮排）。"""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def _ydump(doc, dumper=yaml.SafeDumper, **kw) -> str:
    return yaml.dump(doc, Dumper=dumper, allow_unicode=True, sort_keys=False, default_flow_style=False, **kw)


def _yfile(path: Path, dumper=yaml.SafeDumper, **kw) -> None:
    path.write_text(_ydump(yaml.safe_load(path.read_text(encoding='utf-8')), dumper=dumper, **kw), encoding='utf-8')


def _jfile(path: Path, **kw) -> None:
    doc = json.loads(path.read_text(encoding='utf-8'))
    path.write_text(json.dumps(doc, ensure_ascii=False, **kw) + '\n', encoding='utf-8')


def _crlf(path: Path) -> None:
    path.write_bytes(path.read_text(encoding='utf-8').replace('\n', '\r\n').encode('utf-8'))


def _links_block(root: Path) -> None:
    """只把 `links:` 的流式清單改成區塊序列，其餘位元組不動。"""
    path = root / 'project.yaml'
    out = []
    for ln in path.read_text(encoding='utf-8').split('\n'):
        head, val, cmt = TF.split_field_line(ln)
        if head.strip() == 'links:' and val.strip().startswith('[') and yaml.safe_load(val):
            ind = ' ' * TF.indent_of(ln)
            out.append(f'{ind}links:' + cmt)
            out += [f'{ind}  - {json.dumps(x, ensure_ascii=False)}' for x in yaml.safe_load(val)]
        else:
            out.append(ln)
    path.write_text('\n'.join(out), encoding='utf-8')


def _flow_top(path: Path, key: str) -> None:
    """把某個頂層鍵整段改寫成流式集合（合法 YAML，但沒有行可以逐行改）。

    流式那一段用 JSON 寫（JSON 是 YAML 的子集，日期一律當字串），所以不會因為值裡有 `: ` 而寫壞。
    """
    doc = yaml.safe_load(path.read_text(encoding='utf-8'))
    sub = doc.pop(key)
    body = [_ydump({k: v}).rstrip('\n') for k, v in doc.items()]
    body.append(key + ': ' + json.dumps(sub, ensure_ascii=False, default=str))
    text = '\n'.join(body) + '\n'
    got = yaml.safe_load(text)
    assert set(got) == set(doc) | {key}, f'{key} 流式變體寫壞了：頂層鍵不一致'
    assert got[key] == json.loads(json.dumps(sub, default=str)), f'{key} 流式變體寫壞了：語意不一致'
    path.write_text(text, encoding='utf-8')


def _de_trailing_key(root: Path) -> None:
    """decisions.yaml 用 `sort_keys=True` 重寫，並加一個排在 `decisions` 之後的頂層鍵。

    `decisions:` 因此不再是檔案最後一段：新條目若 append 到檔尾，就成了「頂層鍵底下又冒出序列項」，
    整檔解析不出來。
    """
    path = root / 'decisions.yaml'
    doc = yaml.safe_load(path.read_text(encoding='utf-8'))
    doc['schema_version'] = 1
    path.write_text(yaml.dump(doc, Dumper=_IndentDumper, allow_unicode=True, sort_keys=True,
                              default_flow_style=False), encoding='utf-8')


def _items_first(root: Path) -> None:
    path = root / 'analysis/validation.yaml'
    doc = yaml.safe_load(path.read_text(encoding='utf-8'))
    path.write_text(_ydump({'items': doc.pop('items'), **doc}, dumper=_IndentDumper), encoding='utf-8')


def _reseal_plans(root: Path) -> None:
    for pp in sorted((root / 'analysis/plans').glob('*-v*.yaml')):
        doc = yaml.safe_load(pp.read_text(encoding='utf-8'))
        doc.pop('content_hash', None)
        pp.write_text(_ydump(doc), encoding='utf-8')
        subprocess.run([sys.executable, '-B', str(PLUGIN / 'skills/study-design/scripts/seal_artifact.py'), str(pp),
                        '--kind', 'plan', '--root', str(root), '--confirmed-by', 'user', '--date', '2026-09-10'],
                       capture_output=True, text=True, check=True)


# 變體名 → 套用函式。語意一律不變，只動排版。
VARIANTS: dict[str, object] = {
    'control': lambda r: None,
    'rj_indent1': lambda r: _jfile(r / 'analysis/results.json', indent=1),
    'rj_indent4': lambda r: _jfile(r / 'analysis/results.json', indent=4),
    'rj_tab': lambda r: _jfile(r / 'analysis/results.json', indent='\t'),
    'rj_oneline': lambda r: _jfile(r / 'analysis/results.json', separators=(',', ':')),
    'mf_indent1': lambda r: _jfile(r / 'analysis/figures/manifest.json', indent=1),
    'mf_oneline': lambda r: _jfile(r / 'analysis/figures/manifest.json', separators=(',', ':')),
    'py_dump_flat': lambda r: _yfile(r / 'project.yaml'),
    'py_dump_indent': lambda r: _yfile(r / 'project.yaml', dumper=_IndentDumper),
    'py_indent4': lambda r: _yfile(r / 'project.yaml', dumper=_IndentDumper, indent=4),
    'py_sortkeys': lambda r: (r / 'project.yaml').write_text(
        yaml.dump(yaml.safe_load((r / 'project.yaml').read_text(encoding='utf-8')), Dumper=_IndentDumper,
                  allow_unicode=True, sort_keys=True, default_flow_style=False), encoding='utf-8'),
    'py_links_block': _links_block,
    'va_dump_flat': lambda r: _yfile(r / 'analysis/validation.yaml'),
    'va_dump_indent': lambda r: _yfile(r / 'analysis/validation.yaml', dumper=_IndentDumper),
    'va_items_first': _items_first,
    'de_dump_flat': lambda r: _yfile(r / 'decisions.yaml'),
    'de_dump_indent': lambda r: _yfile(r / 'decisions.yaml', dumper=_IndentDumper),
    'de_trailing_key': _de_trailing_key,
    'idx_dump_flat': lambda r: _yfile(r / 'analysis/plans/index.yaml'),
    'idx_flow': lambda r: (r / 'analysis/plans/index.yaml').write_text(
        yaml.dump(yaml.safe_load((r / 'analysis/plans/index.yaml').read_text(encoding='utf-8')), Dumper=_IndentDumper,
                  allow_unicode=True, sort_keys=False, default_flow_style=True), encoding='utf-8'),
    'plan_dump_reseal': _reseal_plans,
    'crlf_project': lambda r: _crlf(r / 'project.yaml'),
    'crlf_all': lambda r: [_crlf(r / rel) for rel in
                           ('project.yaml', 'decisions.yaml', 'analysis/validation.yaml',
                            'analysis/plans/index.yaml', 'analysis/results.json',
                            'analysis/figures/manifest.json')],
    # 以下兩個不支援，必須明確中止
    'py_state_flow': lambda r: _flow_top(r / 'project.yaml', 'state'),
    'py_goals_flow': lambda r: _flow_top(r / 'project.yaml', 'goals'),
}

# 變體刻意加進去的頂層鍵：拿它當「清單後面還有別的頂層內容」的現場，語意本來就與控制組不同，比對時排除。
VARIANT_EXTRA_KEYS: dict[str, set[tuple[str, str]]] = {
    'de_trailing_key': {('decisions.yaml', '.schema_version')},
}

FLOW_VARIANTS = ('py_state_flow', 'py_goals_flow')
# 流式集合要「該擋的擋、不該擋的不擋」：會改到那一段的動作明確中止，沒碰那一段的動作照常走完。
FLOW_ABORT = {('py_state_flow', 'nest_result'), ('py_goals_flow', 'reassign_question')}

ACTIONS: dict[str, tuple[str, list[str]]] = {
    'reassign_question': ('reassign_question.py', ['--from', 'SQ2']),
    'promote_question': ('promote_question.py', ['--from', 'AQ1']),
    'set_tier': ('set_tier.py', ['--node', 'p:SQ2-v1=extended']),
    'set_figure_role': ('set_figure_role.py', ['--figure', 'F_a=extended']),
    'reorder_questions': ('reorder_questions.py', ['--list', 'sub_questions', '--order', 'SQ2,SQ1']),
    'move_plan': ('move_plan.py', ['--plan', 'AQ1-v1', '--to-question', 'AQ2']),
    'move_result': ('move_result.py', ['--key', 'k2', '--to-plan', 'SQ2-v1']),
    'move_sensitivity': ('move_sensitivity.py', ['--plan', 'SQ1-v1', '--item', 'R2', '--to-plan', 'SQ2-v1']),
    'nest_result': ('nest_result.py', ['--key', 'k2', '--under', 'k1']),
    'demote_plan': ('demote_plan.py', ['--plan', 'AQ1-v1', '--to-plan', 'SQ1-v1']),
    'package_edit': ('package_edit.py', ['--exclude-entry', 'F_a']),
}

# 變體 → 要跑的動作。每個變體至少一支、11 支動作每支至少出現一次；
# 格式敏感面大的變體配「全部敏感面都吃」的動作（retag ＋ project ＋ validation ＋ decisions 都會改到）。
PAIRS: list[tuple[str, str]] = [
    ('control', 'reassign_question'), ('control', 'promote_question'), ('control', 'set_tier'),
    ('control', 'set_figure_role'), ('control', 'reorder_questions'), ('control', 'move_plan'),
    ('control', 'move_result'), ('control', 'move_sensitivity'), ('control', 'nest_result'),
    ('control', 'demote_plan'), ('control', 'package_edit'),
    ('rj_indent1', 'move_result'), ('rj_indent4', 'nest_result'), ('rj_tab', 'move_sensitivity'),
    ('rj_oneline', 'demote_plan'),
    ('mf_indent1', 'set_figure_role'), ('mf_oneline', 'set_figure_role'),
    ('py_dump_flat', 'reassign_question'), ('py_dump_indent', 'move_plan'), ('py_indent4', 'promote_question'),
    ('py_sortkeys', 'reorder_questions'), ('py_links_block', 'move_result'),
    ('va_dump_flat', 'nest_result'), ('va_dump_indent', 'move_sensitivity'), ('va_items_first', 'move_result'),
    ('de_dump_flat', 'set_tier'), ('de_dump_flat', 'reassign_question'), ('de_dump_indent', 'package_edit'),
    ('de_trailing_key', 'reassign_question'), ('de_trailing_key', 'set_tier'),
    ('idx_dump_flat', 'demote_plan'), ('idx_flow', 'move_plan'), ('plan_dump_reseal', 'move_sensitivity'),
    ('crlf_project', 'reorder_questions'), ('crlf_all', 'move_result'),
    ('py_state_flow', 'nest_result'), ('py_state_flow', 'set_tier'),
    ('py_goals_flow', 'reassign_question'), ('py_goals_flow', 'set_figure_role'),
]


def refix_fingerprints(root: Path) -> None:
    """變體改了位元組，指紋跟著變；重算再接回去，才不會被「關卡擋指紋」這個干擾項蓋掉格式的問題。

    除了 validation.yaml 的頂層兩欄，`project.yaml` 的 `state.analysis.rerun`（三欄）與
    `state.analysis.validation`（兩欄）也要接回現值：這些欄位動作前就與現值不符時，動作會刻意
    不重登 waiver、不帶新值（規格 32～34），而那不是格式矩陣要量的東西。`previous_waiver` 底下
    的歷史值縮排更深，`find_key` 指定縮排就碰不到。
    """
    res_fp = T1.T0.results_fingerprint(root / 'analysis/results.json')
    out = subprocess.run([sys.executable, '-B', str(PLUGIN / 'skills/validate-results/scripts/check_validation.py'),
                          str(root), '--source-fingerprint-only'], capture_output=True, text=True, check=True)
    data = json.loads(out.stdout[out.stdout.index('{'):])
    src = data['source_fingerprint']
    for rel in ('analysis/validation.yaml', 'project.yaml'):
        path = root / rel
        raw = path.read_bytes()
        nl = b'\r\n' if b'\r\n' in raw else b'\n'
        text = raw.decode('utf-8')
        for key, new in (('results_fingerprint', res_fp), ('source_fingerprint', src)):
            lines = text.split(nl.decode())
            for i, ln in enumerate(lines):
                if ln.startswith(key + ':'):
                    lines[i] = TF.replace_value(ln, new)
            text = nl.decode().join(lines)
        path.write_bytes(text.encode('utf-8'))
    refix_state_fingerprints(root, {'fingerprint': src, 'results_fingerprint': res_fp,
                                    'input_fingerprint': data['input_fingerprint']})


def refix_state_fingerprints(root: Path, fp: dict[str, str]) -> None:
    """project.yaml 的 state.analysis.rerun／validation 指紋接回現值（只碰那兩個區塊的直屬欄位）。"""
    path = root / 'project.yaml'
    raw = path.read_bytes()
    nl = '\r\n' if b'\r\n' in raw else '\n'
    lines = raw.decode('utf-8').split(nl)
    blocks = ((('state', 'analysis', 'rerun'),
               (('fingerprint', fp['fingerprint']), ('input_fingerprint', fp['input_fingerprint']),
                ('results_fingerprint', fp['results_fingerprint']))),
              (('state', 'analysis', 'validation'),
               (('results_fingerprint', fp['results_fingerprint']), ('source_fingerprint', fp['fingerprint']))))
    for keys, fields in blocks:
        try:
            at, ind, end = TF.map_path(lines, keys, 'project.yaml')
        except Exception:
            continue
        if at < 0:
            continue
        f_ind = TF.child_map_indent(lines, at, ind, end)
        if f_ind < 0:
            continue
        for key, value in fields:
            i = TF.find_key(lines, key, at + 1, end, f_ind)
            if i >= 0:
                lines[i] = TF.replace_value(lines[i], value)
    path.write_bytes(nl.join(lines).encode('utf-8'))


def test_format_matrix(tmp: Path) -> None:
    assert set(a for _v, a in PAIRS) == set(ACTIONS), '11 個動作每支都要被涵蓋'
    assert set(v for v, _a in PAIRS) == set(VARIANTS), '每個變體都要被涵蓋'
    oracle: dict[str, dict[str, dict[str, object]]] = {}
    for variant, action in PAIRS:
        script, args = ACTIONS[action]
        root = copy_fixture(tmp, f'm_{variant}__{action}')
        VARIANTS[variant](root)
        if variant != 'control':
            refix_fingerprints(root)
        before = bytes_of(root)
        rc, out = run_action(script, root, *args)
        if (variant, action) in FLOW_ABORT:
            assert rc != 0, f'{variant} × {action}: 流式集合應明確中止，卻 rc=0\n{out[-1500:]}'
            section = variant.split('_')[1]
            assert 'project.yaml' in out and '流式集合' in out and section in out, \
                f'{variant} × {action}: 中止訊息沒有指出檔名與段落\n{out[-1500:]}'
            assert bytes_of(root) == before, f'{variant} × {action}: 中止後 SSOT 檔沒有逐位元還原'
            shutil.rmtree(root)
            continue
        assert rc == 0, f'{variant} × {action}: rc={rc}\n{out[-2500:]}'
        snap = semantics(root)
        if variant == 'control':
            oracle[action] = snap
        else:
            ref = oracle[action]
            skip_extra = VARIANT_EXTRA_KEYS.get(variant, set())
            diffs = []
            for rel in sorted(set(ref) | set(snap)):
                a, b = ref.get(rel, {}), snap.get(rel, {})
                diffs += [f'{rel}{k}: {a.get(k)!r} != {b.get(k)!r}' for k in sorted(set(a) | set(b))
                          if a.get(k) != b.get(k) and (rel, k) not in skip_extra]
            assert not diffs, f'{variant} × {action}: 語意與控制組不同\n  ' + '\n  '.join(diffs[:8])
        shutil.rmtree(root)
    print(f'[regression] 規格 1：格式矩陣 {len(VARIANTS)} 變體 × {len(ACTIONS)} 動作、{len(PAIRS)} 組配對'
          f'（含 {len(FLOW_ABORT)} 組明確中止、流式變體的其餘動作照常走完）: pass')


# ======================================================================
# 規格 2：JSON 結構掃描
# ======================================================================

def test_json_scan() -> None:
    import set_figure_role as SR
    # 數字與轉義寫法不得被正規化；縮排 1／2／4／TAB／一行式都定位得到
    for raw in ('{\n "a": {"plan_id": "P1", "n": 1.50},\n "b": {"plan_id": "P2"}\n}\n',
                '{\n\t"a": {\n\t\t"plan_id": "P1",\n\t\t"n": 1E2\n\t},\n\t"b": {"plan_id": "P2"}\n}\n',
                '{"a":{"plan_id":"P1","n":0.10},"b":{"plan_id":"P2"}}\n',
                '{\n    "a": {\n        "plan_id": "P1",\n        "n": -0.0\n    },\n    "b": {"plan_id": "P2"}\n}\n'):
        new, info = C.retag_results(raw, {'a': 'P9'})
        assert json.loads(new)['a']['plan_id'] == 'P9', raw
        assert json.loads(new)['b'] == json.loads(raw)['b']
        assert info['changed_lines'] == 1, info
        # 只有 plan_id 那一段變了：把它換回去就該逐位元回到原文
        assert new.replace('"P9"', '"P1"', 1) == raw, f'除 plan_id 外位元組被動到\n{raw!r}\n{new!r}'
    # description 前綴與 model_id 一起改，數字寫法仍不動
    raw = '{\n  "a": {"model_id": "M1", "description": "d", "plan_id": "P1", "n": 2.500}\n}\n'
    new, _ = C.retag_results(raw, {'a': 'P9'}, {'a': ('M1', 'M2', 'pre: ')})
    assert '"n": 2.500' in new and '"description": "pre: d"' in new and '"model_id": "M2"' in new, new
    # manifest：role 不存在時補成員（一行式、id 在最後一欄都要可以）
    one = json.dumps({'figures': [{'id': 'F_x', 'role': 'main'}, {'id': 'F_y', 'caption': 'c'}]},
                     separators=(',', ':')) + '\n'
    got, info = SR.set_roles(one, {'F_x': 'extended', 'F_y': 'main'})
    assert json.loads(got)['figures'][1]['role'] == 'main' and info['inserted'] == ['F_y'], got
    assert '{"id":"F_y","role":"main","caption":"c"}' in got, got
    last = '{\n  "figures": [\n    {\n      "caption": "c",\n      "id": "F_y"\n    }\n  ]\n}\n'
    got2, _ = SR.set_roles(last, {'F_y': 'main'})
    assert json.loads(got2)['figures'][0]['role'] == 'main', got2
    assert got2 == last.replace('"id": "F_y"', '"id": "F_y",\n      "role": "main"'), got2
    # 一行式仍走得到既有的 parse-and-compare 護欄：role 不是字串就中止
    bad = '{"figures":[{"id":"F_z","role":{"a":1}}]}\n'
    try:
        SR.set_roles(bad, {'F_z': 'main'})
        raise AssertionError('role 是物件時應中止')
    except C.ChainError as exc:
        assert 'role' in str(exc), exc
    # 掃描器對每個 path 取回的原文，解出來要與 json.loads 的結果一致（各種縮排都一樣）
    ref = {'_note': 'x', 'arr': [1, {'a': [True, None, -1.5e3]}, 'q\\"uote'], 'obj': {'k': {'n': 0, 's': '中文'}}}
    for kw in ({'indent': 2}, {'indent': 1}, {'indent': '\t'}, {'separators': (',', ':')}, {'indent': 4}):
        raw = json.dumps(ref, ensure_ascii=False, **kw)
        jt = TF.JsonText(raw, 'fixture.json')
        assert jt.keys() == list(ref), (kw, jt.keys())
        for k in ref:
            assert json.loads(jt.raw((k,))) == ref[k], (kw, k, jt.raw((k,)))
        assert json.loads(jt.raw(('arr', 1, 'a', 2))) == -1500.0, kw
        assert jt.index_of(('arr',), 'a', [True, None, -1500.0]) == 1, kw
        assert not jt.has(('obj', 'missing')) and jt.length(('arr',)) == 3, kw
    # 手寫的數字與轉義寫法取回來要逐字相同（`json.dumps` 會把它們正規化，所以不能用 round-trip 來驗）
    hand = '{\n "a": {"n": -1.5e3, "m": 0.10, "z": 1E2, "s": "a\\u4e2d"},\n "b": {"n": 1}\n}\n'
    jt = TF.JsonText(hand, 'fixture.json')
    assert [jt.raw(('a', k)) for k in ('n', 'm', 'z', 's')] == ['-1.5e3', '0.10', '1E2', '"a\\u4e2d"'], \
        [jt.raw(('a', k)) for k in ('n', 'm', 'z', 's')]
    print('[regression] 規格 2：JSON 結構掃描（縮排 1／2／4／TAB／一行式、數字寫法、role 補成員）: pass')


# ======================================================================
# 規格 3：YAML 行層級 helper
# ======================================================================

PY_FLAT = """goals:
  sub_questions:
  - question: "問一"
    status: open
    id: QA1
    links: ["results:kk"]
  - id: QA2
    status: open
state:
  next_stage: "x"
"""

PY_WIDE = """goals:
    sub_questions:
        -   id: QA1
            status: open
            links:
              - "results:kk"
state:
    next_stage: "x"
"""

# 鍵與不縮排序列之間夾一行註解（區塊不能停在那行），且下一個頂層鍵前面的註解仍歸下一個鍵
PY_COMMENT = """goals:
  sub_questions:
  # 清單前的註解
  - id: QA1
    status: open
    links: ["results:kk"]
# 這行屬於 state
state:
  next_stage: "x"
"""


def test_yaml_helpers() -> None:
    for name, text, qid in (('不縮排序列＋id 不是第一欄', PY_FLAT, 'QA1'),
                            ('mapping 縮排 4＋dash 後三空白', PY_WIDE, 'QA1'),
                            ('鍵與不縮排序列之間夾註解', PY_COMMENT, 'QA1')):
        lines = text.split('\n')
        items = C.list_items_regions(lines, 'sub_questions')
        assert [v for _s, _e, v in items][:1] == [qid], (name, items)
        s, e = C.question_block(lines, 'sub_questions', qid)
        block = lines[s:e]
        di, fi = C.block_item(block)
        assert fi == TF.indent_of(block[di]) + len(TF.dash_prefix(block[di])) - TF.indent_of(block[di]), (name, fi)
        li, links, _cmt = C.block_links(block)
        assert links == ['results:kk'], (name, links)
        C.set_block_links(block, links + ['results:k2'])
        C.set_block_status(block, 'blocked')
        C.prefix_status_reason(block, '前綴：')
        out = yaml.safe_load('\n'.join(lines[:s] + block + lines[e:]))
        item = out['goals']['sub_questions'][0]
        assert item['links'] == ['results:kk', 'results:k2'], (name, item)
        assert item['status'] == 'blocked' and item['status_reason'] == '前綴：', (name, item)
        # 區塊序列寫回區塊序列、流式寫回流式
        joined = '\n'.join(block)
        if '- "results:kk"' in text:
            assert '\n' in joined.split('links:')[1].split('status')[0], (name, joined)
        else:
            assert 'links: [' in joined, (name, joined)
    # 下一個頂層鍵前面的註解不會被前一個區塊吃掉
    lines = PY_COMMENT.split('\n')
    s, e = C.question_block(lines, 'sub_questions', 'QA1')
    assert '這行屬於 state' not in '\n'.join(lines[s:e]), lines[s:e]
    C.add_state_comment(lines, '2099-01-01 D-9003：x')
    out = '\n'.join(lines)
    assert out.index('# 這行屬於 state') < out.index('state:') < out.index('D-9003'), out
    # decisions.yaml append 沿用既有縮排
    flat = '# 註解\ndecisions:\n- id: D-900\n  date: 2099-01-01\n  stage: study-design\n  links: []\n'
    assert C.decisions_style(flat) == (0, 2, 2), C.decisions_style(flat)
    body = C.format_decision({'id': 'D-910', 'date': DATE, 'stage': 'study-design', 'decision': 'x',
                              'links': ['a', 'b']}, C.decisions_style(flat))
    got = yaml.safe_load(flat + body)
    assert [d['id'] for d in got['decisions']] == ['D-900', 'D-910'], got
    assert got['decisions'][1]['links'] == ['a', 'b'], got
    wide = 'decisions:\n    -   id: D-900\n        date: 2099-01-01\n        links:\n          - a\n'
    assert C.decisions_style(wide) == (4, 8, 10), C.decisions_style(wide)
    assert yaml.safe_load(wide + C.format_decision({'id': 'D-910', 'date': DATE, 'links': ['z']},
                                                   C.decisions_style(wide)))['decisions'][1]['links'] == ['z']
    print('[regression] 規格 3：YAML 行層級 helper（縮排任意、id 非第一欄、decisions 沿用縮排）: pass')


# ======================================================================
# 規格 3b：Extended Data 與打包清單的序列縮排
# ======================================================================

def test_opt_in_lists() -> None:
    """`extended-data.yaml`／`submission/package.yaml` 的清單：不縮排的序列也要認，新項目跟著既有風格。

    這兩個檔在 fixture 裡不存在（動作走模板新建），所以格式矩陣只走得到模板那條路；
    「既有清單是不縮排的序列」只能在這裡直接測 helper。
    """
    import package_edit as PE
    import set_tier as ST
    flat = 'schema_version: 1\nplans: []        # 註解\nresults:\n- rA\n- rB\nvalidation: []\n'
    got = ST.apply_changes_text(flat, {'p:QA1-v1': 'extended', 'r:rC': 'extended', 'r:rA': ''})
    assert got == ('schema_version: 1\nplans:        # 註解\n  - QA1-v1\nresults:\n- rB\n- rC\n'
                   'validation: []\n'), repr(got)
    indented = 'schema_version: 1\nplans: []\nresults:\n  - rA\nvalidation: []\n'
    got = ST.apply_changes_text(indented, {'r:rB': 'extended'})
    assert got == 'schema_version: 1\nplans: []\nresults:\n  - rA\n  - rB\nvalidation: []\n', repr(got)
    # 空的 dash 項目（`-` 單獨一行）不該讓解析炸掉，只是被當成值為空的項目
    bare = 'schema_version: 1\nplans:\n-\nresults: []\nvalidation: []\n'
    got = ST.apply_changes_text(bare, {'p:QA1-v1': 'extended'})
    assert yaml.safe_load(got)['plans'][-1] == 'QA1-v1', repr(got)
    # 打包清單同一套：不縮排的序列，新項目也不縮排
    pkg = 'schema_version: 1\ninclude:\n- {path: a/b.txt, tier: main}\nexclude: []       # 註\n'
    got = PE.apply_list_text(pkg, 'include', [{'path': 'a/b.txt', 'tier': 'main'}, {'path': 'c.csv', 'tier': 'si'}])
    assert got == ('schema_version: 1\ninclude:\n- {path: "a/b.txt", tier: "main"}\n'
                   '- {path: "c.csv", tier: "si"}\nexclude: []       # 註\n'), repr(got)
    got = PE.apply_list_text(pkg, 'exclude', [{'path': 'z', 'reason': 'r'}])
    assert got.splitlines()[-2:] == ['exclude:       # 註', '  - {path: "z", reason: "r"}'], repr(got)
    print('[regression] 規格 3b：Extended Data／打包清單的序列縮排（含不縮排）: pass')


# ======================================================================
# 規格 4：set_block_field 保留行尾註解
# ======================================================================

def test_trailing_comment_kept() -> None:
    block = ['    - id: QA1', '      status: open   # 這個註解不能被吃掉', '      note: "x"']
    C.set_block_field(block, 'status', 'blocked')
    assert block[1] == '      status: "blocked"   # 這個註解不能被吃掉', block
    C.set_block_status(block, 'open')
    assert block[1].endswith('# 這個註解不能被吃掉'), block
    # 值裡的 # 不算註解
    block2 = ['    - id: QA1', '      note: "a # b"']
    C.set_block_field(block2, 'note', 'c')
    assert block2[1] == '      note: "c"', block2
    print('[regression] 規格 4：set_block_field 保留行尾註解: pass')


# ======================================================================
# 規格 5：update_rerun_state 不再靜默跳過
# ======================================================================

WAIVED = """state:
  analysis:
    rerun:
      result: waived
      at: '2099-01-01'
      fingerprint: aaa
      input_fingerprint: bbb
      results_fingerprint: ccc
      report: reviews/r.json
    validation:
      results_fingerprint: ccc
      source_fingerprint: aaa
      at: '2099-01-01'
"""

FPS = {'fingerprint': 'n1', 'input_fingerprint': 'n2', 'results_fingerprint': 'n3'}


def test_rerun_not_silent() -> None:
    new, info = C.update_rerun_state(WAIVED, FPS, 'reviews/n.json', DATE, '理由')
    assert 'skipped' not in info and info['validation_updated'], info
    doc = yaml.safe_load(new)['state']['analysis']
    assert doc['rerun']['fingerprint'] == 'n1' and doc['rerun']['previous_waiver']['fingerprint'] == 'aaa', doc
    assert doc['validation']['source_fingerprint'] == 'n1', doc
    # 縮排 4 的 mapping 也要能重登
    wide = yaml.dump(yaml.safe_load(WAIVED), Dumper=_IndentDumper, allow_unicode=True, sort_keys=False, indent=4)
    new2, info2 = C.update_rerun_state(wide, FPS, 'reviews/n.json', DATE, '理由')
    assert 'skipped' not in info2, info2
    assert yaml.safe_load(new2)['state']['analysis']['rerun']['fingerprint'] == 'n1'
    # 語意上是 waived、文字層定位不到（流式 mapping）→ ChainError，不是 skipped
    flow = 'state: ' + yaml.dump(yaml.safe_load(WAIVED)['state'], Dumper=yaml.SafeDumper, allow_unicode=True,
                                 sort_keys=False, default_flow_style=True, width=10 ** 6).strip() + '\n'
    assert yaml.safe_load(flow)['state']['analysis']['rerun']['result'] == 'waived'
    try:
        C.update_rerun_state(flow, FPS, 'reviews/n.json', DATE, '理由')
        raise AssertionError('語意上是 waived 卻定位不到時應中止')
    except C.ChainError as exc:
        assert 'project.yaml' in str(exc) and '流式' in str(exc) or '定位不到' in str(exc), exc
    # 真的沒有 rerun／不是 waived 才回 skipped，而且說得出原因
    _t, i3 = C.update_rerun_state('state:\n  analysis:\n    other: 1\n', FPS, 'reviews/n.json', DATE, '理由')
    assert 'skipped' in i3 and 'rerun' in i3['skipped'], i3
    _t, i4 = C.update_rerun_state(WAIVED.replace('result: waived', 'result: pass'), FPS, 'reviews/n.json', DATE, '理由')
    assert 'skipped' in i4 and 'waived' in i4['skipped'], i4
    # validation 的指紋欄位在、文字層卻定位不到 → 也要中止
    half = WAIVED.replace("""    validation:
      results_fingerprint: ccc
      source_fingerprint: aaa
      at: '2099-01-01'
""", "    validation: {results_fingerprint: ccc, source_fingerprint: aaa, at: '2099-01-01'}\n")
    try:
        C.update_rerun_state(half, FPS, 'reviews/n.json', DATE, '理由')
        raise AssertionError('validation 指紋定位不到時應中止')
    except C.ChainError as exc:
        assert 'validation' in str(exc), exc
    print('[regression] 規格 5：update_rerun_state 語意判斷＋定位不到就中止: pass')


# ======================================================================
# 規格 6：add_state_comment
# ======================================================================

def test_state_comment() -> None:
    # D# 不限位數：新註解要排在既有註解之後
    lines = ['state:', '  # 2099-01-01 D-9001：舊註解', '  next_stage: "x"']
    assert C.add_state_comment(lines, f'{DATE} D-9002：新註解') == ''
    assert lines[2] == f'  # {DATE} D-9002：新註解', lines
    # 註解縮排沿用原檔
    wide = ['state:', '    # 2099-01-01 D-900：舊', '    next_stage: "x"']
    C.add_state_comment(wide, f'{DATE} D-910：新')
    assert wide[2] == f'    # {DATE} D-910：新', wide
    # 沒有既有註解時用 state 的子鍵縮排
    bare = ['state:', '      next_stage: "x"']
    C.add_state_comment(bare, 'x')
    assert bare[1] == '      # x', bare
    # 沒有 state: → 可見提示，而且記進 WARNING sink
    C._WARN_SINK.clear()
    why = C.add_state_comment(['project:', '  title: "x"'], 'x')
    assert why and 'state' in why, why
    assert any('state' in w for w in C._WARN_SINK), C._WARN_SINK
    C._WARN_SINK.clear()
    print('[regression] 規格 6：add_state_comment（任意位數 D#、縮排沿用、缺 state 有提示）: pass')


# ======================================================================
# 規格 7：WARNING 印到 stdout
# ======================================================================

def test_warning_visible(tmp: Path) -> None:
    root = copy_fixture(tmp, 'warn')
    # 把 rerun 改成不是 waived，又不給 --waiver-decision：鏈會記一句 WARNING
    path = root / 'project.yaml'
    path.write_text(path.read_text(encoding='utf-8').replace('result: waived', 'result: pass')
                    .replace('decision: D-001', 'decision: ""'), encoding='utf-8')
    refix_fingerprints(root)
    rc, out = run_action('nest_result.py', root, '--key', 'k2', '--under', 'k1')
    assert rc == 0, out[-2000:]
    assert 'WARNING' in out, f'WARNING 沒有印到 stdout\n{out[-2000:]}'
    log_rel = [ln for ln in out.split('\n') if 'run log' in ln][0].split('run log ')[1].strip()
    log = json.loads((root / log_rel).read_text(encoding='utf-8'))
    assert any('WARNING' in n for s in log['steps'] for n in s['notes']), log.get('warnings')
    assert log.get('warnings'), log.get('warnings')
    shutil.rmtree(root)
    print('[regression] 規格 7：鏈裡的 WARNING 印到 stdout 摘要: pass')


# ======================================================================
# 規格 8：CRLF 保留
# ======================================================================

def test_crlf_kept(tmp: Path) -> None:
    root = copy_fixture(tmp, 'crlf')
    for rel in ('project.yaml', 'decisions.yaml', 'analysis/validation.yaml'):
        _crlf(root / rel)
    refix_fingerprints(root)
    before = {rel: (root / rel).read_bytes().count(b'\r\n') for rel in
              ('project.yaml', 'decisions.yaml', 'analysis/validation.yaml')}
    rc, out = run_action('nest_result.py', root, '--key', 'k2', '--under', 'k1')
    assert rc == 0, out[-2000:]
    for rel, n in before.items():
        raw = (root / rel).read_bytes()
        assert raw.count(b'\r\n') >= n, f'{rel} 的 CRLF 被改成 LF（原 {n} 個，現 {raw.count(bytes([13, 10]))} 個）'
        assert raw.count(b'\n') == raw.count(b'\r\n'), f'{rel} 變成混合換行'
    assert (root / 'analysis/results.json').read_bytes().count(b'\r\n') == 0, 'LF 的檔不該變成 CRLF'
    shutil.rmtree(root)
    print('[regression] 規格 8：CRLF 的 SSOT 檔改過之後仍是 CRLF: pass')


# ======================================================================
# 規格 9：links 與區塊純量
# ======================================================================

def test_block_scalar_and_links() -> None:
    for marker in ('|-', '>-'):
        block = ['    - id: QA1', '      status: open',
                 f'      status_reason: {marker}', '        第一行理由', '        第二行理由',
                 '      links: ["results:kk"]']
        C.prefix_status_reason(block, '前綴：')
        doc = yaml.safe_load('\n'.join(['goals:', '  sub_questions:'] + block))
        got = doc['goals']['sub_questions'][0]['status_reason']
        assert got.startswith('前綴：') and '第一行理由' in got and '第二行理由' in got, (marker, got)
        assert got == '前綴：' + ('第一行理由\n第二行理由' if marker == '|-' else '第一行理由 第二行理由'), (marker, got)
    # 區塊序列的 links 讀得到、寫回仍是區塊序列
    block = ['    - id: QA1', '      links:', '        - "results:kk"', '        - "results:k2"', '      status: open']
    li, links, _c = C.block_links(block)
    assert li == 1 and links == ['results:kk', 'results:k2'], (li, links)
    C.set_block_links(block, ['results:kk'])
    assert block[1:3] == ['      links:', '        - "results:kk"'], block
    assert block[3] == '      status: open', block
    C.set_block_links(block, [])
    assert block[1] == '      links: []', block
    print('[regression] 規格 9：links 流式／區塊序列與 status_reason 區塊純量: pass')


# ======================================================================
# 規格 10：後綴字母的問題 id
# ======================================================================

def test_suffix_ids(tmp: Path) -> None:
    assert C.Q_ID_RE.fullmatch('SQ6b') and C.Q_ID_RE.fullmatch('AQ12c'), 'Q_ID_RE 不收後綴字母'
    assert C.SQ_RE.fullmatch('SQ8b') and C.AQ_RE.fullmatch('AQ7b')
    assert not C.AQ_RE.fullmatch('SQ2b') and not C.SQ_RE.fullmatch('SQ')
    assert C.Q_PLAIN_RE.fullmatch('SQ6b') and C.Q_PLAIN_RE.fullmatch('main')
    root = copy_fixture(tmp, 'suffix')
    # 整個 fixture 把 AQ1 換成帶後綴字母的 AQ1b（plan 檔名、index、results、validation、快照一起換）
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.suffix not in ('.yaml', '.yml', '.json', '.md'):
            continue
        old = path.read_text(encoding='utf-8')
        new = re.sub(r'\bAQ1\b', 'AQ1b', old)
        if new != old:
            path.write_text(new, encoding='utf-8')
    (root / 'analysis/plans/AQ1-v1.yaml').replace(root / 'analysis/plans/AQ1b-v1.yaml')
    plan = root / 'analysis/plans/AQ1b-v1.yaml'           # 內容改過了，content_hash 要重算才封得回去
    doc = yaml.safe_load(plan.read_text(encoding='utf-8'))
    doc.pop('content_hash', None)
    plan.write_text(_ydump(doc), encoding='utf-8')
    proc = subprocess.run([sys.executable, '-B', str(PLUGIN / 'skills/study-design/scripts/seal_artifact.py'),
                           str(plan), '--kind', 'plan', '--root', str(root),
                           '--confirmed-by', 'user', '--date', '2026-09-10'], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    refix_fingerprints(root)
    # 自動配號：AQ1b 占了 1 號，下一個附錄編號要是 AQ3（AQ2 仍在）
    assert C.next_question_id(root, 'AQ') == 'AQ3', C.next_question_id(root, 'AQ')
    assert C.next_question_id(root, 'SQ') == 'SQ3', C.next_question_id(root, 'SQ')
    # 帶後綴字母的附錄問題可以升回主問題（目標號由自動配號給，不會落在 SQ1）
    rc, out = run_action('promote_question.py', root, '--from', 'AQ1b')
    assert rc == 0, f'AQ1b 升回失敗\n{out[-2500:]}'
    sq, aq = C.goals_ids(root)
    assert 'AQ1b' not in aq and 'SQ3' in sq, (sq, aq)
    ok, why = C._validate_promote(root, {'from': 'AQ2', 'to': 'SQ4'})
    assert ok and not why, (ok, why)
    # 前端的 SQ／AQ 比對：後綴字母要認，多位數編號也不能因此漏掉
    html = (root / 'progress/PROGRESS.html').read_text(encoding='utf-8')
    pats = re.findall(r'/\^(?:q:)?[SA]Q[^/\n]{1,24}?/', html)
    assert len(pats) >= 8, f'在 PROGRESS.html 只找到 {len(pats)} 個前端的 SQ／AQ 比對式：{sorted(set(pats))}'
    for pat in set(pats):
        assert '[a-z]*' in pat, f'前端比對式沒有放行後綴字母：{pat}'
        assert '+' in pat, f'前端比對式漏掉 + 量詞，多位數編號會比不到：{pat}'
    shutil.rmtree(root)
    print('[regression] 規格 10：帶後綴字母的問題 id 全程可用: pass')


# ======================================================================
# 規格 11：retag 的成本隨鍵數線性
# ======================================================================

SCALE_KEYS = 20000
SCALE_RETAG = 10000
SCALE_LIMIT = 10.0


def test_retag_scale(keys: int = SCALE_KEYS, retag: int = SCALE_RETAG, limit: float = SCALE_LIMIT) -> None:
    """頂層鍵很多、又要改一半：整段限 limit 秒內（驗牙時用小一號的規模與時限）。

    成員查詢逐次線性掃是 O(鍵數 × 改動數)、逐筆重組字串是 O(筆數 × 檔案大小)，兩者在這個量級都會爆。
    """
    doc = {f'k{i:05d}': {'plan_id': 'SQ6-v1' if i < retag else 'SQ7-v1', 'model_id': 'M1',
                         'rows': [{'a': i, 'b': i + 1}]} for i in range(keys)}
    text = json.dumps(doc, ensure_ascii=False, indent=2) + '\n'
    key_map = {f'k{i:05d}': 'SQ8-v1' for i in range(retag)}
    t0 = time.perf_counter()
    new, info = C.retag_results(text, key_map)
    sec = time.perf_counter() - t0
    assert info['changed_lines'] == retag, info
    got = json.loads(new)
    assert list(got) == list(doc), 'retag 後鍵序改變'
    assert all(got[k]['plan_id'] == 'SQ8-v1' for k in key_map), '目標鍵沒有改到'
    assert all(got[f'k{i:05d}']['plan_id'] == 'SQ7-v1' for i in range(retag, keys)), '非目標鍵被改到'
    assert sec < limit, (f'{keys} 個頂層鍵改 {retag} 個花了 {sec:.1f} 秒'
                         f'（限 {limit:.1f} 秒）：成員查詢或替換又變成二次式')
    # 替換區間真的重疊時要明確中止，不能默默接出一份錯的文字
    jt = TF.JsonText('{"a": 1, "b": 2}\n', 'fixture.json')
    s, e = jt.value_span(('a',))
    try:
        jt.apply([(s, e, '9'), (s, e + 1, '8')])
        raise AssertionError('重疊的替換區間應中止')
    except C.ChainError as exc:
        assert '重疊' in str(exc), exc
    print(f'[regression] 規格 11：{keys} 個頂層鍵改 {retag} 個 {sec:.1f} 秒'
          f'（限 {limit:.1f} 秒）、重疊區間明確中止: pass')


# ======================================================================
# 規格 12：行尾註解依引號／流式／純量三態判定
# ======================================================================

COMMENT_CASES = [
    (" don't know  # note", (" don't know", '  # note')),      # 純量裡的撇號不開啟字串
    (' "a # b"  # c', (' "a # b"', '  # c')),                  # 雙引號字串裡的 # 是內容
    (' ["a # b", c]  # d', (' ["a # b", c]', '  # d')),        # 流式集合：引號在 [ 之後才開啟
    (" it's # x's", (" it's", " # x's")),                      # 註解本身有撇號也不影響
    (' plain#notcomment # real', (' plain#notcomment', ' # real')),   # # 前面不是空白就不是註解
    (" 'it''s' # q", (" 'it''s'", ' # q')),                    # 單引號字串裡的 '' 是一個單引號
    (' [a#b, c] # d', (' [a#b, c]', ' # d')),                  # 流式集合裡的 a#b 是純量
    (' {"k": "v # w"} # z', (' {"k": "v # w"}', ' # z')),       # 流式 mapping：引號在 : 之後才開啟
]


def test_comment_modes() -> None:
    for rest, want in COMMENT_CASES:
        assert TF.strip_comment(rest) == want, f'{rest!r} → {TF.strip_comment(rest)!r}，應為 {want!r}'
    # 整行進出：值換掉之後註解還在，鍵與冒號後的空白照原樣
    line = "    reason: don't know  # 保留我"
    assert TF.split_field_line(line) == ('    reason:', " don't know", '  # 保留我'), TF.split_field_line(line)
    assert TF.replace_value(line, 'ok') == '    reason: ok  # 保留我', TF.replace_value(line, 'ok')
    assert TF.line_comment(line) == '  # 保留我'
    assert TF.dash_value("  - it's  # c") == "it's", TF.dash_value("  - it's  # c")
    print(f'[regression] 規格 12：行尾註解三態判定（{len(COMMENT_CASES)} 例）、值換掉後註解仍在: pass')


# ======================================================================
# 規格 13：decisions.yaml 的縮排量法與 append 位置
# ======================================================================

DE_BLOCK_SCALAR = ('decisions:\n  - id: D-900\n    decision: |-\n      head\n'
                   '          - deep bullet\n    links:\n      - a\n')
DE_PLAIN = 'decisions:\n  - id: D-900\n    date: 2099-01-01\n'
DE_TAIL_COMMENT = 'decisions:\n  - id: D-900\n    date: 2099-01-01\n\n# 檔尾註解\n'
DE_ENTRY = {'id': 'D-910', 'date': '2099-01-01', 'decision': 'x'}
DE_ENTRY_TEXT = '  - id: D-910\n    date: 2099-01-01\n    decision: "x"\n'


def _append_decision_text(tmp: Path, name: str, text: str, entry: dict) -> str:
    root = tmp / name
    root.mkdir(parents=True, exist_ok=True)
    (root / 'decisions.yaml').write_text(text, encoding='utf-8')
    C.append_decision(root, dict(entry))
    got = (root / 'decisions.yaml').read_text(encoding='utf-8')
    shutil.rmtree(root)
    return got


def test_decisions_style_and_append(tmp: Path) -> None:
    # 區塊純量（`decision: |-`）的內容裡有 `- …` 的行，縮排再深也不是欄位內清單
    assert C.decisions_style(DE_BLOCK_SCALAR) == (2, 4, 6), C.decisions_style(DE_BLOCK_SCALAR)
    assert C.decisions_style('decisions:\n- id: D-900\n  links:\n  - a\n') == (0, 2, 2)
    assert C.decisions_style('decisions:\n  - id: D-900\n    date: 2099-01-01\n') == (2, 4, 6)
    assert C.decisions_style('decisions:\n    -   id: D-900\n        links:\n            - a\n') == (4, 8, 12)
    # 清單後面沒有別的頂層內容：逐位元等於「接在檔尾」
    assert _append_decision_text(tmp, 'de_plain', DE_PLAIN, DE_ENTRY) == DE_PLAIN + DE_ENTRY_TEXT
    assert _append_decision_text(tmp, 'de_cmt', DE_TAIL_COMMENT, DE_ENTRY) == DE_TAIL_COMMENT + DE_ENTRY_TEXT
    # 清單後面還有頂層鍵：插在 decisions 區塊尾端，整檔仍解析得出來、既有條目與該鍵都不動
    for name, text in (('de_key', DE_PLAIN + 'schema_version: 1\n'),
                       ('de_empty_key', 'decisions: []\nschema_version: 1\n'),
                       ('de_null_key', 'decisions:\nschema_version: 1\n'),
                       ('de_flat_key', 'decisions:\n- id: D-900\n  date: 2099-01-01\nschema_version: 1\n')):
        got = _append_decision_text(tmp, name, text, DE_ENTRY)
        doc = yaml.safe_load(got)
        ids = [str(d.get('id')) for d in doc['decisions']]
        assert ids[-1] == 'D-910', f'{name}: 新條目沒進清單（{ids}）'
        assert ids[:-1] == [str(d.get('id')) for d in (yaml.safe_load(text).get('decisions') or [])], \
            f'{name}: 既有條目被波及（{ids}）'
        assert doc.get('schema_version') == 1, f'{name}: 清單後面的頂層鍵掉了'
        assert got.rstrip('\n').endswith('schema_version: 1'), f'{name}: 新條目接到頂層鍵後面\n{got}'
    print('[regression] 規格 13：decisions.yaml 縮排量法不被區塊純量騙、清單後有頂層鍵時 append 插在區塊尾端: pass')


# ======================================================================
# 規格 14：收件匣的序列縮排從檔案量
# ======================================================================

INBOX_HEAD = '# 收件匣\nschema_version: 1\nitems:\n'
INBOX_FIELDS = ['at: "2099-01-01T00:00:00+08:00"', 'kind: "comment"', 'target: "q:SQ6"',
                'title: "t"', 'body: "b"', 'author: "a"', 'status: "pending"']


def _inbox(root: Path, dash: int, field: int, id_last: bool) -> None:
    fields = list(INBOX_FIELDS) + (['id: "IN-001"'] if id_last else [])
    rows = ([] if id_last else [f'{" " * dash}-{" " * (field - dash - 1)}id: "IN-001"'])
    if id_last:
        rows.append(f'{" " * dash}-{" " * (field - dash - 1)}{fields.pop(0)}')
    rows += [f'{" " * field}{f}' for f in fields]
    path = root / 'progress/PROGRESS.inbox.yaml'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(INBOX_HEAD + '\n'.join(rows) + '\n', encoding='utf-8')


def test_inbox_indent(tmp: Path) -> None:
    script = SCRIPTS / 'check_inbox.py'
    for name, dash, field, id_last in (('srv', 2, 4, False), ('flat', 0, 2, False),
                                       ('indent4', 4, 8, False), ('id_last', 2, 4, True)):
        root = tmp / f'inbox_{name}'
        root.mkdir(parents=True, exist_ok=True)
        _inbox(root, dash, field, id_last)
        proc = subprocess.run([sys.executable, '-B', str(script), str(root), '--resolve', 'IN-001',
                               '--by', 'D-900', '--note', 'n'], capture_output=True, text=True,
                              encoding='utf-8', env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), cwd='/tmp')
        out = (proc.stdout or '') + (proc.stderr or '')
        assert proc.returncode == 0, f'{name}: rc={proc.returncode}\n{out[-1200:]}'
        doc = yaml.safe_load((root / 'progress/PROGRESS.inbox.yaml').read_text(encoding='utf-8'))
        item = doc['items'][0]
        assert item['status'] == 'done' and item['resolved_by'] == 'D-900' and item['note'] == 'n', item
        assert item['title'] == 't' and item['target'] == 'q:SQ6', f'{name}: 其他欄位被動到 {item}'
        assert len(doc['items']) == 1 and doc['schema_version'] == 1, doc
        shutil.rmtree(root)
    print('[regression] 規格 14：收件匣的 dash 與欄位縮排從檔案量（不縮排序列、縮排 4、id 在最後一欄都可結案）: pass')


# ======================================================================
# 規格 15：批次摘要一定帶出子步驟的 WARNING
# ======================================================================

def _no_waiver(root: Path) -> None:
    """把 rerun 改成不是 waived、又不給 waiver 決策：動作鏈會記一句 WARNING。"""
    path = root / 'project.yaml'
    path.write_text(path.read_text(encoding='utf-8').replace('result: waived', 'result: pass')
                    .replace('decision: D-001', 'decision: ""'), encoding='utf-8')
    refix_fingerprints(root)


def test_batch_warning(tmp: Path) -> None:
    root = copy_fixture(tmp, 'batch_warn')
    _no_waiver(root)
    batch = json.dumps({'actions': [{'kind': 'nest_result', 'payload': {'key': 'k2', 'under': 'k1'}}]})
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    proc = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'run_batch.py'), str(root), '--batch', batch,
                           '--dry-run', '--date', DATE], capture_output=True, text=True, encoding='utf-8',
                          env=env, cwd='/tmp')
    out = (proc.stdout or '') + (proc.stderr or '')
    assert proc.returncode == 0, f'rc={proc.returncode}\n{out[-2500:]}'
    assert 'WARNING' in out, f'子步驟的 WARNING 沒有進批次摘要\n{out[-2500:]}'
    # 子步驟自己跑同一件事時也會印 WARNING——批次摘要不該比單步少
    rc1, out1 = run_action('nest_result.py', root, '--key', 'k2', '--under', 'k1')
    assert rc1 == 0, out1[-1500:]
    single = {ln.strip() for ln in out1.splitlines() if ln.strip().startswith('WARNING')}
    batched = {ln.strip() for ln in out.splitlines() if ln.strip().startswith('WARNING')}
    assert single and single <= batched, f'批次摘要漏了 WARNING\n單步：{single}\n批次：{batched}'
    shutil.rmtree(root)
    print(f'[regression] 規格 15：批次摘要帶出子步驟的 {len(batched)} 句 WARNING（不被節錄的終止條件吃掉）: pass')


# ======================================================================
# 規格 16：SSOT 檔無法解析＝BLOCKER，不是 traceback
# ======================================================================

BAD_YAML = 'a:\n b: [1,\n  c: "unclosed\n\t@bad\n'
BAD_JSON = '{"a": {"b": 1,,,\n'
BAD_FILES = ('project.yaml', 'decisions.yaml', 'analysis/validation.yaml',
             'analysis/results.json', 'analysis/figures/manifest.json')
# traceback 外漏不一定看得到 Traceback 這個字——動作把子程序輸出截成尾段再印，只剩堆疊的行。
TB_MARKS = ('Traceback', 'File "', '.py", line ')


def test_broken_ssot(tmp: Path, files: tuple[str, ...] = BAD_FILES, actions: tuple[str, ...] = ()) -> None:
    picked = {k: v for k, v in ACTIONS.items() if not actions or k in actions}
    for rel in files:
        for action, (script, args) in sorted(picked.items()):
            root = copy_fixture(tmp, f'bad_{rel.replace("/", "_")}__{action}')
            (root / rel).write_text(BAD_JSON if rel.endswith('.json') else BAD_YAML, encoding='utf-8')
            rc, out = run_action(script, root, *args)
            hit = [m for m in TB_MARKS if m in out]
            assert not hit, f'{rel} × {action}: 輸出裡有 traceback（{hit}）\n{out[-1500:]}'
            assert rc != 0, f'{rel} × {action}: 壞檔卻 rc=0\n{out[-1500:]}'
            first = next((ln for ln in out.splitlines() if ln.startswith('BLOCKER')), '')
            assert first, f'{rel} × {action}: 沒有 BLOCKER 行\n{out[-1500:]}'
            assert '無法解析' in first and Path(rel).name in first, \
                f'{rel} × {action}: BLOCKER 沒指出是哪個檔無法解析\n{first}'
            shutil.rmtree(root)
    # run_batch 的參數形狀不同，另跑一次
    root = copy_fixture(tmp, 'bad_batch')
    (root / 'project.yaml').write_text(BAD_YAML, encoding='utf-8')
    batch = json.dumps({'actions': [{'kind': 'reorder',
                                     'payload': {'list': 'sub_questions', 'order': ['SQ2', 'SQ1']}}]})
    proc = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'run_batch.py'), str(root), '--batch', batch,
                           '--dry-run', '--date', DATE], capture_output=True, text=True, encoding='utf-8',
                          env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), cwd='/tmp')
    out = (proc.stdout or '') + (proc.stderr or '')
    assert proc.returncode != 0 and not [m for m in TB_MARKS if m in out], out[-1500:]
    assert any(ln.startswith('BLOCKER') and '無法解析' in ln for ln in out.splitlines()), out[-1500:]
    shutil.rmtree(root)
    print(f'[regression] 規格 16：{len(files)} 個壞掉的 SSOT 檔 × {len(picked)} 個動作'
          f'（＋run_batch）都是 BLOCKER、沒有 traceback: pass')


# ======================================================================
# 規格 17：後綴字母編號在其餘比對處也放行
# ======================================================================

def _rename_question(root: Path, old: str, new: str) -> None:
    """整個 fixture 把某個問題 id 換成帶後綴字母的版本（plan 檔名、index、results、validation、快照一起換）。"""
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.suffix not in ('.yaml', '.yml', '.json', '.md'):
            continue
        before = path.read_text(encoding='utf-8')
        after = re.sub(rf'\b{re.escape(old)}\b', new, before)
        if after != before:
            path.write_text(after, encoding='utf-8')
    for plan in sorted((root / 'analysis/plans').glob(f'{old}-v*.yaml')):
        dst = plan.with_name(plan.name.replace(old, new, 1))
        plan.replace(dst)
        doc = yaml.safe_load(dst.read_text(encoding='utf-8'))      # 內容改過了，content_hash 要重算才封得回去
        doc.pop('content_hash', None)
        dst.write_text(_ydump(doc), encoding='utf-8')
        proc = subprocess.run([sys.executable, '-B', str(PLUGIN / 'skills/study-design/scripts/seal_artifact.py'),
                               str(dst), '--kind', 'plan', '--root', str(root),
                               '--confirmed-by', 'user', '--date', '2026-09-10'], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stdout + proc.stderr
    refix_fingerprints(root)


def test_suffix_tier_question(tmp: Path) -> None:
    """帶後綴字母的 plan 改 Extended Data 歸屬：決策的 question 欄要認出那個問題，不能退成 main。"""
    root = copy_fixture(tmp, 'suffix_tier')
    _rename_question(root, 'SQ2', 'SQ2b')
    rc, out = run_action('set_tier.py', root, '--node', 'p:SQ2b-v1=extended')
    assert rc == 0, f'帶後綴字母的 plan 無法改歸屬\n{out[-2500:]}'
    last = C.decisions_list(root)[-1]
    assert str(last.get('question')) == 'SQ2b', \
        f'決策的 question 欄沒認出後綴字母（得到 {last.get("question")!r}）'
    shutil.rmtree(root)
    print('[regression] 規格 17b：帶後綴字母的問題 id 在 set_tier 的決策 question 欄認得出來: pass')


def test_suffix_ids_rest(tmp: Path) -> None:
    import check_decisions as CD
    import render_decisions_timeline as RT
    assert C.PLAN_ID_RE.fullmatch('SQ6b-v2').groups() == ('SQ6b', '2'), 'PLAN_ID_RE 不收後綴字母'
    assert C.PLAN_ID_RE.fullmatch('AQ70c-v3').groups() == ('AQ70c', '3'), '多位數編號不能因此比不到'
    assert C.PLAN_ID_RE.fullmatch('SQ6-v1').groups() == ('SQ6', '1'), '無後綴的編號不能因此比不到'
    assert CD.Q_ID_RE.fullmatch('SQ6b') and CD.Q_ID_RE.fullmatch('AQ70c') and CD.Q_ID_RE.fullmatch('SQ6')
    assert CD.SQ_ID_RE.fullmatch('SQ6b') and not CD.SQ_ID_RE.fullmatch('AQ7b')
    # 時間軸的 section 排序：後綴字母排在同號的無後綴之後，自由文字與 unknown 仍在最後
    names = ['unknown', 'free', 'AQ7b', 'AQ7', 'SQ60', 'SQ6b', 'SQ6', 'main']
    want = ['main', 'SQ6', 'SQ6b', 'SQ60', 'AQ7', 'AQ7b', 'free', 'unknown']
    assert sorted(names, key=RT._section_key) == want, sorted(names, key=RT._section_key)
    # links: [SQ2b] 從「被忽略」變成「被檢查」：存在的過、不存在的報 WARNING
    root = copy_fixture(tmp, 'suffix_links')
    path = root / 'project.yaml'
    path.write_text(path.read_text(encoding='utf-8').replace('    - id: SQ2', '    - id: SQ2b', 1), encoding='utf-8')
    for link, want_warn in (('SQ2b', False), ('SQ9z', True)):
        de = root / 'decisions.yaml'
        text = de.read_text(encoding='utf-8')
        de.write_text(text + f'  - id: D-910\n    date: {DATE}\n    stage: analyze-data\n'
                             f'    decision: "x"\n    links:\n      - "{link}"\n', encoding='utf-8')
        proc = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'check_decisions.py'), str(de),
                               str(root / 'project.yaml')], capture_output=True, text=True, encoding='utf-8',
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), cwd='/tmp')
        out = (proc.stdout or '') + (proc.stderr or '')
        got = any('D-910' in ln and 'link SQ 不存在' in ln for ln in out.splitlines())
        assert got == want_warn, f'link {link}: 預期 WARNING={want_warn}，實際 {got}\n{out[-900:]}'
        de.write_text(text, encoding='utf-8')
    shutil.rmtree(root)
    print('[regression] 規格 17：後綴字母編號在 PLAN_ID_RE／check_decisions／時間軸排序都放行: pass')


# ======================================================================
# 驗牙：改壞 helper，上面的斷言要真的會失敗
# ======================================================================

def shadow_plugin(dst: Path) -> Path:
    """把整個 plugin（不含 .git）複製到暫存資料夾，改壞 helper 之後在複本裡跑測試。

    不能只把單一模組放到 sys.path 前面——測試檔與它 import 的其他測試模組都會
    `Path(__file__).resolve().parents[1]` 回推 plugin 根再把真的 scripts 插到 sys.path[0]，
    影子就被蓋掉了。整棵複製是唯一不會被回推繞過的做法（幾 MB，複製很快）。
    """
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(PLUGIN, dst, ignore=shutil.ignore_patterns('.git'), symlinks=True)
    return dst


def _run_in_shadow(shadow: Path, tests: str) -> subprocess.CompletedProcess:
    code = ('import sys; sys.path.insert(0, %r)\nimport run_v0290_regressions as R\n%s\n'
            % (str(shadow / 'tests'), tests))
    return subprocess.run([sys.executable, '-B', '-c', code], capture_output=True, text=True,
                          env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), cwd='/tmp')


TF_REL = 'skills/status/scripts/ssot_text_format.py'
AC_REL = 'skills/status/scripts/ssot_actions_common.py'
CI_REL = 'skills/status/scripts/check_inbox.py'
RB_REL = 'skills/status/scripts/run_batch.py'
CD_REL = 'skills/status/scripts/check_decisions.py'
RT_REL = 'skills/status/scripts/render_decisions_timeline.py'
PC_REL = 'skills/study-design/scripts/plan_common.py'
IG_REL = 'skills/status/scripts/init_glossary.py'
GT_REL = 'skills/project-init/references/glossary-template.md'

_TEXT_CALLS = 'R.test_yaml_helpers(); R.test_trailing_comment_kept(); R.test_block_scalar_and_links()'
_TMP_CALL = ('import pathlib, tempfile\n'
             'with tempfile.TemporaryDirectory() as _d:\n    %s\n')

# (名稱, 要改壞的檔, 原文, 改壞成, 要跑的測試)。原文必須在該檔出現恰好一次。
TEETH: list[tuple[str, str, str, str, str]] = [
    # 欄位縮排回到寫死的 6 空白 → 規格 3 的縮排 4 變體抓得到
    ('item_field_indent', TF_REL,
     """    pre = dash_prefix(lines[start])
    if lines[start][len(pre):].strip():
        return len(pre)""",
     """    pre = dash_prefix(lines[start])
    if lines[start][len(pre):].strip():
        return 6""", _TEXT_CALLS),
    # 行尾註解又被吃掉 → 規格 4 抓得到
    ('replace_value', TF_REL,
     """    gap = val[:len(val) - len(val.lstrip(' \\t'))] or ' '
    return head + gap + new_value + cmt""",
     """    gap = val[:len(val) - len(val.lstrip(' \\t'))] or ' '
    return head + gap + new_value""", _TEXT_CALLS),
    # 區塊純量只讀第一行 → 規格 9 抓得到
    ('field_value', TF_REL,
     '    end = min(key_block_end(lines, i, field_ind), len(lines) if hi is None else hi)',
     '    end = i + 1', _TEXT_CALLS),
    # JSON 掃描器把值的結束位置算錯一格 → 規格 2 抓得到
    ('json_scalar_span', TF_REL,
     "        return {'kind': 'scalar', 'start': i, 'end': e}, e",
     "        return {'kind': 'scalar', 'start': i, 'end': e - 1}, e", 'R.test_json_scan()'),
    # 成員查詢退回逐次線性掃 → 規格 11 的時限抓得到
    ('member_linear', TF_REL,
     """        idx = obj.get('index')
        if idx is None:
            idx = obj['index'] = {m['key']: m for m in obj['members']}
        return idx.get(key)""",
     """        for m in obj['members']:
            if m['key'] == key:
                return m
        return None""", 'R.test_retag_scale(limit=2.0)'),
    # 替換退回逐筆重組整份文字 → 規格 11 的時限抓得到
    ('apply_per_edit', TF_REL,
     """        order = sorted(range(len(edits)), key=lambda k: (edits[k][0], -k))
        out: list[str] = []
        pos = 0
        for k in order:
            s, e, new = edits[k]
            if s < pos:
                raise ChainError(f'{self.where} 的替換區間重疊（{s}–{e}）')
            out.append(self.text[pos:s])
            out.append(new)
            pos = max(pos, e)
        out.append(self.text[pos:])
        return ''.join(out)""",
     """        out = self.text
        for s, e, new in sorted(edits, key=lambda x: -x[0]):
            out = out[:s] + new + out[e:]
        return out""", 'R.test_retag_scale(limit=2.0)'),
    # 註解判定退回「任何引號都開啟字串」（純量裡的撇號會把後面整段吃掉）→ 規格 12 抓得到
    ('strip_comment_naive', TF_REL,
     """    if head[0] not in '[{':
        return _find_comment(rest, 0)""",
     """    if head[0] not in '[{':
        i = 0
        while i < len(rest):
            if rest[i] in '"\\'':
                i = _scan_quoted(rest, i)
                continue
            if rest[i] == '#' and (i == 0 or rest[i - 1] in ' \\t'):
                return _comment_cut(rest, i)
            i += 1
        return rest, ''""", 'R.test_comment_modes()'),
    # 區塊純量裡的 `- …` 又被當成欄位內清單 → 規格 13 抓得到
    ('decisions_style_deep', AC_REL,
     """            if after_empty_field and TF.is_dash(ln) and TF.indent_of(ln) > f_ind:""",
     """            if TF.is_dash(ln) and TF.indent_of(ln) > f_ind:""",
     _TMP_CALL % 'R.test_decisions_style_and_append(pathlib.Path(_d))'),
    # 新條目又接到檔尾 → 規格 13 抓得到
    ('append_at_eof', AC_REL,
     """        if any(not TF.is_blank(ln) and not TF.is_comment(ln) for ln in lines[end:]):""",
     """        if False and any(not TF.is_blank(ln) and not TF.is_comment(ln) for ln in lines[end:]):""",
     _TMP_CALL % 'R.test_decisions_style_and_append(pathlib.Path(_d))'),
    # 收件匣的序列縮排又寫死 → 規格 14 抓得到
    ('inbox_hardcoded_indent', CI_REL,
     """        field_ind = TF.item_field_indent(lines, start, end)""",
     """        field_ind = 4""",
     _TMP_CALL % "R.test_inbox_indent(pathlib.Path(_d))"),
    # 批次節錄又把 WARNING 吃掉 → 規格 15 抓得到
    ('step_lines_no_warn', RB_REL,
     """    body = body[:limit]
    return body + [w for w in warnings if w not in body]""",
     """    return body[:limit]""",
     _TMP_CALL % 'R.test_batch_warning(pathlib.Path(_d))'),
    # 壞檔又不先擋 → 規格 16 抓得到（關卡子程序的 traceback 外漏）
    ('no_parse_guard', AC_REL,
     """    for rel in TOKEN_FILES:
        (load_json if rel.endswith('.json') else load_yaml)(root / rel)""",
     """    return""",
     _TMP_CALL % ("R.test_broken_ssot(pathlib.Path(_d), files=('project.yaml',), "
                  "actions=('set_tier', 'move_result'))")),
    # plan id 又不收後綴字母 → 規格 17 抓得到
    ('plan_id_no_suffix', AC_REL,
     """PLAN_ID_RE = re.compile(r'((?:SQ|AQ)\\d+' + Q_SUFFIX + r')-v(\\d+)$')""",
     """PLAN_ID_RE = re.compile(r'((?:SQ|AQ)\\d+)-v(\\d+)$')""",
     _TMP_CALL % 'R.test_suffix_ids_rest(pathlib.Path(_d))'),
    # set_tier 的問題 id 比對又不收後綴字母（決策的 question 退成 main）→ 規格 17b 抓得到
    ('set_tier_no_suffix', 'skills/status/scripts/set_tier.py',
     """    questions = {q for q in questions if C.Q_ID_RE.fullmatch(q)}   # 後綴字母（SQ6b）也算合法問題 id""",
     """    questions = {q for q in questions if re.fullmatch(r'(SQ|AQ)\\d+', q)}""",
     _TMP_CALL % 'R.test_suffix_tier_question(pathlib.Path(_d))'),
    # 決策檢核的編號比對又不收後綴字母 → 規格 17 抓得到
    ('decisions_check_no_suffix', CD_REL,
     """Q_ID_RE = re.compile(r'(SQ|AQ)\\d+[a-z]*')
SQ_ID_RE = re.compile(r'SQ\\d+[a-z]*')""",
     """Q_ID_RE = re.compile(r'(SQ|AQ)\\d+')
SQ_ID_RE = re.compile(r'SQ\\d+')""",
     _TMP_CALL % 'R.test_suffix_ids_rest(pathlib.Path(_d))'),
    # 時間軸排序又不收後綴字母 → 規格 17 抓得到
    ('section_key_no_suffix', RT_REL,
     """    m = re.fullmatch(r'(SQ|AQ)(\\d+)([a-z]*)', name)   # 後綴字母（SQ6b）排在同號的無後綴之後
    if m:
        return (1 if m.group(1) == 'SQ' else 2, int(m.group(2)), m.group(3))""",
     """    m = re.fullmatch(r'(SQ|AQ)(\\d+)', name)
    if m:
        return (1 if m.group(1) == 'SQ' else 2, int(m.group(2)), '')""",
     _TMP_CALL % 'R.test_suffix_ids_rest(pathlib.Path(_d))'),
    # 同一支關卡的同一筆又記第二次 → 規格 25 抓得到
    ('existing_not_deduped', AC_REL,
     """        if seen >= counts[str(text)]:
            continue""",
     """        if False:
            continue""", 'R.test_finding_presentation()'),
    # 記正規化後的字串（指紋被遮掉）→ 規格 25 抓得到
    ('existing_normalized_text', AC_REL,
     """        raw = getattr(text, 'raw', '') or str(text)""",
     """        raw = str(text)""", 'R.test_finding_presentation()'),
    # gone 那一類又寫成「與本次動作無關」→ 規格 25 抓得到
    ('gone_wording', AC_REL,
     """    True: ('(既有項目) 動作前全專案關卡有回報、動作後沒有回報的項目共 {n} 筆；'
           '本次動作後這些項目不再回報，請確認是不是這次動作改掉的：'),""",
     """    True: ('(既有項目) 本動作前全專案關卡就已回報、與本次動作無關而仍在的項目共 {n} 筆；'
           '動作鏈只擋本次新增的，既有項目不擋：'),""", 'R.test_finding_presentation()'),
    # 印了 BLOCKER 才當掉又算沒事 → 規格 25 抓得到
    ('crash_after_blockers', AC_REL,
     """    if _GATE_TRACEBACK in out or (not rows and rc != 0):""",
     """    if not rows and rc != 0:""", 'R.test_finding_presentation()'),
    # 步驟紀錄又寫在判斷之前 → 規格 26 抓得到
    ('note_before_verdict', AC_REL,
     """        # 判斷要在寫步驟紀錄之前：中止時不得留下「本次新增 0 筆」這句不實的話
        if new:
            raise ChainError(f'{GATE_LABEL[key]} 本次新增 {len(new)} 筆（動作前沒有這些）：' + findings_text(new))
        if (n_kept or n_gone) and self.cur is not None:
            self.note(f'{GATE_LABEL[key]}：既有 {n_kept} 筆（不擋）、動作前有動作後沒有 {n_gone} 筆、本次新增 0 筆')""",
     """        if (n_kept or n_gone) and self.cur is not None:
            self.note(f'{GATE_LABEL[key]}：既有 {n_kept} 筆（不擋）、動作前有動作後沒有 {n_gone} 筆、本次新增 0 筆')
        if new:
            raise ChainError(f'{GATE_LABEL[key]} 本次新增 {len(new)} 筆（動作前沒有這些）：' + findings_text(new))""",
     'R.test_gate_note_after_verdict()'),
    # check_decisions 的 baseline 回空 → 規格 27 抓得到
    ('decisions_baseline_empty', AC_REL,
     """    return run_gate(root, 'decisions')[0]""",
     """    return []""", 'R.test_decisions_gate_baseline()'),
    # 只查目標問題的那一關又記既有 → 規格 28 抓得到
    ('plan_sq_records', AC_REL,
     """    ch.gate_check('plan_sq', rc, out, record=False)""",
     """    ch.gate_check('plan_sq', rc, out)""",
     _TMP_CALL % 'R.test_gate_existing_once(pathlib.Path(_d))'),
    # 動作解決掉的既有 blocker 又不記 → 規格 28 抓得到
    ('gone_not_recorded', AC_REL,
     """        n_gone = note_existing(GATE_LABEL[key], gone, gone=True) if record else 0""",
     """        n_gone = 0""",
     _TMP_CALL % 'R.test_gate_existing_once(pathlib.Path(_d))'),
    # 暫存空 bib 又不共用 → 規格 29 抓得到
    ('empty_bib_per_call', AC_REL,
     """    if not _EMPTY_BIB:
        fd, tmp = tempfile.mkstemp(prefix='empty-', suffix='.bib')""",
     """    if True:
        fd, tmp = tempfile.mkstemp(prefix='empty-', suffix='.bib')""",
     _TMP_CALL % 'R.test_empty_bib_not_leaked(pathlib.Path(_d))'),
    # 佔位節點的 subtype 又留空（整頁畫不出來）→ 規格 30 抓得到
    ('placeholder_no_subtype', 'skills/status/scripts/render_progress.py',
     """                pn['subtype'] = 'primary'""", """                pass""",
     _TMP_CALL % 'R.test_placeholder_plan_node(pathlib.Path(_d))'),
    # 工作區的連結又不視同原檔 → 規格 31 抓得到
    ('workspace_link_false', 'skills/analyze-data/scripts/rerun_all.py',
     """    return target.parts[-len(rel):] == rel""", """    return False""",
     _TMP_CALL % 'R.test_workspace_link_fingerprint(pathlib.Path(_d))'),
    # 不看工作區標記檔（專案自己的絕對 symlink 被當成原檔）→ 規格 31 抓得到
    ('workspace_link_no_marker', 'skills/analyze-data/scripts/rerun_all.py',
     """    if not path.is_symlink() or not (root / WORKSPACE_MARKER).exists():""",
     """    if not path.is_symlink():""",
     _TMP_CALL % 'R.test_workspace_link_fingerprint(pathlib.Path(_d))'),
    # 中止訊息又印正規化後的字串（<FP>／<DATE>）→ 規格 39 抓得到
    ('abort_normalized_text', AC_REL,
     """    return ' ｜ '.join(getattr(x, 'raw', '') or str(x) for x in rows)[:800]""",
     """    return ' ｜ '.join(str(x) for x in rows)[:800]""", _TMP_CALL % 'R.test_gate_baseline_shape(pathlib.Path(_d))'),
    # gate_baseline 又寫進 plan_sq（它不是跑出來的 baseline）→ 規格 39 抓得到
    ('gate_baseline_plan_sq', AC_REL,
     """            self.log.doc['gate_baseline'] = {k: [getattr(x, 'raw', '') or str(x) for x in v]
                                             for k, v in self.gate_base.items() if v and k != 'plan_sq'}""",
     """            self.log.doc['gate_baseline'] = {k: [getattr(x, 'raw', '') or str(x) for x in v]
                                             for k, v in self.gate_base.items() if v}""",
     _TMP_CALL % 'R.test_gate_baseline_shape(pathlib.Path(_d))'),
    # gate_baseline 又存正規化後的比對鍵（給人讀的紀錄裡路徑變成 <FP>）→ 規格 71 抓得到
    ('gate_baseline_normalized', AC_REL,
     """            self.log.doc['gate_baseline'] = {k: [getattr(x, 'raw', '') or str(x) for x in v]
                                             for k, v in self.gate_base.items() if v and k != 'plan_sq'}""",
     """            self.log.doc['gate_baseline'] = {k: list(v)
                                             for k, v in self.gate_base.items() if v and k != 'plan_sq'}""",
     _TMP_CALL % 'R.test_gate_baseline_raw(pathlib.Path(_d))'),
    # 比對改用原文（指紋／日期一變就被當成新增）→ 規格 71 抓得到
    ('gate_compare_raw', AC_REL,
     """    return _GATE_DATE_RE.sub('<DATE>', _GATE_FP_RE.sub('<FP>', line.rstrip()))""",
     """    return line.rstrip()""", _TMP_CALL % 'R.test_gate_baseline_raw(pathlib.Path(_d))'),
    # (a) 一律帶新值（動作前就過期的欄位也帶）→ 規格 32 抓得到
    ('carry_always', AC_REL,
     """    if policy.carry['results']:
        ri2 = TF.top_key(lines, 'results_fingerprint')""",
     """    if True:
        ri2 = TF.top_key(lines, 'results_fingerprint')""",
     _TMP_CALL % "R.test_stale_not_absorbed(pathlib.Path(_d), ('reassign_question',))"),
    # (a) 任一過期就兩欄都不動 → 規格 33 抓得到（results 相符時不帶，動作自己的 retag 就變成本次新增）
    ('carry_all_or_none', AC_REL,
     """    for col in ('results', 'source'):
        out[col] = bool(recorded.get(col)) and recorded[col] == now.get(col)
    return out""",
     """    for col in ('results', 'source'):
        out[col] = bool(recorded.get(col)) and recorded[col] == now.get(col)
    if not all(out.values()):
        out = {c: False for c in out}
    return out""",
     _TMP_CALL % 'R.test_one_column_stale(pathlib.Path(_d))'),
    # (a) state.analysis.validation 的 at 只帶一欄也改 → 規格 34 抓得到
    ('state_at_always', AC_REL,
     """    if val_policy.mark:
        val_fields.append(('at', f"'{date}'"))""",
     """    if True:
        val_fields.append(('at', f"'{date}'"))""",
     _TMP_CALL % 'R.test_stale_and_drift_independent(pathlib.Path(_d))'),
    # (b) 落後 item 照加 reaffirmed 標記 → 規格 37 抓得到
    ('mark_lagging', AC_REL,
     """        if not policy.mark or lagging:
            unmarked.append(vid)""",
     """        if not policy.mark:
            unmarked.append(vid)""",
     _TMP_CALL % 'R.test_lagging_item_shapes(pathlib.Path(_d))'),
    # (b) 驗證放鬆成不驗「不該加的標記」→ 規格 32 抓得到
    ('verify_skips_negative', AC_REL,
     """        elif mark is not None:
            raise ChainError(f'validation.yaml {vid} 不該加 {key} 標記'""",
     """        elif False:
            raise ChainError(f'validation.yaml {vid} 不該加 {key} 標記'""",
     'R.test_verify_validation_strict()'),
    # (c) 落後 item 照改掛 plan_id → 規格 37 抓得到
    ('rehang_lagging', AC_REL,
     """            if lagging and new_pid:
                sq_only.append(vid)      # 落後的 item 不改掛：plan_id 仍指向它真正驗過的版本
                new_pid = None""",
     """            if lagging and new_pid:
                sq_only.append(vid)      # 落後的 item 不改掛：plan_id 仍指向它真正驗過的版本""",
     _TMP_CALL % 'R.test_lagging_item_shapes(pathlib.Path(_d))'),
    # (c) 落後的判準漏掉（什麼都不算落後）→ 規格 37 抓得到
    ('lagging_none', AC_REL,
     """        if pid and active.get(sq) and pid != str(active[sq]):
            out.add(str(it.get('id')))""",
     """        if False:
            out.add(str(it.get('id')))""",
     _TMP_CALL % 'R.test_lagging_item_shapes(pathlib.Path(_d))'),
    # (d) 漂移照重登 waiver → 規格 32 抓得到
    ('waiver_on_drift', AC_REL,
     """    if ch.rerun_drift:
        # 動作前就漂移：重登會把「這組指紋下已豁免重跑」蓋到一組從沒被豁免過的指紋上""",
     """    if False:
        # 動作前就漂移：重登會把「這組指紋下已豁免重跑」蓋到一組從沒被豁免過的指紋上""",
     _TMP_CALL % "R.test_stale_not_absorbed(pathlib.Path(_d), ('reassign_question',))"),
    # (d) 漂移的判準漏掉（永遠不算漂移）→ 規格 34 抓得到
    ('drift_none', AC_REL,
     """                if fld in rr and str(rr.get(fld) or '') != self.fp_now[col]:
                    self.rerun_drift.append(fld)""",
     """                if False:
                    self.rerun_drift.append(fld)""",
     _TMP_CALL % 'R.test_stale_and_drift_independent(pathlib.Path(_d))'),
    # 政策又在鏈跑到一半才算（量到的是動作自己造成的差異）→ 規格 32 抓得到
    ('stale_baseline_late', AC_REL,
     """        self.take_stale_baseline()""",
     """        self.policy = StalePolicy(); self.state_policy = StalePolicy(); self.rerun_drift = []; self.stale_warn = []""",
     _TMP_CALL % "R.test_stale_not_absorbed(pathlib.Path(_d), ('reassign_question',))"),
    # (e) 未 confirmed 的 plan 照封新版 → 規格 36 抓得到
    ('seal_draft_plan', PC_REL,
     """    if plan.get("status") != "confirmed":
        out.append(f"{pid}: 尚未 confirmed")""",
     """    if False:
        out.append(f"{pid}: 尚未 confirmed")""",
     _TMP_CALL % 'R.test_dirty_source_plan_blocked(pathlib.Path(_d))'),
    # (e) 缺 content_hash 的 plan 照封新版 → 規格 36 抓得到
    ('seal_no_hash_plan', PC_REL,
     """    if not digest:
        out.append(f"{pid}: 缺 content_hash")""",
     """    if False:
        out.append(f"{pid}: 缺 content_hash")""",
     _TMP_CALL % 'R.test_dirty_source_plan_blocked(pathlib.Path(_d))'),
    # (e) content_hash 不符（內容被改過）的 plan 照封新版 → 規格 36 抓得到
    ('seal_hash_mismatch_plan', PC_REL,
     """    elif digest != content_hash(plan):
        out.append(f"{pid}: content_hash 不符——不得原地修改 confirmed plan")""",
     """    elif False:
        out.append(f"{pid}: content_hash 不符——不得原地修改 confirmed plan")""",
     _TMP_CALL % 'R.test_dirty_source_plan_blocked(pathlib.Path(_d))'),
    # (e) index 的 hash 與 plan 不一致照封新版 → 規格 36 抓得到
    ('seal_index_mismatch_plan', PC_REL,
     """    if entry and entry.get("content_hash") != digest:
        out.append(f"{pid}: index content_hash 與 plan 不一致")""",
     """    if False:
        out.append(f"{pid}: index content_hash 與 plan 不一致")""",
     _TMP_CALL % 'R.test_dirty_source_plan_blocked(pathlib.Path(_d))'),
    # (e) 前置條件不擋（只有 check_plan 報，而它看不到被換下的來源 plan）→ 規格 36 抓得到
    ('require_clean_noop', AC_REL,
     """    if bad:
        raise ChainError('；'.join(bad) + '。本動作要從這份 plan 封出新版，而重新封版會把未確認或被改過的內容'""",
     """    if False:
        raise ChainError('；'.join(bad) + '。本動作要從這份 plan 封出新版，而重新封版會把未確認或被改過的內容'""",
     _TMP_CALL % 'R.test_dirty_source_plan_blocked(pathlib.Path(_d))'),
    # (f) 文字照舊宣稱重接 → 規格 32 抓得到
    ('wording_claims_retag', AC_REL,
     """def carry_word(carry: dict[str, bool] | None) -> str:
    \"\"\"給人讀的動詞：有帶新值才叫「重接」，一欄都沒帶只能說「未重接」。\"\"\"
    if carry is None or carry.get('results') or carry.get('source'):
        return '重接'
    return '未重接'""",
     """def carry_word(carry: dict[str, bool] | None) -> str:
    \"\"\"給人讀的動詞：有帶新值才叫「重接」，一欄都沒帶只能說「未重接」。\"\"\"
    return '重接'""",
     _TMP_CALL % "R.test_stale_not_absorbed(pathlib.Path(_d), ('reassign_question',))"),
    # (f) 指紋移動的句子照舊寫成「舊 → 新」→ 規格 32 抓得到
    ('wording_fp_moved', AC_REL,
     """    if carry is None or (carry.get('results') and carry.get('source')):
        return f'results {old.get("results", "—")} → {fps["results"]}、source {old.get("source", "—")} → {fps["source"]}'""",
     """    if True:
        return f'results {old.get("results", "—")} → {fps["results"]}、source {old.get("source", "—")} → {fps["source"]}'""",
     _TMP_CALL % "R.test_stale_not_absorbed(pathlib.Path(_d), ('reassign_question',))"),
    # (g) 決策編號又寫死三位數 → 規格 38 抓得到
    ('decision_id_three_digits', AC_REL,
     """        m = re.fullmatch(r'D-(\\d{3,})', str(d.get('id') or ''))""",
     """        m = re.fullmatch(r'D-(\\d{3})', str(d.get('id') or ''))""",
     _TMP_CALL % 'R.test_decision_id_width(pathlib.Path(_d))'),
    # (g) render 的決策編號比對又寫死三位數（長編號被切成前三位）→ 規格 38 抓得到
    ('render_decision_id_three', 'skills/status/scripts/render_progress.py',
     """DECISION_ID_RE = re.compile(r'D-\\d{3,}')""",
     """DECISION_ID_RE = re.compile(r'D-\\d{3}')""",
     _TMP_CALL % 'R.test_decision_id_width(pathlib.Path(_d))'),
    # ---- 沒有 waiver、沒有 validation.yaml、沒有對應 item 時的文字 ----
    # waiver 狀態永遠算成「會重登」→ 規格 41（單元）抓得到
    ('waiver_state_carries', AC_REL,
     """        return bool(self.waiver) and not self.drift""",
     """        return True""",
     'R.test_waiver_text_units()'),
    # 沒有 waiver 時的現況說明被抽掉 → 規格 41（單元）抓得到
    ('waiver_why_none_empty', AC_REL,
     """        bits = [NO_WAIVER_SHORT]""",
     """        bits = ['']""",
     'R.test_waiver_text_units()'),
    # 短句永遠回「waiver 重登」→ 規格 41（單元）抓得到
    ('waiver_clause_none_claims', AC_REL,
     """    return f'不重登 waiver（{NO_WAIVER_BRIEF}）'""",
     """    return 'waiver 重登'""",
     'R.test_waiver_text_units()'),
    # 整句永遠回重登那句 → 規格 41（單元）抓得到
    ('waiver_sentence_none_claims', AC_REL,
     """    return (f'本專案沒有 rerun waiver——{ws.why_none()}；本動作不重登、不改 state.analysis.rerun；'
            + NO_WAIVER_TAIL)""",
     """    return 'rerun waiver 於新 fingerprint 重登——仍是 waived，不是 pass'""",
     'R.test_waiver_text_units()'),
    # 步驟標題永遠寫「重登」→ 規格 41（單元）抓得到
    ('waiver_step_name_claims', AC_REL,
     """def waiver_step_name(ws: WaiverState) -> str:""",
     """def waiver_step_name(ws: WaiverState) -> str:
    return 'rerun waiver 重登'""",
     'R.test_waiver_text_units()'),
    # 決策那一行把沒有 waiver 寫成漂移 → 規格 41（單元）抓得到
    ('waiver_decision_line_drift', AC_REL,
     """    if ws.waiver:
        return drift_text
    return f'未重登——{ws.why_none()}；state.analysis.rerun 一字不動，{NO_WAIVER_TAIL}'""",
     """    return drift_text""",
     'R.test_waiver_text_units()'),
    # known_consequences 永遠沿用「仍 waived」那句 → 規格 41（單元）抓得到
    ('waiver_known_line_claims', AC_REL,
     """def waiver_known_line(ws: WaiverState, ok_text: str, line: SameLine | None = None) -> str:""",
     """def waiver_known_line(ws: WaiverState, ok_text: str, line: SameLine | None = None) -> str:
    return ok_text""",
     'R.test_waiver_text_units()'),
    # stdout 摘要只寫「未重登」、不說為什麼 → 規格 41（單元）抓得到
    ('waiver_summary_text_bare', AC_REL,
     """    return f'未重登——{ws.why_none()}'""",
     """    return '未重登'""",
     'R.test_waiver_text_units()'),
    # 檔案不存在時照原句寫 → 規格 41（單元）抓得到
    ('absent_or_noop', AC_REL,
     """    return absent_text if vinfo.get('absent') else ok_text""",
     """    return ok_text""",
     'R.test_waiver_text_units()'),
    # 沒有對應 item 時又拼成「（無 item） 只把對應 item …」→ 規格 41（單元）抓得到
    ('rehang_clause_empty_splice', AC_REL,
     """    if not items:
        return f'{empty} {full}' if empty else scope + NO_ITEM_SENTENCE""",
     """    if not items:
        return f'{empty or "（無 item）"} {full}'""",
     'R.test_waiver_text_units()'),
    # waiver 狀態沒有接到動作算出來的 waiver 決策（鏈上一律讀同一個物件）→ 規格 41 抓得到
    ('chain_waiver_state_unwired', AC_REL,
     """        self.waiver_state = WaiverState(self.params.get('waiver_decision') or '', [],""",
     """        self.waiver_state = WaiverState('D-' + '001', [],""",
     _TMP_CALL % "R.test_untrue_waiver_text(pathlib.Path(_d), ('no_rerun/reassign_question',))"),
    # 沒有 validation.yaml 時照「頂層指紋過期」那句印 WARNING → 規格 41 抓得到
    ('absent_warn_as_stale', AC_REL,
     """        if not v_path.is_file():
            # 檔案不存在時沒有「頂層指紋」可比、也沒有「原記錄」可維持，不得照過期那一句寫
            self.stale_warn.append('WARNING 無 analysis/validation.yaml：這個檔不存在，'
                                   '沒有 fingerprint 可帶新值、沒有 item 可改掛或加 reaffirmed 標記')
        elif not self.policy.carry['results'] or not self.policy.carry['source']:""",
     """        if not self.policy.carry['results'] or not self.policy.carry['source']:""",
     _TMP_CALL % "R.test_untrue_waiver_text(pathlib.Path(_d), ('no_validation/reassign_question',))"),
    # 新 plan 的 amendment_reason 在沒有 validation.yaml 時照原句寫 → 規格 41 抓得到
    ('amend_absent_claims', 'skills/status/scripts/reassign_question.py',
     """    v_txt = (C.VALIDATION_ABSENT_TAIL if v_absent else""",
     """    v_txt = (f'只把對應 item 的 sq／plan_id 改掛 {to}／{new_pid}並重接頂層 fingerprint' if v_absent else""",
     _TMP_CALL % "R.test_untrue_waiver_text(pathlib.Path(_d), ('no_validation/reassign_question',))"),
    # 新 plan 的 amendment_reason（升回主問題那一支）在沒有 validation.yaml 時照原句寫 → 規格 41 抓得到
    ('amend_absent_claims_promote', 'skills/status/scripts/promote_question.py',
     """    v_txt = (C.VALIDATION_ABSENT_TAIL + '。' if v_absent else""",
     """    v_txt = ('只改掛 item 並重接 fingerprint。' if v_absent else""",
     _TMP_CALL % "R.test_untrue_waiver_text(pathlib.Path(_d), ('no_validation/promote_question',))"),
    # 沒有 waiver 也把漂移寫成「本次不重登 waiver」（暗示有 waiver）→ 規格 41 抓得到
    ('stale_rerun_warn_claims_waiver', AC_REL,
     """    if ws.waiver:
        return (f'WARNING state.analysis.rerun 的 {"／".join(ws.drift)} '
                f'{STALE_FP_REASON}：本次不重登 waiver')""",
     """    if True:
        return (f'WARNING state.analysis.rerun 的 {"／".join(ws.drift)} '
                f'{STALE_FP_REASON}：本次不重登 waiver')""",
     _TMP_CALL % "R.test_untrue_waiver_text(pathlib.Path(_d), ('pass_drift/reassign_question',))"),
    # 來源 plan 檢查從某一支動作掉線（7 支 × 各角色都要接上）→ 規格 42 抓得到
    ('require_clean_unwired', 'skills/status/scripts/move_sensitivity.py',
     """    C.require_clean_plans(root, [('來源', args.plan), ('目標', args.to_plan)])\n""",
     """""",
     _TMP_CALL % 'R.test_dirty_plan_wiring(pathlib.Path(_d))'),
    # state.analysis.validation 的狀態照抄 validation.yaml 頂層 → 規格 43 抓得到
    ('state_policy_copies_top', AC_REL,
     """        self.state_policy = StalePolicy(carry_of(recorded_fingerprints(sem.get('validation')), now))""",
     """        self.state_policy = StalePolicy(dict(self.policy.carry))""",
     _TMP_CALL % 'R.test_state_policy_independent(pathlib.Path(_d))'),
    # rerun 漂移只看 fingerprint 一欄 → 規格 44 抓得到
    ('drift_only_main_column', AC_REL,
     """            for fld, col in (('fingerprint', 'fingerprint'), ('input_fingerprint', 'input_fingerprint'),
                             ('results_fingerprint', 'results_fingerprint')):""",
     """            for fld, col in (('fingerprint', 'fingerprint'),):""",
     _TMP_CALL % 'R.test_drift_per_field(pathlib.Path(_d))'),
    # 量不到現值時照常帶新值、照常加標記 → 規格 45 抓得到
    ('fp_unavailable_carries', AC_REL,
     """            self.policy = StalePolicy({'results': False, 'source': False})
            self.state_policy = StalePolicy({'results': False, 'source': False})
            self.stale_warn""",
     """            self.policy = StalePolicy()
            self.state_policy = StalePolicy()
            self.stale_warn""",
     _TMP_CALL % 'R.test_fingerprint_unavailable(pathlib.Path(_d))'),
    # 動作前就過期／落後／漂移的 WARNING 不印 → 規格 32 抓得到
    ('stale_warn_not_printed', AC_REL,
     """        for line in self.stale_warn:
            warn(line)""",
     """        for line in self.stale_warn:
            pass""",
     _TMP_CALL % "R.test_stale_not_absorbed(pathlib.Path(_d), ('reassign_question',))"),
    # 決策編號的正規式又寫死三位數 → 規格 46 抓得到
    ('manifest_decision_id_three', 'skills/analyze-data/scripts/check_manifest.py',
     """DECISION_ID_RE = re.compile(r'D-\\d{3,}')""",
     """DECISION_ID_RE = re.compile(r'D-\\d{3}')""",
     'R.test_decision_id_regex_constants()'),
    # 批次／server 解析決策編號又寫死三位數 → 規格 46 抓得到
    ('batch_decision_line_three', 'skills/status/scripts/run_batch.py',
     """DECISION_LINE_RE = re.compile(r'決策 (D-\\d{3,})')""",
     """DECISION_LINE_RE = re.compile(r'決策 (D-\\d{3})')""",
     'R.test_decision_id_regex_constants()'),
    ('server_done_decision_three', 'skills/status/scripts/progress_server.py',
     """DONE_DECISION_RE = re.compile(r'^結果: 完成；決策 (D-\\d{3,}(?:–D-\\d{3,})?)', re.M)""",
     """DONE_DECISION_RE = re.compile(r'^結果: 完成；決策 (D-\\d{3}(?:–D-\\d{3})?)', re.M)""",
     'R.test_decision_id_regex_constants()'),
    ('decisions_link_id_three', 'skills/status/scripts/check_decisions.py',
     """DECISION_ID_RE = re.compile(r'D-\\d{3,}')""",
     """DECISION_ID_RE = re.compile(r'D-\\d{3}')""",
     'R.test_decision_id_regex_constants()'),
    # 「尚無正式結果」這個狀態整段不認 → 規格 47 抓得到（五支動作又全部中止）
    ('no_results_state_ignored', AC_REL,
     """        if self.no_results:
            # 沒有 results.json 就算不出任何 fingerprint""",
     """        if False:
            # 沒有 results.json 就算不出任何 fingerprint""",
     _TMP_CALL % "R.test_no_results_actions(pathlib.Path(_d), ('a/reassign_question',))"),
    # 尚無正式結果時照樣去算 validation 的 source fingerprint → 規格 47 抓得到
    ('no_results_calls_source_fp', AC_REL,
     """    fps = dict(NO_FP) if ch.no_results else source_fingerprint(ch.root)""",
     """    fps = source_fingerprint(ch.root)""",
     _TMP_CALL % "R.test_no_results_actions(pathlib.Path(_d), ('a/reorder_questions',))"),
    # 旗標沒跟著 carry 走（只拿到 carry 的文字 helper 就判不出來）→ 規格 50 抓得到
    ('carry_absent_blind', AC_REL,
     """    return bool(getattr(carry, 'no_results', False))""",
     """    return False""",
     'R.test_no_results_text_units()'),
    # Carry.copy() 把旗標丟掉（vinfo／summary 拿到的就退回舊說法）→ 規格 50 抓得到
    ('carry_copy_drops_flag', AC_REL,
     """    def copy(self) -> 'Carry':
        return Carry(self, self.no_results)""",
     """    def copy(self) -> 'Carry':
        return Carry(self)""",
     'R.test_no_results_text_units()'),
    # 尚無正式結果卻照樣說會重登 waiver → 規格 50 抓得到
    ('waiver_carries_without_results', AC_REL,
     """        return bool(self.waiver) and not self.drift and not self.no_results""",
     """        return bool(self.waiver) and not self.drift""",
     'R.test_no_results_text_units()'),
    # 尚無正式結果時又給「重跑 rerun_all 或另立 waiver」那套建議 → 規格 47 抓得到
    ('waiver_step_advises_rerun', AC_REL,
     """    if ch.no_results:
        # 尚無正式結果：沒有 fingerprint 可重登到""",
     """    if False:
        # 尚無正式結果：沒有 fingerprint 可重登到""",
     _TMP_CALL % "R.test_no_results_actions(pathlib.Path(_d), ('a/move_plan',))"),
    # 一致的新專案形狀也印 WARNING（那是正常階段）→ 規格 47 抓得到
    ('no_results_warn_always', AC_REL,
     """    if not bits:
        return ''
    # 沒有 waiver 決策時不得寫「不重登 waiver」""",
     """    if not bits:
        bits.append('（無）')
    # 沒有 waiver 決策時不得寫「不重登 waiver」""",
     _TMP_CALL % "R.test_no_results_actions(pathlib.Path(_d), ('a/demote_plan',))"),
    # 步驟標題還寫著要 retag → 規格 47 抓得到
    ('retag_step_name_lies', AC_REL,
     """    return NO_RESULTS_STEP if absent else 'results.json plan_id retag'""",
     """    return 'results.json plan_id retag'""",
     _TMP_CALL % "R.test_no_results_actions(pathlib.Path(_d), ('a/promote_question',))"),
    # 結果檔不存在時照樣整檔載入（關卡 traceback、前後都記成 CRASH）→ 規格 49 抓得到
    ('coverage_loads_missing_results', 'skills/evaluate/scripts/check_coverage.py',
     """    results = json.load(open(res_path, encoding='utf-8')) \\
        if os.path.exists(res_path) else None""",
     """    results = json.load(open(res_path, encoding='utf-8'))""",
     _TMP_CALL % 'R.test_no_results_gates(pathlib.Path(_d))'),
    # 結果檔不存在卻說成「無鍵」（讀的人會以為檔案在）→ 規格 53 抓得到
    ('coverage_links_message_lies', 'skills/evaluate/scripts/check_coverage.py',
     """                if results is None:
                    blockers.append(f'{sid}: link 無效, 結果檔 {res_name} 不存在'
                                    f'（尚無正式結果）, 對不到 \"{k}\"')""",
     """                if results is None:
                    blockers.append(f'{sid}: link 無效, results.json 無鍵 \"{k}\"')""",
     _TMP_CALL % 'R.test_no_results_links_message(pathlib.Path(_d))'),
    # 有 waiver 決策時不照實寫編號（c2 讀起來像沒有 waiver）→ 規格 51 抓得到
    ('waiver_no_results_ignores_waiver', AC_REL,
     """                + (f'（waiver 決策 {self.waiver}，範圍不變）' if self.waiver else ''))""",
     """                + '')""",
     _TMP_CALL % "R.test_no_results_waiver_text(pathlib.Path(_d), ('c2/reassign_question',))"),
    # 沒有 waiver 時那行 WARNING 又寫成「不重登 waiver」→ 規格 51 抓得到
    ('no_results_warn_claims_waiver', AC_REL,
     """    tail = '不重登 waiver' if waiver else f'不重登（{NO_WAIVER_BRIEF}）'""",
     """    tail = '不重登 waiver'""",
     _TMP_CALL % "R.test_no_results_waiver_text(pathlib.Path(_d), ('c1/reassign_question',))"),
    # 檔名那半句不讓理由，同一行把「尚無正式結果」整句講兩次 → 規格 57 抓得到
    ('no_results_brief_dups', AC_REL,
     """    return NO_RESULTS_BRIEF if line_need(line, SameLine.WHY) else RESULTS_REL + ' 不存在'""",
     """    return NO_RESULTS_BRIEF""",
     _TMP_CALL % "R.test_no_results_once_per_line(pathlib.Path(_d), ('c1/promote_question',))"),
    # 標記那一句又把理由重講一次（同一行兩次）→ 規格 57 的單元抓得到
    ('mark_clause_reason_again', AC_REL,
     """        why = []
        if line_need(line, SameLine.WHY):
            why.append(NO_RESULTS_SHORT)
        if line_need(line, SameLine.FP):
            why.append('沒有 fingerprint 可接')""",
     """        why = [NO_RESULTS_SHORT, '沒有 fingerprint 可接']""",
     'R.test_same_line_units()'),
    # 標記那一句連自己的理由都不講（只剩結論）→ 規格 50／57 的單元抓得到
    ('mark_clause_reason_gone', AC_REL,
     """        if line_need(line, SameLine.WHY):
            why.append(NO_RESULTS_SHORT)
        if line_need(line, SameLine.FP):
            why.append('沒有 fingerprint 可接')
        line_own(line, SameLine.MARK)""",
     """        line_own(line, SameLine.MARK)""",
     'R.test_same_line_units(); R.test_no_results_text_units()'),
    # 問過一次就該讓掉，卻每次都回「要講」→ 規格 57 的單元抓得到
    ('same_line_need_always', AC_REL,
     """        if phrase in self.said:
            return False
        self.said.add(phrase)
        return True""",
     """        self.said.add(phrase)
        return True""",
     'R.test_same_line_units()'),
    # 尚無正式結果的讓句漏到有結果的路徑（有結果也開始刪理由）→ 規格 57 的單元抓得到
    ('same_line_absent_always', AC_REL,
     """    def __init__(self, absent: Any = False) -> None:
        self.absent = bool(absent)
        self.said: set[str] = set()""",
     """    def __init__(self, absent: Any = False) -> None:
        self.absent = True
        self.said: set[str] = set()""",
     'R.test_same_line_units()'),
    # 主詞不登記：標記那一句說完，指紋那一句又說一次「不加 reaffirmed 標記」→ 規格 57 的單元抓得到
    ('same_line_own_noop', AC_REL,
     """    def own(self, phrase: str) -> None:
        \"\"\"這個片語由本子句說出（不問，直接登記）：它是本子句的主詞，讓給別人就不成句。\"\"\"
        if self.absent:
            self.said.add(phrase)""",
     """    def own(self, phrase: str) -> None:
        \"\"\"這個片語由本子句說出（不問，直接登記）：它是本子句的主詞，讓給別人就不成句。\"\"\"
        return None""",
     'R.test_same_line_units()'),
    # 指紋那一句的標記結論不讓（同一行講兩次）→ 規格 57 的單元抓得到
    ('fp_text_keeps_mark', AC_REL,
     """    tail = '本次不寫 fingerprint' + ('、不加 reaffirmed 標記' if line_need(line, SameLine.MARK) else '')""",
     """    tail = '本次不寫 fingerprint' + '、不加 reaffirmed 標記'""",
     'R.test_same_line_units()'),
    # waiver 那一句不吃同一行的狀態，理由照講一次（有 waiver 的那種也一樣）→ 規格 57 的單元抓得到
    ('waiver_no_results_reason_again', AC_REL,
     """        because = []
        if line_need(line, SameLine.WHY):
            because.append(NO_RESULTS_SHORT)
        if line_need(line, SameLine.FP):
            because.append('沒有 fingerprint 可算')""",
     """        because = [NO_RESULTS_SHORT, '沒有 fingerprint 可算']""",
     'R.test_same_line_units()'),
    # 步驟紀錄那一則沒把同一行的狀態帶給指紋那一句 → 規格 57 抓得到
    ('validation_note_dups_reason', AC_REL,
     """    bits.append('fingerprint ' + fp_move_text(vinfo['old'], fps, carry, line=line))""",
     """    bits.append('fingerprint ' + fp_move_text(vinfo['old'], fps, carry))""",
     _TMP_CALL % "R.test_no_results_once_per_line(pathlib.Path(_d), ('c1/reorder_questions',))"),
    # 決策那一行沒把同一行的狀態帶給標記那一句 → 規格 57 抓得到
    ('reorder_decision_line_unwired', 'skills/status/scripts/reorder_questions.py',
     """            vinfo, f'analysis/validation.yaml：{C.mark_clause(ch.policy, vinfo.get("reaffirm_key") or "—", l3)}、不改掛', C.VALIDATION_ABSENT)""",
     """            vinfo, f'analysis/validation.yaml：{C.mark_clause(ch.policy, vinfo.get("reaffirm_key") or "—")}、不改掛', C.VALIDATION_ABSENT)""",
     _TMP_CALL % "R.test_no_results_once_per_line(pathlib.Path(_d), ('c1/reorder_questions',))"),
    # check_coverage 那一句又不看實況（永遠沿用寫死的原句）→ 規格 52 抓得到
    ('coverage_text_always_normal', AC_REL,
     """    if not isinstance(cov, dict) or not cov.get('path') or coverage_normal(cov):
        return normal""",
     """    if True:
        return normal""",
     'R.test_coverage_sentence_units()'),
    # 動作前沒有快照時，步驟紀錄又寫「快照前 TAMPER 0 筆（<本次預期>）」→ 規格 52 抓得到
    ('coverage_note_contradicts', AC_REL,
     """    if not cov['snapshot_before']:
        # 動作前沒有快照""",
     """    if False:
        # 動作前沒有快照""",
     _TMP_CALL % "R.test_coverage_sentence_actions(pathlib.Path(_d), ('q/reassign_question',))"),
    # 調順序在沒有快照時整段跳過、連一則照實的紀錄都不留 → 規格 52 抓得到
    ('reorder_no_snapshot_silent', 'skills/status/scripts/reorder_questions.py',
     """        if not snap.is_file():
            ch.note(C.coverage_note(cov))""",
     """        if False:
            ch.note(C.coverage_note(cov))""",
     _TMP_CALL % "R.test_coverage_sentence_actions(pathlib.Path(_d), ('q/reorder_questions',))"),
    # plan_results 關卡在缺檔時還傳 --results（前後都是「找不到 results」＝沒在看）→ 規格 49 抓得到
    ('plan_results_always_results', AC_REL,
     """        if (root / RESULTS_REL).is_file():
            return ['check_plan', root, '--require-confirmed', '--results', RESULTS_REL]
        return ['check_plan', root, '--require-confirmed']""",
     """        return ['check_plan', root, '--require-confirmed', '--results', RESULTS_REL]""",
     _TMP_CALL % 'R.test_no_results_gates(pathlib.Path(_d))'),
    # 搬結果鍵的動作少掛前置拒絕（會先寫檔再倒）→ 規格 48 抓得到
    ('move_key_precondition_unwired', AC_REL,
     """    dst = str(payload.get('to_plan') or '').strip()
    if no_results(root):
        return None, NO_RESULTS_MOVE""",
     """    dst = str(payload.get('to_plan') or '').strip()""",
     _TMP_CALL % 'R.test_no_results_move_blocked(pathlib.Path(_d))'),
    # 調順序後的 TAMPER 比對因為缺檔被跳過 → 規格 47 抓得到
    ('reorder_skips_tamper_compare', 'skills/status/scripts/reorder_questions.py',
     """        if snap.is_file():
            rc, out = C.run_script('check_coverage', *C.coverage_argv(root))""",
     """        if snap.is_file() and (root / 'analysis/results.json').is_file():
            rc, out = C.run_script('check_coverage', *C.coverage_argv(root))""",
     _TMP_CALL % "R.test_no_results_actions(pathlib.Path(_d), ('b/reorder_questions',))"),
    # move_plan 搬了 links 卻沒登記 → 規格 55 抓得到
    ('moved_link_not_registered', 'skills/status/scripts/move_plan.py',
     "        ch.register_moved_links(linfo['moved_links'], src_q, dst_q)\n", '',
     _TMP_CALL % "R.test_moved_link_existing(pathlib.Path(_d), ('move_plan',))"),
    # demote_plan 搬了 links 卻沒登記 → 規格 56 抓得到
    ('moved_link_demote_not_registered', 'skills/status/scripts/demote_plan.py',
     "        ch.register_moved_links(linfo['moved_links'], src_q, dst_q)\n", '',
     _TMP_CALL % "R.test_moved_link_no_results(pathlib.Path(_d), ('demote_plan',))"),
    # 對照不限鍵：沒搬走的 link 也跟著換問題 → 規格 54 抓得到
    ('moved_link_any_key', AC_REL,
     "        if m.group('qid') != mv.src_q or f'\"{mv.key}\"' not in item:",
     "        if m.group('qid') != mv.src_q:", 'R.test_moved_link_forms_units()'),
    # 對照不限來源問題：別的問題報的同一個鍵也算同一筆 → 規格 54 抓得到
    ('moved_link_any_source', AC_REL,
     "        if m.group('qid') != mv.src_q or f'\"{mv.key}\"' not in item:",
     "        if f'\"{mv.key}\"' not in item:", 'R.test_moved_link_forms_units()'),
    # 登記不挑前綴：cite:／ms: 的 link 也被當成結果鍵 → 規格 54 抓得到
    ('moved_link_any_prefix', AC_REL,
     "            if str(one).startswith(RESULTS_LINK):",
     '            if True:', 'R.test_moved_link_forms_units()'),
    # 對照給了所有關卡，不只 check_coverage → 規格 54 抓得到
    ('moved_link_all_gates', AC_REL,
     "    return list(moved) if key in MOVED_LINK_GATES else []",
     '    return list(moved)', 'R.test_moved_link_forms_units()'),
    # 第三種對照形式沒接上 → 規格 54 抓得到
    ('moved_link_form_unwired', AC_REL,
     "        for form in (mapped, item, *moved_link_forms(mapped, moved or [])):",
     '        for form in (mapped, item):', 'R.test_moved_link_forms_units()'),
    # 定位退回「第一個第三格寫主子問題」，第二格是不是編號清單不看 → 規格 58 抓得到
    ('glossary_first_main_cell', AC_REL,
     "        if cells[2] == GLOSSARY_MAIN_CELL and (cells[1] == GLOSSARY_EMPTY_Q or _SQ_LIST_RE.fullmatch(cells[1])):",
     '        if cells[2] == GLOSSARY_MAIN_CELL:', 'R.test_glossary_locate()'),
    # code fence 裡的行也照看 → 規格 58 抓得到
    ('glossary_fence_ignored', AC_REL,
     """    out: list[bool] = []
    marker = ''""",
     """    return [False] * len(lines)
    out: list[bool] = []
    marker = ''""", 'R.test_glossary_locate()'),
    # 主子問題列多於一列時改最後一列 → 規格 58 抓得到
    ('glossary_many_main_last', AC_REL,
     """    if len(main_rows) > 1:
        return -1, -1, -1, -1
    anchor = main_rows[0] if main_rows else""",
     '    anchor = main_rows[-1] if main_rows else', 'R.test_glossary_locate()'),
    # 沒有主子問題列就回 -1（只有 AQ 列的表找不到）→ 規格 58 抓得到
    ('glossary_no_main_aborts', AC_REL,
     '    anchor = main_rows[0] if main_rows else (aq_rows[0] if aq_rows else -1)',
     '    anchor = main_rows[0] if main_rows else -1', 'R.test_glossary_locate()'),
    # AQ 編號不收後綴字母 → 規格 58 抓得到
    ('glossary_aq_no_suffix', AC_REL,
     '        if not fenced[i] and len(cells) >= 4 and AQ_RE.fullmatch(cells[1]):',
     "        if not fenced[i] and len(cells) >= 4 and re.fullmatch(r'AQ\\d+', cells[1]):",
     'R.test_glossary_locate()'),
    # 節尾退回 `^##`（下一個一級標題漏掉）→ 規格 58 抓得到
    ('glossary_section_end_h2', AC_REL,
     '    sec_end = next((i for i in range(sec + 1, len(lines)) if i in heads), len(lines))',
     "    sec_end = next((i for i in range(sec + 1, len(lines)) if re.match(r'^##', lines[i])), len(lines))",
     'R.test_glossary_locate()'),
    # setext 標題不算標題 → 規格 58 抓得到
    ('glossary_setext_ignored', AC_REL,
     '        if nxt < len(lines) and not fenced[nxt] and _SETEXT_RULE_RE.fullmatch(lines[nxt]):',
     '        if False:', 'R.test_glossary_locate()'),
    # 兩種略過原因不分（都寫成無編號對照表）→ 規格 58 抓得到
    ('glossary_skip_reason_flat', AC_REL,
     '    return GLOSSARY_MANY_MAIN if len(main_rows) > 1 else GLOSSARY_NO_TABLE',
     '    return GLOSSARY_NO_TABLE', 'R.test_glossary_locate()'),
    # 略過時第 (7) 項寫成已更新 → 規格 59（單元）抓得到
    ('glossary_skipped_as_done', AC_REL, "    if ginfo.get('skipped'):", '    if False:',
     'R.test_glossary_decision_units()'),
    # 只改到一部分仍寫兩部分 → 規格 59（單元）抓得到
    ('glossary_decision_all_parts', AC_REL,
     "    said = [parts[k] for k in ginfo.get('changed') or [] if k in parts]",
     '    said = list(parts.values())', 'R.test_glossary_decision_units()'),
    # 備註裡的「降為 <編號>」不收後綴字母，新子句插進編號中間 → 規格 58 抓得到
    ('glossary_demote_clause_suffix', 'skills/status/scripts/reassign_question.py',
     "        hits = list(re.finditer(r'降為 [A-Z]{2}\\d+' + C.Q_SUFFIX, note))",
     "        hits = list(re.finditer(r'降為 [A-Z]{2}\\d+', note))", 'R.test_glossary_locate()'),
    # 第 (7) 項不分情況照舊寫（降附錄那一支）→ 規格 59 抓得到
    ('glossary_decision_fixed_demote', 'skills/status/scripts/reassign_question.py',
     "        + C.glossary_decision_text(ginfo, {'主子問題列': f'主子問題列改「{remaining}」', f'{to} 列': f'補 {to} 一列'}) + '\\n'",
     "        + f'(7) GLOSSARY.md 編號對照表：主子問題列改「{remaining}」、補 {to} 一列' + '\\n'",
     _TMP_CALL % "R.test_glossary_decision_actions(pathlib.Path(_d), ('none/reassign_question',))"),
    # 第 (7) 項不分情況照舊寫（升回那一支）→ 規格 59 抓得到
    ('glossary_decision_fixed_promote', 'skills/status/scripts/promote_question.py',
     "            + C.glossary_decision_text(ginfo, {'主子問題列': f'主子問題列加回 {to}', f'{src} 列': f'{src} 列註明已升回'}) + '\\n'",
     "            + f'(7) GLOSSARY.md 編號對照表：主子問題列加回 {to}、{src} 列註明已升回' + '\\n'",
     _TMP_CALL % "R.test_glossary_decision_actions(pathlib.Path(_d), ('many/promote_question',))"),
    # 一列都改不到時仍寫成更新 → 規格 58 抓得到
    ('glossary_promote_empty_changed', 'skills/status/scripts/promote_question.py',
     '    if not changed:', '    if False:', 'R.test_glossary_locate()'),
    # promote 找來源列不跳過 fence，改到的是範例列 → 規格 65 抓得到
    ('glossary_promote_fence_seen', 'skills/status/scripts/promote_question.py',
     """    for i in range(sec, sec_end):
        if fenced[i]:
            continue""",
     """    for i in range(sec, sec_end):
        if False:
            continue""", 'R.test_glossary_promote_fence()'),
    # 沒有這個檔那一句少了建檔提示 → 規格 64 抓得到
    ('glossary_hint_dropped', AC_REL,
     "        return f'(7) {GLOSSARY_REL}：專案沒有這個檔，編號對照表未更新（{GLOSSARY_INIT_HINT}）'",
     "        return f'(7) {GLOSSARY_REL}：專案沒有這個檔，編號對照表未更新'", 'R.test_glossary_init_hint()'),
    # 有檔也附上建檔提示 → 規格 64 抓得到
    ('glossary_hint_always', AC_REL,
     "    return f'(7) {GLOSSARY_REL} 編號對照表：' + '、'.join(said)",
     "    return f'(7) {GLOSSARY_REL} 編號對照表：' + '、'.join(said) + f'（{GLOSSARY_INIT_HINT}）'",
     'R.test_glossary_init_hint()'),
    # 動作自己拼「沒有這個檔」那句 note，提示跟著漏掉 → 規格 59 抓得到
    ('glossary_note_hand_written', 'skills/status/scripts/promote_question.py',
     '            ch.note(C.GLOSSARY_MISSING_NOTE)', "            ch.note('無 GLOSSARY.md，略過')",
     _TMP_CALL % "R.test_glossary_decision_actions(pathlib.Path(_d), ('none/promote_question',))"),
    # 範本少了與 project.yaml glossary 的分工那句 → 規格 66 抓得到
    ('glossary_template_no_split', GT_REL,
     '，翻譯對照則以 `project.yaml` 的 `glossary` 為準：譯名只登在那裡，定義只寫在這裡。', '。',
     'R.test_glossary_docs()'),
    # 已經有編號列也當成「對照表還是空的」→ 第二次就會再追加一次 → 規格 60 抓得到
    ('ig_skip_as_append', IG_REL,
     """    if main_rows or aq_rows:
        return SKIP,""",
     """    if False:
        return SKIP,""", _TMP_CALL % 'R.test_init_glossary_states(pathlib.Path(_d))'),
    # 入口不先攔「已經有編號列」，走進前置條件變成 BLOCKER → 規格 60 抓得到
    ('ig_skip_not_shortcircuited', IG_REL,
     """    if state == SKIP:
        print(f'init_glossary {VERSION}：{C.GLOSSARY_REL} {why}，不寫任何檔、不記決策'""",
     """    if False:
        print(f'init_glossary {VERSION}：{C.GLOSSARY_REL} {why}，不寫任何檔、不記決策'""",
     _TMP_CALL % 'R.test_init_glossary_states(pathlib.Path(_d))'),
    # 有檔也照範本整份寫（覆寫既有內容）→ 規格 60 抓得到
    ('ig_append_overwrites', IG_REL,
     '    tail = body[body.index(TABLE_HEADING):]',
     '    return body\n    tail = body[body.index(TABLE_HEADING):]',
     _TMP_CALL % 'R.test_init_glossary_states(pathlib.Path(_d))'),
    # 追加時把既有內容丟掉 → 寫入前的「以舊內容開頭」那道檢查要擋下來 → 規格 60 抓得到
    ('ig_append_drops_old', IG_REL, '    new = old + sep + tail', '    new = sep + tail',
     _TMP_CALL % 'R.test_init_glossary_states(pathlib.Path(_d))'),
    # `{{ID_ROWS}}` 沒代換 → 規格 60 抓得到
    ('ig_rows_not_substituted', IG_REL,
     '    body = template.replace(ID_ROWS_TOKEN, rows)', '    body = template',
     _TMP_CALL % 'R.test_init_glossary_states(pathlib.Path(_d))'),
    # `question` 裡的 `|` 不轉義，那一列被拆成兩格 → 規格 60 抓得到
    ('ig_rows_no_escape', IG_REL,
     "    return ' '.join(str(text).split()).replace('|', r'\\|')", "    return ' '.join(str(text).split())",
     _TMP_CALL % 'R.test_init_glossary_states(pathlib.Path(_d))'),
    # goals 空時主子問題列的第二格留空，定位認不出那一列 → 規格 60 抓得到
    ('ig_rows_no_empty_mark', IG_REL,
     '    rows = [f\'| {"、".join(sq_ids) if sq_ids else C.GLOSSARY_EMPTY_Q} | {C.GLOSSARY_MAIN_CELL} |  |\']',
     '    rows = [f\'| {"、".join(sq_ids)} | {C.GLOSSARY_MAIN_CELL} |  |\']',
     _TMP_CALL % 'R.test_init_glossary_states(pathlib.Path(_d))'),
    # 建了檔卻沒記決策 → 規格 60 抓得到
    ('ig_no_decision', IG_REL, '        C.append_decision(root, entry, backups)', '        pass',
     _TMP_CALL % 'R.test_init_glossary_states(pathlib.Path(_d))'),
    # 鏈不重新判斷檔案現況，沿用 dry-run 當時那個 → 規格 61 抓得到
    ('ig_state_not_rechecked', IG_REL,
     """    state, why = glossary_state(root)
    if state != ctx['state']:
        raise ChainError(f'{C.GLOSSARY_REL} 的現況已經不是 dry-run 當時那樣（{ctx["why"]} → {why}）：'
                         '一個位元都沒改，請重跑 --dry-run')""",
     "    state, why = ctx['state'], ctx['why']",
     _TMP_CALL % 'R.test_init_glossary_guards(pathlib.Path(_d))'),
    # 新建的檔沒登記進 Backups，失敗還原時留在原地 → 規格 61 抓得到
    ('ig_new_file_not_registered', IG_REL,
     '        bk = backups.backup(g_path)      # 原本不存在時只記進 created，失敗還原＝把新建的檔刪掉',
     '        bk = None', _TMP_CALL % 'R.test_init_glossary_guards(pathlib.Path(_d))'),
    # 預設理由又寫成使用者沒做過的裁定 → 規格 67 抓得到
    ('ig_default_reason_claims', IG_REL,
     """    reason_parts = [args.reason.strip()] if args.reason else [f'使用者裁定建立 {C.GLOSSARY_REL}（未附理由）']""",
     """    reason_parts = [args.reason.strip()] if args.reason else ['使用者裁定每個專案都要有一份術語表（未附理由）']""",
     _TMP_CALL % 'R.test_init_glossary_reason_wording(pathlib.Path(_d))'),
    # 決策第 (1) 項又說「四段的表頭以外都還是空的」（編號對照表其實已經填了編號）→ 規格 67 抓得到
    ('ig_create_says_four', IG_REL,
     """                 f'編號對照表列{rows_phrase(ctx["ids"])}，縮寫、變數、方法三段只有表頭')""",
     """                 f'編號對照表列{rows_phrase(ctx["ids"])}，四段的表頭以外都還是空的')""",
     _TMP_CALL % 'R.test_init_glossary_reason_wording(pathlib.Path(_d))'),
    # project-init 第 7 步的命令不帶理由 → 規格 67 抓得到
    ('ig_project_init_no_reason', 'skills/project-init/SKILL.md',
     'init_glossary.py <root> --apply --reason "project-init 建立專案時一併建立"',
     'init_glossary.py <root> --apply',
     _TMP_CALL % 'R.test_init_glossary_reason_wording(pathlib.Path(_d))'),
    # 不看同名標題，有那一節也照樣再追加一次 → 規格 68 抓得到
    ('ig_heading_not_checked', IG_REL,
     """    if has_table_heading(lines):
        return SKIP, SKIP_NO_ROWS""",
     """    if False:
        return SKIP, SKIP_NO_ROWS""", _TMP_CALL % 'R.test_init_glossary_heading_order(pathlib.Path(_d))'),
    # fence 裡的標題也算「已經有那一節」→ 規格 68 抓得到
    ('ig_heading_in_fence', IG_REL,
     '    heads = C._heading_lines(lines, C._fenced_mask(lines))',
     '    heads = C._heading_lines(lines, [False] * len(lines))',
     _TMP_CALL % 'R.test_init_glossary_heading_order(pathlib.Path(_d))'),
    # 不檢查自己認不認得（認不得也不說）→ 規格 69 抓得到
    ('ig_no_self_check', IG_REL,
     """    if len(main_rows) == 1 and len(aq_rows) == want_aq:
        return '', ''""",
     """    if True:
        return '', ''""", _TMP_CALL % 'R.test_init_glossary_self_check(pathlib.Path(_d))'),
    # 認不得的那幾列只印 WARNING、決策不提 → 規格 69 抓得到
    ('ig_self_note_not_in_decision', IG_REL,
     """    first += ctx.get('self_note') or ''   # 自己的定位認不得那幾列時照實補一句（兩種都補）""",
     """    first += ''""", _TMP_CALL % 'R.test_init_glossary_self_check(pathlib.Path(_d))'),
    # 首次建檔的檔頭又寫死某兩支的名字 → 規格 70 抓得到
    ('decisions_header_hardcoded', AC_REL,
     """    return head if head.endswith('.py') else 'academic-pipeline 的動作腳本'""",
     """    return 'reassign_question.py／set_figure_role.py'""",
     _TMP_CALL % 'R.test_decisions_header_author(pathlib.Path(_d))'),
]


def test_teeth(tmp: Path) -> None:
    """把每個修法逐一改壞（只在暫存複本），確認對應規格的斷言真的會紅。"""
    sandbox = shadow_plugin(tmp / 'teeth')
    pristine = {rel: (PLUGIN / rel).read_text(encoding='utf-8') for rel in {t[1] for t in TEETH}}
    results = {}
    for name, rel, old, new, call in TEETH:
        assert pristine[rel].count(old) == 1, f'{name}: {rel} 裡的原文出現 {pristine[rel].count(old)} 次'
        (sandbox / rel).write_text(pristine[rel].replace(old, new, 1), encoding='utf-8')
        proc = _run_in_shadow(sandbox, call)
        results[name] = proc.returncode
        (sandbox / rel).write_text(pristine[rel], encoding='utf-8')
        assert proc.returncode != 0, \
            f'把 {name} 改壞之後測試仍通過，斷言沒有牙\n{proc.stdout[-900:]}{proc.stderr[-900:]}'
    # 影子沒改壞時要是綠的——否則上面的紅不能歸因於「改壞」
    ok = _run_in_shadow(sandbox, 'R.test_glossary_locate(); R.test_glossary_decision_units()\n'
                        'R.test_glossary_promote_fence(); R.test_glossary_init_hint(); R.test_glossary_docs()\n'
                        'R.test_json_scan(); R.test_comment_modes(); R.test_retag_scale(limit=2.0)\n'
                        'R.test_finding_presentation(); R.test_gate_note_after_verdict(); '
                        'R.test_decisions_gate_baseline()\n'
                        'R.test_waiver_text_units(); R.test_decision_id_regex_constants()\n'
                        'R.test_no_results_text_units(); R.test_moved_link_forms_units()\n'
                        + _TEXT_CALLS + '\n'
                        + _TMP_CALL % ('R.test_decisions_style_and_append(pathlib.Path(_d)); '
                                       'R.test_suffix_ids_rest(pathlib.Path(_d)); '
                                       'R.test_suffix_tier_question(pathlib.Path(_d)); '
                                       'R.test_inbox_indent(pathlib.Path(_d)); '
                                       'R.test_batch_warning(pathlib.Path(_d)); '
                                       'R.test_gate_existing_once(pathlib.Path(_d)); '
                                       'R.test_empty_bib_not_leaked(pathlib.Path(_d)); '
                                       'R.test_placeholder_plan_node(pathlib.Path(_d)); '
                                       'R.test_workspace_link_fingerprint(pathlib.Path(_d)); '
                                       "R.test_broken_ssot(pathlib.Path(_d), files=('project.yaml',), "
                                       "actions=('set_tier', 'move_result')); "
                                       'R.test_decision_id_width(pathlib.Path(_d)); '
                                       'R.test_gate_baseline_shape(pathlib.Path(_d)); '
                                       'R.test_lagging_item_shapes(pathlib.Path(_d)); '
                                       'R.test_one_column_stale(pathlib.Path(_d)); '
                                       'R.test_stale_and_drift_independent(pathlib.Path(_d)); '
                                       'R.test_dirty_source_plan_blocked(pathlib.Path(_d)); '
                                       'R.test_state_policy_independent(pathlib.Path(_d)); '
                                       'R.test_drift_per_field(pathlib.Path(_d)); '
                                       'R.test_fingerprint_unavailable(pathlib.Path(_d)); '
                                       'R.test_dirty_plan_wiring(pathlib.Path(_d)); '
                                       "R.test_untrue_waiver_text(pathlib.Path(_d), ('no_rerun/reassign_question', "
                                       "'no_validation/reassign_question', 'pass_drift/reassign_question')); "
                                       "R.test_stale_not_absorbed(pathlib.Path(_d), ('reassign_question',)); "
                                       'R.test_no_results_gates(pathlib.Path(_d)); '
                                       'R.test_no_results_move_blocked(pathlib.Path(_d)); '
                                       "R.test_no_results_actions(pathlib.Path(_d), ('a/reassign_question', "
                                       "'a/reorder_questions', 'a/move_plan', 'a/demote_plan', "
                                       "'a/promote_question', 'b/reorder_questions')); "
                                       "R.test_moved_link_existing(pathlib.Path(_d), ('move_plan',)); "
                                       "R.test_moved_link_no_results(pathlib.Path(_d), ('demote_plan',)); "
                                       "R.test_glossary_decision_actions(pathlib.Path(_d), "
                                       "('both/reassign_question',)); "
                                       'R.test_init_glossary_states(pathlib.Path(_d)); '
                                       'R.test_init_glossary_guards(pathlib.Path(_d)); '
                                       'R.test_init_glossary_fresh(pathlib.Path(_d)); '
                                       'R.test_init_glossary_reason_wording(pathlib.Path(_d)); '
                                       'R.test_init_glossary_heading_order(pathlib.Path(_d)); '
                                       'R.test_init_glossary_self_check(pathlib.Path(_d)); '
                                       'R.test_decisions_header_author(pathlib.Path(_d)); '
                                       'R.test_gate_baseline_raw(pathlib.Path(_d)); '
                                       "R.test_init_glossary_end_to_end(pathlib.Path(_d), ('有結果',))"))
    assert ok.returncode == 0, f'未改壞的影子複本就失敗，驗牙不成立\n{ok.stdout[-900:]}{ok.stderr[-900:]}'
    shutil.rmtree(sandbox)
    print(f'[regression] 驗牙：{len(TEETH)} 處改壞都讓測試失敗、未改壞的影子複本是綠的'
          f'（rc={sorted(set(results.values()))}）: pass')


# ======================================================================
# 規格 18～24：全專案關卡「只擋這次新增的」
# ======================================================================

def _dirty_fixture(tmp: Path, name: str, tamper: bool = True) -> Path:
    """乾淨 fixture ＋ 一批「動作前就已經存在、與動作無關」的問題。

    一次湊齊七種：protocol 未 confirmed（check_plan）、validation item blocker（check_validation）、
    非終態問題（check_coverage BLOCKER，其中一個的 id 會被動作改掉，用來驗 id 對照）、
    欄位改動／新增／被移除三種 TAMPER、決策舊條目的 schema 問題。
    頂層指紋照 refix 接回現行值；驗證過期不在本檔範圍。

    tamper=False：只留「有既有 BLOCKER、但沒有任何 TAMPER」那一種組合。這條路徑走的是原本的嚴格
    TAMPER 判準與原本的 `--update-snapshot`，而快照更新之後 check_coverage 仍因既有 BLOCKER 回非 0
    ——那一步也必須只擋新增的，所以要單獨釘住。
    """
    root = copy_fixture(tmp, name)
    path = root / 'protocol/study-protocol.yaml'
    path.write_text(path.read_text(encoding='utf-8').replace('status: confirmed', 'status: draft', 1), encoding='utf-8')
    path = root / 'analysis/validation.yaml'
    path.write_text(path.read_text(encoding='utf-8').replace(
        'independent_recalculation: {mode: second-implementation, result: pass,',
        'independent_recalculation: {mode: not-applicable, result: not-applicable,', 1), encoding='utf-8')
    path = root / 'project.yaml'
    text = path.read_text(encoding='utf-8')
    text = text.replace('      status: addressed\n      status_reason: "原本的理由二"',
                        '      status: open\n      status_reason: "原本的理由二"', 1)
    if tamper:
        text = text.replace('      links: []\n',
                            '      links: []\n'
                            '    - id: AQ7\n      question: "附錄問題七"\n      why: "為什麼七"\n'
                            '      evidence: [analysis]\n      success_criteria: "附錄準則七"\n'
                            '      status: open\n      status_reason: "尚未開始"\n      links: []\n', 1)
        text = text.replace('      question: "問題一"', '      question: "問題一（已改，尚未確認）"', 1)
    path.write_text(text, encoding='utf-8')
    if tamper:
        path = root / 'evaluations/goals-snapshot.json'
        doc = json.loads(path.read_text(encoding='utf-8'))
        doc['appendix_questions'].append({'id': 'AQ8', 'question': '附錄問題八', 'why': '為什麼八',
                                          'evidence': ['analysis'], 'success_criteria': '附錄準則八',
                                          'status': 'dropped'})
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    path = root / 'decisions.yaml'
    path.write_text(path.read_text(encoding='utf-8').replace('    stage: analyze-data', '    stage: 不在詞彙表', 1),
                    encoding='utf-8')
    refix_fingerprints(root)
    return root


def _gate_lines(root: Path, key: str) -> list[str]:
    cmd = C.gate_cmd(root, key)
    rc, out = C.run_script(str(cmd[0]), *cmd[1:])
    return C.gate_findings(rc, out)


def _dirty_baseline(root: Path) -> dict[str, list[str]]:
    base = {k: _gate_lines(root, k) for k in ('plan', 'validation', 'coverage', 'decisions')}
    assert any('protocol' in x for x in base['plan']), base['plan']
    assert any('V1' in x for x in base['validation']), base['validation']
    assert any('AQ7' in x for x in base['coverage']) and any('SQ2' in x for x in base['coverage']), base['coverage']
    _rc, out = C.run_script('check_coverage', *C.coverage_argv(root))
    assert sorted(C.tamper_keys(out)) == ['AQ7: 新增', 'AQ8: 被移除', 'SQ1.question'], C.tamper_keys(out)
    return base


def test_findings_multiset() -> None:
    """規格 20：正規化、id 對照、multiset、關卡當掉的比對規則。"""
    stale = 'BLOCKER V7: plan_id SQ6-v1 不是 SQ6 active plan SQ6-v2'
    bumped = 'BLOCKER V7: plan_id SQ6-v1 不是 SQ6 active plan SQ6-v3'
    new, kept, gone = C.diff_findings([stale], [bumped], {'SQ6-v2': 'SQ6-v3'})
    assert (new, kept, gone) == ([], [bumped], []), (new, kept, gone)
    # 完整 token：`SQ6` 不得改到 `SQ6-v1`／`SQ6_x`，但 `SQ6.question` 要改到
    mapped = C.map_ids('SQ6 SQ6-v1 SQ6_x SQ6.question SQ60', {'SQ6': 'AQ9'})
    assert mapped == 'AQ9 SQ6-v1 SQ6_x AQ9.question SQ60', mapped
    # 指紋與日期遮掉之後同形；既有 1 筆、動作後 2 筆 → 多的那筆是新增
    stale_fp = 'BLOCKER validation 上游已過期：記錄 source fingerprint 0123456789ab，目前 fedcba987654'
    other_fp = 'BLOCKER validation 上游已過期：記錄 source fingerprint aaaabbbbcccc，目前 ddddeeeeffff'
    assert C.normalize_finding(stale_fp) == C.normalize_finding(other_fp)
    new, kept, gone = C.diff_findings(C.gate_findings(1, stale_fp), C.gate_findings(1, stale_fp + '\n' + other_fp), {})
    assert len(new) == 1 and len(kept) == 1 and not gone, (new, kept, gone)
    # 動作前有、動作後沒有：不得靜默消失
    new, kept, gone = C.diff_findings([stale], [], {})
    assert (new, kept, gone) == ([], [], [stale]), (new, kept, gone)
    # 關卡本身當掉：沒有 BLOCKER 行就記一筆 CRASH；同一筆才不算新增
    crash = C.gate_findings(1, 'x\nAttributeError: boom\n')
    assert crash == ['CRASH rc=1: AttributeError: boom'], crash
    assert C.diff_findings(crash, crash, {})[0] == []
    assert C.diff_findings(crash, C.gate_findings(2, 'x\nKeyError: other\n'), {})[0] \
        == ['CRASH rc=2: KeyError: other']
    assert C.tamper_keys('TAMPER SQ6.question: "甲（一）" → "乙"（goals 自上次評估後被改動, 需使用者確認）') \
        == ['SQ6.question'], '問題敘述含全形括號時鍵不能被切掉'
    print('[regression] 規格 20：BLOCKER 正規化（指紋／日期）、id 對照只換完整 token、'
          'multiset 只算多出來的那筆、關卡當掉記成 CRASH: pass')


def test_existing_not_blocking(tmp: Path) -> None:
    """規格 18：帶既有問題的專案，八個動作 dry-run 與 apply 都走得完，既有項目照實列出。"""
    root = _dirty_fixture(tmp, 'dirty_base')
    base = _dirty_baseline(root)
    chain = [a for a in ACTIONS if a not in ('set_tier', 'set_figure_role', 'package_edit')]
    assert len(chain) == 8, chain
    for action in chain:
        script, args = ACTIONS[action]
        work = tmp / f'dirty__{action}'
        shutil.copytree(root, work)
        rc, out = run_dry(script, work, *args)
        assert rc == 0, f'{action} dry-run 被既有問題擋下 rc={rc}\n{out[-2000:]}'
        assert '既有項目 #1' in out, f'{action} dry-run 沒有把既有項目列進摘要\n{out[-2000:]}'
        before = bytes_of(work)
        rc, out = run_action(script, work, *args)
        assert rc == 0, f'{action} apply 被既有問題擋下 rc={rc}\n{out[-2000:]}'
        assert '既有項目 #1' in out, f'{action} apply 沒有把既有項目列進摘要\n{out[-2000:]}'
        assert bytes_of(work) != before, f'{action} 什麼都沒改'
        did = re.search(r'決策 (D-\d+)', out)
        assert did, out[-800:]
        entry = next(d for d in yaml.safe_load((work / 'decisions.yaml').read_text(encoding='utf-8'))['decisions']
                     if d['id'] == did.group(1))
        assert '既有項目' in str(entry.get('known_consequences') or ''), \
            f'{action}：既有項目沒有寫進決策的 known_consequences\n{entry.get("known_consequences")}'
        log = json.loads((work / re.search(r'run log (\S+)', out).group(1)).read_text(encoding='utf-8'))
        assert log.get('gate_baseline'), f'{action}：步驟紀錄沒有留 baseline'
        # 動作後既有項目仍報得出來；快照裡動作前的 TAMPER 還在
        after = {k: _gate_lines(work, k) for k in base}
        assert any('protocol' in x for x in after['plan']), after['plan']
        assert any('V1' in x for x in after['validation']), after['validation']
        assert any('AQ7' in x for x in after['coverage']), after['coverage']
        _rc, cov = C.run_script('check_coverage', *C.coverage_argv(work))
        keys = set(C.tamper_keys(cov))
        assert {'AQ8: 被移除', 'SQ1.question'} <= keys, f'{action}：既有 TAMPER 被快照吃掉了\n{sorted(keys)}'
        shutil.rmtree(work)
    shutil.rmtree(root)
    # 有既有 BLOCKER、但沒有任何 TAMPER：走原本的嚴格 TAMPER 判準 ＋ 原本的 --update-snapshot，
    # 而快照更新之後 check_coverage 仍因既有 BLOCKER 回非 0——那一步也只能擋新增的。
    root = _dirty_fixture(tmp, 'dirty_notamper', tamper=False)
    _rc, cov = C.run_script('check_coverage', *C.coverage_argv(root))
    assert not C.tamper_keys(cov), C.tamper_keys(cov)
    assert any('狀態非終態' in x for x in C.gate_findings(_rc, cov)), cov[-400:]
    rc, out = run_dry('reassign_question.py', root, '--from', 'SQ2')
    assert rc == 0, f'無 TAMPER 但有既有 BLOCKER 的專案 dry-run 被擋下 rc={rc}\n{out[-2500:]}'
    rc, out = run_action('reassign_question.py', root, '--from', 'SQ2')
    assert rc == 0, f'無 TAMPER 但有既有 BLOCKER 的專案 apply 被擋下 rc={rc}\n{out[-2500:]}'
    _rc, cov = C.run_script('check_coverage', *C.coverage_argv(root))
    assert not C.tamper_keys(cov), f'快照該被更新成 0 tamper\n{cov[-400:]}'
    assert any('狀態非終態' in x for x in C.gate_findings(_rc, cov)), f'既有 BLOCKER 應該還在\n{cov[-400:]}'
    assert '既有項目 #1' in out, out[-1500:]
    shutil.rmtree(root)
    print(f'[regression] 規格 18：帶既有問題的專案 {len(chain)} 個動作 dry-run ＋ apply 都 rc=0，'
          '既有項目進摘要／決策／步驟紀錄，動作後仍報得出來、快照沒有代替使用者確認；'
          '「有既有 BLOCKER、無 TAMPER」那條路徑（走原本的 --update-snapshot）也不被既有的擋下: pass')


def test_existing_decisions_only(tmp: Path) -> None:
    """規格 24：只跑 check_decisions 的三個動作在帶既有問題的專案上照樣完成。"""
    root = _dirty_fixture(tmp, 'dirty_cd')
    for action in ('set_tier', 'set_figure_role', 'package_edit'):
        script, args = ACTIONS[action]
        work = tmp / f'dirty_cd__{action}'
        shutil.copytree(root, work)
        rc, out = run_action(script, work, *args)
        assert rc == 0, f'{action} 被既有問題擋下 rc={rc}\n{out[-2000:]}'
        log_rel = re.search(r'run log (\S+)', out)
        log = json.loads((work / log_rel.group(1)).read_text(encoding='utf-8')) if log_rel else {}
        steps = ' '.join(json.dumps(log.get('steps') or [], ensure_ascii=False))
        for other in ('check_plan', 'check_validation', 'check_coverage'):
            assert other not in steps, f'{action} 多跑了 {other}\n{steps[:600]}'
        shutil.rmtree(work)
    # 「只擋新增」不等於放行本次 D#：注入一個讓本次條目自己出 WARNING 的 stage，必須擋
    shadow = shadow_plugin(tmp / 'cd_inject')
    rel = 'skills/status/scripts/set_tier.py'
    pristine = (PLUGIN / rel).read_text(encoding='utf-8')
    anchor = '        C.append_decision(root, entry, backups)'
    assert pristine.count(anchor) == 1, pristine.count(anchor)
    (shadow / rel).write_text(pristine.replace(
        anchor, "        entry['stage'] = '不在詞彙表'\n" + anchor, 1), encoding='utf-8')
    work = tmp / 'dirty_cd__own_warning'
    shutil.copytree(root, work)
    before = bytes_of(work)
    script, args = ACTIONS['set_tier']
    rc, out = run_action(script, work, *args, plugin=shadow)
    assert rc != 0, f'本次 D# 自己有 WARNING 卻沒被擋下\n{out[-2000:]}'
    blocker = next((ln for ln in out.splitlines() if ln.startswith('BLOCKER')), '')
    assert re.search(r'D-\d+', blocker) and 'WARNING' in blocker, f'擋下的理由沒指出是本次 D#\n{blocker}'
    assert bytes_of(work) == before, 'set_tier 失敗後沒有逐位元還原'
    shutil.rmtree(work)
    shutil.rmtree(shadow)
    shutil.rmtree(root)
    print('[regression] 規格 24：舊決策條目有 schema 問題時 set_tier／set_figure_role／package_edit '
          '都完成、不多跑別的全專案關卡；本次 D# 自己出 WARNING 仍被擋下: pass')


def test_snapshot_merge(tmp: Path) -> None:
    """規格 21：快照三方合併——被搬移的問題帶 TAMPER 時舊值留著，其他題的既有 TAMPER 也不動。"""
    s0 = ([{'id': 'SQ6', 'question': '舊的六', 'why': '六'}, {'id': 'SQ7', 'question': '七', 'why': '七'}],
          [{'id': 'AQ8', 'question': '八', 'why': '八'}])
    g0 = ([{'id': 'SQ6', 'question': '新的六', 'why': '六'}, {'id': 'SQ7', 'question': '七', 'why': '七'},
           {'id': 'SQ9', 'question': '九', 'why': '九'}], [])
    g1 = ([{'id': 'SQ7', 'question': '七', 'why': '七'}, {'id': 'SQ9', 'question': '九', 'why': '九'}],
          [{'id': 'AQ9', 'question': '新的六', 'why': '六', 'status': 'blocked'}])
    out = C.merge_snapshot(s0, g0, g1, {'SQ6': 'AQ9'})
    moved = next(x for x in out['appendix_questions'] if x['id'] == 'AQ9')
    assert moved['question'] == '舊的六', moved          # 既有未確認的改動：舊值留在快照裡
    assert moved['status'] == 'blocked', moved           # 本次動作的效果：照動作後的值
    assert [x['id'] for x in out['sub_questions']] == ['SQ7'], out['sub_questions']   # SQ9 是既有「新增」
    assert any(x['id'] == 'AQ8' for x in out['appendix_questions']), out               # 既有「被移除」原樣保留
    assert C.COVERAGE_FIELDS == ('question', 'success_criteria', 'evidence', 'why')
    # 搬移的問題帶 TAMPER：合併後 check_coverage 還是報得出同一個鍵
    root = _dirty_fixture(tmp, 'merge_tamper')
    path = root / 'evaluations/goals-snapshot.json'
    doc = json.loads(path.read_text(encoding='utf-8'))
    old_q = next(x for x in doc['sub_questions'] if x['id'] == 'SQ2')['question']
    proj = root / 'project.yaml'
    proj.write_text(proj.read_text(encoding='utf-8').replace('      question: "問題二"',
                                                             '      question: "問題二（已改，尚未確認）"', 1),
                    encoding='utf-8')
    refix_fingerprints(root)
    rc, out_txt = run_action('reassign_question.py', root, '--from', 'SQ2')
    assert rc == 0, out_txt[-2000:]
    doc = json.loads(path.read_text(encoding='utf-8'))
    merged = [x for x in doc['appendix_questions'] if x.get('question') == old_q]
    assert merged, f'搬移後快照沒有保留舊的問題敘述（{old_q}）\n{json.dumps(doc, ensure_ascii=False)[:800]}'
    new_id = merged[0]['id']
    _rc, cov = C.run_script('check_coverage', *C.coverage_argv(root))
    keys = set(C.tamper_keys(cov))
    assert f'{new_id}.question' in keys, f'搬移後 TAMPER 應改報新 id 的 question\n{sorted(keys)}'
    assert {'AQ8: 被移除', 'SQ1.question'} <= keys, sorted(keys)
    shutil.rmtree(root)
    print('[regression] 規格 21：快照三方合併保住既有的欄位改動／被移除／新增三種 TAMPER，'
          '只把本次動作的效果寫進快照: pass')


def test_snapshot_ids_not_reused(tmp: Path) -> None:
    """規格 22：自動配號避開快照裡的舊號；明確指到快照裡的號會被拒並說明。"""
    root = _dirty_fixture(tmp, 'snap_ids')
    assert 'AQ8' in C.used_question_ids(root)
    assert C.next_question_id(root, 'AQ') == 'AQ9', C.next_question_id(root, 'AQ')
    why = C.question_id_occupied_why(root, 'AQ8')
    assert why and why != C.QID_CLASSIC and '快照' in why, why
    rc, out = run_dry('reassign_question.py', root, '--from', 'SQ2', '--to', 'AQ8')
    assert rc != 0 and '快照' in out, f'指到快照裡的號應被拒並說明\n{out[-800:]}'
    rc, out = run_action('reassign_question.py', root, '--from', 'SQ2')
    assert rc == 0 and 'AQ9' in out, out[-1200:]
    shutil.rmtree(root)
    print('[regression] 規格 22：自動配號跳過快照裡的 AQ8 配到 AQ9；明確指到 AQ8 被拒並說明原因: pass')


# 影子複本注入錯誤：每組一到兩處替換（原文都必須恰好出現一次）。
# A／B 的第二處是拿掉動作自己的就地護欄，否則錯誤在送到全專案關卡之前就被攔下來，驗不到關卡的牙齒。
INJECT: list[tuple[str, str, list[tuple[str, str, str]]]] = [
    ('retag_少改一鍵', 'check_plan.py --require-confirmed --results', [
        (AC_REL, '    for key, new_pid in key_map.items():\n        if doc.has((key, \'plan_id\'))',
         '    for key, new_pid in list(key_map.items())[1:]:\n        if doc.has((key, \'plan_id\'))'),
        (AC_REL, "        if k in key_map and (not isinstance(b, dict) or b.get('plan_id') != key_map[k]):",
         "        if False and k in key_map:"),
    ]),
    ('item_plan_id_沒改', 'check_validation.py', [
        (AC_REL, '            if new_pid and pid_i >= 0:\n                lines[pid_i] = TF.replace_value(lines[pid_i], new_pid)',
         '            if False and pid_i >= 0:\n                lines[pid_i] = TF.replace_value(lines[pid_i], new_pid)'),
        (AC_REL, "            if new_pid and vid not in policy.lagging:\n                a['plan_id'] = new_pid",
         "            if False:\n                a['plan_id'] = new_pid"),
    ]),
    ('順手改另一題的_question', 'TAMPER', [
        (AC_REL, '        self.backup(path)\n        write_text(path, text)',
         "        self.backup(path)\n        if path.name == 'project.yaml':\n"
         "            text = text.replace('附錄問題二', '附錄問題二順手改掉')\n        write_text(path, text)"),
    ]),
]


def test_new_findings_blocked(tmp: Path) -> None:
    """規格 19（牙齒）：本次動作新造成的問題一定要擋——乾淨專案與帶既有問題的專案各跑一輪。"""
    shadow = shadow_plugin(tmp / 'inject')
    pristine = {rel: (PLUGIN / rel).read_text(encoding='utf-8') for rel in {e[0] for _n, _w, es in INJECT for e in es}}
    fixtures = {'clean': copy_fixture(tmp, 'teeth_clean'), 'dirty': _dirty_fixture(tmp, 'teeth_dirty'),
                'dirty_notamper': _dirty_fixture(tmp, 'teeth_notamper', tamper=False)}
    # 先確認未注入的影子複本是綠的，上面的紅才能歸因於注入
    for tag, src in fixtures.items():
        work = tmp / f'inject_ok_{tag}'
        shutil.copytree(src, work)
        rc, out = run_action('reassign_question.py', work, '--from', 'SQ2', plugin=shadow)
        assert rc == 0, f'未注入的影子複本在 {tag} fixture 就失敗，驗牙不成立\n{out[-1500:]}'
        shutil.rmtree(work)
    for name, want, edits in INJECT:
        for rel, old, new in edits:
            assert pristine[rel].count(old) == 1, f'{name}: {rel} 裡的原文出現 {pristine[rel].count(old)} 次'
        for rel in {e[0] for e in edits}:
            text = pristine[rel]
            for r, old, new in edits:
                if r == rel:
                    text = text.replace(old, new, 1)
            (shadow / rel).write_text(text, encoding='utf-8')
        for tag, src in fixtures.items():
            work = tmp / f'inject_{tag}'
            shutil.copytree(src, work)
            before = bytes_of(work)
            rc, out = run_action('reassign_question.py', work, '--from', 'SQ2', plugin=shadow)
            assert rc != 0, f'{name}（{tag}）：注入錯誤之後仍然 rc=0，關卡沒有牙\n{out[-2000:]}'
            assert '已還原' in out, f'{name}（{tag}）：沒有還原\n{out[-2000:]}'
            assert want in out, f'{name}（{tag}）：擋下來的理由不是 {want}\n{out[-2000:]}'
            if tag != 'clean' and want != 'TAMPER':
                assert '本次新增' in out, f'{name}（{tag}）：不是走「只擋新增」那條判準\n{out[-2000:]}'
            if tag == 'dirty_notamper' and want == 'TAMPER':
                assert 'TAMPER 與預期不符' in out, \
                    f'{name}（{tag}）：沒有 baseline TAMPER 時應走原本的嚴格判準\n{out[-2000:]}'
            assert bytes_of(work) == before, f'{name}（{tag}）：SSOT 沒有逐位元還原'
            shutil.rmtree(work)
        for rel in {e[0] for e in edits}:
            (shadow / rel).write_text(pristine[rel], encoding='utf-8')
    for src in fixtures.values():
        shutil.rmtree(src)
    shutil.rmtree(shadow)
    print(f'[regression] 規格 19（牙齒）：{len(INJECT)} 組注入的錯誤在 {len(fixtures)} 種 fixture'
          '（乾淨／帶既有問題／有既有 BLOCKER 但無 TAMPER）上都 rc≠0、已還原、SSOT 逐位元回到動作前: pass')


# ======================================================================
# 規格 25～30：關卡呈現、暫存檔、佔位節點、工作區連結的指紋
# ======================================================================

def _clear_sinks() -> None:
    C._EXISTING_SINK.clear()
    C._EXISTING_SEEN.clear()
    C._WARN_SINK.clear()


def test_finding_presentation() -> None:
    """規格 25：同一支腳本只記一次、記原文、兩類文字分開、印了 BLOCKER 才當掉也要記。"""
    # 關卡印了幾行 BLOCKER 才丟 traceback：那幾行不代表關卡跑完了，仍要記一筆 CRASH
    noisy = 'BLOCKER 甲壞了\nTraceback (most recent call last)\n  File "gate.py", line 1\nValueError: 爆了\n'
    rows = C.gate_findings(1, noisy)
    assert len(rows) == 2 and rows[1].startswith('CRASH rc=1') and '爆了' in rows[1], rows
    assert len(C.gate_findings(1, 'BLOCKER 甲壞了\n')) == 1, '沒有 traceback 不該多記一筆'
    # 比對用正規化後的字串，呈現用原文：讀的人要看得到是哪個指紋
    old = C.gate_findings(1, 'BLOCKER 指紋 0123456789ab 與記錄不符')
    now = C.gate_findings(1, 'BLOCKER 指紋 fedcba987654 與記錄不符')
    new, kept, gone = C.diff_findings(old, now, {})
    assert (new, gone) == ([], []) and len(kept) == 1, (new, kept, gone)
    assert str(kept[0]) == 'BLOCKER 指紋 <FP> 與記錄不符', kept
    _clear_sinks()
    assert C.note_existing('check_plan.py', kept) == 1
    assert C._EXISTING_SINK == [('check_plan.py', False, 'BLOCKER 指紋 fedcba987654 與記錄不符')], C._EXISTING_SINK
    # 同一支腳本的不同參數、同一支跑第二次：都只記一次
    assert C.note_existing('check_plan.py --sq --require-confirmed', kept) == 0
    assert C.note_existing('check_plan.py --require-confirmed --results', kept) == 0
    assert C.note_existing('check_plan.py', kept) == 0
    assert len(C._EXISTING_SINK) == 1, C._EXISTING_SINK
    # 真正重複的訊息（同一次呼叫裡兩行相同）仍按 multiset 保留筆數
    twice = C.gate_findings(1, 'BLOCKER 同一句\nBLOCKER 同一句\n')
    assert C.note_existing('check_validation.py', twice) == 2
    assert C.note_existing('check_validation.py', twice) == 0
    assert len(C._EXISTING_SINK) == 3, C._EXISTING_SINK
    # 兩類文字分開：gone 那一段不能寫成「與本次動作無關」
    assert C.note_existing('check_coverage.py', C.gate_findings(1, 'BLOCKER 被動作改掉了'), gone=True) == 1
    text = C.existing_consequences()
    parts = text.split('(既有項目)')
    assert len(parts) == 3, text
    stay, went = parts[1], parts[2]
    assert '與本次動作無關' in stay and '與本次動作無關' not in went, text
    assert '請確認' in went and '請確認' not in stay, text
    assert '被動作改掉了' in went and '被動作改掉了' not in stay, text
    assert '指紋 fedcba987654' in stay and '<FP>' not in text, text
    _clear_sinks()
    print('[regression] 規格 25：同一支關卡的同一筆只記一次（不同參數、封兩次版都算）、呈現用原文而不是'
          '正規化後的字串、既有與「動作前有動作後沒有」分兩段、印了 BLOCKER 才丟 traceback 也記 CRASH: pass')


def test_gate_note_after_verdict() -> None:
    """規格 26：關卡中止時步驟紀錄不得留下「本次新增 0 筆」。"""
    ch = C.Chain.__new__(C.Chain)   # 只驗 gate_check 的判斷順序，不要整條鏈的檔案 I/O
    ch.action, ch.id_map, ch.moved_links, ch.cur = 'reassign_question', {}, [], {'notes': []}
    ch.gate_base = {'plan': C.gate_findings(1, 'BLOCKER 既有的一筆\n')}
    _clear_sinks()
    try:
        ch.gate_check('plan', 1, 'BLOCKER 既有的一筆\nBLOCKER 這次才有的一筆\n')
    except C.ChainError as exc:
        assert '本次新增 1 筆' in str(exc), exc
    else:
        raise AssertionError('本次新增的發現沒有被擋下')
    assert ch.cur['notes'] == [], f'中止時步驟紀錄留下了不實的話: {ch.cur["notes"]}'
    # 沒有新增時才寫那句，而且筆數要是實際記下的筆數
    ch.cur = {'notes': []}
    _clear_sinks()
    ch.gate_check('plan', 1, 'BLOCKER 既有的一筆\n')
    assert ch.cur['notes'] == ['check_plan.py：既有 1 筆（不擋）、動作前有動作後沒有 0 筆、本次新增 0 筆'], \
        ch.cur['notes']
    # 已經記過的那筆不再記，也就不再多寫一句步驟紀錄
    ch.cur = {'notes': []}
    ch.gate_check('plan', 1, 'BLOCKER 既有的一筆\n')
    assert ch.cur['notes'] == [], ch.cur['notes']
    _clear_sinks()
    print('[regression] 規格 26：關卡中止時不寫「本次新增 0 筆」、通過時的筆數等於實際記下的筆數: pass')


def test_decisions_gate_baseline() -> None:
    """規格 27：check_decisions 的 baseline 真的有取（rc 非 0 的前置條件在專案層到不了，替換 run_gate）。"""
    orig = C.run_gate
    out_old = 'BLOCKER 舊條目的 stage 不在詞彙表\n'
    out_new = 'BLOCKER 這次 append 才造成的一筆\n'
    try:
        C.run_gate = lambda root, key: (C.gate_findings(1, out_old), out_old)
        _clear_sinks()
        base = C.decisions_baseline(Path('/nonexistent'))
        assert [str(x) for x in base] == ['BLOCKER 舊條目的 stage 不在詞彙表'], base
        C.check_decisions_gate(Path('/nonexistent'), 'D-900', base)   # 既有的不擋
        assert len(C._EXISTING_SINK) == 1 and C._EXISTING_SINK[0][1] is False, C._EXISTING_SINK
        C.run_gate = lambda root, key: (C.gate_findings(1, out_new), out_new)
        try:
            C.check_decisions_gate(Path('/nonexistent'), 'D-900', base)
        except C.ChainError as exc:
            assert '本次新增 1 筆' in str(exc), exc
        else:
            raise AssertionError('append 之後新造成的一筆沒有被擋下')
    finally:
        C.run_gate = orig
        _clear_sinks()
    print('[regression] 規格 27：check_decisions 的 baseline 取得到——既有的不擋、append 後新造成的仍擋: pass')


def _plan_hash_mismatch(root: Path, pid: str) -> str:
    """把一個 active plan 的 content_hash 改掉（plan 與 index 同步），回那筆 BLOCKER 的關鍵字。

    這筆只有完整 `check_plan` 報得出來，`check_plan --sq <別的問題>` 不會報——正好用來驗
    `--sq` 那一關不得把它記成「動作前有、動作後沒有」。
    """
    path = root / f'analysis/plans/{pid}.yaml'
    text = path.read_text(encoding='utf-8')
    old = re.search(r'^content_hash: *"?([0-9a-f]{8,})"?', text, re.M).group(1)
    bogus = 'f' * (len(old) - 1) + 'e'   # 開頭不能是數字：全數字的值會被 YAML 讀成 int，index 那邊就對不上型別
    path.write_text(text.replace(old, bogus), encoding='utf-8')
    index = root / 'analysis/plans/index.yaml'
    index.write_text(index.read_text(encoding='utf-8').replace(old, bogus), encoding='utf-8')
    return f'{pid}: content_hash 不符'


def test_gate_existing_once(tmp: Path) -> None:
    """規格 28：既有項目每支腳本只記一次、動作解決掉的記成 gone、`--sq` 那一關不記既有。"""
    root = copy_fixture(tmp, 'gate_once')
    want_kept = _plan_hash_mismatch(root, 'AQ1-v1')   # 別題的 plan；本動作完全不碰它
    path = root / 'project.yaml'                      # SQ2 宣稱 addressed 卻沒有證據鏈
    path.write_text(path.read_text(encoding='utf-8').replace(
        '      links: ["results:m1"]', '      links: []', 1), encoding='utf-8')
    refix_fingerprints(root)
    base = {k: _gate_lines(root, k) for k in ('plan', 'plan_results', 'validation', 'coverage')}
    want_gone = 'SQ2: addressed 但 links 為空'
    assert sum(want_kept in x for x in base['plan']) == 1, base['plan']
    assert sum(want_kept in x for x in base['plan_results']) == 1, base['plan_results']
    assert sum(want_gone in x for x in base['coverage']) == 1, base['coverage']
    assert not base['validation'], base['validation']
    _rc, sq_out = C.run_script('check_plan', root, '--sq', 'SQ2', '--require-confirmed')
    assert want_kept not in sq_out, f'--sq SQ2 竟然也報 {want_kept}，這個測試驗不到東西'
    # move_result 封兩次版（來源與目標 plan 各一次）→ 完整 check_plan 跑兩次，同一筆只能記一次
    script, args = ACTIONS['move_result']
    rc, out = run_action(script, root, *args)
    assert rc == 0, f'既有問題擋下了 move_result rc={rc}\n{out[-2500:]}'
    rows = [ln for ln in out.splitlines() if '既有項目 #' in ln]
    stay = [ln for ln in rows if '（既有）' in ln]
    went = [ln for ln in rows if '（動作前有、動作後沒有）' in ln]
    assert len(rows) == 2, f'既有項目不是 2 筆（{len(rows)}）\n' + '\n'.join(rows)
    assert len(stay) == 1 and want_kept in stay[0] and stay[0].split('：', 1)[1].startswith('check_plan.py'), rows
    assert len(went) == 1 and want_gone in went[0] and 'check_coverage.py' in went[0], rows
    assert want_kept not in went[0], f'只查目標問題的那一關把別題的既有發現記成 gone\n{went[0]}'
    did = re.search(r'決策 (D-\d+)', out).group(1)
    entry = next(d for d in yaml.safe_load((root / 'decisions.yaml').read_text(encoding='utf-8'))['decisions']
                 if d['id'] == did)
    cons = str(entry.get('known_consequences') or '')
    parts = cons.split('(既有項目)')
    assert len(parts) == 3, cons
    assert want_kept in parts[1] and '與本次動作無關' in parts[1], cons
    assert want_gone in parts[2] and '請確認' in parts[2] and '與本次動作無關' not in parts[2], cons
    log = json.loads((root / re.search(r'run log (\S+)', out).group(1)).read_text(encoding='utf-8'))
    steps = json.dumps(log.get('steps') or [], ensure_ascii=False)
    assert steps.count('check_plan.py：既有') == 1, f'同一支關卡的既有項目在步驟紀錄裡出現多次\n{steps[:900]}'
    shutil.rmtree(root)
    print('[regression] 規格 28：封兩次版的動作裡同一筆既有發現只記一次、`check_plan --sq` 不把別題的'
          '既有發現記成「動作前有、動作後沒有」、真的被動作解決的既有 blocker 記成 gone 並請使用者確認: pass')


def test_empty_bib_not_leaked(tmp: Path) -> None:
    """規格 29：動作鏈跑完不得在暫存目錄留下 check_coverage 用的空 bib。"""
    root = copy_fixture(tmp, 'bib_leak')
    assert not (root / 'literature/references.bib').is_file(), '這個 fixture 有自己的 bib，驗不到暫存路徑'
    # 兩個資料夾分開：本行程建的檔不能落在「數子行程留下幾個」的那一個，否則單跑時會假紅
    selfdir, subdir = tmp / 'bib_self', tmp / 'bib_sub'
    selfdir.mkdir()
    subdir.mkdir()
    saved = tempfile.tempdir
    tempfile.tempdir = str(selfdir)   # 驗牙時這一段每次都會建檔，落在自己的資料夾才不會留在系統暫存目錄
    try:
        first = C.empty_bib(root)
        assert first.name.startswith('empty-') and first.suffix == '.bib' and first.is_file(), first
        assert C.empty_bib(root) == first and len(C._EMPTY_BIB) == 1, \
            f'同一個 process 要共用同一個暫存空檔，現在有 {len(C._EMPTY_BIB)} 個'
    finally:
        tempfile.tempdir = saved
    script, args = ACTIONS['nest_result']
    rc, out = run_action(script, root, *args, env_extra={'TMPDIR': str(subdir)})
    assert rc == 0, out[-1500:]
    left = sorted(p.name for p in subdir.glob('empty-*.bib'))
    assert not left, f'動作鏈在暫存目錄留下 {len(left)} 個空 bib: {left[:5]}'
    shutil.rmtree(root)
    print('[regression] 規格 29：一個 process 共用一個暫存空 bib，動作鏈跑完暫存目錄裡 0 個 empty-*.bib: pass')


def test_placeholder_plan_node(tmp: Path) -> None:
    """規格 30：validation item 的 plan_id 指到不存在的 plan 時，整頁仍要畫得出來。"""
    root = copy_fixture(tmp, 'ghost_plan')
    path = root / 'analysis/validation.yaml'
    path.write_text(path.read_text(encoding='utf-8').rstrip('\n')
                    + '\n  - id: V9\n    sq: SQ1\n    plan_id: SQ1-v9\n    status: qualified\n'
                      '    primary_results: ["k1"]\n', encoding='utf-8')
    proc = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'render_progress.py'), str(root),
                           '--dry-run', '--json'], capture_output=True, text=True, encoding='utf-8',
                          env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), cwd='/tmp')
    text = (proc.stdout or '') + (proc.stderr or '')
    assert proc.returncode == 0 and 'IR 驗證失敗' not in text, text[-1200:]
    ir = json.loads(proc.stdout[proc.stdout.index('{'):])
    node = next(n for n in ir['graph']['nodes'] if n['id'] == 'p:SQ1-v9')
    assert node['type'] == 'method' and node['subtype'] == 'primary', node
    assert node['state'] == 'unknown' and node['band'] in ('main', 'ext'), node
    hit = [ln for ln in text.splitlines() if ln.startswith('WARNING') and 'items[V9]' in ln]
    assert len(hit) == 1 and 'SQ1-v9' in hit[0], text[-1200:]
    shutil.rmtree(root)
    print('[regression] 規格 30：指到不存在 plan 的 validation item 只讓佔位節點多一筆 WARNING，'
          'IR 驗證照過、頁面畫得出來: pass')


def _ws_inputs_fixture(tmp: Path, name: str) -> Path:
    """補上三種在 dry-run 工作區裡會變成「檔案層級 symlink」的輸入。

    根目錄下的環境鎖定檔、`analysis/data-manifest.yaml`、根目錄下被宣告為 inputs 的檔。`data/`、
    `protocol/` 這些是目錄層級的連結，底下的檔本身不是 symlink，碰不到這條判斷。
    """
    root = copy_fixture(tmp, name)
    (root / 'requirements.txt').write_text('pyyaml==6.0\n', encoding='utf-8')
    (root / 'analysis/data-manifest.yaml').write_text('files:\n  - path: table.csv\n', encoding='utf-8')
    (root / 'table.csv').write_text('a,b\n1,2\n', encoding='utf-8')
    (root / 'analysis/scripts').mkdir(parents=True, exist_ok=True)
    (root / 'analysis/scripts/run-order.txt').write_text('step.py  # inputs=table.csv\n', encoding='utf-8')
    return root


def test_workspace_link_fingerprint(tmp: Path) -> None:
    """規格 31：工作區替原檔擺的連結視同原檔；沒有標記檔的根，絕對 symlink 照舊跳過。"""
    root = _ws_inputs_fixture(tmp, 'ws_fp')
    ws = C.make_workspace(root)
    try:
        for rel in ('requirements.txt', 'analysis/data-manifest.yaml', 'table.csv'):
            assert (ws / rel).is_symlink(), f'{rel} 在工作區裡不是檔案層級 symlink，這個測試驗不到東西'
        assert C.fingerprint_only(ws) == C.fingerprint_only(root), 'dry-run 工作區的指紋與原根不同'
    finally:
        C.remove_workspace(ws)
    plain = _ws_inputs_fixture(tmp, 'ws_plain')
    assert not (plain / C.WORKSPACE_ORIGIN).exists()
    before = C.fingerprint_only(plain)
    outside = tmp / 'ws_outside'
    outside.mkdir()
    (outside / 'renv.lock').write_text('{}\n', encoding='utf-8')
    os.symlink(outside / 'renv.lock', plain / 'renv.lock')   # 絕對、尾段剛好等於相對路徑
    assert C.fingerprint_only(plain) == before, '沒有工作區標記檔的根，專案自己的絕對 symlink 仍要跳過'
    shutil.rmtree(root)
    shutil.rmtree(plain)
    print('[regression] 規格 31：三種檔案層級 symlink 的輸入在工作區裡算進指紋（工作區＝原根），'
          '沒有標記檔的根照舊跳過 symlink: pass')


# ======================================================================
# 規格 32～38：動作前就過期／落後／漂移的東西不得被動作吃掉
# ======================================================================

STALE_RES = 'a' * 20      # 刻意用假值：只要與現值不同就成立，不必是真指紋
STALE_SRC = 'b' * 20
DRIFT = ('c' * 20, 'd' * 20, 'e' * 20)
SVAL = ('a' * 19 + 'e', 'b' * 19 + 'e')
LAG_PID = 'SQ2-v0'        # V2 真正驗過的舊版；active 是 SQ2-v1
WAIVER_ID = 'D-' + '900'  # 單元斷言用的樣本編號（不寫進任何檔）


def _top_fp(root: Path) -> dict[str, str]:
    doc = yaml.safe_load((root / 'analysis/validation.yaml').read_text(encoding='utf-8'))
    return {k: str(doc.get(k) or '') for k in ('results_fingerprint', 'source_fingerprint')}


def _state_analysis(root: Path) -> dict[str, dict]:
    doc = yaml.safe_load((root / 'project.yaml').read_text(encoding='utf-8'))
    a = ((doc.get('state') or {}).get('analysis') or {})
    return {'rerun': dict(a.get('rerun') or {}), 'validation': dict(a.get('validation') or {})}


def _items_of(root: Path) -> dict[str, dict]:
    doc = yaml.safe_load((root / 'analysis/validation.yaml').read_text(encoding='utf-8'))
    return {str(i['id']): {'sq': str(i.get('sq')), 'plan_id': str(i.get('plan_id')),
                           'marks': sorted(k for k in i if str(k).startswith('reaffirmed_'))}
            for i in (doc.get('items') or [])}


def _add_lagging_item(root: Path, vid: str = 'V2', sq: str = 'SQ2', active: str = 'SQ2-v1',
                      old_pid: str = LAG_PID, with_plan: bool = True) -> None:
    """照實際形狀造落後 item：舊版 plan 檔與 index 條目都在（superseded），active 是新版，item 指舊版。

    `with_plan=False`：item 指到 index 根本沒有的 plan（render 會建佔位節點那種形狀）。
    """
    v_path = root / 'analysis/validation.yaml'
    text = v_path.read_text(encoding='utf-8')
    assert f'    plan_id: {active}\n' in text, text[:400]
    v_path.write_text(text.replace(f'    plan_id: {active}\n', f'    plan_id: {old_pid}\n', 1), encoding='utf-8')
    plans = root / 'analysis/plans'
    index = C.plan_common.load_index(root)
    if with_plan:
        doc = C.plan_common.load_yaml(plans / f'{active}.yaml')
        doc['plan_id'] = old_pid
        doc.pop('content_hash', None)
        doc['content_hash'] = C.plan_common.content_hash(doc)
        C.plan_common.dump_yaml(plans / f'{old_pid}.yaml', doc)
        index.setdefault('plans', []).append(
            {'plan_id': old_pid, 'path': f'analysis/plans/{old_pid}.yaml', 'sq': sq, 'status': 'superseded',
             'replaced_by': active, 'content_hash': doc['content_hash'], 'confirmed_at': '2099-01-01'})
        C.plan_common.save_index(root, index)


def _stale_fixture(tmp: Path, name: str, results: bool = True, source: bool = True,
                   drift: bool = True, lagging: bool = True) -> Path:
    """乾淨 fixture ＋「動作前就過期／漂移／落後」。每一項可單獨關掉，用來測彼此獨立。"""
    root = copy_fixture(tmp, name)
    if lagging:
        _add_lagging_item(root)      # 先造落後 item：它會新增 plan 檔與 index 條目，source fingerprint 跟著變
    # analysis/validation.yaml 本身不進 source fingerprint（改它頂層兩欄，fingerprint_only 的三個值都不變），
    # 所以這裡寫什麼都不會反過來影響現值；要「不過期」就寫現值、要「過期」才寫假值。
    now = C.fingerprint_only(root)
    v_path = root / 'analysis/validation.yaml'
    text = v_path.read_text(encoding='utf-8')
    text = re.sub(r'^results_fingerprint: \S+',
                  'results_fingerprint: ' + (STALE_RES if results else now['results_fingerprint']),
                  text, count=1, flags=re.M)
    text = re.sub(r'^source_fingerprint: \S+',
                  'source_fingerprint: ' + (STALE_SRC if source else now['fingerprint']),
                  text, count=1, flags=re.M)
    v_path.write_text(text, encoding='utf-8')
    # project.yaml 的三組記錄值一律重寫：要「不漂移／不過期」就寫現值，要「漂移／過期」才寫假值
    p_path = root / 'project.yaml'
    text = p_path.read_text(encoding='utf-8')
    doc = yaml.safe_load(text)['state']['analysis']
    rerun, sval = doc['rerun'], doc['validation']
    want = dict(zip(('fingerprint', 'input_fingerprint', 'results_fingerprint'), DRIFT)) if drift else now
    # 兩個區塊分開改：rerun 與 validation 的 results_fingerprint 原值相同，整份 replace 會改到錯的那一個
    head, mark, tail = text.partition('\n    validation:')
    assert mark and head.count('\n    rerun:') == 1, text[:600]
    for key in ('fingerprint', 'input_fingerprint', 'results_fingerprint'):
        head = head.replace(f'      {key}: {rerun[key]}\n', f'      {key}: {want[key]}\n', 1)
    # state.analysis.validation 的兩欄照 validation.yaml 頂層的狀態走（獨立比對，所以過期時各給一個別的假值）
    tail = tail.replace(f'      results_fingerprint: {sval["results_fingerprint"]}\n',
                        f'      results_fingerprint: {SVAL[0] if results else now["results_fingerprint"]}\n', 1)
    tail = tail.replace(f'      source_fingerprint: {sval["source_fingerprint"]}\n',
                        f'      source_fingerprint: {SVAL[1] if source else now["fingerprint"]}\n', 1)
    p_path.write_text(head + mark + tail, encoding='utf-8')
    return root


def _new_header_lines(root: Path) -> list[str]:
    """本次動作插進 validation.yaml 的那幾行註解（檔裡其他註解是 fixture 的歷史，不算）。"""
    text = (root / 'analysis/validation.yaml').read_text(encoding='utf-8')
    out, taking = [], False
    for line in text.split('\n'):
        if line.startswith(f'# {DATE} '):
            taking = True
        elif not line.startswith('#   '):
            taking = False
        if taking:
            out.append(line)
    return out


def test_stale_not_absorbed(tmp: Path, actions: tuple[str, ...] = ()) -> None:
    """規格 32：兩欄都過期＋rerun 漂移＋有落後 item 時，八個動作一個都不准把既有問題吃掉。

    `actions`：只跑指定的動作（驗牙用——同一組斷言，不必每個注入都跑完八個動作）。
    """
    base = _stale_fixture(tmp, 'stale_base')
    base_fp, base_state = _top_fp(base), _state_analysis(base)
    base_lines = [ln for ln in C.gate_findings(*C.run_script('check_validation', base))]
    assert any('已過期' in x for x in base_lines) and any('上游已過期' in x for x in base_lines), base_lines
    assert any(LAG_PID in x for x in base_lines), base_lines
    chain = [a for a in ACTIONS if a not in ('set_tier', 'set_figure_role', 'package_edit')]
    assert len(chain) == 8, chain
    chain = [a for a in chain if a in actions] if actions else chain
    said_lagging: set[str] = set()
    for action in chain:
        script, args = ACTIONS[action]
        work = tmp / f'stale__{action}'
        shutil.copytree(base, work)
        rc, out = run_action(script, work, *args)
        assert rc == 0, f'{action} 被動作前就有的過期／落後擋下 rc={rc}\n{out[-2500:]}'
        # (a) 頂層兩欄、state.analysis.validation、state.analysis.rerun 逐字未變
        assert _top_fp(work) == base_fp, f'{action}：頂層指紋被帶到新值\n{_top_fp(work)}'
        now_state = _state_analysis(work)
        assert now_state == base_state, f'{action}：state.analysis 被改到\n{C.leaf_diff(base_state, now_state)}'
        # (b) 沒有本次日期的 reaffirmed 標記
        items = _items_of(work)
        marks = sorted({m for it in items.values() for m in it['marks']})
        assert all(DATE.replace('-', '_') not in m for m in marks), f'{action}：多出本次的 reaffirmed 標記 {marks}'
        # (c) 落後 item 的 plan_id 沒動
        assert items['V2']['plan_id'] == LAG_PID, f'{action}：落後 item 被改掛成 {items["V2"]["plan_id"]}'
        # (d) waiver 沒重登
        assert '未重登' in out, f'{action}：摘要沒說 waiver 未重登\n{out[-1200:]}'
        assert not list((work / 'reviews').glob(f'rerun-waiver-{DATE}*')), f'{action}：漂移時仍寫了本次的 waiver 報告'
        # (f) 決策與本次插進檔頭的註解都不得宣稱重接
        did = re.search(r'決策 (D-\d+)', out).group(1)
        entry = next(d for d in yaml.safe_load((work / 'decisions.yaml').read_text(encoding='utf-8'))['decisions']
                     if d['id'] == did)
        blob = '\n'.join(str(entry.get(f) or '') for f in C.DECISION_FIELDS)
        assert not re.search(r'(?<!未)重接', blob), f'{action}：決策宣稱重接\n{blob[:1200]}'
        head = '\n'.join(_new_header_lines(work))
        assert head, f'{action}：找不到本次插進 validation.yaml 的註解'
        assert not re.search(r'(?<!未)重接', head), f'{action}：檔頭宣稱重接\n{head}'
        # (g) 動作前就過期／落後／漂移都要印成 WARNING，不能靜默吃掉
        assert 'WARNING analysis/validation.yaml 頂層指紋動作前就不是現值' in out, \
            f'{action}：頂層指紋動作前就過期沒有印 WARNING\n{out[-1800:]}'
        assert f'WARNING validation item V2 {C.LAGGING_REASON}' in out, \
            f'{action}：落後 item 沒有印 WARNING\n{out[-1800:]}'
        assert 'WARNING state.analysis.rerun 的 ' in out and '本次不重登 waiver' in out, \
            f'{action}：rerun 漂移沒有印 WARNING\n{out[-1800:]}'
        # (h) 兩欄都沒帶新值時不加標記，決策要照實寫（不得寫成「各 item 加 reaffirmed_…」）
        assert '不加 reaffirmed 標記' in blob, f'{action}：決策沒說不加標記\n{blob[:1200]}'
        # (i) waiver 的整句與短句都不得宣稱重登
        assert '於新 fingerprint 重登' not in head + blob, \
            f'{action}：宣稱 rerun waiver 於新 fingerprint 重登\n{head}\n{blob[:900]}'
        assert 'waiver 重登' not in head, f'{action}：檔頭宣稱 waiver 重登\n{head}'
        # (j) 新 plan 的 amendment_reason 會算進 content_hash，同樣不得宣稱重接
        for name, amend in _plan_amendments(work).items():
            assert not re.search(r'(?<!未)重接', amend), f'{action}／{name} 的 amendment_reason 宣稱重接\n{amend}'
        # 「<記錄值> → <新值>」這種寫法等於宣稱那一欄移動過；沒帶新值時三處都不准出現
        for stale_v, where, text in ((STALE_RES, '決策', blob), (STALE_SRC, '決策', blob),
                                     (STALE_RES, '檔頭', head), (STALE_SRC, '檔頭', head),
                                     (STALE_RES, 'stdout', out), (STALE_SRC, 'stdout', out)):
            assert f'{stale_v} → ' not in text, \
                f'{action}：{where}宣稱過期的指紋移動到新值（{stale_v} → …）\n{text[:1200]}'
        # 檔頭提到落後 item 時，一定要說它為什麼只改 sq（沒提到＝這個動作的 item_map 根本不含它）
        if 'V2' in head:
            assert C.LAGGING_REASON in head, f'{action}：檔頭提到落後 item 卻沒說它只改 sq\n{head}'
            said_lagging.add(action)
        # 動作後過期與落後仍報得出來，而且算既有（本次新增 0 筆、動作前有動作後沒有 0 筆）
        after = C.gate_findings(*C.run_script('check_validation', work))
        assert any('已過期' in x for x in after) and any(LAG_PID in x for x in after), after
        assert '動作前有、動作後沒有' not in out, f'{action}：既有問題被記成「動作後沒有」\n{out[-1500:]}'
        assert '既有項目 #1' in out, out[-1200:]
        shutil.rmtree(work)
    assert 'reassign_question' in said_lagging, \
        f'沒有任何動作把落後 item 的處理寫進檔頭（{sorted(said_lagging)}）——那句實話沒被走到'
    if actions:
        shutil.rmtree(base)
        print(f'[regression] 規格 32（{"／".join(chain)}）: pass')
        return
    # 對照：同一組動作在未過期的 fixture 上照舊帶新值、照舊加標記
    clean = copy_fixture(tmp, 'stale_control')
    rc, out = run_action('reassign_question.py', clean, '--from', 'SQ2')
    assert rc == 0, out[-1500:]
    assert _top_fp(clean) != {'results_fingerprint': STALE_RES, 'source_fingerprint': STALE_SRC}
    marks = sorted({m for it in _items_of(clean).values() for m in it['marks']})
    assert any(DATE.replace('-', '_') in m for m in marks), f'未過期的 fixture 也沒加標記 {marks}'
    shutil.rmtree(clean)
    shutil.rmtree(base)
    print(f'[regression] 規格 32：兩欄過期＋漂移＋落後 item 時 {len(chain)} 個動作 rc=0，'
          '頂層指紋／state.analysis／落後 item 的 plan_id 逐字未變、沒有新標記、waiver 未重登、'
          '決策與檔頭不宣稱重接、既有問題動作後仍報得出來且算既有: pass')


def test_one_column_stale(tmp: Path) -> None:
    """規格 33：只有一欄過期時，另一欄照舊帶到新值——不能「任一過期就兩欄都不動」。"""
    for which in ('source', 'results'):
        root = _stale_fixture(tmp, f'one_{which}', results=(which == 'results'), source=(which == 'source'),
                              drift=False, lagging=False)
        held = f'{which}_fingerprint'
        carried = 'results_fingerprint' if which == 'source' else 'source_fingerprint'
        before = _top_fp(root)
        rc, out = run_action('reassign_question.py', root, '--from', 'SQ2')
        assert rc == 0, f'只有 {which} 過期時被擋下 rc={rc}\n{out[-2500:]}'
        now = _top_fp(root)
        assert now[held] == before[held], f'{held} {C.STALE_FP_REASON}，不該被帶到新值：{now[held]}'
        assert now[carried] != before[carried], f'{carried} 動作前相符，應該帶到新值（現為 {now[carried]}）'
        assert '本次新增' not in out, f'只有一欄過期不該有本次新增\n{out[-1500:]}'
        # 帶過去的那一欄不得再是過期的：否則動作自己的 retag 會變成本次新增的 blocker
        after = C.gate_findings(*C.run_script('check_validation', root))
        stale_now = {'results': [x for x in after if x.startswith('BLOCKER validation 已過期')],
                     'source': [x for x in after if x.startswith('BLOCKER validation 上游已過期')]}
        kept_col = 'results' if which == 'source' else 'source'
        assert not stale_now[kept_col], f'{carried} 帶了新值卻仍過期\n{stale_now[kept_col]}'
        assert stale_now[which], f'{held} 本來就過期，動作後該照舊報\n{after}'
        shutil.rmtree(root)
    print('[regression] 規格 33：只有 source 過期時 results 照舊帶新值、只有 results 過期時 source 照舊帶新值，'
          '兩種都 rc=0 且沒有本次新增: pass')


def test_stale_and_drift_independent(tmp: Path) -> None:
    """規格 34：validation 過期與 rerun waiver 漂移彼此獨立，不得互相綁住。"""
    # 只過期不漂移：waiver 照舊重登，但 state.analysis.validation 不動
    root = _stale_fixture(tmp, 'stale_nodrift', drift=False, lagging=False)
    before = _state_analysis(root)
    rc, out = run_action('reassign_question.py', root, '--from', 'SQ2')
    assert rc == 0, out[-2000:]
    after = _state_analysis(root)
    assert after['rerun']['fingerprint'] != before['rerun']['fingerprint'], '沒漂移就該重登 waiver'
    assert after['validation'] == before['validation'], \
        f'state.analysis.validation 動作前就過期，不該被帶新值\n{after["validation"]}'
    steps = _run_log_text(root, out)
    assert 'state.analysis.validation 的 ' in steps and '不帶新值、at 不改' in steps, \
        f'步驟紀錄沒說 state.analysis.validation 沒帶新值\n{steps}'
    assert 'state.analysis.validation fingerprint 改新值' not in steps, \
        f'步驟紀錄宣稱 state.analysis.validation 改了新值\n{steps}'
    shutil.rmtree(root)
    # 只漂移不過期：waiver 不重登，但頂層指紋照舊帶到新值
    root = _stale_fixture(tmp, 'drift_nostale', results=False, source=False, lagging=False)
    before, before_state = _top_fp(root), _state_analysis(root)
    rc, out = run_action('reassign_question.py', root, '--from', 'SQ2')
    assert rc == 0, out[-2000:]
    assert _top_fp(root) != before, '沒過期就該把頂層指紋帶到新值'
    assert _state_analysis(root)['rerun'] == before_state['rerun'], \
        f'rerun 動作前就漂移，不該重登\n{_state_analysis(root)["rerun"]}'
    assert '未重登' in out, out[-1200:]
    # 兩欄都帶了新值、會寫 reaffirmed 標記，標記的 note 裡那句短句也不得宣稱 waiver 重登
    v_text = (root / 'analysis/validation.yaml').read_text(encoding='utf-8')
    assert 'waiver 未重登（' in v_text, f'validation.yaml 的 note 沒說 waiver 未重登\n{v_text[:1500]}'
    assert 'waiver 重登' not in v_text, f'validation.yaml 的 note 宣稱 waiver 重登\n{v_text[:1500]}'
    shutil.rmtree(root)
    print('[regression] 規格 34：只過期不漂移 → waiver 照舊重登、state.analysis.validation 不動；'
          '只漂移不過期 → 頂層指紋照舊帶新值、waiver 不重登: pass')


def _shadow_with(tmp: Path, name: str, rel: str, old: str, new: str) -> Path:
    """影子 plugin 複本，把 `rel` 裡的 `old` 換成 `new`（驗牙用）。"""
    shadow = shadow_plugin(tmp / name)
    text = (PLUGIN / rel).read_text(encoding='utf-8')
    assert text.count(old) == 1, f'{rel} 裡的原文出現 {text.count(old)} 次'
    (shadow / rel).write_text(text.replace(old, new, 1), encoding='utf-8')
    return shadow


def test_new_stale_still_blocks(tmp: Path) -> None:
    """規格 35：未過期的專案如果被本次動作寫出錯的指紋，那是本次新增 → 中止並還原。

    放寬「動作前就過期的欄位不帶新值」不等於放行「本次自己把它寫錯」。
    """
    root = copy_fixture(tmp, 'new_stale')
    before = bytes_of(root)
    shadow = _shadow_with(tmp, 'shadow_fp', AC_REL,
                          "        lines[ri2] = TF.replace_value(lines[ri2], fps['results'])",
                          "        lines[ri2] = TF.replace_value(lines[ri2], 'f' * 19 + 'e')")
    rc, out = run_action('reassign_question.py', root, '--from', 'SQ2', plugin=shadow)
    assert rc != 0, f'寫錯指紋卻完成了\n{out[-2000:]}'
    assert '已還原' in out, out[-1500:]
    assert bytes_of(root) == before, '中止後沒有完整還原'
    shutil.rmtree(shadow)
    shutil.rmtree(root)
    print('[regression] 規格 35：本次動作把頂層指紋寫成別的值 → 中止、逐位元還原: pass')


# 四種「不乾淨」→ 那筆 blocker 的關鍵字
DIRTY_PLAN = {'draft': '尚未 confirmed', 'no_hash': '缺 content_hash',
              'hash_mismatch': 'content_hash 不符', 'index_mismatch': 'index content_hash 與 plan 不一致'}


def _dirty_plan(root: Path, pid: str, kind: str) -> str:
    """把一份 plan 弄成四種「不乾淨」之一，回那筆 blocker 的關鍵字。"""
    path = root / f'analysis/plans/{pid}.yaml'
    text = path.read_text(encoding='utf-8')
    if kind == 'draft':
        path.write_text(text.replace('status: confirmed', 'status: draft', 1), encoding='utf-8')
    elif kind == 'no_hash':
        path.write_text(re.sub(r'^content_hash: .*\n', '', text, count=1, flags=re.M), encoding='utf-8')
    elif kind == 'hash_mismatch':
        path.write_text(re.sub(r'^(question: .*)$', r'\1（內容被改過）', text, count=1, flags=re.M), encoding='utf-8')
    elif kind == 'index_mismatch':
        index = root / 'analysis/plans/index.yaml'
        itext = index.read_text(encoding='utf-8')
        digest = re.search(rf'plan_id: {pid}\n(?:.*\n)*?  content_hash: (\S+)', itext).group(1)
        index.write_text(itext.replace(digest, 'f' * (len(digest) - 1) + 'e', 1), encoding='utf-8')
    return DIRTY_PLAN[kind]


def test_dirty_source_plan_blocked(tmp: Path) -> None:
    """規格 36：來源（與目標）plan 動作前就不乾淨時，不得從它封出新版——四種都要擋、都要還原。"""
    cases = [('reassign_question', 'SQ2-v1', '來源'), ('demote_plan', 'SQ1-v1', '目標')]
    for action, pid, role in cases:
        script, args = ACTIONS[action]
        for kind in DIRTY_PLAN:
            root = copy_fixture(tmp, f'dirty_plan__{action}_{kind}')
            want = _dirty_plan(root, pid, kind)
            before = bytes_of(root)
            for mode, run in (('dry-run', run_dry), ('apply', run_action)):
                rc, out = run(script, root, *args)
                assert rc != 0, f'{action}／{kind}／{mode}：plan 不乾淨卻完成了\n{out[-1500:]}'
                assert want in out, f'{action}／{kind}／{mode}：訊息沒說原因（要有「{want}」）\n{out[-1200:]}'
                assert role in out, f'{action}／{kind}／{mode}：訊息沒說是哪一份 plan\n{out[-1200:]}'
                assert '重新封版' in out, f'{action}／{kind}／{mode}：訊息沒說重新封版的後果\n{out[-1200:]}'
                assert bytes_of(root) == before, f'{action}／{kind}／{mode}：被擋下卻改到了檔'
            shutil.rmtree(root)
    print(f'[regression] 規格 36：{len(cases)} 個動作 × {len(DIRTY_PLAN)} 種不乾淨的 plan（未 confirmed／缺 hash／'
          'hash 不符／index 不一致）在 dry-run 與 apply 都中止、一個位元都沒改、訊息說明原因: pass')


def test_lagging_item_shapes(tmp: Path) -> None:
    """規格 37：落後 item 的兩種形狀——舊版 plan 還在、以及 plan 根本不存在。"""
    # 形狀一：舊版 plan 檔與 index 條目都在
    root = _stale_fixture(tmp, 'lag_withplan', results=False, source=False, drift=False)
    before = _items_of(root)
    assert before['V2']['plan_id'] == LAG_PID
    rc, out = run_action('reassign_question.py', root, '--from', 'SQ2')
    assert rc == 0, f'落後 item 讓動作被擋下 rc={rc}\n{out[-2500:]}'
    after = _items_of(root)
    assert after['V2']['plan_id'] == LAG_PID, f'落後 item 被改掛成 {after["V2"]["plan_id"]}'
    assert after['V2']['sq'] != before['V2']['sq'], 'sq 沒改會多出「sq 無效」'
    assert not after['V2']['marks'] or DATE.replace('-', '_') not in ''.join(after['V2']['marks']), \
        f'落後 item 加了標記 {after["V2"]["marks"]}'
    # 其他 item 動作前就對齊，照舊改掛且照舊加標記
    assert after['V1']['marks'] != before['V1']['marks'], '對齊的 item 應該照舊加標記'
    shutil.rmtree(root)
    # 形狀二：item 指到 index 根本沒有的 plan → 畫面畫得出來、動作不因重畫中止
    root = copy_fixture(tmp, 'lag_noplan')
    _add_lagging_item(root, with_plan=False)
    refix_fingerprints(root)
    proc = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'render_progress.py'), str(root), '--dry-run', '--json'],
                          capture_output=True, text=True, encoding='utf-8',
                          env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), cwd='/tmp')
    assert proc.returncode == 0, f'指到不存在的 plan 讓整頁畫不出來\n{proc.stdout[-900:]}{proc.stderr[-900:]}'
    rc, out = run_action('reassign_question.py', root, '--from', 'SQ2')
    assert rc == 0, f'指到不存在的 plan 讓動作中止 rc={rc}\n{out[-2500:]}'
    assert _items_of(root)['V2']['plan_id'] == LAG_PID, '指到不存在的 plan 也不該被改掛'
    shutil.rmtree(root)
    print('[regression] 規格 37：落後 item 的兩種形狀（舊版 plan 仍在／plan 不存在）都只改 sq、不改掛、不加標記，'
          '動作 rc=0 且頁面畫得出來: pass')


def test_decision_id_width(tmp: Path) -> None:
    """規格 38：決策編號不得寫死三位數——四位數的編號在各處都要認得。"""
    wide = 'D-' + '1000'          # 字面上不出現三位數以外的 D#（公開 repo 的字串防線會抓子字串）
    wider = 'D-' + '1001'
    assert re.fullmatch(r'D-\d{3,}', wide)
    import render_progress as RP
    assert RP.DECISION_ID_RE.fullmatch(wide), 'render 的決策編號比對仍寫死三位數'
    assert RP.DECISION_ID_RE.findall(f'見 {wide}') == [wide], RP.DECISION_ID_RE.findall(f'見 {wide}')
    root = copy_fixture(tmp, 'wide_did')
    d_path = root / 'decisions.yaml'
    text = d_path.read_text(encoding='utf-8')
    first = re.search(r'id: (D-\d+)', text).group(1)
    d_path.write_text(text.replace(f'id: {first}', f'id: {wide}', 1), encoding='utf-8')
    assert C.next_decision_id(root) == wider, f'四位數編號之後的下一號算錯：{C.next_decision_id(root)}'
    # waiver 參數與 check_decisions 都要放行四位數
    p_path = root / 'project.yaml'
    p_path.write_text(p_path.read_text(encoding='utf-8').replace(f'decision: {first}', f'decision: {wide}', 1),
                      encoding='utf-8')
    assert C.waiver_of(root, '') == wide, '--waiver-decision 仍只認三位數'
    rc, out = C.run_script('check_decisions', *C.decisions_argv(root))
    assert not [ln for ln in out.splitlines() if ln.startswith('WARNING') and 'id 格式' in ln], \
        f'check_decisions 把四位數編號當格式錯\n{out[-900:]}'
    shutil.rmtree(root)
    print(f'[regression] 規格 38：{len("1000")} 位數的決策編號在 next_decision_id／check_decisions／'
          'render 的比對／waiver 參數都放行: pass')


def test_verify_validation_strict() -> None:
    """規格 40：`verify_validation_generic` 要雙向驗——不該加的標記、不該帶的欄位、不該改掛的 plan_id。

    純文字層單元測試。`update_validation_generic` 本來就不會寫出這些，所以第二道驗證改壞了從動作看不出來；
    這裡直接餵一份「寫錯的結果」給它，它必須攔下來。
    """
    old = ('results_fingerprint: ' + 'a' * 20 + '\n'
           'source_fingerprint: ' + 'b' * 20 + '\n'
           'items:\n'
           '  - id: V6\n'
           '    sq: SQ6\n'
           '    plan_id: SQ6-v1\n'
           '    status: qualified\n')
    fps = {'results': 'c' * 20, 'source': 'd' * 20}
    key, item_map = 'reaffirmed_2099_01_01', {'V6': ('SQ7', 'SQ7-v1')}
    stale = C.StalePolicy({'results': False, 'source': False})
    lag = C.StalePolicy({'results': True, 'source': True}, {'V6'})
    mark_block = (f'    {key}:\n      results: {fps["results"]}\n      source: {fps["source"]}\n'
                  '    status: qualified\n')
    rehung = old.replace('    sq: SQ6\n', '    sq: SQ7\n').replace('    plan_id: SQ6-v1\n', '    plan_id: SQ7-v1\n')
    # 兩欄都不帶時的正解：sq／plan_id 改了、兩個指紋逐字不變、沒有標記
    C.verify_validation_generic(old, rehung, item_map, key, fps, stale)
    # 落後時的正解（頂層兩欄相符，所以指紋帶新值；落後的 item 不加標記、plan_id 不動）：只改 sq
    carried = (old.replace('a' * 20, fps['results']).replace('b' * 20, fps['source'])
               .replace('    sq: SQ6\n', '    sq: SQ7\n'))
    C.verify_validation_generic(old, carried, item_map, key, fps, lag)
    for name, text, policy, want in (
            ('多加了標記', rehung.replace('    status: qualified\n', mark_block), stale, '不該加'),
            ('帶了不該帶的 results', rehung.replace('a' * 20, fps['results']), stale, 'results_fingerprint'),
            ('帶了不該帶的 source', rehung.replace('b' * 20, fps['source']), stale, 'source_fingerprint'),
            ('落後 item 加了標記', carried.replace('    status: qualified\n', mark_block), lag, '不該加'),
            ('改掛了落後 item', carried.replace('    plan_id: SQ6-v1\n', '    plan_id: SQ7-v1\n'), lag, 'V6'),
            ('該帶的 results 沒帶', carried.replace(fps['results'], 'a' * 20, 1), lag, '未正確重接')):
        try:
            C.verify_validation_generic(old, text, item_map, key, fps, policy)
        except C.ChainError as exc:
            assert want in str(exc), f'{name}：攔下來了但理由不對——{exc}'
        else:
            raise AssertionError(f'{name}：verify_validation_generic 沒有攔下來')
    print('[regression] 規格 40：verify_validation_generic 攔下「多加標記／帶了不該帶的欄位／改掛落後 item／'
          '該加的標記沒加」四類寫錯，兩種正解都不誤判: pass')


def test_gate_baseline_shape(tmp: Path) -> None:
    """規格 39（尾巴）：中止訊息印原文、步驟紀錄的 gate_baseline 不含 plan_sq。"""
    rows = [C.Finding('BLOCKER x <FP> y', 'BLOCKER x 0123456789abcdef y'), 'BLOCKER 純字串']
    text = C.findings_text(rows)
    assert '0123456789abcdef' in text and '<FP>' not in text, text
    assert 'BLOCKER 純字串' in text, text
    root = _dirty_fixture(tmp, 'baseline_shape')
    rc, out = run_action('move_result.py', root, '--key', 'k2', '--to-plan', 'SQ2-v1')
    assert rc == 0, out[-1500:]
    log = json.loads((root / re.search(r'run log (\S+)', out).group(1)).read_text(encoding='utf-8'))
    assert log.get('gate_baseline'), '步驟紀錄沒有留 baseline'
    assert 'plan_sq' not in log['gate_baseline'], \
        f'gate_baseline 寫了 plan_sq（那不是跑出來的 baseline，只是 plan 的複本）：{sorted(log["gate_baseline"])}'
    assert 'plan' in log['gate_baseline'], sorted(log['gate_baseline'])
    assert any('<FP>' not in w and '<DATE>' not in w for w in log.get('warnings') or []), log.get('warnings')
    shutil.rmtree(root)
    print('[regression] 規格 39：關卡中止訊息與既有項目都印原文（不是 <FP>／<DATE>）、'
          'gate_baseline 不寫 plan_sq: pass')


# ======================================================================
# 規格 41～46：沒有 waiver、沒有 validation.yaml、沒有對應 item 時，文字要照實寫
# ======================================================================

BARE_REREG = re.compile(r'(?<![未不])重登')      # 前面不是「未」「不」的「重登」＝宣稱重登過


def _waiver_states() -> dict[str, object]:
    """三種 waiver 狀態的樣本：重登、漂移、無 waiver（兩種形狀）。"""
    return {'carry': C.WaiverState(WAIVER_ID, [], 'waived', True),
            'drift': C.WaiverState(WAIVER_ID, ['fingerprint'], 'waived', True),
            'none_absent': C.WaiverState('', [], '', False),
            'none_pass': C.WaiverState('', ['fingerprint'], 'pass', True)}


def test_waiver_text_units() -> None:
    """規格 41（單元）：waiver 三態的每個文字 helper——重登／漂移逐字沿用，無 waiver 不得宣稱重登。"""
    st = _waiver_states()
    assert st['carry'].state == 'carry' and st['drift'].state == 'drift'
    assert st['none_absent'].state == 'none' and st['none_pass'].state == 'none'
    assert st['carry'].carries and not st['drift'].carries and not st['none_pass'].carries
    # 重登：與放寬前逐字相同
    assert C.waiver_clause(st['carry']) == 'waiver 重登'
    assert C.waiver_sentence(st['carry']) == 'rerun waiver 於新 fingerprint 重登——仍是 waived，不是 pass'
    assert C.waiver_step_name(st['carry']) == 'rerun waiver 重登'
    assert C.waiver_phrase(st['carry'], 'OK') == 'OK'
    assert C.waiver_known_line(st['carry'], 'OK') == 'OK'
    assert C.waiver_decision_line(st['carry'], 'reviews/x.json') == 'reviews/x.json，仍是 waived、不是 pass'
    assert C.waiver_summary_text({'waiver': 'reviews/x.json'}) == 'reviews/x.json'
    # 漂移：維持原本的說法（有 waiver，只是本次沒重登）
    assert C.waiver_clause(st['drift']).startswith('waiver 未重登（')
    assert C.waiver_known_line(st['drift'], 'OK') == 'OK'
    assert C.waiver_decision_line(st['drift'], '') == '未重登'
    assert C.waiver_decision_line(st['drift'], '', drift_text='自己的話') == '自己的話'
    assert C.waiver_summary_text({'waiver': '', 'waiver_state': st['drift']}) == '未重登'
    # 有 waiver 的漂移 WARNING 逐字沿用（漂移就是不重登的理由，這一行不准改）
    assert C.stale_rerun_warn(st['drift']) == \
        'WARNING state.analysis.rerun 的 fingerprint 動作前就與現值不符：本次不重登 waiver'
    # 無 waiver：不得出現「仍 waived」或沒有前綴的「重登」，而且要說清楚沒有 waiver
    for key in ('none_absent', 'none_pass'):
        ws = st[key]
        texts = {'clause': C.waiver_clause(ws), 'sentence': C.waiver_sentence(ws),
                 'step': C.waiver_step_name(ws), 'phrase': C.waiver_phrase(ws, 'waiver 重登（仍是 waived）'),
                 'known': C.waiver_known_line(ws, f'rerun 仍 waived（{WAIVER_ID}），不是 pass'),
                 'decision': C.waiver_decision_line(ws, '', '；舊值推進', '未重登（動作前就漂移）'),
                 'summary': C.waiver_summary_text({'waiver': '', 'waiver_state': ws}),
                 'warn': C.stale_rerun_warn(ws)}
        for name, text in texts.items():
            assert '仍 waived' not in text, f'{key}／{name} 宣稱仍 waived：{text}'
            assert not BARE_REREG.search(text), f'{key}／{name} 宣稱重登：{text}'
            assert '動作前就漂移' not in text, f'{key}／{name} 把沒有 waiver 說成漂移：{text}'
            assert WAIVER_ID not in text, f'{key}／{name} 寫了不存在的 waiver 決策：{text}'
        for name in ('sentence', 'step', 'known', 'decision', 'summary', 'clause', 'warn'):
            assert C.NO_WAIVER_BRIEF in texts[name], f'{key}／{name} 沒說沒有 waiver：{texts[name]}'
        for name in ('sentence', 'known', 'decision'):
            assert C.NO_WAIVER_TAIL in texts[name], f'{key}／{name} 沒說 rerun 狀態要另行處理：{texts[name]}'
        assert '本次不重登 waiver' not in texts['warn'], \
            f'{key}／warn 寫成「本次不重登 waiver」（暗示有一個 waiver 在）：{texts["warn"]}'
    # 有 rerun 區塊時講它的 result；動作前就漂移另外講一句，但順序是「沒有 waiver」在前
    why = st['none_pass'].why_none()
    assert why.index(C.NO_WAIVER_BRIEF) < why.index('動作前就與現值不符'), why
    assert 'result: pass' in why, why
    nw = C.stale_rerun_warn(st['none_pass'])
    assert nw.index(C.NO_WAIVER_BRIEF) < nw.index(C.STALE_FP_REASON), nw
    assert 'result:' not in st['none_absent'].why_none(), st['none_absent'].why_none()
    # 檔案不存在：absent_or 換成實話，不得保留只在檔案存在時才成立的句子
    for text in (C.absent_or({'absent': True}, '頂層指紋動作前就與現值不符'),
                 C.absent_or({'absent': True}, 'x', C.VALIDATION_ABSENT_FP)):
        assert '頂層指紋' not in text and C.STALE_FP_REASON not in text, text
        assert 'analysis/validation.yaml 不存在' in text, text
    assert C.absent_or({'absent': False}, '原句') == '原句'
    assert C.absent_or({}, '原句') == '原句'
    # 沒有對應 item：要是完整句子，不是拼出來的「（無 item） 只把對應 item …」
    pol = C.StalePolicy()
    empty = C.rehang_clause(pol, [], '只把對應 item 的 sq／plan_id 改掛 AQ9／AQ9-v1', '只改 sq')
    assert empty == C.NO_ITEM_SENTENCE, empty
    assert '（無 item）' not in empty and '只把對應 item' not in empty, empty
    assert C.rehang_clause(pol, [], 'x', 'y', scope='來源') == '來源' + C.NO_ITEM_SENTENCE
    assert C.rehang_clause(pol, [], '改掛目標', 'y', '無 item') == '無 item 改掛目標'   # 接得通的照舊
    assert C.rehang_clause(pol, ['V1'], '改掛', 'y') == 'V1 改掛'
    print('[regression] 規格 41（單元）：waiver 三態 × 7 個文字 helper——重登／漂移逐字沿用、'
          '無 waiver 不宣稱重登也不說仍 waived、檔案不存在與無 item 都寫完整實話: pass')


def _drop_rerun_block(root: Path) -> None:
    """把 project.yaml 的 state.analysis.rerun 整段拿掉（＝這個專案從來沒有 waiver 決策）。"""
    path = root / 'project.yaml'
    lines = path.read_text(encoding='utf-8').split('\n')
    i = next(k for k, ln in enumerate(lines) if ln.startswith('    rerun:'))
    j = next(k for k in range(i + 1, len(lines)) if lines[k].strip() and not lines[k].startswith('      '))
    path.write_text('\n'.join(lines[:i] + lines[j:]), encoding='utf-8')
    refix_fingerprints(root)


def _fx_no_rerun(tmp: Path, name: str) -> Path:
    """(i) 沒有 state.analysis.rerun。"""
    root = copy_fixture(tmp, name)
    _drop_rerun_block(root)
    return root


def _fx_pass_drift(tmp: Path, name: str) -> Path:
    """(ii) state.analysis.rerun 是 result: pass、沒有 decision，而且指紋動作前就漂移。"""
    root = copy_fixture(tmp, name)
    path = root / 'project.yaml'
    text = path.read_text(encoding='utf-8').replace('result: waived', 'result: pass')
    text = re.sub(r'^      decision: D-\d+\n', '', text, count=1, flags=re.M)
    path.write_text(text, encoding='utf-8')
    refix_fingerprints(root)
    head, mark, tail = path.read_text(encoding='utf-8').partition('\n    validation:')
    assert mark, '找不到 state.analysis.validation'
    for key, val in zip(('fingerprint', 'input_fingerprint', 'results_fingerprint'), DRIFT):
        head = re.sub(rf'^      {key}: \S+$', f'      {key}: {val}', head, count=1, flags=re.M)
    path.write_text(head + mark + tail, encoding='utf-8')
    return root


def _fx_no_validation(tmp: Path, name: str) -> Path:
    """(iii) 沒有 analysis/validation.yaml，也沒有 state.analysis.rerun。"""
    root = copy_fixture(tmp, name)
    _drop_rerun_block(root)      # 要先接回指紋再刪檔：refix 會讀 validation.yaml
    (root / 'analysis/validation.yaml').unlink()
    return root


def _fx_no_item(tmp: Path, name: str) -> Path:
    """(iv) validation.yaml 在、但這個問題沒有對應的 item（也沒有 waiver）。"""
    root = _fx_no_rerun(tmp, name)
    path = root / 'analysis/validation.yaml'
    lines = path.read_text(encoding='utf-8').split('\n')
    i = next(k for k, ln in enumerate(lines) if ln.strip().startswith('- id: V2'))
    j = next((k for k in range(i + 1, len(lines)) if lines[k].lstrip().startswith('- id: ')), len(lines))
    path.write_text('\n'.join(lines[:i] + lines[j:]), encoding='utf-8')
    refix_fingerprints(root)
    return root


# 動作在某個 fixture 上跑不動的原因（寫明才算數，不是靜默略過）
WAIVER_SKIP: dict[str, str] = {}


def _plan_amendments(root: Path) -> dict[str, str]:
    """本次日期封出來的新 plan 的 amendment_reason（會算進 content_hash）。"""
    out = {}
    for path in sorted((root / 'analysis/plans').glob('*.yaml')):
        if path.name == 'index.yaml':
            continue
        doc = yaml.safe_load(path.read_text(encoding='utf-8'))
        if isinstance(doc, dict) and str(doc.get('created_at') or '') == DATE:
            out[path.name] = str(doc.get('amendment_reason') or '')
    return out


def _run_log_lines(root: Path, out: str) -> list[str]:
    """步驟紀錄裡所有會寫進 reviews/*.json 給人讀的文字：步驟標題、note，以及 `warnings` 陣列。

    `warnings` 原本沒收：`warn()` 印出來的句子會進 `self.log.doc['warnings']`，整個陣列都落在專案的
    `reviews/*.json` 裡，漏收等於任何 WARNING 的措辭都不在文字檢查範圍內（這是通用盲點，不只 waiver）。
    """
    m = re.search(r'run log (\S+)', out)
    if not m:
        return []
    doc = json.loads((root / m.group(1)).read_text(encoding='utf-8'))
    bits = []
    for step in doc.get('steps') or []:
        bits.append(str(step.get('name') or ''))
        bits += [str(n) for n in (step.get('notes') or [])]
    bits += [str(w) for w in (doc.get('warnings') or [])]
    return bits


def _run_log_text(root: Path, out: str) -> str:
    return '\n'.join(_run_log_lines(root, out))


def _run_log_names(root: Path, out: str) -> list[str]:
    """步驟紀錄的步驟標題（只標題，不含 note 與 warnings）。"""
    m = re.search(r'run log (\S+)', out)
    if not m:
        return []
    doc = json.loads((root / m.group(1)).read_text(encoding='utf-8'))
    return [str(s.get('name') or '') for s in (doc.get('steps') or [])]


def _summary_waiver_line(out: str) -> str:
    return next((ln for ln in out.splitlines() if 'rerun waiver：' in ln), '')


def _validation_note_lines(root: Path, did: str) -> str:
    """本次寫進 validation.yaml 的 reaffirmed 標記 note（短句版的 waiver 說法在裡面）。"""
    path = root / 'analysis/validation.yaml'
    if not path.is_file():
        return ''
    return '\n'.join(ln for ln in path.read_text(encoding='utf-8').split('\n') if did in ln)


# 一定會寫到 waiver 的地方：這幾處都要自己說清楚現況，不能只靠別處的 WARNING
WAIVER_SOURCES = ('決策', 'known_consequences', 'stdout', '步驟紀錄')
# reorder_questions 的 reaffirmed note 本來就不提 waiver（它不改掛、也沒寫 waiver 短句），其餘七支有
NOTE_WAIVER_SKIP = ('reorder_questions',)
# reorder_questions 只調順序、不改掛任何 item，所以沒有「沒有對應 item」這句話可寫
NO_REHANG_ACTIONS = ('reorder_questions',)


def test_untrue_waiver_text(tmp: Path, only: tuple[str, ...] = ()) -> None:
    """規格 41：沒有 waiver、沒有 validation.yaml、沒有對應 item 時，寫進專案檔的文字要照實。

    `only`：只跑指定的「fixture/動作」（驗牙用）。
    """
    chain = [a for a in ACTIONS if a not in ('set_tier', 'set_figure_role', 'package_edit')]
    assert len(chain) == 8, chain
    three = ('reassign_question', 'reorder_questions', 'nest_result')
    # (iii) 另外加 promote_question：封出新版的兩支都會在 amendment_reason 寫一句 validation.yaml
    # 怎麼動（那句算進 content_hash），兩支都要測到檔案不存在那一支分支
    # (iv) no_item 只跑 reassign_question：fixture 裡只有它動的那個 item 可以拿掉而仍留下非空的 items 清單
    #（清單整個空掉會在 update_validation_generic 直接 ChainError，那是另一種情況）
    fx_actions = {'no_rerun': tuple(chain), 'pass_drift': three,
                  'no_validation': three + ('promote_question',), 'no_item': ('reassign_question',)}
    cases = [(f, a) for f, acts in fx_actions.items() for a in acts]
    builders = {'no_rerun': _fx_no_rerun, 'pass_drift': _fx_pass_drift,
                'no_validation': _fx_no_validation, 'no_item': _fx_no_item}
    if only:
        cases = [(f, a) for f, a in cases if f'{f}/{a}' in only]
        assert cases, only
    skipped, done = [], []
    for fx, action in cases:
        key = f'{fx}/{action}'
        if key in WAIVER_SKIP:
            skipped.append(f'{key}（{WAIVER_SKIP[key]}）')
            continue
        script, args = ACTIONS[action]
        root = builders[fx](tmp, f'waiver_{fx}__{action}')
        rerun_before = _state_analysis(root)['rerun']
        rc, out = run_action(script, root, *args)
        assert rc == 0, f'{key}：沒有 waiver／沒有 validation.yaml 讓動作中止 rc={rc}\n{out[-2500:]}'
        # 本動作不重登，也不碰 state.analysis.rerun（沒有這個區塊的就維持沒有）
        assert _state_analysis(root)['rerun'] == rerun_before, \
            f'{key}：state.analysis.rerun 被改到 {_state_analysis(root)["rerun"]}'
        assert not list((root / 'reviews').glob(f'rerun-waiver-{DATE}*')), f'{key}：沒有 waiver 卻寫了 waiver 報告'
        did = re.search(r'決策 (D-\d+)', out).group(1)
        entry = next(d for d in yaml.safe_load((root / 'decisions.yaml').read_text(encoding='utf-8'))['decisions']
                     if d['id'] == did)
        sources = {'決策': '\n'.join(str(entry.get(f) or '') for f in C.DECISION_FIELDS),
                   'known_consequences': str(entry.get('known_consequences') or ''),
                   'stdout': out, '步驟紀錄': _run_log_text(root, out)}
        if (root / 'analysis/validation.yaml').is_file():
            sources['檔頭'] = '\n'.join(_new_header_lines(root))
            assert sources['檔頭'], f'{key}：找不到本次插進 validation.yaml 的註解'
            note = _validation_note_lines(root, did)
            if note:
                sources['validation note'] = note
        for name, text in _plan_amendments(root).items():
            sources[f'新 plan {name}'] = text
        if action in ('reassign_question', 'promote_question'):
            assert any(k.startswith('新 plan ') for k in sources), f'{key}：找不到本次封出來的新 plan'
        positive = set(WAIVER_SOURCES)
        if 'validation note' in sources and action not in NOTE_WAIVER_SKIP:
            positive.add('validation note')
        for where, text in sources.items():
            assert '仍 waived' not in text, f'{key}／{where} 宣稱 rerun 仍 waived\n{text[:1200]}'
            assert not BARE_REREG.search(text), f'{key}／{where} 宣稱重登過\n{text[:1200]}'
            assert 'waiver 未重登' not in text, \
                f'{key}／{where} 寫成「waiver 未重登」（暗示有 waiver 只是沒重登）\n{text[:1200]}'
            if where in positive:
                assert C.NO_WAIVER_BRIEF in text, f'{key}／{where} 沒有說明這個專案沒有 waiver\n{text[:1200]}'
        # stdout 的摘要行自己也要說清楚，不能只靠 WARNING 那一行
        assert C.NO_WAIVER_BRIEF in _summary_waiver_line(out), \
            f'{key}：stdout 的 rerun waiver 摘要行沒說沒有 waiver\n{_summary_waiver_line(out)}'
        if fx == 'pass_drift':
            # 講 state.analysis.rerun 漂移的那幾行（stdout 與步驟紀錄的 warnings 都會被人讀到）：
            # 沒有 waiver 時「沒有 waiver」要在同一行、而且在漂移之前——漂移是附帶的現況，不是不重登的理由
            drift_lines = [ln for ln in out.split('\n') + _run_log_lines(root, out)
                           if C.STALE_FP_REASON in ln and 'state.analysis.rerun' in ln]
            assert drift_lines, f'{key}：沒有任何一行講 state.analysis.rerun 動作前就漂移\n{out[-1800:]}'
            for ln in drift_lines:
                assert C.NO_WAIVER_BRIEF in ln, f'{key}：講漂移卻沒在同一行說沒有 waiver\n{ln}'
                assert ln.index(C.NO_WAIVER_BRIEF) < ln.index(C.STALE_FP_REASON), \
                    f'{key}：漂移寫在「沒有 waiver」之前＝把漂移當成不重登的理由\n{ln}'
                assert '本次不重登 waiver' not in ln, \
                    f'{key}：寫成「本次不重登 waiver」（暗示有一個 waiver 只是沒重登）\n{ln}'
        if fx in ('no_validation', 'no_item'):
            for where, text in sources.items():
                assert '頂層指紋' not in text, f'{key}／{where} 描述了不存在的頂層指紋\n{text[:1200]}'
        if fx == 'no_validation':
            # stdout 也算：摘要的 fingerprint 欄照實寫「無 analysis/validation.yaml」，WARNING 不得
            # 退回「頂層指紋動作前就不是現值（…）：不符的欄位本次不帶新值，維持原記錄」那一句
            for where, text in sources.items():
                assert C.STALE_FP_REASON not in text, \
                    f'{key}／{where} 說指紋動作前就與現值不符，但這個專案沒有 validation.yaml\n{text[:1200]}'
                assert '不加 reaffirmed 標記' not in text, \
                    f'{key}／{where} 說各 item 不加標記，但這個專案沒有 item\n{text[:1200]}'
                assert not re.search(r'(?<!未)重接', text), \
                    f'{key}／{where} 宣稱重接了 validation 的 fingerprint\n{text[:1200]}'
            assert 'analysis/validation.yaml 不存在' in sources['決策'], sources['決策'][:1200]
            # 只有這兩支的 amendment_reason 本來就會寫一句 validation.yaml 怎麼動（會算進 content_hash）
            if action in ('reassign_question', 'promote_question'):
                for where, text in sources.items():
                    if where.startswith('新 plan '):
                        assert C.VALIDATION_ABSENT_TAIL in text, \
                            f'{key}／{where} 的 amendment_reason 沒說 validation.yaml 不存在\n{text[:1200]}'
        if fx == 'no_item':
            for where, text in sources.items():
                assert '（無 item）' not in text, f'{key}／{where} 拼出「（無 item） …」不成句\n{text[:1200]}'
            if action not in NO_REHANG_ACTIONS:
                assert C.NO_ITEM_SENTENCE in sources['決策'] + sources['檔頭'], \
                    f'{key}：沒有對應 item 卻沒寫成完整句子\n{sources["檔頭"][:900]}'
        if fx == 'no_rerun':
            # 寫入行為不變：沒有 waiver 不影響頂層指紋與 reaffirmed 標記
            items = _items_of(root)
            assert _top_fp(root)['source_fingerprint'] == C.fingerprint_only(root)['fingerprint'], \
                f'{key}：沒有 waiver 不該影響頂層指紋'
            if action not in ('reorder_questions',):
                assert any(DATE.replace('-', '_') in m for it in items.values() for m in it['marks']), \
                    f'{key}：沒有 waiver 不該影響 reaffirmed 標記'
        done.append(key)
        shutil.rmtree(root)
    if only:
        print(f'[regression] 規格 41（{"／".join(done)}）: pass')
        return
    assert len(done) == len(cases) - len(skipped), (len(done), len(cases), skipped)
    # 對照：正常路徑（有 waiver、沒漂移、檔案與 item 都在）的原句一字不改
    clean = copy_fixture(tmp, 'waiver_control')
    rc, out = run_action('reassign_question.py', clean, '--from', 'SQ2')
    assert rc == 0, out[-1500:]
    head = '\n'.join(_new_header_lines(clean))
    assert 'rerun waiver 於新 fingerprint 重登——仍是 waived，不是 pass' in head, head
    did = re.search(r'決策 (D-\d+)', out).group(1)
    entry = next(d for d in yaml.safe_load((clean / 'decisions.yaml').read_text(encoding='utf-8'))['decisions']
                 if d['id'] == did)
    assert '，仍是 waived、不是 pass；state.analysis.rerun 舊值推進 previous_waiver' in str(entry['decision']), entry['decision']
    assert 'rerun 仍 waived（' in str(entry['known_consequences']), entry['known_consequences']
    assert C.NO_WAIVER_BRIEF not in str(entry['decision']), entry['decision']
    shutil.rmtree(clean)
    print(f'[regression] 規格 41：{len(done)} 組（fixture × 動作）在沒有 waiver／沒有 validation.yaml／'
          f'沒有對應 item 時，決策、known_consequences、檔頭、stdout、步驟紀錄（含 warnings）與新 plan 的 '
          f'amendment_reason 都不宣稱重登或仍 waived、都說明了現況；漂移的 WARNING 先講沒有 waiver；'
          f'state.analysis.rerun 逐字未變；'
          f'正常路徑原句不變（略過 {len(skipped)} 組：{"；".join(skipped) or "無"}）: pass')


# 每個（動作，角色）至少一種不乾淨的狀態，四種輪流分配、全部都要出現
PLAN_ROLES: list[tuple[str, str, str, str]] = [
    ('reassign_question', 'SQ2-v1', '來源', 'draft'),
    ('promote_question', 'AQ1-v1', '來源', 'no_hash'),
    ('demote_plan', 'AQ1-v1', '來源', 'hash_mismatch'),
    ('demote_plan', 'SQ1-v1', '目標', 'index_mismatch'),
    ('move_plan', 'AQ1-v1', '來源', 'draft'),
    ('move_result', 'SQ1-v1', '來源', 'no_hash'),
    ('move_result', 'SQ2-v1', '目標', 'hash_mismatch'),
    ('move_sensitivity', 'SQ1-v1', '來源', 'index_mismatch'),
    ('move_sensitivity', 'SQ2-v1', '目標', 'draft'),
    ('nest_result', 'SQ1-v1', '來源', 'no_hash'),
]


def test_dirty_plan_wiring(tmp: Path) -> None:
    """規格 42：7 支會封版的動作 × 各自的角色都要接上來源 plan 檢查——少掛一處就不該是綠的。"""
    assert {r[3] for r in PLAN_ROLES} == set(DIRTY_PLAN), '四種不乾淨要全部出現'
    actions = {r[0] for r in PLAN_ROLES}
    assert actions == {'reassign_question', 'promote_question', 'demote_plan', 'move_plan',
                       'move_result', 'move_sensitivity', 'nest_result'}, sorted(actions)
    for action, pid, role, kind in PLAN_ROLES:
        script, args = ACTIONS[action]
        root = copy_fixture(tmp, f'wire__{action}_{role}_{kind}')
        assert (root / f'analysis/plans/{pid}.yaml').is_file(), pid
        want = _dirty_plan(root, pid, kind)
        before = bytes_of(root)
        for mode, run in (('dry-run', run_dry), ('apply', run_action)):
            rc, out = run(script, root, *args)
            assert rc != 0, f'{action}／{role}／{kind}／{mode}：plan 不乾淨卻完成了\n{out[-1500:]}'
            assert want in out, f'{action}／{role}／{kind}／{mode}：訊息沒說原因（要有「{want}」）\n{out[-1200:]}'
            assert f'{role} {pid}' in out, f'{action}／{role}／{kind}／{mode}：訊息沒說是哪一份 plan\n{out[-1200:]}'
            assert '重新封版' in out, f'{action}／{role}／{kind}／{mode}：訊息沒說重新封版的後果\n{out[-1200:]}'
            assert bytes_of(root) == before, f'{action}／{role}／{kind}／{mode}：被擋下卻改到了檔'
        shutil.rmtree(root)
    print(f'[regression] 規格 42：{len(PLAN_ROLES)} 組（動作，角色）在 dry-run 與 apply 都因來源／目標 plan '
          '不乾淨而中止、訊息說明原因與角色與重新封版的後果、一個位元都沒改: pass')


def _state_fp_fixture(tmp: Path, name: str, top_stale: bool) -> Path:
    """頂層與 state.analysis.validation 只有一邊過期：兩組狀態必須各自判斷。"""
    root = copy_fixture(tmp, name)
    refix_fingerprints(root)
    now = C.fingerprint_only(root)
    path = root / ('analysis/validation.yaml' if top_stale else 'project.yaml')
    if top_stale:
        text = path.read_text(encoding='utf-8')
        text = re.sub(r'^results_fingerprint: \S+', f'results_fingerprint: {STALE_RES}', text, count=1, flags=re.M)
        text = re.sub(r'^source_fingerprint: \S+', f'source_fingerprint: {STALE_SRC}', text, count=1, flags=re.M)
        path.write_text(text, encoding='utf-8')
    else:
        head, mark, tail = path.read_text(encoding='utf-8').partition('\n    validation:')
        assert mark, '找不到 state.analysis.validation'
        tail = re.sub(r'^      results_fingerprint: \S+', f'      results_fingerprint: {SVAL[0]}',
                      tail, count=1, flags=re.M)
        tail = re.sub(r'^      source_fingerprint: \S+', f'      source_fingerprint: {SVAL[1]}',
                      tail, count=1, flags=re.M)
        path.write_text(head + mark + tail, encoding='utf-8')
    assert now  # 指紋不受上面兩個檔影響（它們都不進 source fingerprint）
    return root


def test_state_policy_independent(tmp: Path) -> None:
    """規格 43：state.analysis.validation 與 validation.yaml 頂層各自判斷，不得照抄另一邊。"""
    # (a) 頂層相符、state 過期 → 頂層帶新值，state 不動
    root = _state_fp_fixture(tmp, 'state_only_stale', top_stale=False)
    top_before, state_before = _top_fp(root), _state_analysis(root)
    rc, out = run_action('reassign_question.py', root, '--from', 'SQ2')
    assert rc == 0, out[-2000:]
    assert _top_fp(root) != top_before, '頂層動作前相符，應該帶到新值'
    assert _state_analysis(root)['validation'] == state_before['validation'], \
        f'state.analysis.validation 動作前就過期，不該被帶新值\n{_state_analysis(root)["validation"]}'
    assert _state_analysis(root)['rerun'] != state_before['rerun'], '沒漂移就該重登 waiver'
    shutil.rmtree(root)
    # (b) 頂層過期、state 相符 → 頂層不動，state 照舊帶新值
    root = _state_fp_fixture(tmp, 'top_only_stale', top_stale=True)
    top_before, state_before = _top_fp(root), _state_analysis(root)
    rc, out = run_action('reassign_question.py', root, '--from', 'SQ2')
    assert rc == 0, out[-2000:]
    assert _top_fp(root) == top_before, f'頂層動作前就過期，不該被帶新值\n{_top_fp(root)}'
    now = _state_analysis(root)['validation']
    assert now != state_before['validation'], f'state.analysis.validation 動作前相符，應該帶到新值\n{now}'
    assert now['results_fingerprint'] != SVAL[0] and now['source_fingerprint'] != SVAL[1], now
    shutil.rmtree(root)
    print('[regression] 規格 43：頂層相符＋state 過期 → 只帶頂層；頂層過期＋state 相符 → 只帶 state: pass')


def test_drift_per_field(tmp: Path) -> None:
    """規格 44：rerun 的三個指紋欄位各自判斷漂移——只看 fingerprint 一欄會漏掉另外兩種。"""
    fields = ('fingerprint', 'input_fingerprint', 'results_fingerprint')
    for n, field in enumerate(fields):
        root = copy_fixture(tmp, f'drift_{field}')
        refix_fingerprints(root)
        path = root / 'project.yaml'
        head, mark, tail = path.read_text(encoding='utf-8').partition('\n    validation:')
        assert mark, '找不到 state.analysis.validation'
        head = re.sub(rf'^      {field}: \S+$', f'      {field}: {DRIFT[n]}', head, count=1, flags=re.M)
        path.write_text(head + mark + tail, encoding='utf-8')
        before = _state_analysis(root)['rerun']
        assert before[field] == DRIFT[n], before
        rc, out = run_action('reassign_question.py', root, '--from', 'SQ2')
        assert rc == 0, f'{field} 單獨漂移讓動作中止 rc={rc}\n{out[-2000:]}'
        assert _state_analysis(root)['rerun'] == before, \
            f'{field} 動作前就漂移，不該重登\n{_state_analysis(root)["rerun"]}'
        assert f'WARNING state.analysis.rerun 的 {field} ' in out, f'{field} 單獨漂移沒有 WARNING\n{out[-1500:]}'
        assert '未重登' in out, out[-1200:]
        assert not list((root / 'reviews').glob(f'rerun-waiver-{DATE}*')), f'{field} 漂移時仍寫了 waiver 報告'
        shutil.rmtree(root)
    print(f'[regression] 規格 44：{"／".join(fields)} 三欄各自單獨漂移時都不重登 waiver、都有 WARNING: pass')


FP_FAIL_ENV = 'SSOT_TEST_FP_FAIL_ONCE'
_FP_HEAD = "def fingerprint_only(root: Path) -> dict[str, str]:"
_FP_INJECT = _FP_HEAD + f"""
    import os as _os
    if _os.environ.get({FP_FAIL_ENV!r}) and not getattr(fingerprint_only, '_failed', False):
        fingerprint_only._failed = True
        raise ChainError('測試注入：量不到現值')"""


def test_fingerprint_unavailable(tmp: Path) -> None:
    """規格 45：動作前量不到現值時照常走完，但一欄都不帶、不加標記、不重登，而且要印 WARNING。"""
    shadow = _shadow_with(tmp, 'fp_unavail_plugin', 'skills/status/scripts/ssot_actions_common.py',
                          _FP_HEAD, _FP_INJECT)
    # 頂層兩欄本來就過期的 fixture：不帶新值不會變成「本次新增的 blocker」，整條鏈才走得完
    root = _stale_fixture(tmp, 'fp_unavail', drift=False, lagging=False)
    top_before, state_before = _top_fp(root), _state_analysis(root)
    marks_before = sorted({m for it in _items_of(root).values() for m in it['marks']})
    rc, out = run_action('reassign_question.py', root, '--from', 'SQ2', plugin=shadow,
                         env_extra={FP_FAIL_ENV: '1'})
    assert rc == 0, f'量不到現值時中止了（行為不該改成中止）rc={rc}\n{out[-2500:]}'
    assert 'WARNING 動作前量不到目前的 fingerprint' in out, f'沒有 WARNING\n{out[-1500:]}'
    assert _top_fp(root) == top_before, f'量不到現值卻帶了新值\n{_top_fp(root)}'
    assert _state_analysis(root) == state_before, f'量不到現值卻改了 state.analysis\n{_state_analysis(root)}'
    assert sorted({m for it in _items_of(root).values() for m in it['marks']}) == marks_before, '多了標記'
    assert not list((root / 'reviews').glob(f'rerun-waiver-{DATE}*')), '量不到現值卻重登了 waiver'
    log = json.loads((root / re.search(r'run log (\S+)', out).group(1)).read_text(encoding='utf-8'))
    assert (log.get('stale_baseline') or {}).get('fingerprint_unavailable') is True, log.get('stale_baseline')
    shutil.rmtree(root)
    shutil.rmtree(shadow)
    print('[regression] 規格 45：動作前量不到現值 → 動作照常完成（rc=0，不改成中止）、頂層與 '
          'state.analysis 逐字未變、沒有新標記、沒有重登 waiver、stdout 有 WARNING: pass')


def test_decision_id_regex_constants() -> None:
    """規格 46：四處比對決策編號的正規式抽成模組常數，且都認得長過三位的編號。"""
    wide = 'D-' + '1000'
    narrow = 'D-' + '12'
    mods = {rel: _load_script(rel) for rel in ('skills/analyze-data/scripts/check_manifest.py',
                                               'skills/status/scripts/check_decisions.py',
                                               'skills/status/scripts/run_batch.py',
                                               'skills/status/scripts/progress_server.py',
                                               'skills/status/scripts/render_progress.py')}
    for rel in ('skills/analyze-data/scripts/check_manifest.py', 'skills/status/scripts/check_decisions.py'):
        pat = mods[rel].DECISION_ID_RE
        assert pat.fullmatch(wide), f'{rel}: DECISION_ID_RE 認不出 {wide}'
        assert not pat.fullmatch(narrow), f'{rel}: DECISION_ID_RE 連兩位數都收'
    assert mods['skills/status/scripts/render_progress.py'].DECISION_ID_RE.fullmatch(wide)
    for rel in ('skills/status/scripts/run_batch.py', 'skills/status/scripts/progress_server.py'):
        m = mods[rel].DECISION_LINE_RE.search(f'結果: 完成；決策 {wide}；run log x.json')
        assert m and m.group(1) == wide, f'{rel}: DECISION_LINE_RE 抓到 {m and m.group(1)}'
    ps = mods['skills/status/scripts/progress_server.py']
    for text, want in ((f'結果: 完成；決策 {wide}', wide),
                       (f'結果: 完成；決策 {wide}–D-' + '1001', wide + '–D-' + '1001')):
        m = ps.DONE_DECISION_RE.search(text)
        assert m and m.group(1) == want, f'progress_server: DONE_DECISION_RE 抓到 {m and m.group(1)}（要 {want}）'
    print('[regression] 規格 46：check_manifest／check_decisions／run_batch／progress_server／render_progress '
          '的決策編號正規式都是模組常數，且都認得長過三位的編號: pass')


# ======================================================================
# 規格 47～51：沒有 analysis/results.json（尚無正式結果）的專案
# ======================================================================

# 尚無正式結果時不得出現的說法：指紋相關的句子、「量不到現值」那條路的用語、fps 佔位標記，
# 以及「retag N 鍵」這種暗示那個檔在的寫法。
NO_RESULTS_FORBID = ('頂層指紋', '量不到', '（量不到現值）')
BARE_RECONNECT = re.compile(r'(?<!未)重接')     # 前面不是「未」的「重接」＝宣稱重接過
RETAG_N_KEYS = re.compile(r'retag \d+ 鍵')      # 沒有這個檔時不得用鍵數暗示它在
# project-init 第 4 步的目錄樹（skills/project-init/SKILL.md）
INIT_DIRS = ('progress', 'progress/logs', 'backups', 'protocol', 'methodology', 'integrity', 'data',
             'analysis/scripts', 'analysis/plans', 'analysis/derived', 'analysis/figures',
             'analysis/validation', 'analysis/exploration', 'analysis/integration',
             'literature/notes', 'manuscript/zh', 'manuscript/en', 'reviews', 'evaluations', 'submission')
INIT_QIDS = ('SQ6', 'SQ7')
INIT_DID = 'D-' + '900'
# 三支要搬結果鍵的動作：沒有結果鍵可搬，前置條件就拒絕
MOVE_KEY_ACTIONS = ('move_result', 'move_sensitivity', 'nest_result')


def _strip_results(root: Path, validation: bool = False, keep_rerun: bool = False,
                   keep_links: bool = False) -> None:
    """把乾淨 fixture 改成「尚無正式結果」：拿掉 results.json，並按形狀決定留不留 validation.yaml／rerun 欄位。

    不能呼叫 `refix_fingerprints`——它要跑 `check_validation --source-fingerprint-only`，
    沒有 results.json 時那支算不出值。
    """
    (root / 'analysis/results.json').unlink()
    if not validation:
        (root / 'analysis/validation.yaml').unlink()
    path = root / 'project.yaml'
    lines = path.read_text(encoding='utf-8').split('\n')
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith('    rerun:') or ln.startswith('    validation:'):
            if keep_rerun and ln.startswith('    rerun:'):      # (c2)：留著只有跑過分析才會有的指紋與 waiver
                out.append(ln)
                i += 1
                continue
            out.append(ln.split(':')[0] + ': {}')
            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith('      ')):
                i += 1
            continue
        out.append(ln)
        i += 1
    text = '\n'.join(out)
    # study-design 階段該有的形狀：還沒有結果鍵可連、問題還沒答。
    # keep_links=True：結果都還沒有、goals 卻還掛著 results links（比上面那種髒），用來驗關卡的訊息
    if not keep_links:
        text = re.sub(r'^(\s+)links: \["results:[^\]]*\]([^\n]*)$', r'\1links: []\2', text, flags=re.M)
        text = text.replace('status: addressed', 'status: open')
    path.write_text(text, encoding='utf-8')


def _fx_no_results(tmp: Path, name: str, validation: bool = False, keep_rerun: bool = False,
                   keep_links: bool = False) -> Path:
    """(a) study-design 形狀：plan 都封版、沒有 results.json／validation.yaml、state.analysis 兩區都空。

    `validation=True`＝(c1)（沒有 results.json 卻留著 validation.yaml）；
    `keep_rerun=True`＝(c2)（state.analysis.rerun 留著指紋欄位與 waiver 決策）。
    """
    root = copy_fixture(tmp, name)
    _strip_results(root, validation, keep_rerun, keep_links)
    return root


def _fx_project_init(tmp: Path, name: str, snapshot: bool = True) -> Path:
    """(b) project-init 剛建好：只有目錄樹、模板 project.yaml、一筆收尾決策與 goals 快照。

    沒有 plans index、`analysis/plans/` 底下沒有檔；results.json／validation.yaml 都還沒有。
    `snapshot=False`＝連 goals 快照都還沒建（project-init 第 6 步沒跑完就停下的形狀）。
    """
    root = tmp / name
    if root.exists():
        shutil.rmtree(root)
    for d in INIT_DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    tpl = yaml.safe_load((PLUGIN / 'skills/project-init/references/project-template.yaml').read_text(encoding='utf-8'))
    tpl['project'].update({'title_zh': '新專案', 'title_en': 'fresh', 'research_question': '主問題一句',
                           'field': 'testing'})
    tpl['methodology'].update({'primary': 'quantitative-inference', 'confirmed': True,
                               'rationale': '模板', 'routed_at': DATE})
    tpl['goals']['sub_questions'] = [
        {'id': q, 'question': f'子問題{i + 1}', 'why': '角色', 'evidence': ['analysis'],
         'success_criteria': '準則', 'role': 'primary', 'status': 'open', 'status_reason': '', 'links': []}
        for i, q in enumerate(INIT_QIDS)]
    tpl['goals']['appendix_questions'] = []
    (root / 'project.yaml').write_text(
        '# 新專案（project-init 剛建好）\n' + _ydump(tpl), encoding='utf-8')
    (root / 'decisions.yaml').write_text(
        '# 決策日誌——append-only\ndecisions:\n'
        f'  - id: {INIT_DID}\n    date: {DATE}\n    stage: project-init\n'
        '    checkpoint: "階段收尾"\n    question: main\n    method: "研究設計"\n'
        '    decision: "建立專案結構與 goals"\n    reason: "新專案"\n    rejected: ""\n'
        '    known_consequences: ""\n    evidence: []\n    links: []\n    supersedes: ""\n', encoding='utf-8')
    (root / 'literature/references.bib').write_text('', encoding='utf-8')
    if snapshot:
        empty = root / '_empty_for_snapshot.json'    # project-init 第 6 步也建 goals 快照
        empty.write_text('{}\n', encoding='utf-8')
        subprocess.run([sys.executable, '-B', str(PLUGIN / 'skills/evaluate/scripts/check_coverage.py'),
                        str(root / 'project.yaml'), str(empty), str(root / 'literature/references.bib'),
                        '--snapshot', str(root / 'evaluations/goals-snapshot.json'), '--update-snapshot'],
                       capture_output=True, text=True)
        empty.unlink()
    assert not (root / 'analysis/plans/index.yaml').exists(), 'project-init 形狀不該有 plans index'
    assert not list((root / 'analysis/plans').glob('*')), 'project-init 形狀的 analysis/plans/ 要是空的'
    assert (root / 'evaluations/goals-snapshot.json').is_file() == snapshot, '快照建得不對'
    return root


def _no_results_sources(root: Path, out: str) -> dict[str, str]:
    """「尚無正式結果」時會被人讀到的每一處文字：決策、known_consequences、stdout、步驟紀錄、
    新 plan 的 amendment_reason，以及 validation.yaml 裡本次寫進去的行（檔案存在時）。"""
    sources = {'stdout': out, '步驟紀錄': '\n'.join(_run_log_lines(root, out))}
    did = re.search(r'決策 (D-\d+)', out)
    if did:
        entry = next(d for d in yaml.safe_load((root / 'decisions.yaml').read_text(encoding='utf-8'))['decisions']
                     if d['id'] == did.group(1))
        sources['決策'] = '\n'.join(str(entry.get(f) or '') for f in C.DECISION_FIELDS)
        sources['known_consequences'] = str(entry.get('known_consequences') or '')
    for name, text in _plan_amendments(root).items():
        sources[f'新 plan {name}'] = text
    if (root / 'analysis/validation.yaml').is_file():
        lines = [ln for ln in (root / 'analysis/validation.yaml').read_text(encoding='utf-8').split('\n')
                 if DATE in ln or DATE.replace('-', '_') in ln]
        if lines:
            sources['validation.yaml 本次寫入'] = '\n'.join(lines)
    return sources


# (a)(b) 不需要結果鍵、要照常完成的五支動作
NO_RESULTS_OK = ('reorder_questions', 'reassign_question', 'promote_question', 'move_plan', 'demote_plan')


def test_no_results_actions(tmp: Path, only: tuple[str, ...] = ()) -> None:
    """規格 47：沒有 analysis/results.json 時，不需要結果鍵的五支動作照常完成，紀錄照實寫「尚無正式結果」。

    `only`：只跑指定的「fixture/動作」（驗牙用）。
    """
    cases = [('a', a) for a in NO_RESULTS_OK] + [('b', 'reorder_questions'),
                                                 ('c1', 'reassign_question'), ('c2', 'reassign_question')]
    if only:
        cases = [(f, a) for f, a in cases if f'{f}/{a}' in only]
        assert cases, only
    done = []
    for fx, action in cases:
        key = f'{fx}/{action}'
        script, args = ACTIONS[action]
        if fx == 'b':
            root = _fx_project_init(tmp, f'nores_{fx}__{action}')
            args = ['--list', 'sub_questions', '--order', ','.join(reversed(INIT_QIDS))]
        else:
            root = _fx_no_results(tmp, f'nores_{fx}__{action}',
                                  validation=(fx == 'c1'), keep_rerun=(fx == 'c2'))
        v_before = (root / 'analysis/validation.yaml').is_file()
        state_before = _state_analysis(root)
        top_before = _top_fp(root) if v_before else {}
        marks_before = sorted({m for it in _items_of(root).values() for m in it['marks']}) if v_before else []
        proj_before = (root / 'project.yaml').read_text(encoding='utf-8')
        # 先 dry-run：一個位元都不該改
        stamp = {p: p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file()}
        rc_d, out_d = run_dry(script, root, *args)
        assert rc_d == 0, f'{key}：dry-run 失敗 rc={rc_d}\n{out_d[-2500:]}'
        after = {p: p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file()}
        assert after == stamp, f'{key}：dry-run 改了檔 {sorted(set(after) ^ set(stamp))[:5]}'
        rc, out = run_action(script, root, *args)
        assert rc == 0, f'{key}：沒有 results.json 讓動作中止 rc={rc}\n{out[-2500:]}'
        # 不得建立這兩個檔、不得動 state.analysis
        assert not (root / 'analysis/results.json').exists(), f'{key}：動作建了 analysis/results.json'
        assert (root / 'analysis/validation.yaml').is_file() == v_before, f'{key}：validation.yaml 存在性被動作改了'
        assert _state_analysis(root) == state_before, f'{key}：state.analysis 被改到 {_state_analysis(root)}'
        sa_old = re.search(r'\n  analysis:\n(?:    .*\n|      .*\n|\n)*', proj_before)
        sa_new = re.search(r'\n  analysis:\n(?:    .*\n|      .*\n|\n)*',
                           (root / 'project.yaml').read_text(encoding='utf-8'))
        assert bool(sa_old) == bool(sa_new) and (not sa_old or sa_old.group(0) == sa_new.group(0)), \
            f'{key}：state.analysis 區段逐字變了'
        assert not list((root / 'reviews').glob(f'rerun-waiver-{DATE}*')), f'{key}：沒有結果卻寫了 waiver 報告'
        sources = _no_results_sources(root, out)
        if action in ('reassign_question', 'promote_question'):
            assert any(k.startswith('新 plan ') for k in sources), f'{key}：找不到本次封出來的新 plan'
        for where, text in sources.items():
            for bad in NO_RESULTS_FORBID + (C.STALE_FP_REASON, C.NO_FP_MARK):
                assert bad not in text, f'{key}／{where} 出現「{bad}」\n{text[:1200]}'
            assert not BARE_RECONNECT.search(text), f'{key}／{where} 宣稱重接了 fingerprint\n{text[:1200]}'
            assert not BARE_REREG.search(text), f'{key}／{where} 宣稱重登過\n{text[:1200]}'
            assert not RETAG_N_KEYS.search(text), f'{key}／{where} 用「retag N 鍵」暗示那個檔在\n{text[:1200]}'
            assert '仍 waived' not in text, f'{key}／{where} 宣稱 rerun 仍 waived\n{text[:1200]}'
            # 這個專案連結果都還沒有，叫人「重跑 rerun_all 或另立 waiver 決策」是錯的建議
            assert C.NO_WAIVER_TAIL not in text, \
                f'{key}／{where} 叫人重跑 rerun_all／另立 waiver，但這個專案尚無正式結果\n{text[:1200]}'
        for where in ('決策', 'known_consequences', 'stdout', '步驟紀錄'):
            assert C.NO_RESULTS_BRIEF in sources[where], \
                f'{key}／{where} 沒說這個專案尚無正式結果\n{sources[where][:1200]}'
        # 關卡不得變瞎：步驟紀錄與 stdout 不許有 crash 列或 traceback 字樣
        for where, text in sources.items():
            assert 'CRASH' not in text and 'Traceback' not in text, f'{key}／{where} 有關卡當掉的痕跡\n{text[:1200]}'
        # 步驟標題也要照實：沒有那個檔時不能留著「results.json plan_id retag」這種標題
        names = _run_log_names(root, out)
        assert 'results.json plan_id retag' not in names, f'{key}：步驟標題還寫著要 retag\n{names}'
        if action == 'reorder_questions':
            # 調順序後的 TAMPER 比對不得因為缺檔被跳過（跳過就等於這個關卡沒在看）
            assert 'tamper' in sources['步驟紀錄'], f'{key}：沒有比對調順序後的 TAMPER\n{sources["步驟紀錄"][:900]}'
        warn_lines = sorted({ln for ln in out.split('\n') + _run_log_lines(root, out)
                             if 'WARNING' in ln and C.RESULTS_REL in ln})
        if fx in ('a', 'b'):
            assert not warn_lines, f'{key}：正常的新專案形狀不該有提到 results.json 的 WARNING\n{warn_lines}'
        else:
            assert len(warn_lines) == 1, f'{key}：不一致的形狀要剛好一行照實的 WARNING\n{warn_lines}'
            w = warn_lines[0]
            assert C.NO_RESULTS_BRIEF in w, w
            assert ('analysis/validation.yaml 還在' in w) == (fx == 'c1'), w
            assert ('state.analysis.rerun 留著' in w) == (fx == 'c2'), w
            assert 'state.analysis 一字不動' in w, w
        if fx == 'c1':
            # validation.yaml 的 item 照正常路徑改掛（那是 metadata），但頂層兩欄與標記一律不動
            assert _top_fp(root) == top_before, f'{key}：頂層 fingerprint 被帶到新值 {_top_fp(root)}'
            assert sorted({m for it in _items_of(root).values() for m in it['marks']}) == marks_before, \
                f'{key}：多了 reaffirmed 標記'
            assert _items_of(root)['V2']['sq'] == 'AQ3', f'{key}：item 沒改掛 sq（那是 metadata，該改）'
        done.append(key)
        shutil.rmtree(root)
    if only:
        print(f'[regression] 規格 47（{"／".join(done)}）: pass')
        return
    print(f'[regression] 規格 47：{len(done)} 組（形狀 × 動作）在沒有 analysis/results.json 時 dry-run 零寫入、'
          f'--apply 完成（rc=0）、沒有建出 results.json／validation.yaml、state.analysis 逐字未變；'
          f'決策、known_consequences、stdout、步驟紀錄都照實寫「尚無正式結果」，'
          f'沒有指紋值、沒有「重接」「重登」「retag N 鍵」；正常形狀 0 WARNING、不一致的形狀各 1 行: pass')


def test_no_results_move_blocked(tmp: Path) -> None:
    """規格 48：沒有結果鍵可搬——三支搬結果鍵的動作在前置條件就拒絕（exit 2、第一次寫檔之前）。"""
    for action in MOVE_KEY_ACTIONS:
        script, args = ACTIONS[action]
        root = _fx_no_results(tmp, f'nores_blocked__{action}')
        stamp = {p: p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file()}
        for mode in ('dry', 'apply'):
            rc, out = (run_dry if mode == 'dry' else run_action)(script, root, *args)
            assert rc == 2, f'{action}／{mode}：該在前置條件就拒絕（exit 2），實際 rc={rc}\n{out[-1500:]}'
            assert C.NO_RESULTS_MOVE in out, f'{action}／{mode}：訊息沒說缺檔也沒說沒有結果鍵可搬\n{out[-800:]}'
            assert 'Traceback' not in out, f'{action}／{mode}：訊息是 traceback\n{out[-800:]}'
            now = {p: p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file()}
            assert now == stamp, f'{action}／{mode}：被拒絕卻改了檔 {sorted(set(now) ^ set(stamp))[:5]}'
        shutil.rmtree(root)
    print(f'[regression] 規格 48：{"／".join(MOVE_KEY_ACTIONS)} 在沒有 analysis/results.json 時 dry-run 與 apply '
          '都 rc=2、訊息說沒有結果鍵可搬、一個位元都沒改: pass')


def test_no_results_gates(tmp: Path) -> None:
    """規格 49：缺 results.json 時每個全專案關卡都還在看——不 traceback、不記成 CRASH、參數前後一致。"""
    root = _fx_no_results(tmp, 'nores_gates')
    for key in ('plan', 'plan_results', 'validation', 'coverage', 'decisions'):
        cmd = C.gate_cmd(root, key)
        findings, out = C.run_gate(root, key)
        assert 'Traceback' not in out, f'{key} 關卡在缺檔時丟 traceback\n{out[-800:]}'
        assert not [f for f in findings if 'CRASH' in str(f)], f'{key} 關卡被記成 CRASH（等於沒在看）：{findings}'
        tail = ' '.join(str(x) for x in cmd[1:])
        assert '找不到 results' not in out, f'{key} 關卡只回報「找不到 results」，前後都有、等於沒在看\n{out[-500:]}'
        if key == 'plan_results':
            assert '--results' not in tail, f'plan_results 在缺檔時還傳 --results：{tail}'
        if key == 'decisions':
            assert '--results' not in tail, f'decisions 在缺檔時還傳 --results：{tail}'
        if key == 'coverage':
            # results 是位置參數（少傳一個 bib 會被當成 results，check_coverage usage exit 2），
            # 所以缺檔也照傳專案裡那個路徑：check_coverage 自己認得結果檔不存在、不 traceback，
            # 動作前後同一個路徑，比對才成立（規格 53）
            pos = [str(x) for x in cmd[1:4]]
            assert pos[1] == str(root / C.RESULTS_REL), f'coverage 的 results 參數不是專案裡那個路徑：{pos}'
            assert not Path(pos[1]).exists(), f'這個 fixture 本來就沒有 results.json：{pos}'
            assert [str(x) for x in C.gate_cmd(root, key)[1:4]] == pos, 'coverage 兩次組出來的參數不同'
            assert C.gate_findings(1, out), 'coverage 在這個 fixture 上該報得出既有的非終態問題'
    # 有 results.json 的專案：參數照舊（控制組逐位元不變的前提）
    clean = copy_fixture(tmp, 'nores_gates_clean')
    assert '--results' in ' '.join(str(x) for x in C.gate_cmd(clean, 'plan_results')), 'plan_results 掉了 --results'
    assert str(clean / 'analysis/results.json') in [str(x) for x in C.coverage_argv(clean)], 'coverage 掉了 results'
    # 暫存空 bib 的規矩：一個 process 只建一個、結束刪掉（結果檔不再借暫存空 JSON）
    own = tmp / 'nores_tmpdir'
    own.mkdir(exist_ok=True)
    script, args = ACTIONS['reorder_questions']
    rc, out = run_action(script, root, *args, env_extra={'TMPDIR': str(own)})
    assert rc == 0, out[-1500:]
    left = sorted(p.name for p in own.glob('empty-*'))
    assert not left, f'動作鏈跑完還留著暫存空檔：{left}'
    shutil.rmtree(root)
    shutil.rmtree(clean)
    print('[regression] 規格 49：缺 results.json 時 check_plan／check_plan --require-confirmed／check_validation／'
          'check_coverage／check_decisions 都不 traceback、不記成 CRASH、也不只回報「找不到 results」；'
          'coverage 的 results 位置參數照傳專案裡那個路徑（前後同一個）、plan_results 與 decisions 不帶 --results；'
          '有 results.json 的專案參數照舊；暫存空檔跑完 0 個: pass')


def test_no_results_text_units() -> None:
    """規格 50：「尚無正式結果」的判斷與說法只有一個來源，每個文字 helper 都照實。"""
    assert C.NO_RESULTS_BRIEF in C.NO_RESULTS and C.NO_RESULTS_BRIEF in C.NO_RESULTS_FP
    assert C.NO_RESULTS_BRIEF in C.NO_RESULTS_MOVE and C.NO_RESULTS_BRIEF in C.NO_RESULTS_STEP
    # 短說法是 BRIEF 的一部分，但不含那個檔名：同一行已經有一次 BRIEF 時接的是它（規格 51）
    assert C.NO_RESULTS_SHORT in C.NO_RESULTS_BRIEF and C.RESULTS_REL not in C.NO_RESULTS_SHORT
    assert C.NO_RESULTS_SHORT in C.NO_RESULTS_FP_SHORT and C.NO_RESULTS_FP not in C.NO_RESULTS_FP_SHORT
    assert not hasattr(C, 'NO_RESULTS_WAIVER'), 'waiver 那句改由 WaiverState 依有沒有 waiver 分兩種（規格 51）'
    # 旗標跟著 carry 走：只拿到 carry 的 helper 也判得出來，copy() 不得把它丟掉
    pol = C.StalePolicy({'results': False, 'source': False}, no_results=True)
    assert pol.no_results and pol.carry.no_results and not pol.mark and not pol.pristine
    assert pol.carry.copy().no_results, 'Carry.copy() 把旗標丟了'
    assert C.carry_absent(pol.carry) and not C.carry_absent({'results': True, 'source': True})
    assert not C.carry_absent(None) and not C.StalePolicy().no_results
    old = {'results': 'a' * 20, 'source': 'b' * 20}
    fps = dict(C.NO_FP)
    texts = {'fp_move': C.fp_move_text(old, fps, pol.carry), 'known_fp': C.known_fp_text(pol.carry, old, fps),
             'only_retag': C.only_retag_sentence(pol.carry, '3 鍵 rows 逐位元未變'),
             'fp_col': C.fp_col_text(old, fps, 'source', pol.carry), 'mark': C.mark_clause(pol, 'reaffirmed_x'),
             'summary_fp': C.summary_fp_text({'fingerprint_old': old, 'fingerprint_new': fps,
                                              'fingerprint_carry': pol.carry}),
             'summary_col': C.summary_fp_col({'fingerprint_old': old, 'fingerprint_new': fps,
                                              'fingerprint_carry': pol.carry}, 'source'),
             'note': C.validation_note_text({'items': ['V1'], 'reaffirm_key': 'reaffirmed_x', 'old': old,
                                             'carry': pol.carry, 'unmarked': ['V1'], 'no_results': True}, fps),
             'step': C.retag_step_name(True), 'or': C.results_or(True, '原句')}
    for name, text in texts.items():
        for bad in NO_RESULTS_FORBID + (C.STALE_FP_REASON, C.NO_FP_MARK, old['results'], old['source']):
            assert bad not in text, f'{name} 出現「{bad}」：{text}'
        assert not BARE_RECONNECT.search(text), f'{name} 宣稱重接過：{text}'
        # 短說法也算照實：同一行已經有一次 BRIEF 的位置改用它（規格 51）
        assert C.NO_RESULTS_SHORT in text, f'{name} 沒說尚無正式結果：{text}'
    assert C.results_or(False, '原句') == '原句' and C.retag_step_name(False) == 'results.json plan_id retag'
    # waiver：尚無正式結果時沒有 fingerprint 可重登到，連「無 waiver」那套建議都不該給
    for waiver in ('', WAIVER_ID):
        ws = C.WaiverState(waiver, [], 'waived' if waiver else '', bool(waiver), no_results=True)
        assert ws.state == 'no_results' and not ws.carries, waiver
        wtexts = {'clause': C.waiver_clause(ws), 'sentence': C.waiver_sentence(ws), 'step': C.waiver_step_name(ws),
                  'phrase': C.waiver_phrase(ws, 'waiver 重登（仍是 waived）'),
                  'known': C.waiver_known_line(ws, f'rerun 仍 waived（{WAIVER_ID}），不是 pass'),
                  'decision': C.waiver_decision_line(ws, '', '；舊值推進', '未重登（動作前就漂移）'),
                  'summary': C.waiver_summary_text({'waiver': '', 'waiver_state': ws}),
                  'warn': C.stale_rerun_warn(ws)}
        for name, text in wtexts.items():
            assert '仍 waived' not in text, f'{name} 宣稱仍 waived：{text}'
            assert not BARE_REREG.search(text), f'{name} 宣稱重登：{text}'
            assert C.STALE_FP_REASON not in text and '動作前就漂移' not in text, f'{name} 說成漂移：{text}'
            assert C.NO_WAIVER_TAIL not in text, f'{name} 叫人重跑 rerun_all，但這個專案還沒有結果：{text}'
            # 有 waiver 決策就照實寫編號；沒有就不得出現編號，而且每一句都要說「無 waiver 決策」（規格 51）
            assert (WAIVER_ID in text) == bool(waiver), f'{name} 的 waiver 編號寫得不對：{text}'
            if not waiver:
                assert C.NO_WAIVER_BRIEF in text, f'{name} 沒說本專案沒有 waiver 決策：{text}'
                for bad in NO_WAIVER_FORBID:
                    assert bad not in text, f'{name} 用「{bad}」暗示有一個 waiver 在：{text}'
        for name in ('clause', 'sentence', 'step', 'phrase', 'known', 'decision', 'summary', 'warn'):
            assert '尚無正式結果' in wtexts[name], f'{name} 沒說尚無正式結果：{wtexts[name]}'
    # 判斷只看檔案
    assert C.no_results(Path('/nonexistent-root-for-unit-test')) is True
    warn = C.no_results_warn(True, ['fingerprint'], WAIVER_ID)
    assert C.NO_RESULTS_BRIEF in warn and 'analysis/validation.yaml 還在' in warn and WAIVER_ID in warn
    assert C.no_results_warn(False, [], '') == '', '一致的新專案形狀不該有 WARNING'
    print('[regression] 規格 50：「尚無正式結果」的旗標跟著 StalePolicy／Carry／WaiverState 走（copy() 不掉）、'
          '10 個指紋文字 helper 與 8 個 waiver 文字 helper 都照實寫、不印指紋值也不印佔位標記、'
          '不叫人重跑 rerun_all；一致的新專案形狀不印 WARNING: pass')



# ---------- waiver 說法與重複句、check_coverage 那一句、results links 訊息 ----------

# 沒有 waiver 決策時不得用的說法（都暗示有一個 waiver 在）
NO_WAIVER_FORBID = ('本次不重登', '不重登 waiver')


def _lines_of(sources: dict[str, str]) -> list[tuple[str, str]]:
    """把每個來源切成「一行」：stdout 與步驟紀錄本來一則一行；決策與 `known_consequences` 的編號
    項目、validation.yaml 檔頭的註解行也都各自一行。重複句的規矩是按行算的，所以按行拆。"""
    return [(where, ln) for where, text in sources.items() for ln in text.split('\n') if ln.strip()]


def _validation_header_block(root: Path) -> str:
    """validation.yaml 本次寫進去的檔頭區塊（`# <date> 第…次更新` 起、到下一個檔頭或非註解行為止）。

    `_no_results_sources` 只收含日期的行——檔頭第二行起都沒有日期，重複的整句就躲在那幾行裡。
    """
    path = root / 'analysis/validation.yaml'
    if not path.is_file():
        return ''
    out, grab = [], False
    for ln in path.read_text(encoding='utf-8').split('\n'):
        head = ln.startswith('#') and not ln.startswith('#   ')
        if head and ln.startswith(f'# {DATE} 第'):
            grab = True
        elif grab and (head or not ln.startswith('#')):
            break
        if grab:
            out.append(ln)
    return '\n'.join(out)


def _waiver_of(root: Path) -> str:
    doc = yaml.safe_load((root / 'project.yaml').read_text(encoding='utf-8')) or {}
    rerun = (((doc.get('state') or {}).get('analysis') or {}).get('rerun') or {})
    return str(rerun.get('decision') or '') if isinstance(rerun, dict) else ''


def _assert_waiver_and_dups(key: str, sources: dict[str, str], waiver: str) -> None:
    """規格 51 的三條：同一行最多講一次、檔頭整句最多一次、提到 waiver 的行照實。"""
    for where, ln in _lines_of(sources):
        assert ln.count(C.NO_RESULTS_BRIEF) <= 1, f'{key}／{where} 同一行把「尚無正式結果」講了兩次：\n{ln}'
        assert ln.count('不重登') + ln.count('未重登') <= 1, f'{key}／{where} 同一行說了兩次不重登：\n{ln}'
        if 'waiver' not in ln:
            continue
        if waiver:
            assert waiver in ln, f'{key}／{where} 提到 waiver 卻沒說是哪一筆決策：\n{ln}'
        else:
            assert C.NO_WAIVER_BRIEF in ln, f'{key}／{where} 提到 waiver 卻沒說本專案沒有 waiver 決策：\n{ln}'
            for bad in NO_WAIVER_FORBID:
                assert bad not in ln, f'{key}／{where} 用「{bad}」暗示有一個 waiver 在：\n{ln}'
    hdr = sources.get('validation.yaml 檔頭區塊', '')
    assert hdr.count(C.NO_RESULTS_FP) <= 1, \
        f'{key}：檔頭區塊把同一整句講了 {hdr.count(C.NO_RESULTS_FP)} 次\n{hdr}'


def test_no_results_waiver_text(tmp: Path, only: tuple[str, ...] = ()) -> None:
    """規格 51：尚無正式結果時 waiver 的說法分「沒有 waiver」「有 waiver」兩種，而且同一行不講兩次。

    a／b／c1 沒有 waiver 決策：每一行提到 waiver 的都要含 `NO_WAIVER_BRIEF`，不得用「本次不重登」
    「不重登 waiver」。c2 的 `state.analysis.rerun` 記著一筆 waiver 決策：提到 waiver 的行要寫出編號。
    """
    cases = [('a', 'reorder_questions'), ('b', 'reorder_questions'),
             ('c1', 'reassign_question'), ('c2', 'reassign_question')]
    if only:
        cases = [(f, a) for f, a in cases if f'{f}/{a}' in only]
        assert cases, only
    done = []
    for fx, action in cases:
        key = f'{fx}/{action}'
        script, args = ACTIONS[action]
        if fx == 'b':
            root = _fx_project_init(tmp, f'wv_{fx}__{action}')
            args = ['--list', 'sub_questions', '--order', ','.join(reversed(INIT_QIDS))]
        else:
            root = _fx_no_results(tmp, f'wv_{fx}__{action}',
                                  validation=(fx == 'c1'), keep_rerun=(fx == 'c2'))
        waiver = _waiver_of(root)
        assert bool(waiver) == (fx == 'c2'), f'{key}：形狀沒造對（waiver={waiver!r}）'
        rc, out = run_action(script, root, *args)
        assert rc == 0, f'{key}：動作沒完成 rc={rc}\n{out[-2000:]}'
        sources = _no_results_sources(root, out)
        hdr = _validation_header_block(root)
        assert bool(hdr) == (fx == 'c1'), f'{key}：檔頭區塊收得不對（c1 才有 validation.yaml）'
        if hdr:
            sources['validation.yaml 檔頭區塊'] = hdr
        _assert_waiver_and_dups(key, sources, waiver)
        if waiver:
            for where in ('決策', 'stdout', '步驟紀錄'):
                assert waiver in sources[where], \
                    f'{key}／{where} 沒寫出那筆 waiver 決策\n{sources[where][:900]}'
        else:
            for where in ('決策', 'stdout', '步驟紀錄'):
                assert C.NO_WAIVER_BRIEF in sources[where], \
                    f'{key}／{where} 沒說本專案沒有 waiver 決策\n{sources[where][:900]}'
        done.append(key)
        shutil.rmtree(root)
    if only:
        print(f'[regression] 規格 51（{"／".join(done)}）: pass')
        return
    print(f'[regression] 規格 51：{len(done)} 種形狀——沒有 waiver 的三種每一處都寫「{C.NO_WAIVER_BRIEF}」、'
          '不用「本次不重登」「不重登 waiver」；有 waiver 的那種寫出決策編號；'
          '同一行「尚無正式結果」最多一次、「不重登／未重登」最多一次、檔頭區塊同一整句最多一次: pass')


# check_coverage 那一句：各動作原本的寫法（正常形狀逐字沿用），用來驗 helper 不亂改
COVERAGE_NORMALS = ('快照不變（id 集合相同，check_coverage 0 tamper）',
                    'TAMPER 只有 AQ7 新增、SQ6 被移除兩筆 → --update-snapshot → 0 tamper',
                    'goals id 集合不變、0 tamper（快照重寫一次對帳）', 'goals id 集合不變、0 tamper',
                    'goals 不變、0 tamper', 'sub_questions 已空、無法執行，快照由腳本直接寫入')
# 動作前就有 TAMPER／動作前沒有快照時，各自不得出現的寫死說法
COVERAGE_FORBID = {'p': ('0 tamper', '--update-snapshot'),
                   'q': ('快照不變', '0 tamper', 'TAMPER 只有')}


def _cov(snapshot_before: bool, tamper_before: int, path: str, tamper_after=None) -> dict:
    return {'snapshot_before': snapshot_before, 'tamper_before': tamper_before,
            'expected': ['AQ7: 新增', 'SQ6: 被移除'], 'path': path, 'tamper_after': tamper_after}


def test_coverage_sentence_units() -> None:
    """規格 52（單元）：決策裡講 check_coverage 的那一句只有一個來源，每條路徑一案。"""
    normal = _cov(True, 0, 'update', 0)
    for text in COVERAGE_NORMALS:
        # 正常形狀（有快照、沒有既有 TAMPER）逐字沿用原句；沒有記錄時也沿用，不自己編
        for cov in (normal, _cov(True, 0, 'direct'), _cov(True, 0, 'compare'), None, {}, _cov(True, 0, '')):
            assert C.coverage_text(cov, text) == text, (text, cov)
        # (p) 動作前就有 TAMPER：三方合併／只比對／直接寫入三條路徑
        for cov in (_cov(True, 3, 'merge', 3), _cov(True, 3, 'compare'), _cov(True, 3, 'direct')):
            got = C.coverage_text(cov, text)
            assert got != text and '動作前就有 3 筆' in got, got
            for bad in COVERAGE_FORBID['p']:
                assert bad not in got, f'{cov["path"]}：{bad}\n{got}'
        # (q) 動作前沒有快照：--update-snapshot 新建／不比對也不建／直接寫入
        for cov in (_cov(False, 0, 'create', 0), _cov(False, 0, 'skip'), _cov(False, 0, 'direct')):
            got = C.coverage_text(cov, text)
            assert got != text and f'動作前沒有 goals 快照（{C.SNAPSHOT_REL} 不存在）' in got, got
            for bad in COVERAGE_FORBID['q']:
                assert bad not in got, f'{cov["path"]}：{bad}\n{got}'
    # 每條路徑的「本動作做了什麼」各有一句、互不相同
    assert len(set(C.COVERAGE_PATH_TEXT.values())) == len(C.COVERAGE_PATH_TEXT) == 6, C.COVERAGE_PATH_TEXT
    assert C.coverage_normal(_cov(True, 0, 'update', 0)) and not C.coverage_normal(_cov(False, 0, 'create', 0))
    assert not C.coverage_normal(_cov(True, 2, 'merge', 2)) and not C.coverage_normal(None)
    # 步驟紀錄那一則：不得寫成「快照前 TAMPER 0 筆（<本次預期>）」那種自相矛盾的句子
    note = C.coverage_note(_cov(False, 0, 'create', 0))
    assert '略過 TAMPER 比對（本次預期 AQ7: 新增、SQ6: 被移除）' in note and '0 筆 TAMPER' in note, note
    assert '快照前 TAMPER 0 筆' not in note, note
    skip = C.coverage_note(_cov(False, 0, 'skip'))
    assert '沒有比對也沒有建立快照' in skip and 'TAMPER' in skip.split('；')[0], skip
    for text in (note, skip):
        for bad in COVERAGE_FORBID['q']:
            assert bad not in text, f'{bad}\n{text}'
    print('[regression] 規格 52（單元）：check_coverage 那一句由 coverage_text 一處產生——正常形狀 6 種'
          '寫法逐字沿用、動作前就有 TAMPER 的三條路徑都說出既有筆數且不寫「0 tamper」「--update-snapshot」、'
          '動作前沒有快照的三條路徑都說出沒有快照且不寫「快照不變」「TAMPER 只有」；'
          '步驟紀錄那一則不再寫「快照前 TAMPER 0 筆（<預期>）」: pass')


COVERAGE_ACTIONS = ('reorder_questions', 'reassign_question', 'nest_result')


def test_coverage_sentence_actions(tmp: Path, only: tuple[str, ...] = ()) -> None:
    """規格 52（實跑）：(p) 動作前就有 TAMPER、(q) 動作前沒有快照，兩種形狀各三支動作都照實寫。"""
    cases = [(shape, a) for shape in ('p', 'q') for a in COVERAGE_ACTIONS]
    if only:
        cases = [(s, a) for s, a in cases if f'{s}/{a}' in only]
        assert cases, only
    done = []
    for shape, action in cases:
        key = f'{shape}/{action}'
        script, args = ACTIONS[action]
        name = f'cov_{shape}__{action}'
        if shape == 'p':
            root = _dirty_fixture(tmp, name)
            n_before = len(C.tamper_keys(C.run_script('check_coverage', *C.coverage_argv(root))[1]))
            assert n_before >= 2, f'{key}：形狀沒造對（動作前 TAMPER {n_before} 筆）'
        else:
            root = copy_fixture(tmp, name)
            (root / 'evaluations/goals-snapshot.json').unlink()
            n_before = 0
        rc, out = run_action(script, root, *args)
        assert rc == 0, f'{key}：動作沒完成 rc={rc}\n{out[-2000:]}'
        did = re.search(r'決策 (D-\d+)', out).group(1)
        entry = next(d for d in yaml.safe_load((root / 'decisions.yaml').read_text(encoding='utf-8'))['decisions']
                     if d['id'] == did)
        sources = {'決策': str(entry.get('decision') or ''),
                   'known_consequences': str(entry.get('known_consequences') or ''),
                   'stdout': out, '步驟紀錄': _run_log_text(root, out)}
        for where, text in sources.items():
            for bad in COVERAGE_FORBID[shape]:
                assert bad not in text, f'{key}／{where} 還寫著「{bad}」\n{text[:1500]}'
        if shape == 'p':
            assert f'動作前就有 {n_before} 筆' in sources['決策'], \
                f'{key}：決策沒說動作前就有幾筆\n{sources["決策"][:1200]}'
            # 會寫快照的動作（走 step_coverage）才有三方合併；reorder 只比對、不動快照
            merged = action != 'reorder_questions'
            assert ('三方合併' in sources['決策']) == merged, f'{key}：三方合併寫得不對\n{sources["決策"][:1200]}'
            assert ('未代替使用者確認' in sources['決策'] + sources['步驟紀錄']) == merged, \
                f'{key}：未代替使用者確認寫得不對\n{sources["決策"][:1200]}'
            assert ('只比對、不動快照' in sources['決策']) != merged, f'{key}：快照處置寫得不對'
        else:
            for where in ('決策', '步驟紀錄'):
                assert f'動作前沒有 goals 快照（{C.SNAPSHOT_REL} 不存在）' in sources[where], \
                    f'{key}／{where} 沒說動作前沒有快照\n{sources[where][:1200]}'
            built = (root / 'evaluations/goals-snapshot.json').is_file()
            assert built == (action != 'reorder_questions'), f'{key}：快照建不建與原本不同（{built}）'
            did_what = ('沒有比對也沒有建立快照' if action == 'reorder_questions' else '新建了快照')
            assert did_what in sources['決策'], f'{key}：決策沒說本動作做了什麼\n{sources["決策"][:1200]}'
        done.append(key)
        shutil.rmtree(root)
    if only:
        print(f'[regression] 規格 52（{"／".join(done)}）: pass')
        return
    print(f'[regression] 規格 52（實跑）：{len(done)} 組——動作前就有 TAMPER 的三支都說出既有筆數與'
          '三方合併、未代替使用者確認；動作前沒有快照的三支都說出沒有快照與本動作做了什麼；'
          '兩種形狀的決策、known_consequences、stdout、步驟紀錄都不再有「0 tamper」那類寫死的句子: pass')


def test_no_results_links_message(tmp: Path) -> None:
    """規格 53：沒有 results.json 時，check_coverage 對 goals 的 results links 照實說結果檔不存在。

    暫存空 JSON 那套做法會讓關卡報「results.json 無鍵 "k"」——讀的人會以為檔案在、只是少了鍵。
    改法選 (B)：`check_coverage.py` 自己認得結果檔不存在，`coverage_argv` 改回傳專案裡那個路徑。
    """
    root = _fx_no_results(tmp, 'nores_links', keep_links=True)
    links = [ln for ln in (root / 'project.yaml').read_text(encoding='utf-8').split('\n') if 'results:' in ln]
    assert links, '這個 fixture 要留著 goals 的 results links'
    rc, out = run_action('reorder_questions.py', root, '--list', 'sub_questions', '--order', 'SQ2,SQ1')
    assert rc == 0, f'rc={rc}\n{out[-2000:]}'
    sources = _no_results_sources(root, out)
    for where in ('決策', 'known_consequences', 'stdout', '步驟紀錄'):
        text = sources[where]
        assert 'results.json 無鍵' not in text, \
            f'{where}：結果檔不存在卻說成「無鍵」（讀的人會以為檔案在）\n{text[:1500]}'
        assert '結果檔 results.json 不存在（尚無正式結果）' in text, \
            f'{where}：既有項目那一段沒照實說結果檔不存在\n{text[:1500]}'
        assert 'Traceback' not in text and 'CRASH' not in text, f'{where} 有關卡當掉的痕跡\n{text[:1200]}'
    # 參數用專案裡那個路徑（前後同一個），不再借一個暫存空 JSON
    pos = [str(x) for x in C.coverage_argv(root)[:3]]
    assert pos[1] == str(root / C.RESULTS_REL) and not Path(pos[1]).exists(), pos
    assert not hasattr(C, 'results_path_or_empty'), '暫存空 JSON 那套該整組拿掉'
    # 有 results.json 的專案：訊息逐字不變（鍵真的少了才說「無鍵」）
    clean = copy_fixture(tmp, 'nores_links_clean')
    text = (clean / 'project.yaml').read_text(encoding='utf-8')
    (clean / 'project.yaml').write_text(text.replace('results:k1', 'results:k_gone', 1), encoding='utf-8')
    _rc, cov = C.run_script('check_coverage', *C.coverage_argv(clean))
    assert 'results.json 無鍵 "k_gone"' in cov, f'有結果檔時那句該逐字不變\n{cov[-600:]}'
    assert '結果檔 results.json 不存在' not in cov, cov[-600:]
    shutil.rmtree(root)
    shutil.rmtree(clean)
    print('[regression] 規格 53：沒有 analysis/results.json 時 check_coverage 對 results links 照實說'
          '「結果檔 results.json 不存在（尚無正式結果）」——決策、known_consequences、stdout、步驟紀錄'
          '都不再出現「無鍵」；coverage 的 results 位置參數改回專案裡那個路徑（暫存空 JSON 整組移除）；'
          '有結果檔時「無鍵」那句逐字不變: pass')


# ======================================================================
# 規格 54～56：搬 plan／降為敏感性分析時，隨 links 搬走的既有發現
# ======================================================================

# check_coverage 對壞掉的 results link 的兩種寫法（單元測試與實跑的斷言共用同一個模子）
_LINK_MISSING = 'BLOCKER {q}: link 無效, results.json 無鍵 "{k}"'
_LINK_NO_FILE = 'BLOCKER {q}: link 無效, 結果檔 results.json 不存在（尚無正式結果）, 對不到 "{k}"'
# a1 是 AQ1-v1 宣告的 outputs 鍵，會隨 plan 一起搬走；zz 誰都沒宣告，不隨 plan 搬走
LINK_MOVED_KEY = 'a1'
LINK_STAY_KEY = 'zz'
# (動作, 來源問題, 目的問題)：兩支會搬 links 的動作
MOVED_LINK_CASES = (('move_plan', 'AQ1', 'AQ2'), ('demote_plan', 'AQ1', 'SQ1'))


def test_moved_link_forms_units() -> None:
    """規格 54（單元）：只有隨本動作搬走的那條 link 認得「換到目的問題」，其餘一概不放寬。"""
    mv = [C.MovedLink(LINK_MOVED_KEY, 'AQ8', 'AQ9')]
    before = _LINK_NO_FILE.format(q='AQ8', k=LINK_MOVED_KEY)
    after = _LINK_NO_FILE.format(q='AQ9', k=LINK_MOVED_KEY)
    new, kept, gone = C.diff_findings([before], [after], {}, mv)
    assert (new, kept, gone) == ([], [after], []), (new, kept, gone)
    # 沒有登記（等於沒搬過這條 link）就只認原來的問題 id
    assert C.diff_findings([before], [after], {})[0] == [after], '沒登記卻換了問題 id'
    # 只對登記過的鍵：同一個來源問題上另一個鍵不跟著換
    stay_after = _LINK_MISSING.format(q='AQ9', k=LINK_STAY_KEY)
    assert C.diff_findings([_LINK_MISSING.format(q='AQ8', k=LINK_STAY_KEY)], [stay_after], {}, mv)[0] \
        == [stay_after], '沒搬走的鍵也被換了問題 id'
    # 鍵要帶引號才算提到它：`a1` 是 `a11` 的前段，不得混為一談
    long_after = _LINK_MISSING.format(q='AQ9', k=LINK_MOVED_KEY + '1')
    assert C.diff_findings([_LINK_MISSING.format(q='AQ8', k=LINK_MOVED_KEY + '1')], [long_after], {}, mv)[0] \
        == [long_after], '鍵只比前段就算提到了'
    # 只從來源問題換到目的問題：第三個問題報的同一個鍵不算同一筆，換到第三個問題也不算
    assert C.diff_findings([_LINK_NO_FILE.format(q='SQ6', k=LINK_MOVED_KEY)], [after], {}, mv)[0] == [after], \
        '別的問題底下的同一個鍵被當成同一筆'
    third = _LINK_NO_FILE.format(q='AQ7', k=LINK_MOVED_KEY)
    assert C.diff_findings([before], [third], {}, mv)[0] == [third], '換到不是目的問題的問題也算'
    # 完整 token：來源問題是 AQ8 時 AQ80 不算
    assert C.diff_findings([_LINK_NO_FILE.format(q='AQ80', k=LINK_MOVED_KEY)], [after], {}, mv)[0] == [after], \
        '來源問題 id 只比前段就算'
    # multiset 不變：動作前一筆、動作後來源與目的各一筆 → 多出的那筆算新增
    new, kept, gone = C.diff_findings([before], [after, before], {}, mv)
    assert len(new) == 1 and len(kept) == 1 and not gone, (new, kept, gone)
    # 動作後目的問題報兩筆一樣的：換過問題的那條路也只消耗一筆，多的那筆仍算新增
    new, kept, gone = C.diff_findings([before], [after, after], {}, mv)
    assert len(new) == 1 and len(kept) == 1 and not gone, (new, kept, gone)
    # 對照形式只多這一種；開頭沒掛問題 id 的訊息（例如關卡當掉）一律不生成
    assert C.moved_link_forms(before, mv) == [after], C.moved_link_forms(before, mv)
    assert C.moved_link_forms(before, []) == [], '沒有登記卻生成了對照形式'
    assert C.moved_link_forms('CRASH rc=1: boom', mv) == [], 'CRASH 也被換了'
    assert C.moved_link_forms('BLOCKER V3: primary result 不存在: ' + LINK_MOVED_KEY, mv) == [], \
        '掛 validation item id 的訊息也被換了'
    # 只有 check_coverage 吃這種對照：別的關卡掛的是 plan id／item id／D#
    for key in C.GATE_LABEL:
        assert C.moved_for_gate(key, mv) == (mv if key in C.MOVED_LINK_GATES else []), key
    assert C.MOVED_LINK_GATES == ('coverage',), C.MOVED_LINK_GATES
    # 登記只收 results: 開頭的 link，重複的只留一筆（不開整條鏈，直接拿登記那一支來驗）

    class _Reg:
        moved_links: list[C.MovedLink] = []

    stub = _Reg()
    stub.moved_links = []
    C.Chain.register_moved_links(stub, [f'results:{LINK_MOVED_KEY}', 'cite:x', 'ms:§1',
                                        f'results:{LINK_MOVED_KEY}'], 'AQ8', 'AQ9')
    assert stub.moved_links == [C.MovedLink(LINK_MOVED_KEY, 'AQ8', 'AQ9')], stub.moved_links
    print('[regression] 規格 54（單元）：隨本動作搬走的 link 換到目的問題才認成既有——沒登記、沒搬走的鍵、'
          '鍵只比前段、別的來源問題、換到第三個問題、掛 item id 或 CRASH 的訊息都不放寬；'
          'multiset 照舊（動作後多一筆仍算新增）；只有 check_coverage 吃這種對照；'
          '登記只收 results: 的 link 且會去重: pass')


def _fx_link_broken(tmp: Path, name: str) -> Path:
    """有結果的專案：把 AQ1-v1 宣告的 `a1` 從 results.json 拿掉，AQ1 的 links 照舊連著它。

    再加一條誰都沒宣告的 `results:zz`——它不是 plan 的 outputs 鍵，不隨 plan 搬走，
    動作後必須仍掛在來源問題下（用來驗「不得放寬沒搬走的 link」）。
    """
    root = copy_fixture(tmp, name)
    path = root / 'analysis/results.json'
    doc = json.loads(path.read_text(encoding='utf-8'))
    doc.pop(LINK_MOVED_KEY)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    path = root / 'project.yaml'
    text = path.read_text(encoding='utf-8')
    old = f'    links: ["results:{LINK_MOVED_KEY}"]'
    assert text.count(old) == 1, f'fixture 的 AQ1 links 那一行出現 {text.count(old)} 次'
    path.write_text(text.replace(old, f'{old[:-1]}, "results:{LINK_STAY_KEY}"]'), encoding='utf-8')
    refix_fingerprints(root)
    return root


def _coverage_existing(root: Path, out: str) -> list[str]:
    """stdout 與步驟紀錄裡 check_coverage 的既有項目（原文，不含標籤）。"""
    label = C.GATE_LABEL['coverage'] + '（' + C._EXISTING_KIND[False] + '）'
    return [ln.split(label, 1)[1] for ln in out.split('\n') + _run_log_lines(root, out)
            if '既有項目' in ln and label in ln]


def _links_of(root: Path, qid: str) -> list[str]:
    doc = yaml.safe_load((root / 'project.yaml').read_text(encoding='utf-8'))
    sq, aq = C.goals_of(doc)
    return [str(x) for x in (next(q for q in sq + aq if str(q.get('id')) == qid).get('links') or [])]


def test_moved_link_existing(tmp: Path, only: tuple[str, ...] = ()) -> None:
    """規格 55：有結果的專案裡搬走一條動作前就壞掉的 link——動作照常完成，那一筆列為既有（帶目的問題）。

    `only`：只跑指定的動作（驗牙用）。
    """
    cases = [c for c in MOVED_LINK_CASES if not only or c[0] in only]
    assert cases, only
    done = []
    for action, src_q, dst_q in cases:
        script, args = ACTIONS[action]
        root = _fx_link_broken(tmp, f'movedlink__{action}')
        before = _LINK_MISSING.format(q=src_q, k=LINK_MOVED_KEY)
        stay = _LINK_MISSING.format(q=src_q, k=LINK_STAY_KEY)
        base = _gate_lines(root, 'coverage')
        assert before in base and stay in base, f'{action}：fixture 沒造出動作前就壞掉的兩條 link\n{base}'
        rc, out = run_action(script, root, *args)
        assert rc == 0, f'{action}：搬走一條動作前就壞掉的 link 讓動作中止 rc={rc}\n{out[-2500:]}'
        rows = _coverage_existing(root, out)
        after = _LINK_MISSING.format(q=dst_q, k=LINK_MOVED_KEY)
        assert after in rows, f'{action}：搬走的那一筆沒有列為既有（帶 {dst_q}）\n{rows}'
        assert before not in rows, f'{action}：搬走之後還把那一筆記在 {src_q} 下\n{rows}'
        assert stay in rows, f'{action}：沒搬走的壞 link 不在既有項目裡\n{rows}'
        # 呈現照既有項目原本的寫法，沒有本次新增
        log = '\n'.join(_run_log_lines(root, out))
        assert f'{C.GATE_LABEL["coverage"]}：既有' in log and '本次新增 0 筆' in log, \
            f'{action}：步驟紀錄沒有照既有項目的寫法記 check_coverage\n{log[-1200:]}'
        assert '本次新增 1' not in out and '本次新增 1' not in log, f'{action}：還是把它當成本次新增\n{out[-1200:]}'
        did = re.search(r'決策 (D-\d+)', out)
        assert did, out[-800:]
        entry = next(d for d in yaml.safe_load((root / 'decisions.yaml').read_text(encoding='utf-8'))['decisions']
                     if d['id'] == did.group(1))
        kc = str(entry.get('known_consequences') or '')
        assert after in kc and stay in kc, f'{action}：既有項目沒有照實寫進決策\n{kc[:1200]}'
        # links 真的搬過去了，沒搬的那條還在來源問題
        assert f'results:{LINK_MOVED_KEY}' in _links_of(root, dst_q), f'{action}：link 沒搬到 {dst_q}'
        assert _links_of(root, src_q) == [f'results:{LINK_STAY_KEY}'], \
            f'{action}：{src_q} 的 links 不是只剩沒搬走的那條 {_links_of(root, src_q)}'
        done.append(action)
        shutil.rmtree(root)
    if only:
        print(f'[regression] 規格 55（{"／".join(done)}）: pass')
        return
    print(f'[regression] 規格 55：{"／".join(done)} 在「plan 宣告的鍵不在結果檔、goals 卻連著它」的專案上 '
          'rc=0——那一筆以目的問題 id 列進 stdout、決策與步驟紀錄，本次新增 0 筆；'
          '沒搬走的壞 link 仍掛在來源問題下: pass')


def test_moved_link_no_results(tmp: Path, only: tuple[str, ...] = ()) -> None:
    """規格 56：尚無正式結果卻還留著 results links 時，搬 plan 照常完成，既有的文字規則照樣成立。

    `only`：只跑指定的動作（驗牙用）。
    """
    cases = [c for c in MOVED_LINK_CASES if not only or c[0] in only]
    assert cases, only
    done = []
    for action, src_q, dst_q in cases:
        script, args = ACTIONS[action]
        root = _fx_no_results(tmp, f'movedlink_nores__{action}', keep_links=True)
        key = f'nores/{action}'
        before = _LINK_NO_FILE.format(q=src_q, k=LINK_MOVED_KEY)
        assert before in _gate_lines(root, 'coverage'), f'{key}：fixture 沒造出動作前就壞掉的 link'
        assert not _waiver_of(root), f'{key}：這個形狀不該有 waiver 決策'
        if action == 'move_plan':      # dry-run 零寫入在這個形狀驗一次就夠
            stamp = bytes_of(root)
            rc, out = run_dry(script, root, *args)
            assert rc == 0, f'{key}：dry-run 被擋下 rc={rc}\n{out[-2500:]}'
            assert bytes_of(root) == stamp, f'{key}：dry-run 改了檔'
        rc, out = run_action(script, root, *args)
        assert rc == 0, f'{key}：動作沒完成 rc={rc}\n{out[-2500:]}'
        after = _LINK_NO_FILE.format(q=dst_q, k=LINK_MOVED_KEY)
        rows = _coverage_existing(root, out)
        assert after in rows, f'{key}：搬走的那一筆沒有列為既有（帶 {dst_q}）\n{rows}'
        assert before not in rows, f'{key}：搬走之後還把那一筆記在 {src_q} 下\n{rows}'
        assert not (root / 'analysis/results.json').exists(), f'{key}：動作建了 analysis/results.json'
        # 規格 47、51 的否定清單與「同一行最多一次」在這個形狀下照樣成立
        sources = _no_results_sources(root, out)
        for where, text in sources.items():
            for bad in NO_RESULTS_FORBID + (C.STALE_FP_REASON, C.NO_FP_MARK, C.NO_WAIVER_TAIL):
                assert bad not in text, f'{key}／{where} 出現「{bad}」\n{text[:1200]}'
            assert not BARE_RECONNECT.search(text), f'{key}／{where} 宣稱重接了 fingerprint\n{text[:1200]}'
            assert not BARE_REREG.search(text), f'{key}／{where} 宣稱重登過\n{text[:1200]}'
            assert not RETAG_N_KEYS.search(text), f'{key}／{where} 用「retag N 鍵」暗示那個檔在\n{text[:1200]}'
            assert 'CRASH' not in text and 'Traceback' not in text, f'{key}／{where} 有關卡當掉的痕跡\n{text[:1200]}'
        for where in ('決策', 'known_consequences', 'stdout', '步驟紀錄'):
            assert C.NO_RESULTS_BRIEF in sources[where], \
                f'{key}／{where} 沒說這個專案尚無正式結果\n{sources[where][:1200]}'
        dups = {ln for _w, ln in _lines_of(sources) if ln.count(C.NO_RESULTS_BRIEF) > 1}
        assert not dups, f'{key}：有行把「尚無正式結果」整句講了兩次\n{sorted(dups)}'
        _assert_waiver_and_dups(key, sources, '')
        _assert_once_per_line(key, sources)
        done.append(action)
        shutil.rmtree(root)
    if only:
        print(f'[regression] 規格 56（{"／".join(done)}）: pass')
        return
    print(f'[regression] 規格 56：{"／".join(done)} 在「尚無正式結果卻還留著 results links」的專案上 '
          'dry-run 零寫入、--apply 完成，那一筆以目的問題 id 列為既有；'
          '沒有建出 results.json，規格 47／51 的否定清單與「同一行每個片語最多一次」照樣成立: pass')


# ======================================================================
# 規格 57：尚無正式結果時，同一行只講一次理由
# ======================================================================

# 同一行各最多一次的片語（直接取自組句機制的常數，兩邊不會漂開）
ONCE_PHRASES = (C.SameLine.WHY, C.SameLine.FP, C.SameLine.MARK, C.SameLine.RELOG)
# 這兩個是結論：出現在哪一行，同一行就要看得到理由（理由跟著結論走，不得只剩結論）
CONCLUSIONS = (C.SameLine.MARK, C.SameLine.RELOG)


def _assert_once_per_line(key: str, sources: dict[str, str]) -> None:
    """規則 1：同一行每個片語最多一次。規則 2：講了結論的行，同一行要看得到理由。"""
    for where, ln in _lines_of(sources):
        for ph in ONCE_PHRASES:
            assert ln.count(ph) <= 1, \
                f'{key}／{where} 同一行把「{ph}」講了 {ln.count(ph)} 次：\n{ln}'
        for ph in CONCLUSIONS:
            if ph in ln:
                assert C.SameLine.WHY in ln, \
                    f'{key}／{where} 同一行只剩結論「{ph}」、理由被刪掉了：\n{ln}'


def test_same_line_units() -> None:
    """規格 57（單元）：組句機制本身——理由只說一次、結論留著、有結果的路徑一字不動。"""
    assert ONCE_PHRASES == ('尚無正式結果', '沒有 fingerprint 可', '不加 reaffirmed 標記', '不重登'), ONCE_PHRASES
    # 有結果（absent=False）：問幾次都回 True，一個字都不記 → 子句逐字沿用原句
    ok = C.SameLine(False)
    assert all(ok.need(p) for p in ONCE_PHRASES) and all(ok.need(p) for p in ONCE_PHRASES) and not ok.said
    ok.own(C.SameLine.WHY)
    assert not ok.said, '有結果時 own() 也不該記'
    assert C.line_need(None, C.SameLine.WHY) and C.no_results_text(None) == C.NO_RESULTS
    C.line_own(None, C.SameLine.WHY)        # None 容忍：不得丟例外
    # 尚無正式結果：第一個問到的自己說，之後同一行都回 False
    line = C.SameLine(True)
    assert line.need(C.SameLine.WHY) and not line.need(C.SameLine.WHY)
    assert line.need(C.SameLine.FP) and not line.need(C.SameLine.FP)
    # 兩句整句的 builder：沒人說過時與常數逐字相同
    assert C.no_results_text() == C.NO_RESULTS and C.no_results_fp_text() == C.NO_RESULTS_FP
    assert C.no_results_brief() == C.NO_RESULTS_BRIEF
    assert C.NO_RESULTS_BRIEF in C.no_results_text() and C.SameLine.MARK in C.no_results_fp_text()
    pol = C.StalePolicy({'results': False, 'source': False}, no_results=True)
    # (a) 檔名那一句先說理由 → 標記那一句只留結論，片語種類不少
    one = C.SameLine(True)
    first, second = C.no_results_text(one), C.mark_clause(pol, 'reaffirmed_x', one)
    assert first == C.NO_RESULTS, first
    assert second == '各 item 不加 reaffirmed 標記', second
    joined = first + '；' + second
    assert all(joined.count(p) <= 1 for p in ONCE_PHRASES), joined
    assert C.SameLine.WHY in joined and C.SameLine.MARK in joined, joined
    # (b) 標記那一句先說理由 → 指紋那一句讓掉理由與標記、留下自己的結論
    two = C.SameLine(True)
    first, second = C.mark_clause(pol, 'reaffirmed_x', two), C.no_results_fp_text(two)
    assert first == f'各 item 不加 reaffirmed 標記（{C.NO_RESULTS_SHORT}，沒有 fingerprint 可接）', first
    assert second == C.RESULTS_REL + ' 不存在：本次不寫 fingerprint', second
    joined = first + '；' + second
    assert all(joined.count(p) <= 1 for p in ONCE_PHRASES), joined
    # (c) waiver：沒有 waiver 與有 waiver 兩種說法都要讓掉重複的理由，結論與影響留著
    for waiver in ('', WAIVER_ID):
        ws = C.WaiverState(waiver, [], 'waived' if waiver else '', bool(waiver), no_results=True)
        full = ws.why_no_results()
        line = C.SameLine(True)
        head = C.no_results_fp_text(line)
        short = ws.why_no_results(line)
        assert C.SameLine.RELOG in short and 'state.analysis.rerun 一字不動' in short, short
        assert C.NO_RESULTS_SHORT not in short and '沒有 fingerprint 可' not in short, short
        assert (WAIVER_ID in short) == bool(waiver), short
        assert (C.NO_WAIVER_BRIEF in short) == (not waiver), short      # 沒有 waiver 是另一個理由，照舊
        assert len(short) < len(full), (short, full)
        joined = head + '；rerun waiver ' + short
        assert all(joined.count(p) <= 1 for p in ONCE_PHRASES), joined
        assert C.SameLine.WHY in joined, joined
        # 同一行的短句版與檔頭整句版都吃這個物件
        for fn in (C.waiver_clause, lambda w, ln: C.waiver_sentence(w, ln),
                   lambda w, ln: C.waiver_known_line(w, 'rerun 仍 waived，不是 pass', ln),
                   lambda w, ln: C.waiver_phrase(w, 'waiver 重登', ln),
                   lambda w, ln: C.waiver_summary_text({'waiver': '', 'waiver_state': w}, ln)):
            lone, shared = C.SameLine(True), C.SameLine(True)
            C.no_results_text(shared)
            a, b = fn(ws, lone), fn(ws, shared)
            assert C.NO_RESULTS_SHORT in a and C.NO_RESULTS_SHORT not in b, (a, b)
            assert C.SameLine.RELOG in b, b
    # (d) 有結果的路徑：這些 helper 的輸出與放寬前逐字相同（給了物件也一樣）
    old, fps = {'results': 'a' * 20, 'source': 'b' * 20}, {'results': 'c' * 20, 'source': 'd' * 20}
    for policy in (C.StalePolicy(), C.StalePolicy({'results': True, 'source': False}),
                   C.StalePolicy({'results': True, 'source': True}, lagging={'V1'})):
        line = C.SameLine(policy.no_results)
        assert C.mark_clause(policy, 'reaffirmed_x') == C.mark_clause(policy, 'reaffirmed_x', line)
        assert C.fp_move_text(old, fps, policy.carry) == C.fp_move_text(old, fps, policy.carry, line=line)
        assert C.known_fp_text(policy.carry, old, fps) == C.known_fp_text(policy.carry, old, fps, line)
        assert C.NO_RESULTS_SHORT not in C.mark_clause(policy, 'reaffirmed_x', line)
    ws = C.WaiverState(WAIVER_ID, [], 'waived', True)        # 有結果、會重登
    assert ws.carries and C.waiver_clause(ws) == C.waiver_clause(ws, C.SameLine(False)) == 'waiver 重登'
    assert C.waiver_sentence(ws) == C.waiver_sentence(ws, C.SameLine(False))
    print('[regression] 規格 57（單元）：同一行的理由由第一個子句說出、後面的子句只留結論'
          f'（{len(ONCE_PHRASES)} 個片語各最多一次，「不加 reaffirmed 標記」「不重登」仍帶得到理由）；'
          '沒有 waiver 與有 waiver 兩種說法都吃這個機制；有結果的路徑與放寬前逐字相同: pass')


# (形狀, 動作) → 這一組覆蓋到的組句點（註解寫在哪一處拼出來的）
ONCE_CASES: list[tuple[str, str]] = [
    ('a', 'reorder_questions'),      # stdout 末行、known (3)：沒有 waiver 的那種
    ('a', 'move_plan'),              # stdout 的 retag＋fingerprint 行、known (3)
    ('a', 'demote_plan'),            # 同上，加 known (3) 中間那個子句
    ('a', 'promote_question'),       # stdout 的 retag＋fingerprint 行
    ('b', 'reorder_questions'),      # project-init 剛建好、有 goals 快照
    ('bns', 'reorder_questions'),    # project-init 剛建好、還沒有快照
    ('c1', 'reorder_questions'),     # 決策 (3)：檔名那句＋標記那句；步驟紀錄的 validation note
    ('c1', 'reassign_question'),     # 決策 (4)：標記那句＋指紋那句；檔頭 (3)(4) 同一行
    ('c1', 'promote_question'),      # 檔頭 goals 那一行：檔名那句＋waiver 短句
    ('c1', 'demote_plan'),           # 決策 (3)：標記那句＋指紋那句
    ('c2', 'reorder_questions'),     # 有 waiver 決策的 known (3) 與 stdout
    ('c3', 'reassign_question'),     # 有 waiver 決策的檔頭 (3)(4) 同一行
    ('c3', 'move_plan'),             # 決策 (4)＋步驟紀錄 note（有 waiver 的形狀）
]
# 每支動作第一次出現時也跑一次 dry-run：stdout 的摘要是 dry 與 apply 共用的那一份
ONCE_DRY = tuple(dict.fromkeys(a for _f, a in ONCE_CASES))


def test_no_results_once_per_line(tmp: Path, only: tuple[str, ...] = ()) -> None:
    """規格 57：尚無正式結果的五支動作，每一處呈現的同一行都不把同一個理由講兩次。

    形狀：(a) study-design、(b) project-init 有快照、(bns) project-init 沒快照、
    (c1) 留 validation.yaml、(c2) 留 rerun waived＋waiver 決策、(c3) 兩者都留。
    呈現：dry-run stdout、`--apply` stdout、決策三欄、步驟紀錄的 note 與 warnings、
    validation.yaml 本次寫入的行與檔頭區塊、本次封出來的新 plan。
    """
    cases = [c for c in ONCE_CASES if not only or f'{c[0]}/{c[1]}' in only]
    assert cases, only
    done, dry_done = [], set()
    for fx, action in cases:
        key = f'{fx}/{action}'
        script, args = ACTIONS[action]
        if fx in ('b', 'bns'):
            root = _fx_project_init(tmp, f'once_{fx}__{action}', snapshot=(fx == 'b'))
            args = ['--list', 'sub_questions', '--order', ','.join(reversed(INIT_QIDS))]
        else:
            root = _fx_no_results(tmp, f'once_{fx}__{action}', validation=fx in ('c1', 'c3'),
                                  keep_rerun=fx in ('c2', 'c3'))
        waiver = _waiver_of(root)
        assert bool(waiver) == (fx in ('c2', 'c3')), f'{key}：形狀沒造對（waiver={waiver!r}）'
        if action in ONCE_DRY and action not in dry_done:
            rc_d, out_d = run_dry(script, root, *args)
            assert rc_d == 0, f'{key}：dry-run 失敗 rc={rc_d}\n{out_d[-2000:]}'
            _assert_once_per_line(f'{key}（dry-run stdout）', {'stdout': out_d})
            dry_done.add(action)
        rc, out = run_action(script, root, *args)
        assert rc == 0, f'{key}：動作沒完成 rc={rc}\n{out[-2000:]}'
        sources = _no_results_sources(root, out)
        hdr = _validation_header_block(root)
        if hdr:
            sources['validation.yaml 檔頭區塊'] = hdr
        assert bool(hdr) == (fx in ('c1', 'c3')), f'{key}：檔頭區塊收得不對（留著 validation.yaml 才有）'
        for where in ('決策', 'known_consequences', 'stdout', '步驟紀錄'):
            assert C.NO_RESULTS_SHORT in sources[where], \
                f'{key}／{where} 一個字都沒說這個專案尚無正式結果\n{sources[where][:900]}'
        _assert_once_per_line(key, sources)
        _assert_waiver_and_dups(key, sources, waiver)
        done.append(key)
        shutil.rmtree(root)
    if only:
        print(f'[regression] 規格 57（{"／".join(done)}）: pass')
        return
    print(f'[regression] 規格 57：{len(done)} 組（形狀 × 動作）、{len(dry_done)} 支動作的 dry-run——'
          'dry-run 與 apply 的 stdout、決策三欄、步驟紀錄的 note 與 warnings、validation.yaml 本次寫入與檔頭，'
          f'每一行的 {len(ONCE_PHRASES)} 個片語各最多一次；含「不加 reaffirmed 標記」「不重登」的行'
          '同一行仍看得到「尚無正式結果」: pass')


# ======================================================================
# 規格 58～59：編號對照表的定位、決策第 (7) 項照實寫
# ======================================================================

# 虛構的對照表零件（編號、題材與備註全是編出來的）
G_HEAD = '| 代號 | 分類 | 說明 |\n| :-- | :-- | :-- |'
G_MAIN = '| SQ6、SQ7 | 主子問題 | 備註 |'
G_AQ7 = '| AQ7 | 附錄問題 | 附錄甲；列在附錄，不計入主問題覆蓋 |'
G_AQ8 = '| AQ8 | 附錄問題 | 附錄乙；列在附錄，不計入主問題覆蓋 |'
G_AQ9B = '| AQ9b | 附錄問題 | 附錄丙；列在附錄，不計入主問題覆蓋 |'
G_DID = '| D-' + '900… | 記錄編號 | 逐條追加 |'
# 別張表也把第三格寫成「主子問題」，但第二格不是編號清單（題材刻意與問題無關）
G_DECOY = ['| 代號 | 分類 | 說明 |', '| :-- | :-- | :-- |', '| 合金硬度 | 主子問題 | 另一張表的用法 |', '']
# code fence 裡的範例列與註解：形狀像，但一行都不算
G_FENCE = ['```markdown', '| SQ8 | 主子問題 | 範例 |', '# 註解', '```', '']


def _g_doc(rows: list[str], *, heading: str = '## 對照', decoy=(), lead=(), tail=()) -> str:
    """組一份詞彙表：heading 是表格上方最近的標題，decoy 擺在前一節，lead 擺在同一節的表格之前。"""
    return '\n'.join(['# 詞彙', '', '## 說明', '', '一段跟對照表無關的文字。', '', *decoy,
                      heading, '', *lead, G_HEAD, *rows, '', *tail, ''])


def _g_reassign(RQ, text: str, *, src: str = 'SQ7', to: str = 'AQ9') -> tuple[str, dict]:
    return RQ.update_glossary(text, src, to, 'D-' + '900', DATE, ['SQ6'], '問題甲', f'{src}-v1', f'{to}-v1',
                              'M9', ['k9'], ['V99'], '')


def _g_promote(PQ, text: str, *, src: str = 'AQ7', to: str = 'SQ9') -> tuple[str, dict]:
    return PQ.update_glossary(text, src, to, 'D-' + '910', DATE, ['SQ6', 'SQ9'])


# (名稱, 文件, 節起點那一行, 主子問題列（None＝沒有）, 新列要插在這一列之後, 略過原因（''＝不略過）)
GLOSSARY_LOCATE: list[tuple[str, str, str, str | None, str, str]] = [
    ('plain', _g_doc([G_MAIN, G_AQ8, G_AQ7, G_DID], tail=['## 其他', '', '文字。']),
     '## 對照', G_MAIN, G_AQ7, ''),
    # 前一節有別張表也寫「主子問題」：定位不得被它拉走（第二格不是編號清單）
    ('decoy_table', _g_doc([G_MAIN, G_AQ7, G_DID], decoy=G_DECOY, tail=['## 其他']),
     '## 對照', G_MAIN, G_AQ7, ''),
    # 只有 AQ 列的表：以第一個 AQ 錨點列定位，主子問題列回 -1
    ('aq_only', _g_doc([G_AQ8, G_AQ7, G_DID], tail=['## 其他']),
     '## 對照', None, G_AQ7, ''),
    ('fence', _g_doc([G_MAIN, G_AQ7, G_DID], lead=G_FENCE, tail=['## 其他']),
     '## 對照', G_MAIN, G_AQ7, ''),
    ('setext', _g_doc([G_MAIN, G_AQ7, G_DID], heading='對照\n----', tail=['## 其他']),
     '對照', G_MAIN, G_AQ7, ''),
    # 節尾是一級標題：節外那一列 AQ 不算，新列要留在節內
    ('next_h1', _g_doc([G_MAIN, G_AQ7, G_DID], tail=['# 一級', '', G_AQ8]),
     '## 對照', G_MAIN, G_AQ7, ''),
    ('suffix', _g_doc(['| SQ8b | 主子問題 | 備註 |', G_AQ7, G_AQ9B, G_DID], tail=['## 其他']),
     '## 對照', '| SQ8b | 主子問題 | 備註 |', G_AQ9B, ''),
    ('empty_main', _g_doc(['| （無） | 主子問題 | 備註 |', G_AQ7, G_DID], tail=['## 其他']),
     '## 對照', '| （無） | 主子問題 | 備註 |', G_AQ7, ''),
    # 主子問題列不只一列（逐題一列的表）：不猜要改哪一列
    ('two_main', _g_doc([G_MAIN, '| SQ8 | 主子問題 | 逐題一列 |', G_AQ7, G_DID], tail=['## 其他']),
     '', None, '', C.GLOSSARY_MANY_MAIN),
    ('no_table', _g_doc([G_DID], tail=['## 其他']), '', None, '', C.GLOSSARY_NO_TABLE),
]


def test_glossary_locate() -> None:
    """規格 58：編號對照表的定位只看形狀——別張表、fence 裡的範例、逐題一列的表都不會改錯。

    每一案都真的跑一次兩支動作的 `update_glossary`，比對改到的是哪幾行。
    """
    RQ = _load_script('skills/status/scripts/reassign_question.py')
    PQ = _load_script('skills/status/scripts/promote_question.py')
    done = []
    for name, text, head_row, main_row, after_row, skip in GLOSSARY_LOCATE:
        lines = text.split('\n')
        got = C.glossary_table(lines)
        if skip:
            assert got == (-1, -1, -1, -1), (name, got)
            for out, info in (_g_reassign(RQ, text), _g_promote(PQ, text)):
                assert out == text, f'{name}：定位不到卻動了文件'
                assert info == {'skipped': skip}, (name, info)
            done.append(name)
            continue
        sec, sec_end, main_i, last_aq = got
        assert lines[sec] == head_row, (name, lines[sec])
        assert (lines[main_i] if main_i >= 0 else None) == main_row, (name, main_i)
        assert lines[last_aq] == after_row and sec < last_aq < sec_end, (name, lines[last_aq], sec, sec_end)
        # reassign：新列插在節內最後一個 AQ 列之後，其餘只差主子問題列那一行
        out, info = _g_reassign(RQ, text)
        after = out.split('\n')
        i_ins = lines.index(after_row) + 1
        assert after[i_ins].startswith('| AQ9 | 附錄問題 |'), (name, after[i_ins])
        rest = after[:i_ins] + after[i_ins + 1:]
        assert len(rest) == len(lines), (name, len(rest), len(lines))
        touched = [i for i, (x, y) in enumerate(zip(rest, lines)) if x != y]
        assert touched == ([lines.index(main_row)] if main_row else []), (name, touched)
        assert info['changed'] == (['主子問題列', 'AQ9 列'] if main_row else ['AQ9 列']), (name, info)
        # promote：來源列加註、主子問題列加回，一列都不新增
        out2, info2 = _g_promote(PQ, text)
        after2 = out2.split('\n')
        assert len(after2) == len(lines), (name, len(after2), len(lines))
        want = sorted([lines.index(G_AQ7)] + ([lines.index(main_row)] if main_row else []))
        touched2 = sorted(i for i, (x, y) in enumerate(zip(after2, lines)) if x != y)
        assert touched2 == want, (name, touched2, want)
        assert info2['changed'] == (['主子問題列', 'AQ7 列'] if main_row else ['AQ7 列']), (name, info2)
        done.append(name)
    # 備註裡已經有帶後綴字母的「降為 AQ9b」：新子句插在它之後（後綴字母不收就會插進編號中間）
    note = 'SQ8 已依 D-' + '910' + ' 降為 AQ9b，編號不重用'
    out, _info = _g_reassign(RQ, _g_doc([f'| SQ6、SQ7 | 主子問題 | {note} |', G_AQ7], tail=['## 其他']))
    row = next(ln for ln in out.split('\n') if ln.startswith('| SQ6 |'))
    assert row == ('| SQ6 | 主子問題 | SQ8 已依 D-' + '910' + ' 降為 AQ9b、SQ7 已依 D-' + '900'
                   + f'（{DATE}）降為 AQ9，編號不重用；舊紀錄的「SQ7」即指 AQ9 |'), row
    # 只有 AQ 列、而且那一列不是來源列：promote 一列都改不到，照實回略過（不得寫成「更新」）
    plain = _g_doc([G_AQ8, G_DID], tail=['## 其他'])
    out, info = _g_promote(PQ, plain)
    assert out == plain and 'AQ7' in str(info.get('skipped')), info
    print(f'[regression] 規格 58：{len(done)} 案（{"／".join(done)}）定位只看形狀——'
          'code fence 裡的範例列與註解不算、setext 標題與任意層級的節尾、後綴字母編號、'
          '只有 AQ 列時以 AQ 錨點定位、主子問題列不只一列就不猜: pass')


# 決策第 (7) 項的四種實況；`part` 的表只有 AQ 列、`many` 的表有兩列主子問題列
G7_PART_TABLE = _g_doc(['| AQ1 | 附錄問題 | 附錄甲；列在附錄，不計入主問題覆蓋 |', G_DID], tail=['## 其他'])
G7_MANY_TABLE = _g_doc([G_MAIN, '| SQ8 | 主子問題 | 逐題一列 |',
                        '| AQ1 | 附錄問題 | 附錄甲；列在附錄，不計入主問題覆蓋 |', G_DID], tail=['## 其他'])
G7_ARGS = {'reassign_question': ['--from', 'SQ2', '--to', 'AQ9'],
           'promote_question': ['--from', 'AQ1', '--to', 'SQ9']}
# (形狀, 動作, 要不要用「尚無正式結果」的 fixture)
G7_CASES: list[tuple[str, str, bool]] = [
    ('both', 'reassign_question', False), ('part', 'reassign_question', False),
    ('none', 'reassign_question', True), ('many', 'reassign_question', False),
    ('both', 'promote_question', False), ('part', 'promote_question', True),
    ('none', 'promote_question', False), ('many', 'promote_question', True),
]
# 這一句實際上該長什麼樣：`both` 與基底逐位元相同（有 GLOSSARY.md 的專案決策不得變）
G7_WANT = {
    ('both', 'reassign_question'): '(7) GLOSSARY.md 編號對照表：主子問題列改「SQ1」、補 AQ9 一列',
    ('part', 'reassign_question'): '(7) GLOSSARY.md 編號對照表：補 AQ9 一列',
    ('both', 'promote_question'): '(7) GLOSSARY.md 編號對照表：主子問題列加回 SQ9、AQ1 列註明已升回',
    ('part', 'promote_question'): '(7) GLOSSARY.md 編號對照表：AQ1 列註明已升回',
}
# 第 7 步的步驟紀錄該寫什麼：決策與它說的要是同一件事
G7_NOTE = {('both', 'reassign_question'): '更新 主子問題列、AQ9 列',
           ('part', 'reassign_question'): '更新 AQ9 列',
           ('both', 'promote_question'): '更新 主子問題列、AQ1 列',
           ('part', 'promote_question'): '更新 AQ1 列'}


def _g7_forbid(shape: str, action: str) -> tuple[str, ...]:
    """沒改到的部分不准在那一句裡出現的說法。"""
    if shape in ('none', 'many'):
        return ('主子問題列改', '主子問題列加回', '列註明已升回', '補 ')
    if shape == 'part':
        return ('主子問題列改', '主子問題列加回') + (('補 ',) if action == 'promote_question' else ())
    return ()


def _step_notes(root: Path, out: str, step_no: int) -> list[str]:
    """步驟紀錄裡某一步的 note。"""
    m = re.search(r'run log (\S+)', out)
    assert m, out[-600:]
    doc = json.loads((root / m.group(1)).read_text(encoding='utf-8'))
    step = next(s for s in doc['steps'] if s.get('step') == step_no)
    return [str(n) for n in (step.get('notes') or [])]


def _decision_of(root: Path, out: str) -> dict:
    """本次 append 的那一條決策。"""
    m = re.search(r'決策 (D-\d+)', out)
    assert m, out[-600:]
    return next(d for d in yaml.safe_load((root / 'decisions.yaml').read_text(encoding='utf-8'))['decisions']
                if d['id'] == m.group(1))


def test_glossary_decision_actions(tmp: Path, only: tuple[str, ...] = ()) -> None:
    """規格 59：決策第 (7) 項依第 7 步的實際結果寫，不宣稱沒發生的事。

    四種實況 × 兩支動作：兩部分都改到、只改到一部分（表裡沒有主子問題列）、
    專案沒有 GLOSSARY.md、主子問題列不只一列而略過。`only`：只跑指定的「形狀/動作」（驗牙用）。
    """
    cases = [c for c in G7_CASES if not only or f'{c[0]}/{c[1]}' in only]
    assert cases, only
    done = []
    for shape, action, no_results in cases:
        key = f'{shape}/{action}'
        script, _default = ACTIONS[action]
        name = f'g7_{shape}__{action}'
        root = _fx_no_results(tmp, name) if no_results else copy_fixture(tmp, name)
        g_path = root / 'GLOSSARY.md'
        if shape == 'none':
            g_path.unlink()
        elif shape == 'part':
            g_path.write_text(G7_PART_TABLE, encoding='utf-8')
        elif shape == 'many':
            g_path.write_text(G7_MANY_TABLE, encoding='utf-8')
        before = g_path.read_bytes() if g_path.exists() else b''
        rc, out = run_action(script, root, *G7_ARGS[action])
        assert rc == 0, f'{key}：動作沒完成 rc={rc}\n{out[-2000:]}'
        line = next(ln for ln in str(_decision_of(root, out)['decision']).split('\n') if ln.startswith('(7) '))
        notes = _step_notes(root, out, 7)
        if shape in ('both', 'part'):
            assert line == G7_WANT[(shape, action)], f'{key}：第 (7) 項寫成\n{line}'
            assert notes == [G7_NOTE[(shape, action)]], (key, notes)
            assert (root / f'backups/GLOSSARY.md.pre_{G7_ARGS[action][1].lower()}_to_'
                    f'{G7_ARGS[action][3].lower()}_backup').is_file(), f'{key}：改了檔卻沒有備份'
        else:
            # 沒寫檔：決策與步驟紀錄都說未更新，而且一個備份都沒留
            want_note = ('無 GLOSSARY.md，略過；可用 init_glossary.py 依範本建立' if shape == 'none'
                         else f'WARNING 略過：{C.GLOSSARY_MANY_MAIN}')
            assert notes == [want_note], (key, notes)
            assert '未更新' in line, f'{key}：第 (7) 項沒說未更新\n{line}'
            if shape == 'none':
                assert line == ('(7) GLOSSARY.md：專案沒有這個檔，編號對照表未更新'
                                '（可用 init_glossary.py 依範本建立）'), line
                assert not g_path.exists(), f'{key}：動作把 GLOSSARY.md 建出來了'
            else:
                assert line == f'(7) {C.GLOSSARY_REL} 編號對照表未更新：{C.GLOSSARY_MANY_MAIN}', line
                assert C.GLOSSARY_MANY_MAIN in want_note and g_path.read_bytes() == before, f'{key}：略過卻改了檔'
            assert not list((root / 'backups').glob('GLOSSARY.md*')), f'{key}：沒寫檔卻留了備份'
        for bad in _g7_forbid(shape, action):
            assert bad not in line, f'{key}：第 (7) 項寫了沒做的「{bad}」\n{line}'
        if no_results:
            # 這次的改動不得把「尚無正式結果」的兩條規則弄壞（同一行只說一次、waiver 照實）
            sources = _no_results_sources(root, out)
            hdr = _validation_header_block(root)
            if hdr:
                sources['validation.yaml 檔頭區塊'] = hdr
            _assert_once_per_line(key, sources)
            _assert_waiver_and_dups(key, sources, _waiver_of(root))
        done.append(key)
        shutil.rmtree(root)
    if only:
        print(f'[regression] 規格 59（{"／".join(done)}）: pass')
        return
    print(f'[regression] 規格 59：{len(done)} 組（實況 × 動作）——兩部分都改到時與基底逐位元相同、'
          '只改到一部分只寫那一部分、沒有 GLOSSARY.md 與略過都寫未更新且不留備份，'
          '決策與第 7 步的步驟紀錄說同一件事: pass')


def test_glossary_decision_units() -> None:
    """規格 59（單元）：第 (7) 項的四種實況只由 `glossary_decision_text()` 組，兩支動作不各自拼。"""
    parts = {'主子問題列': '主子問題列改「SQ6」', 'AQ9 列': '補 AQ9 一列'}
    both = C.glossary_decision_text({'changed': ['主子問題列', 'AQ9 列']}, parts)
    assert both == '(7) GLOSSARY.md 編號對照表：主子問題列改「SQ6」、補 AQ9 一列', both
    one = C.glossary_decision_text({'changed': ['AQ9 列']}, parts)
    assert one == '(7) GLOSSARY.md 編號對照表：補 AQ9 一列', one
    head = C.glossary_decision_text({'changed': ['主子問題列']}, parts)
    assert head == '(7) GLOSSARY.md 編號對照表：主子問題列改「SQ6」', head
    missing = C.glossary_decision_text(None, parts)
    assert missing == '(7) GLOSSARY.md：專案沒有這個檔，編號對照表未更新（可用 init_glossary.py 依範本建立）', missing
    for reason in (C.GLOSSARY_NO_TABLE, C.GLOSSARY_MANY_MAIN):
        got = C.glossary_decision_text({'skipped': reason}, parts)
        assert got == f'(7) GLOSSARY.md 編號對照表未更新：{reason}', got
        for bad in ('主子問題列改', '補 AQ9 一列'):
            assert bad not in got, (got, bad)
    for bad in ('主子問題列改', '補 AQ9 一列'):
        assert bad not in missing, (missing, bad)
    assert '主子問題列' not in one and '補 ' not in head, (one, head)
    print('[regression] 規格 59（單元）：第 (7) 項四種實況各一句——兩部分、只有一部分、'
          '沒有這個檔、略過（原因字串與步驟紀錄同一個）: pass')


# ======================================================================
# 規格 60～65：每個專案都有 GLOSSARY.md
# ======================================================================

IG = 'init_glossary.py'
# 這支只管「有沒有這份文件」，不碰結果、驗證、指紋與 waiver，所以它寫的字裡一個都不准出現這些
IG_FORBID = ('fingerprint', '指紋', 'waiver', 'reaffirmed', '尚無正式結果')
# 乾淨 fixture 的 goals 長這樣 → 工具該產出的三列（主子問題一列、附錄問題各一列）
IG_WANT_ROWS = [f'| SQ1、SQ2 | {C.GLOSSARY_MAIN_CELL} |  |',
                f'| AQ1 | {C.GLOSSARY_AQ_CELL} | 附錄問題一 |',
                f'| AQ2 | {C.GLOSSARY_AQ_CELL} | 附錄問題二 |']
IG_TABLE_HEAD = '## 編號對照表'


def _ig_template() -> str:
    return (PLUGIN / GT_REL).read_text(encoding='utf-8')


def _ig_rows(root: Path) -> list[str]:
    """`glossary_rows` 在這個專案的 GLOSSARY.md 裡認得的那幾列（工具產的表，自己的定位要認得）。"""
    lines = (root / C.GLOSSARY_REL).read_text(encoding='utf-8').split('\n')
    main_rows, aq_rows = C.glossary_rows(lines)
    return [lines[i] for i in sorted(main_rows + aq_rows)]


def _ig_dids(root: Path) -> list[str]:
    path = root / 'decisions.yaml'
    if not path.is_file():
        return []
    doc = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    return [str(d.get('id')) for d in (doc.get('decisions') or [])]


def _ig_texts(root: Path, out: str) -> dict[str, str]:
    """init_glossary 寫出來、會被人讀到的每一處文字：stdout、步驟紀錄、決策全欄。"""
    sources = {'stdout': out, '步驟紀錄': _run_log_text(root, out)}
    did = re.search(r'決策 (D-\d+)', out)
    if did:
        entry = next(d for d in yaml.safe_load((root / 'decisions.yaml').read_text(encoding='utf-8'))['decisions']
                     if d['id'] == did.group(1))
        sources['決策'] = '\n'.join(str(entry.get(f) or '') for f in C.DECISION_FIELDS)
    return sources


def _ig_no_forbidden(key: str, sources: dict[str, str]) -> None:
    for where, text in sources.items():
        for bad in IG_FORBID:
            assert bad not in text, f'{key}：{where} 提到了這支不碰的「{bad}」\n{text[:600]}'


def _tree_stamp(root: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file()}


def _ig_fp(root: Path):
    """現在量得到的 rerun 指紋；這個形狀量不到就回 None（量不到的專案前後都該量不到）。"""
    try:
        return C.fingerprint_only(root)
    except C.ChainError:
        return None


def _ig_decisions_clean(key: str, root: Path) -> None:
    """check_decisions 對本次這筆沒話說（判準同 `check_decisions_gate`：BLOCKER／WARNING 提到它就算有）。"""
    rc, out = C.run_script('check_decisions', *C.decisions_argv(root))
    did = _ig_dids(root)[-1]
    bad = [ln for ln in out.splitlines() if ln.startswith(('BLOCKER', 'WARNING')) and did in ln]
    assert rc == 0 and not bad, f'{key}：check_decisions rc={rc}、對 {did} 有話說 {bad}\n{out[-600:]}'


def _ig_units(tmp: Path) -> None:
    """`{{ID_ROWS}}` 的單元面：後綴字母、`|` 與換行、goals 空、goals 以外的頂層鍵不寫。"""
    IGM = _load_script(IG_REL)
    d = tmp / 'ig_units'
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    (d / 'project.yaml').write_text(
        'goals:\n'
        '  sub_questions:\n'
        '    - id: SQ6b\n      question: "子問題甲"\n'
        '    - id: SQ7\n      question: "子問題乙"\n'
        '  appendix_questions:\n'
        '    - id: AQ7b\n      question: "含一根 | 豎線\\n與換行的問法"\n'
        '    - id: AQ8\n      question: "附錄乙"\n'
        'other_questions:\n'
        '    - id: SQ9\n      question: "別的頂層鍵"\n', encoding='utf-8')
    rows, ids = IGM.id_rows(d)
    lines = rows.split('\n')
    assert lines[0] == f'| SQ6b、SQ7 | {C.GLOSSARY_MAIN_CELL} |  |', lines[0]
    assert lines[1] == rf'| AQ7b | {C.GLOSSARY_AQ_CELL} | 含一根 \| 豎線 與換行的問法 |', lines[1]
    assert lines[2] == f'| AQ8 | {C.GLOSSARY_AQ_CELL} | 附錄乙 |', lines[2]
    assert len(lines) == 3 and 'SQ9' not in rows, rows
    assert ids == {'sub_questions': ['SQ6b', 'SQ7'], 'appendix_questions': ['AQ7b', 'AQ8']}, ids
    assert C.glossary_rows(lines) == ([0], [1, 2]), C.glossary_rows(lines)
    # goals 空：主子問題列寫「（無）」，而且那一列照樣認得出來
    (d / 'project.yaml').write_text('goals:\n  sub_questions: []\n  appendix_questions: []\n', encoding='utf-8')
    rows, ids = IGM.id_rows(d)
    assert rows == f'| {C.GLOSSARY_EMPTY_Q} | {C.GLOSSARY_MAIN_CELL} |  |', rows
    assert ids == {'sub_questions': [], 'appendix_questions': []}, ids
    assert C.glossary_rows(rows.split('\n')) == ([0], []), C.glossary_rows(rows.split('\n'))
    # 範本本身一列編號都沒有 → 剛建好的空範本會被判成「對照表還沒有編號列」
    assert C.glossary_rows(_ig_template().split('\n')) == ([], []), '範本自己就帶編號列'


def test_init_glossary_states(tmp: Path) -> None:
    """規格 60：三種現況各走一條路——沒有檔依範本建、對照表空著只追加、已經有編號列就什麼都不做。

    工具產的表要能被 `glossary_rows` 認得（否則兩支動作改不到），既有內容一律不覆寫，重跑第二次零寫入。
    """
    _ig_units(tmp)
    tpl = _ig_template()
    # (a) 沒有這個檔 → 依範本建立；順便確認它不動 rerun 指紋
    root = copy_fixture(tmp, 'ig_create')
    (root / C.GLOSSARY_REL).unlink()
    fp0 = _ig_fp(root)
    base_dids = _ig_dids(root)
    want_did = C.next_decision_id(root)
    rc, out = run_action(IG, root)
    assert rc == 0, f'建立失敗 rc={rc}\n{out[-2000:]}'
    assert (root / C.GLOSSARY_REL).read_text(encoding='utf-8') == tpl.replace('{{ID_ROWS}}', '\n'.join(IG_WANT_ROWS))
    assert _ig_rows(root) == IG_WANT_ROWS, _ig_rows(root)
    assert _ig_dids(root) == base_dids + [want_did], _ig_dids(root)
    _ig_no_forbidden('建立', _ig_texts(root, out))
    assert _ig_fp(root) == fp0 and fp0 is not None, 'init_glossary 改掉了 rerun 指紋'
    _ig_decisions_clean('建立', root)
    # 第二次：走「已經有編號列」那一列——零寫入、不記決策、也不印決策與步驟紀錄
    stamp = _tree_stamp(root)
    rc2, out2 = run_action(IG, root)
    assert rc2 == 0, out2[-1200:]
    assert _tree_stamp(root) == stamp, '第二次改了檔'
    assert '決策 D-' not in out2 and 'run log' not in out2, out2
    assert '不寫任何檔、不記決策' in out2, out2
    # (b) 有檔、對照表還是空的 → 只追加對照表那一節，既有內容逐位元保留
    root = copy_fixture(tmp, 'ig_append')
    old = '# 我們的術語\n\n## 縮寫\n\n| 縮寫 | 全稱 |\n|---|---|\n| ABC | 甲乙丙 |\n'
    (root / C.GLOSSARY_REL).write_text(old, encoding='utf-8')
    rc, out = run_action(IG, root)
    assert rc == 0, f'追加失敗 rc={rc}\n{out[-2000:]}'
    new = (root / C.GLOSSARY_REL).read_text(encoding='utf-8')
    tail = tpl[tpl.index(IG_TABLE_HEAD):].replace('{{ID_ROWS}}', '\n'.join(IG_WANT_ROWS))
    assert new == old + '\n' + tail, repr(new[len(old):][:120])
    assert new.startswith(old) and '| ABC | 甲乙丙 |' in new, '既有內容沒有逐位元保留'
    assert _ig_rows(root) == IG_WANT_ROWS, _ig_rows(root)
    line1 = str(_decision_of(root, out)['decision']).split('\n')[0]
    assert '只在檔尾追加' in line1 and '既有內容一個位元都沒改' in line1, line1
    assert '依範本' not in line1 and '新建' not in line1, line1
    _ig_no_forbidden('追加', _ig_texts(root, out))
    assert (root / f'backups/{C.GLOSSARY_REL}.pre_init_glossary_{DATE.replace("-", "")}_backup').is_file()
    # (c) fixture 自帶的對照表（run_v0160 的 GLOSSARY）已經有編號列 → 不寫、不記決策
    root = copy_fixture(tmp, 'ig_skip')
    stamp = _tree_stamp(root)
    rc, out = run_action(IG, root)
    assert rc == 0, out[-1200:]
    assert _tree_stamp(root) == stamp, '已經有編號列卻改了檔'
    assert '決策 D-' not in out and C.GLOSSARY_MANY_MAIN not in out, out
    print('[regression] 規格 60：三種現況——沒有檔依範本建（四段、對照表三列、check_decisions 乾淨、指紋不動）、'
          '對照表空著只追加一節（既有內容逐位元）、已經有編號列零寫入零決策；'
          '`{{ID_ROWS}}` 收後綴字母、轉義 `|`、壓單行、goals 空寫（無）、goals 以外的鍵不寫: pass')


def test_init_glossary_guards(tmp: Path) -> None:
    """規格 61：護欄——dry-run 零寫入、token 不符拒絕、dry-run 之後才冒出來的檔不被蓋掉、鏈中失敗全還原。"""
    IGM = _load_script(IG_REL)
    # dry-run：整棵樹逐位元不動，檔也沒被建出來
    root = copy_fixture(tmp, 'ig_dry')
    (root / C.GLOSSARY_REL).unlink()
    stamp = _tree_stamp(root)
    rc, out = run_dry(IG, root)
    assert rc == 0, out[-1200:]
    assert _tree_stamp(root) == stamp, f'dry-run 改了檔 {sorted(set(_tree_stamp(root)) ^ set(stamp))[:5]}'
    assert not (root / C.GLOSSARY_REL).exists(), 'dry-run 把檔建出來了'
    token = re.search(r'token: (\S+)', out).group(1)
    rc, bad = run_action(IG, root, '--expect-token', token[:-1] + ('0' if token[-1] != '0' else '1'))
    assert rc == 2 and 'token 不符' in bad, (rc, bad[-400:])
    assert not (root / C.GLOSSARY_REL).exists(), 'token 不符卻寫了檔'
    # dry-run 之後才冒出來的檔：GLOSSARY.md 不在 TOKEN_FILES，token 擋不住，只有重新判斷才不會蓋掉它
    planted = _g_doc([G_MAIN, G_AQ7, G_DID], tail=['## 其他'])
    (root / C.GLOSSARY_REL).write_text(planted, encoding='utf-8')
    dids = _ig_dids(root)
    rc, out = run_action(IG, root, '--expect-token', token)
    assert rc == 0, out[-1200:]
    assert (root / C.GLOSSARY_REL).read_text(encoding='utf-8') == planted, 'dry-run 之後冒出來的檔被蓋掉了'
    assert _ig_dids(root) == dids and '決策 D-' not in out, (out[-400:], _ig_dids(root))
    # 同一件事在鏈裡再擋一層：ctx 說要建、檔案現況卻已經有編號列 → 一個位元都不改
    ctx = {'state': 'create', 'why': '專案還沒有這個檔', 'rows': '\n'.join(IG_WANT_ROWS),
           'ids': {'sub_questions': ['SQ1'], 'appendix_questions': []}, 'sections': ['縮寫']}
    stamp = _tree_stamp(root)
    args = IGM.argparse.Namespace(reason='', daily_log='', date=DATE)
    try:
        IGM.run_chain(root, args, ctx, 'D-' + '910', DATE, False)
        raise AssertionError('鏈沒有重新判斷檔案現況')
    except C.ChainError as exc:
        assert '已經不是 dry-run 當時那樣' in str(exc), str(exc)[:300]
    assert _tree_stamp(root) == stamp, '重新判斷之後還是改了檔'
    # 鏈中失敗（decisions.yaml 唯讀）：新建的 GLOSSARY.md 刪掉、decisions.yaml 逐位元
    root = copy_fixture(tmp, 'ig_fail')
    (root / C.GLOSSARY_REL).unlink()
    dec0 = (root / 'decisions.yaml').read_bytes()
    os.chmod(root / 'decisions.yaml', 0o444)
    try:
        rc, out = run_action(IG, root)
    finally:
        os.chmod(root / 'decisions.yaml', 0o644)
    assert rc == 1, (rc, out[-900:])
    assert not (root / C.GLOSSARY_REL).exists(), '失敗了卻把新建的 GLOSSARY.md 留著'
    assert (root / 'decisions.yaml').read_bytes() == dec0, 'decisions.yaml 沒有還原'
    print('[regression] 規格 61：dry-run 整棵樹零寫入、token 不符 exit 2 不寫檔、'
          'dry-run 之後才冒出來的檔不被蓋掉（入口與鏈各擋一層）、鏈中失敗把新建的檔刪掉且既有檔還原: pass')


def test_init_glossary_fresh(tmp: Path) -> None:
    """規格 62：project-init 剛建好的形狀（有快照與沒快照）照樣完成，而且不提它不碰的那些東西。"""
    done = []
    for snapshot in (True, False):
        key = f'snapshot={snapshot}'
        root = _fx_project_init(tmp, f'ig_fresh_{snapshot}', snapshot=snapshot)
        assert not (root / C.GLOSSARY_REL).exists(), 'project-init 形狀不該已經有 GLOSSARY.md'
        assert _ig_fp(root) is None, f'{key}：這個形狀動作前本來就量不到指紋'
        rc, out = run_action(IG, root)
        assert rc == 0, f'{key}：rc={rc}\n{out[-2000:]}'
        assert (root / C.GLOSSARY_REL).is_file(), f'{key}：沒建出檔'
        assert _ig_rows(root) == [f'| {"、".join(INIT_QIDS)} | {C.GLOSSARY_MAIN_CELL} |  |'], _ig_rows(root)
        assert _ig_dids(root) == [INIT_DID, 'D-' + '901'], _ig_dids(root)
        _ig_no_forbidden(key, _ig_texts(root, out))
        _ig_decisions_clean(key, root)
        assert _ig_fp(root) is None, f'{key}：這個形狀本來量不到指紋'
        assert not (root / 'analysis/results.json').exists() and not (root / 'analysis/validation.yaml').exists()
        done.append(key)
    # 沒有 decisions.yaml 的專案：由 append_decision 建檔
    root = _fx_project_init(tmp, 'ig_fresh_nodec')
    (root / 'decisions.yaml').unlink()
    rc, out = run_action(IG, root)
    assert rc == 0, f'無 decisions.yaml：rc={rc}\n{out[-2000:]}'
    assert _ig_dids(root) == ['D-' + '001'], _ig_dids(root)
    _ig_no_forbidden('無 decisions.yaml', _ig_texts(root, out))
    print(f'[regression] 規格 62：project-init 形狀（{"／".join(done)}）與沒有 decisions.yaml 的專案都 rc=0——'
          '建出檔、記一筆決策、check_decisions 乾淨，文字不提結果、驗證、指紋與 waiver: pass')


# 端到端：(fixture 名稱, 要不要用「尚無正式結果」的 fixture)
IG_E2E: list[tuple[str, bool]] = [('有結果', False), ('尚無正式結果', True)]


def test_init_glossary_end_to_end(tmp: Path, only: tuple[str, ...] = ()) -> None:
    """規格 63：工具自己產的表，自己的動作要認得——init_glossary → reassign_question → promote_question。

    `only`：只跑指定的 fixture（驗牙用）。
    """
    cases = [c for c in IG_E2E if not only or c[0] in only]
    assert cases, only
    done = []
    for key, no_results in cases:
        name = 'ig_e2e_' + ('nr' if no_results else 'ctl')
        root = _fx_no_results(tmp, name) if no_results else copy_fixture(tmp, name)
        (root / C.GLOSSARY_REL).unlink()          # fixture 自帶一份，先拿掉才會走「依範本建立」那一列
        rc, out = run_action(IG, root)
        assert rc == 0, f'{key}／init：rc={rc}\n{out[-2000:]}'
        assert _ig_rows(root) == IG_WANT_ROWS, (key, _ig_rows(root))
        # reassign：主子問題列少一個編號、尾端多一列 AQ9；決策第 (7) 項是「兩部分都改到」那一種
        rc, out = run_action('reassign_question.py', root, '--from', 'SQ2', '--to', 'AQ9')
        assert rc == 0, f'{key}／reassign：rc={rc}\n{out[-2500:]}'
        rows = _ig_rows(root)
        assert rows[0].startswith(f'| SQ1 | {C.GLOSSARY_MAIN_CELL} |') and 'AQ9' in rows[0], (key, rows[0])
        assert rows[-1].startswith(f'| AQ9 | {C.GLOSSARY_AQ_CELL} |'), (key, rows[-1])
        assert len(rows) == len(IG_WANT_ROWS) + 1, (key, rows)
        line = next(ln for ln in str(_decision_of(root, out)['decision']).split('\n') if ln.startswith('(7) '))
        assert line == '(7) GLOSSARY.md 編號對照表：主子問題列改「SQ1」、補 AQ9 一列', (key, line)
        if no_results:
            _ig_e2e_no_results(f'{key}／reassign', root, out)
        # promote：編號加回主子問題列、AQ9 那一列註明已升回，一列都不新增
        rc, out = run_action('promote_question.py', root, '--from', 'AQ9', '--to', 'SQ2')
        assert rc == 0, f'{key}／promote：rc={rc}\n{out[-2500:]}'
        rows2 = _ig_rows(root)
        assert len(rows2) == len(rows), (key, rows2)
        assert rows2[0].startswith(f'| SQ1、SQ2 | {C.GLOSSARY_MAIN_CELL} |') and '升回 SQ2' in rows2[0], (key, rows2[0])
        assert '升回主問題 SQ2，本列保留供追溯' in rows2[-1], (key, rows2[-1])
        line = next(ln for ln in str(_decision_of(root, out)['decision']).split('\n') if ln.startswith('(7) '))
        assert line == '(7) GLOSSARY.md 編號對照表：主子問題列加回 SQ2、AQ9 列註明已升回', (key, line)
        if no_results:
            _ig_e2e_no_results(f'{key}／promote', root, out)
        done.append(key)
        shutil.rmtree(root)
    if only:
        print(f'[regression] 規格 63（{"／".join(done)}）: pass')
        return
    # 保留 fixture 自帶的表：init_glossary 走第三列，兩支動作之後照樣改得到那張表
    root = copy_fixture(tmp, 'ig_e2e_keep')
    stamp = _tree_stamp(root)
    rc, out = run_action(IG, root)
    assert rc == 0 and _tree_stamp(root) == stamp and '決策 D-' not in out, (rc, out[-600:])
    print(f'[regression] 規格 63：{len(done)} 組（{"／".join(done)}）端到端——init_glossary 建的表，'
          'reassign_question 與 promote_question 都定位得到並改對那兩列（決策第 (7) 項是兩部分都改到那一種）；'
          '已經有表時 init_glossary 零寫入: pass')


def _ig_e2e_no_results(key: str, root: Path, out: str) -> None:
    """尚無正式結果那一組：這次改動不得把既有的兩條規則弄壞。"""
    sources = _no_results_sources(root, out)
    hdr = _validation_header_block(root)
    if hdr:
        sources['validation.yaml 檔頭區塊'] = hdr
    _assert_once_per_line(key, sources)
    _assert_waiver_and_dups(key, sources, _waiver_of(root))


def test_glossary_init_hint() -> None:
    """規格 64：沒有 GLOSSARY.md 時第 7 步的 note 與決策第 (7) 項都指出可以建一份；其他三種實況不提。"""
    assert C.GLOSSARY_MISSING_NOTE == '無 GLOSSARY.md，略過；可用 init_glossary.py 依範本建立', C.GLOSSARY_MISSING_NOTE
    parts = {'主子問題列': '主子問題列改「SQ6」', 'AQ9 列': '補 AQ9 一列'}
    missing = C.glossary_decision_text(None, parts)
    assert missing == '(7) GLOSSARY.md：專案沒有這個檔，編號對照表未更新（可用 init_glossary.py 依範本建立）', missing
    for text in (C.GLOSSARY_MISSING_NOTE, missing):
        assert 'init_glossary.py' in text, text
    others = [C.glossary_decision_text({'changed': ['主子問題列', 'AQ9 列']}, parts),
              C.glossary_decision_text({'changed': ['AQ9 列']}, parts),
              C.glossary_decision_text({'skipped': C.GLOSSARY_NO_TABLE}, parts),
              C.glossary_decision_text({'skipped': C.GLOSSARY_MANY_MAIN}, parts)]
    for text in others:
        assert 'init_glossary' not in text, f'有檔時不該提建檔：{text}'
    # 說法只有一處：兩支動作都讀共用常數，不自己拼
    for rel in ('skills/status/scripts/reassign_question.py', 'skills/status/scripts/promote_question.py'):
        src = (PLUGIN / rel).read_text(encoding='utf-8')
        assert 'C.GLOSSARY_MISSING_NOTE' in src, rel
        assert 'init_glossary' not in src, f'{rel} 自己拼了這句話'
    print('[regression] 規格 64：沒有 GLOSSARY.md 那一種的 note 與決策第 (7) 項各多一句建檔提示'
          '（兩支動作共用同一個常數），兩部分、只有一部分與兩種略過都不提: pass')


# 用得到 GLOSSARY.md 的 skill、agent 與文件 → 各自至少要提到的字
GLOSSARY_DOCS: dict[str, tuple[str, ...]] = {
    'skills/project-init/SKILL.md': ('GLOSSARY.md', 'init_glossary.py'),
    'skills/status/SKILL.md': ('GLOSSARY.md', 'init_glossary.py'),
    'skills/study-design/SKILL.md': ('GLOSSARY.md', 'init_glossary.py'),
    'skills/interpret-results/SKILL.md': ('GLOSSARY.md', 'init_glossary.py'),
    'skills/write-manuscript/SKILL.md': ('GLOSSARY.md', 'init_glossary.py'),
    'agents/research-designer.md': ('GLOSSARY.md',),
    'agents/interpreter.md': ('GLOSSARY.md',),
    'README.md': ('GLOSSARY.md', 'init_glossary.py'),
}


def test_glossary_docs() -> None:
    """規格 66：範本四段齊全、有代換記號與分工那句；用得到它的 skill、agent 與 README 都寫了。"""
    tpl = _ig_template()
    lines = tpl.split('\n')
    assert lines[0] == '# 術語表', lines[0]
    assert [ln for ln in lines if ln.startswith('## ')] == ['## 縮寫', '## 變數', '## 方法', IG_TABLE_HEAD], \
        [ln for ln in lines if ln.startswith('## ')]
    assert lines[-2] == '{{ID_ROWS}}' and tpl.count('{{ID_ROWS}}') == 1, lines[-3:]
    assert '`project.yaml` 的 `glossary`' in tpl and '定義只寫在這裡' in tpl, '範本沒寫與 glossary 的分工'
    assert '「主子問題」「附錄問題」' in tpl, '範本沒交代「類別」欄要維持哪兩個寫法'
    for rel, needles in GLOSSARY_DOCS.items():
        text = (PLUGIN / rel).read_text(encoding='utf-8')
        for needle in needles:
            assert needle in text, f'{rel} 沒提到 {needle}'
    # README 要寫出兩處的分工，不要只列檔名
    readme = (PLUGIN / 'README.md').read_text(encoding='utf-8')
    section = readme.split('### 術語表')
    assert len(section) == 2, 'README 沒有術語表那一節'
    body = section[1].split('\n### ')[0]
    for needle in ('GLOSSARY.md', 'glossary', '中英譯名', 'init_glossary.py', 'reassign_question.py'):
        assert needle in body, f'README 術語表那一節沒提到 {needle}'
    print(f'[regression] 規格 66：範本四段齊全、只有一個 {{{{ID_ROWS}}}}、分工與「類別」欄的寫法都交代了；'
          f'{len(GLOSSARY_DOCS)} 份 skill／agent／README 各自提到該提的: pass')


def test_glossary_promote_fence() -> None:
    """規格 65：promote 找來源列時跳過 code fence——節內 fence 裡的範例列不是來源列。"""
    PQ = _load_script('skills/status/scripts/promote_question.py')
    real = '| AQ7 | 附錄問題 | 真正那一列 |'
    fake = '| AQ7 | 附錄問題 | 範例 |'
    fence = ['```markdown', fake, '```', '']
    # fence 裡有、fence 外也有 → 只改 fence 外那一列
    text = _g_doc([G_MAIN, real, G_DID], lead=fence, tail=['## 其他'])
    lines = text.split('\n')
    out, info = _g_promote(PQ, text)
    after = out.split('\n')
    assert len(after) == len(lines), (len(after), len(lines))
    touched = sorted(i for i, (x, y) in enumerate(zip(after, lines)) if x != y)
    assert touched == sorted([lines.index(G_MAIN), lines.index(real)]), touched
    assert after[lines.index(fake)] == fake, after[lines.index(fake)]
    assert info['changed'] == ['主子問題列', 'AQ7 列'], info
    # fence 裡有、fence 外沒有 → 一列都不改（沒有主子問題列時照規格 58 的規則回略過）
    text2 = _g_doc([G_AQ8, G_DID], lead=fence, tail=['## 其他'])
    out2, info2 = _g_promote(PQ, text2)
    assert out2 == text2, 'fence 裡的範例列被當成來源列改掉了'
    assert 'AQ7' in str(info2.get('skipped')), info2
    print('[regression] 規格 65：promote 找來源列跳過 code fence——fence 內外都有時只改 fence 外那列，'
          '只有 fence 裡有時一列都不改: pass')


# ======================================================================
# 規格 67～71：init_glossary 的說法與判斷順序、首次建檔的檔頭、步驟紀錄的 baseline 形式
# ======================================================================

# 舊版那兩種說法：一種把使用者沒做過的裁定寫進每個專案的帳本，一種與實際寫出來的檔不符
IG_OLD_WORDING = ('每個專案都要有', '四段的表頭以外')
IG_SKIP_TAIL = '（編號對照表之後由 reassign_question.py 與 promote_question.py 維護）'
# 認不得的編號列：形狀像，但第二格不是 SQ／AQ 編號清單（題材刻意與問題無關）
IG_ODD_MAIN = f'| RQ1 | {C.GLOSSARY_MAIN_CELL} | 備註 |'


def test_init_glossary_reason_wording(tmp: Path) -> None:
    """規格 67：沒給 `--reason` 的預設理由、決策第 (1) 項的說法、project-init 第 7 步的命令。

    reason 讀完整字串（沒給與給了各一次，兩段的順序也釘住）、決策第一行讀實際字串；舊版那兩種說法
    （宣稱使用者做過的裁定、與實際寫出來的檔不符）一個字都不准再出現。
    """
    ver = _load_script(IG_REL).VERSION
    tail = f'只建文件與編號對照表，不替任何名稱填定義；由 init_glossary.py {ver} 確定性執行'
    default_head = f'使用者裁定建立 {C.GLOSSARY_REL}（未附理由）'
    create_line = (f'(1) {C.GLOSSARY_REL}：依 {GT_REL} 新建，4 段（縮寫、變數、方法、編號對照表）；'
                   '編號對照表列主子問題 SQ1、SQ2、附錄問題 AQ1、AQ2（共 3 列），縮寫、變數、方法三段只有表頭')
    append_rows = '；對照表列主子問題 SQ1、SQ2、附錄問題 AQ1、AQ2（共 3 列）'
    old_doc = '# 我們的術語\n\n## 縮寫\n\n| 縮寫 | 全稱 |\n|---|---|\n| ABC | 甲乙丙 |\n'
    cases = [('建立／沒給理由', None, (), default_head),
             ('建立／給了理由', None, ('--reason', '虛構理由一句'), '虛構理由一句'),
             ('追加／沒給理由', old_doc, (), default_head),
             ('追加／給了理由', old_doc, ('--reason', '虛構理由一句'), '虛構理由一句')]
    for i, (key, pre, extra, head) in enumerate(cases):
        root = copy_fixture(tmp, f'ig_reason_{i}')
        if pre is None:
            (root / C.GLOSSARY_REL).unlink()
        else:
            (root / C.GLOSSARY_REL).write_text(pre, encoding='utf-8')
        rc, out = run_action(IG, root, *extra)
        assert rc == 0, f'{key}：rc={rc}\n{out[-1500:]}'
        entry = _decision_of(root, out)
        assert str(entry['reason']) == f'{head}；{tail}', f'{key}：{entry["reason"]!r}'
        line1 = str(entry['decision']).split('\n')[0]
        if pre is None:
            assert line1 == create_line, f'{key}：{line1!r}'
        else:
            assert line1.startswith(f'(1) {C.GLOSSARY_REL}：只在檔尾追加「{IG_TABLE_HEAD}」一節，'
                                    '既有內容一個位元都沒改（備份 '), f'{key}：{line1!r}'
            assert line1.endswith(append_rows), f'{key}：{line1!r}'
        sources = _ig_texts(root, out)
        for where, text in sources.items():
            for bad in IG_OLD_WORDING:
                assert bad not in text, f'{key}：{where} 還留著舊說法「{bad}」\n{text[:600]}'
        _ig_no_forbidden(key, sources)
        shutil.rmtree(root)
    # project-init 第 7 步的命令要帶理由，新專案帳本裡的理由才照實
    skill = (PLUGIN / 'skills/project-init/SKILL.md').read_text(encoding='utf-8')
    cmd = [ln for ln in skill.split('\n') if 'init_glossary.py' in ln and '--apply' in ln]
    assert len(cmd) == 1, cmd
    assert '--reason "project-init 建立專案時一併建立"' in cmd[0], cmd[0]
    print(f'[regression] 規格 67：{len(cases)} 組（建立／追加 × 有無 --reason）的 reason 完整字串與兩段順序、'
          '決策第 (1) 項的實際字串都釘住，舊的兩種說法 0 命中；project-init 第 7 步的命令帶 --reason: pass')


def test_init_glossary_heading_order(tmp: Path) -> None:
    """規格 68：判斷順序固定——①沒有檔 ②認得的編號列 ③同名標題 ④追加。

    有「編號對照表」一節就不再追加一節（編號不是 SQ／AQ 加數字的專案重跑不會被多加一張認不得的表）。
    """
    IGM = _load_script(IG_REL)
    # (a) 同時有認得的列與同名標題 → 說明用第一種（② 先於 ③）
    root = copy_fixture(tmp, 'ig_order')
    (root / C.GLOSSARY_REL).unlink()
    rc, out = run_action(IG, root)
    assert rc == 0, out[-1500:]
    assert IGM.has_table_heading((root / C.GLOSSARY_REL).read_text(encoding='utf-8').split('\n')), \
        '工具自己建的表沒有那個標題，第三列的判準測不到'
    stamp, dids = _tree_stamp(root), _ig_dids(root)
    rc, out = run_action(IG, root)
    assert rc == 0 and _tree_stamp(root) == stamp and _ig_dids(root) == dids, (rc, out[-600:])
    assert '已經有編號列（主子問題列 1 列、附錄問題列 2 列）' in out, out
    assert IGM.SKIP_NO_ROWS not in out and IG_SKIP_TAIL in out, out
    # (b) 有那一節、沒有認得的編號列 → 零寫入、零決策、印第二種說明（不接「之後由那兩支維護」）
    odd = _g_doc([IG_ODD_MAIN, G_DID], heading=IG_TABLE_HEAD, tail=['## 其他'])
    (root / C.GLOSSARY_REL).write_text(odd, encoding='utf-8')
    assert C.glossary_rows(odd.split('\n')) == ([], []), '這份 fixture 不該有認得的編號列'
    stamp = _tree_stamp(root)
    rc, out = run_action(IG, root)
    assert rc == 0, out[-1200:]
    assert _tree_stamp(root) == stamp, '有那一節卻又追加了一次'
    assert _ig_dids(root) == dids and '決策 D-' not in out, (out[-400:], _ig_dids(root))
    assert IGM.SKIP_NO_ROWS in out and '第 7 步會略過' in out, out
    assert IG_SKIP_TAIL not in out, f'同一行又說「之後由那兩支維護」，與「第 7 步會略過」矛盾\n{out}'
    # (c) 同名標題只在 fence 裡 → 照常追加
    fenced = '\n'.join(['# 我們的術語', '', '## 說明', '', '```markdown', IG_TABLE_HEAD, '', G_HEAD, '```', ''])
    (root / C.GLOSSARY_REL).write_text(fenced, encoding='utf-8')
    rc, out = run_action(IG, root)
    assert rc == 0, out[-1200:]
    new = (root / C.GLOSSARY_REL).read_text(encoding='utf-8')
    assert new.startswith(fenced) and len(new) > len(fenced), 'fence 裡的標題被當成「已經有那一節」'
    assert _ig_rows(root) == IG_WANT_ROWS, _ig_rows(root)
    assert _ig_dids(root) == dids + [dids[-1][:2] + str(int(dids[-1][2:]) + 1).zfill(3)], _ig_dids(root)
    # (d) 標題寫法：ATX 任一層級與 setext 都算；`### 編號對照` 這種不同寫法不算
    shapes = [('ATX 六級', ['###### 編號對照表', '', G_HEAD, G_DID, ''], IGM.SKIP),
              ('setext', ['# 甲', '', '編號對照表', '----', '', G_HEAD, G_DID, ''], IGM.SKIP),
              ('前後空白', ['##   編號對照表   ', '', G_HEAD, G_DID, ''], IGM.SKIP),
              ('不同寫法', ['# 甲', '', '### 編號對照', '', G_HEAD, G_DID, ''], IGM.APPEND)]
    for name, lines, want in shapes:
        (root / C.GLOSSARY_REL).write_text('\n'.join(lines), encoding='utf-8')
        state, why = IGM.glossary_state(root)
        assert state == want, (name, state, why)
        if want == IGM.SKIP:
            assert why == IGM.SKIP_NO_ROWS, (name, why)
    # (e) 沒有這個檔仍然排在最前面
    (root / C.GLOSSARY_REL).unlink()
    assert IGM.glossary_state(root) == (IGM.CREATE, '專案還沒有這個檔'), IGM.glossary_state(root)
    shutil.rmtree(root)
    print('[regression] 規格 68：判斷順序 ①沒有檔 ②認得的編號列 ③同名標題 ④追加——有認得的列時說明是第一種、'
          '只有那一節時零寫入零決策且不說「之後由那兩支維護」、fence 裡的標題不算、'
          f'{len(shapes)} 種標題寫法各判對: pass')


def test_init_glossary_self_check(tmp: Path) -> None:
    """規格 69：寫檔前量自己產的表認不認得——認不得照常寫，但 WARNING、步驟紀錄與決策都照實。"""
    IGM = _load_script(IG_REL)
    # 單元：編號都合格式、只是列數對不上時不得說成「不是 SQ／AQ 加數字」
    ok_ids = {'sub_questions': ['SQ8'], 'appendix_questions': ['AQ9']}
    ok_text = '\n'.join([G_HEAD, f'| SQ8 | {C.GLOSSARY_MAIN_CELL} |  |',
                         f'| AQ9 | {C.GLOSSARY_AQ_CELL} | 甲 |'])
    assert IGM.self_check(ok_text, ok_ids) == ('', ''), IGM.self_check(ok_text, ok_ids)
    odd_text = '\n'.join([G_HEAD, f'| SQ8 | {C.GLOSSARY_MAIN_CELL} |  |',
                          f'| SQ9 | {C.GLOSSARY_AQ_CELL} | 甲 |'])
    warn, clause = IGM.self_check(odd_text, {'sub_questions': ['SQ8'], 'appendix_questions': ['SQ9']})
    assert warn.startswith('WARNING') and '附錄問題列 0 列' in warn and 'goals 有 1 個附錄問題' in warn, warn
    assert '不是 SQ／AQ 加數字' not in warn and '不是 SQ／AQ 加數字' not in clause, (warn, clause)
    # 乾淨 fixture：都認得 → 一行 WARNING 都不印
    root = copy_fixture(tmp, 'ig_self_ok')
    (root / C.GLOSSARY_REL).unlink()
    rc, out = run_action(IG, root)
    assert rc == 0 and 'WARNING' not in out, (rc, out[-900:])
    shutil.rmtree(root)
    # goals 的編號不是 SQ／AQ 加數字 → 照常建出檔，但三處照實
    root = _fx_project_init(tmp, 'ig_self_odd', snapshot=False)
    doc = yaml.safe_load((root / 'project.yaml').read_text(encoding='utf-8'))
    doc['goals']['sub_questions'][0]['id'] = 'RQ1'
    doc['goals']['appendix_questions'] = [dict(doc['goals']['sub_questions'][1], id='AQ-2', question='附錄甲')]
    (root / 'project.yaml').write_text('# 新專案\n' + _ydump(doc), encoding='utf-8')
    rc, out = run_action(IG, root)
    assert rc == 0, f'認不得就中止了 rc={rc}\n{out[-1800:]}'
    assert (root / C.GLOSSARY_REL).is_file() and _ig_rows(root) == [], _ig_rows(root)
    want = ('WARNING GLOSSARY.md 的編號對照表有列認不出來：RQ1、AQ-2 不是 SQ／AQ 加數字（可帶小寫字母）；'
            'reassign_question.py 與 promote_question.py 的第 7 步會略過那些列')
    assert want in out, f'stdout 沒有那一行 WARNING\n{out[-1200:]}'
    assert want in _step_notes(root, out, 1), _step_notes(root, out, 1)
    line1 = str(_decision_of(root, out)['decision']).split('\n')[0]
    assert line1.endswith('；其中 RQ1、AQ-2 不是 SQ／AQ 加數字（可帶小寫字母），對照表的動作認不得'), line1
    _ig_decisions_clean('認不得的編號', root)
    _ig_no_forbidden('認不得的編號', _ig_texts(root, out))
    # 同一個專案再跑一次：走第三列（已經有那一節），不再追加一張認不得的表
    stamp, dids = _tree_stamp(root), _ig_dids(root)
    rc, out = run_action(IG, root)
    assert rc == 0 and _tree_stamp(root) == stamp and _ig_dids(root) == dids, (rc, out[-600:])
    assert IGM.SKIP_NO_ROWS in out, out
    shutil.rmtree(root)
    print('[regression] 規格 69：寫檔前量新內容——都認得就 0 行 WARNING；'
          '編號不是 SQ／AQ 加數字時照常建檔，stdout 與步驟紀錄各一行 WARNING 列出那些編號、'
          '決策第 (1) 項照實補一句，重跑走第三列（冪等）；列數對不上但編號合格式時不說成格式不對: pass')


def test_decisions_header_author(tmp: Path) -> None:
    """規格 70：`decisions.yaml` 首次建檔的檔頭寫實際那支腳本的名字；取不到 `method` 走後備句。"""
    assert C.decision_author({'method': 'init_glossary.py 9.9.9 --apply；步驟紀錄 reviews/x.json'}) \
        == 'init_glossary.py'
    for entry in ({}, {'method': ''}, {'method': None}, {'method': '研究設計'}, {'method': 'x.py.bak 1'}):
        assert C.decision_author(entry) == 'academic-pipeline 的動作腳本', entry
    head_of = (lambda root: (root / 'decisions.yaml').read_text(encoding='utf-8').split('\n')[0])
    # 兩支會 append 決策的動作，各在沒有 decisions.yaml 的 fixture 上建檔
    cases = [('init_glossary.py', IG, (), lambda name: _fx_project_init(tmp, name, snapshot=False)),
             ('set_figure_role.py', 'set_figure_role.py', ('--figure', 'F_a=extended'),
              lambda name: copy_fixture(tmp, name))]
    for script, runner, args, build in cases:
        root = build('hdr_' + Path(script).stem)
        (root / 'decisions.yaml').unlink()
        rc, out = run_action(runner, root, *args)
        assert rc == 0, f'{script}：rc={rc}\n{out[-1500:]}'
        assert head_of(root) == f'# 決策日誌——append-only；由 {script} 首次建檔。', head_of(root)
        assert _ig_dids(root) == ['D-' + '001'], _ig_dids(root)
        shutil.rmtree(root)
    # 已經有 decisions.yaml：檔頭一個位元都不動
    root = copy_fixture(tmp, 'hdr_keep')
    (root / C.GLOSSARY_REL).unlink()
    before = (root / 'decisions.yaml').read_bytes()
    rc, out = run_action(IG, root)
    after = (root / 'decisions.yaml').read_bytes()
    assert rc == 0 and after.startswith(before), (rc, after[:len(before)][-200:], before[-200:])
    assert len(after) > len(before) and '首次建檔' not in after.decode('utf-8'), head_of(root)
    shutil.rmtree(root)
    print(f'[regression] 規格 70：{len(cases)} 支動作各自在沒有 decisions.yaml 的專案上建檔，檔頭各寫自己的腳本名；'
          'method 取不到時走後備句；已有的檔頭不動: pass')


def test_gate_baseline_raw(tmp: Path) -> None:
    """規格 71：步驟紀錄的 `gate_baseline` 存原文（指紋與日期不遮），比對鍵與比對語意仍走正規化。"""
    root = copy_fixture(tmp, 'gb_raw')
    raw = 'BLOCKER R9: /tmp/ws-0123456789abcdef/合金硬度.yaml 的封存值不符（2099-01-01 量的）'
    norm = C.normalize_finding(raw)
    assert '<FP>' in norm and '<DATE>' in norm and norm != raw, norm
    orig = C.run_gate
    try:
        C.run_gate = lambda root, key: (C.gate_findings(1, raw + '\n'), raw + '\n')
        ch = C.Chain(root, 'move_result', 'gb_raw', 'reviews/gb-raw.json', {}, 'D-' + '900', DATE, True)
        gb = ch.log.doc.get('gate_baseline') or {}
        assert gb, '步驟紀錄沒有留 baseline'
        for key, rows in gb.items():
            assert rows == [raw], (key, rows)
            assert ch.gate_base[key] == [norm], (key, ch.gate_base[key])   # 比對鍵仍是正規化形式
        disk = json.loads(ch.log.write().read_text(encoding='utf-8'))['gate_baseline']
        assert all(rows == [raw] for rows in disk.values()), disk
        assert '<FP>' not in json.dumps(disk) and '<DATE>' not in json.dumps(disk), disk
        # 動作後同一筆只差指紋與日期 → 照樣判成既有，不擋
        after = 'BLOCKER R9: /tmp/ws-fedcba98765432/合金硬度.yaml 的封存值不符（2099-12-31 量的）'
        assert C.normalize_finding(after) == norm, C.normalize_finding(after)
        _clear_sinks()
        ch.gate_check('plan', 1, after + '\n')
        assert len(C._EXISTING_SINK) == 1 and C._EXISTING_SINK[0][1] is False, C._EXISTING_SINK
        assert '<FP>' not in C._EXISTING_SINK[0][2], C._EXISTING_SINK
    finally:
        C.run_gate = orig
        _clear_sinks()
    shutil.rmtree(root)
    print('[regression] 規格 71：步驟紀錄的 gate_baseline 存當次輸出的原行（記憶體裡的比對鍵仍是 <FP>／<DATE>），'
          '動作前後只差指紋與日期的同一筆照樣判成既有、不擋: pass')


# ======================================================================
# 規格 72：版號、CHANGELOG 與文件登記
# ======================================================================

def test_registration() -> None:
    cl = (PLUGIN / 'CHANGELOG.md').read_text(encoding='utf-8')
    assert cl.startswith(f'# CHANGELOG\n\n## {V}（'), cl[:60]   # 當期精確版號由本檔 pin，下一版改單調斷言
    ver = json.loads((PLUGIN / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))['version']
    assert ver == V, ver
    name = Path(__file__).name
    assert name in (PLUGIN / 'tests/README.md').read_text(encoding='utf-8'), 'tests/README.md 沒有登記本檔'
    assert name in (PLUGIN / 'README.md').read_text(encoding='utf-8'), 'README.md 沒有登記本檔'
    # 依慣例：前一支回歸測試改為單調斷言，升版不會誤紅。這個針不能寫成字面字串——本檔上面那條精確斷言
    # 自己就含著它，寫成字面的話下一版照抄這段時會永遠判「前一支仍精確 pin」。用相加組出來。
    needle = 'cl.startswith(' + "f'# CHANGELOG"
    prev = (PLUGIN / 'tests/run_v0282_regressions.py').read_text(encoding='utf-8')
    assert '(0, 28, 2)' in prev, 'run_v0282 的 plugin.json 斷言不是與 (0, 28, 2) 比大小的單調形式'
    assert needle not in prev, 'run_v0282 仍精確 pin CHANGELOG 第一節，升版會誤紅'
    print(f'[regression] 規格 72：CHANGELOG 最上面是 {V}、plugin.json == {V}、tests README 與 README 登記本檔、'
          'run_v0282 已是單調斷言: pass')


def _load_script(rel: str):
    """按路徑載入一支腳本當模組（不走 sys.path，避免互相蓋掉同名模組）。"""
    name = 'probe_' + Path(rel).stem
    spec = importlib.util.spec_from_file_location(name, PLUGIN / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='v0290-') as td:
        tmp = Path(td).resolve()
        test_json_scan()
        test_yaml_helpers()
        test_opt_in_lists()
        test_trailing_comment_kept()
        test_rerun_not_silent()
        test_state_comment()
        test_block_scalar_and_links()
        test_format_matrix(tmp)
        test_warning_visible(tmp)
        test_crlf_kept(tmp)
        test_suffix_ids(tmp)
        test_retag_scale()
        test_comment_modes()
        test_decisions_style_and_append(tmp)
        test_inbox_indent(tmp)
        test_batch_warning(tmp)
        test_broken_ssot(tmp)
        test_suffix_ids_rest(tmp)
        test_suffix_tier_question(tmp)
        test_findings_multiset()
        test_snapshot_merge(tmp)
        test_snapshot_ids_not_reused(tmp)
        test_existing_decisions_only(tmp)
        test_existing_not_blocking(tmp)
        test_finding_presentation()
        test_gate_note_after_verdict()
        test_decisions_gate_baseline()
        test_gate_existing_once(tmp)
        test_empty_bib_not_leaked(tmp)
        test_placeholder_plan_node(tmp)
        test_workspace_link_fingerprint(tmp)
        test_new_findings_blocked(tmp)
        test_one_column_stale(tmp)
        test_stale_and_drift_independent(tmp)
        test_new_stale_still_blocks(tmp)
        test_dirty_source_plan_blocked(tmp)
        test_lagging_item_shapes(tmp)
        test_decision_id_width(tmp)
        test_verify_validation_strict()
        test_gate_baseline_shape(tmp)
        test_waiver_text_units()
        test_decision_id_regex_constants()
        test_state_policy_independent(tmp)
        test_drift_per_field(tmp)
        test_fingerprint_unavailable(tmp)
        test_dirty_plan_wiring(tmp)
        test_untrue_waiver_text(tmp)
        test_stale_not_absorbed(tmp)
        test_no_results_text_units()
        test_no_results_gates(tmp)
        test_no_results_move_blocked(tmp)
        test_no_results_actions(tmp)
        test_no_results_waiver_text(tmp)
        test_coverage_sentence_units()
        test_coverage_sentence_actions(tmp)
        test_no_results_links_message(tmp)
        test_moved_link_forms_units()
        test_moved_link_existing(tmp)
        test_moved_link_no_results(tmp)
        test_same_line_units()
        test_no_results_once_per_line(tmp)
        test_glossary_locate()
        test_glossary_decision_units()
        test_glossary_decision_actions(tmp)
        test_glossary_promote_fence()
        test_glossary_init_hint()
        test_glossary_docs()
        test_init_glossary_states(tmp)
        test_init_glossary_guards(tmp)
        test_init_glossary_fresh(tmp)
        test_init_glossary_end_to_end(tmp)
        test_init_glossary_reason_wording(tmp)
        test_init_glossary_heading_order(tmp)
        test_init_glossary_self_check(tmp)
        test_decisions_header_author(tmp)
        test_gate_baseline_raw(tmp)
        test_registration()
        test_teeth(tmp)
    print(f'PASS v{V} regressions（檔案格式假設與靜默寫錯；關卡只擋新增；'
          '既有問題不得被動作吃掉；每個專案都有 GLOSSARY.md）')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
