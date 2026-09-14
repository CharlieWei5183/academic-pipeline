---
name: status
description: >
  This skill should be used when the user asks 「論文寫到哪了」、「進度如何」、「現在到哪個階段」、
  「接下來要做什麼」、「幫我從數據一路做到投稿」、"status"、"what's next"，or wants an
  overview, migration audit, or routing across academic-pipeline stages.
metadata:
  version: "0.7.1"
---

# 進度總覽與導航

`project.yaml.state` 是快取，artifacts 才是狀態真相。掃描實際檔案、重算必要 fingerprints，再指出第一個未通過或已過期的 gate。不得只看 state 字串就宣稱完成。

## 掃描範圍

除既有 results、manuscript、reviews、evaluations、decisions、exploration、manifest 外，必查：

- `methodology/route.yaml`
- `protocol/study-protocol.yaml`
- `analysis/plans/index.yaml` 與 active plans
- `integrity/register.yaml` 的 prestudy／presubmission
- `analysis/data-profile.json`、`analysis/data-audit.yaml`
- `literature/evidence-protocol.yaml`、`screening.yaml`、`evidence-synthesis.yaml`
- rerun JSON、code-review、`analysis/validation.yaml` 或 adapter validation artifact
- `analysis/claims.yaml`、`analysis/claim-audit.yaml`
- `reviews/issue-ledger.yaml`
- `state.review.scores` 與 `check_ledger.py` 的趨勢／保險閥輸出
- `state.last_consistency` 的 version、result、gate_fingerprint、report
- 中英文最新／定稿版本及 optional editing hook 狀態

對 v0.7.x 專案執行適用 checker；state 與 artifact 衝突時以 checker 為準並修復快取。決策日誌 warning 不擋路，但 gate blocker 不能跳過。

重算兩份自動產生的進度檔（兩支腳本都唯讀 SSOT，只寫各自的產出）：

```bash
python3 <skill路徑>/scripts/render_progress.py <root>             # PROGRESS.ir.json ＋ PROGRESS.html
python3 <skill路徑>/scripts/render_decisions_timeline.py <root>   # DECISIONS-TIMELINE.md
```

`render_progress.py` 是研究問題里程圖：唯讀 `project.yaml`、`decisions.yaml`、`analysis/plans/index.yaml`、`analysis/results.json`、`analysis/validation.yaml`、`analysis/claims.yaml`、`analysis/claim-audit.yaml`、`methodology/route.yaml` 等 SSOT，建出 typed JSON IR（`PROGRESS.ir.json`，`schema_version: 1`）、通過自身 schema 驗證後再確定性渲染成單一自含 HTML（`PROGRESS.html`，無外部資源、`file://` 直接開）；泳道＝專案層（17 站）與每個 SQ／AQ（6 站：study-design → analyze-data → validate-results → evaluate → interpret-results → claim-audit），每站一個節點，state 為 done／expired／blocked／pending／unknown，缺檔缺欄位一律 pending、檔存在但無法解析一律 unknown 並 WARNING，不過濾任何泳道或站；決策註記依 `question`／`links` 掛到泳道，預設收合。IR 另有 `graph` 鍵、HTML 另有「關聯」分頁（URL hash `#relations`）：欄序照「問題 → 方法 → 驗證 → 主要結果 → 決策」——節點 `q:`問題／`p:`方法（＝計畫版本，label 帶 model_id，superseded 版本收合、現行版帶「v4（3 舊版）」徽章）／`v:`驗證／`r:`結果（徽章「主要」／「其他」）／`d:`決策，邊 decomposes／plans／supersedes／validated_by／primary／produces／cites／refers 全部只從 SSOT 建，每條帶 `default_visible` 與 `style`——預設只畫主幹（問題→現行方法→驗證→主要結果）與「未驗證旁路」（現行方法直接到不在任何 primary_results 的鍵，虛線）；plan 宣告但 results.json 沒登錄的鍵建 pending 節點、goals 指向不存在的鍵建 unknown 節點並計入 `stats.dangling_result_keys`、未驗證的登錄鍵計入 `stats.unvalidated_result_keys`。節點底色與符號顯示 state，工具列有 state 篩選、「顯示舊版計畫」「顯示全部邊」「顯示決策」（都預設關），SVG 內嵌並可縮放平移，點節點顯示其全部邊並亮上下游、`/` 搜尋、Shift+點找最短路徑、`P` 逐 SQ 導覽。旗標：`--dry-run` 不寫檔並印 HTML、`--json` 印 IR、`--ir-only` 只寫 IR。只有根目錄不存在或 IR 未通過驗證才 exit 2（後者不落檔）。

`render_decisions_timeline.py` 是決策時間軸：只讀 `project.yaml`、`decisions.yaml`、`analysis/results.json`，只寫 `<root>/DECISIONS-TIMELINE.md`（一張記錄表＋一張 mermaid gantt 里程碑圖，按 `question` 分 section、一筆一個 milestone，無日期的列不入圖而列於圖下）；加 `--dry-run` 不寫檔、加 `--json` 印機器可讀結果。缺欄位、缺 `decisions.yaml` 都不是錯誤（顯示 `unknown`、exit 0）；只有根目錄不存在或 `decisions.yaml` 無法解析才 exit 2。

## v0.7.1 主流程

```text
project-init
→ methodology-router
→ integrity-check(prestudy)
→ study-design（protocol＋versioned plans＋design-review＋seal）
→ data-audit
→ [analyze-data ∥ lit-review]
   analyze-data: execute → schema/manifest → clean rerun → code-review
                 → validate-results → result-fit＋人工確認
   lit-review → evidence-synthesis
→ evaluate(full)
→ interpret-results → claim-audit → 人工確認 claims
→ figure-design → write-manuscript → write-supplementary → check-consistency(zh)
→ peer-review ⇄ revise
   每個完整 panel 輪：editor score → record_review_score.py → check_ledger 保險閥
   minor：editor 單人 re-check，不增加 round、不新增 score
   accept／minor 覆核通過：converged
→ 中文潤稿（chinese-academic-editing，內建·選用）
→ ★中文人工定稿
→ translate-en
→ 英文潤稿（academic-english-editing，內建·選用）
→ ★英文人工確認
→ check-consistency(en，全量)
→ submission-prep（題目／摘要改動則新版本＋重跑全量 consistency）
→ integrity-check(presubmission)
→ 最終 gate → typeset
```

route adapter 可把定量 analyze-data 換成質性 audit trail、proof audit、systematic-review synthesis 或 mixed-method integration；required gates 仍由 route 機械檢查。

## 路由判斷

依第一個未通過／過期項導向：

- 無 route／未確認 → methodology-router；
- prestudy 未過 → integrity-check；
- protocol/plans 缺或 hash 不符 → study-design；
- data profile/audit 缺或 raw fingerprint 改變 → data-audit；
- results／findings 變動、rerun 過期 → analyze-data → clean rerun → code-review → validate-results；
- 腳本 crash／clean-room rerun 非預期失敗／`source_fingerprint` 查不出漂移來源／跨階段筆數不守恆，且根因未知 → `debug-pipeline`（流程線外；根因定位後把失效 gate 交回本 skill 分診）；
- validation fail／過期 → validate-results 或 plan amendment；
- evidence synthesis 缺／過期 → evidence-synthesis；
- claims 未 audit／fingerprint 不符 → claim-audit；
- claims 未由使用者確認 → interpret-results 人工確認點；
- 中文稿 consistency 未過 → check-consistency(zh)；
- 尚未 peer-review 或 decision=major → peer-review／revise；
- decision=minor → revise 快速通道；
- `state.review.scores` 缺本輪而存在 editor decision → `record_review_score.py` 回填後再跑 check_ledger；
- 保險閥觸發 → 人工裁決並記 D#，不得自動續輪；
- decision=reject → journal-match；
- `state.review.converged=true` 且中文未定稿 → `chinese-academic-editing`（內建·選用）或直接中文人工定稿；
- 中文已定稿但英文未確認 → translate-en；翻譯後可選 `academic-english-editing`；
- 英文已確認但 full consistency 未過 → check-consistency(en)，**不是 submission-prep**；
- submission 修改稿件使 fingerprint 改變 → 新版本＋check-consistency(en)；
- presubmission integrity 未過 → integrity-check；
- prep 與最終 gate 通過 → typeset。

## 回溯相容

未有 `pipeline.version` 或版本低於 0.7 的專案先只讀盤點，不自動升版。`check_gate.py` 的預設相容模式按 v0.6 契約處理：

- 完全沒有 `last_consistency`：INFO，不因新 checker 阻擋；
- 已有 `{result, version}`：只驗這兩個舊欄位；
- 不要求 v0.7 才新增的 `gate_fingerprint`、`report`、`language` 或 `en_final.confirmed_at`；
- 只有明確 `--strict` 或 `pipeline.version >= 0.7` 才啟用完整 gate。

遷移時先備份，再補 route、protocol/plans、audits、validation、evidence、claim-audit 與 consistency fingerprint；升版後不得再以舊專案跳過硬關卡。

## review scores 與保險閥

狀態報告必列：

- round、decision、converged；
- `state.review.scores` 筆數與最新七維／total／must_fix_open／model；
- 相鄰可比輪的 total 差；
- 跨模型或 `panel_changed` 跳過原因；
- max_rounds 與邊際遞減是否觸發。

`check_ledger.py` 仍在讀 scores；若沒有任何寫入者，視為 pipeline contract broken，不得把「無資料」誤報成「未觸發」。

## 選用潤稿站

`academic-english-editing`（0.8.0 起隨附）與 `chinese-academic-editing`（0.10.0 起隨附）皆為本 plugin 內建 skill。兩者都是選用潤稿站，只能改語言呈現，不得改數字、markers、citekeys、claim strength、validation boundary 或方法語意；潤稿後須重跑對應語言的完整 consistency，且都不能取代該語言的人工確認點。外部 user skill `chinese-deai-editing` 不再是 pipeline 的中文潤稿站（語域基準是「像人整理過」，與稿件層不符），仍可獨立用於非稿件的中文材料。

## 人工確認點

SQ/goals、route、protocol/plans、data-audit 處置、分析結果、claims、persona、保險閥裁決、中文定稿、英文確認、integrity evidence 與 typeset 產物均不得自動跨越。

本 skill 原則上只讀；若只依 artifacts 修復快取，逐欄申報。否則固定申報：「無狀態變更」。
