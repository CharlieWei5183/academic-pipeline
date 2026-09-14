---
name: write-supplementary
description: >
  This skill should be used when the user asks to 「組補充材料」、「整理 SI」、「補充資料放哪」、
  「supplementary information」、"write-supplementary"、"assemble the SI"，or after
  write-manuscript and before check-consistency in an academic-pipeline project.
  上游強制生產的 SI 素材（sens_* 鍵、figure-story 淘汰圖表、方法附錄）由本 skill 收尾出口。
metadata:
  version: "0.2.0"
---

# 撰寫補充材料（SI）

管線上游強制生產 SI 素材——analyze-data 的敏感度分析（`sens_*` 鍵）、figure-design 處置為「補充」的圖表、report.md 放不進正文的方法細節——本 skill 是它們的固定出口：組裝成與正文同規格、同溯源規則的 SI 稿。

## 前置

1. 定位專案根目錄；`state.zh_latest` 必須非空（正文先於 SI）——否則停止並回呼 write-manuscript。
2. 讀取：`analysis/results.json`、`analysis/figures/manifest.json` 與 `analysis/figures/figure-story.md`（處置為「補充」的項目）、`analysis/report.md`、`analysis/claims.yaml`、正文最新版。

## 步驟

1. **素材盤點**：列三類來源清單，向使用者確認取捨——
   - `sens_*` 鍵與其他未被正文引用的 results 鍵（與正文 `<!-- results.* -->`／`<!-- table:* -->` 標註集合比對得出）；
   - figure-story 處置為「補充」的圖表（依出場序重編為 S1、S2…）；
   - 方法附錄素材（report.md 中超出正文篇幅的細節：完整前提檢查、參數表、收斂性驗證）。

   不是所有素材都必須進 SI，但**承重 SQ 的敏感度分析必收**——正文結論所繫，reviewer 必查；analyze-data 強制生產它們，本 skill 是其固定出口。

2. **組裝成稿** `manuscript/zh/si-v1.md`（既有版本取號遞增，不覆蓋）：章節慣例——補充方法、補充表（含敏感度分析彙總表）、補充圖；圖說直接取 manifest.json 的 `caption` 欄位，不另行重寫。每個 SI 項目在正文須有至少一處引用（如「見補充圖 S1」）；缺引用的項目列清單請使用者決定——正文補引用，或該項目不進 SI。

3. **收尾**：更新 `project.yaml` 的 `state.si_latest`；建議下一步 check-consistency（正文與 SI 同批檢核）。收尾申報一行：「本階段更新：state.si_latest <舊值>→<新值>；下一站：check-consistency」。此後 SI 隨行整條管線：peer-review 送審含 SI、translate-en 同流程翻譯、submission-prep 的 checklist 含 SI 項。
4. 收尾必記一筆 D#：追加 `decisions.yaml` 條目，`stage: write-supplementary`、`checkpoint: 階段收尾`，並填 `question`（本階段對應的問題層：`main` 或子問題 id 如 `SQ2`）、`issue`（只在這筆是該問題之下的執行問題時填，一句話）、`method`（對應該層的方法：main＝研究設計、SQ＝分析方法、有 issue＝解決該執行問題的做法）、`evidence`（本階段的指令、腳本路徑、fingerprint 或輸出檔路徑清單）；照建議原樣通過也要記。這一筆是進度時間軸的資料來源，沒記就不會出現在時間軸上。

## 硬性規則

- **溯源規則與正文同一套**：資料數字只能出自 results.json，句尾 `<!-- results.鍵 -->` 註解，精度依 `analysis.rounding`；script 渲染的表格用整表標註 `<!-- table:鍵名 -->`；豁免定義同 check_numbers.py。check-consistency 對 SI 跑同一批腳本，blocker 同樣擋路。
- **主張規則與正文同一套**：詮釋性語句句尾標 `<!-- claims.C# -->`，措辭不得超出該主張分級；SI 不得引入未登記的新科學主張——要新主張，回 interpret-results 登記。
- 引用一律 `[@citekey]`，citekey 必須存在於 references.bib。
- SI 圖表沿用 figure-design 的規格與 manifest 登記——不得出現 manifest 之外的圖表。
