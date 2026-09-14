---
name: lit-review
description: >
  This skill should be used when the user asks to 「文獻回顧」、「找相關研究」、「整理文獻」、
  「補文獻」、"lit-review"、"literature review"，or needs literature discovery and reading
  in an academic-pipeline project.
metadata:
  version: "0.7.2"
---

# 文獻搜尋與精讀

literature-scout 負責搜尋、取得、撤稿／版本檢查、筆記、references.bib 與 matrix；證據品質、screening、一致／矛盾證據與 citation-entailment 由 evidence-synthesis 的 evidence-auditor 獨立完成。

## 模式

- **全模式**：建立或更新研究背景、缺口與 novelty statement，之後強制 evidence-synthesis。
- **增補模式**：針對無錨 claim、審稿問題、方法或相反證據搜尋；同樣更新 evidence protocol/search log，並使舊 synthesis/audit 過期。

## 前置

定位並讀取 `project.yaml`：`research_question`、`goals`（含各 SQ 的 `evidence` 與 `success_criteria`）、`field`、methodology route，以及既有 `literature/evidence-protocol.yaml`、matrix、references.bib 與 search log。向使用者確認搜尋關鍵字（中英文）與大致篇數期望（預設 15–30 篇核心文獻）。

## 步驟

1. 讀 goals、methodology route、既有 evidence protocol、matrix、references 與 search log。
2. 在 `literature/evidence-protocol.yaml` 已確認的範圍內委派 literature-scout；若需改資料庫、搜尋式、日期／語言限制或 eligibility，先由 evidence-synthesis 建 protocol amendment，不得悄改。
3. 每次搜尋記完整 query、database、日期、命中、去重與失敗來源；文獻全文筆記要含方法、樣本、主要 findings、限制與可支持／不可支持的敘述。
4. references.bib 是 citekey 白名單；查撤稿、修正、版本與重複 cohort。無法取得全文時標記，不以摘要冒充完整方法審查。
5. 更新 `literature/matrix.md`：表格彙整全部文獻；**缺口分析對照 sub_questions 撰寫**——逐一列出：哪些 SQ 文獻已回答（本研究只需引用）、哪些部分回答、哪些留給本研究，並在每個文獻型 SQ 下列出候選 citekey（收尾寫 links 的取材來源）。novelty statement 與目標回訪的正式落點見〈收尾（全模式）〉。
6. **強制回呼 evidence-synthesis**：更新 screening、risk of bias、certainty、conflicting evidence 與 citation audit。只完成 literature search 不等於 evidence gate pass。
7. 更新 `state.literature.updated_at/mode`；evidence-synthesis 通過後再更新其 state。

## 收尾（全模式）

1. **novelty statement（新穎性的早期關卡）**：缺口分析完成後，產出一段新穎性聲明——本研究相對矩陣的新東西是什麼、與最接近的工作差異何在、為何值得目標層級的期刊——**經使用者確認後**寫入 `matrix.md` 末節（或 `project.yaml` 的 `meta.novelty_statement`）。此後 peer-review 的 contribution 打分對照這份聲明稽核稿件，而不是投稿前夕才初次發現致命傷；聲明本身站不住時，就在本階段退回調整 goals（正式落點即下一步的目標回訪）。
2. **文獻後目標回訪**：novelty statement 確認後，對照缺口分析與矩陣**逐 SQ 檢視，限定三類**——
   - **已被回答**：某 SQ 的答案已被既有文獻充分給出 → 建議改向、合併或降為背景敘述。
   - **無覆蓋**：主問題的重要面向沒有任何 SQ 承接 → 建議增補。
   - **criteria 脫節**：success_criteria 與該領域慣用的量測或報告方式、或與文獻現況明顯不合 → 建議校準措辭。

   有增修 → 走既有 goals 變更確認；屬**結構性增修**（增刪多個 SQ、或改動主問題拆法）時觸發一次 evaluate 拆解審（此時材料含矩陣與 novelty statement，覆蓋性判斷升為有據）；裁決記 D#（方向性選擇）。無增修 → 申報「goals 與矩陣對齊已檢視，無變更」。
3. **文獻型 SQ 的 evidence links 寫入（evidence-synthesis 通過後執行）**：對 `evidence` 含 `literature` 或 `both` 的每一個 SQ，把實際支撐它的文獻以 **`cite:<citekey>`** 逐筆補入該 SQ 的 `goals[].links`（**經使用者確認**後寫入 project.yaml）。判準與格式**寫死如下**：
   - 格式只認 `cite:<citekey>`（evaluate 的 `check_coverage.py` 僅接受 `results:` / `cite:` / `ms:` 三種前綴，其他前綴一律報 WARNING；`evidence:` 之類的新前綴**不得使用**）。
   - citekey 必須存在於 `literature/references.bib`（否則 check_coverage 報 BLOCKER），且必須已出現在 `literature/evidence-synthesis.yaml` 的 `studies[].citekey`（即經 risk of bias 審查）——evaluate `full` 檔的硬前置要的是**已審查**的 evidence links，未過 evidence-synthesis 的 citekey 不得寫入。
   - 只**增補** `cite:` links，不刪改該 SQ 既有的 `results:` / `ms:` links（`both` 型 SQ 的 `results:` 由 analyze-data／evaluate 那條線維護）。
   - 取材自步驟 5 matrix 中該 SQ 的候選 citekey，逐筆對照 success_criteria 篩選：只列真正支撐該 SQ 結論者，不把整份 bib 倒進 links。
   - **寫入者分工（單一寫入者，兩邊不重複寫）**：evidence-synthesis 走 `focused` 模式的 SQ，links 由**本 skill 在此步驟**寫入；走 `systematic`／`scoping`／`meta-analysis`（系統性回顧／統合分析路線，文獻本身即研究主體）的 SQ，links 改由 **evidence-synthesis 在其確定性檢核通過後**寫入，本 skill 只交付 matrix 候選清單，**不寫 links**。
4. **literature 時戳**：寫入 `state.literature: {updated_at: <日期>, mode: 全}`——peer-review 的 matrix 新鮮度檢查（逾六個月）讀此欄，取代不可靠的檔案 mtime。
5. **收尾申報**：「本階段更新：literature 搜尋與 matrix → <日期>；evidence synthesis → <pass/待執行>；文獻型 SQ links → <已補 N 條／由 evidence-synthesis 寫入>（另列 goals 變更，若有）；下一站：evidence-synthesis／evaluate」。
6. 收尾必記一筆 D#：追加 `decisions.yaml` 條目，`stage: lit-review`、`checkpoint: 階段收尾`，並填 `question`（本階段對應的問題層：`main` 或子問題 id 如 `SQ2`）、`issue`（只在這筆是該問題之下的執行問題時填，一句話）、`method`（對應該層的方法：main＝研究設計、SQ＝分析方法、有 issue＝解決該執行問題的做法）、`evidence`（本階段的指令、腳本路徑、fingerprint 或輸出檔路徑清單）；照建議原樣通過也要記。這一筆是進度時間軸的資料來源，沒記就不會出現在時間軸上。

## 增補模式

寫作或修訂途中只需加 1–2 篇文獻時（含 lit_anchors 補錨、novelty spot-check），**不重做全域搜尋**，只跑必要步驟：DOI 查證（加入 Zotero）→ 撤稿檢查 → 該篇精讀筆記 → matrix.md 補列 → 重匯 references.bib → 使舊 synthesis/audit 過期並跑增量 evidence-synthesis。**不觸發目標回訪**（增補多為下游具體需求驅動的局部更新，逐 SQ 回訪的訊噪比低），也不重寫既有 links；僅當新文獻確為某文獻型 SQ 的支撐證據、且已通過增量 evidence-synthesis 時，才依收尾第 3 點的格式與分工補入該 SQ 的 `cite:` links。同樣寫入 `state.literature: {updated_at, mode: 增補}` 並申報。目標是把寫作中斷成本降到最低。

## 規則

- `literature/references.bib` 中每筆必須真實存在且經查證；引用庫是白名單，寫作階段只能引用其中的文獻，之後要加文獻一律回到本 skill 走查證流程（增補模式即可）。
- Zotero 搜尋／匯入／撤稿與版本檢查的具體流程，以及「嚴禁憑記憶編造書目」的零捏造規則，見 `agents/literature-scout.md`，此處不重複。
- `goals[].links` 的 `cite:` 條目**只有一個寫入者**：focused → lit-review；systematic／scoping／meta-analysis → evidence-synthesis。任一支發現對方已寫入，不覆寫、不重複追加，以避免雙寫打架。
