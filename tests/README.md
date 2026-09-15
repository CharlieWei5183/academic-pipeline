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

`check_decisions.py` 自 0.11.0 起另做階段覆蓋檢查：讀 `project.yaml` 的 `state`，某 stage 已有紀錄（判準見腳本的 `STATE_COVERAGE` 表）而 `decisions.yaml` 沒有任何該 stage 條目時列 `WARNING <stage>: ... 無此 stage 條目`；mini-project 沒有 `decisions.yaml`，腳本在讀 `state` 之前即列 INFO 並 exit 0，故此處不會出現該 WARNING。新欄位 `question`／`exec_issue`／`method`／`evidence` 為選填，舊條目缺欄位不報，exit code 契約不變；`question` 指向的 `SQ#`／`AQ#` 須存在於 `goals`（兩個清單都空時只列 INFO），`exec_issue` 非空而 `question` 空時 WARNING。

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

- `project-init/SKILL.md` 的 schema 註解含 `question:`／`exec_issue:`／`method:`／`evidence:` 四個選填欄位（依此順序、置於 `links` 之前）、「階段收尾」類別，與步驟 5 正文的三層語意（主問題／子問題／執行問題，`method` 跟著那一層走）。
- `check_decisions.py` 的 `STAGES` 含 `debug-pipeline`，且匯出 `STAGE_CLOSE_CHECKPOINT`。
- 在暫存目錄動態建最小專案實跑 checker：`state.study_design.result: pass` 而 `decisions.yaml` 只有 `project-init` 條目 → exit 0 且 stdout 含 `WARNING study-design` 與「無此 stage 條目」；補一筆 `stage: study-design`、`checkpoint: 階段收尾`、三個新欄位齊全的條目 → 該 WARNING 消失且「階段收尾條目: 1/2」；舊格式條目（無新欄位、裸日期）→ exit 0、無任何關於新欄位的 WARNING；`evidence: "not-a-list"` → 有 WARNING、仍 exit 0。暫存目錄測試結束自動清除。
- `exec_issue` 非空而 `question` 空 → `WARNING D-002: exec_issue 須掛在某個 question 之下`；`question: SQ9` 而 `goals` 無此 id → `WARNING D-002: question 指向不存在的子問題 "SQ9"`；`sub_questions` 與 `appendix_questions` 都空 → 只列 INFO 不驗；`AQ1` 列於 `appendix_questions` 時視為存在。
- 22 個目標 SKILL.md 每一份都含「收尾必記一筆 D#」、`checkpoint: 階段收尾` 與 `question`／`exec_issue`／`method`／`evidence` 四欄的固定措辭，且不再出現舊欄位名；`status`、兩個潤稿站、`debug-pipeline` 不含該句。
- README 含 `run_v0110_regressions.py`；CHANGELOG 含 `0.11.0`。

階段 2 在同一檔追加 `render_decisions_timeline.py`（決策時間軸 renderer；開發中曾名 `render_progress.py`、產出曾名 `DECISIONS-TIMELINE.md`）的測試，全部以 `tempfile.TemporaryDirectory` 建 fixture、讀磁碟上實際產出的 `DECISIONS-TIMELINE.md` 斷言，結束自動清除：

- 欄位完整專案（3 筆四軸齊全、其中一筆 `links: [results.k1]`、一筆有 `exec_issue`）→ 表格 3 列、統計「共 3 筆記錄，其中 3 筆有完整四軸」、問題欄分別為 `main`／`SQ1`／`SQ1 › <exec_issue>`、`k1` 那列含 fixture 的 `script`／`run_id`／`data_fingerprint`、mermaid 區塊為 `gantt`（section 順序 `main`→`SQ1`、section 內依日期升冪、每列 `milestone, <日期>, 0d`）；執行前後 fixture 逐檔 sha256 相同、只多出 `DECISIONS-TIMELINE.md`；產出無 BOM、無 `\r`、檔尾恰一個換行；重跑除「產生時間」外相同。
- 舊格式專案（只有必填欄、缺 `date`、缺 `stage`）→ exit 0、三列都在、對應欄顯示 `unknown`、缺日期那列排最後、「共 3 筆記錄，其中 0 筆有完整四軸」，且不用 `checkpoint`／`decision` 代填。
- `exec_issue` 非空而 `question` 缺 → 問題欄「unknown › <exec_issue>」、問題軸不計、不算完整四軸；JSON rows 的 `question` 為 `unknown`、`exec_issue` 為原文。
- `decisions: []` 與沒有 `decisions.yaml`（同時缺 `project.yaml`／`results.json`）→ exit 0、「共 0 筆記錄」、表頭存在、無 mermaid 區塊、有「無記錄」。
- `--dry-run` → 目錄檔案清單與雜湊完全不變、無 `DECISIONS-TIMELINE.md`、stdout 含 `## 記錄表`；`--dry-run --json` 只印 JSON。
- `--json` → stdout 可 `json.loads`，`n_total`／`n_complete`／`len(rows)`／`axes`（鍵為 `date`／`method`／`question`／`evidence`）／`sources`／`mermaid` 與 fixture 一致，`rows[0]` 有全部欄位（含 `question`、`exec_issue`）；單獨使用仍寫檔。
- `method` 含半形 `:` → exit 0、表格仍有該列、檔內無 ```` ```mermaid ```` 而有「時間軸略過」與該 id；`question` 含半形 `:` → 同樣略過並註明 section 名。
- gantt section 順序：fixture 含 `main`、`SQ2`、`SQ10`、`AQ1`、自由文字、缺 question → 斷言 section 序為 main, SQ2, SQ10, AQ1, 自由文字, unknown（整數序，非字串序）；缺 date 與非 ISO date 的列不入圖、圖下「無日期未入圖：D-007、D-008。」、JSON `mermaid.undated_ids` 一致；全部列都無已知日期 → 無 ```` ```mermaid ```` 而有「無已知日期的記錄」。
- `results.<key>` 找不到 → 憑據含「results.json 無此鍵」；無 `results.json` → 含「無 results.json」。
- 根目錄不存在／`decisions.yaml` 無法解析 → exit 2、無 traceback、不落檔。
- 登記錨點：README、`project-init` 步驟 4 樹、`status` SKILL.md（frontmatter 未動）、CHANGELOG 0.11.0 段與本檔都含三個產出檔名（`DECISIONS-TIMELINE.md`、`PROGRESS.ir.json`、`PROGRESS.html`）與兩支腳本名（`render_progress.py`、`render_decisions_timeline.py`）；README 與 `project-init` 樹不得再列舊檔名 `PROGRESS.md`；22 個 stage skill 收尾句「這一筆是進度時間軸的資料來源」與 `check_decisions.py` 不因改名而動。

階段 3 在同一檔追加新的 `render_progress.py`（研究問題里程圖：唯讀 SSOT → `PROGRESS.ir.json` → `validate_ir()` → 自含 `PROGRESS.html`）的測試，同樣以暫存目錄動態建 fixture、讀磁碟實際產出斷言：

- 改名：`render_decisions_timeline.py` 存在、產出 `DECISIONS-TIMELINE.md`、標題含「決策時間軸」、stdout 開頭 `=== render_decisions_timeline:`，腳本與產出內無 `PROGRESS.md`／`render_progress`／「進度時間軸」殘留。
- 完整 fixture（`project.yaml` 含 2 個 SQ＋1 個 AQ、goals status 各 addressed／blocked／open、`state.next_stage: evaluate`、`state.methodology`、`state.review.round: 1`；`plans/index.yaml` SQ1 有 v1 superseded＋v2 active、SQ2 只有 v1 active、AQ1 無；`results.json` 兩鍵掛 SQ1-v2（run_id 含日期）、一鍵掛 SQ2-v1（run_id 無日期）；`validation.yaml` 頂層 expired、items SQ1 pass；`decisions.yaml` 三筆：question SQ1、question main＋links [SQ2]、無）→ lanes 順序 project, SQ1, SQ2, AQ1；`stages[]` 前六個為 SQ 六站、含 `analyze-data:rerun` 與 `evaluate:full`、id 唯一；SQ1 study-design done（date＝v2 confirmed_at、summary 含「第 2 版」、history 1 筆為 v1、evidence 含 plan path 與 content_hash 且 source 都指向 `analysis/plans/index.yaml#`）、analyze-data done 且 date 取 run_id 最大日期、run／script 各兩筆、data_fingerprint 去重為一筆、evidence 註明「日期取自 run_id」、validate-results expired（date＝completed_at、summary含「過期」、兩個 fingerprint 進 evidence）、evaluate done 且 evidence source 為 `project.yaml#goals.sub_questions[SQ1].status`、interpret-results／claim-audit pending；SQ2 evaluate blocked 且 summary 含 status_reason、`evaluations/` 含 SQ2 的 md 進 evidence、analyze-data date 為空；AQ1 六站全 pending；專案層 17 站、`evaluate:full` 節點 `current: true` 且僅此一個、peer-review done「第 1 輪，major」、methodology-router 依 state 判 done 並註明 route.yaml 不存在、其餘 pending；註記分配 SQ1=[D-001]、SQ2=[D-002]、project=[D-003]、AQ1=[]，且 D-002 六欄逐一相符；`stats` 與 stdout 統計行一致；IR 檔與 HTML 檔都在磁碟上、HTML 內嵌 JSON 可 `json.loads` 且等於 IR 檔；HTML 含 `<title>`、「請勿手動編輯」、「目前站：整體評估（evaluate）」與每條泳道「完成 x／N 站」；執行前後 fixture 逐檔 sha256 相同、只多出兩個產出檔。
- methodology-router：`methodology/route.yaml` 存在 → done，date 以 `state.methodology.at` 優先於 route.yaml 的 `confirmed_at`，route.yaml 路徑進 evidence。
- 空 fixture（只有最小 `project.yaml`）→ exit 0、只有專案層泳道、除 project-init 外全 pending、`WARNING project.yaml 無 goals，只有專案層泳道`、`INFO decisions.yaml 不存在`、`current_stage` 為空且無 current 節點、HTML 含「無研究問題泳道」；完全空目錄也 exit 0（project-init pending、WARNING 改為「project.yaml 不存在」）。
- 無法解析：`plans/index.yaml` 內容 `: : :`、`validation.yaml` 內容 `items: [` → 每條 SQ／AQ 的 study-design 與 validate-results 為 unknown 且 summary 含「無法解析」、index 壞掉時 results 鍵歸屬無法判定故 analyze-data 亦 unknown、兩個 WARNING、exit 0、無 traceback、SSOT 未動。
- 旗標正交：`--dry-run` 目錄不變、stdout 含 `<html` 與 `<title>`、無「已寫入」；`--dry-run --json` stdout 可 `json.loads` 且 `schema_version == 1`、無 `<html`；`--ir-only` 只多出 `PROGRESS.ir.json`、stdout 無「PROGRESS.html 已寫入」；`--json` 單獨用仍寫兩檔、stdout 只有 JSON。
- 自含與逸出：HTML 無 `http://`、`https://`、`<link `、`src=`，恰兩個 `<script`（內嵌 IR 與內嵌 JS），含 `prefers-color-scheme: dark`；無 BOM、無 `\r`；SQ question 含 `<script>alert(1)</script>` 時靜態表格為 `&lt;script&gt;…`、內嵌 JSON 為 `\u003cscript>…`、原文 `<script>alert` 不出現，IR 檔與內嵌 IR 都保留原文；IR 檔無 BOM、無 CR、以 `}\n` 結尾。
- 確定性：同一 fixture 跑兩次，HTML 除含 `generated_at` 的兩行（檔頭與內嵌 IR）外逐行相同，IR 除 `generated_at` 外相等。
- IR 驗證關卡：`validate_ir()` 對正常 IR 回空清單；`state` 非法 → `IR-05 lanes[2].nodes[3].state`；date 非 ISO、evidence 缺欄、stages 空 → `IR-06`／`IR-07`／`IR-02`；以 monkeypatch 把 `build_ir` 換成壞 IR 後呼叫 `main([root])` → 回 2、stdout 含 `BLOCKER IR 驗證失敗: IR-05 …`、不落任何檔；根目錄不存在 → exit 2、無 traceback。

階段 3 續（關聯圖）在同一檔追加 graph IR 與 HTML「關聯」分頁的測試，沿用階段 3 的 fixture 並補：`analysis/plans/SQ1-v2.yaml`（outputs k1／k2、robustness R1 expected_keys [k2]、`supersedes: SQ1-v1`、`primary_model.id: M-shared`）與 `SQ2-v1.yaml`（outputs k3 與未登錄的 `k_missing`）、三個結果鍵共用 `model_id: M-shared`、SQ1 的 goals links 含不存在的 `results:legacy_key`、validation item `primary_results: [k1]` 與 `robustness: [{id: R1, result_keys: [k2]}]`、decisions 改為 `question: SQ1`／`links: [SQ2, D-001]`／`supersedes: "D-001"`：

- 完整 fixture → `node_types` 順序 question／method／validation／result／decision，無 `m:` 節點、無 `uses`／`validates` 邊；`q:main`（title＝research_question、state 空）、`q:SQ1`／`q:SQ2`／`q:AQ1`（state 依 goals status）；方法節點 `p:SQ1-v2`（done、`collapsed: false`、label `SQ1-v2 ｜ M-shared`、`meta.models == ["M-shared"]`、badge `v2（1 舊版）`、`superseded_versions == ["SQ1-v1"]`、meta 帶 version／content_hash／amendment_reason／primary_model）、`p:SQ1-v1`（expired、`collapsed: true`、badge 空、models 空）、`p:SQ2-v1`（done、無徽章）；結果節點 `r:k1`（done、`meta.primary` true、`validated_by == ["V1"]`、`validation_kind: primary`、badge「主要」）、`r:k2`（只在 V1 的 robustness result_keys → badge「穩健性」、`validation_kind: robustness`、`robustness_id: R1`）、`r:k3`（badge「其他」、`validation_kind` 空）、`r:legacy_key`（unknown、「goals 指向的鍵不在 results.json」）、`r:k_missing`（pending、「已宣告、results.json 尚無此鍵」、`declared_by: SQ2-v1`）；`v:V1`（expired、meta 帶 status／primary_results）；`d:D-001`～`D-003` state 空；每個節點帶非空 `source`、數值 x／y、整數 col／order、布林 collapsed、字串 badge；五欄 x 依 question → method → validation → result → decision 遞增、`col` 對應 0–4；收合檢視：`p:SQ1-v1`／`p:SQ1-v2`／`p:SQ2-v1` 的 order 為 0／1／2，`p:SQ1-v2` y=20、`p:SQ2-v1` y=68、collapsed 的 `p:SQ1-v1` y 等於 `p:SQ1-v2`，result 欄與 decision 欄 y 連續（列距 48）、`k1 < k2 < legacy_key < k3 < k_missing`、decision 依 id；邊：`decomposes` 可見、`plans` 現行版可見／舊版隱藏、`supersedes` 隱藏 dashed、`validated_by p:SQ1-v2→v:V1` 可見 label「驗證」、`primary v:V1→r:k1` 可見 label「主要結果」、`robustness v:V1→r:k2` 可見 `thin` label「穩健性」（同一 item 同一鍵同在 primary_results 時只畫 primary）、`produces p:SQ1-v2→r:k1` 與 `→r:k2` 都隱藏（已驗證，含穩健性），meta 仍帶 robustness_id 與 change、`produces p:SQ2-v1→r:k3`／`→r:k_missing` 可見 dashed、`cites`／`refers` 隱藏、`d:D-001→d:D-003 supersedes` 隱藏 dashed（反向不存在）、反向 `validated_by` 不存在；D-003 只靠 supersedes 對到 D-001 故不掛 `q:main`，全無對應的 D-004 → 一條 `refers → q:main`；邊去重、每條邊有 `default_visible` 布林與 `style` solid｜dashed；`shared` SQ1–SQ2 一筆 via `["model:M-shared"]`、kinds `["method"]`，V1 的 primary_results 加上 k3 後 via 為 `["model:M-shared", "r:k3"]`、kinds 加 result，`q:main` 不出現；`stats.by_type`、`dangling_result_keys == 1`、`unvalidated_result_keys == 1`（拿掉 robustness 後 k2 的旁路回到可見 dashed、計數變 2、badge 回「其他」）；stdout 摘要含「…goals 指向不存在的結果鍵 1、未驗證的結果鍵 1。」。
- 版面確定性：同 fixture 兩次 `--dry-run --json` 的 `graph` 序列化後逐位元相同；兩次寫檔的 HTML 除產生時間與 `generated_at` 兩行外相同。
- HTML 關聯分頁：含 `id="tab-relations"`、`id="tab-milestones"`、`<svg`、`data-node-id="q:SQ1"`、`data-node-id="r:legacy_key"`、「共用關係」「導覽」「Shift」、`data-tab="relations"`、`id="graph-search"`、`id="toggle-dec"`、「顯示舊版計畫」（`id="toggle-old"`）、「顯示全部邊」（`id="toggle-alledges"`）、五個 `data-gstate` state 篩選 checkbox、「未驗證旁路」、徽章文字「v2（1 舊版）」、「關聯圖：節點」；每條邊的 `d` 以 `M` 開頭、含 ` L`、至少一條含 ` Q` 圓角、無 ` C`（無三次貝茲），邊數與 IR 一致；預設隱藏的邊帶 `off`、收合節點帶 `gone`、未驗證旁路帶 `st-dashed`、穩健性邊帶 `st-thin` 且圖例有「細線＝穩健性」、節點有 state 符號（● ◐）與右端中文小標、CSS 有 `--bg-done`／`--bg-expired` 淡色；仍無 `http://`／`https://`／`<link `／`src=`；決策節點帶 `dec gone`；SVG 文字逸出；以 `html.parser` 追蹤開閉 tag（void 元素除外）→ 錯誤清單空、stack 空。
- graph 驗證關卡：邊指到不存在節點 → `IR-13 graph.edges[i].to`；node id 前綴非法 → `IR-12 graph.nodes[0].id`、x 為字串 → `IR-12 …x`、col 與 type 不符 → `IR-12 …col`、collapsed 非布林 → `IR-12 …collapsed`；邊缺 `default_visible` → `IR-13 …default_visible`、style 非 solid｜dashed｜thin → `IR-13 …style`（thin 合法）；刪掉 `graph` → `IR-01 top-level.graph`；壞 IR 經 monkeypatch 進主程式 → exit 2、`BLOCKER IR 驗證失敗: IR-13 …`、不落檔。
- 空 fixture：無 goals → graph 只有 `q:main`、無邊、stats 全零（含 `unvalidated_result_keys`），HTML 仍含 `<svg`；有 goals（無 links）而無其他 SSOT → 只有四個問題節點與三條 decomposes 邊；goals 有 links 而無 results.json → 兩個 dangling `r:` 節點、cites 邊仍建、`dangling_result_keys == 2`。

階段 4「自動觸發」在同一檔追加 plugin 級 `SessionEnd` hook 的測試：`hooks/hooks.json` 契約與 `skills/status/scripts/progress_hook.py` 的行為，fixture 一律 `tempfile.TemporaryDirectory`、以 stdin 餵 hook JSON 實跑腳本、斷言讀磁碟實際產出：

- `hooks/hooks.json` 可解析、只註冊 `SessionEnd`、command 含 `progress_hook.py` 與 `${CLAUDE_PLUGIN_ROOT}`、timeout 為整數；依 codex plugin 的註冊方式，`plugin.json` 不加 `hooks` 欄位（斷言不存在）且版號維持 `0.10.2`。
- 專案在 cwd 子目錄（`proj/` 含最小 `project.yaml` 有 `goals`＋一筆 `decisions.yaml`）→ exit 0、stdout 空、`proj/PROGRESS.html`／`PROGRESS.ir.json`／`DECISIONS-TIMELINE.md` 齊、`proj/.progress-hook.log` 恰兩行 `ok`（五欄 tab 分隔、時間為 ISO、session_id 為 `t1`）、cwd 本身無新檔、既有檔逐檔 sha256 不變。
- 專案即 cwd → 同上；再跑一次 log 追加為四行；stdin 沒 `cwd` 時 `--cwd` 生效、`session_id` 缺時寫 `-`；stdin 不是 JSON 也不炸。
- 找不到專案（無 `project.yaml`、`project.yaml` 非 dict、只有 `pipeline` 鍵、完全空目錄、cwd 不存在）→ exit 0、stdout 空、目錄雜湊完全不變（不寫 log）。
- `decisions.yaml` 內容 `: : :` → hook exit 0、stdout 空、log 第 1 行 `render_progress.py ok`、第 2 行 `render_decisions_timeline.py fail rc=2` 且細節單行 ≤200 字含「無法解析」、`PROGRESS.html` 仍產出、無 `DECISIONS-TIMELINE.md`、`decisions.yaml` 原文未動。
- `ACADEMIC_PIPELINE_PROGRESS_HOOK=off`（含 `OFF`、前後空白）→ exit 0、不產任何檔；設為其他值照跑。
- 跳過：cwd 下只有 `archive/`、`data/`、`node_modules/`、`.hidden/` 是專案根 → 都不選、不落檔；cwd 本身在 `/archive/` 之下 → 不選；同層有 `archive/`、`zz_proj/`、`aa_proj/` → 依名稱序選 `aa_proj`；`--find-only` 只把根印到 stderr、stdout 空、不跑 renderer、不寫 log，在 archive 下則什麼都不印。
- 雜湊紅線：fixture 多放 `analysis/results.json`、`plans/index.yaml`、`validation.yaml`、`methodology/route.yaml`，執行前後 SSOT 逐檔 sha256 相同；預放的舊 `PROGRESS.html` 被覆寫、舊 `.progress-hook.log` 被追加（第一行仍為舊內容）。
- log 截斷：預放 220 KB 的 log → 執行後 ≤100 KB＋兩行新紀錄，截斷對齊換行不留半行。
- 登記錨點：README artifacts block 含 `.progress-hook.log`、有「自動重算」與「逃生口」；`project-init` 步驟 4 樹含 `.progress-hook.log`（註明 hook）；`status` SKILL.md 含 `SessionEnd`／`progress_hook.py`／`.progress-hook.log`／`ACADEMIC_PIPELINE_PROGRESS_HOOK`；CHANGELOG 0.11.0 段有第 9 條並含 `hooks/hooks.json`；本檔含「自動觸發」。frontmatter 未動。

## run_v0120_regressions.py

v0.12.0 為關聯圖加第五欄「圖表」與結果節點面板的表／圖，全部以 `tempfile.TemporaryDirectory` 動態建 fixture（`project.yaml` 兩個 SQ、兩份 active plan、`results.json` 三鍵——k1 三列表、k2 純量含 value／display／unit、k3 250 列表、`validation.yaml` V1 primary [k1]、`analysis/figures/manifest.json` 兩張圖——`fig_a` 掛 k1、`registered_not_reviewed`、file 為 tempdir 內真的小 svg，`fig_b` 掛不存在的 `nope` 且無 file）、讀磁碟實際產出斷言：

- 圖表節點與 depicts 邊：`node_types` 順序 question／method／validation／result／figure／decision、`edge_types` 含 `depicts`（「呈現於」）；`f:fig_a`（col 4、badge「主圖」、pending、title「已登錄未審：」＋去 markdown 的 caption、meta 帶 file／files／role／figure_number／status／script／registered_at／results_keys／caption／spec、預設無 `data_uri`）；`f:fig_b`（無 file → unknown「檔案不存在」、badge「無對應結果鍵」、stderr `WARNING …figures[fig_b].results_keys 指到不在圖裡的鍵: nope`、無 depicts 邊、不反向建 `r:nope`）；`r:k1→f:fig_a depicts` 可見 solid label「呈現於」；k1 `meta.table == {columns, rows（3 列）, n_rows 3, truncated false}` 與 `description`、k2 無 table 而有 value／display／unit、k3 `n_rows 250`／`truncated true`／rows 200 列；`stats.by_type.figure == 2`、`figures_unreviewed == 2`；圖表欄 fig_a 在 fig_b 前；SQ1／SQ2 不因 depicts 誤共用；stdout 摘要含「圖表 2 張（未審 2）。」。
- figure state 規則：`confirmed`／`reviewed` → done、`draft` → pending 無前綴、部分鍵對到 → 建邊＋WARNING 並保留 role 徽章、無 `results_keys` → 徽章「無結果鍵」＋INFO；`figures_unreviewed` 只算 state 非 done；manifest 無法解析 → WARNING、無圖表節點、exit 0；manifest 缺 → 無圖表節點、無 depicts 邊。
- `--embed-figures`：`meta.data_uri` 以 `data:image/svg+xml;base64,` 開頭且解回原 svg、無檔的圖不內嵌、`--dry-run` 不落檔；寫檔後 HTML 與 IR 都含 data URI；預設 HTML 不含 `data:image`；> 5 MB 的 svg 跳過並 `WARNING … 超過 5 MB`、state 不受影響。
- HTML：含 `id="lightbox"`、figure 圖例色與「呈現於（depicts）」、`t-figure` 節點、`e-depicts` 邊、`loading="lazy"`、「找不到檔案：」、表格與圖表的 JS 片段、導覽文字的圖表段；自含改為無 `http://`／`https://`／`<link `／`src="http`；靜態 HTML 只有燈箱那個不帶 src 的 `<img>`；SSOT 字串（`x<y`、`<b>`）在內嵌 IR 逸出成 `\u003c`；無 BOM／CR；`html.parser` tag 平衡；里程分頁錨點仍在。
- `validate_ir`：figure `meta.files` 非清單、`data_uri` 不以 `data:` 開頭、result `meta.table.rows` 非清單、缺 `stats.figures_unreviewed`、id 前綴 `x:` → 各自的 `IR-12`／`IR-14`。
- 登記錨點：CHANGELOG `## 0.12.0（未發布）` 含 figure／depicts／`--embed-figures`／figures_unreviewed；`status` SKILL.md 含 `--embed-figures`（frontmatter 未動）；本檔與 README 含 `run_v0120_regressions.py`；README artifacts 說明含「看表與圖」。

收件匣（同檔追加 5 段）：

- `progress_server.py`：在 tempdir fixture 以 `threading` 起 `make_server(root, "127.0.0.1", 0)` → `GET /api/ping` 回 `{ok, root, inbox_pending: 0}` 且 `Cache-Control: no-store`；`POST /api/inbox` 合法 → 201 `{ok, id: IN-001}`、收件匣以固定表頭建立、`at` 含時區、第二筆 IN-002 連號；非法 kind／不存在的 target／空 body／title 超長／非 JSON → 400 且檔案雜湊不變；偽造 `Origin: http://evil.test`（與 `Origin: null`）→ 403「跨來源請求已拒絕」、`Content-Type: text/plain`（與缺 Content-Type）→ 415，皆不寫檔且不回 CORS header，同源 `Origin` 放行；`GET /api/inbox` 列兩筆、ping 的 `inbox_pending` 為 2；`GET /` 回 HTML 且 `PROGRESS.html` mtime 變、內容含「收件匣待處理 2 筆」與徽章「收件 1」；`/../etc/passwd` 與 `/analysis/../project.yaml` → 403、`/project.yaml`（yaml 允許）與 svg → 200、目錄／白名單外副檔名／不存在 → 404、`/api/nope` → 404、PUT／DELETE／PATCH 與 POST 非 `/api/inbox` → 405；結束後 SSOT 檔雜湊全同、無暫存檔殘留。沒有任何產物的 fixture 直接 POST（不先 GET /）→ 先重算再核對 target → 201，IR 壞掉時亦重算恢復；CLI 啟動時印 URL 前已重算出 IR 與 HTML；`--host 0.0.0.0` → exit 2 且 stderr 含 BLOCKER／loopback；`make_server` 對非 loopback 丟 ValueError；根不存在 → exit 2。
- `check_inbox.py`：缺檔 → INFO exit 0、此時 `--resolve` → BLOCKER 找不到；有 fixture 收件匣（IN-001 pending、IN-002 done）→ 列出 pending 一筆與 `pending 1／done 1／dismissed 0`、無 WARNING；`--resolve IN-001 --by D-051 --note …` → 只有 IN-001 的 status／resolved_by／resolved_at／note 四行改變、其餘行逐行相同、`resolved_at` 為含時區的 ISO 時間；`--dismiss IN-002` → dismissed；`--resolve` 缺 `--by`、找不到 id → exit 2；id 跳號／status 非法／target 不在 IR → WARNING 仍 exit 0；無法解析 → exit 2。
- renderer：無收件匣 → IR `inbox == {present: false, pending: 0, items: []}`、`stats.inbox_pending == 0`、HTML 無橫幅、stdout 句尾「收件匣待處理 0。」；有收件匣 → `inbox.pending == 1`、items 逐欄原樣、`q:SQ2` 的 `meta.inbox == ["IN-001"]` 與 badge「收件 1」、其他節點無 `meta.inbox`、HTML 含「收件匣待處理 1 筆」／`id="inbox-banner"`／可點的 target／`api/ping`／「＋ 新問題／新分析」／「＋ 意見」／「用 progress_server.py 開啟才能送出」／`id="inbox-new" disabled`，仍自含、tag 平衡；收件匣無法解析 → WARNING、視為無；`validate_ir` 的 IR-15（pending 數不符）與 IR-01（缺 inbox）。
- 登記錨點：README、`status` SKILL.md（含 `--resolve`／`--dismiss`／loopback）、`project-init` 樹、CHANGELOG、本檔含 `PROGRESS.inbox.yaml`／`progress_server.py`／`check_inbox.py`。

## run_v0130_regressions.py

v0.13.0 為關聯圖把主要結果與次要結果（敏感性分析）分開，fixture 以 tempfile 動態建（SQ1-v1 superseded 帶 R1；SQ1-v2 active、outputs [k1, k2]、R1 expected [k2]（與主要重疊，executed true）、R2 expected [k4]（只在 robustness）、R3 expected [k6, k7]（k7 未登錄，executed false）；results.json 有 k1、k2、k4、k6、k3 與掛在 SQ1-v2 但未宣告的 k5；validation V1 primary [k1]、robustness result_keys [k4]），讀磁碟實際產出斷言：

- 敏感性子節點：`p:SQ1-v2#R1`／`#R2`／`#R3` 與 `p:SQ1-v1#R1` 存在，type method、`subtype: sensitivity`、col 1、`parent` 正確、label「R1：<change 前 24 字>…」、title＝change、meta（change／expected_keys／registered_keys／executed 原值／execution_note）、source `analysis/plans/SQ1-v2.yaml#robustness[R1]`；R1／R2 done、R3 pending 且徽章「部分」；主節點 `subtype: primary` 與 `meta.sensitivity_ids`；superseded 父的子節點 expired、`collapsed: true`、y 借用現行版。
- 結果分類與驗證標記：k1／k2／k3 主要（k2 也在 R1 expected）、k4／k6／k7 次要、k5 未宣告，徽章「主要」「次要」「未宣告」；`meta.declared_by` 列出宣告節點（k2 為 `["p:SQ1-v2", "p:SQ1-v2#R1"]`、k1 含舊版）；k7 未登錄 → pending；`meta.validated`／`validation_kind` 獨立（k1 primary、k4 robustness、其餘 false）；舊的 `meta.primary` 不存在。
- 邊：父→子 `sensitivity`（label「敏感性」，舊版隱藏）；`produces` 主節點→outputs 鍵、子節點→expected 鍵一律可見實線 label 空（含子分析連到主要鍵 k2）；未宣告 k5 → dashed「未宣告」；舊版 plan 與其子節點的 produces 隱藏；次要鍵不由主節點直連；`validated_by`「驗證」、`primary`「驗證（主要）」、`robustness`「驗證（穩健性）」thin。
- 列序：方法欄 SQ1-v1、#R1、SQ1-v2、#R1、#R2、#R3、SQ2-v1 依序 0–6，子節點 x 縮排 24、y 連續；結果欄 k1 < k2 < k4 < k6 < k7 < k5 < k3、y 連續。
- stats：`by_type.method == 7`、`sensitivity_items == 4`、`secondary_result_keys == 2`、`undeclared_result_keys == 1`、`unvalidated_result_keys == 4`；stdout 含「次要 2、未宣告 1、敏感性子分析 4 項、」；把 k4 從 results.json 拿掉 → R2 pending 無徽章、k4 節點 pending 仍「次要」、次要計數變 1。
- HTML：子節點 `data-node-id="p:SQ1-v2#R1"`、`data-parent`、`sub` class 三種 state、寬度 236、父→子 L 形線的 d 從父節點左緣下方（x+12, y+36）垂下、以子節點左緣中線結束、無貝茲；`e-sensitivity`／`e-produces st-dashed`、「敏感性子分析」「未宣告」「未驗證」「縮排子節點＝敏感性子分析」「虛線＝未宣告」「父分析」「expected_keys（」「result_kind」「declared_by」與導覽文字的「敏感性 '+sc+' 項」錨點；「未驗證」小標恰 5 個（k2、k3、k5、k6、k7）；無「未驗證旁路」；自含、tag 平衡。
- `validate_ir`：`parent` 不存在、`subtype` 非法或掛在非 method 節點、缺 `stats.sensitivity_items` → 各自的 `IR-12`／`IR-14`。
- 登記錨點：CHANGELOG `## 0.13.0` 含 sensitivity／secondary_result_keys／undeclared_result_keys／敏感性子分析；`status` SKILL.md 含敏感性子分析／次要／未宣告（frontmatter 未動）；本檔與 README 含 `run_v0130_regressions.py`。

走線（同檔追加兩段，v0.13.2）：

- `route_edges`（直接 import 呼叫合成 fixture）：一個來源連 3 個目標 → 3 條 path、同一條幹線（`trunk_of` 相同、幹線 x 相同、`lane_max == {1: 0}`、幹線 d 為 `M660,86 H720 M720,38 V134`）；兩個來源目標 y 範圍重疊 → 車道與幹線 x 不同、`lane_max == {1: 1}`；不重疊 → 都在車道 0、幹線 x 相同；單一目標同列 → 直線 `M660,38 L780,38`、無幹線、不占車道；反向邊從來源左緣出、走來源左側走道、進目標右緣，同欄 supersedes 走右側走道回右緣；同輸入兩次結果相等；上限＋1（14）條互相重疊的幹線 → `lane_max == {1: 13}`、`overflow == [1]`、幹線 x 只有 13 種（折回）；恰 13 條 → 不折回、車道 x 等距 8px 且都在走道內；Python／JS 版面常數（`NODE_W` 260、`COL_PITCH` 380、`ROW_GAP` 48、`GRAPH_PAD` 20、`LANE_GAP` 8）以正則從 `GRAPH_JS` 取出比對同值。
- 對 v0.13 fixture 的可見邊：同一走道內任兩條垂直區間重疊的幹線 x 不同、無 overflow、每條可見非 sensitivity 邊都有 path；HTML 含 `<g id="graph-trunks">`、`class="trunk e-decomposes st-solid" data-trunk="q:main|1|decomposes|solid|fwd" data-gap="0" data-lane="0"`、`data-trunk="p:SQ1-v2|4|produces|solid|fwd"`、圖例「同來源的線合併成幹線＋分支」，sensitivity 邊不帶 `data-trunk`；有 headless Chrome（google-chrome／chromium）時以 `--dump-dom` 取 JS 重算後的 DOM，比對所有可見邊的 `d` 與幹線（key／gap／lane／d）與 Python 靜態產出逐字相同，無 Chrome 則印一句略過。`run_v0110` 的路徑格式斷言改為「M 開頭、含 H 或 L、無 C」。

結果階層（同檔追加一段，v0.13.3）：fixture 的 k4（只在 R2 宣告）→ `subtype: secondary`、`parent: p:SQ1-v2#R2`、x 縮排 24；k6／k7 parent 為 `#R3`；k1／k2 primary、k5 undeclared 皆頂層且同 x；結果欄 y 連續且序為 k1 < k2 < k4 < k6 < k7 < k5；產出邊仍由子分析連到次要結果、結果欄無 sensitivity 邊；HTML 的 `r:k4` rect x 比 `r:k1` 多 24、寬少 24、帶 `sub` class 與 `data-parent`，圖例句「縮排子節點＝敏感性子分析與其次要結果」，面板有「父子分析」與「次要結果」；把 SQ1-v2 換成 superseded（新增 SQ1-v3 現行版）→ `p:SQ1-v2#R2` 與 `r:k4` 都 `collapsed`、k4 的 y 借用 `p:SQ1-v3`、HTML 帶 `gone`。validate 測試補「result 的 parent 須為敏感性子節點」。

附錄問題進機械關卡（同檔追加四段，v0.13.4）：fixture 以 tempfile 動態建、真的跑 `init_protocol.py`／`init_plan.py`／`seal_artifact.py` 建與封——`sub_questions` [SQ1]、`appendix_questions` [AQ1 evidence [analysis]]、`index.active` 含 SQ1-v1 與 AQ1-v1、results.json 兩鍵（`sq1_primary` 掛 SQ1-v1、`aq1_primary` 掛 AQ1-v1，皆在 outputs 預宣告）、validation.yaml V1 `sq: SQ1`／V2 `sq: AQ1`（fingerprints 由 `check_validation.py --fingerprint-only`／`--source-fingerprint-only` 取）。斷言：`check_plan --require-confirmed --results` 0 blocker、統計 `checked SQ 1 + AQ 1`、`--sq AQ1` 可用；`check_validation` 無「sq 無效」、`target SQ 1 + AQ 1`、`--sq AQ1` 可用；AQ 從 `index.active` 拿掉 → `WARNING AQ1: index.active 無 confirmed plan（附錄問題，不擋）`、exit 0，AQ 結果鍵仍掛已不 active 的 plan → BLOCKER；SQ 拿掉 → `BLOCKER SQ1: index.active 無 confirmed plan`；validation 只留 SQ item → `WARNING AQ1: 無 validation item（附錄問題，不擋）`、只留 AQ item → `BLOCKER SQ1: 無 validation item`；AQ item 的 plan_id 錯、`sq: AQ9` → BLOCKER；protocol 的 `sub_questions` 只有 SQ1；`init_plan --sq AQ1` 建 `AQ1-v1.yaml`、`sq: AQ1`、`role: secondary`（SQ1 為 primary）。`rerun_all --fingerprint-only`：改 AQ 的 status／links／status_reason 前後 `input_fingerprint` 相同、改 question 不同、`appendix_questions: []` 前後不變。`check_claims` 接受 `sq: AQ1`（AQ9 仍 `sq 無效`）、`check_exploration` promoted 到 AQ1 且 AQ1.origin = E1 通過（AQ9 仍 blocker）、`check_coverage --sq AQ1` 只列 AQ1、`check_claim_audit.project_claim_context` 有 AQ 時另列 `appendix_questions`（只留白名單欄位），`[]`／缺鍵時不加鍵。登記錨點：CHANGELOG `## 0.13.4`、`study-design` 與 `validate-results` SKILL.md（frontmatter 未動）、README、本檔、`plugin.json` >= 0.13.4。

## run_v0140_regressions.py

v0.14.0 把關聯圖分成 Main／Supplementary 兩個區帶，每組敏感性分析一條線（`supplements`「敏感性對照」）連回所屬分析的主要結果。fixture 以 tempfile 動態建（SQ1-v1 superseded 帶 R1；SQ1-v2 active、outputs [k1, k2]、R1 expected [k2]（與主要重疊）、R2 expected [k4]（只在 robustness → 次要）、results.json 另有掛在 SQ1-v2 但未宣告的 k5；SQ2-v1 沒有 robustness；SQ3-v1 只宣告 robustness R1 expected [z1] 且未執行；AQ1-v1（appendix_questions）outputs [a1]、R1 expected [a2]；validation V1（sq SQ1，primary [k1]、robustness [k4]）與 V2（sq AQ1，primary [a1]）；manifest F1 指 k1、F2 指 k4（真的小 svg）；一筆決策），讀磁碟實際產出斷言：

- 區帶指派全部規則：q:main／SQ／SQ 的 plan／主要與未宣告結果／V1／F1／決策為 main；AQ1 及其 plan／結果／V2、四個群、五個子分析、次要結果 k4／z1／a2、F2 為 supp；沒有 robustness 的 SQ2-v1 不建群。
- 群節點 `p:SQ1-v2#S`：type method、`subtype: sensitivity_group`、parent＝plan、col 2、label「SQ1-v2 敏感性分析」、badge「2 項」、title、state done、`meta == {plan_id, sensitivity_ids, supplements: [k1, k2, k5]}`、source、x 不縮排；舊版群 expired／collapsed；SQ3 群 pending 且 `supplements: []`；AQ 群 done；plan 的 `meta.sensitivity_ids` 照舊。子分析 parent＝同 plan 的群、x 縮排 24；次要結果 parent＝子分析。
- 邊：`p → p#S` sensitivity 隱藏；`p#S → p#R` 可見（舊版隱藏）；plan → 子分析不再建；`p#R → 主要結果` 隱藏、`p#R → 次要結果` 可見；`p#S → r:k1／k2／k5` supplements 可見實線「敏感性對照」、不連 k4、舊版隱藏、AQ 群 → a1、SQ3 群退回 → plan 一條；supplements 只從群出發；跨區帶的邊除 decomposes／supplements 一律隱藏（含 `v:V1 → r:k4` robustness）、同區帶照舊；`route_edges` 對每個 active 群的 supplements 邊 `trunk_of` 全同一 key；stats（`sensitivity_groups == 4`、`band_main_nodes`／`band_supp_nodes`、method 14、次要 2）與 stdout 摘要「；區帶 main a 節點、supp b 節點、敏感性分析群 4 組。」。
- 版面：可見 main 節點 y ≥ 48 且最小為 48、決策從 48 起；`y0_supp = main_bottom + 40 + 28`，可見 supp 節點 y ≥ y0_supp 且最小為 y0_supp；每 (band, col) 內 order 為整數序、可見 y 連續（欄 0 的 q:main 居中除外）；supp 欄 2 順序＝SQ1-v1 群→R1→SQ1-v2 群→R1→R2→SQ3 群→R1→AQ1 plan→AQ1 群→R1；q:main 只對 SQ1／SQ2／SQ3 居中、AQ1 在 supp；舊版 plan 借現行 plan 的列、舊版群與 R# 借現行版群的列。無 AQ 也無 robustness 的變體：全 main、`graph-bands` 帶 `off`、SQ 欄從 20 起、摘要「supp 0 節點、敏感性分析群 0 組」。
- HTML：`<g id="graph-bands" class="bands">` 在 `graph-trunks` 前，分隔線 x 從 20 到 width − 20、y = main_bottom + 20，標題「Main ｜ 主結果」y = 38、「Supplementary ｜ 補充：敏感性分析與附錄問題」y = main_bottom + 58；圖例句、面板錨點（區帶／所屬分析／子分析／連回主要結果／父分析）、`data-band`、CSS 錨點、JS 常數列 `var BAND_TITLE_H=28,BAND_GAP=40,BAND_TITLE_DY=18;`、`data-trunk="p:SQ1-v2#S|4|supplements|solid|fwd"`、`trunk e-supplements`；群節點寬 260 不縮排、子分析寬 236 縮排 24；群 → 子分析 L 形線從群左緣下方垂下；`p → p#S`、`p#R1 → r:k2`、`v:V1 → r:k4` 帶 `off`；自含、tag 平衡。有 headless Chrome 時以 `--dump-dom` 比對 JS `relayout()` 後每個可見非決策節點的 transform、`graph-bands` 三個元素的屬性、所有可見邊的 `d`、幹線清單、svg 尺寸與 Python 靜態產出逐字相同；再把 `toggle-old` 預設 `checked` 另存一份載入，斷言舊版群與 R# 落在 supp 區帶（y ≥ 由 supp 標題 y 推回的 y0_supp）、舊版 plan 在分隔線上方、舊版 R# 緊接舊版群下一列、所有可見節點各在自己的區帶；無 Chrome 則印一句略過。
- `validate_ir`：band 非法（連帶跨區帶錯誤）、q 節點冒充 sensitivity_group（連帶缺 supplements）、子分析 parent 改成 plan、群 parent 改成別的 plan、supplements 從 plan 出發、active 群的 supplements 全隱藏或目標跨欄、`p → p#S` 或 `p#R → 主要結果` 改可見（跨區帶）、缺 `stats.sensitivity_groups`、`band_main_nodes` 與節點數不符；`schema_version` 仍 1。
- 登記錨點：CHANGELOG `## 0.14.0` 含 supplements／sensitivity_group／band_main_nodes／BAND_TITLE_H／Supplementary／本檔名；README 與 `status` SKILL.md 含 Supplementary／敏感性對照（SKILL 另含敏感性分析群，frontmatter 未動）；本檔含 `run_v0140_regressions.py`；`plugin.json` version ≥ 0.14.0。

## run_v0141_regressions.py

v0.14.1 加「問題 id 別名」：主問題降為附錄問題後，index 舊版條目、決策 links、validation item 仍寫的舊 id 併進現行問題。fixture 以 tempfile 動態建（goals 只有 SQ2 與 appendix AQ2；index 有 SQ1-v1（superseded、replaced_by SQ1-v2、sq SQ1）、SQ1-v2（superseded、replaced_by AQ2-v1、sq SQ1）、AQ2-v1（active、sq AQ2、`supersedes: SQ1-v2`、robustness R1）、SQ2-v1（active）、孤兒 SQ9-v1（superseded、鏈走不到 goals）；results k1／k4 掛 AQ2-v1、k3 掛 SQ2-v1；validation V1 `sq: SQ1` plan AQ2-v1、V2 `sq: SQ2`；決策 D-001 `links: [SQ1]`、D-002 `question: SQ1`），讀 `--dry-run --json` 與磁碟產出斷言：

- 關聯圖：`graph.question_aliases == {SQ1: AQ2}`；無 `q:SQ1`；`q:SQ9` 仍為「goals 無此問題」占位（unknown、main）；`q:AQ2` 的 `meta.aliases == [SQ1]`、title 尾綴「（原 SQ1；index 舊版 SQ1-v1／SQ1-v2）」，`q:SQ2` 無 aliases；`p:AQ2-v1` 的 `superseded_versions == [SQ1-v1, SQ1-v2]`、徽章「v1（2 舊版）」、band supp；`p:SQ1-v1`／`p:SQ1-v2` collapsed、expired、band supp、`meta.sq == AQ2`、`meta.sq_original == SQ1`、y 借 `p:AQ2-v1`、`q:AQ2 → p:SQ1-vN` 的 plans 邊存在且隱藏、supersedes 鏈 SQ1-v1 → SQ1-v2 → AQ2-v1；舊版群 `p:SQ1-v1#S` 與 `#R1` collapsed、supp、借 `p:AQ2-v1#S` 的列；`d:D-001`／`d:D-002` 的 refers 都指 `q:AQ2`、沒有任何邊指 `q:SQ1`；`v:V1` 的 `meta.sq == AQ2`、`sq_original == SQ1`、supp、title「AQ2 驗證 …」、`p:AQ2-v1 → v:V1`、`v:V1 → r:k1`；V2 不變；k1／k4 supp、k3 main。
- 里程分頁：lanes 為 project／SQ2／AQ2（無 SQ1）；AQ2 泳道 study-design done「plan AQ2-v1 封版（第 1 版）」且 history 兩筆「SQ1-v1 封版，已被 SQ1-v2 取代」「SQ1-v2 封版，已被 AQ2-v1 取代」、analyze-data done、validate-results done 且 evidence 含「V1: qualified」；D-001／D-002 只掛 AQ2 泳道；stdout 含 `INFO 問題 id 別名：SQ1 → AQ2（index 舊版 SQ1-v1／SQ1-v2）`。
- 變體：index 拿掉 SQ1-v2 的 `replaced_by`、只靠 AQ2-v1.yaml 的 `supersedes` 反推 → alias 與 superseded_versions 不變；goals 拿掉 AQ2 → `question_aliases == {}`、`q:SQ1` 與 `q:AQ2` 都成 unknown 占位。
- HTML：面板「舊 id」「問題」（含「已併入」「index 寫 」）錨點、無 `data-node-id="q:SQ1"`、自含；有 headless Chrome 時比對 JS relayout 後可見節點 transform、`graph-bands` 屬性、可見邊 `d`、幹線清單與 Python 靜態產出逐字相同，無 Chrome 則印一句略過。
- `validate_ir`：`question_aliases[SQ1] = NOPE` → `IR-14 graph.question_aliases[SQ1]`；value 為 `main` 合法；key 本身是節點（SQ9）→ 錯；非 mapping → `IR-14 graph.question_aliases`；缺鍵 → `IR-11 graph.question_aliases`。
- 登記錨點：CHANGELOG `## 0.14.1` 含 question_aliases／別名／本檔名；README 與 `status` SKILL.md 含「別名」（SKILL 另含 question_aliases，frontmatter 未動）；本檔含 `run_v0141_regressions.py`；`plugin.json` ≥ 0.14.1。

## run_v0150_regressions.py

v0.15.0 把關聯圖分成 Main／Extended Data／Supplementary 三個區帶、敏感性對照改連所屬 plan、版面改成不交叉。fixture 以 tempfile 動態建（SQ1-v1 superseded 帶 R1；SQ1-v2 active、outputs [k1, k2, k3]、R1 expected [k2]、R2 expected [s1]（次要）；SQ2-v1 active 沒有驗證、outputs [m1]、R1 expected [m1]；AQ1-v1 outputs [a1]、R1 expected [a2]；validation V1（sq SQ1，primary [k1]、robustness [k2]）與 V2（sq AQ1，primary [a1]）；manifest 八筆：F_main（role main、k1）、F_ext（extended、k1）、F_ext2（`Extended Data`、無鍵）、F_supp（`SI`、k1）、F_norole（缺 role、k3 → 推導 main）、F_norole_supp（缺 role、s1 → 推導 supp）、T_main（`type: table`、role main、無鍵）、F_badrole（role weird、指到不存在的鍵）；一筆決策；`with_ext=False` 變體拿掉兩張 ext 圖），讀 `--dry-run --json` 與磁碟產出斷言：

- 區帶與徽章：圖表依 role 落帶與 `role_source`（manifest／derived）、徽章「主圖」「主表」「延伸」「補充」、role 蓋過「無結果鍵」「無對應結果鍵」而後者留在 `meta.keys_badge`、`meta.type`；非圖表節點 band 規則不變、ext 帶只有圖表；三帶 stats 相加＝節點數；跨帶可見邊只剩 decomposes／depicts／supplements；stdout「；區帶 main a 節點、ext 2 節點、supp b 節點、敏感性分析群 4 組；預設檢視線段交叉 0、穿過節點 0。」且無交叉 WARNING。
- 敏感性對照與隱藏規則：每個群恰一條 `supplements` → 所屬 plan（舊版隱藏、不連任何結果、`meta.supplements == [pid]`、title 尾句「以一條線（敏感性對照）連回所屬 plan」）；`_spine_path` 為 `M x+12,群y V plan.y+36`；`spine_lanes` 對要穿過 SQ1-v2#S 區塊的 SQ2-v1#S 對照線給第 1 道（x+8）、其餘第 0 道；`p#R → 主要結果` 隱藏不分帶（含 main → main 的 SQ2-v1#R1 → m1）、`p#R → 次要結果` 可見；遞移隱藏：`p:SQ1-v2 → k1`（V1 primary）與 `→ k2`（V1 robustness）隱藏並記 `meta.via_validation`，`→ k3` 未驗證維持可見、AQ 的 a1 同規則；supplements 不進 `route_edges`。
- dummy 列與 via：四條跳欄邊（p → k3、p → m1、R2 → s1、AQ R1 → a2）的 `via == [[3, y]]`、`via_order` 等長、目標的帶；其餘邊 via 為 `[]` 且沒有預設可見的跳欄邊漏掉；每帶欄 3 的節點與 dummy 一起為連續整數序、y 連續且不同列；整條邊一條連續折線（一個 M、含穿過 dummy 列的 `H x3+260`）、`trunk_of` 為兩段 key（`p|3|…` 與 `~idx@3|4|…`）；同輸入兩次 IR 相同。
- 三帶版面：main 從 48 起、ext 從 main_bottom（含 dummy 列）+40+28 起、supp 從 ext_bottom+40+28 起；決策欄自 48 起；問題欄維持 goals 序、`q:main` 對 SQ1／SQ2 居中；舊版借列；群與其 R、plan 與群（同帶）連續；每走道車道索引連續、x 隨車道單調遞增且置中、重疊幹線 x 不同、無 overflow；`crossing_stats` 直接重算與 stats 一致（0／0）；`with_ext=False` 時無 ext 節點、supp 直接接在 main 之後、仍 0／0。
- `route_edges` 合成 fixture：巢狀幹線（列 0 → 列 4 與 列 1 → 列 7）→ 後者在左（車道 0）且交叉 0、反向亦然；兩條都不交叉 → 仍不共道；共線相接（A 的分支 y == B 的出口 y）→ B 在左；單目標只在 sy == ty 直線（`M660,38 L780,38`），y 差 10 也走幹線；3 條互相重疊 → x 為中央 ±8 置中、13 條等距置中、14 條折回 overflow。`crossing_stats`：真正交叉 1、共端點 0、T 形 0、同邊 0、同幹線 0、共線重疊 1；穿過節點：穿過內部 1、沿邊緣 0、只碰邊緣 0、對照線 0。
- HTML：`graph-bands` 三組元素（main 分隔線 off、ext／supp 兩者都畫）與 y、標題文字、JS `BANDS`／`spinePath`／`assignLanes`／`laneX`／`spineLanes`／`dummyActive` 錨點、圖例兩句、面板「敏感性對照」與三帶文字、`arrow-method` marker 與 CSS、對照線 path（第二條 x+8）、遞移隱藏帶 `off`、跳欄邊帶 `data-trunk`、無 `laneOffset`、自含、tag 平衡；有 headless Chrome 時以 `--dump-dom` 比對可見節點 transform、三帶元素、可見邊 `d`、`data-trunk`、幹線清單、svg 尺寸與 Python 逐字相同；再把 `toggle-old` 預設勾起載入，斷言舊版 plan／群／R# 可見且每個可見節點各在自己的帶內，並用 DOM 的 path 逐段檢查沒有線穿過任何可見節點；無 Chrome 則印一句略過。
- `validate_ir`：band ext 合法；supplements 目標改成結果 → 「非群的所屬 plan」＋群缺可見對照；從 plan 出發 → 「非敏感性分析群」；對照隱藏 → `graph.nodes[<群>].supplements`；`via` 元素長度錯／col 非 int／`via_order` 長度不符 → `.via／via_order`；隱藏邊帶 via → `.via 只准預設可見的跳欄邊`；stats 缺 `band_ext_nodes`／`crossings`、`edge_node_overlaps` 為負 → `IR-14 graph.stats`；三帶相加不符 → `IR-14 graph.stats.band_main_nodes／band_ext_nodes／band_supp_nodes`；跨區帶邊改可見 → 「跨區帶」。
- 登記錨點：CHANGELOG `## 0.15.0` 含 Extended Data／role_source／_spine_path／via_order／barycenter／crossings／edge_node_overlaps／band_ext_nodes／本檔名；README 與 `status` SKILL.md 含 Extended Data／敏感性對照（SKILL 另含 crossings，frontmatter 未動）；本檔含 `run_v0150_regressions.py`；`plugin.json` ≥ 0.15.0。

## run_v0160_regressions.py

v0.16.0 加「收件匣結構化動作」：主問題降為附錄問題與圖表 role 改定改由 `reassign_question.py`／`set_figure_role.py` 確定性執行，server 加 `--allow-apply` 才開的兩個 actions 端點，關聯圖可拖放送收件匣。fixture 以 tempfile 動態建（v0.7.3；protocol 與 SQ1-v1／SQ2-v1／AQ1-v1 由 `seal_artifact.py` 封版；results 五鍵 k1／k2／r1（SQ1-v1）、m1（SQ2-v1）、a1（AQ1-v1）；validation V1–V3 帶頂層兩段註解與既有 `reaffirmed_2026_09_10`；`project.yaml` 帶多處註解、`state.analysis.rerun` waived 且有兩層 previous_waiver；GLOSSARY §10.4 表；manifest F_a main／F_b extended／F_c 缺 role；收件匣 IN-001 reassign SQ1），斷言讀磁碟實際產出：

- dry-run：整棵目錄 hash 前後相同；摘要 ≤ 30 行、含 `token:`、預定 D-003、retag 3 鍵、V1 改掛；前置條件（無此 SQ、`--to` 已用、無此收件匣、`--expect-token` 不符、role 非法、role 已同值）exit 2 且不寫檔。
- apply SQ1 → AQ2：`project.yaml` 各註解行原樣、AQ2 區塊除 id／status_reason 前綴外與原 SQ1 相等、state 加一行、`state.analysis.rerun` 新值＋`previous_waiver` 推進（第三次）＋內層原樣、validation state 同步；AQ2-v1 封版（sq／version／supersedes／role／timing／created_at／registered_into_pipeline_at 尾綴／timing_justification 加段、其餘 14 個區塊與 SQ1-v1 逐字相同、changes 七條）；index active 與 superseded／replaced_by；results 只有三鍵 plan_id 變且位元組長度相同；validation V1 改掛、每 item 加 `reaffirmed_2026_09_15`、頂層「第三次更新」註解在既有註解之前、fingerprint 等於重算值；waiver 檔；快照；GLOSSARY 主子問題列與 AQ2 列；D-003 各欄（checkpoint／method／decision 條列／reason 含收件匣原文與 `--reason`／rejected 模板／known_consequences 四項 open item／links）且檔案前綴一字未動、新條目 < 3.5 KB；收件匣 done、run log 九步 ok、IR alias、DECISIONS-TIMELINE、daily log 只 append；`check_plan --require-confirmed --results`／`check_validation` 0 blocker／`check_coverage` 0 tamper／`check_decisions` 對 D-003 0 warning／`check_inbox`／`render_progress`／`rerun_all --state-fingerprint` 一致；再搬 SQ1 被擋、搬最後一個主問題要 `--allow-empty-main`。
- `--primary-model M2-alt`（SQ2 → AQ5）：primary_model.id 改、method 尾接原文、specification 前綴註記、assumptions 加一條、R2 新增（expected_keys [m1]、executed true）、R1 原樣、multiplicity.family 補句、results m1 的 model_id／description 前綴而數字不動、k1 不動、D-003 checkpoint 與 (2b)。
- `set_figure_role --figure F_a=supplementary --figure F_c=extended --apply`：manifest 只多一行（F_c 補 role）、F_b 不動、`_note` 不動、備份等於原檔、D-004 figure-design 與 links、IR 落帶 supp／ext。
- 失敗還原：decisions 非清單 → 前置條件 exit 2 不寫檔；唯讀 `decisions.yaml` → 鏈中失敗 exit 1、目錄 hash 還原、AQ2-v1 與備份檔皆不存在；dry-run 後改檔 → `--expect-token` 不符 exit 2。
- payload：`validate_payload` 各錯誤訊息、`validate_submission` 自動 title／body／target、`append_item` 寫 `payload: {...}` 流式 mapping、`check_inbox` 印「可直接：python3 reassign_question.py …」與 payload WARNING、`--resolve` 不動 payload、IR item 帶 payload、HTML 有 `actions-panel`／`act-form`／file:// 說明、JS 通過 `node --check`（有 node 時）。
- server：未開 `--allow-apply` 兩端點 403、`/api/ping` `actions_enabled false`、收件匣 POST 照常（payload 錯誤 400）；開了之後 dry-run 200 帶 24 位 token 且目錄 hash 不變、缺 token 400、非結構化項目 400、不存在 404、期間改 `decisions.yaml` → 409 且無 actions log、apply 200 回 D-003 與 run log、manifest 已改、`PROGRESS.actions.log` 一行、daily log 透傳、已結案再 apply 400、reassign 走完 D-004、跨來源 Origin 403。
- 登記錨點：CHANGELOG `## 0.16.0` 含兩支腳本名／兩個端點／`--allow-apply`／`PROGRESS.actions.log`／`ssot_actions_common.py`／本檔名；README 與 `status` SKILL.md 含腳本名與 `--allow-apply`（SKILL 另含「不得人工重做」「不得整本讀 decisions.yaml」，frontmatter 未動）；`plugin.json ≥ 0.16.0`；新檔與 CHANGELOG／SKILL 不用 arm 的直譯字。

## run_v0161_regressions.py

v0.16.1 加四種 SSOT 搬移動作（`promote_question.py`／`move_plan.py`／`move_sensitivity.py`／`reorder_questions.py`）與關聯圖拖曳時的即時接線預覽。fixture 以 `run_v0160_regressions.build_fixture` 為底（monkeypatch PROJECT／plan_doc）：多一個沒有 active plan 的附錄問題 AQ2（blocked）、SQ1-v1 多一個 robustness R2（expected_keys r2，不在 outputs）、results 多 r2 並重接 fingerprint。斷言讀磁碟實際產出：

- dry-run：四支腳本目錄 hash 前後相同、摘要 ≤ 30 行含 token；前置條件 exit 2——promote（from 非 AQ、無此 AQ、`--to` 已被使用、`--to` 非 SQ、無 active plan）、move_plan（目標已有 active plan、來源是主問題、非 active plan、目標不在 goals）、move_sensitivity（R 不存在、同一 plan、primary 只剩一項、目標非 active）、reorder（id 集合不符、順序相同、重複 id）、`--expect-token` 不符。
- promote apply 與往返：reassign SQ2 → AQ3 後 promote AQ3（`--to` 省略）回原號 SQ2、新版 SQ2-v2 supersedes AQ3-v1、role primary、goals 搬回（只改 id 與 status_reason 前綴、state 註解）、results 只改 plan_id、validation V2 改掛＋reaffirmed＋頂層「第四次更新」註解、waiver 推進 previous_waiver、快照、GLOSSARY 主子問題列與 AQ3 列註記、D-004 evaluate（覆蓋 gate 句、四項 open item、links）、run log 九步、備份、daily log 只 append、各 checker 全過；再 reassign `--to AQ3`（已空出的號）→ AQ3-v2 supersedes SQ2-v2；promote `--to` 指定與原號被占用 → 最大 SQ 號 +1（SQ3）。
- move_plan apply（AQ1-v1 → AQ2，經收件匣 IN-002）：來源 links 搬到目標尾端、來源 blocked＋前綴、目標前綴、AQ2-v1 封版 supersedes AQ1-v1（其餘區塊逐字同）、index、results a1、validation V3 改掛、fingerprint、快照 0 tamper、D-003 study-design（設計變更、open item、收件匣原文）、收件匣 done、daily log；之後再搬到 AQ2 被擋。
- move_sensitivity apply：SQ1-v1 R2（r2 不在 outputs）→ SQ2-v1：SQ1-v2 只剩 R1、SQ2-v2 追加 R2 逐字、r2 retag 到 SQ2-v2、V1／V2 改掛新版、每 item 加 reaffirmed、D-003 study-design；AQ1-v1 R1（a1 在 outputs）→ SQ2-v2：AQ1-v2 沒有 robustness（exploratory 可）、SQ2-v3 的 R3 expected_keys 改指 m1、`evidence_owned_by: AQ1-v2`、`evidence_keys: [a1]`、execution_note 前綴；a1 留在 AQ1-v2。
- reorder apply：sub_questions SQ2／SQ1——文字層順序、項目內註解與行尾註解跟著走、`# 附錄問題` 與清單頭不動、state 註解；只改 project.yaml／decisions.yaml／validation.yaml（source 重接、item 不改掛）／waiver／重畫產物；results fingerprint、快照、results.json 不動；D-003 evaluate 記新舊順序與 fingerprint；appendix AQ2／AQ1 時 id 行尾註解與項目前註解行跟著區塊走。
- 失敗還原：四支腳本在唯讀 `decisions.yaml` 下鏈中失敗 exit 1、目錄 hash 還原、新建 plan 與備份檔皆不存在；dry-run 後改檔 → token 不符。
- payload：四種 kind 的 `validate_payload` 各錯誤訊息、`ACTION_KINDS` 六種同序、`validate_submission` 自動 title／target、`check_inbox --list` 印四種建議命令、payload WARNING、IR item 帶 payload、HTML 面板列六種 kind 與五筆 pending。
- server：`/api/ping` 帶 `next_sq`；六種 kind 經 `/api/inbox` 進來（錯誤 400）；六筆 dry-run 都回 summary＋24 位 token 且不寫檔；套用 reorder 後舊 token 409；move_sensitivity／move_plan 重新預覽後 apply；plan 已搬走的舊 promote 項目 dry-run 回 `ok: false`、`rc: 2` 不寫檔；新 promote AQ2 → SQ3；`PROGRESS.actions.log` 四行、daily log 四段、已結案 400；最後 index active 與 checker 全過。
- 拖曳預覽：HTML 有空的 `<g id="drag-preview">`（在 graph-nodes 之後）、JS 錨點（`dragCandidate`／`drawDragPreview`／`clearDragPreview`／`openActionForm`／`hitNode`／`activePlanOf`／`listOrder`）、六組表單欄位、CSS 打亮類；IR 不含預覽；有 node 時 `node --check` 主 script，並把 `dragCandidate` 與它用到的小函式抽出來、用 IR 的 graph 跑 15 個案例（同帶問題 → reorder 與順序、跨帶 → reassign／promote、ext 帶非法、方法 → 問題 move_plan 含「目標已有 active plan」與「來源是主問題」兩種紅色、子分析 → 方法、同一 plan 無候選、圖表落帶、`q:main` 無候選）。
- 登記錨點：CHANGELOG `## 0.16.1` 含四支腳本名／`drag-preview`／本檔名；README 與 `status` SKILL.md 含四支腳本名與四種 kind；本檔含 `run_v0161_regressions.py`；`plugin.json ≥ 0.16.1`；五支腳本 `VERSION = '0.16.1'`；新檔與 CHANGELOG／SKILL 不用 arm 的直譯字。

## run_v0162_regressions.py

v0.16.2 加第七種 SSOT 搬移動作「結果鍵搬家」（`move_result.py`，kind `move_result`）與關聯圖結果節點可拖。fixture 沿用 `run_v0161_regressions.fixture`（SQ1-v1 outputs k1／k2、R1 r1、R2 r2；SQ2-v1 outputs m1、R1 m1；AQ1-v1 outputs a1、R1 a1；AQ2 無 plan）。斷言讀磁碟實際產出：

- dry-run：A 型（k2 → SQ2-v1）與 B 型（r2 → AQ1-v1 R1）目錄 hash 前後相同、摘要 ≤ 30 行含 token；前置條件 exit 2——鍵不存在、目標非 active、同一份 plan 且已在 outputs（無事可做）、R 已含該鍵、R 不存在、來源 outputs 只剩一鍵、來源 plan 非 active（results.json plan_id 指到舊版）；`--expect-token` 不符。
- apply A 型（k2 → SQ2-v1）：SQ1-v2 outputs 只剩 k1、robustness 逐字；SQ2-v2 outputs 尾端多 k2（條目與 SQ1-v1 的逐字相同）；estimand／primary_model／validation／scripts／notes／multiplicity／question 不動；index 兩邊 active 與 replaced_by；results 五鍵只改 plan_id、其餘逐鍵相同；V1 primary_results 由 [k1, k2] 變 [k1]（流式清單重寫）並改掛 SQ1-v2、V2 改掛 SQ2-v2、三個 item 各加 reaffirmed；SQ1 links 去掉 `results:k2`、SQ2 links 尾端加上、行尾註解保留、兩邊 status_reason 前綴＋原文、state 註解一行；D-003 stage study-design、question SQ2、decision 八段、known_consequences 含設計變更／V1 移除該鍵／四項 open item、links、method；run log 九步 ok、備份檔存在；checker 全過。
- apply B 型（接著 r2 → AQ1-v1 R1）：SQ1-v3 的 R2 expected_keys 由 [r2] 變空 → 改指本 plan outputs 鍵 [k1]、`evidence_owned_by: AQ1-v2`、`evidence_keys: [r2]`、execution_note 前綴＋原註；AQ1-v2 的 R1 expected_keys [a1, r2]、不加 evidence_owned_by、execution_note 前綴、其餘欄位逐字；results r2 → AQ1-v2；V1／V3 改掛；links 原本沒有 `results:r2` 就不動；D-004。目標已含該鍵再搬 exit 2。
- 同一份 plan 只出一版：k1 由 outputs 搬到自己的 R1（SQ1-v2：outputs [k2]、R1 [r1, k1]、不記 evidence_owned_by、validation 不改掛不移除、links 不動、status_reason 前綴）；r2 由 R2 搬到自己的 outputs（SQ1-v3：補的 outputs 條目照既有條目形狀、R2 改指 [k2]）。
- 未宣告鍵：results.json 掛在 SQ1-v1 但未宣告的 u1 → SQ2-v1：來源不出新版（無 SQ1-v2）、SQ2-v2 outputs 多 u1、只 retag u1 與 m1。
- 失敗還原：三種搬法在唯讀 `decisions.yaml` 下鏈中失敗 exit 1、目錄 hash 還原、新建 plan 與備份檔皆不存在；dry-run 後改檔 → token 不符。
- payload：`validate_payload` 各錯誤訊息、`ACTION_KINDS` 七種同序（`move_result` 在尾端）、`action_argv`、`validate_submission` 自動 title／body／target `r:<key>`、`check_inbox --list` 印兩種建議命令、to_item 壞掉 WARNING、IR item 帶 payload 與 target、HTML 面板列七種 kind 與三筆 pending、結果節點掛「收件 1」徽章。
- server：兩筆 `move_result` 經 `/api/inbox` 進來（已含該鍵或缺 key 400）；dry-run 回 summary＋24 位 token 且不寫檔；apply A 型回 D-003 後 B 型舊 token 409、重新預覽後 apply 回 D-004；已結案 400；`PROGRESS.actions.log` 兩行、daily log 兩段、D-003 reason 含收件匣原文與 `--inbox`。
- 關聯圖：HTML／JS 錨點（`isDragResult`／`resultOwner`／`act-move-result-fields`／`ACT_LABEL.move_result`／圖例句）、`node --check`；把 `dragCandidate` 與小函式抽到 node 用 IR graph 跑 10 個候選判定（主要結果 → 別的 plan A 型、→ 自己 plan 已在 outputs 紅、→ 自己的 R B 型、次要結果 → 已含它的 R 紅、→ 自己 plan 合法且註明同一份 plan 出一版、主要結果 → 已含它的 R 紅、別 plan 的鍵 → 任一 R B 型、空白／問題節點／敏感性群節點無候選）與 `draggable`（驗證節點與敏感性群節點不可拖）。
- 登記錨點：CHANGELOG `## 0.16.2` 含腳本名與本檔名；README 與 `status` SKILL.md 含 `move_result.py`；本檔含 `run_v0162_regressions.py`；`plugin.json` ≥ 0.16.2；`VERSION = '0.16.2'`；相關檔不含 arm 的直譯字。

## run_v0163_regressions.py

v0.16.3 把拖放流程縮短一步：放開節點、填理由、按「送出並預覽」後，同一個對話框立刻顯示 dry-run 摘要，摘要下「套用」「先留在收件匣」「撤回」；server 多一個 `POST /api/inbox/dismiss`。fixture 沿用 `run_v0161_regressions.fixture`。執行：`python3 tests/run_v0163_regressions.py`（有 google-chrome／chromium 時多跑瀏覽器端到端，約 1–2 分鐘；沒有就印一行跳過）。

- `/api/inbox/dismiss`：未開 `--allow-apply` 的 server 上，兩筆 `set_role` 進收件匣 → dismiss 第一筆（省略 note）200、status dismissed、note 為預設「使用者在放開預覽後撤回」、目錄裡只有收件匣與進度產物變、IR 該筆 dismissed、`/api/ping` `inbox_pending` 減一；第二筆帶自訂 note；同一筆再 dismiss 400（非 pending）、`IN-999` 400、缺 id／空 id／note 過長 400、`text/plain` 415、外來 Origin 403，pending 那筆都沒被動到；actions 端點仍 403。開 `--allow-apply` 後 dismiss 照常，dismissed 那筆再 dry-run／apply 都 400；`check_inbox.py` 計數 `pending 1／done 0／dismissed 3`；checker 全過。
- 對話框錨點：`#act-preview-box`（預設 hidden）、`<pre id="act-summary" class="act-summary">`、`#act-dismiss`／`#act-keep`／`#act-apply`（預設 disabled）、`#act-submit-row`、送出鈕「送出並預覽」、`#act-item-id`；`pre.act-summary` 樣式不再只限面板；JS 的 `actStage`／`actPreview`／`actApply`／`actDialogUi`／`actRowUi`／`actBusy`／`actPost`／`closeActForm` 各只定義一次，`'/api/actions/dry-run'` 與 `'/api/actions/apply'` 各只出現一次（面板與對話框共用）、`'/api/inbox/dismiss'` 一次且帶預設 note、送出成功後 `actStage('preview')` 直接 `actPreview`、409 走 `ui.onStale`、403 的套用鈕 title、對話框 `confirm:false` 面板 `confirm:true`、四個開表單入口加 `closeActForm` 共五處回到 form 階段；`node --check`。
- headless Chrome（stdlib 寫的最小 CDP client：起 `--headless=new --remote-debugging-port=0`、讀 `DevToolsActivePort`、websocket 送 `Runtime.evaluate`）：fixture server `--allow-apply` 起在隨機 port，頁面由 `GET /` 來。(a) 切到關聯分頁，用 MouseEvent 在 `.gnode[data-node-id="r:k2"]` mousedown、window mousemove 到 `p:SQ2-v1` 的中心、mouseup → 表單開、標題「搬結果：k2 → SQ2-v1」、欄位帶入、拖曳中預覽標籤「搬結果：成為 SQ2-v1 的主要結果」；填理由 `requestSubmit()` → 對話框切到預覽階段（欄位鎖住、送出列隱藏、顯示 IN-002）、摘要出現含「k2（SQ1-v1 的主要結果）→ SQ2-v1 outputs」與 24 位 token、套用啟用、收件匣該筆 pending 且 body 含理由；按「撤回」→ 頁面 reload 後收件匣該筆 dismissed（預設 note）、只有收件匣與進度產物變。(b) 拖 `r:r2` 到 `p:AQ1-v1#R1` → B 型摘要 → 外部在 `decisions.yaml` 加一行 → 按「套用」→ 409 → 對話框自動重跑 dry-run、拿到不同的 token、未寫檔 → 再按「套用」→ 摘要含「決策 D-003」、收件匣該筆 done、SQ1-v2／AQ1-v2 落地、D-003 的 decision／reason 引用 IN-003、`PROGRESS.actions.log` 一行；checker 全過。(c) 未開 `--allow-apply` 的 server：送出後摘要區顯示「未開 --allow-apply」、套用停用（title 說明）、撤回與先留在收件匣可用；撤回後該筆 dismissed。
- 登記錨點：CHANGELOG `## 0.16.3` 含 `/api/inbox/dismiss`、「送出並預覽」、`actPreview`、本檔名；README 與 `status` SKILL.md 含 `/api/inbox/dismiss`；本檔含 `run_v0163_regressions.py`；`plugin.json` ≥ 0.16.3；相關檔不含 arm 的直譯字。

## run_v0164_regressions.py

v0.16.4 讓結果節點也能拖到區帶（Main／Supplementary），並給 `move_result.py` 加 `--new-item`（在目標 plan 新增一個 `R<n+1>` 收該鍵）。fixture 沿用 `run_v0161_regressions.fixture`，headless Chrome 的 CDP client 沿用 `run_v0163_regressions`。執行：`python3 tests/run_v0164_regressions.py`（有 google-chrome／chromium 時多跑瀏覽器端到端，約 1 分鐘；沒有就印一行跳過）。

- `--new-item` 同一份 plan：dry-run 不寫檔、摘要那行帶「新增的 R3」與預設描述「補充結果：k2 由主要結果降為次要結果」；`--to-item` 與 `--new-item` 同給 exit 2（兩種順序）；apply 後 SQ1-v2 的 outputs 只剩 k1、robustness 為 R1／R2（逐字）＋R3（欄位順序 id／change／expected_keys／executed／execution_note；expected_keys 只有 k2、executed true、execution_note 含「只是歸屬容器」）、amendment_reason／changes 的措辭、results 四鍵 retag、index active、D-003 的 checkpoint／method（帶 `--new-item "…"`）／decision（「R3（新增子分析，change「…」）」）／known_consequences（「新增的 R 只是歸屬容器」）、run log 的 args；全部 checker 通過；重畫後 `r:k2` 在 `p:SQ1-v2#R3` 之下、Supplementary 帶；對已在新 R 之下的鍵再 `--new-item` 一次的 dry-run 合法（R4）。
- `--new-item` 跨 plan、自訂描述：k2 → AQ1-v1 出 SQ1-v2／AQ1-v2 兩版，AQ1-v2 的 R1 逐字、R2 新增（change 用給的描述、execution_note 記「自 SQ1-v1 的 outputs 搬入」）、來源 robustness 不動、results retag、D-003 的 question 為 AQ1；checker 全過、重畫後在 `p:AQ1-v2#R2` 之下。
- payload：`validate_payload` 的 `new_item` 非空才進正規化 dict（空字串走 A 型規則）、與 `to_item` 互斥、非字串擋；`new_item_text`／`next_robustness_id`／`NEW_ITEM_DEFAULT`；`action_argv` 帶 `--new-item <描述>`；title「搬結果：k2 → SQ1-v1 新增子分析」；token extra 只在有 new_item 時多一段（0.16.2 的字串不變）；server `/api/inbox` 兩者同給 400、只給 `new_item` 201 並在收件匣落 `to_item: ''`＋`new_item`；`check_inbox --list` 建議命令帶 `--new-item`；dry-run 摘要與 apply（D-003、R3 落地）。
- 關聯圖候選判定（node 跑抽出的 JS，假 `bandAtY`）：主要結果 Main → Supplementary 帶（候選＝帶、無 target、options＝新增子分析／R1／R2／AQ1-v1 的 outputs、payload＝首項）、次要結果 Supplementary → Main 帶（升回本 plan 的 outputs／SQ2-v1 的 outputs）、附錄問題的主要結果拖到 Supplementary 帶（ok false「已在 Supplementary」）、附錄問題的結果拖到 Main 帶（只列 SQ1-v1／SQ2-v1 的 outputs）、Extended Data 帶（ok false）、同帶兩例 null、把主問題 plan 都折疊後再拖附錄結果到 Main（ok false「沒有主問題的 active plan 可以收」）；表單 `#act-mr-dest-wrap`／`#act-mr-dest`、`mrFill`／`nextRid`、圖例句與結果節點動作說明的錨點；前端預設描述與 `ssot_actions_common.NEW_ITEM_DEFAULT` 同一句；`node --check`。
- headless Chrome：`r:k2` 拖到 Supplementary 帶、`p:SQ1-v1#S` 左側 120px 空白處放開 → 預覽標籤「搬結果：放到 Supplementary 帶、降為次要結果（放開後選落點）（放開後填理由）」、帶打亮 `drop-ok`、沒有預覽線 → 表單開、下拉可見四個選項、預設第 0 項、標題「搬結果：k2 → SQ1-v1 新增子分析」、to_item 欄「新增 R3：…」→ 換選 AQ1-v1 的 outputs（標題／欄位跟著換）再換回 → 填理由送出 → 摘要含「新增子分析 R3」與 token、收件匣 payload 帶 `new_item` → 撤回 → dismissed；再把 `r:a1` 拖到 Supplementary 帶空白處 → 帶改紅、不開表單、toast「已在 Supplementary」。
- 登記錨點：CHANGELOG `## 0.16.4` 含 `--new-item` 與 `act-mr-dest`；README 與 `status` SKILL.md 含 `--new-item`；本檔含 `run_v0164_regressions.py`；`plugin.json` ≥ 0.16.4；`VERSION = '0.16.4'`；相關檔不含 arm 的直譯字與常見簡體字。
- 為了讓 `run_v0162_regressions.py` 在 0.16.4 之後仍通過，該檔的兩處 `move_result.py` 版號斷言改讀腳本的 `VERSION`，「主要結果拖到 `p:SQ1-v1#S` 上」那一例改為接受區帶候選（0.16.4 起不再是 None）。
