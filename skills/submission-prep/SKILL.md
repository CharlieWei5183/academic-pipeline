---
name: submission-prep
description: >
  This skill should be used when the user asks to 「準備投稿」、「投稿包」、「cover letter」、
  「重現性打包」、"submission-prep"、"prepare for submission"，after the confirmed English
  manuscript has passed the full English consistency gate.
metadata:
  version: "0.7.2"
---

# 投稿準備

組裝投稿包。此站不能用翻譯檢查或舊 consistency 狀態代替英文定稿的全量一致性，也不能替作者虛構倫理、作者資格、相似度或授權證明。

## 入口硬關卡

1. `state.en_final.version` 指向實際英文稿。
2. 執行：

   ```bash
   python3 <plugin>/skills/check-consistency/scripts/check_gate.py <root> \
     --manuscript manuscript/en/<version>.md --require-language en
   ```

   fingerprint 不符即回 check-consistency(en)。
3. 目標期刊規範已由 journal-match 或最新官方指南確認。**動手前一律上網查證該期刊最新 author guidelines**（字數、圖表格式、聲明與 checklist 要求），不得只靠記憶或舊紀錄；查到的要點向使用者確認。轉投時所有期刊特定產物重做。

## 步驟

1. **題目與摘要打磨**：題目給 2–3 個候選——準確、含檢索關鍵詞、不誇大；候選只能在 confirmed claims 與 validation boundary 內。摘要逐句檢視動機—方法—結果—意義是否齊備。任何題目、摘要或正文改動都寫入新的英文稿版本，更新 `state.en_final.version`，再跑**完整** check-consistency(en)；只跑 numbers/citations 不足。
2. **投稿文件**：cover letter、highlights、keywords、author declarations、CRediT、COI、data/code availability、AI disclosure 與 reporting guideline 文件。草稿需使用者／作者群確認。
   - cover letter：貢獻一段、為何適合該刊一段、原創性與無一稿多投聲明；**轉投必須重寫，不得沿用前刊版本**。
   - highlights（期刊要求時）3–5 條，每條依期刊字元限制；keywords 依期刊數量要求，兼顧檢索性與領域慣例。
   - 參考文獻依 `target.citation_style` 由 Zotero 匯出（`zotero_export_bibliography` 指定 style）；**Zotero 未連接時**以 references.bib 手動格式化，並在 checklist 註明需人工複核。
3. **重現性包**：

   ```bash
   python3 <skill路徑>/scripts/build_repro_package.py <root> [--out submission/repro]
   ```

   README 讀 run-order、plans、manifest、環境 lock 與 script↔result/figure 對照。clean rerun report、validation artifacts 與版本 fingerprint 納入清單。防呆逐項確認：
   - README 內的**【請人工補】區塊**（資料取得方式、執行環境細節）逐項向使用者確認補齊，不得留空出包。
   - **依賴掃描**：Python import 掃描產 requirements.txt（已安裝套件附版本）或 R 套件清單；掃不到即列待辦。
   - **隨機種子檢查**：scripts 中未見顯式種子＝warning，向使用者確認是否影響重現。
   - **`data/` 不自動隨包**——是否附原始資料由使用者依期刊政策、隱私與授權決定；`derived/` 比照辦理。
3b. **投稿檔案分頁與打包（0.23.0）**：上一條的重現性包給的是「怎麼重跑」，這一條給的是「要上傳哪些檔」。`PROGRESS.html` 的第四個分頁「投稿檔案」（`#submission`）把投稿要上傳的檔案整份列出來，看過沒問題就在頁面上按鈕打包。

   - **清單是衍生的，不是手寫的**：入口＝`analysis/figures/manifest.json` 裡 role 屬 main／extended／supplementary 的圖表 ＋ `analysis/results.json` 的現行結果鍵，從入口往回追 `script` 欄、run 的 `scripts/`／`report.md`／`status.json`／`input_snapshot/`，以及快照 hash 表逐 cell 指到的來源檔。規則只有一份：`scripts/submission_package_common.py` 的 `derive()`。
   - **`submission/package.yaml` 只記手動差量**：`include`（手動加入）與 `exclude`（移除），不存整份清單，每次都重算再套。移除是可逆的——被移除的項目在分頁上仍列出、標「已移除」，還原就回到衍生規則算出來的樣子。這個檔**不在 `rerun_all` 的 fingerprint 雜湊範圍**，改它不會讓 validation 或 results 過期。
   - **兩支 CLI**（分頁上的按鈕就是代跑這兩支，旁邊都寫著等效命令）：

     ```bash
     # 看清單（不寫任何檔）；確認後改 --apply 才真的複製
     python3 <skill路徑>/scripts/build_submission_package.py <root> --dry-run
     python3 <skill路徑>/scripts/build_submission_package.py <root> --apply [--no-zip]

     # 清單增刪：一次一個動作，--exclude 可重複；一次 apply 記一筆 D#
     python3 <skill路徑>/scripts/package_edit.py <root> --exclude <路徑> --reason <理由> --dry-run
     python3 <skill路徑>/scripts/package_edit.py <root> --include <路徑> --tier <帶> --kind <分類> --dry-run
     python3 <skill路徑>/scripts/package_edit.py <root> --restore <路徑或入口 id> --dry-run
     ```

   - **打包產出**：`submission/package_<日期>/`，含逐檔 sha256 的 `MANIFEST.tsv`、README、`results_subset.json` 與依賴清單，預設壓成 zip（`--no-zip` 可關）。**有納入中的缺檔一律拒絕打包**（exit 1）：先移除那些節點，或補上替代檔。未見顯式隨機種子的腳本照舊只記 warning。
   - **與步驟 3 的 `build_repro_package.py` 差在哪**：那支是**重現性包**，目的是讓人重跑你的分析，所以 `data/` 與 `derived/` **不自動隨包**——附不附原始資料由使用者依期刊政策、隱私與授權逐次決定。這一支是**投稿上傳包**，目的是把期刊要的檔案一次交齊，所以**預設帶資料**：清單是從結果往回追出來的，資料檔本來就在裡面。兩者的判斷位置不同——那邊是「打包時才問」，這邊是「使用者已經在網頁上逐項看過了」，不想附的在分頁上移除掉就好，移除還是可逆的。所以這一支不重複問一次，也不把 `data/` 特別挑出來。兩支並存、各自產出，互不取代。

4. **presubmission integrity gate**：題目摘要與作者／聲明定稿後回呼 integrity-check `presubmission`。必須有真實 evidence；外部相似度項只能 external/manual verified。執行：

   ```bash
   python3 <plugin>/skills/integrity-check/scripts/check_integrity.py <root> --stage presubmission
   ```

5. **投稿 checklist**：字數、圖表（**規格對照 figure-design 寫入 manifest 的 `spec` 欄位**逐項查核；未跑過 figure-design 時先跑一次做期刊規格終檢）、SI、引用、reporting guideline、匿名／行號、聲明、權限、repro package、完整英文 consistency 與 integrity 均標通過。
6. **最終凍結檢查**：若步驟 2–5 又修改稿件、SI、figure manifest、references、claims 或 statements，先重新跑 full consistency；作者／COI／權限等變更則重跑 integrity。兩者皆未過期才組裝 `submission/`。
7. 更新 `state.submission.prep`，含 journal、manuscript、consistency fingerprint、integrity report、checklist 與 at；下一站 typeset。

## 收尾

申報：「本階段更新：state.submission.prep → pass（en/<v>，consistency <fp>，integrity pass）；下一站：typeset」。

收尾必記一筆 D#：追加 `decisions.yaml` 條目，`stage: submission-prep`、`checkpoint: 階段收尾`，並填 `question`（本階段對應的問題層：`main` 或子問題 id 如 `SQ2`）、`exec_issue`（只在這筆是該問題之下的執行問題時填，一句話）、`method`（對應該層的方法：main＝研究設計、SQ＝分析方法、有 exec_issue＝解決該執行問題的做法）、`evidence`（本階段的指令、腳本路徑、fingerprint 或輸出檔路徑清單）；照建議原樣通過也要記。這一筆是進度時間軸的資料來源，沒記就不會出現在時間軸上。
