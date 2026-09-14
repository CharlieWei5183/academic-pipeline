---
name: analyze-data
description: >
  This skill should be used when the user asks to 「分析資料」、「跑統計」、「做數據分析」、
  「先看看資料」、"analyze-data"、"run the analysis"，or wants to execute the
  formal or exploratory analysis stage of an academic-pipeline project.
metadata:
  version: "0.7.2"
---

# 資料分析

正式模式執行已封存的 analysis plan，產生 `analysis/results.json`、derived data、圖表與報告。此 skill 不再在對話中臨時發明「迷你預註冊」；計畫由 study-design 版本化，結果在 clean rerun、code-review 與 validate-results 全部通過後才可定案。

## 前置硬關卡（正式模式）

```bash
python3 <plugin>/skills/methodology-router/scripts/check_route.py <root>
python3 <plugin>/skills/integrity-check/scripts/check_integrity.py <root> --stage prestudy
python3 <plugin>/skills/study-design/scripts/check_plan.py <root> --require-confirmed
python3 <plugin>/skills/data-audit/scripts/check_data_audit.py <root>
```

任一 blocker 均停止。若 route 不含 `analyze-data`，改走 adapter 指定的等價產物，不硬套 results.json。

## 探索模式（分艙）

使用者要求「先看看資料」時，可委派 data-analyst `mode: exploratory`。產物全部置於 `analysis/exploration/`，只寫 `analysis/exploration-log.yaml`；不得寫 results.json、不得進正式 figures manifest、不得被稿件引用。資料權利、隱私與倫理仍不可因「探索」而略過。E# 轉正後必須新增／修改 SQ，建立新 plan，走完整正式流程。

## 正式流程

1. **鎖定執行契約**：讀 active plan、protocol、route、data-audit、data-profile 與 data-manifest。確認本次 SQ、plan_id、預宣告 outputs、robustness keys、data fingerprint 與 model_id。任何新增模型、改納排、改缺失值策略或新增正式鍵，先回 study-design 建 amendment，不得邊跑邊改考卷。
2. **資料流向建檔與品質確認（data-manifest）**：data-audit 已完成獨立稽核與 `analysis/data-profile.json`；本站不重做稽核，只把「原始 → 分析用」的樣本流向落帳。
   - 尚無 `analysis/data-manifest.yaml` 時先建骨架（只在本 skill 寫入；schema 見 `references/data-manifest-template.yaml`）：

     ```bash
     python3 <skill路徑>/scripts/init_manifest.py <root>
     ```

     origin、unit、known_issues 由使用者補；既有 manifest 不覆蓋，只列出 `data/` 中尚未登記的檔案。
   - 對照 data-audit 的處置結論逐檔檢視缺失值、離群值、單位一致性與樣本數，品質摘要與處置建議一併呈報。**有疑慮（如可疑離群值）必須先問使用者，不得自行剔除資料**；剔除或插補屬方向性選擇，記 D#——若牽動 estimand、納排或模型，先回 study-design 建 amendment。
   - 主分析執行前更新 manifest 的 `flow` 表（每條主分析路徑一列，尾端掛 results_key），每個清理／轉換步驟同步追加 `steps` 條目（affected 筆數與 reason，涉及取捨者連 D#）。筆數守恆（相鄰 flow 列之差＝對應 step 的 affected）由 `check_manifest.py` 把關。
   - 分工：**data-audit 負責獨立稽核與 data-profile；analyze-data 負責 `analysis/data-manifest.yaml` 的樣本流向與筆數守恆。**
3. **委派 data-analyst 執行**：
   - `data/` 唯讀；清理／轉換 script 寫入 `analysis/derived/` 並更新 manifest steps/flow；
   - 所有正式數字由 `analysis/scripts/` 產生；results key 必須在 active plan 預宣告；
   - 每個結果帶 `plan_id`、`model_id`、`data_fingerprint`、`script`、`description`；推論性結果帶效應量與明確不確定度欄位；
   - 交付 `analysis/scripts/run-order.txt`、`analysis/report.md` 與 figure manifest。
4. **結構與溯源檢核**：

   ```bash
   python3 <skill路徑>/scripts/check_results_schema.py <root>
   python3 <skill路徑>/scripts/check_manifest.py analysis/data-manifest.yaml <root> \
     --decisions decisions.yaml --results analysis/results.json
   python3 <skill路徑>/scripts/check_exploration.py analysis/exploration-log.yaml project.yaml <root> \
     --figures-manifest analysis/figures/manifest.json
   python3 <plugin>/skills/study-design/scripts/check_plan.py <root> --require-confirmed \
     --results analysis/results.json
   ```

5. **clean-room rerun（先於 code-review）**：

   ```bash
   python3 <skill路徑>/scripts/rerun_all.py <root> --mode <full|spot|off> \
     [--keys key1,key2] [--decision D-001] --report reviews/rerun-<SQ>-<序>.json
   ```

   暫存專案只複製 inputs；既有 results、derived、figures、reports、validation、manuscript 不會被帶入。fingerprint 覆蓋 raw data、完整 `analysis/scripts/`（含 helper modules）、run-order、protocol/plans、data profile/audit、manifest、route、分析設定與環境 lock。非標準輸入必須在對應 run-order 行明列，例如 `python3 scripts/analyze.py # tol=1e-10; inputs=config/model.yaml,models/frozen.bin`；未宣告的外部輸入不會進 clean room。未從零產生 results、輸入不安全／不存在或數值超差皆為 blocker。
6. **code-review**：rerun 通過後委派 reviewer-methods `mode: code-review`。材料只含 sealed plan、protocol、adapter、scripts、manifest、results schema 摘要、results key 與 rerun JSON 報告。code-review 證「實作忠實且正確」；不得把它當作結果穩健性驗證。blocker 未解不得前進。
7. **獨立結果驗證**：回呼 **validate-results**。statistical-validator 以獨立 scripts／診斷在 `analysis/validation/` 壓測結果；`fail` 回 study-design amendment／analyze-data，`qualified` 的限制必須一路傳到 claims 與稿件。
8. **結果契合評估與人工確認**：只有 rerun、code-review、validation 皆通過後，回呼 evaluate（result review）。將 validation 限制、report 與圖表一併呈使用者。使用者確認後才將 SQ 設為 addressed，links 寫 results keys 與 validation V#；否則 blocked/dropped 並記理由。

## results.json v0.7 最低契約

```json
{
  "effect_primary": {
    "value": 0.42,
    "unit": "unit",
    "kind": "inferential",
    "n": 128,
    "se": 0.11,
    "ci_level": 0.95,
    "ci_lower": 0.20,
    "ci_upper": 0.64,
    "statistic": 3.82,
    "df": 126,
    "p_raw": 0.0002,
    "p_adjusted": 0.001,
    "multiplicity_family": "primary_outcomes",
    "method": "...",
    "model_id": "M1",
    "plan_id": "SQ1-v1",
    "data_fingerprint": "...",
    "script": "scripts/analyze_sq1.py",
    "description": "..."
  }
}
```

表格沿用 `type: table / columns / rows`，同樣必帶 plan、model、data fingerprint、script 與 description。

## 失效規則

raw data、active plan、analysis settings、scripts、run-order、results 或環境 lock 任一變更，都使 rerun、code-review、validation、claim-audit、consistency 失效。補充分析必須用 amendment 與新 results key，不覆寫舊鍵。

## 收尾

更新 `state.analysis.rerun` 與 `state.analysis.validation`。申報：「本階段更新：clean rerun → <pass/waived>；validation → <pass/qualified>；SQ <id> → <status>；下一站：evaluate／interpret-results」。

收尾必記一筆 D#：追加 `decisions.yaml` 條目，`stage: analyze-data`、`checkpoint: 階段收尾`，並填 `question`（本階段對應的問題層：`main` 或子問題 id 如 `SQ2`）、`exec_issue`（只在這筆是該問題之下的執行問題時填，一句話）、`method`（對應該層的方法：main＝研究設計、SQ＝分析方法、有 exec_issue＝解決該執行問題的做法）、`evidence`（本階段的指令、腳本路徑、fingerprint 或輸出檔路徑清單）；照建議原樣通過也要記。這一筆是進度時間軸的資料來源，沒記就不會出現在時間軸上。
