# 測試資產

改動任何 skill / agent / script 後，用這裡的資產驗證沒有退步。

## 1. trigger-evals.yaml

觸發測試：每筆是「使用者語句 → 應觸發的 skill（或 none）」。人工或用 skill-creator 的 eval 方法跑：把語句丟給安裝了本 plugin 的新對話，檢查觸發是否符合 `expect`。

## 2. mini-project/ — 迷你端到端測試專案

一個縮小版專案，`manuscript/`、`goals` 與 `analysis/claims.yaml` 內**故意埋了已知錯誤**，用來驗證各檢核腳本。

執行：

```bash
cd tests/mini-project
python3 ../../skills/check-consistency/scripts/check_numbers.py manuscript/zh/v1.md analysis/results.json
python3 ../../skills/check-consistency/scripts/check_citations.py manuscript/zh/v1.md literature/references.bib
python3 ../../skills/translate-en/scripts/check_markers.py manuscript/zh/v1.md manuscript/en/v1.md
python3 ../../skills/evaluate/scripts/check_coverage.py project.yaml analysis/results.json literature/references.bib
python3 ../../skills/interpret-results/scripts/check_claims.py analysis/claims.yaml project.yaml analysis/results.json literature/references.bib
python3 ../../skills/revise/scripts/diff_versions.py manuscript/zh/v1.md manuscript/zh/v1.md --sections
```

### 預期結果（黃金答案）

**check_numbers**（exit 1，3 blockers）：

- BLOCKER：`0.045 ≠ 0.0321 (results.ttest_ab_p)` — 標註數字與鍵值不符
- BLOCKER：`鍵名不存在: results.effect_size`
- BLOCKER：`資料型數字未標註溯源: 12.5%`
- WARNING：`4.7`（同句有 citekey，引用他人數值）
- 不得誤報：`2024`（年份）、`圖 1`（圖編號）、`3.42 <!-- results.mean_A -->`（正確標註）

**check_citations**（exit 1，1 blocker）：

- BLOCKER：`@wang2025missing` 不存在於 bib
- 不得誤報：`@smith2023effect`

**check_markers**（exit 1，2 差異）：

- `results註解 "mean_A"`：zh x1 vs en x0
- `citekey "wang2025missing"`：zh x1 vs en x0
- 註：腳本同時比對 `<!-- claims.* -->` 標註；mini-project 兩版皆無主張標註，不得因此新增差異

**check_coverage**（exit 1，2 blockers）：

- BLOCKER：`SQ2: 狀態非終態 (open)`
- BLOCKER：`SQ2: link 無效, results.json 無鍵 "loading_rate_effect"`
- 不得誤報：SQ1（addressed、三條 links 皆有效）
- 加 `--sq SQ1` 時（輕量模式）：0 blocker，exit 0

**check_claims**（exit 1，4 blockers）：

- BLOCKER：`C2: evidence 無效, results.json 無鍵 "effect_size"`
- BLOCKER：`C3: sq 無效, goals 無 "SQ9"`
- BLOCKER：`C3: strength 無效 "proven"`
- BLOCKER：`C4: causal 級 basis 為空`
- WARNING：`confirmed: false`（主張尚未經使用者確認）
- 不得誤報：C1（sq、strength、三條 evidence 皆有效）
- 加 `--manuscript manuscript/zh/v1.md` 時：blocker 數不變，另出現 4 條「主張未見於稿件」warning（稿件無 claims 標註）

**diff_versions**（自我比對煙霧測試，exit 0）：

- 同版比對 `--sections` 輸出 `無變更`；改動任一節後重跑須列出該節

腳本輸出與上述不符＝退步。

## 3. 新腳本（v0.6）煙霧測試——回溯相容驗收

mini-project 沒有任何 v0.6 新帳本（issue-ledger、decisions、exploration-log、data-manifest、run-order）。對它跑下列腳本，**全部應列 INFO 提示可補建並 exit 0，不報錯**（總則驗收：無新產物時行為與現行版本相同）：

```bash
cd tests/mini-project
python3 ../../skills/revise/scripts/check_ledger.py reviews/issue-ledger.yaml project.yaml
python3 ../../skills/status/scripts/check_decisions.py decisions.yaml project.yaml
python3 ../../skills/analyze-data/scripts/check_manifest.py analysis/data-manifest.yaml .
python3 ../../skills/analyze-data/scripts/check_exploration.py analysis/exploration-log.yaml project.yaml .
python3 ../../skills/evaluate/scripts/check_coverage.py project.yaml analysis/results.json literature/references.bib --history evaluations
# 裁決史應全列「無史料」；check_coverage 黃金答案不變
```

`check_decisions.py` 自 0.11.0 起另做階段覆蓋檢查：讀 `project.yaml` 的 `state`，某 stage 已有紀錄（判準見腳本的 `STATE_COVERAGE` 表）而 `decisions.yaml` 沒有任何該 stage 條目時列 `WARNING <stage>: ... 無此 stage 條目`；mini-project 沒有 `decisions.yaml`，腳本在讀 `state` 之前即列 INFO 並 exit 0，故此處不會出現該 WARNING。新欄位 `method`／`problem`／`evidence` 為選填，舊條目缺欄位不報，exit code 契約不變。

typeset 建置（需 pandoc；舊版 pandoc 無 citeproc 時應優雅降級並警示）：

```bash
python3 ../../skills/typeset/scripts/build_docx.py manuscript/en/v1.md --bib literature/references.bib --reference-doc ../../skills/typeset/references/reference.docx --out /tmp/build
python3 ../../skills/typeset/scripts/anonymize.py manuscript/en/v1.md --out /tmp/build/anonymous.md
python3 ../../skills/typeset/scripts/check_build.py /tmp/build --project project.yaml --source manuscript/en/v1.md
```

check_claims 對 mini-project 的黃金答案（第 2 節）不變；新增兩行 INFO（無 origin 欄、無 lit_anchors 欄——探索性連結與文獻錨點檢查略過）。

## 4. v0.7 端到端煙霧測試

```bash
python3 tests/run_v07_smoke.py
```

測試會在暫存目錄動態建立專案並驗證：

- 七種 methodology adapter 均可建立、封存及檢核 route／protocol／plan；
- qualitative adapter validation 的 source fingerprint 與必要 checks；
- quantitative data profile、data-audit、manifest、results schema；
- clean-room rerun 能通過正常案例，且 no-op script 無法靠既有 results.json 假通過；
- independent validation（含完整 analysis-source fingerprint）、evidence protocol/synthesis（含實際 notes／bibliography source fingerprint）、claims 與 claim-audit；
- prestudy／presubmission integrity；
- 中文與英文 consistency gate、presubmission 非循環失效，以及稿件、validation evidence、declared analysis input 改動後的 stale fingerprint 阻擋。

## 5. v0.7.1 語意回歸測試

v0.7.0 的新功能 smoke test 沒有覆蓋四個跨檔案舊契約；0.7.1 新增：

```bash
python3 tests/run_v071_regressions.py
```

必須驗證：

- v0.6 已有 `{last_consistency: {result: pass, version: vN}}` 時，`check_gate.py` 相容模式通過，不要求 `gate_fingerprint`／`report`；明確 `--strict` 或 0.7.x 專案仍阻擋缺欄。
- editor 四段分數帶、新穎性／定位敘事子問題及 `REVIEW_SCORE` block 均存在。
- 每個完整 panel 輪可由 `record_review_score.py` 寫入且依 round 去重；兩輪改善不足時 `check_ledger.py` 確實輸出邊際遞減保險閥。
- README、status、peer-review、revise 都保留中文潤稿掛點（0.10.0 起為內建 `chinese-academic-editing`；skill 名的當期契約由 run_v0100 pin）。

## run_v072_regressions.py

驗證 v0.7.2 回填的 v0.6 契約：agent 層紅線（code-review 風格限 suggestion、fact-checker 的 Bash 權限與 blocker 門檻、data-analyst 四條核心原則）、skill 層規則（evaluate 短路規則、decisions.yaml 三類記錄、write-manuscript 數字豁免清單）、project-template 的欄位註解密度，以及文獻型 SQ 的 `cite:` links producer——包含 `check_coverage.py --evidence` 的四種情境實測：不傳旗標（回溯相容）、citekey 已審查（通過）、citekey 未審查（BLOCKER）、evidence 檔不存在（略過）。

檔案數與 frontmatter 檢查抓不到這類跨檔案語意退步，因此以錨點字串斷言。回填條款若被再次刪除，本測試會失敗。

## run_v081_regressions.py

v0.8.1 的兩個確定性缺陷修補，以**實際執行腳本**斷言行為（錨點字串比對抓不到這類 bug）：

- `check_results_schema.py`：superseded plan 不得宣告結果鍵——跨 SQ 撞鍵時不再從 active plan 手上搶走歸屬；v1 宣告、v2 未再宣告的鍵，blocker 須指向「未在 sealed active plan 預宣告」而非誣賴 result 的 `plan_id`；無 `status` 欄與無 `active` map 的舊 index 行為不變。
- `rerun_all.py`、`check_gate.py`、`plan_common.content_hash`：`project.yaml`／plan 內的裸日期（`routed_at: 2026-07-20`、`created_at: 2026-07-14`）不得崩潰，且與有引號版本產生**相同** fingerprint／`content_hash`。
- 全 repo 掃描：範本與文件不得再出現裸日期寫法（`*_at`／`date`／`*_on`）。
- `methodology-router/SKILL.md` 範例已改為有引號寫法。
- `plugin.json` 版號單調 `>= 0.8.1`（當期精確 pin 由最新一支回歸測試負責），且 `run_v080_regressions.py` 已改為單調斷言。

注意 `run_v07_smoke.py` 寫入的 `routed_at` 是 Python 字串（序列化成有引號的 YAML），因此**不會**覆蓋無引號路徑；缺陷 2 能在全綠狀態下存活正是這個原因。測試若只走自己寫入的那條路徑，就守不住文件所教的那條。

## run_v0100_regressions.py

v0.10.0 把中文潤稿站由外部 user skill 升為內建 `chinese-academic-editing`，以跨檔案錨點斷言：

- 內建 skill 存在，且掛點合約完整——只改語言呈現、不得動數字／markers／citekey／claim strength／validation boundary；潤稿後 full `check-consistency(zh)`；不可取代★中文人工定稿。
- **語域分野**：寫死「去 AI 味不等於改得像講話」與「像期刊論文」，避免退回外部 `chinese-deai-editing` 的口語尺；且刻意不含 claim 強度調整與起草模式。
- **Layer 4（結果與討論的陳述規格）**的十二個規則錨點：不以裸 p 值作主句、效果量與不確定度同時報、缺鍵回 `analyze-data` 且不得自行換算、精度以 `display`／`analysis.rounding` 為準、限制節不得改成正面語氣、摘要不得移除正文核心限定、強度對照表「跨級一律不動」。這些全部錨定 `write-manuscript` 與 `check_numbers.py` 的既有契約——**Layer 4 若被改寬，本測試會失敗**。
- README／status／peer-review／revise 四處掛點改為內建，且 peer-review／revise 不再把外部 `chinese-deai-editing` 當成中文潤稿站；潤稿後 gate 未被放寬。
- trigger-eval 新增四條例句，且 `write-manuscript`／`translate-en`／`check-consistency` 的既有歸屬未被搶走。
- README skills 數為 26；`plugin.json` 精確 pin `0.10.0`，`run_v090_regressions.py` 已改為單調斷言。

有牙驗證：未修補版本下 `test_hook_wording_builtin`／`test_trigger_evals_no_collision`／`test_docs_and_version` 三段各自失敗；只放 skill 檔而不改掛點與文件時，前兩段仍失敗。

## run_v0110_regressions.py

v0.11.0 為進度時間軸補齊 `decisions.yaml` 的資料來源，以錨點字串與實際執行 checker 兩種方式斷言：

- `project-init/SKILL.md` 的 schema 註解含 `method:`／`problem:`／`evidence:` 三個選填欄位與「階段收尾」類別。
- `check_decisions.py` 的 `STAGES` 含 `debug-pipeline`，且匯出 `STAGE_CLOSE_CHECKPOINT`。
- 在暫存目錄動態建最小專案實跑 checker：`state.study_design.result: pass` 而 `decisions.yaml` 只有 `project-init` 條目 → exit 0 且 stdout 含 `WARNING study-design` 與「無此 stage 條目」；補一筆 `stage: study-design`、`checkpoint: 階段收尾`、三個新欄位齊全的條目 → 該 WARNING 消失且「階段收尾條目: 1/2」；舊格式條目（無新欄位、裸日期）→ exit 0、無任何關於新欄位的 WARNING；`evidence: "not-a-list"` → 有 WARNING、仍 exit 0。暫存目錄測試結束自動清除。
- 22 個目標 SKILL.md 每一份都含「收尾必記一筆 D#」與 `checkpoint: 階段收尾`；`status`、兩個潤稿站、`debug-pipeline` 不含該句。
- README 含 `run_v0110_regressions.py`；CHANGELOG 含 `0.11.0`。
