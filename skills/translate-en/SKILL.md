---
name: translate-en
description: >
  This skill should be used when the user asks to 「翻成英文」、「中翻英」、「英文版」、
  "translate-en"、"translate the manuscript to English"，after the Traditional Chinese
  manuscript is finalized in an academic-pipeline project.
metadata:
  version: "0.7.2"
---

# 中翻英

把使用者確認的中文定稿譯為學術英文。中文仍是 source of meaning；英文確認只是人工確認點，**其後必須跑完整 check-consistency(en)**，不能直接進 submission-prep。

## 前置

1. `state.zh_final` 指向使用者親自確認的中文版本；該版本已有 pass 的完整 consistency gate。
2. 讀 glossary、target、claims、claim-audit、validation limitations 與 evidence synthesis。翻譯不得改變 claim strength 或移除邊界。
3. 中文源或上游 artifacts 若在翻譯期間變動，停止並先重建中文一致性狀態。

## 模式

- **全文**：無英文版或中文源大改。
- **增量**：已有 `state.en_final.source`，用 `diff_versions.py --sections` 比對舊中文源與新定稿取得變更節清單，**只重譯有變更的節／段**，其餘照舊；最後仍對整篇英文稿做檢核。**每輪修訂都整篇重翻會使成本失控，禁止**。

## 步驟

1. 翻譯前掃描全文，把 glossary 未收錄的術語（中文、建議英譯、依據）**一次**確認完並補入 `project.yaml` 的 glossary；翻譯途中不再逐詞打斷。途中遇漏網新術語以 `[TERM?]` 標記暫定譯法，完稿後彙整一次確認並補登 glossary——交稿前 `[TERM?]` 必須清空。
2. 委派 translator；保留所有 `<!-- results.* -->`、`<!-- table:* -->`、`<!-- claims.* -->`、`[@citekey]`、圖表／SI 交叉引用與限定語。輸出新版本 `manuscript/en/vN.md`，SI 同步新版本。
3. marker 保全：

   ```bash
   python3 <skill路徑>/scripts/check_markers.py <zh.md> <en.md>
   ```

   兩版的 results／table／claims 註解與 citekey 多重集合必須一致；有差異先修正再繼續。**有 SI 時對 SI 中英兩版再跑一次 check_markers。**

4. fact-checker 做跨語意回查（**每節抽 2–3 句回譯成中文與原文比對語意**；標記保全已由腳本把關，不必人工重查）；reviewer-language 查英文正確性與術語一致。
5. 套用語言修正；任何涉及 claim 強度、數字解讀、方法或限制的修改回原 source artifact，不由 translator 自行裁定。
6. **英文潤稿站（本 plugin 內建，選用）**：呼叫內建 skill `academic-english-editing`（0.8.0 起隨附；可略過但不可取代人工確認）。可先做句構重寫、精煉、學術慣例校準，並清除 AI 生成痕跡（AI tells）與對齊語域。只可動語言呈現，不得改數字、`<!-- -->` markers、`[@citekey]`、claim strength、validation boundary、方法或限制語意；發現 over-claim 只標記回 claim-audit，不在本站改寫。潤稿產生新英文版本後，重跑 `check_markers.py`、跨語意回查與 reviewer-language；之後仍須人工英文確認及 full `check-consistency(en)`。
7. **人工英文確認**：使用者確認後更新：

   ```yaml
   state:
     en_final: {version: "v2", source: "zh/v4", confirmed_at: "..."}
   ```

8. **強制下一站**：立即回呼完整 `check-consistency`，對 `manuscript/en/v2.md` 與英文 SI 執行所有上游 gate、數字、引用、claims、validation、evidence、圖文、摘要與方法語意檢核。只有 `state.last_consistency = {version: en/v2, result: pass, gate_fingerprint: ...}` 才可 submission-prep。

## 收尾

申報：「本階段更新：state.en_final → {version, source}；下一站：check-consistency（英文全量，強制）」。

收尾必記一筆 D#：追加 `decisions.yaml` 條目，`stage: translate-en`、`checkpoint: 階段收尾`，並填 `question`（本階段對應的問題層：`main` 或子問題 id 如 `SQ2`）、`exec_issue`（只在這筆是該問題之下的執行問題時填，一句話）、`method`（對應該層的方法：main＝研究設計、SQ＝分析方法、有 exec_issue＝解決該執行問題的做法）、`evidence`（本階段的指令、腳本路徑、fingerprint 或輸出檔路徑清單）；照建議原樣通過也要記。這一筆是進度時間軸的資料來源，沒記就不會出現在時間軸上。
