---
name: journal-match
description: >
  This skill should be used when the user asks 「投哪本期刊」、「選期刊」、「期刊比對」、
  「被拒了要轉投」、「換一家投」、"journal-match"、"which journal should I submit to"、
  "resubmit elsewhere"，for journal selection, cascade planning, or reformatting
  after rejection in an academic-pipeline project.
metadata:
  version: "0.2.0"
---

# 選刊與轉投

兩個模式：投稿前的選刊比對與 cascade 計畫；被拒後的轉投改裝。期刊資訊一律以當下網路查證為準（aims & scope、字數、格式都會變），不憑記憶回答，並註明查證日期。

## 模式一：選刊（建議時點：整體評估通過後——知道發現強度再選；或定稿後）

1. 讀取 `project.yaml`（research_question、field、target 現值）、`analysis/claims.yaml`（若有——主張分級與規模是層級定位的依據）。
2. 網路搜尋候選期刊 3–6 本：aims & scope 原文、文章類型、字數限制、審稿週期（查得到時）、OA 與 APC；順帶排查掠奪性期刊疑慮並標記。
3. 產出比對表：每本一列——契合度評述（對照 research_question 與主張）、規格、層級定位（頂刊衝刺／領域旗艦／紮實專業刊）。依發現強度給推薦與理由：claims 以 causal／associative 且效應扎實者可上攻；descriptive 或探索性為主者建議務實定位。
4. 使用者選定後寫入 `target`（journal、article_type、word_limit、abstract_limit、citation_style、structure），並提案 `target.cascade`（後備 2–3 本，reject 後依序取用），經使用者確認。
5. **格式欄與 CSL（typeset 排版站的輸入）**：同步寫入 `target.submission_format`（format: docx／latex、line_numbers、anonymous、figures: embedded／separate——依該刊 author guidelines 查證）；自 Zotero style repository 取得該刊官方 CSL 存 `submission/csl/<journal>.csl` 並寫入 `target.csl`。CSL 缺檔時提示取得方式（zotero.org/styles 搜尋期刊名），不自行猜測樣式。

## 模式二：轉投（editor 裁決或真實期刊 reject 後，由 revise 路由或使用者直接呼叫）

1. 從 `target.cascade` 取下一本（無 cascade → 先跑模式一）；網路查證該刊最新 author guidelines。
2. 經使用者確認後更新 `target` 各欄位；原期刊移入 cascade 尾端並註明已拒。
3. **改裝計畫**（先呈使用者確認）：字數縮放（超限時列可刪節候選）、章節結構改裝（依新刊 structure）、citation_style 轉換（重匯格式化書目）、圖規差異（→ 回呼 figure-design 調整）、被拒意見中低成本可修的點順手併入（上一輪意見不浪費）。
4. 執行改裝：稿件存新版本（遵守 write-manuscript 全部硬性規則），**強制重跑 check-consistency**——結構大動時數字與引用最容易掉。
5. 更新格式欄與 CSL（同模式一步驟 5——新刊的 submission_format 與 csl）。
6. 回呼 submission-prep：cover letter 全部重寫（不同期刊不同賣點），checklist 依新刊重核；檢核通過後**回到 typeset 重排**（轉投改裝的最後一哩：新刊格式的 docx／LaTeX、行號、匿名版）。

## 規則

- `target` 與 `cascade` 的任何修改經使用者確認。
- 本 skill 不改研究內容與主張；改裝只動格式、結構與敘事裁剪。
- 層級建議只是建議；引用期刊聲望指標時須註明年份與來源。
- 收尾申報一行：「本階段更新：target →{journal, submission_format, csl}（轉投時另列 cascade）；下一站：<skill 名>」。
