---
name: write-manuscript
description: >
  This skill should be used when the user asks to 「寫論文」、「撰寫文稿」、「開始寫稿」、
  「寫中文稿」、"write-manuscript"、"draft the manuscript"，or wants to draft the
  Traditional Chinese manuscript for an academic-pipeline project.
metadata:
  version: "0.7.2"
---

# 撰寫中文稿

依已驗證 findings、通過反方審查且經使用者確認的 claims，以及可重現 evidence synthesis 撰寫繁體中文稿。

## 開寫硬關卡

1. `state.last_full_evaluation.result: pass`。
2. `analysis/claims.yaml confirmed: true`。
3. `check_claim_audit.py <root>` 通過，且 claims fingerprint 與 audit 一致。
4. route 所要求的 validation、data-audit、evidence-synthesis 與 prestudy integrity 均通過；定量專案另需 clean rerun fingerprint 與目前 inputs/results 一致。
5. 任一 blocker 時停止並回對應 skill；不得以文字潤飾掩蓋分析／證據缺口。

## 讀取材料

`project.yaml`、protocol、active plans、route、data-audit、manifest、results／等價 findings、validation、claims、claim-audit、interpretation、evidence synthesis、references、figure story/manifest、decisions。稿件不得消費未轉正 exploration outputs。

## 步驟

1. **段落級大綱**：每段標 SQ、claim id、results／finding key、validation V#、citekey、圖表與段落功能。結果順序對齊 figure story；限制段預先配置 qualified validation、data-audit conditional、blocked/dropped SQ 與 claim-critic 最強反方。使用者確認後才成稿。
2. **成稿至新版本** `manuscript/zh/vN.md`，不覆蓋舊版。圖說直接取 figure manifest 的 `caption` 欄位，figure-design 已寫入者不另行重寫。
3. **方法節**：依 protocol、sealed plans、scripts/report 與 manifest 寫；樣本流、剔除、插補與偏離須可追到 P#/D#。不得把 post-hoc amendment 描述成事前預註冊。
4. **結果節**：只報 active/current artifacts；本研究數字取 results.json 並加 `<!-- results.key -->`；整表加 `<!-- table:key -->`。推論性證據同時報 effect 與 uncertainty，不以裸 p 值作主句。results.json 缺效應量或不確定度鍵時，停下回呼 analyze-data 補算——新鍵須經 plan amendment 登記後才可使用，**不得在稿中自行換算或估算**。
5. **討論與結論**：固定四塊——主要發現詮釋／與文獻的對話／研究限制／未來方向。每個科學主張只能取 confirmed claims，句尾加 `<!-- claims.C# -->`；措辭不超出 strength，qualified validation 的 boundary 必須保留。文獻對話優先使用 audited lit_anchors——**有錨主張的標註段落至少引用其 lit_anchors 之一**（無錨主張豁免）——並處理 counterevidence。限制節如實揭露 qualified validation、data-audit conditional、blocked／dropped SQ、未排除的替代解釋與 claim-critic 最強反方。
6. **摘要**：字數依 `target.abstract_limit`；數字、claim strength、population/domain boundary 與正文一致；不得在摘要移除正文保留的核心限定。

## 數字標註與豁免（與 check_numbers.py 一致）

- **`display` 優先**：results.json 該筆有 `display` 欄位時，稿件數字必須與 `display` 字串**完全一致**，不得自行改寫精度；無 `display` 時依 `analysis.rounding` 的有效位數呈現，腳本按稿件顯示精度四捨五入比對。
- **完全豁免（腳本不檢查，不需 results 註解）**：
  - 年份（19xx／20xx）。
  - 結構性編號：前綴為 圖／表／式／第／章／節／附錄／樣本／Fig／Figure／Table／Eq／Equation／Section／Round／version／v 的數字（版本號如 `v2` 走此豁免）。
  - 行首清單編號（如「1.」「2、」）。
  - HTML 註解與 `[@citekey]` 內的數字；程式碼區塊、行內 code 與網址內的數字。
  - 通過整表比對的 `<!-- table:key -->` 表格區塊內的數字（不逐格標註）。
- **不豁免、但降級為 warning（需人工確認）**：
  - **引用他人文獻的數值**：不加 results 註解，但**同句（以句末標點切分）必須有 `[@citekey]`**——同句無 citekey 即視為未溯源的資料型數字，直接 blocker。
  - **結構性計數的裸整數**（如「3 個階段」）：列 warning 逐則確認；改用中文數字（「三個階段」）則不會被掃描。
- **blocker**：不在上述豁免內、又未標註 `<!-- results.key -->` 的資料型數字（含小數點、百分號、科學記號，或 5 位以上整數）。
- 此豁免定義與 check-consistency 的 `scripts/check_numbers.py` 完全對齊；腳本改版時同步本節，撰稿端不得自行假設更寬的豁免。

## 硬規則

- 新數字、新分析、新 citekey、新 claim 均不得在寫作中臨時創造；分別回 analyze-data、lit-review/evidence-synthesis、interpret-results/claim-audit。
- 表格由 script／figure-design 產生，不手改 cell。
- 探索性 claim 必須明示；預測結果不得寫成因果；質性結論不得冒充統計普遍化；模擬結論限於已驗證域。
- claims、validation、evidence 或 results 變更後，既有稿件 consistency 立即失效。
- **文風**：學術但流暢的繁體中文；避免翻譯腔（「被進行」、「作為一個」）與冗贅套語；句長有變化。
- 專有名詞首次出現附英文原文，並同步登錄 `project.yaml` 的 glossary。

## 收尾

經使用者確認後更新 SQ 的 `ms:` links 與 `state.zh_latest`。有 SI 素材先 write-supplementary，再執行完整 check-consistency。申報：「本階段更新：state.zh_latest → v<N>；下一站：write-supplementary／check-consistency」。

收尾必記一筆 D#：追加 `decisions.yaml` 條目，`stage: write-manuscript`、`checkpoint: 階段收尾`，並填 `question`（本階段對應的問題層：`main` 或子問題 id 如 `SQ2`）、`exec_issue`（只在這筆是該問題之下的執行問題時填，一句話）、`method`（對應該層的方法：main＝研究設計、SQ＝分析方法、有 exec_issue＝解決該執行問題的做法）、`evidence`（本階段的指令、腳本路徑、fingerprint 或輸出檔路徑清單）；照建議原樣通過也要記。這一筆是進度時間軸的資料來源，沒記就不會出現在時間軸上。
