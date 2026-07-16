---
name: evaluate
description: >
  This skill should be used when the user asks to 「評估目前進度」、「評估這個子問題」、
  「研究做夠了嗎」、「整體評估」、「審一下子問題拆解」、"evaluate"、"goal-fit evaluation"，
  or when another academic-pipeline skill requests decomposition, design-fit, result-fit, or full goal-fit evaluation.
metadata:
  version: "0.7.3"
---

# 目標契合評估

本 skill 只回答「現有證據是否回答已宣告的 SQ／主問題」。方法設計由 reviewer-methods、執行可重現性由 rerun、結果穩健性由 statistical-validator、主張強度由 claim-audit 負責，互不取代。報告格式與判準集中於此，各階段回呼時不得長出變體。

## 前置

定位並讀取 `project.yaml` 的 `goals`。缺 goals → 停止，建議先跑 project-init 的目標分解（`decomposition-review` 檔別除外——它評的正是 goals 草案）。

**硬前置（依檔別；未滿足即停止，不啟動 evaluator）**：

- `result-fit`：對應結果須先通過 results schema、clean rerun、code-review 與 validate-results；`qualified` validation 必須隨材料提供限制。
- `full`：route 指定的 gates 均已完成；分析型 SQ 不得只靠 `status: addressed`，必須有 results 與 V# links；文獻型 SQ 必須有已審查 evidence synthesis links。

## 範圍與深度（rubric 檔別）

- **decomposition-review**：評「考卷出得好不好」——主問題 → SQ → success_criteria 的完整、互斥與可判定性。觸發點兩個：（a）project-init 步驟 3——SQ 草案成形後、寫入 goals 前；（b）goals **結構性變更**時（增刪多個 SQ、或改動主問題拆法；單句措辭微調不觸發）——含 revise 動 goals 與 lit-review 目標回訪產生的結構性增修。**範圍限 `sub_questions`**：`appendix_questions`（穩健性／敏感度／跨方法）不進主問題的完整／互斥判斷——它們 defend 主答案而非拆解主問題；判它們是否*本該*是 SQ（把穩健性偽裝成研究問題灌 SQ 數，或把真研究問題誤降附錄）屬本檔別的順帶檢視。
- **design-fit**：study-design 草案時，輕量檢查 plan 是否對準 SQ；不取代 reviewer-methods 的方法效度審。**單一 SQ 的新增或修改（含 E# 轉正）在此順帶檢視兩項**：與既有 SQ 的互斥、criteria 可判定——成本近零，不觸發完整 decomposition-review。
- **result-fit**：正式分析結果確認前，檢查 validated results 是否滿足該 SQ 的 success_criteria。
- **full**：所有 SQ 終態後的開寫關卡（亦用於 revise 動過 goals 之後、使用者要求整體評估）。

**升檔規則（可升不可降）**：承重 SQ、非標準方法、資料品質 `conditional`、或 `review.strictness: harsh` → 該 SQ 的輕量評升為 full rubric 檢視。整體評估永遠完整。

**模型檔位（委派時傳參數）**：例行輕量評（design-fit、result-fit、單 SQ 點名）傳 `model: sonnet`；full、升檔情形與 decomposition-review 維持 opus——忘記傳參數的失手方向是偏貴，不是關卡變鬆。

## 步驟

### 第一層：腳本（機械，先跑）

```bash
python3 <skill路徑>/scripts/check_coverage.py project.yaml analysis/results.json literature/references.bib \
  [--sq SQ2] [--manuscript <稿件.md>] [--evidence literature/evidence-synthesis.yaml] \
  --snapshot evaluations/goals-snapshot.json --history evaluations
```

檢查：SQ 終態覆蓋、links 有效性（`--evidence`：`cite:` 的 citekey 必須是 evidence-synthesis 已審查的 `studies[].citekey`，否則 blocker——封死「在 bib 裡但沒過篩選／偏誤評估」的文獻充當證據鏈；`literature/evidence-synthesis.yaml` 存在時一律帶上此旗標）、addressed 卻無 links、**goals 快照比對**（防悄悄改考卷；有差異須向使用者逐條確認；快照涵蓋 `sub_questions` 與 `appendix_questions` 兩者）、**per-SQ 裁決史摘要**（解析 `evaluations/<SQ id>-*.md` 的固定裁決區塊，每 SQ 一行：歷次裁決序列與最近一次未通過主因；無史料列「無史料」，不報錯）、最近一筆拆解審（decomp-*）裁決。**附錄問題（`appendix_questions`）另段呈示**：受同一套逐項 integrity 檢查（終態、links 有效、addressed 須有 links），但不計入主問題覆蓋、不進裁決史／稿件收錄檢查——其角色是 defend 主答案，不是主問題的一塊拼圖。

**短路規則**：`full` 模式下腳本若有 blocker → **直接判未通過，不啟動 evaluator agent**（省 token，也避免在破損材料上做判斷）。

### 第二層：evaluator agent（判斷力）

委派 **evaluator**，材料**只含**：goals（或指定 SQ／SQ 草案）、sealed plan、data-audit、validated results 摘錄、validation limitations、evidence synthesis、對應 report／文獻矩陣節錄、rubric 檔別、strictness、**該 SQ 的裁決史一行（不附歷次報告全文**——只給結果序列防照抄前輪理由，給序列讓重複失敗被看見）。**不提供**寫作或提案過程的對話脈絡。

`decomposition-review` 材料**只含**：主問題與 SQ 草案（或變更 diff）、資料／材料概況摘要（project-init 步驟 2 訪談產物）、matrix 節錄與 novelty statement（已存在時）；**矩陣尚未建立時，材料強制註明「文獻矩陣未建，覆蓋性判斷為初步」**——文獻後目標回訪是該判斷的第二次機會。

**Fallback**：無法啟動 subagent 的環境下，改為依 evaluator 定義檔的判準清單逐項自評，報告開頭標示「⚠ 自評（無獨立 evaluator）」。

## 輸出與狀態更新

- 報告存檔：輕量（design-fit／result-fit）`evaluations/<SQ id>-<序>.md`；完整 `evaluations/full-<序>.md`；拆解審 `evaluations/decomp-<序>.md`。**報告開頭固定引用該 SQ 的裁決史一行**。結尾必為固定裁決區塊（通過／有條件通過／未通過＋分流建議；拆解審為通過／有條件通過／未通過＋逐 SQ 意見）。
- **連續同因分流**：同一 SQ 連續兩次未通過且主因同類 → 本次裁決區塊**強制附分流建議**（回設計、補資料／證據，或如實轉 blocked／dropped），不得只叫同一分析再跑一次；使用者的裁決記入決策日誌（D#）。強制的是附建議，不是停止——SQ 迴圈每輪有人在環中，不設保險閥硬停（與審稿迴圈保險閥的刻意差異，那裡輪內無人）。
- **拆解審不是凍結關卡**：有條件通過即可放行寫入 goals——資訊最少的階段不追求完美拆解，goals 變更管道照舊暢通。使用者推翻拆解審意見記 D#（推翻 agent 建議類）；照建議通過可不記。
- SQ 狀態變更：evaluator 只給建議；**經使用者確認後**由本 skill 寫入 `goals`。分析型 SQ 只有在 validation `pass`／`qualified` 且使用者確認後才可轉 addressed；否則 blocked／dropped 並記理由。
- `full` 通過 → 更新 `state.last_full_evaluation: {id: "full-<序>", result: "pass"}`。
- goals 變更時，使 plans、validation、claims、稿件 consistency 依影響範圍失效。
- **收尾更新快照**：本輪檢核與使用者逐條確認完成後，重跑第一層腳本並加 `--update-snapshot`，把現行 goals 寫入 `evaluations/goals-snapshot.json`——確認過的改動才進快照，下一輪的比對基準才乾淨。
- 收尾申報一行：「本階段更新：<SQ status／state.last_full_evaluation> <舊值>→<新值>（無則「無狀態變更」）；下一站：<skill 名>」。

## 規則

- goals 是單一事實來源：本 skill 之外不得修改 status；任何修改都經使用者確認。
- **主問題與附錄問題分離**：`full` 的目標覆蓋只以 `sub_questions` 判定「主問題答了沒」；`appendix_questions`（穩健性／敏感度／跨方法）defend 主答案、報在附錄／SI，不能拿它們的 addressed 去補主問題的覆蓋缺口，也不因主問題未答就用附錄結果頂替。附錄問題若揭露與主結果的分歧，依結果中立原則並陳、不藏。
- **評估結果中立**：以「答了沒」論，不以結果方向論。
- 方法效度不歸本 skill——那由 study-design／analyze-data 的 reviewer-methods 設計審與 code-review 把關，結果穩健性由 validate-results 把關；本 skill 只評目標契合。
