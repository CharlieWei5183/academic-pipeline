---
name: claim-audit
description: >
  This skill should be used when the user asks to 「審查主張」、「反方檢驗結論」、
  「主張是否過度」、「claim-audit」，or automatically after interpret-results drafts
  claims.yaml and before the user confirms claims in an academic-pipeline project.
metadata:
  version: "0.7.0"
---

# 主張獨立反方審查

把「提出主張」與「攻擊主張」拆成兩個角色。interpreter 只起草；claim-critic 逐條找證據跳躍、反證、邊界與選擇性報告。audit 通過前，`claims.confirmed` 不得設為 true。

## 前置

1. `analysis/claims.yaml` 存在且 `confirmed: false`。
2. 對應 results 已通過 validate-results；qualified 結果的限制已提供給 interpreter。
3. evidence-synthesis 已完成或 adapter 明確標不適用；references.bib 與 lit_anchors 可查。
4. 先跑原有 `check_claims.py`，結構 blocker 清零。

## 步驟

1. **計算不可猜測的 fingerprints**：`claims_fingerprint` 只涵蓋 claims 語意（故 audit 後把 `confirmed` 設為 true 不會自我失效）；`source_fingerprint` 另綁定 results／validation、evidence synthesis／bibliography、route、protocol／active plans、goals 與 exploration record。

   ```bash
   python3 <skill路徑>/scripts/check_claim_audit.py <專案根> --fingerprint-only
   python3 <skill路徑>/scripts/check_claim_audit.py <專案根> --source-fingerprint-only
   ```

2. **委派 claim-critic**：材料只含 claims、goals、sealed plans、validation、results 摘錄、evidence synthesis/matrix、exploration-log。不得提供 interpreter 的辯解過程。
3. **逐條裁決**：
   - `pass`：證據直接支持且強度／邊界恰當。
   - `qualify`：需降級、加限定、補反證或改實務意義；修正後標 resolved。
   - `reject`：證據不推出該主張，或核心反證未處理；整體 audit fail。
4. **迭代**：需要修改時回 interpret-results 產生新 claims version或更新草案；任何 claim 內容或承重上游來源變更都使舊 fingerprint 過期，必須重跑 audit。claim-critic 不直接改 claims。
5. 產出 `analysis/claim-audit.yaml` 與 `reviews/claim-audit-v<claims version>.md`，再跑：

   ```bash
   python3 <skill路徑>/scripts/check_claim_audit.py <專案根>
   ```

6. **人工確認點**：只有 audit pass 後，才把逐條主張、critic 最強反方與最後限定語一併呈使用者確認；確認後設 `analysis/claims.yaml confirmed: true`，更新 `state.claims` 與 `state.claim_audit`。

## 下游硬關卡

write-manuscript 必須確認：claims/source fingerprints 與最近 audit 一致、audit pass、claims confirmed。修改 claims、validation、results、evidence、active plan 或 route 後，稿件關卡自動失效。

## 收尾

申報：「本階段更新：state.claim_audit → pass（claims fingerprint <...>）；經使用者確認後 state.claims.confirmed → true；下一站：figure-design 或 write-manuscript」。
