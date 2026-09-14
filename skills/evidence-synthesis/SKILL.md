---
name: evidence-synthesis
description: >
  This skill should be used when the user asks to 「證據綜整」、「系統性整理文獻證據」、
  「風險偏誤評估」、「引用是否真的支持主張」、「evidence-synthesis」，or after lit-review
  and before interpretation/writing in an academic-pipeline project.
metadata:
  version: "0.7.2"
---

# 可重現的證據綜整

lit-review 負責搜尋、精讀與建立引用白名單；本 skill 將其提升為可稽核的 evidence pipeline：搜尋 protocol、screening、risk of bias、矛盾證據、certainty 與 citation-entailment。

## 模式

- `focused`：一般實證研究的聚焦證據背景；仍需記完整搜尋式、日期、納排與研究品質，但不冒充 systematic review。
- `systematic`／`scoping`／`meta-analysis`：依 adapter 強制 screening flow、全文排除理由、品質評估；meta-analysis 另需異質性、影響分析與 publication bias。

## 步驟

1. **建立 evidence protocol**：以 `references/evidence-protocol-template.yaml` 建 `literature/evidence-protocol.yaml`，填完整搜尋式、資料庫、日期、納排、screening、擷取與品質工具。使用者確認後執行 `python3 <skill路徑>/scripts/seal_evidence_protocol.py literature/evidence-protocol.yaml --confirmed-by user`，寫入確定性 content hash；若搜尋策略改變，新版本記 amendment，不悄改。
2. **資料蒐集**：回呼 lit-review／literature-scout 執行搜尋、撤稿檢查、筆記與 references.bib；把命中、去重、screening 與排除理由寫 `literature/screening.yaml`（focused 可簡化但仍記納排）。
3. **委派 evidence-auditor**：材料含 protocol、screening、notes、matrix、references.bib 與 adapter。逐研究評 risk of bias、辨認重複 cohort、綜整一致／矛盾證據、給 certainty，並做關鍵 statement 的 citation-entailment。
4. **建立綜整產物與來源清單**：產出：
   - `literature/evidence-synthesis.yaml`（結構化事實來源）
   - `literature/evidence-synthesis.md`（敘述綜整）
   - `reviews/evidence-audit-<序>.md`

   在 `literature/evidence-synthesis.yaml.source_artifacts` 明列 notes、matrix、擷取表等實際綜整來源；`references.bib` 與存在時的 `screening.yaml` 固定納入。綜整輸出本身不得列為 source。
5. **封存 evidence source fingerprint**：先計算：

   ```bash
   python3 <skill路徑>/scripts/check_evidence.py <專案根> \
     --source-fingerprint-only \
     --source literature/notes \
     --source literature/evidence-matrix.yaml
   ```

   將輸出的 `source_fingerprint` 與來源清單寫回 `literature/evidence-synthesis.yaml`。任何來源檔、bibliography 或 screening 後續改動，都會使 synthesis 過期。
6. **確定性檢核**：

   ```bash
   python3 <skill路徑>/scripts/check_evidence.py <專案根>
   ```

   citekey 不存在、protocol 或 evidence source fingerprint 過期、risk of bias 空白、citation verdict=fail、systematic flow 缺漏均為 blocker。
7. 更新 `state.evidence_synthesis: {result, mode, protocol_fingerprint, source_fingerprint, report, at}`；lit-review 後續增補使 protocol／synthesis 過期時，重跑增量綜整與 citation audit。

## 與 goals links 的分工（文獻型 SQ）

`goals[].links` 的 `cite:` 條目**只有一個寫入者**，本 skill 與 lit-review 依 evidence-synthesis 模式切分，兩邊不重複寫入：

- **`focused` 模式的 SQ**：links 由 **lit-review 收尾**寫入。本 skill 只交付「已審查名單」——即 `literature/evidence-synthesis.yaml` 的 `studies[]`（含 risk of bias 評等）與 certainty——**不自行改動 project.yaml 的 goals**。
- **`systematic`／`scoping`／`meta-analysis` 模式的 SQ**（文獻本身即研究主體，SQ 的答案由綜整結論給出）：links 由**本 skill 寫入**，時機在步驟 6 的確定性檢核通過之後、步驟 7 更新 state 之前。lit-review 此時只維護 matrix 候選清單，不寫 links。

寫入規格（兩邊共用，寫死）：

- 格式只認 **`cite:<citekey>`**——evaluate 的 `check_coverage.py` 僅接受 `results:` / `cite:` / `ms:` 三種前綴，其他前綴一律報 WARNING；不得自創 `evidence:` 之類的新前綴。
- citekey 必須存在於 `literature/references.bib`，且必須出現在本 skill 的 `evidence-synthesis.yaml` `studies[].citekey`（即已評 risk of bias）——evaluate `full` 檔的硬前置要的是**已審查**的 evidence links。
- 只列真正支撐該 SQ 結論的研究（對照該 SQ 的 success_criteria 與 synthesis 的 consistent／conflicting evidence），不把 included studies 整批倒進 links；`conflicting_evidence` 中的關鍵反證亦應列入，讓 evaluator 看得到矛盾。
- **經使用者確認後**才寫入 project.yaml；只增補 `cite:` links，不刪改該 SQ 既有的 `results:` / `ms:` links（`evidence: both` 的 SQ，其 `results:` 由 analyze-data／evaluate 那條線維護）。
- 綜整過期（protocol 或 source fingerprint 變動）時，已寫入的 links 隨重跑的增量綜整覆核：被排除或降級的研究要從 links 移除，並向使用者說明。

## 與 claims 的連結

interpreter 的 lit_anchors 優先取 evidence synthesis 內已審查研究；claim-critic 必須讀 conflicting evidence 與 certainty。文獻只與主題相關但不支持該句，不得列作 supports。

## 回溯相容

舊專案缺 evidence artifacts 時只提示；v0.7 寫作與 claim-audit 前必須完成或由 adapter 明確標 not-applicable（本版所有內建 adapter 均要求至少 focused synthesis）。

## 收尾

申報：「本階段更新：state.evidence_synthesis → <pass/qualified>；下一站：interpret-results／claim-audit」。

收尾必記一筆 D#：追加 `decisions.yaml` 條目，`stage: evidence-synthesis`、`checkpoint: 階段收尾`，並填 `question`（本階段對應的問題層：`main` 或子問題 id 如 `SQ2`）、`issue`（只在這筆是該問題之下的執行問題時填，一句話）、`method`（對應該層的方法：main＝研究設計、SQ＝分析方法、有 issue＝解決該執行問題的做法）、`evidence`（本階段的指令、腳本路徑、fingerprint 或輸出檔路徑清單）；照建議原樣通過也要記。這一筆是進度時間軸的資料來源，沒記就不會出現在時間軸上。
