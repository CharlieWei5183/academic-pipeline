---
name: peer-review
description: >
  This skill should be used when the user asks to 「送審看看」、「虛擬審稿」、「peer-review」、
  or wants a full-manuscript persona review after a current consistency gate has passed.
metadata:
  version: "0.7.1"
---

# 虛擬同儕審查

三至四席 persona 全文審稿，再由 editor 依固定七維分數帶評分與裁決。v0.7 材料包加入 upstream audit artifacts，避免審稿人只看到已被敘事包裝的結果。每個完整 panel 輪次的 editor 分數都必須寫入 `state.review.scores`，否則邊際遞減保險閥沒有資料可用。

## 三條紅線（persona 席位）

1. 指定學者席的報告開頭固定聲明：「本報告為風格參考之模擬審查，依據 <persona 檔> 所整理的方法學立場產出，不代表該學者本人意見。」內建通用席改註所用通用立場。
2. 不得以該學者名義使用第一人稱發言。
3. persona profile 必須由使用者逐項核可並記 D# 後才可啟用。

## 前置

1. 定位專案根目錄與送審稿件；`state.si_latest` 非空時，SI 隨稿送審。
2. 對稿件執行 `check_gate.py`：

   ```bash
   python3 <plugin>/skills/check-consistency/scripts/check_gate.py <root> \
     --manuscript <稿件.md> --require-language <zh|en>
   ```

   - 一律是完整 fingerprint gate：`last_consistency` 的 `result`、`version`、`gate_fingerprint` 與 `report` 缺一即阻擋。
3. 另確認：claims confirmed、claim-audit pass，route 要求的 validation/evidence/data-audit 均通過且未過期。
4. 讀取 `review.strictness`、`review.emphasis`、`review.max_rounds`（預設 3）與 `review.panel`。
5. issue-ledger schema 通過；authorial 池有 open must-fix 時，提示先處理或記錄帶病送審。
6. 決定輪次 N：完整 panel 輪為 `state.review.round + 1`；建立 `reviews/roundN/`。minor re-check 不增加輪次。

## 席位組成與 persona

- `panel.seat` 只接受 S1–S4；同一 seat 重複設定時報錯。
- 未設或未列滿三席時，以 methods-rigorist、field-positioner、argument-critic 補滿；S4 為選用加席。
- 未設 panel 的舊專案，自下一個新輪次採內建三席；進行中的輪次先完成。跨制切換的相鄰分數不可比，editor score block 必須設 `panel_changed: true`。
- 指定學者 profile 不存在時，從 references.bib 與 literature notes 萃取；著作不足則退回不掛名通用 persona。
- 三席確定後向使用者並列立場軸；明顯同質時先建議調整。
- editor 提名只能來自 references.bib／matrix 的引用網絡，不得憑訓練資料想像。
- matrix 超過六個月或 goals 變更後未更新時，先建議 lit-review 增補模式；材料包註明更新日期。

## 統一材料包

每席取得完整稿件／SI及同一組事實材料：goals/evaluations、route、protocol/active plans、data-audit、manifest、results／adapter findings、clean rerun/code-review、validation、claims、claim-audit、evidence synthesis、matrix/novelty statement、figure story/manifest、consistency report。各席另附自己的 persona profile；指定學者席再附 grounding notes。

不提供 decisions.yaml 或其他席報告。第 2 輪起另附前輪意見、response letter、ledger、diff 與變更節清單；scope freeze 下，新 must-fix 只能針對變更節或由既有議題衍生。

## 流程

1. **並行審稿**：同一訊息啟動三至四個 `reviewer` agent。每席獨立、互不可見，報告存 `reviews/roundN/reviewer-<persona_id>.md`。
2. **彙入 ledger**：新增 review 池條目，保留來源席、severity、layer、位置與 derived_from。先跑一次：

   ```bash
   python3 <plugin>/skills/revise/scripts/check_ledger.py \
     reviews/issue-ledger.yaml project.yaml --round N [--sections <變更節清單>]
   ```

   此次供 editor 看既有帳本、範圍凍結與前輪趨勢；不含本輪尚未產生的分數。
3. **editor 評分與裁決**：委派 editor，材料包含各席報告、稿件全文、ledger 與全部七維事實來源；不提供前輪分數或 decisions.yaml。editor 依 `agents/editor.md` 的固定分數帶、contribution 兩子問題及裁決函數，產出 `reviews/roundN/editor-decision.md`，並在末尾輸出唯一的 `REVIEW_SCORE` YAML block。
4. **確定性寫入分數**：每個完整 panel 輪次，不論 accept／minor／major／reject，立即執行：

   ```bash
   python3 <plugin>/skills/revise/scripts/record_review_score.py \
     project.yaml reviews/roundN/editor-decision.md
   ```

   腳本驗證七維均為 1–10、`total` 等於加總、model/decision/must_fix_open 齊全，並以 round 去重後寫入：

   ```yaml
   state:
     review:
       round: N
       decision: major
       converged: false
       scores:
         - {round: N, method: 6, argument: 5, goal_fit: 7, contribution: 7,
            reporting: 6, writing: 7, figures: 7, total: 45,
            must_fix_open: 3, model: "...", decision: major}
   ```

   寫入失敗即停止，不得直接路由 revise。更正同輪 editor decision 時才可用 `--replace`。
5. **保險閥再檢查**：分數寫入後再跑 `check_ledger.py --round N`，此時必須能讀到本輪與前輪分數。若觸發輪次上限或「連續兩輪 total 改善 <5 且 must-fix open 未下降」，強制交人工裁決並記 D#；不得自動續跑。
6. **路由**：
   - accept → `converged: true` → 選用中文潤稿站 → 中文人工定稿；
   - minor → revise 快速通道，editor 單人 re-check；不新增 score、不增加 round；
   - major → revise 完整修訂後進下一個 panel 輪；
   - reject → journal-match 轉投。

   reviewer 要求新分析、新證據或改 claim 時，不得只改文字：回 study-design／data-audit／analyze-data／validate-results／evidence-synthesis／interpret-results／claim-audit，之後重建所有下游 fingerprints。

## 中文潤稿站掛點

收斂後、使用者確認中文定稿前，呼叫內建 skill `chinese-academic-editing`（0.10.0 起隨附；選用，可略過但**不可取代**★中文人工定稿）：

- 清除中文 AI tells、把語域拉回學術書面體，並依其 Layer 4 校準結果與討論的陳述句型（效果量與不確定度同時報、不以裸 p 值作主句、限制節不得改成正面語氣、摘要不得移除正文保留的核心限定）。
- 只可動語言呈現，不得改數字、`<!-- -->` 標記、`[@citekey]`、claim strength、validation boundary 或方法語意；發現 over-claim 或 `results.json` 缺鍵只**標記**回 `claim-audit`／`analyze-data`，不在潤稿站裁定。
- 產生新中文版本後，重跑 marker／numbers／citations／claims 及 full `check-consistency(zh)`，再進★中文人工定稿。

此站是選用外部掛點，不是 plugin 內建 skill；不得因未安裝而報錯。

## 收尾

摘要裁決、七維分數、必改重點與保險閥狀態；固定註明：「收斂是虛擬審稿的停止訊號，不等於真實期刊會 accept。」並申報：

「本階段更新：state.review.round <舊>→N、decision →<裁決>、state.review.scores 追加 round N；下一站：<skill／人工確認點>」。

收尾必記一筆 D#：追加 `decisions.yaml` 條目，`stage: peer-review`、`checkpoint: 階段收尾`，並填 `question`（本階段對應的問題層：`main` 或子問題 id 如 `SQ2`）、`exec_issue`（只在這筆是該問題之下的執行問題時填，一句話）、`method`（對應該層的方法：main＝研究設計、SQ＝分析方法、有 exec_issue＝解決該執行問題的做法）、`evidence`（本階段的指令、腳本路徑、fingerprint 或輸出檔路徑清單）；照建議原樣通過也要記。這一筆是進度時間軸的資料來源，沒記就不會出現在時間軸上。

## 規則

- 審稿席互不可見；只有 editor 讀全部。
- editor 固定分數帶不得刪除或每輪改寫。
- `state.review.scores` 的完整 panel 輪寫入者是 `record_review_score.py`；check_ledger 是讀者，不得出現有讀者而無寫者的懸空契約。
- 舊 ledger 的 M／D／W 席位代碼照讀不改寫。
