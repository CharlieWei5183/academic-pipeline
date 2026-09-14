---
name: validate-results
description: >
  This skill should be used when the user asks to 「驗證分析結果」、「做穩健性與模型診斷」、
  「獨立重算」、「質性可信度稽核」、「證明檢查」、「結果可以相信嗎」、"validate-results"，
  or after execution/reproduction QA and before interpretation in an academic-pipeline project.
metadata:
  version: "0.7.0"
---

# 結果與推導的獨立驗證

回答「這些 findings 在合理替代方法、診斷、反例與獨立查核下是否仍成立」。results-based route 由 statistical-validator 執行；質性、systematic、mixed-methods 與理論 route 使用 adapter validation contract，不硬套統計模型。

## 共通前置

route、protocol/active plans、prestudy integrity、適用的 data/evidence audit 已通過；執行 artifact 可重建。任何驗證要求新正式分析／編碼／篩選／推導時，先建 plan amendment，不由 validator 靜默改主結果。

## A. results-based route

適用 `quantitative-inference`、`predictive-ml`、`simulation-computational`，以及 mixed-methods 的定量 strand。

1. results schema、manifest、clean rerun 與 code-review 通過。
2. 委派 statistical-validator；驗證用 scripts/artifacts 放 `analysis/validation/`，不得覆寫正式結果。
3. 必查 assumptions/convergence、influence、alternative specification、missingness、multiplicity、stability/generalization、null precision，以及承重結果的第二實作／獨立重算。
4. 先以 `check_validation.py <root> --source-fingerprint-only` 取得綁定 raw data、完整分析程式面、declared inputs、route、protocol/active plans、manifest/audit、設定、環境 lock 與 current results 的 `source_fingerprint`；寫入 `analysis/validation.yaml`，再執行：

   ```bash
   python3 <skill路徑>/scripts/check_validation.py <root> [--sq SQ1]
   ```

5. `fail` 回 amendment；`qualified` 必須明列 limitations 並傳入 claims/稿件。

## B. adapter validation route

- qualitative → `analysis/qualitative-audit-trail.yaml`
- theoretical-mathematical → `analysis/proof-audit.yaml`
- systematic-review-meta-analysis → `analysis/review-validation.yaml`
- mixed-methods → `analysis/integration/joint-display.yaml`，且定量 strand 另跑 A

先以 `references/adapter-validation-template.yaml` 建立 artifact；`source_artifacts` 列所有 findings/codes/proofs/synthesis/joint display inputs。計算 source fingerprint：

```bash
python3 <skill路徑>/scripts/check_adapter_validation.py <root> --fingerprint-only \
  [--source analysis/<artifact> ...]
```

委派 reviewer-methods `mode: adapter-validation`，以全新 context 依 adapter.validation_checks 查：

- qualitative：audit trail、reflexivity、coder disagreement、negative cases、triangulation、information power/saturation；
- systematic/meta：dual screening/audit、risk of bias、heterogeneity、influence、publication bias、certainty、search reproducibility；
- theoretical：assumption trace、逐步推導、edge cases、counterexample search、symbolic/numeric check、independent proof review；
- mixed：各 strand 品質、joint display、convergence/divergence、discordance resolution 與 meta-inference。

每項 check 必須有 evidence artifact；qualified 限制不得省略。執行：

```bash
python3 <skill路徑>/scripts/check_adapter_validation.py <root>
```

## 狀態與失效

更新 `state.analysis.validation`：results-based 同時記 `results_fingerprint` 與 `source_fingerprint`，adapter-based 記 `source_fingerprint`。raw data、declared inputs、route、protocol/active plan、manifest/audit、results、code 或環境 lock 任一改變，results-based validation 立即過期；adapter source artifact 或 contract 改變亦同。舊 validation 不能靠改 state 復活。

## 下游

只有 pass/qualified 才可 result-fit 與 interpret-results；qualified 的 limitations 強制進 claims.boundary、claim-audit 與稿件限制／摘要語意。

## 收尾

申報：「本階段更新：state.analysis.validation → <pass/qualified>（<results/source> fingerprint <...>）；下一站：evaluate（result-fit）」。

收尾必記一筆 D#：追加 `decisions.yaml` 條目，`stage: validate-results`、`checkpoint: 階段收尾`，並填 `method`（本階段採用的方法）、`problem`（本階段解決的問題）、`evidence`（本階段的指令、腳本路徑、fingerprint 或輸出檔路徑清單）；照建議原樣通過也要記。這一筆是進度時間軸的資料來源，沒記就不會出現在時間軸上。
