---
name: study-design
description: >
  This skill should be used when the user asks to 「建立研究計畫」、「寫分析計畫」、「正式預註冊」、
  「版本化分析方案」、「study-design」、「analysis-plan」，or after methodology-router and
  before formal analysis in an academic-pipeline project.
metadata:
  version: "0.7.0"
---

# 研究設計與版本化分析計畫

把研究設計與原本只存在於對話中的「迷你預註冊」落成不可悄改的 artifacts：`protocol/study-protocol.yaml` 與 `analysis/plans/<SQ>-vN.yaml`。研究設計者與方法審查者分離。

## 前置

1. methodology-router 已確認，`methodology/route.yaml` 通過 `check_route.py`。
2. integrity-check（prestudy）至少已列出適用性；涉及人類、動物、敏感資料或註冊而仍 pending 時，不得把 protocol 封存為可執行。
3. 讀取 project.yaml goals、data/design、adapter 與既有 data profile（若已有）。

## 步驟

1. **初始化 protocol**（首次）：

   ```bash
   python3 <skill路徑>/scripts/init_protocol.py <專案根> --timing prospective|retrospective
   ```

2. **委派 research-designer**：完成 protocol；逐個 route 所需 SQ 建立分析計畫。一般包含 analysis／both／qualitative／proof；systematic-review-meta-analysis 的 literature 型 SQ 也必須有計畫。首次可用：

   ```bash
   python3 <skill路徑>/scripts/init_plan.py <專案根> --sq SQ1 \
     --timing retrospective-before-analysis
   ```

   已確認計畫要改時，禁止原地編輯；先建立新版本：

   ```bash
   python3 <skill路徑>/scripts/init_plan.py <專案根> --sq SQ1 \
     --timing post-hoc-amendment --supersedes SQ1-v1
   ```

3. **計畫內容最低要求**：所有 adapter 都要明列 analysis unit、納排、預宣告 outputs、validation.required 與時序；其餘依 route adapter 的 `plan_requirements`。定量推論使用 estimand／缺失值／主模型／多重比較；預測模型使用 split、tuning、metrics、calibration 與外部驗證；質性使用 sampling、reflexivity、coding/codebook、negative cases 與 information power；混合方法使用 sequence／priority／integration／discordance；systematic/meta 使用完整搜尋、篩選、risk of bias、synthesis；模擬使用 verification/validation/convergence/UQ；理論研究使用 assumptions／proof dependency／counterexample checks。承重的定量、ML、模擬 plan 缺 robustness 是 blocker。
4. **獨立設計審**：委派 reviewer-methods `mode: design-review`，材料是 plan 檔、protocol、data-audit／profile 與 adapter；不提供 research-designer 的辯解對話。blocker 必須修改草案後重審。
5. **人工確認點與封存**：使用者逐項確認 protocol 與 plan；確認後執行：

   ```bash
   python3 <skill路徑>/scripts/seal_artifact.py protocol/study-protocol.yaml \
     --kind protocol --confirmed-by user
   python3 <skill路徑>/scripts/seal_artifact.py analysis/plans/SQ1-v1.yaml \
     --kind plan --root <專案根> --confirmed-by user
   ```

   seal script 寫 content_hash 與 `analysis/plans/index.yaml`。confirmed artifact 的 hash 不符時視為原地篡改，必須新建版本。
6. **檢核**：

   ```bash
   python3 <skill路徑>/scripts/check_plan.py <專案根> --require-confirmed
   ```

7. 更新 `state.study_design`，含 protocol、active plans、result、at。下一站 data-audit；若 audit 發現會改變納排或模型的問題，回本 skill 做 amendment。

## 結果與計畫的機械連結

v0.7 results 每筆需帶 `plan_id`、`data_fingerprint`、`model_id`；鍵名必須出現在 active plan 的 outputs 或 robustness.expected_keys。補充分析不得覆寫舊鍵，須以 amendment 新增鍵。

## 回溯相容

舊專案未標 `pipeline.version: 0.7.0` 時，check_plan 只提示補建；一旦建立 v0.7 route／plans，後續分析走新關卡。

## 收尾

申報：「本階段更新：state.study_design → pass；active plans：<清單>；下一站：data-audit」。
