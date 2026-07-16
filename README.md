# academic-pipeline v0.7.3

`academic-pipeline` 是一套以 artifacts、獨立角色與確定性檢核構成的研究—論文 pipeline。v0.7 將原本以「資料已取得後的定量論文生產」為中心的流程，擴充為可處理一般研究的治理與驗證架構。

## v0.7 主流程

```text
project-init
→ methodology-router
→ integrity-check (prestudy)
→ study-design
→ data-audit
→ [analyze-data ∥ lit-review / evidence-synthesis]
→ clean-room rerun
→ code-review
→ validate-results
→ evaluate
→ interpret-results
→ claim-audit
→ 人工確認 claims
→ figure-design
→ write-manuscript
→ write-supplementary
→ check-consistency (zh)
→ peer-review ⇄ revise
→ 中文潤稿（chinese-deai-editing，選用外部掛點）
→ 中文人工定稿
→ translate-en
→ 英文潤稿（academic-english-editing，選用外部掛點）
→ 英文人工確認
→ check-consistency (en，完整重跑)
→ submission-prep
→ integrity-check (presubmission)
→ 最終 gate 檢查
→ typeset
```

`project.yaml` 的 `state` 是快取；protocol、plans、results、validation、claims、audit reports 等 artifacts 才是狀態真相。任何承重來源變動，都必須使下游 pass 狀態失效。

## v0.7.3 主問題與附錄問題分離

`goals` 新增 `appendix_questions`，把「穩健性／敏感度／跨方法」這類 **defend 主答案而非產生新答案** 的問題，從 `sub_questions` 移出、獨立成塊，不再混列灌大 SQ 數。判準是問的對象：問「現象」（X 與 Y 是否關聯、機制、邊界）屬 `sub_questions`；問「分析本身」（換方法／換設定下主結果是否維持、跨方法收斂或分歧）屬 `appendix_questions`，報在附錄／SI。

- **schema**：`project-template.yaml` 的 `goals.appendix_questions` 預設 `[]`，欄位結構與 `sub_questions` 相同，id 用 `AQ#`。缺此鍵對舊專案回溯相容（視同 `[]`）。
- **分離的制度後果**：`decomposition-review` 與 `full` 的目標覆蓋只以 `sub_questions` 判定「主問題答了沒」；附錄問題不計入主覆蓋、不進裁決史與稿件收錄檢查，也不能拿它們的 `addressed` 去補主問題的覆蓋缺口。
- **仍受機械把關**：`check_coverage.py` 對附錄問題套用同一套逐項 integrity 檢查（終態、links 有效、`addressed` 須有 links），並納入 `--snapshot` 竄改偵測——證據鏈斷不斷不因層級豁免。附錄問題在報告中另段呈示。
- **回溯相容**：`--snapshot` 讀舊版裸 list 快照仍可運作，`--update-snapshot` 起改寫為 `{sub_questions, appendix_questions}` 物件。skills（23）與 agents（18）數量不變，管線階段未新增；新增回歸測試 `tests/run_v073_regressions.py`。

## v0.7.2 規則密度回填與 producer 修補

0.7.0 在重寫核心 SKILL／agent 時，把 v0.6 的規則、紅線與防呆條款一併壓縮掉；0.7.1 只修回其中四項。0.7.2 以 v0.6 的文件結構與規則密度為基準做全面回填，並修掉兩個實質功能缺口。skills（23）與 agents（18）數量不變，管線階段未新增。

回填的高風險條款：

1. `agents/reviewer-methods.md` 的「code-review 限縮在正確性；風格類意見一律 suggestion，不得列 blocker」與 strictness 旋鈕。
2. `evaluate` 的短路規則（腳本有 blocker → 不啟動 evaluator）、Fallback 自評、`--update-snapshot` 收尾。
3. `project-init` 的 `decisions.yaml` 完整 schema 與三類 D# 觸發條件、「推翻既有決策先呈示原 D#」。
4. `write-manuscript` 的數字標註豁免清單——依**現行 `check_numbers.py` 行為**重寫，不照抄 v0.6 文字。
5. `agents/data-analyst.md` 四條核心原則、`agents/fact-checker.md` 的 Bash 權限與「blocker 未清空即為未通過」、`agents/reviewer.md` 的範圍凍結上限。
6. `project-init/references/project-template.yaml` 的逐欄註解（3.1KB → 10.6KB；欄位集合與 0.7.1 完全相同）。

修掉的功能缺口：

7. **文獻型 SQ 的 `cite:` links 沒有 producer**：0.7.1 壓縮 lit-review 時刪掉了「把 `cite:<citekey>` 寫進 `goals[].links`」的收尾步驟，但 `evaluate` 的 full 硬前置與 `check_coverage.py` 仍要求 links——`evidence: [literature]` 的 SQ 一旦 addressed 就必然 BLOCKER。0.7.2 把寫入者寫死為單一責任：`focused` 由 lit-review 收尾寫入，`systematic`／`scoping`／`meta-analysis` 由 evidence-synthesis 寫入。
8. **未經審查的 citekey 可充當證據鏈**：`check_coverage.py` 新增 `--evidence`，`cite:` 的 citekey 必須出現在 evidence-synthesis 的 `studies[].citekey`，否則 BLOCKER（未傳旗標或檔案不存在則略過）。
9. **`display` 欄位的孤兒功能**：`check_numbers.py` 一直在執法，但 0.7.1 已無人被要求產生此欄位。契約接回 data-analyst（產生端）、write-manuscript（使用端）與 project-template。

## v0.7.1 相容性與既有契約修補

0.7.1 修正 0.7.0 在重寫核心 SKILL/agent 文件時造成的四項回歸：

1. `check_gate.py` 的舊專案分支改以 `pipeline.version` 判斷；v0.6 已有 `{result, version}` 的 consistency state 不再因缺少 v0.7 才新增的 `gate_fingerprint`／`report` 被阻擋。
2. 恢復 `state.review.scores` 的 producer contract：每個完整 panel 輪次，不論裁決為 accept／minor／major／reject，都由 `record_review_score.py` 從 editor 的固定 YAML block 寫入；`check_ledger.py` 再據此計算分數差與邊際遞減。
3. 恢復外部 `chinese-deai-editing` 中文潤稿掛點；與 `academic-english-editing` 一樣，未安裝自動略過，已安裝時只能修改語言呈現，之後重跑完整一致性檢核。
4. 恢復 `agents/editor.md` 的共同分數帶定錨（1–3／4–5／6–7／8–10）、contribution 兩個具名子問題與 machine-readable score block，維持跨輪可比性。

## v0.7 六項補強

### 1. 正式、版本化的研究與分析計畫

新增 `study-design` skill 與 `research-designer` agent。研究設計落地為：

- `protocol/study-protocol.yaml`
- `analysis/plans/<SQ>-vN.yaml`
- `analysis/plans/index.yaml`

confirmed plan 以 content hash 封存；修改須建立新版本、標示 `supersedes`、`amendment_reason` 與差異，不得原地改寫。results 每筆必須連回 active `plan_id`、`model_id` 與 `data_fingerprint`。

### 2. 正確排序的 clean-room rerun

`analyze-data` 現在強制：

```text
執行 sealed plan
→ results schema / manifest 檢核
→ clean-room rerun
→ code-review
→ validate-results
→ result-fit / 人工確認
```

`rerun_all.py` 只複製 inputs，不複製既有 `results.json`、derived data、生成圖表、reports、validation 或 manuscript。fingerprint 涵蓋 raw data、完整 `analysis/scripts/`（含 helper modules）、run-order、明示的非標準 inputs、protocol／active plans、data profile/audit、manifest、methodology route、分析設定與環境 lock；未從零重建輸出即失敗。非標準設定或 frozen model 需以 run-order 的 `inputs=` directive 登記。

### 3. 獨立結果驗證

新增 `validate-results` skill 與 `statistical-validator` agent。定量、ML、模擬路線以 `analysis/validation.yaml` 記錄模型診斷、影響點、替代規格、缺失值、多重比較、穩定性／外部驗證、null precision，以及承重結果的第二實作或獨立重算；`source_fingerprint` 直接復用 clean rerun 的完整 input+results 契約，避免只改程式／計畫卻沿用舊 validation。

質性、系統性回顧、混合方法與理論研究使用 adapter validation artifacts：

- `analysis/qualitative-audit-trail.yaml`
- `analysis/review-validation.yaml`
- `analysis/integration/joint-display.yaml`
- `analysis/proof-audit.yaml`

### 4. 獨立主張反方審查

新增 `claim-audit` skill 與 `claim-critic` agent。`interpreter` 只能起草 `claims.yaml`；claim-critic 逐條攻擊 entailment、主張強度、反證、適用邊界、選擇性報告與探索轉驗證問題。audit 同時保存 claims 語意 fingerprint 與上游 source fingerprint；results／validation、evidence、route 或 active plans 任一漂移，都會擋下舊 audit。

### 5. 英文定稿後的完整一致性 gate

英文人工確認不再直接進 submission-prep。`translate-en` 後強制執行完整 `check-consistency(en)`，重查：

- 上游 route、plans、data/evidence audit 與 validation；
- 數字、表格、引用、claims 與圖文；
- 中文—英文 claim strength、限定語與方法語意；
- SI、摘要、正文與 reporting guideline。

`check_gate.py` 以 gate fingerprint 防止沿用過期 pass；除稿件外，也直接雜湊 raw data、analysis scripts／environment lock、validation/evidence source artifacts 與實際 figure files。投稿前只接受與目前英文稿及承重來源完全相符的 full consistency state。

### 6. 一般研究所需的治理與方法 adapter

新增：

- `data-audit` + `data-auditor`
- `evidence-synthesis` + `evidence-auditor`
- `integrity-check` + `integrity-officer`
- `methodology-router` + `methodology-router` agent

內建七種 adapter：

1. `quantitative-inference`
2. `predictive-ml`
3. `qualitative`
4. `mixed-methods`
5. `systematic-review-meta-analysis`
6. `simulation-computational`
7. `theoretical-mathematical`

每個 adapter 定義自己的 required gates、plan requirements、data audit checks、validation checks、results contract、interpretation limits 與 reporting guideline 建議。

## 元件

### Skills（23）

`project-init`、`methodology-router`、`integrity-check`、`study-design`、`data-audit`、`analyze-data`、`validate-results`、`lit-review`、`evidence-synthesis`、`evaluate`、`interpret-results`、`claim-audit`、`figure-design`、`write-manuscript`、`write-supplementary`、`check-consistency`、`peer-review`、`revise`、`translate-en`、`submission-prep`、`journal-match`、`status`、`typeset`。

### Agents（18）

新增七席：`methodology-router`、`research-designer`、`data-auditor`、`statistical-validator`、`evidence-auditor`、`claim-critic`、`integrity-officer`。既有 agent 維持專責分工；設計者不審自己的設計、分析者不驗自己的結果、主張起草者不審自己的主張。

### v0.7 新增的確定性腳本

- route：`check_route.py`
- protocol／plans：`init_protocol.py`、`init_plan.py`、`seal_artifact.py`、`check_plan.py`
- data audit：`profile_data.py`、`check_data_audit.py`
- results：`check_results_schema.py`、重寫的 `rerun_all.py`
- validation：`check_validation.py`、`check_adapter_validation.py`
- evidence：`seal_evidence_protocol.py`、`check_evidence.py`
- claims：擴充的 `check_claims.py`、`check_claim_audit.py`
- integrity：`check_integrity.py`
- consistency：`check_gate.py`
- review state：`record_review_score.py`（驗證 editor score block、依 round 去重、寫入 `state.review.scores`）

機械檢核歸 scripts；需要領域判斷的工作歸 agents；人工確認與方向性取捨寫入 `decisions.yaml`。

## 審稿分數與潤稿掛點

`agents/editor.md` 的四段分數帶是跨輪共同基準，不得在壓縮文件時省略。editor 的完整 panel 裁決末尾必須有唯一 `REVIEW_SCORE` YAML block；peer-review 隨即執行：

```bash
python3 skills/revise/scripts/record_review_score.py \
  project.yaml reviews/roundN/editor-decision.md
```

minor re-check 不建立新 score；下一個完整 panel 輪才新增。寫入後再跑 `check_ledger.py`，保證邊際遞減不是名義上存在、實際上永遠無資料。

中文與英文潤稿站皆為選用的外部 user skills，不是本 plugin 內建目錄：`chinese-deai-editing`、`academic-english-editing`。未安裝不報錯；潤稿後必須建立新版本並重跑相應語言的 full consistency。

## 主要事實與治理 artifacts

```text
project.yaml
methodology/route.yaml
protocol/study-protocol.yaml
analysis/plans/index.yaml + active plans
analysis/data-profile.json
analysis/data-audit.yaml
analysis/data-manifest.yaml
analysis/results.json 或 adapter findings artifact
analysis/validation.yaml 或 adapter validation artifact
literature/evidence-protocol.yaml
literature/evidence-synthesis.yaml
analysis/claims.yaml
analysis/claim-audit.yaml
integrity/register.yaml
analysis/exploration-log.yaml
reviews/issue-ledger.yaml
decisions.yaml
```

## 回溯相容與升級

沒有 `pipeline.version >= 0.7` 的舊專案，新增 checker 以相容模式運作。`check_gate.py` 對完全沒有 last_consistency 的舊專案只輸出 INFO；對已跑過 v0.6 consistency 的專案只驗既有的 `result` 與 `version`，不要求 `gate_fingerprint`、`report`、`language` 或 `en_final.confirmed_at`。只有明確 `--strict` 或升版到 0.7.x 後才啟用完整 fingerprint gate。升級不是只改版本號：先備份，再依 [`MIGRATION-v0.7.md`](MIGRATION-v0.7.md) 補 route、integrity、protocol/plans、audit、validation、evidence 與 claim-audit。

## 測試

```bash
python3 -m compileall -q agents skills tests
python3 tests/run_v07_smoke.py
python3 tests/run_v071_regressions.py
python3 tests/run_v072_regressions.py
```

`tests/mini-project` 保留 v0.6 黃金答案；`run_v071_regressions.py` 另驗證 legacy populated consistency、strict opt-in、review score 寫入／邊際遞減、中文潤稿掛點與 editor 分數帶不再消失。`run_v072_regressions.py` 以跨檔案錨點驗證回填的規則條款（agent 紅線、短路規則、決策日誌、數字豁免、模板註解），並實測 `check_coverage.py --evidence` 的四種情境。`run_v07_smoke.py` 動態建立 v0.7 專案，驗證七種 adapter 的 plan contract、adapter 專屬 data/validation checks、clean-room 重跑、資料稽核、results schema、validation、evidence source fingerprint、claim-audit、integrity 與中英文 consistency source-staleness gate。

腳本需要 Python 3.10+ 與 PyYAML。排版功能另依原有 typeset 說明使用 pandoc／LaTeX。
