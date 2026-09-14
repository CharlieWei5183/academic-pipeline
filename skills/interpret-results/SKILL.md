---
name: interpret-results
description: >
  This skill should be used when the user asks to 「判讀結果」、「解讀分析結果」、「這些結果代表什麼」、
  「整理主張」、「準備討論素材」、"interpret-results"、"interpret the results"，or after
  validated evidence and a full goal-fit evaluation are ready in an academic-pipeline project.
metadata:
  version: "0.7.2"
---

# 結果判讀與主張草擬

把已驗證的研究結果與已審查文獻轉成分級、可稽核的 `analysis/claims.yaml` 草案與 `analysis/interpretation.md`。**interpreter 只起草；claim-critic 獨立攻擊；使用者在 audit 通過後才確認。**

## 前置硬關卡

1. `state.last_full_evaluation.result: pass`，或明確限定為尚未開寫的單 SQ 增量判讀。
2. route 指定的驗證產物已完成。定量／ML／模擬：`analysis/validation.yaml` pass/qualified；質性／理論／systematic route：adapter 指定的等價 validation artifact 與 audit 結果可讀。
3. `literature/evidence-synthesis.yaml` pass/qualified；若尚無直接文獻，仍須有可重現搜尋與「未找到」的審查紀錄，不能以空白代替。
4. 結果、validation 或 evidence 變更時，舊 claims 與 claim-audit 一律過期。

## 步驟

1. **補足領域脈絡**：只詢問 AI 無法從 artifacts 得知的機制、實務門檻與事前／事後性。探索紀錄已有者不重問；**事後才發現、帳上沒有的探索性分析，須補登追認條目進 `analysis/exploration-log.yaml`，note 註明事後補記**。
2. **委派 interpreter**：材料包括 goals、sealed plans、results／等價 findings、validation、data-audit、evidence synthesis、exploration log 與必要領域脈絡；不提供稿件故事。
3. **產出未確認草案**：`confirmed: false`。每條 claim 至少含：SQ、文字、strength、evidence、validation V#/等價 audit、practical、alternatives、boundary、exploratory/origin、lit_anchors、counterevidence、basis。
4. **結構檢核**：

   ```bash
   python3 <skill路徑>/scripts/check_claims.py analysis/claims.yaml project.yaml \
     analysis/results.json literature/references.bib \
     --exploration analysis/exploration-log.yaml --validation analysis/validation.yaml
   ```

5. **回呼 claim-audit**：claim-critic 逐條檢查 entailment、強度、反證、適用邊界、選擇性報告與文獻位置。reject／未解 blocker 回本 skill 修訂草案並遞增 version；內容變更後必須重跑 audit。
6. **人工確認點**：audit pass 後，將每條最終 claim、最強反方、限定語、evidence 與 **lit_anchors** 一併呈使用者。
   - **無錨主張明確問**：「文獻裡真的沒有可對話對象，還是矩陣沒涵蓋？」——屬後者則帶主張關鍵詞回 lit-review／evidence-synthesis 增補。
   - confirmed 主張 anchor 為空**列 warning 而非 blocker**（真正首創的發現本就可能沒有直接可比文獻），但須成清單列出，供討論與限制節取用。
   - **`origin: E#`（探索轉正 SQ）產出的主張無錨時從嚴**：須先增補查證一次，或由使用者明示確認無可比文獻並記入 note——探索性發現最容易撞上「早被做過」。
   - 確認後才設 `confirmed: true`，更新 `state.claims` 與 `state.claim_audit`。

## 分級上限

- randomized/credible identification：causal candidate，仍須 validation 與明確 basis；
- observational：通常 associative 上限；
- descriptive estimate：descriptive；質性主題／意義建構：interpretive，必須保留脈絡與反身性邊界；
- systematic review／meta-analysis：synthesis，強度受 risk of bias、異質性與 certainty 限制；
- theorem／proof：theoretical，只在明列假設與定義域內成立；
- mechanism hypothesis：speculative；
- predictive model：predictive，不得把預測能力寫成因果；
- qualified validation：claim 必須保留其 limitations/boundary；
- null：不顯著不等於無效應，需 precision/equivalence/non-inferiority 支持才可下相應主張。
- **調整不對稱**：分級**調降隨時可以**；**調升須有設計依據**（randomization、可信識別策略、預註冊等）並記入 `basis`，且內容變更後必須重跑 claim-audit。

## 單一事實來源與權限

claims.yaml 只由本 skill 建版；claim-critic 不直接改。確認後的 claim 不可原地強化；新增結果或 evidence 時建立新 claims version，再走 claim-audit 與人工確認。

## 收尾

申報：「本階段更新：claims v<N> → audit pass → confirmed true；下一站：figure-design／write-manuscript」。

收尾必記一筆 D#：追加 `decisions.yaml` 條目，`stage: interpret-results`、`checkpoint: 階段收尾`，並填 `question`（本階段對應的問題層：`main` 或子問題 id 如 `SQ2`）、`exec_issue`（只在這筆是該問題之下的執行問題時填，一句話）、`method`（對應該層的方法：main＝研究設計、SQ＝分析方法、有 exec_issue＝解決該執行問題的做法）、`evidence`（本階段的指令、腳本路徑、fingerprint 或輸出檔路徑清單）；照建議原樣通過也要記。這一筆是進度時間軸的資料來源，沒記就不會出現在時間軸上。
