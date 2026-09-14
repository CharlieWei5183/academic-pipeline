---
name: project-init
description: >
  This skill should be used when the user asks to 「開新研究專案」、「初始化專案」、
  「建立論文專案」、「開始新論文」、"project-init"、"start a new research project"，
  or wants to set up the folder structure and project.yaml for the academic pipeline.
metadata:
  version: "0.7.3"
---

# 專案初始化

建立 academic-pipeline v0.7 專案骨架、研究問題分解與可追蹤狀態。此站只建立「要研究什麼」；研究方法類型、正式 protocol 與分析計畫分別交由 methodology-router 與 study-design，避免在初始化時過早鎖死方法。

## 步驟

1. **確認專案位置**：若已有 `project.yaml`，不得直接覆蓋；先判斷是繼續、遷移或另建專案。
2. **訪談使用者**（已知的不重問）：
   - 主研究問題、暫定題目與領域；
   - 資料、材料、實驗、訪談、文獻或模擬的現況；
   - 預期知識任務：估計／因果、預測、理解經驗、證據綜整、模擬、理論或混合方法；
   - 目標期刊／文章類型／格式限制（未知可留空）；
   - 分析軟體、alpha、審稿嚴格度與治理限制。
3. **目標分解＋拆解審**：提案 2–6 個互補 SQ。每個 SQ 包含 `why`、`evidence`、結果中立的 `success_criteria` 與初始 `status: open`。寫入前回呼 evaluate 的 `decomposition-review`；意見與草案一併交使用者裁定，推翻建議記 D#。有條件通過即可建立專案。
   - **主問題與附錄問題分離（不混列）**：`sub_questions` 只放問「現象」的問題（X 與 Y 是否關聯、機制、邊界）。問「分析本身」的穩健性／敏感度／跨方法問題——那些 **defend 主答案而非產生新答案、報在附錄／SI** 的——一律列入 `goals.appendix_questions`（id 用 `AQ#`），不得混進 `sub_questions` 灌大 SQ 數。判準：換方法／換設定下主結果是否維持、跨方法收斂或分歧 → 附錄問題。附錄問題不進 `decomposition-review` 的主問題覆蓋判斷，但仍受 `check_coverage.py` 逐項 integrity 檢查（終態、links 有效）。無附錄問題時 `appendix_questions: []`。
4. **建立結構**：

   ```text
   <root>/
   ├── project.yaml
   ├── decisions.yaml
   ├── DECISIONS-TIMELINE.md   # 自動產生（status/scripts/render_decisions_timeline.py），不要手動編輯
   ├── PROGRESS.ir.json        # 自動產生（status/scripts/render_progress.py 的 IR），不要手動編輯
   ├── PROGRESS.html           # 自動產生（同上，自含 HTML 里程圖），不要手動編輯
   ├── protocol/
   ├── methodology/
   ├── integrity/
   ├── data/
   ├── analysis/
   │   ├── scripts/  plans/  derived/  figures/  validation/  exploration/  integration/
   ├── literature/notes/
   ├── manuscript/zh/  manuscript/en/
   ├── reviews/
   ├── evaluations/
   └── submission/
   ```

5. **建立決策日誌**：建立空的 `decisions.yaml`（研究決策的「為什麼」的單一落點，既有帳本記「是什麼」）。append-only：修正舊決策以新條目填 `supersedes`，不改寫舊條目。收尾強制記錄的規則見各 skill 收尾：每個 pipeline stage skill 收尾時各追加一筆 `checkpoint: 階段收尾` 的條目，照建議原樣通過也要記。每筆決策落在三層之一——主問題（`question: main`）、子問題（`question: SQ2` 等 id）、或某個問題之下執行時發生的執行問題（該 `question` 再加 `exec_issue`）；`method` 只有一欄，意義跟著那一層走（main＝研究設計、SQ＝分析方法、有 exec_issue＝解決該執行問題的做法）。

   ```yaml
   # 決策日誌——研究決策的「為什麼」的單一落點（既有帳本記「是什麼」）。
   # 只記四類：(a) 人工確認點附帶的取捨、條件或修改（照建議原樣通過可不記）;
   # (b) 使用者推翻 agent 建議（註明理由）; (c) 方向性選擇（資料剔除或插補、
   # goals 增修、審稿意見反駁定案、保險閥裁決、persona profile 核可）;
   # (d) 階段收尾：每個 pipeline stage skill 收尾時各記一筆，checkpoint 固定寫「階段收尾」，
   # 照建議原樣通過也要記——(a) 的「可不記」不適用於 (d)。
   # v0.7 新關卡同樣適用：methodology route 的選定與推翻、protocol/plan amendment、
   # data-audit 處置、validation qualified 的接受、claim 分級的推翻、integrity 例外。
   # 條目 schema：
   #   - id: D-014            # D-<三位連號>
   #     date: "2026-07-10"   # ISO 8601（YYYY-MM-DD），加引號寫成字串
   #     stage: analyze-data  # 產生決策的 skill 名
   #     checkpoint: 結果評估確認
   #     decision: ""         # 一句話
   #     reason: ""           # 展開的理由
   #     rejected: ""         # 選填：被否決的替代方案
   #     question: ""         # 選填：這筆決策落在哪一層：main（主問題）、SQ2／AQ1（子問題 id），或自由文字
   #     exec_issue: ""            # 選填：只在這筆是該 question 之下的執行問題時填（一句話）
   #     method: ""           # 選填：對應 question 那一層的方法（main＝研究設計；SQ＝分析方法；有 exec_issue＝解決該執行問題的做法）
   #     evidence: []         # 選填：執行憑據——指令、腳本路徑、fingerprint 或輸出檔路徑（字串清單）
   #     links: []            # SQ / results 鍵 / claim / issue / E# / P# / V# / D#
   #     supersedes: ""       # 選填：修正舊決策時填原 D#
   decisions: []
   ```
6. **生成 project.yaml**：以 `references/project-template.yaml` 為模板，保留 `pipeline.version: 0.7.3`。建立 goals 快照與 glossary。
7. **收尾與路由**：摘要 SQ 與拆解審結果；下一站固定為 **methodology-router**，其後才依 route 走 `integrity-check (prestudy) → study-design → data-audit`。不得在 v0.7 新專案中直接跳到正式 analyze-data。

## 規則

- `data/` 唯讀；任何清理均由後續 script 寫入 `analysis/derived/`。
- goals 是單一事實來源；任何增刪改均須使用者確認，結構性變更重跑拆解審並使 study-design、validation、claims 與稿件關卡過期。
- 推翻既有決策時（任何 skill）：先呈示原 D# 條目，經使用者確認後才以 `supersedes` 條目落地——跨 session 防翻案的主要機制。
- 專案內所有路徑引用一律相對於專案根目錄。
- 舊專案不自動升版。遷移到 v0.7 時先備份，再由 status 盤點缺失 artifacts；一旦將 `pipeline.version` 設為 0.7.3，新硬關卡即生效。`appendix_questions` 為附加、可選欄位（缺省視同 `[]`），對舊專案回溯相容。
- 收尾申報：「本階段更新：pipeline.version → 0.7.3；goals 寫入 <N> 個 SQ；下一站：methodology-router」。
- 收尾必記一筆 D#：追加 `decisions.yaml` 條目，`stage: project-init`、`checkpoint: 階段收尾`，並填 `question`（本階段對應的問題層：`main` 或子問題 id 如 `SQ2`）、`exec_issue`（只在這筆是該問題之下的執行問題時填，一句話）、`method`（對應該層的方法：main＝研究設計、SQ＝分析方法、有 exec_issue＝解決該執行問題的做法）、`evidence`（本階段的指令、腳本路徑、fingerprint 或輸出檔路徑清單）；照建議原樣通過也要記。這一筆是進度時間軸的資料來源，沒記就不會出現在時間軸上。
