---
name: revise
description: >
  This skill should be used when the user asks to 「修改稿件」、「回覆審稿意見」、「修訂」、
  "revise"、"respond to reviewers"，or needs to process virtual, journal, or authorial comments.
metadata:
  version: "0.7.1"
---

# 修訂、逐點回覆與審稿閉環

逐條處理 `reviews/issue-ledger.yaml`，不以文字修改掩蓋結構問題。任何 upstream artifact 變更都依依賴鏈失效與重跑。審稿分數由完整 panel 輪的 editor 產生，並由 `record_review_score.py` 寫入；本 skill 不得讓 `check_ledger.py` 面對永遠為空的 `state.review.scores`。

## 意見來源

- **虛擬審稿**：最新 `reviews/roundN/` 的 reviewer reports、editor decision、response letter、diff 與 ledger。
- **期刊實際意見**：存 `reviews/roundN/external/`；先整理為逐點清單供使用者確認。
- **作者方意見**：指導教授、共同作者、口試委員等，存 `reviews/authorial/<日期>-<來源>.md`；ledger id 用 `A-<序號>`。authorial 池不驅動審稿輪、裁決或保險閥，但其稿件改動仍會影響下輪 diff 與 consistency fingerprint。

裁決為 reject 時，本 skill 不直接啟動修稿迴圈，先路由 journal-match 轉投模式。

## issue-ledger 契約

每條意見至少含：

```yaml
issues:
  - id: R1-S1-03          # R<輪>-<S1–S4|M|D|W>-<序>；作者方用 A-<序>
    round_raised: 1
    reviewer: methods-rigorist
    severity: must_fix    # must_fix / suggestion / preference
    layer: structural     # structural / textual
    summary: "主分析未報效應量信賴區間"
    status: open          # open / resolved / rebutted / dropped
    resolved_round: null
    ms_location: "結果 3.2"
    derived_from: ""
    note: ""
```

帳本只由 revise 登錄／更新，以及 peer-review 中 editor 調整 severity/layer；舊專案無帳本時可補建並提示。

## 分類與回流

- **純文字／格式／圖說**：改新稿版本，之後 full check-consistency。
- **新引用／文獻定位**：lit-review 增補 → evidence-synthesis → 必要時 claims/claim-audit → 稿件。
- **新分析、模型、納排、missing data、multiplicity**：study-design amendment → 必要 integrity/data-audit → analyze-data → clean rerun → code-review → validate-results → result-fit → claims/claim-audit → 稿件。
- **raw data 或資料語意問題**：data-audit；fingerprint 變更則整條正式結果鏈重建。
- **claim 強度／邊界**：interpret-results 新版本 → claim-audit → 使用者確認 → 稿件。
- **goals／主問題變更**：decomposition-review → route 重檢 → protocol/plans amendment → full evaluation 與所有下游失效。
- **作者、COI、權限、AI disclosure**：integrity-check 對應 stage 重跑。

## 快速通道：decision = minor

minor fast track 不增加 round，也不建立新 score entry：

1. 只處理 textual must-fix；逐點提出處置，使用者確認後修改稿件並更新 ledger。
2. 產生新稿與 diff；重跑完整 check-consistency，不只重跑先前失敗項。
3. 委派 editor `mode: re-check`，材料只有 ledger、diff 與修改後稿件；不重啟 panel、不重打七維分數、不輸出 REVIEW_SCORE block。
4. must-fix 清零且無新問題：寫 `state.review.converged: true`，進選用中文潤稿站／中文人工定稿。
5. 未清：給一次補正；仍未清則交人工裁決並記 D#。

## 完整修訂：decision = major 或外部意見

1. **逐點分類與人工裁定**：每點標接受、部分接受或有依據地反駁。反駁必須連 results key、V#、claim id 或 citekey，不得空口。計畫反駁的項目先呈使用者確認；方向性取捨記 D#。
2. **確認本輪分數已落帳**：若這是虛擬完整 panel 輪，`state.review.scores` 必須已有同 round 條目。若因舊版或中斷而缺失，從該輪 `editor-decision.md` 回填：

   ```bash
   python3 <plugin>/skills/revise/scripts/record_review_score.py \
     project.yaml reviews/roundN/editor-decision.md
   ```

   已存在同輪相同分數時腳本 no-op；不同分數不得覆寫，除非 editor decision 明確更正且使用 `--replace`。外部期刊意見若沒有本 pipeline 的 editor score，不得偽造。
3. **執行依賴鏈**：按「分類與回流」重建 artifacts。禁止手動把舊 rerun、validation、claim-audit 或 consistency state 改成 pass。
4. **改稿與回覆信**：輸出 `manuscript/<lang>/v(N+1).md`、`reviews/roundN/response-letter.md`；每一點連到具體 diff、artifact 或證據。更新 `state.zh_latest`／對應語言最新版本。
5. **修改對照**：

   ```bash
   python3 <plugin>/skills/revise/scripts/diff_versions.py \
     <舊版> <新版> --out reviews/roundN/diff-*.md --sections
   ```

   變更節清單供下一輪 scope freeze 與 translate-en 增量重譯。
6. **收尾檢核**：
   - goals 有變 → 重跑完整 evaluate；
   - 強制 full check-consistency；
   - 執行 `check_ledger.py ... --round N [--sections ...]`；
   - 確認本輪 score 可讀，並回報分數趨勢與 must-fix 變化。
7. **保險閥**：任一觸發即離開自動迴圈、交人工裁決，不寫 converged：
   - major 全審輪達 `review.max_rounds`；
   - 相鄰可比分數中，total 改善 `<5` 且 must-fix open 未下降。相鄰模型不同或 `panel_changed: true` 時跳過該對。
8. **下一站**：major → 下一個 peer-review panel 輪；minor → 快速通道；accept／覆核通過 → 中文潤稿站／人工定稿；reject → journal-match。

## `state.review.scores` 寫入契約

每個完整 panel 輪次都必須有一筆，不能只在 accept 時寫，也不能等到 revise 才憑記憶重建：

```yaml
state:
  review:
    scores:
      - round: 1
        method: 6
        argument: 5
        goal_fit: 7
        contribution: 7
        reporting: 6
        writing: 7
        figures: 7
        total: 45
        must_fix_open: 3
        model: "實際 model alias 或 ID"
        decision: major
        panel_changed: false
```

canonical writer 是 `record_review_score.py`；canonical reader 是 `check_ledger.py`。minor re-check 不新增分數；完整新 panel 輪才新增。這個 producer–consumer 契約是邊際遞減保險閥的必要條件。

## 中文潤稿站掛點

收斂後、中文人工定稿前，呼叫內建 skill `chinese-academic-editing`（0.10.0 起隨附；選用，不可取代★中文人工定稿）：

- 產生新中文版本；只可改語言呈現，不得改數字、結果／主張標記、citekey、claim strength、validation boundary、方法或限制語意。
- 其 Layer 4 校準結果與討論的陳述句型；發現 over-claim 或 `results.json` 缺鍵只標記回 `claim-audit`／`analyze-data`。
- 潤稿後重跑 numbers、citations、claims、marker 與 full `check-consistency(zh)`。

使用者仍須親自確認 `state.zh_final`；潤稿站不能取代人工定稿。

## 收尾

逐列申報實際變更與失效，例如：

「本階段更新：state.zh_latest v3→v4；results/validation/claims/consistency 因 plan amendment 重建；state.review.scores round 2 已驗證存在；下一站：peer-review。」

固定加註：收斂只代表虛擬審稿停止，不等於真實期刊 accept。

收尾必記一筆 D#：追加 `decisions.yaml` 條目，`stage: revise`、`checkpoint: 階段收尾`，並填 `question`（本階段對應的問題層：`main` 或子問題 id 如 `SQ2`）、`exec_issue`（只在這筆是該問題之下的執行問題時填，一句話）、`method`（對應該層的方法：main＝研究設計、SQ＝分析方法、有 exec_issue＝解決該執行問題的做法）、`evidence`（本階段的指令、腳本路徑、fingerprint 或輸出檔路徑清單）；照建議原樣通過也要記。這一筆是進度時間軸的資料來源，沒記就不會出現在時間軸上。
