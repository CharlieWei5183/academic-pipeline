---
name: figure-design
description: >
  This skill should be used when the user asks to 「設計圖表」、「排 figure story」、「圖說」、
  「出版級圖表」、「出版級表格」、「圖美化」、"figure-design"、"polish the figures"、
  "graphical abstract"，between interpret-results and write-manuscript—or as a final
  spec check before submission—in an academic-pipeline project.
metadata:
  version: "0.3.0"
---

# 圖表敘事與出版級圖表

兩件事：動筆前先排「圖表敘事」（figure story——主圖與主表的序列講完整個論證），並把圖與表都做到出版級品質。圖表是多數讀者唯一細看的部分，不該只是分析的副產品。表格是一等公民：table story 併入 figure story，一起排序、一起驗收。

## 前置

讀取 `analysis/figures/manifest.json`、`analysis/results.json`（含 `table_*` 鍵）、`analysis/claims.yaml`（若有——主張是圖表敘事的骨架）、`project.yaml` 的 `target`。期刊圖規不明時網路搜尋該刊 author guidelines（欄寬 mm、最低 dpi、格式、字型、表格規範），向使用者確認查到的要點。

## 步驟

1. **排圖表敘事**：提案 `analysis/figures/figure-story.md`——表格：序（Fig 1…／Table 1…）↔ 一句 message ↔ 對應 claims（以 C# id 標註）／SQ ↔ 處置（沿用／重製／併版／新製／補充）。原則：主圖 4–8 張、主表 1–3 張、每張只講一個 message、圖表序即論證序；放不進敘事的處置標「補充」——不是丟棄，是 write-supplementary 的固定素材（將重編為 S1、S2…）。

   送使用者確認前先跑主張覆蓋檢查（便宜的腳本保險，取代人眼）：

   ```bash
   python3 <skill路徑>/scripts/check_claim_coverage.py analysis/claims.yaml analysis/figures/figure-story.md
   ```

   每條登記主張至少出現在一張主圖／主表：causal／associative 缺席＝blocker，descriptive／speculative＝warning。通過後**經使用者確認才動工**。write-manuscript 的結果與討論大綱將對齊此敘事序。

2. **委派 figure-designer agent 執行**：交付 figure-story、manifest、期刊圖規與 `analysis.rounding`。要求（詳見 agent 定義）：一切修改經可重跑 script；multi-panel 程式組版（面板標 a、b、c）；出版縮放後字級與線寬達標；色盲友善配色；全篇風格統一（集中樣式檔）；**表格由 script 從 results.json 的 `table_*` 鍵直接渲染**（三線表；渲染即溯源，數字不得手打），輸出檔與渲染 script 登記進 manifest（`type: "table"`）；graphical abstract（期刊要求時）。

3. **Caption 撰寫**：每張圖與每張表的 caption 寫入 manifest.json 的 `caption` 欄位——自足（不讀內文能懂）、逐面板說明、n 與誤差棒含義標明。寫作階段直接取用；check-consistency 據此核對圖文一致。

4. **驗收（人工確認點）**：逐圖逐表對照 checklist（訊息單一、自足、解析度、字級、色盲檢視、表格三線式與有效位數）呈使用者確認。確認後更新 manifest（含 `spec`：寬 mm、dpi、格式）——submission-prep 的圖表項以此為準。收尾申報一行：「本階段更新：figures/manifest.json <N> 筆（caption／spec）；state 無變更則申報「無狀態變更」；下一站：<skill 名>」。
5. 收尾必記一筆 D#：追加 `decisions.yaml` 條目，`stage: figure-design`、`checkpoint: 階段收尾`，並填 `question`（本階段對應的問題層：`main` 或子問題 id 如 `SQ2`）、`issue`（只在這筆是該問題之下的執行問題時填，一句話）、`method`（對應該層的方法：main＝研究設計、SQ＝分析方法、有 issue＝解決該執行問題的做法）、`evidence`（本階段的指令、腳本路徑、fingerprint 或輸出檔路徑清單）；照建議原樣通過也要記。這一筆是進度時間軸的資料來源，沒記就不會出現在時間軸上。

## 規則

- 圖表中數據只能來自 results.json 既有鍵；manifest 的 `results_keys` 必須同步維護——圖表不得引入未登記的數字。
- 禁止手工修圖（點陣編輯）與手打表格數字；任何視覺調整都改 script 重跑，script 存 `analysis/scripts/`。
- script 渲染的表格進稿件時以整表標註 `<!-- table:鍵名 -->` 引用，由 check_numbers.py 整表比對（見 check-consistency）；不得在稿件內手改渲染結果——要改，回來重渲染。
- 投稿前可再跑一次本 skill 做期刊規格終檢（轉投換刊時圖規常變）。
