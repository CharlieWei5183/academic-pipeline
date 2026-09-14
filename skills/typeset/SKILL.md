---
name: typeset
description: >
  This skill should be used when the user asks to 「排版」、「排版輸出」、「轉成投稿格式」、
  「產生投稿用 docx」、「LaTeX 投稿版」、「行號版」、「雙匿名版」、「圖表分離」、"typeset"、
  "build the submission files"，after submission-prep passes (or when reformatting
  after journal-match cascade) in an academic-pipeline project.
metadata:
  version: "0.1.0"
---

# 排版輸出站（typeset）

投稿格式的機械產出：全管線稿件是 .md，期刊收 docx 或 LaTeX，常要行號、雙匿名版與圖表分離。轉檔、行號、去識別化是機械活，歸腳本。**判斷不進本站**：內容早在上游定稿，本站不動文字、數字與引用內容，只動呈現。journal-match 被拒轉投的改裝也回到本站重排。

## 輸入與設定

- **稿源**：`state.en_final` 指向的英文定稿（或使用者指定的中文定稿）。
- **引用**：`literature/references.bib` 加目標期刊官方 CSL——讀 `target.csl`（journal-match 選定期刊時自 Zotero style repository 取得，存 `submission/csl/<journal>.csl`）；缺檔時提示取得方式（zotero.org/styles），不自行猜測樣式。
- **格式需求**：讀 `target.submission_format`（format: docx／latex、line_numbers、anonymous、figures: embedded／separate）；缺項由本 skill 執行中逐項問（舊專案無此欄照此辦理）。
- 需要 pandoc（docx／LaTeX 轉檔）；LaTeX 路徑需 PDF 時另需 latexmk。工具缺失時腳本會明確報錯並提示安裝。

## 步驟

1. **前置**：`state.last_consistency` 對稿源版本為 pass 且 submission-prep 檢核通過，或使用者明示跳過並記 note。讀 target 格式需求，缺項逐項問。
2. **建置**（依格式跑對應腳本；產物存 `submission/build/<日期>/`）：

   ```bash
   python3 <skill路徑>/scripts/build_docx.py <稿件.md> --bib literature/references.bib --csl <target.csl> --reference-doc <skill路徑>/references/reference.docx --out submission/build/<日期>/
   python3 <skill路徑>/scripts/build_latex.py <稿件.md> --bib literature/references.bib --csl <target.csl> [--line-numbers] [--pdf] --out submission/build/<日期>/
   python3 <skill路徑>/scripts/anonymize.py <稿件.md> --out submission/build/<日期>/anonymous.md [--authors "姓名1,姓名2"]
   python3 <skill路徑>/scripts/check_build.py submission/build/<日期>/ --manifest analysis/figures/manifest.json --project project.yaml --source <稿件.md>
   ```

   - 行號版：LaTeX 路徑用 lineno 為準；docx 路徑由 reference-doc 的節屬性帶入（相容性不保證，check_build 不支援時列 checklist 手動項）。
   - 雙匿名版：anonymize.py 移除作者、機構、致謝、funding 區塊；掃描全文列出疑似自我引用與自我指涉句清單（"our previous work" 之類），**交使用者裁定，不代改**——機械改寫自引有語意風險。匿名版再經 build_docx／build_latex 轉檔。
   - 圖表分離（target 要求時）：正文圖位改 placeholder（Figure N about here），圖檔依 manifest 集中至 build 目錄 figures/。
3. **收尾（人工確認點）**：產物清單、check_build 結果（citeproc 未解引用＝blocker；字數對照 target.word_limit 列示）、自引清單呈使用者；確認後寫入 `state.submission.build: {at, format, files}`。收尾申報一行：「本階段更新：state.submission.build →{at, format}；下一站：投稿（使用者）」。
4. 收尾必記一筆 D#：追加 `decisions.yaml` 條目，`stage: typeset`、`checkpoint: 階段收尾`，並填 `question`（本階段對應的問題層：`main` 或子問題 id 如 `SQ2`）、`exec_issue`（只在這筆是該問題之下的執行問題時填，一句話）、`method`（對應該層的方法：main＝研究設計、SQ＝分析方法、有 exec_issue＝解決該執行問題的做法）、`evidence`（本階段的指令、腳本路徑、fingerprint 或輸出檔路徑清單）；照建議原樣通過也要記。這一筆是進度時間軸的資料來源，沒記就不會出現在時間軸上。

## 規則

- **build 產物唯讀、單向**：pandoc 轉檔會丟 `<!-- -->` 標記與部分格式，build 產物不具工作稿資格——任何修改回 .md 重建，防雙頭編輯。
- 本站不動文字、數字、引用內容與主張措辭；發現內容問題一律回上游（revise／check-consistency）。
- 未跑本站時，submission-prep 與其他 skill 行為不變；CSL 缺檔提示取得方式，不擋其餘產出（引用改留 [@citekey] 原樣並列 checklist 手動項）。
