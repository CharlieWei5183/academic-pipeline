---
name: status
description: >
  This skill should be used when the user asks 「論文寫到哪了」、「進度如何」、「現在到哪個階段」、
  「接下來要做什麼」、「幫我從數據一路做到投稿」、"status"、"what's next"，or wants an
  overview, migration audit, or routing across academic-pipeline stages.
metadata:
  version: "0.7.1"
---

# 進度總覽與導航

`project.yaml.state` 是快取，artifacts 才是狀態真相。掃描實際檔案、重算必要 fingerprints，再指出第一個未通過或已過期的 gate。不得只看 state 字串就宣稱完成。

## 掃描範圍

除既有 results、manuscript、reviews、evaluations、decisions、exploration、manifest 外，必查：

- `methodology/route.yaml`
- `protocol/study-protocol.yaml`
- `analysis/plans/index.yaml` 與 active plans
- `integrity/register.yaml` 的 prestudy／presubmission
- `analysis/data-profile.json`、`analysis/data-audit.yaml`
- `literature/evidence-protocol.yaml`、`screening.yaml`、`evidence-synthesis.yaml`
- rerun JSON、code-review、`analysis/validation.yaml` 或 adapter validation artifact
- `analysis/claims.yaml`、`analysis/claim-audit.yaml`
- `reviews/issue-ledger.yaml`
- `state.review.scores` 與 `check_ledger.py` 的趨勢／保險閥輸出
- `state.last_consistency` 的 version、result、gate_fingerprint、report
- 中英文最新／定稿版本及 optional editing hook 狀態
- `PROGRESS.inbox.yaml`（進度頁面收件匣：`python3 <skill路徑>/scripts/check_inbox.py <root>` 列 pending；有 pending 先於其他路由處理，見下）

對 v0.7.x 專案執行適用 checker；state 與 artifact 衝突時以 checker 為準並修復快取。決策日誌 warning 不擋路，但 gate blocker 不能跳過。

重算兩份自動產生的進度檔（兩支腳本都唯讀 SSOT，只寫各自的產出）；同樣兩支亦由 plugin 的 `SessionEnd` hook（`hooks/hooks.json` → `scripts/progress_hook.py`）在 session 結束時自動重算，執行紀錄在 `<root>/.progress-hook.log`，`ACADEMIC_PIPELINE_PROGRESS_HOOK=off` 可關；hook 失敗不影響主流程，要立刻看到最新進度仍可手動跑：

```bash
python3 <skill路徑>/scripts/render_progress.py <root>             # PROGRESS.ir.json ＋ PROGRESS.html
python3 <skill路徑>/scripts/render_decisions_timeline.py <root>   # DECISIONS-TIMELINE.md
```

`render_progress.py` 是研究問題里程圖：唯讀 `project.yaml`、`decisions.yaml`、`analysis/plans/index.yaml`、`analysis/results.json`、`analysis/validation.yaml`、`analysis/claims.yaml`、`analysis/claim-audit.yaml`、`methodology/route.yaml` 等 SSOT，建出 typed JSON IR（`PROGRESS.ir.json`，`schema_version: 1`）、通過自身 schema 驗證後再確定性渲染成單一自含 HTML（`PROGRESS.html`，無外部資源、`file://` 直接開）；泳道＝專案層（17 站）與每個 SQ／AQ（6 站：study-design → analyze-data → validate-results → evaluate → interpret-results → claim-audit），每站一個節點，state 為 done／expired／blocked／pending／unknown，缺檔缺欄位一律 pending、檔存在但無法解析一律 unknown 並 WARNING，不過濾任何泳道或站；決策註記依 `question`／`links` 掛到泳道，預設收合。IR 另有 `graph` 鍵、HTML 另有「關聯」分頁（URL hash `#relations`）：欄序照「主問題 → 問題（SQ／AQ）→ 方法 → 驗證 → 結果 → 圖表 → 決策」，主問題 `q:main` 獨占最左一欄並在 SQ／AQ 之間垂直居中——節點 `q:`問題／`p:`方法（＝計畫版本，label 帶 model_id，superseded 版本收合、現行版帶「v4（3 舊版）」徽章；plan 的 `robustness[]` 每項是這個分析底下的**敏感性子分析**，建為縮排子節點 `p:<pid>#<Rid>`，先收成一個**敏感性分析群** `p:<pid>#S`（label「<pid> 敏感性分析」、徽章「n 項」，子分析的 parent 是群），隨 plan 收合）／`v:`驗證／`r:`結果（依宣告分主次：在 plan `outputs[]` → 徽章「主要」、只在 `robustness[].expected_keys` → 「次要」並縮排成產生它的那個子分析的子項（跟父收合）、results.json 掛在該 plan 但都沒宣告 → 「未宣告」；驗證與否是獨立標記——沒有任何驗證邊的結果右端多一個琥珀色「未驗證」）／`d:`決策，邊 decomposes／plans／supersedes／sensitivity／supplements／validated_by／primary／robustness／produces／cites／refers 全部只從 SSOT 建，每條帶 `default_visible` 與 `style`（solid／dashed／thin）——預設畫主幹（問題→現行方法→驗證→結果，穩健性 result_keys 為細線）、父→子 L 形線與**每個有產出的分析到它的結果**（主分析→outputs 鍵、子分析→expected_keys，一律實線；未宣告鍵虛線）；plan 宣告但 results.json 沒登錄的鍵建 pending 節點、goals 指向不存在的鍵建 unknown 節點並計入 `stats.dangling_result_keys`、未驗證的登錄鍵計入 `stats.unvalidated_result_keys`、次要／未宣告／敏感性子分析數各有計數。圖分三個區帶（每個節點帶 `band`，由上而下）：**Main** 是主結果鏈（主問題、SQ 及其計畫／驗證／主要與未宣告結果／主圖、決策），**Extended Data** 只放 manifest `role` 為 extended（extended_data／extended-data／ed）的圖表，**Supplementary** 是補充（敏感性分析群與子分析、次要結果、AQ 及其計畫／驗證／結果、role supplementary／supp／si 的圖表）；圖表缺 role 或不認得時沿用推導（呈現的結果全在 supp 才 supp），`meta.role_source` 記 manifest／derived，徽章「主圖」（表為「主表」）／「延伸」／「補充」。每組敏感性分析以一條短垂線（`supplements`「敏感性對照」：群上緣 → 所屬 plan 下緣、方法色箭頭，同欄多條時往左錯開）連回它所屬的 plan；plan → 群、子分析 → 主要結果、以及其他跨區帶的邊（主問題 → AQ 的 decomposes、結果 → 圖表的 depicts 除外）預設不畫，點選節點或「顯示全部邊」才顯示；沒有可見節點的區帶不畫分隔線與標題、不佔高度。版面不交叉：已由「plan → 驗證 → 結果」覆蓋的 plan → 結果產出線預設不畫（`meta.via_validation`）；跳欄的線在每個中間欄留一個 dummy 列穿過（邊的 `via`／`via_order`）；每欄順序以區塊為單位 barycenter 重排（問題欄維持 goals 順序）並保留實際交叉最少的版面；走道車道依「必須在左」關係做拓樸序與區間著色；`graph.stats.crossings`（精確線段相交計數）與 `edge_node_overlaps`（線段穿過可見節點）預設檢視應為 0，> 0 時印 WARNING 列出前 10 對。問題 id 別名：主問題降為附錄問題（SQ1 → AQ2）後，index 舊版條目、決策 `links`、validation item 的 `sq` 仍寫舊 id，renderer 沿 `replaced_by`／`supersedes` 鏈解出 `{舊 id → 現行 id}`（IR `graph.question_aliases`），里程泳道與關聯圖都把它們併進現行問題（舊版 plan 進現行版的舊版鏈、決策 refers 指現行問題、現行問題節點列「舊 id」），只有解析不到的 sq 才造「goals 無此問題」占位節點。節點底色與符號顯示 state，線走「同來源併幹線＋分支、走道分車道」（同一來源往同一欄的邊合成一條幹線，每個欄間走道以區間圖貪婪著色分車道，重疊的幹線不共線；滑過任一分支整束高亮），工具列有 state 篩選、「顯示舊版計畫」「顯示全部邊」「顯示決策」（都預設關），SVG 內嵌並可縮放平移，點節點顯示其全部邊並亮上下游、`/` 搜尋、Shift+點找最短路徑、`P` 逐 SQ 導覽。第五欄 `f:`圖表來自 `analysis/figures/manifest.json`（`r:` → `f:` 為「呈現於」depicts 邊；results_keys 指到不在圖裡的鍵不建邊、徽章「無對應結果鍵」並 WARNING；state 依 `status` 與檔案存在與否），結果節點面板可直接看完成的表（rows 最多 200 列）與掛在此鍵的圖（點圖放大），圖表節點面板顯示圖、圖說與結果鍵。旗標：`--dry-run` 不寫檔並印 HTML、`--json` 印 IR、`--ir-only` 只寫 IR、`--embed-figures` 把圖檔（svg／png，單檔 ≤ 5 MB）以 data URI 內嵌進 IR 與 HTML（預設不內嵌，HTML 以相對路徑顯示圖）。只有根目錄不存在或 IR 未通過驗證才 exit 2（後者不落檔）。

### 進度頁面伺服器與收件匣

要在 `PROGRESS.html` 上直接送「新問題／新分析／意見」，用本機伺服器開頁面（`file://` 開的頁面表單一律 disabled）：

```bash
python3 <skill路徑>/scripts/progress_server.py <root> --port 8765   # 只綁 127.0.0.1；--port 0 自動選埠
```

伺服器啟動時先重算一次進度產物，之後只做三件事：`GET /` 先重跑 `render_progress.py` 再回 `PROGRESS.html`；提供 root 底下白名單副檔名的靜態檔（給圖用；路徑含 `..` 或跑出 root 一律 403）；`POST /api/inbox` 把表單 append 到 `<root>/PROGRESS.inbox.yaml`（IN-### 連號、`status: pending`、鎖檔後寫暫存檔再替換）。它**只綁 loopback、只寫收件匣**，不碰任何 SSOT；下次 session 由本 skill 依上面的路由逐筆處理。

結構化動作（0.16.0）：頁面上把 Main 帶的問題拖到 Supplementary 帶（或面板按「降為附錄問題」）會送一筆 `kind: reassign`（payload `{from, to, primary_model}`）、把圖表拖到別的帶（或面板改 role）會送一筆 `kind: set_role`（payload `{figures: {id: role}}`），title／body 由伺服器生成。這兩種項目的整條 SSOT 變更鏈由確定性腳本完成：

```bash
python3 <skill路徑>/scripts/reassign_question.py <root> --from SQ2 [--to AQ4] [--primary-model M] --inbox IN-xxx --dry-run   # 預覽（不寫任何檔、印 token）
python3 <skill路徑>/scripts/reassign_question.py <root> --from SQ2 [--to AQ4] [--primary-model M] --inbox IN-xxx [--daily-log daily_log/daily_log_YYYY-MM-DD.md] --apply
python3 <skill路徑>/scripts/set_figure_role.py <root> --figure fig_x=supplementary [--figure fig_y=main] --inbox IN-xxx (--dry-run | --apply)
```

四種搬移（0.16.1）同樣走腳本：拖到 Main 帶（或面板按「升回主問題」）→ `kind: promote`（payload `{from, to}`）；方法節點拖到沒有 active plan 的問題上 → `kind: move_plan`（`{plan, to_question}`；目標已有 active plan 會被擋，那是合併不是搬移）；敏感性子分析拖到別的方法上 → `kind: move_sensitivity`（`{plan, item, to_plan}`）；問題拖到同帶另一個問題上（排在它之後）→ `kind: reorder`（`{list, order}`）。拖曳中頁面只畫預覽線與打亮，不寫任何東西；放開後開表單、只填理由、送收件匣。

```bash
python3 <skill路徑>/scripts/promote_question.py <root> --from AQ4 [--to SQ2] --inbox IN-xxx (--dry-run | --apply)                  # --to 省略＝回原號（空著時）或最大 SQ 號 +1
python3 <skill路徑>/scripts/move_plan.py <root> --plan AQ2-v2 --to-question AQ5 --inbox IN-xxx (--dry-run | --apply)              # 目標須沒有 active plan；來源須為附錄問題
python3 <skill路徑>/scripts/move_sensitivity.py <root> --plan SQ5-v6 --item R2 --to-plan AQ3-v1 --inbox IN-xxx (--dry-run | --apply)
python3 <skill路徑>/scripts/reorder_questions.py <root> --list appendix_questions --order AQ1,AQ3,AQ2,AQ4 --inbox IN-xxx (--dry-run | --apply)
python3 <skill路徑>/scripts/move_result.py <root> --key <結果鍵> --to-plan AQ3-v1 [--to-item R2] --inbox IN-xxx (--dry-run | --apply)   # 0.16.2：省略 --to-item＝搬到 outputs（主要結果）；給 R<n>＝搬到該子分析的 expected_keys（次要結果）
```

結果鍵搬家（0.16.2）也走腳本：結果節點拖到別的方法上 → `kind: move_result`（payload `{key, to_plan}`，A 型）；拖到任一敏感性子分析上 → 同 kind 加 `to_item`（B 型）。來源由 results.json 該鍵的 plan_id 判，須為 active plan；目標已含該鍵會被擋。來源與目標各出一版（同一份 plan 只出一版），數字不動；validation 中只以該鍵為 primary_results 的 item 改掛目標、同時含別的鍵的 item 會移除該鍵那一行（該鍵在目標問題下的驗證列為 open item）。

要讓頁面上的「待套用動作」面板能預覽與套用，啟動伺服器時加 `--allow-apply`（另可加 `--daily-log <path>` 透傳給腳本）：`python3 <skill路徑>/scripts/progress_server.py <root> --port 8765 --allow-apply`。開了之後 `POST /api/actions/dry-run {id}` 代跑 `--dry-run` 回摘要與 token，`POST /api/actions/apply {id, token}` 在 token 與現行 SSOT 相符時才代跑 `--apply`（不符 409，要重新預覽），每次 apply 追記 `<root>/PROGRESS.actions.log`；不加旗標時兩個端點一律 403，伺服器維持「只寫收件匣」。

放開節點後的流程（0.16.3）：表單按「送出並預覽」→ `POST /api/inbox` 建一筆 → 同一個對話框立刻 `POST /api/actions/dry-run` 顯示摘要 → 三個鈕：「套用」（`/api/actions/apply`；409 自動重跑預覽）、「先留在收件匣」（留 pending，之後在「待套用動作」面板處理）、「撤回」（`POST /api/inbox/dismiss {id, note?}`，伺服器代跑 `check_inbox.py --dismiss <id> --note <note>`，note 預設「使用者在放開預覽後撤回」；這個端點只動收件匣、**不需 `--allow-apply`**）。server 未開 `--allow-apply` 時對話框仍會送收件匣，摘要區顯示 403 原因、「套用」停用，另外兩個鈕照常。收件匣裡 `status: dismissed` 的項目本 skill 不再處理。

`render_decisions_timeline.py` 是決策時間軸：只讀 `project.yaml`、`decisions.yaml`、`analysis/results.json`，只寫 `<root>/DECISIONS-TIMELINE.md`（一張記錄表＋一張 mermaid gantt 里程碑圖，按 `question` 分 section、一筆一個 milestone，無日期的列不入圖而列於圖下）；加 `--dry-run` 不寫檔、加 `--json` 印機器可讀結果。缺欄位、缺 `decisions.yaml` 都不是錯誤（顯示 `unknown`、exit 0）；只有根目錄不存在或 `decisions.yaml` 無法解析才 exit 2。

## v0.7.1 主流程

```text
project-init
→ methodology-router
→ integrity-check(prestudy)
→ study-design（protocol＋versioned plans＋design-review＋seal）
→ data-audit
→ [analyze-data ∥ lit-review]
   analyze-data: execute → schema/manifest → clean rerun → code-review
                 → validate-results → result-fit＋人工確認
   lit-review → evidence-synthesis
→ evaluate(full)
→ interpret-results → claim-audit → 人工確認 claims
→ figure-design → write-manuscript → write-supplementary → check-consistency(zh)
→ peer-review ⇄ revise
   每個完整 panel 輪：editor score → record_review_score.py → check_ledger 保險閥
   minor：editor 單人 re-check，不增加 round、不新增 score
   accept／minor 覆核通過：converged
→ 中文潤稿（chinese-academic-editing，內建·選用）
→ ★中文人工定稿
→ translate-en
→ 英文潤稿（academic-english-editing，內建·選用）
→ ★英文人工確認
→ check-consistency(en，全量)
→ submission-prep（題目／摘要改動則新版本＋重跑全量 consistency）
→ integrity-check(presubmission)
→ 最終 gate → typeset
```

route adapter 可把定量 analyze-data 換成質性 audit trail、proof audit、systematic-review synthesis 或 mixed-method integration；required gates 仍由 route 機械檢查。

## 路由判斷

依第一個未通過／過期項導向：

- **收件匣有 pending（`check_inbox.py <root>` 列出）→ 先於其他路由，逐筆呈使用者裁決**：`new_question` → goals 變更確認（結構性增修觸發 evaluate 的拆解審）並記 D#；`new_analysis` → study-design（新 plan 或 amendment）並記 D#；`comment` → 依內容記一筆 D#（`question`＝target 所屬問題，`exec_issue`／`method` 視內容填）或轉對應 skill。使用者裁定後跑 `python3 <skill路徑>/scripts/check_inbox.py <root> --resolve IN-xxx --by <D#／plan id／SQ id>`；不採納 → `--dismiss IN-xxx --note <理由>`。**收件匣不是事實來源，不得未經使用者確認直接改 goals／plans／decisions**；`check_inbox.py` 是唯一可以改收件匣 status 的程式。
  - **pending 為 `reassign`（主問題降為附錄問題）、`promote`（升回主問題）、`set_role`（圖表 role）、`move_plan`（搬方法）、`move_sensitivity`（搬敏感性子分析）、`reorder`（調順序）或 `move_result`（搬結果）時走腳本，不走人工**：`check_inbox.py` 已在該筆下面印出可直接執行的命令。**不得人工重做各步**（不得自己搬 goals、建 plan、retag results、改 validation、重登 waiver、寫 D#），**不得整本讀 decisions.yaml** 去仿寫先例；只跑對應腳本 `reassign_question.py`／`promote_question.py`／`set_figure_role.py`／`move_plan.py`／`move_sensitivity.py`／`reorder_questions.py`／`move_result.py` 的 `--dry-run`→ 把 ≤ 30 行的摘要（要改哪些檔、搬哪段、新舊 fingerprint、預定 D#）呈給使用者 → 使用者同意後改 `--apply`（可加 `--daily-log`）。腳本會自己備份、失敗還原、結案收件匣、重畫進度圖並 append 一筆模板 D#；主 loop 驗收只看磁碟成品（`reviews/reassign-*.json`／`set-figure-role-*.json` 的步驟紀錄、新 D#、各 checker）。前置條件被擋（exit 2）或鏈失敗（exit 1，已還原）時把原因照實回報，不要繞過腳本手做。搬走最後一個主問題須明確加 `--allow-empty-main`，且要先告知使用者 `check_coverage` 會因此擋關。
- 無 route／未確認 → methodology-router；
- prestudy 未過 → integrity-check；
- protocol/plans 缺或 hash 不符 → study-design；
- data profile/audit 缺或 raw fingerprint 改變 → data-audit；
- results／findings 變動、rerun 過期 → analyze-data → clean rerun → code-review → validate-results；
- 腳本 crash／clean-room rerun 非預期失敗／`source_fingerprint` 查不出漂移來源／跨階段筆數不守恆，且根因未知 → `debug-pipeline`（流程線外；根因定位後把失效 gate 交回本 skill 分診）；
- validation fail／過期 → validate-results 或 plan amendment；
- evidence synthesis 缺／過期 → evidence-synthesis；
- claims 未 audit／fingerprint 不符 → claim-audit；
- claims 未由使用者確認 → interpret-results 人工確認點；
- 中文稿 consistency 未過 → check-consistency(zh)；
- 尚未 peer-review 或 decision=major → peer-review／revise；
- decision=minor → revise 快速通道；
- `state.review.scores` 缺本輪而存在 editor decision → `record_review_score.py` 回填後再跑 check_ledger；
- 保險閥觸發 → 人工裁決並記 D#，不得自動續輪；
- decision=reject → journal-match；
- `state.review.converged=true` 且中文未定稿 → `chinese-academic-editing`（內建·選用）或直接中文人工定稿；
- 中文已定稿但英文未確認 → translate-en；翻譯後可選 `academic-english-editing`；
- 英文已確認但 full consistency 未過 → check-consistency(en)，**不是 submission-prep**；
- submission 修改稿件使 fingerprint 改變 → 新版本＋check-consistency(en)；
- presubmission integrity 未過 → integrity-check；
- prep 與最終 gate 通過 → typeset。

## 回溯相容

未有 `pipeline.version` 或版本低於 0.7 的專案先只讀盤點，不自動升版。`check_gate.py` 的預設相容模式按 v0.6 契約處理：

- 完全沒有 `last_consistency`：INFO，不因新 checker 阻擋；
- 已有 `{result, version}`：只驗這兩個舊欄位；
- 不要求 v0.7 才新增的 `gate_fingerprint`、`report`、`language` 或 `en_final.confirmed_at`；
- 只有明確 `--strict` 或 `pipeline.version >= 0.7` 才啟用完整 gate。

遷移時先備份，再補 route、protocol/plans、audits、validation、evidence、claim-audit 與 consistency fingerprint；升版後不得再以舊專案跳過硬關卡。

## review scores 與保險閥

狀態報告必列：

- round、decision、converged；
- `state.review.scores` 筆數與最新七維／total／must_fix_open／model；
- 相鄰可比輪的 total 差；
- 跨模型或 `panel_changed` 跳過原因；
- max_rounds 與邊際遞減是否觸發。

`check_ledger.py` 仍在讀 scores；若沒有任何寫入者，視為 pipeline contract broken，不得把「無資料」誤報成「未觸發」。

## 選用潤稿站

`academic-english-editing`（0.8.0 起隨附）與 `chinese-academic-editing`（0.10.0 起隨附）皆為本 plugin 內建 skill。兩者都是選用潤稿站，只能改語言呈現，不得改數字、markers、citekeys、claim strength、validation boundary 或方法語意；潤稿後須重跑對應語言的完整 consistency，且都不能取代該語言的人工確認點。外部 user skill `chinese-deai-editing` 不再是 pipeline 的中文潤稿站（語域基準是「像人整理過」，與稿件層不符），仍可獨立用於非稿件的中文材料。

## 人工確認點

SQ/goals、route、protocol/plans、data-audit 處置、分析結果、claims、persona、保險閥裁決、中文定稿、英文確認、integrity evidence 與 typeset 產物均不得自動跨越。

本 skill 原則上只讀；若只依 artifacts 修復快取，逐欄申報。否則固定申報：「無狀態變更」。
