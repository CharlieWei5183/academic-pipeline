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

`render_progress.py` 是研究問題里程圖：唯讀 `project.yaml`、`decisions.yaml`、`analysis/plans/index.yaml`、`analysis/results.json`、`analysis/validation.yaml`、`analysis/claims.yaml`、`analysis/claim-audit.yaml`、`methodology/route.yaml` 等 SSOT，建出 typed JSON IR（`PROGRESS.ir.json`，`schema_version: 1`）、通過自身 schema 驗證後再確定性渲染成單一自含 HTML（`PROGRESS.html`，無外部資源、`file://` 直接開）；泳道＝專案層（17 站）與每個 SQ／AQ（6 站：study-design → analyze-data → validate-results → evaluate → interpret-results → claim-audit），每站一個節點，state 為 done／expired／blocked／pending／unknown，缺檔缺欄位一律 pending、檔存在但無法解析一律 unknown 並 WARNING，不過濾任何泳道或站；決策註記依 `question`／`links` 掛到泳道，預設收合。IR 另有 `graph` 鍵、HTML 另有「關聯」分頁（URL hash `#relations`）：欄序照「主問題 → 問題（SQ／AQ）→ 方法 → 驗證 → 結果 → 圖表 → 決策」，主問題 `q:main` 獨占最左一欄並在 SQ／AQ 之間垂直居中——節點 `q:`問題／`p:`方法（＝計畫版本，label 帶 model_id，superseded 版本收合、現行版帶「v4（3 舊版）」徽章；plan 的 `robustness[]` 每項是這個分析底下的**敏感性子分析**，建為縮排子節點 `p:<pid>#<Rid>`，先收成一個**敏感性分析群** `p:<pid>#S`（label「<pid> 敏感性分析」、徽章「n 項」，子分析的 parent 是群；0.18.0 起群縮排在所屬 plan 之下一層、子分析再縮一層，區帶跟 plan，plan 徽章「敏感性 n」、點選 plan 可暫時收合群與子分析），隨 plan 收合）／`v:`驗證／`r:`結果（依宣告分主次：在 plan `outputs[]` → 徽章「主要」、只在 `robustness[].expected_keys` → 「次要」並縮排成產生它的那個子分析的子項（跟父收合）、results.json 掛在該 plan 但都沒宣告 → 「未宣告」；驗證與否是獨立標記——沒有任何驗證邊的結果右端多一個琥珀色「未驗證」）／`d:`決策，邊 decomposes／plans／supersedes／sensitivity／validated_by／primary／robustness／produces／cites／refers／supports 全部只從 SSOT 建（`supplements` 型別 0.18.0 起只保留在 `edge_types`，不再出邊），每條帶 `default_visible` 與 `style`（solid／dashed／thin）——預設畫主幹（問題→現行方法→驗證→結果，穩健性 result_keys 為細線）、父→子 L 形線與**每個有產出的分析到它的結果**（主分析→outputs 鍵、子分析→expected_keys，一律實線；未宣告鍵虛線）；plan 宣告但 results.json 沒登錄的鍵建 pending 節點、goals 指向不存在的鍵建 unknown 節點並計入 `stats.dangling_result_keys`、未驗證的登錄鍵計入 `stats.unvalidated_result_keys`、次要／未宣告／敏感性子分析數各有計數。圖分三個區帶（每個節點帶 `band`，由上而下）：**Main** 是主結果鏈（主問題、SQ 及其計畫／驗證／主要與未宣告結果／主圖、決策），**Extended Data** 放 manifest `role` 為 extended（extended_data／extended-data／ed）的圖表，0.20.0 起也放 `analysis/extended-data.yaml` 列出的方法（plan／敏感性子分析）、主要或未宣告結果、驗證與跟著它們走的節點（群與子分析跟 plan、次要結果跟子分析、支撐結果跟主結果、主要結果跟 owner plan、驗證跟 plan_id 的 plan、缺 role 的圖表跟呈現的結果；每個非問題節點 `meta.band_source`＝`explicit`／`inherited:<來源>`／`derived`；只有問題節點不能放——使用者 2026-09-17 裁定；缺檔＝畫法與 0.19.0 相同；這個檔不在 rerun_all 的 fingerprint 雜湊範圍），**Supplementary** 是補充（AQ 及其一切——計畫、敏感性分析群與子分析、驗證、結果——與 role supplementary／supp／si 的圖表；0.18.0 起 SQ 的群、子分析與次要結果跟 plan 留在 Main，這是使用者 2026-09-16 的裁定，取代 2026-09-15 的「群放 Supplementary」畫法）；圖表缺 role 或不認得時沿用推導（呈現的結果全在 supp 才 supp），`meta.role_source` 記 manifest／derived，徽章「主圖」（表為「主表」）／「延伸」／「補充」。plan → 群、群 → 子分析都是方法色的 L 形父子線（0.18.0 起不再有 `supplements`「敏感性對照」短垂線，IR 也不出這種邊）；子分析 → 主要結果、以及其他跨區帶的邊（主問題 → AQ 的 decomposes、結果 → 圖表的 depicts 除外）預設不畫，點選節點或「顯示全部邊」才顯示；沒有可見節點的區帶不畫分隔線與標題、不佔高度。版面不交叉：已由「plan → 驗證 → 結果」覆蓋的 plan → 結果產出線預設不畫（`meta.via_validation`）；跳欄的線在每個中間欄留一個 dummy 列穿過（邊的 `via`／`via_order`）；每欄順序以區塊為單位 barycenter 重排（問題欄維持 goals 順序；0.18.1 起只在同一條問題帶內重排）並保留實際交叉最少的版面；走道車道依「必須在左」關係做拓樸序與區間著色；每個區帶內依問題分成橫向的**問題帶**（0.18.1）：同一個問題延伸出來的方法／驗證／結果／圖表在各欄從帶的第一列起對齊、問題節點在帶首列、帶高＝帶內最高那欄的列數、帶與帶之間留 `STRIP_GAP`（1 列）並以淡色細線分隔（區帶標題列與第一條帶之間不另加），帶序＝goals 順序（問題節點在別的區帶、但有節點落在這一帶的問題也各成一帶，找不到問題的孤兒節點放該區帶最後一條空字串帶），決策註記掛在 refers 的問題（或 plan 所屬問題）那條帶、只掛 q:main／無 refers 的排最後；IR 每個非決策節點帶 `strip`（問題節點是自己）、`graph.strips`＝[{band, question, y0, y1}]、`stats.strips`；JS `relayout()` 同為 band → strip → col 三層，暫存後 `reorderStaged()` 依新歸屬重算 strip；`graph.stats.crossings`（精確線段相交計數）與 `edge_node_overlaps`（線段穿過可見節點）預設檢視應為 0，> 0 時印 WARNING 列出前 10 對。問題 id 別名：主問題降為附錄問題（SQ1 → AQ2）後，index 舊版條目、決策 `links`、validation item 的 `sq` 仍寫舊 id，renderer 沿 `replaced_by`／`supersedes` 鏈解出 `{舊 id → 現行 id}`（IR `graph.question_aliases`），里程泳道與關聯圖都把它們併進現行問題（舊版 plan 進現行版的舊版鏈、決策 refers 指現行問題、現行問題節點列「舊 id」），只有解析不到的 sq 才造「goals 無此問題」占位節點。節點底色與符號顯示 state，線走「同來源併幹線＋分支、走道分車道」（同一來源往同一欄的邊合成一條幹線，每個欄間走道以區間圖貪婪著色分車道，重疊的幹線不共線；滑過任一分支整束高亮），工具列有 state 篩選、「顯示舊版計畫」「顯示全部邊」「顯示決策」（都預設關），SVG 內嵌並可縮放平移，點節點顯示其全部邊並亮上下游、`/` 搜尋、Shift+點找最短路徑、`P` 逐 SQ 導覽。第五欄 `f:`圖表來自 `analysis/figures/manifest.json`（`r:` → `f:` 為「呈現於」depicts 邊；results_keys 指到不在圖裡的鍵不建邊、徽章「無對應結果鍵」並 WARNING；state 依 `status` 與檔案存在與否），結果節點面板可直接看完成的表（rows 最多 200 列）與掛在此鍵的圖（點圖放大），圖表節點面板顯示圖、圖說與結果鍵。旗標：`--dry-run` 不寫檔並印 HTML、`--json` 印 IR、`--ir-only` 只寫 IR、`--embed-figures` 把圖檔（svg／png，單檔 ≤ 5 MB）以 data URI 內嵌進 IR 與 HTML（預設不內嵌，HTML 以相對路徑顯示圖）。只有根目錄不存在或 IR 未通過驗證才 exit 2（後者不落檔）。

結果欄的粒度（0.19.0，使用者 2026-09-17 裁定的**宣告粒度**，跨專案一致、不設門檻、不做專案設定）：節點粒度＝plan 的宣告粒度——`outputs` 逐條宣告的主要結果一條一個節點；敏感性子分析 `p:<pid>#R<k>` 的 `expected_keys` 是該子分析的屬性、不是獨立宣告單位，所以有自有次要鍵的子分析底下一個次要結果節點 `r:<pid>#R<k>#secondary`（subtype `secondary_group`、縮排在子分析之下、跟父收合），1 鍵直接顯示鍵名、多鍵「次要結果 n 鍵」；沒有自有鍵的子分析（expected_keys 為空、或只引用本 plan outputs／別 plan 的鍵）沒有次要結果這個宣告單位，不建節點也不建邊；徽章「未登錄 a／未驗證 b」，鍵全列在面板（> 200 筆分頁＋搜尋，每鍵旁「升為主要結果」＝暫存一筆 `move_result` 回本 plan outputs）；圖表 → 聚合節點一條 depicts 標「n 鍵」、validation 列到次要鍵的邊指聚合節點並記鍵數；整個聚合節點可拖（裡面全部鍵一起搬：拖到 plan 上＝各一筆 A 型 `move_result`、拖到別的子分析上＝各一筆 B 型、所屬 plan 在 Main 時拖到 Main 帶＝各一筆升回本 plan）；未宣告鍵維持逐鍵虛線。`stats.secondary_result_keys` 仍是鍵數、`secondary_groups` 是節點數。圖表欄最後一列另有 **report.md 節點** `o:report`（type `report`）：讀 `analysis/report.md` 的 `![…](path)` 引用對 manifest 比對，label「report.md（引用 k／manifest m 張）」，有檔 done、無檔 pending；圖表 → report 一條 `embedded_in`（點選才顯）；role=main 且 report.md 存在但沒引用的圖表徽章「報告未引用」。

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
python3 <skill路徑>/scripts/move_result.py <root> --key <結果鍵> --to-plan SQ5-v6 --new-item ["<change 描述>"] --inbox IN-xxx (--dry-run | --apply)   # 0.16.4：在目標 plan 新增一個 R<n+1> 收該鍵（次要結果）；不給描述＝預設「補充結果：<key> 由主要結果降為次要結果」；與 --to-item 互斥
python3 <skill路徑>/scripts/nest_result.py <root> --key <結果鍵> --under <主結果鍵> --inbox IN-xxx (--dry-run | --apply)   # 0.16.5：結果主從——同一份 plan outputs 裡把該鍵宣告為另一個鍵的支撐結果（outputs[i].supports）；只改呈現層級，不改數字、不改歸屬
python3 <skill路徑>/scripts/nest_result.py <root> --key <結果鍵> --top --inbox IN-xxx (--dry-run | --apply)                        # 0.16.5：移除 supports、拉回頂層（--under '' 同義）
python3 <skill路徑>/scripts/set_tier.py <root> --node p:SQ5-v14#R1=extended [--node r:some_key=] [--node v:V15=extended] --inbox IN-xxx (--dry-run | --apply)   # 0.20.0：方法／敏感性子分析／主要或未宣告結果／驗證放入（=extended）或移出（=空）Extended Data 區帶；只改 analysis/extended-data.yaml；拒收問題、圖表（走 set_figure_role.py）、群 #S、次要鍵、支撐結果鍵
python3 <skill路徑>/scripts/demote_plan.py <root> --plan AQ1-v1 --to-plan SQ5-v7 --inbox IN-xxx (--dry-run | --apply)   # 0.18.0：附錄問題的 active plan 整份降為另一份 active plan 的敏感性子分析（來源 outputs 成為目標新版 robustness 的 R<n+1>、來源自己的子分析接在後面、來源問題無 active plan）
python3 <skill路徑>/scripts/run_batch.py <root> --batch <json 檔 | - | '{"actions": [{"kind": "nest_result", "payload": {...}}, ...]}'> --inbox IN-xxx (--dry-run | --apply)   # 0.17.0：批次——依序跑整串動作、版本接力、每步各記 D#、最後只重畫一次
```

批次（0.17.0，kind `batch`，payload `{actions: [{kind, payload, reason?}, …], reason?}`）也走腳本：使用者在關聯圖連續拖放多次——0.17.1 起**放開即暫存**：放開節點不彈表單，直接用各 kind 的預設值（reassign 的 `to`＝下一個 AQ 號、promote 的 `to` 空、拖到 Supplementary 帶的結果＝新增子分析、其餘照候選）加進暫存、圖立刻重排（節點虛線外框＝已暫存；0.17.2 起位置也跟著新的 parent／band 走——每格重算 order，子結果緊接主結果、搬走的結果／子分析排到目標區塊、換帶的子樹排到新帶最後，暫存期間跳欄邊直接畫折線），toast 附「復原」；要改 `to`／落點／單項理由就按暫存面板那列的「編輯」（開原本的表單、「更新暫存」取代）；關聯圖控制列勾「放開時先開表單」才回到 0.17.0 的放開 → 表單 → 「加入暫存」／「單獨送出並預覽」——最後在頁首「暫存動作」面板按「全部預覽」→ 頁面建一筆 `batch` 進收件匣並跑 `run_batch.py --dry-run`（整串在**同一個**工作區依序真跑，摘要每步一段＋總結：最終各問題的 plan 版本、fingerprint、預定 D# 範圍、版本接力對照），「全部套用」才 `--apply`；「理由（整批，可空）」可在預覽後填（0.17.3：理由不是 dry-run 內容，套用時才以 `{id, token, reason}` 帶給 server、`run_batch.py --reason` 收，改理由不必重新預覽；只有暫存清單本身變了——增刪、上下移、編輯——才讓已建的批次項目作廢；同清單重按「全部預覽」重用同一筆、重新載入後沿用仍 pending 的那筆；「全部套用」停用時鈕旁寫原因；不是本頁建立的 pending `batch` 項目可在面板下方一鍵撤回）。`run_batch.py` 對每個子步驟以子程序跑該 kind 的既有腳本 `--apply` 並設環境變數 `SSOT_ACTIONS_BATCH_STEP=1`（子步驟略過自己的工作區 dry-run、不重畫、不追記 daily log），每步之後從 index 的 active 差異讀出「舊 plan id → 新 plan id」（與 reassign／promote 的「舊問題 id → 新問題 id」），後續步驟 payload 裡引用舊 id 的欄位（`plan`／`to_plan`／`from`／`to_question`／`order`）自動改指新 id；結果鍵不改名。每步仍各記一筆模板 D#（append-only 帳本不合併）、waiver 重登每步照舊；成功後收件匣 `resolved_by` 寫 D# 範圍（如 `D-054–D-058`）、重畫一次、daily log 追記一段（列全部步驟與 D#）、run log `reviews/batch-<date>.json`。**中途失敗**：先在工作區整串跑過才動 root，所以 root 上失敗多半是 token／競態；第 k 步在 root 失敗時該步自己還原、前 k−1 步保留（各有 D#）、後面不跑、exit 1，摘要與 run log 寫明「已套用 1..k−1、第 k 步失敗已還原、k+1.. 未執行」，收件匣項目留 pending 並在 note 記停在哪（`check_inbox.py --annotate IN-xxx --note …`）。`check_inbox.py` 對 pending 的 `batch` 驗每一項 payload——第 1 項嚴格、第 2 項起對 plan／問題 id 放寬為「現行 id 或前面步驟會產生的 id」（語意留給工作區 dry-run 判）——並印建議命令。理由：頁面建 batch 時把整批理由放進 payload 頂層 `reason`，套用時再帶一次現值蓋過（server 成功後以 `check_inbox.py --set-reason` 同步收件匣那筆），`run_batch.py --reason` 收；各步 D# 的 reason ＝ 該項自己的 `reason`（「編輯」填的）否則整批理由，都空則模板句「使用者於進度頁面批次拖放（IN-xxx）」，後接「批次（收件匣 IN-xxx）第 k／n 步」。0.17.1 起沒有獨立的單動作入口——一項暫存也走「全部預覽」→「全部套用」；「待套用動作」面板（pending 收件匣項目）照舊，對 `batch` 項目一樣可預覽／套用／撤回。

Extended Data 歸屬（0.20.0）也走腳本：關聯圖上把方法（active plan）、敏感性子分析、主要／未宣告結果或驗證拖到 **Extended Data 帶** → `kind: set_tier`（payload `{node, tier: 'extended'}`）；已列在檔裡（`band_source` explicit）的節點拖回它的推導區帶（從檔裡拿掉後會落到的帶）→ 同 kind、`tier` 空（移出）；拖到既非 ext 也非推導區帶的帶則走該型別原本的規則（例如主要結果 → Supplementary 仍是 `move_result` 下拉）。紅線 toast：問題節點（「問題（SQ／AQ）不能放 Extended Data」）、群 `#S`（跟 plan 走）、次要結果聚合節點（跟子分析走）、支撐結果（跟主結果走）、`inherited` 的節點拖出 ext（「這個節點的 ED 歸屬來自 <來源 id>，請拖那個節點」）；圖表照舊走 `set_role`。`set_tier.py` 只在 `analysis/extended-data.yaml` 的對應清單（`plans`／`results`／`validation`）逐行增刪那一項（缺檔用模板建；註解與鍵序不動；清單由 `[]` 改成區塊、刪到空改回 `[]`）、寫前後以 YAML 比對，D#（stage figure-design、question＝節點所屬問題）內文列出跟著走的節點——由 render_progress 的區帶規則算（把改後的清單注入 Sources 建一次關聯圖比對前後 band），不另寫一套規則；收件匣結案、重畫。前置條件（exit 2）：id 不存在、問題／圖表／群／次要鍵／支撐鍵、已列（放入）或未列（移出）、已跟著別的節點在 ED（inherited）。批次裡 `node` 為 `p:` 時 plan 部分隨版本接力。

降為敏感性子分析（0.18.0）也走腳本：關聯圖上把一份 active plan 拖到**另一個問題**的 active plan 上 → `kind: demote_plan`（payload `{plan, to_plan}`）；來源是主問題的 plan、目標同問題、目標非 active 都是紅線 toast。`demote_plan.py` 只在目標 plan 出一版 amendment：robustness 追加 `R<n+1>`（歸屬容器——`change`「由 <來源>（<來源問題>）降為本 plan 的敏感性子分析：<來源 question 前 80 字>」、`expected_keys`＝來源 outputs 全部鍵、`executed`＝鍵是否都在 results.json、`execution_note` 註明 rows 逐位沿用來源 run、本項只是歸屬容器、原 plan 檔保留），來源自己的 robustness 項逐一接在後面（`change` 前綴「（原 <來源> 的 R<k>）」、其餘逐字複製、`evidence_owned_by` 指向來源者改指目標新版）；來源 plan yaml 不動，index 標 superseded／replaced_by＝目標新版、來源問題 `active` 移除；results 來源全部鍵與目標舊版鍵 retag 到目標新版；validation 來源 item 改掛目標問題／新版——`primary_results` **不改列**（`check_validation` 只要求鍵存在且 plan_id 與 item 一致、不要求在 outputs，改空反而撞「必須是非空 list」；降階記在 reaffirmed note）；project.yaml 來源問題 status 改 `blocked`、`results:<鍵>` links 搬到目標問題尾端；waiver 重登、快照 0 tamper、D#（stage study-design；known_consequences 註明屬設計變更、來源問題無 active plan——`check_plan` 對附錄問題只 WARNING、evaluate 對附錄問題不要求覆蓋，不擋關，它若要保留須另立 plan 或裁定 dropped／併入——與四項 open item）。前置條件（exit 2）：來源不是附錄問題的 active plan（主問題的 plan 要先降階）、目標非 active 或與來源同問題、來源 outputs 沒有鍵。

結果主從（0.16.5）也走腳本：關聯圖上把頂層主要結果拖到**同一份 plan** 的另一個頂層主要結果上 → `kind: nest_result`（payload `{key, under}`）；支撐結果拖到所在帶的空白處 → 同 kind、`under` 空（拉回頂層）；拖到別的結果上 → 換主結果（一步到位）。`nest_result.py` 在同一份 plan 出一版 amendment，只改該 outputs 條目的 `supports`（加／改／刪），其餘 leaf 逐字不動；results 該 plan 全部鍵 retag 到新版、validation 改掛新版、waiver 重登、D#（stage study-design，known_consequences 註明只改呈現層級與稿件主表／支撐表歸類，open item 只列 reviewer-methods）。前置條件（exit 2）：鍵不在該 plan 的 outputs（次要／未宣告結果不能巢狀）、`under` 不在同 plan outputs、`under` 自己已是支撐結果（深度只允許一層）、`under == key`、已是該狀態。`check_plan.py` 對 `supports` 驗：指向的鍵在同 plan outputs、不自指、不成環、只一層（BLOCKER）。支撐結果要換帶仍走 `move_result`，但得先拉回頂層（前端紅線 toast）。

結果鍵搬家（0.16.2）也走腳本：結果節點拖到別的方法上 → `kind: move_result`（payload `{key, to_plan}`，A 型）；拖到任一敏感性子分析上 → 同 kind 加 `to_item`（B 型）。0.16.4 起結果節點也能拖到區帶：Main 帶的主要結果拖到 Supplementary 帶、放開後表單以下拉選落點——預設「新增一個敏感性子分析（補充結果）」＝同 kind 加 `new_item`（change 描述；由 `move_result.py --new-item` 在來源 plan 新增 `R<n+1>`、expected_keys 只有該鍵、executed true、execution_note 註明只是歸屬容器），另可選來源 plan 既有的各 R（`to_item`）或各附錄問題 active plan 的 outputs；Supplementary 帶的次要結果拖到 Main 帶則預設升回本 plan 的 outputs、另列各主問題 active plan 的 outputs。`to_item` 與 `new_item` 互斥（腳本 exit 2、server 400）。來源由 results.json 該鍵的 plan_id 判，須為 active plan；目標已含該鍵會被擋。來源與目標各出一版（同一份 plan 只出一版），數字不動；validation 中只以該鍵為 primary_results 的 item 改掛目標、同時含別的鍵的 item 會移除該鍵那一行（該鍵在目標問題下的驗證列為 open item）。

要讓頁面上的「待套用動作」面板能預覽與套用，啟動伺服器時加 `--allow-apply`（另可加 `--daily-log <path>` 透傳給腳本）：`python3 <skill路徑>/scripts/progress_server.py <root> --port 8765 --allow-apply`。開了之後 `POST /api/actions/dry-run {id}` 代跑 `--dry-run` 回摘要與 token，`POST /api/actions/apply {id, token}` 在 token 與現行 SSOT 相符時才代跑 `--apply`（不符 409，要重新預覽），每次 apply 追記 `<root>/PROGRESS.actions.log`；不加旗標時兩個端點一律 403，伺服器維持「只寫收件匣」。

放開節點後的流程（0.16.3）：表單按「送出並預覽」→ `POST /api/inbox` 建一筆 → 同一個對話框立刻 `POST /api/actions/dry-run` 顯示摘要 → 三個鈕：「套用」（`/api/actions/apply`；409 自動重跑預覽）、「先留在收件匣」（留 pending，之後在「待套用動作」面板處理）、「撤回」（`POST /api/inbox/dismiss {id, note?}`，伺服器代跑 `check_inbox.py --dismiss <id> --note <note>`，note 預設「使用者在放開預覽後撤回」；這個端點只動收件匣、**不需 `--allow-apply`**）。server 未開 `--allow-apply` 時對話框仍會送收件匣，摘要區顯示 403 原因、「套用」停用，另外兩個鈕照常。收件匣裡 `status: dismissed` 的項目本 skill 不再處理。0.18.2 起「待套用動作」面板每列也有「撤回」鈕（同一個 `/api/inbox/dismiss` 端點，note「使用者在待套用動作面板撤回」；不需 `--allow-apply`，連上伺服器就能用；撤回期間該列預覽／套用／撤回三個鈕一起停用，成功後重新載入、失敗把原因寫在該列摘要區），十一種 kind（含 batch；0.20.0 加 set_tier）都有。

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
  - **pending 為 `reassign`（主問題降為附錄問題）、`promote`（升回主問題）、`set_role`（圖表 role）、`move_plan`（搬方法）、`move_sensitivity`（搬敏感性子分析）、`reorder`（調順序）、`move_result`（搬結果）、`nest_result`（掛到主結果下／拉回頂層）、`demote_plan`（降為敏感性子分析）、`set_tier`（0.20.0；Extended Data 歸屬，`set_tier.py`）或 `batch`（0.17.0；整串動作，`run_batch.py`）時走腳本，不走人工**：`check_inbox.py` 已在該筆下面印出可直接執行的命令。**不得人工重做各步**（不得自己搬 goals、建 plan、retag results、改 validation、重登 waiver、寫 D#），**不得整本讀 decisions.yaml** 去仿寫先例；只跑對應腳本 `reassign_question.py`／`promote_question.py`／`set_figure_role.py`／`move_plan.py`／`move_sensitivity.py`／`reorder_questions.py`／`move_result.py`／`demote_plan.py`／`nest_result.py`／`set_tier.py` 的 `--dry-run`→ 把 ≤ 30 行的摘要（要改哪些檔、搬哪段、新舊 fingerprint、預定 D#）呈給使用者 → 使用者同意後改 `--apply`（可加 `--daily-log`）。腳本會自己備份、失敗還原、結案收件匣、重畫進度圖並 append 一筆模板 D#；主 loop 驗收只看磁碟成品（`reviews/reassign-*.json`／`set-figure-role-*.json` 的步驟紀錄、新 D#、各 checker）。前置條件被擋（exit 2）或鏈失敗（exit 1，已還原）時把原因照實回報，不要繞過腳本手做。搬走最後一個主問題須明確加 `--allow-empty-main`，且要先告知使用者 `check_coverage` 會因此擋關。
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
