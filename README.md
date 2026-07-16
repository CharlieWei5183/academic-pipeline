# academic-pipeline

`academic-pipeline` 是一套以 artifacts、獨立角色與確定性檢核構成的研究—論文 pipeline，涵蓋從專案初始化、方法學路由、資料分析，到中英文稿撰寫、虛擬同儕審查、投稿與排版的全流程。設計目標是可稽核、可重現、能跨 Cowork session 穩定執行的 agent 驅動研究流程；所有輸出為繁體中文。

核心原則：`project.yaml` 的 `state` 只是快取；protocol、plans、results、validation、claims、audit reports 等 artifacts 才是狀態真相。任何承重來源變動，都必須使下游 pass 狀態失效。

## Pipeline 主流程

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
→ 英文潤稿（academic-english-editing，內建·選用）
→ 英文人工確認
→ check-consistency (en，完整重跑)
→ submission-prep
→ integrity-check (presubmission)
→ 最終 gate 檢查
→ typeset
```

## 核心設計

**版本化研究與分析計畫**：`study-design` skill 與 `research-designer` agent 把研究設計落地為 `protocol/study-protocol.yaml`、`analysis/plans/<SQ>-vN.yaml` 與 `analysis/plans/index.yaml`。confirmed plan 以 content hash 封存；修改須建立新版本並標示 `supersedes`、`amendment_reason` 與差異，不得原地改寫。每筆 result 必須連回 active `plan_id`、`model_id` 與 `data_fingerprint`。

**clean-room rerun**：`analyze-data` 強制「執行 sealed plan → schema/manifest 檢核 → clean-room rerun → code-review → validate-results → 人工確認」。`rerun_all.py` 只複製 inputs，fingerprint 涵蓋 raw data、完整 `analysis/scripts/`、run-order、protocol／active plans、data profile/audit、manifest、方法路由與環境 lock；未從零重建輸出即失敗。

**獨立結果驗證**：`validate-results` skill 與 `statistical-validator` agent 以 `analysis/validation.yaml` 記錄模型診斷、影響點、替代規格、缺失值、多重比較、穩定性與承重結果的獨立重算；質性／系統性回顧／混合方法／理論研究改用對應 adapter validation artifacts。

**獨立主張反方審查**：`interpreter` 只能起草 `claims.yaml`；`claim-audit` skill 與 `claim-critic` agent 逐條攻擊 entailment、主張強度、反證、適用邊界與探索轉驗證問題。任一上游 fingerprint 漂移都會擋下舊 audit。

**英文定稿後的完整一致性 gate**：`translate-en` 後強制執行完整 `check-consistency(en)`，重查上游 route/plans/audit/validation、數字表格引用圖文、中英 claim strength 與方法語意。`check_gate.py` 以 gate fingerprint 防止沿用過期 pass。

**治理與方法 adapter**：`methodology-router`、`data-audit`、`evidence-synthesis`、`integrity-check` 提供一般研究所需治理；內建七種 adapter——`quantitative-inference`、`predictive-ml`、`qualitative`、`mixed-methods`、`systematic-review-meta-analysis`、`simulation-computational`、`theoretical-mathematical`——各自定義 required gates、plan／validation／results 契約、interpretation limits 與 reporting guideline。

**主問題與附錄問題分離**：`goals` 分為 `sub_questions`（問「現象」：X 與 Y 是否關聯、機制、邊界）與 `appendix_questions`（問「分析本身」：換方法／換設定下主結果是否維持）。目標覆蓋只以 `sub_questions` 判定主問題是否答足；附錄問題不計入主覆蓋，但同受 `check_coverage.py` 的逐項 integrity 檢查。

**內建英文潤稿站**：`academic-english-editing` 為內建 skill，源自 `academic-humanizer` v0.3.3（MIT）的 Layer 1／2／3／5，逐節標註來源；刻意不含會改動 claim strength 的 Layer 4（發現 over-claim 只標記回 `claim-audit`）。掛點只改語言呈現，不得動數字、markers、citekey、claim strength、validation boundary 或方法語意，潤稿後重跑對應語言的 full consistency。

## 元件

### Skills（24）

`project-init`、`methodology-router`、`integrity-check`、`study-design`、`data-audit`、`analyze-data`、`validate-results`、`lit-review`、`evidence-synthesis`、`evaluate`、`interpret-results`、`claim-audit`、`figure-design`、`write-manuscript`、`write-supplementary`、`check-consistency`、`peer-review`、`revise`、`translate-en`、`academic-english-editing`、`submission-prep`、`journal-match`、`status`、`typeset`。

### Agents（18）

含七席獨立審查角色：`methodology-router`、`research-designer`、`data-auditor`、`statistical-validator`、`evidence-auditor`、`claim-critic`、`integrity-officer`。角色專責分工：設計者不審自己的設計、分析者不驗自己的結果、主張起草者不審自己的主張。

### 確定性腳本

機械檢核歸 scripts、領域判斷歸 agents、人工確認與方向性取捨寫入 `decisions.yaml`。主要腳本涵蓋 route（`check_route.py`）、protocol／plans（`init_protocol.py`、`init_plan.py`、`seal_artifact.py`、`check_plan.py`）、data audit（`profile_data.py`、`check_data_audit.py`）、results（`check_results_schema.py`、`rerun_all.py`）、validation（`check_validation.py`、`check_adapter_validation.py`）、evidence（`seal_evidence_protocol.py`、`check_evidence.py`）、claims（`check_claims.py`、`check_claim_audit.py`）、integrity（`check_integrity.py`）、consistency（`check_gate.py`）與 review state（`record_review_score.py`）。

## 審稿分數與潤稿掛點

`agents/editor.md` 的四段分數帶（1–3／4–5／6–7／8–10）是跨輪共同基準。每次完整 panel 裁決末尾必須有唯一 `REVIEW_SCORE` YAML block，peer-review 隨即執行：

```bash
python3 skills/revise/scripts/record_review_score.py \
  project.yaml reviews/roundN/editor-decision.md
```

minor re-check 不建立新 score；下一個完整 panel 輪才新增，寫入後再跑 `check_ledger.py` 計算邊際遞減。中文潤稿站 `chinese-deai-editing` 為選用外部 user skill，未安裝不報錯。

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

## 相容性與升級

沒有 `pipeline.version >= 0.7` 的舊專案，新增 checker 以相容模式運作：`check_gate.py` 對完全沒有 last_consistency 的專案只輸出 INFO，對已跑過 v0.6 consistency 的專案只驗既有 `result` 與 `version`。只有 `--strict` 或升版到 0.7.x 後才啟用完整 fingerprint gate。升級請先備份，再依 [`MIGRATION-v0.7.md`](MIGRATION-v0.7.md) 補 route、integrity、protocol/plans、audit、validation、evidence 與 claim-audit。

## 測試

```bash
python3 -m compileall -q agents skills tests
python3 tests/run_v07_smoke.py
python3 tests/run_v071_regressions.py
python3 tests/run_v072_regressions.py
python3 tests/run_v073_regressions.py
python3 tests/run_v080_regressions.py
```

`tests/mini-project` 保留黃金答案；smoke 測試動態建立 v0.7 專案，驗證七種 adapter 的 plan／validation 契約、clean-room 重跑、資料稽核、results schema、evidence fingerprint、claim-audit、integrity 與中英文 consistency 的 source-staleness gate。腳本需要 Python 3.10+ 與 PyYAML；排版另依 typeset 說明使用 pandoc／LaTeX。

## 版本歷程

完整逐版變更請見 [`CHANGELOG.md`](CHANGELOG.md)。
