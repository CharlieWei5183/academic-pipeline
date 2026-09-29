#!/usr/bin/env python3
"""研究問題里程圖 renderer（確定性）: 唯讀 SSOT → typed JSON IR → schema 驗證 → 自含 HTML。

用法: python3 render_progress.py <project-root> [--dry-run] [--json] [--ir-only]

讀取（只讀）: <root>/project.yaml、decisions.yaml、analysis/plans/index.yaml、
analysis/results.json、analysis/validation.yaml、analysis/claims.yaml、analysis/claim-audit.yaml、
methodology/route.yaml、integrity/register.yaml、analysis/data-audit.yaml、literature/*、
analysis/figures/manifest.json、manuscript/{zh,en}/v*.md、reviews/issue-ledger.yaml、evaluations/*.md
寫入: 只寫 <root>/PROGRESS.ir.json（IR）與 <root>/PROGRESS.html（自含 HTML）

旗標:
- --dry-run  不寫檔；單獨使用時把整份 HTML 印到 stdout
- --json     stdout 改印 IR（ensure_ascii=False, indent=2）；與 --dry-run 正交
             （單獨用仍寫檔；兩者同時 = 只印 IR、不寫）
- --ir-only  只寫 PROGRESS.ir.json、不寫 PROGRESS.html
- --embed-figures  圖表節點 meta.data_uri 內嵌圖檔（svg／png、單檔 ≤ 5 MB，超過跳過並 WARNING）；預設不內嵌，
             HTML 以相對路徑 meta.file 顯示（HTML 在專案根，相對路徑直接可用）

收件匣（唯讀）: 讀 <root>/PROGRESS.inbox.yaml（progress_server.py 寫、check_inbox.py 結案）→ IR 頂層 inbox
{present, pending, items}（0.16.0 起 item 另帶 payload 物件：reassign {from, to, primary_model}／set_role {figures}／promote {from, to}／
move_plan {plan, to_question}／move_sensitivity {plan, item, to_plan}／reorder {list, order}／move_result {key, to_plan, to_item, new_item?}／
nest_result {key, under}，其他 kind 為 {}）、
有 target 的 pending 項掛到圖節點 meta.inbox 並加徽章「收件 N」、stats.inbox_pending；關聯圖分頁另有「結構化動作」（0.16.0；0.16.1 起六種；0.16.2 起七種；0.16.5 起八種）：
問題節點拖到另一個帶 → reassign／promote、拖到同帶另一個問題上（排在它之後）→ reorder；方法節點拖到沒有 active plan 的問題上 → move_plan；
敏感性子分析拖到別的方法上 → move_sensitivity；結果節點（主要／次要／未宣告）拖到別的方法上（A 型，成為其主要結果）或任何敏感性
子分析上（B 型，成為其次要結果；含來源 plan 自己的 R）→ move_result；0.16.4 起結果節點也能拖到區帶：Main 帶的主要結果拖到 Supplementary 帶、
Supplementary 帶的次要（或附錄問題的主要）結果拖到 Main 帶，游標不在任何候選節點上時候選＝整個帶（打亮、不畫線；節點落點優先），放開後表單多一個
「放到哪裡」下拉——降到 Supplementary 預設「新增一個敏感性子分析（補充結果）」（payload new_item 帶預設描述、由 move_result.py --new-item 在來源 plan
新增 R<n+1>），另列來源 plan 既有的各 R 與各附錄問題 active plan 的 outputs；升到 Main 預設「升回本 plan 的 outputs」（所屬 plan 屬主問題時），另列各
主問題 active plan 的 outputs（沒有可放的就不算候選、toast 說明）；附錄問題 plan 的主要結果拖到 Supplementary 帶不算候選（toast「已在 Supplementary」）；
0.16.5 結果主從：plan outputs 條目可帶 supports: <同 plan 另一鍵>（check_plan 驗：存在、不自指、不成環、只一層）——有 supports 的主要結果節點
subtype supporting、parent＝r:<under>、縮排在主結果之下、同一區帶（band 跟主結果）、meta.supports；主結果 meta.supporting_ids、徽章「支撐 n」、
面板可暫時收合；主結果 → 支撐結果一條 supports 型 L 形線（結果色）、plan → 支撐結果的 produces 預設不畫；stats.supporting_result_keys。
拖放：頂層主要結果拖到同 plan 的另一個頂層主要結果上 → nest_result {key, under}（跨 plan、次要、已是支撐結果的目標 → 紅）；支撐結果拖到所在帶
的空白處 → nest_result {key, under: ''}（拉回頂層）、拖到別的結果上 → 換主結果、拖到別帶 → 紅（先拉回頂層）。
圖表拖到別的帶或在面板改 role → set_role。0.20.0：方法（active plan）、敏感性子分析、主要／未宣告結果、驗證拖到 Extended Data 帶 → set_tier
{node, tier: 'extended'}（寫進 analysis/extended-data.yaml，跟著走的節點一起換帶）；已是 explicit 的節點拖回推導區帶 → set_tier {node, tier: ''}；
問題、群 #S、次要結果聚合節點、支撐結果、inherited 的節點 → 紅（各有提示句）。拖曳中依游標位置即時判定候選並在
SVG 的 <g id="drag-preview">（Python 只出空骨架）畫虛線與打亮，非法落點改紅、放開不送出；放開後開表單（父節點欄位唯讀帶入、只填理由）
→ 按「送出並預覽」POST /api/inbox 建一筆，成功後不重載，同一個對話框立刻 POST /api/actions/dry-run 把變更摘要顯示出來（0.16.3），
摘要下三個鈕：「套用」（/api/actions/apply 帶 token；409 顯示「SSOT 已變，重新預覽」並自動再跑一次 dry-run）、「先留在收件匣」（關對話框重載，
項目留 pending）、「撤回」（POST /api/inbox/dismiss，代跑 check_inbox.py --dismiss）；server 未開 --allow-apply 或 dry-run 前置條件不符時摘要區
顯示原因、「套用」停用、另外兩個鈕照常。頁首「待套用動作」面板（第二入口，行為不變）列 pending 的七種項目，「預覽變更」呼叫
/api/actions/dry-run、「套用」帶 token 呼叫 /api/actions/apply（server 未開 --allow-apply 或 file:// 開啟時按鈕停用並說明）；面板與對話框
共用同一段預覽／套用 JS（actPreview／actApply）。0.17.0 批次暫存：表單另有「加入暫存」——不呼叫 server，把 {kind, payload, reason} 推進本頁的
staged[]（localStorage，key ap-staged:<project_root>）並對本地圖模型做樂觀更新（applyOptimistic：parent／band／subtype 一定改對，邊只改做得到的）後
reorderStaged()（0.17.2：每個 (band, col) 格子以 IR 的 order0 為基準重算 order——頂層節點照 order0、子孫緊接其後；被動過的節點依 anchor 插到目標區塊，換帶的子樹排到新帶最後；暫存期間 dummy 列停用、跳欄邊直接畫折線）再 relayout()，暫存節點加 class staged（虛線外框）；頁首「暫存動作」面板列每項、可刪除／上下移（重新載入後重新套用其餘暫存）、「全部預覽」建一筆
kind batch 進收件匣並 dry-run（run_batch.py 在同一個工作區依序真跑、版本接力）、「全部套用」帶 token。0.17.1 放開即暫存：放開節點預設不開表單，直接用各 kind
的預設值（stageDirect／defaultPayload）加進暫存並重排，toast 附「復原」；面板每列「編輯」開原本的表單預填、「更新暫存」取代；「全部預覽」旁「理由（整批，可空）」
放進 batch payload 頂層 reason（run_batch --reason 收；各步 D# reason＝該項理由否則整批理由，都空則模板句）；核取「放開時先開表單」（localStorage）才回到放開 → 表單。
0.17.3 理由不再作廢批次：理由欄改動只存 localStorage，「全部套用」時以 {id, token, reason} 帶給 server（token 只看 actions）；只有暫存清單本身變了（增刪、上下移、編輯）才 stagedInvalidate()
（dismiss 舊項目、清 stagedBatchId、標 stagedStale）；stagedBatchId＋token＋actions JSON 存 localStorage（ap-staged-batch:<project_root>），重新載入後該筆仍 pending 且 actions 相同就沿用、直接啟用「全部套用」；
同清單再按「全部預覽」重用同一筆只重跑 dry-run；「全部套用」停用時按鈕旁 #staged-apply-why 顯示原因；#staged-old 列出不是本頁暫存建立的 pending batch 項目、一鍵撤回。
0.18.0 demote_plan：active plan 拖到另一個問題的 active plan 上 → kind demote_plan（payload {plan, to_plan}；來源是主問題的 plan、目標同問題、目標非 active → 紅線）；樂觀更新把來源 plan 變成目標群下的子分析（parent p:<to>#S、subtype sensitivity、縮排 48、帶跟目標、fixBox 縮框）、其主要結果變次要、其群 staged_gone、其子分析改掛目標群、來源問題徽章「無 active plan」（setBadge）。拖放只產生收件匣項目，頁面不直接改任何 SSOT、預覽不進 IR；
頁首顯示「收件匣待處理 N 筆」與可展開清單；無法解析 → WARNING 視為無。頁面表單（＋ 新問題／新分析、節點面板
＋ 意見）只在經 progress_server.py 以 http 開啟（fetch /api/ping 成功）時啟用，file:// 一律 disabled。

泳道: 專案層（17 站，含 clean rerun 與整體評估兩個專案級關卡）最上，接著 goals.sub_questions
（kind sq）、goals.appendix_questions（kind aq）各 6 站。每站從對應 SSOT 檔判定 done／expired／blocked／pending／unknown，
判定規則見 SQ_RULES／PROJECT_RULES 與各 judge_* 函式；每個節點的 evidence[].source 寫出
實際讀的檔與欄位。決策註記（decisions.yaml）依 question／links 掛到泳道，預設收合。
缺檔、缺欄位一律 pending；檔存在但無法解析一律 unknown 並 WARNING；不過濾任何泳道或站。

關聯圖（IR 的 graph 鍵、HTML 的「關聯」分頁）: 節點＝問題 q:／方法 p:（＝計畫版本，label 帶 model_id）／
驗證 v:／結果 r:／決策 d:，邊＝decomposes／plans／supersedes／validated_by／primary／produces／cites／refers，
方法節點下掛敏感性子分析（plan yaml robustness[] → p:<pid>#<Rid>，subtype sensitivity、L 形父子線），一個 plan 的全部子分析
先收成一個敏感性分析群 p:<pid>#S（subtype sensitivity_group、parent＝plan、label「<pid> 敏感性分析」、徽章「n 項」），
子分析的 parent 是群；0.18.0（使用者 2026-09-16 裁定，取代 2026-09-15 的「群放 Supplementary」畫法）：群縮排在所屬 plan 之下（縮一層 24px、
plan → 群 L 形父子線）、子分析再縮一層（48px）、群／子分析／次要結果的區帶一律跟 plan；不再有 supplements「敏感性對照」短垂線；
plan 徽章「敏感性 n」、面板可收合群與子分析（nestHidden，與主結果的「支撐 n」同一套）；結果依宣告分主要（outputs，頂層）／次要（只在 robustness expected_keys；subtype secondary、
parent＝宣告它的子分析，縮排成子項、跟父收合）／未宣告（results.json 掛此 plan 但沒宣告，虛線），
驗證與否改為結果節點的獨立標記（meta.validated、右端「未驗證」小標）。
0.19.0 宣告粒度（使用者 2026-09-17 裁定，跨專案一致、不設門檻）：次要鍵不再逐鍵建 r:<key>，有自有次要鍵的敏感性子分析底下一個次要結果聚合節點
r:<pid>#R<k>#secondary（subtype secondary_group、parent＝子分析、鍵全列在 meta.keys；1 鍵顯示鍵名、多鍵「次要結果 n 鍵」；沒宣告任何次要鍵的
子分析沒有這個宣告單位，不建節點也不建邊；徽章「未登錄 a／未驗證 b」；圖表／驗證／決策指到次要鍵的邊都改指聚合節點並記鍵數），未宣告鍵仍逐鍵虛線；另有 report.md 節點 o:report
（type report、圖表欄最後一列、main 區帶孤兒帶；圖表 → report 的 embedded_in 邊預設不畫；role=main 未被 report.md 引用的圖表徽章「報告未引用」）。
區帶（每個節點的 band 欄位，main｜ext｜supp）：Main＝主問題、SQ、其計畫（含敏感性分析群、子分析、次要結果）／驗證／結果、只呈現 main
結果的圖表、決策；Extended Data＝依 manifest role 的圖表，0.20.0 起也放 analysis/extended-data.yaml 列出的方法／子分析／主要或未宣告結果／
驗證與跟著它們走的節點（群與子分析跟 plan、次要結果跟子分析、支撐結果跟主結果、主要結果跟 owner plan、驗證跟 plan_id 的 plan、缺 role 的圖表
跟呈現的結果；每個非問題節點 meta.band_source ∈ explicit／inherited:<來源>／derived；只有問題節點不能放——使用者 2026-09-17 裁定；缺檔＝
與 0.19.0 畫法相同）；Supplementary＝附錄問題及其一切（計畫、群、子分析、驗證、結果）、補充圖表
（0.18.0 起；0.15.0–0.17.3 的「Supplementary＝敏感性分析群與子分析、次要結果」規則作廢）。同來源往同欄的邊由 route_edges 併成一條幹線＋分支；
任何跨區帶的邊（decomposes 主問題→AQ、depicts 結果→圖表除外）預設不畫，IR 仍保留。版面：main 區帶標題列在 y = GRAPH_PAD、節點從
GRAPH_PAD + BAND_TITLE_H 起，main_bottom＝可見 main 節點（不計決策）最低下緣，分隔線 main_bottom + BAND_GAP/2、supp 標題列
main_bottom + BAND_GAP、supp 節點從 main_bottom + BAND_GAP + BAND_TITLE_H 起；supp 無可見節點時不畫分隔線與標題、節點從
GRAPH_PAD 起；order 為每 (band, col) 內的整數序；q:main 只對 main 區帶的問題垂直居中；收合舊版的群／子分析／次要結果借現行版
群的列（現行版沒有群時借 plan 的列）。stats 加 band_main_nodes／band_ext_nodes／band_supp_nodes／sensitivity_groups。
問題帶（0.18.1；每個非決策節點的 strip 欄位）：每個區帶內依問題再分橫向的帶——問題節點是自己、plan／群／子分析跟 plan 的 sq、驗證跟
item 的 sq、結果跟 owner plan（只被 goals 引用的取最前的引用問題）、次要／支撐跟父、圖表取呈現的結果中 goals 順序最前的問題、孤兒
空字串；帶序＝goals 順序（問題節點在別的區帶但有節點落在這一帶的問題也各成一帶）、孤兒帶最後；帶內各欄從帶的第一列起各自往下排、
帶高＝最高那欄的列數、帶與帶之間留 STRIP_GAP（1 列）、以淡色細線分隔；問題節點在帶首列；決策不帶 strip、依 refers 掛到對應的帶
（_decision_strip）。barycenter 只在同帶同欄內重排、dummy 列落在目標的帶。IR graph.strips＝[{band, question, y0, y1}]、stats.strips。
問題 id 別名（Sources.question_aliases）：index 裡 sq 不在 goals 的 plan，沿 replaced_by（或反向 supersedes）鏈走到終點 plan，
終點的 sq 在 goals 就記 {舊 id → 現行 id}；里程分頁的 plan／validation item／claims 篩選與決策註記、關聯圖的 plan 歸屬
（舊版進現行版的 superseded_versions、收合借列、band）、決策 refers、validation 節點都套用；現行問題節點 meta.aliases 與
title 尾綴標出舊 id，IR graph 頂層 question_aliases（空就 {}）。只有解析不到的 sq 才造「goals 無此問題」占位節點。
再加第五欄圖表 f:（analysis/figures/manifest.json，r → f depicts「呈現於」；state 依 status 與檔案存在與否；
results_keys 指到不在圖裡的鍵不建邊、徽章「無對應結果鍵」並 WARNING），結果節點 meta 帶表（columns／rows 最多
200 列／n_rows／truncated）或 value／display／unit，面板可直接看表與圖。
全部只從 SSOT 建（來源見 build_graph），缺檔缺欄位就沒有那條邊；每條邊帶 default_visible 與 style
（solid／dashed／thin）——預設只畫主幹（q→SQ、q→現行 p、p→v、v→主要結果 r、v→穩健性 r 細線）與「未驗證
旁路」（現行 p→不在任何 primary_results 也不在任何 robustness result_keys 的 r，虛線），取代／引用／決策邊
點選或開關才顯。superseded 計畫收合（collapsed），現行版帶 superseded_versions 與
徽章。plan 宣告但 results.json 沒登錄的鍵建 pending 節點、goals 指向不存在的鍵建 unknown 節點並計入
stats.dangling_result_keys；primary 與 robustness 都沒驗過的登錄鍵計入 stats.unvalidated_result_keys。版面由
Python 算好（欄序 主問題 q:main → question（SQ／AQ）→ method → validation → result → figure → decision，主問題獨占
最左一欄並在 SQ／AQ 欄的第一筆與最後一筆之間居中；每欄固定序：問題依 lanes、方法依
（問題, 版本）、驗證依（問題, item 序）、結果依（問題, 主要→其他→dangling, 現行 plan 宣告序）、決策依 id；
x／y 為收合檢視，另給 col／order 讓 JS 展開時重排），HTML 只照座標畫 SVG，渲染確定性。邊的走線由 route_edges
決定：同來源往同目標欄的可見邊合併成一條垂直幹線＋每個目標一條水平分支，每個欄間走道以區間圖貪婪著色分車道
（車道間距 8px、最多用走道 80% 寬——走道 120px 即 13 條，超過折回並記 INFO），JS 端同一套演算法在展開／點選時重算。

exit code: 0 完成; 2 BLOCKER（專案根目錄不存在、IR 未通過自身 schema 驗證——後者不落檔）。
診斷訊息（BLOCKER／WARNING／INFO）在無旗標時印到 stdout，--dry-run 或 --json 時改印 stderr。
"""
from __future__ import annotations

import argparse
import base64
import bisect
import heapq
import math
import posixpath
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print('需要 PyYAML: pip install pyyaml --break-system-packages')
    sys.exit(2)

SCRIPT_REL = 'skills/status/scripts/render_progress.py'
IR_NAME = 'PROGRESS.ir.json'
HTML_NAME = 'PROGRESS.html'
SCHEMA_VERSION = 1
STATES = ('done', 'expired', 'blocked', 'pending', 'unknown')
STATE_ZH = {'done': '完成', 'expired': '過期', 'blocked': '受阻', 'pending': '未到', 'unknown': '不明'}
DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')
SUMMARY_MAX = 120
CELL_MAX = 24

# ---------- 站（stage）定義 ----------

SQ_STAGES = (
    ('study-design', '研究設計'),
    ('analyze-data', '正式分析'),
    ('validate-results', '結果驗證'),
    ('evaluate', '目標評估'),
    ('interpret-results', '結果判讀'),
    ('claim-audit', '主張審查'),
)
PROJECT_STAGES = (
    ('project-init', '專案初始化'),
    ('methodology-router', '方法路由'),
    ('integrity-check', '完整性檢查'),
    ('data-audit', '資料稽核'),
    ('lit-review', '文獻回顧'),
    ('evidence-synthesis', '證據綜整'),
    ('analyze-data:rerun', 'clean rerun'),
    ('evaluate:full', '整體評估'),
    ('figure-design', '圖表設計'),
    ('write-manuscript', '中文稿'),
    ('write-supplementary', '補充材料'),
    ('check-consistency', '一致性檢核'),
    ('peer-review', '虛擬審稿'),
    ('revise', '修訂'),
    ('translate-en', '英文稿'),
    ('submission-prep', '投稿準備'),
    ('typeset', '排版'),
)

# 判定規則表: stage id → (讀的檔, 判定摘要)。判定函式為 judge_<stage>（冒號後綴改底線）。
SQ_RULES = {
    'study-design': ('analysis/plans/index.yaml', 'plans[] 篩 sq；active → done、只剩 superseded → expired、無版本 → pending'),
    'analyze-data': ('analysis/results.json', '鍵篩 plan_id 屬該 SQ；掛 active plan → done、只掛 superseded → expired、無鍵 → pending'),
    'validate-results': ('analysis/validation.yaml', 'items[] 篩 sq；頂層 status expired → expired、item pass／qualified → done、fail → blocked、無 item → pending'),
    'evaluate': ('project.yaml', 'goals 該問題 status：addressed → done、blocked／dropped → blocked、open／缺 → pending'),
    'interpret-results': ('analysis/claims.yaml', 'claims[] 篩 sq；有 → done、無 → pending'),
    'claim-audit': ('analysis/claim-audit.yaml', '檔存在且 state.claim_audit.result 非空：pass → done、其他 → blocked；否則 pending（專案級結果套到每條問題）'),
}
PROJECT_RULES = {
    'project-init': ('project.yaml', '存在 → done；date 取 decisions.yaml 中 stage project-init 最早日期'),
    'methodology-router': ('methodology/route.yaml', '存在 → done；date 取 state.methodology.at 或 route.yaml 的 routed_at／confirmed_at／at'),
    'integrity-check': ('project.yaml / integrity/register.yaml', 'state.integrity.prestudy 非空 → done；否則 register.yaml 存在 → done'),
    'data-audit': ('project.yaml / analysis/data-audit.yaml', 'state.data_audit.result 非空 → done；否則 data-audit.yaml 存在 → done'),
    'lit-review': ('project.yaml / literature/', 'state.literature.updated_at 非空 → done；否則 references.bib 或 matrix 檔存在 → done'),
    'evidence-synthesis': ('project.yaml / literature/evidence-synthesis.yaml', 'state.evidence_synthesis.result 非空或檔存在 → done'),
    'analyze-data:rerun': ('project.yaml', 'state.analysis.rerun 非空：pass／waived → done、其他 → blocked'),
    'evaluate:full': ('project.yaml', 'state.last_full_evaluation.result：pass → done、fail → blocked、空 → pending（開寫關卡的完整評估）'),
    'figure-design': ('analysis/figures/manifest.json', '存在 → done（summary 帶筆數）'),
    'write-manuscript': ('project.yaml / manuscript/zh/', 'state.zh_latest 非空 → done；否則 v*.md 存在 → done'),
    'write-supplementary': ('project.yaml', 'state.si_latest 非空 → done'),
    'check-consistency': ('project.yaml', 'state.last_consistency.result：pass → done、fail → blocked'),
    'peer-review': ('project.yaml', 'state.review.round > 0 → done'),
    'revise': ('reviews/issue-ledger.yaml', '存在 → done（summary 帶 issues 筆數）'),
    'translate-en': ('project.yaml / manuscript/en/', 'state.en_final.version 非空 → done；否則 v*.md 存在 → done'),
    'submission-prep': ('project.yaml', 'state.submission.prep 非空 → done'),
    'typeset': ('project.yaml', 'state.submission.build 非空 → done'),
}

# 各來源檔的相對路徑
REL = {
    'project': 'project.yaml',
    'decisions': 'decisions.yaml',
    'index': 'analysis/plans/index.yaml',
    'results': 'analysis/results.json',
    'validation': 'analysis/validation.yaml',
    'claims': 'analysis/claims.yaml',
    'claim_audit': 'analysis/claim-audit.yaml',
    'route': 'methodology/route.yaml',
    'register': 'integrity/register.yaml',
    'data_audit': 'analysis/data-audit.yaml',
    'evidence_synthesis': 'literature/evidence-synthesis.yaml',
    'manifest': 'analysis/figures/manifest.json',
    'extended_data': 'analysis/extended-data.yaml',   # 0.20.0：哪些方法／結果／驗證放 Extended Data 區帶（opt-in；不在 fingerprint 雜湊範圍）
    'ledger': 'reviews/issue-ledger.yaml',
    'inbox': 'PROGRESS.inbox.yaml',
}

# 文獻引用 3D 圖（0.21.0）：固定路徑，可用 --literature-graph 改指別的檔案（測試與預覽用）
LIT_REL = 'literature/citation-graph.json'
LIT_SCHEMA = 'academic-pipeline/citation-graph@1'
LIT_NODE_KINDS = {'question': 1, 'literature': 0}       # kind → 節點是不是問題點
LIT_EDGE_KINDS = {'cited_for': 'lq', 'cites': 'll'}     # kind → 畫線類別（文獻—問題／文獻引用文獻）
LIT_STR_FIELDS = ('authors', 'title', 'journal', 'doi')
# 0.22.0：文獻點的顏色＝圈內被引數（in-degree，只算 cites 邊）；global_citations 是向下相容的選填欄位
LIT_GC_FIELDS = ('count', 'source', 'retrieved')
LIT_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


# ---------- 讀檔（唯讀） ----------

def _one_line(exc: BaseException) -> str:
    return ' '.join(str(exc).split()) or type(exc).__name__


class Sources:
    """把每個 SSOT 檔讀一次、記住狀態：ok（dict）／missing／broken（附原因）。只讀不寫。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._cache: dict[str, tuple[str, dict | None, str]] = {}
        self.warnings: list[str] = []
        self.infos: list[str] = []
        self._aliases: dict[str, str] | None = None

    def _load(self, key: str) -> tuple[str, dict | None, str]:
        if key in self._cache:
            return self._cache[key]
        rel = REL[key]
        path = self.root / rel
        if not path.is_file():
            out = ('missing', None, '')
        else:
            try:
                text = path.read_text(encoding='utf-8')
                data = json.loads(text) if rel.endswith('.json') else yaml.safe_load(text)
                if data is None:
                    data = {}
                if not isinstance(data, dict):
                    raise ValueError(f'頂層不是 mapping（實際 {type(data).__name__}）')
                out = ('ok', data, '')
            except Exception as exc:  # YAMLError / JSONDecodeError / UnicodeDecodeError / OSError
                out = ('broken', None, _one_line(exc))
                self.warnings.append(f'{rel} 無法解析: {_one_line(exc)}')
        self._cache[key] = out
        return out

    def status(self, key: str) -> str:
        return self._load(key)[0]

    def data(self, key: str) -> dict:
        return self._load(key)[1] or {}

    def exists(self, rel: str) -> bool:
        return (self.root / rel).is_file()

    def yaml_rel(self, rel: str) -> dict | None:
        """讀任意相對路徑的 yaml（快取）；缺檔或無法解析回 None，後者記 WARNING。"""
        key = f'rel:{rel}'
        if key not in self._cache:
            path = self.root / rel
            if not path.is_file():
                self._cache[key] = ('missing', None, '')
            else:
                try:
                    data = yaml.safe_load(path.read_text(encoding='utf-8'))
                    if data is None:
                        data = {}
                    if not isinstance(data, dict):
                        raise ValueError(f'頂層不是 mapping（實際 {type(data).__name__}）')
                    self._cache[key] = ('ok', data, '')
                except Exception as exc:
                    self._cache[key] = ('broken', None, _one_line(exc))
                    self.warnings.append(f'{rel} 無法解析: {_one_line(exc)}')
        return self._cache[key][1]

    def glob(self, rel_dir: str, pattern: str) -> list[str]:
        d = self.root / rel_dir
        if not d.is_dir():
            return []
        return sorted(p.name for p in d.glob(pattern) if p.is_file())

    def question_aliases(self) -> dict[str, str]:
        """問題 id 別名 {舊 sq id → 現行問題 id}（只算一次、快取）。

        index.yaml 裡 `sq` 不在 goals（sub_questions ∪ appendix_questions）的每筆 plan，沿 index 的 `replaced_by`
        （缺的話用其他 plan 的 `supersedes`——plan yaml 或 index 條目——反推）走到鏈的終點 plan；終點的 `sq` 在 goals 就記
        alias，否則不記（那個 sq 仍是孤兒，關聯圖照舊造占位節點）。用途：主問題降為附錄問題（SQ1 → AQ2）後，舊版 plan、
        決策 links、validation item 的 `sq` 仍寫舊 id，里程與關聯圖都要把它們歸到現行問題。"""
        if self._aliases is not None:
            return self._aliases
        proj = self.data('project') if self.status('project') == 'ok' else {}
        goals = _dict(proj.get('goals'))
        goal_ids = {_text(_dict(q).get('id')) for name in ('sub_questions', 'appendix_questions') for q in _list(goals.get(name))}
        goal_ids.discard('')
        index = self.data('index') if self.status('index') == 'ok' else {}
        entries = [p for p in _list(index.get('plans')) if isinstance(p, dict) and _text(p.get('plan_id'))]
        sq_of = {_text(p.get('plan_id')): _text(p.get('sq')) for p in entries}
        next_of: dict[str, str] = {}
        for p in entries:   # index 的 replaced_by 為準
            if _text(p.get('replaced_by')):
                next_of[_text(p.get('plan_id'))] = _text(p.get('replaced_by'))
        for p in entries:   # 沒有 replaced_by 的，用「誰 supersedes 我」反推（index 條目或 plan yaml）
            pid = _text(p.get('plan_id'))
            sup = _text(p.get('supersedes'))
            if not sup:
                doc = self.yaml_rel(_text(p.get('path')) or f'analysis/plans/{pid}.yaml')
                sup = _text(doc.get('supersedes')) if doc else ''
            if sup and sup not in next_of and sup in sq_of:
                next_of[sup] = pid
        alias: dict[str, str] = {}
        for p in entries:
            pid, sq = _text(p.get('plan_id')), _text(p.get('sq'))
            if not sq or sq in goal_ids or sq in alias:
                continue
            cur, seen = pid, {pid}
            while cur in next_of and next_of[cur] not in seen:
                cur = next_of[cur]
                seen.add(cur)
            term = sq_of.get(cur, '')
            if term and term in goal_ids and term != sq:
                alias[sq] = term
        self._aliases = alias
        for old, new in alias.items():
            olds = '／'.join(pid for pid, s in sq_of.items() if s == old)
            self.infos.append(f'問題 id 別名：{old} → {new}（index 舊版 {olds}）')
        return alias

    def alias_of(self, sq: str) -> str:
        """把可能是舊 id 的問題 id 換成現行 id；不是別名就原樣回傳。"""
        return self.question_aliases().get(sq, sq)

    def alias_olds(self, qid: str) -> list[str]:
        """回傳指向 qid 的全部舊 id（index 順序）。"""
        return [old for old, new in self.question_aliases().items() if new == qid]


# ---------- 欄位取值 ----------

def _text(value) -> str:
    return '' if value is None else ' '.join(str(value).split())


def _date(value) -> str:
    """回傳 YYYY-MM-DD 或 ''（bare date、ISO datetime 字串都取前十碼）。"""
    s = _text(value)
    m = DATE_RE.match(s)
    return m.group(0) if m else ''


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + '…'


def _get(d, *keys):
    cur = d
    for k in keys:
        cur = _dict(cur).get(k)
        if cur is None:
            return None
    return cur


def ev(kind: str, value, source: str) -> dict:
    return {'kind': kind, 'value': _text(value), 'source': source}


def node(stage: str, state: str, date: str = '', summary: str = '',
         evidence: list | None = None, history: list | None = None) -> dict:
    return {
        'stage': stage, 'state': state, 'date': _date(date), 'summary': _text(summary),
        'evidence': evidence or [], 'history': history or [], 'current': False,
    }


def _unknown(stage: str, rel: str, reason: str = '') -> dict:
    return node(stage, 'unknown', summary=f'{rel} 無法解析' + (f'：{reason}' if reason else ''),
                evidence=[ev('path', rel, rel)])


# ---------- SQ／AQ 泳道判定 ----------

def _sq_plans(src: Sources, lane_id: str) -> tuple[dict | None, list[dict], list[dict]]:
    """回傳 (active plan entry 或 None, superseded 清單, 其他狀態清單)，皆依 index 檔案順序。"""
    index = src.data('index')
    active_map = _dict(index.get('active'))
    active_id = _text(active_map.get(lane_id))
    entries = [p for p in _list(index.get('plans')) if isinstance(p, dict) and src.alias_of(_text(p.get('sq'))) == lane_id]
    # active map 是權威來源；map 缺或指到不存在的 plan_id 時退回 status == active 的第一筆
    active = None
    if active_id:
        active = next((p for p in entries if _text(p.get('plan_id')) == active_id), None)
    if active is None:
        active = next((p for p in entries if _text(p.get('status')).lower() == 'active'), None)
    superseded: list[dict] = []
    others: list[dict] = []
    for p in entries:
        if p is active:
            continue
        status = _text(p.get('status')).lower()
        if status in ('superseded', 'active'):  # 第二個 active 是殘留標記，視同已被取代
            superseded.append(p)
        else:
            others.append(p)
    return active, superseded, others


def _plan_version(plan_id: str, fallback: int) -> int:
    m = re.search(r'-v(\d+)$', plan_id)
    return int(m.group(1)) if m else fallback


def judge_study_design(src: Sources, lane: dict) -> dict:
    stage, rel, lane_id = 'study-design', REL['index'], lane['id']
    st = src.status('index')
    if st == 'missing':
        return node(stage, 'pending', summary='尚無 plan（無 index.yaml）',
                    evidence=[ev('value', '檔案不存在', rel)])
    if st == 'broken':
        return _unknown(stage, rel)
    active, superseded, others = _sq_plans(src, lane_id)
    history = []
    for p in superseded:
        pid = _text(p.get('plan_id'))
        rb = _text(p.get('replaced_by'))
        history.append({'date': _date(p.get('confirmed_at')),
                        'summary': f'{pid} 封版，已被 {rb} 取代' if rb else f'{pid} 封版，已被取代'})
    if active is not None:
        pid = _text(active.get('plan_id'))
        ver = _plan_version(pid, len(superseded) + 1)
        evidence = [
            ev('path', active.get('path') or f'analysis/plans/{pid}.yaml', f'{rel}#plans[{pid}].path'),
            ev('hash', active.get('content_hash'), f'{rel}#plans[{pid}].content_hash'),
            ev('value', f'status={_text(active.get("status")) or "active"}', f'{rel}#plans[{pid}].status'),
        ]
        return node(stage, 'done', active.get('confirmed_at'), f'plan {pid} 封版（第 {ver} 版）', evidence, history)
    if superseded:
        latest = max((_date(p.get('confirmed_at')) for p in superseded), default='')
        ids = '、'.join(_text(p.get('plan_id')) for p in superseded)
        return node(stage, 'expired', latest, f'{len(superseded)} 版皆已被取代，無 active plan（{ids}）',
                    [ev('value', ids, f'{rel}#plans[sq={lane_id}].status')], history)
    if others:
        ids = '、'.join(_text(p.get('plan_id')) for p in others)
        return node(stage, 'pending', summary=f'plan 尚未封版（{ids}）',
                    evidence=[ev('value', ids, f'{rel}#plans[sq={lane_id}].status')])
    return node(stage, 'pending', summary='尚無 plan', evidence=[ev('value', f'plans[] 無 sq={lane_id}', f'{rel}#plans[]')])


def judge_analyze_data(src: Sources, lane: dict) -> dict:
    stage, rel, lane_id = 'analyze-data', REL['results'], lane['id']
    st = src.status('results')
    if st == 'missing':
        return node(stage, 'pending', summary='尚無結果鍵（無 results.json）', evidence=[ev('value', '檔案不存在', rel)])
    if st == 'broken':
        return _unknown(stage, rel)
    index_ok = src.status('index') == 'ok'
    active, superseded, others = _sq_plans(src, lane_id) if index_ok else (None, [], [])
    active_ids = {_text(active.get('plan_id'))} if active else set()
    superseded_ids = {_text(p.get('plan_id')) for p in superseded}
    listed_ids = active_ids | superseded_ids | {_text(p.get('plan_id')) for p in others}
    pat = re.compile('(' + '|'.join(re.escape(x) for x in [lane_id] + src.alias_olds(lane_id)) + r')-v\d+$')
    keys_active: list[str] = []
    keys_superseded: list[str] = []
    keys_orphan: list[str] = []
    entries: dict[str, dict] = {}
    for key, obj in src.data('results').items():
        if not isinstance(obj, dict):
            continue
        pid = _text(obj.get('plan_id'))
        if not pid:
            continue
        if pid in active_ids:
            keys_active.append(str(key))
        elif pid in superseded_ids:
            keys_superseded.append(str(key))
        elif pid not in listed_ids and pat.fullmatch(pid):
            keys_orphan.append(str(key))
        else:
            continue
        entries[str(key)] = obj

    def collect(keys: list[str]) -> tuple[list[dict], str]:
        evidence: list[dict] = []
        seen_run: dict[str, str] = {}
        seen_script: set[str] = set()
        seen_fp: set[str] = set()
        for k in keys:
            obj = entries[k]
            run_id = _text(obj.get('run_id'))
            if run_id and run_id not in seen_run:
                seen_run[run_id] = k
                evidence.append(ev('run', run_id, f'{rel}#{k}.run_id'))
            script = _text(obj.get('script'))
            if script and script not in seen_script:
                seen_script.add(script)
                evidence.append(ev('path', script, f'{rel}#{k}.script'))
            fp = _text(obj.get('data_fingerprint'))
            if fp and fp not in seen_fp:
                seen_fp.add(fp)
                evidence.append(ev('hash', fp, f'{rel}#{k}.data_fingerprint'))
        dates = [m.group(0) for r in seen_run for m in [DATE_RE.search(r)] if m]
        date = max(dates) if dates else ''
        if seen_run:
            note = f'日期取自 run_id（{date}）' if date else 'run_id 無 YYYY-MM-DD 日期，date 留空'
            evidence.append(ev('value', note, f'{rel}#<key>.run_id'))
        return evidence, date

    if keys_active:
        evidence, date = collect(keys_active)
        runs = '、'.join(dict.fromkeys(_text(entries[k].get('run_id')) or 'unknown' for k in keys_active))
        return node(stage, 'done', date, f'{len(keys_active)} 個結果鍵，run {runs}', evidence)
    if keys_superseded:
        evidence, date = collect(keys_superseded)
        pids = '、'.join(dict.fromkeys(_text(entries[k].get('plan_id')) for k in keys_superseded))
        return node(stage, 'expired', date, f'{len(keys_superseded)} 個結果鍵只掛在已取代的 plan（{pids}）', evidence)
    if keys_orphan:
        evidence, date = collect(keys_orphan)
        pids = '、'.join(dict.fromkeys(_text(entries[k].get('plan_id')) for k in keys_orphan))
        why = 'index.yaml 無法解析或不存在' if not index_ok else 'index.yaml 未登錄'
        return node(stage, 'unknown', date, f'{len(keys_orphan)} 個結果鍵掛在 {pids}，但 {why}，無法判定 plan 歸屬', evidence)
    return node(stage, 'pending', summary='尚無結果鍵', evidence=[ev('value', f'無 plan_id 屬 {lane_id} 的鍵', f'{rel}#<key>.plan_id')])


def judge_validate_results(src: Sources, lane: dict) -> dict:
    stage, rel, lane_id = 'validate-results', REL['validation'], lane['id']
    st = src.status('validation')
    if st == 'missing':
        return node(stage, 'pending', summary='尚無驗證（無 validation.yaml）', evidence=[ev('value', '檔案不存在', rel)])
    if st == 'broken':
        return _unknown(stage, rel)
    doc = src.data('validation')
    top_status = _text(doc.get('status')).lower()
    completed_at = _date(doc.get('completed_at'))
    expired_at = _date(doc.get('expired_at'))
    items = [it for it in _list(doc.get('items')) if isinstance(it, dict) and src.alias_of(_text(it.get('sq'))) == lane_id]
    if not items:
        return node(stage, 'pending', summary='無 validation item',
                    evidence=[ev('value', f'items[] 無 sq={lane_id}', f'{rel}#items[]'),
                              ev('value', f'頂層 status={top_status or "unknown"}', f'{rel}#status')])
    statuses = list(dict.fromkeys(_text(it.get('status')).lower() or 'unknown' for it in items))
    label = '／'.join(statuses)
    evidence = [
        ev('hash', doc.get('results_fingerprint'), f'{rel}#results_fingerprint'),
        ev('hash', doc.get('source_fingerprint'), f'{rel}#source_fingerprint'),
        ev('path', doc.get('report'), f'{rel}#report'),
        ev('value', f'頂層 status={top_status or "unknown"}', f'{rel}#status'),
    ]
    for it in items:
        iid = _text(it.get('id')) or '?'
        evidence.append(ev('value', f'{iid}: {_text(it.get("status")) or "unknown"}（plan {_text(it.get("plan_id")) or "unknown"}）',
                           f'{rel}#items[{iid}].status'))
    if top_status == 'expired':
        summary = f'驗證 {label}，{completed_at or "unknown"} 完成，{expired_at or "unknown"} 過期'
        return node(stage, 'expired', completed_at, summary, evidence)
    if any(s == 'fail' for s in statuses):
        return node(stage, 'blocked', completed_at, f'驗證 {label}（{len(items)} 項），{completed_at or "unknown"} 完成', evidence)
    if all(s in ('pass', 'qualified') for s in statuses):
        return node(stage, 'done', completed_at, f'驗證 {label}（{len(items)} 項），{completed_at or "unknown"} 完成', evidence)
    return node(stage, 'unknown', completed_at, f'驗證 item status 不在 pass／qualified／fail 之內（{label}）', evidence)


def judge_evaluate(src: Sources, lane: dict) -> dict:
    stage, rel, lane_id = 'evaluate', REL['project'], lane['id']
    goal_path = f'{rel}#goals.{lane["goal_list"]}[{lane_id}]'
    status = _text(lane.get('status')).lower()
    reason = _clip(_text(lane.get('status_reason')), SUMMARY_MAX)
    evidence = [ev('value', f'status={status or "（缺）"}', f'{goal_path}.status')]
    for name in src.glob('evaluations', '*.md'):
        if lane_id in name or any(old in name for old in src.alias_olds(lane_id)):
            evidence.append(ev('path', f'evaluations/{name}', 'evaluations/'))
    if status == 'addressed':
        return node(stage, 'done', summary='addressed' + (f'：{reason}' if reason else ''), evidence=evidence)
    if status == 'blocked':
        return node(stage, 'blocked', summary='blocked' + (f'：{reason}' if reason else ''), evidence=evidence)
    if status == 'dropped':
        return node(stage, 'blocked', summary='dropped' + (f'：{reason}' if reason else ''), evidence=evidence)
    if status in ('', 'open'):
        return node(stage, 'pending', summary='open' if status else 'status 缺，視為 open', evidence=evidence)
    return node(stage, 'unknown', summary=f'status 值不在 open／addressed／blocked／dropped 之內（{status}）', evidence=evidence)


def judge_interpret_results(src: Sources, lane: dict) -> dict:
    stage, rel, lane_id = 'interpret-results', REL['claims'], lane['id']
    st = src.status('claims')
    if st == 'missing':
        return node(stage, 'pending', summary='尚無主張（無 claims.yaml）', evidence=[ev('value', '檔案不存在', rel)])
    if st == 'broken':
        return _unknown(stage, rel)
    doc = src.data('claims')
    claims = [c for c in _list(doc.get('claims')) if isinstance(c, dict) and src.alias_of(_text(c.get('sq'))) == lane_id]
    if not claims:
        return node(stage, 'pending', summary='無主張', evidence=[ev('value', f'claims[] 無 sq={lane_id}', f'{rel}#claims[]')])
    state_claims = _dict(_get(src.data('project'), 'state', 'claims'))
    version = _text(state_claims.get('version')) or _text(doc.get('version')) or 'unknown'
    confirmed = state_claims.get('confirmed') if 'confirmed' in state_claims else doc.get('confirmed')
    confirmed_s = 'unknown' if confirmed is None else str(bool(confirmed)).lower()
    evidence = [ev('path', rel, rel),
                ev('value', f'version={version}', f'{REL["project"]}#state.claims.version'),
                ev('value', f'confirmed={confirmed_s}', f'{REL["project"]}#state.claims.confirmed')]
    for c in claims:
        cid = _text(c.get('id')) or '?'
        evidence.append(ev('value', f'{cid}: {_clip(_text(c.get("claim")), 60)}', f'{rel}#claims[{cid}].sq'))
    return node(stage, 'done', summary=f'{len(claims)} 條主張（claims v{version}，confirmed={confirmed_s}）', evidence=evidence)


def judge_claim_audit(src: Sources, lane: dict) -> dict:
    stage, rel = 'claim-audit', REL['claim_audit']
    audit = _dict(_get(src.data('project'), 'state', 'claim_audit'))
    result = _text(audit.get('result')).lower()
    exists = src.exists(rel)
    evidence = [ev('value', f'result={result or "（空）"}', f'{REL["project"]}#state.claim_audit.result'),
                ev('value', '檔案存在' if exists else '檔案不存在', rel)]
    if exists and result:
        evidence.append(ev('path', rel, rel))
        if _text(audit.get('report')):
            evidence.append(ev('path', audit.get('report'), f'{REL["project"]}#state.claim_audit.report'))
        note = f'專案級主張審查 {result}，套用到本問題'
        return node(stage, 'done' if result == 'pass' else 'blocked', audit.get('at'), note, evidence)
    return node(stage, 'pending', summary='尚無主張審查', evidence=evidence)


SQ_JUDGES = {
    'study-design': judge_study_design,
    'analyze-data': judge_analyze_data,
    'validate-results': judge_validate_results,
    'evaluate': judge_evaluate,
    'interpret-results': judge_interpret_results,
    'claim-audit': judge_claim_audit,
}


# ---------- 專案層泳道判定 ----------

def _state(src: Sources, *keys):
    return _get(src.data('project'), 'state', *keys)


def judge_project_init(src: Sources, lane: dict) -> dict:
    stage, rel = 'project-init', REL['project']
    st = src.status('project')
    if st == 'missing':
        return node(stage, 'pending', summary='無 project.yaml', evidence=[ev('value', '檔案不存在', rel)])
    if st == 'broken':
        return _unknown(stage, rel)
    dates = []
    ids = []
    if src.status('decisions') == 'ok':
        for d in _list(src.data('decisions').get('decisions')):
            if isinstance(d, dict) and _text(d.get('stage')) == 'project-init':
                dd = _date(d.get('date'))
                if dd:
                    dates.append(dd)
                    ids.append(_text(d.get('id')) or '?')
    date = min(dates) if dates else ''
    evidence = [ev('path', rel, rel)]
    if date:
        evidence.append(ev('value', f'最早 project-init 決策 {ids[dates.index(date)]}（{date}）', f'{REL["decisions"]}#decisions[stage=project-init].date'))
    title = _text(_get(src.data('project'), 'project', 'title_zh')) or _text(_get(src.data('project'), 'project', 'title_en'))
    return node(stage, 'done', date, f'project.yaml 已建立' + (f'：{_clip(title, 40)}' if title else ''), evidence)


def judge_methodology_router(src: Sources, lane: dict) -> dict:
    stage, rel = 'methodology-router', REL['route']
    st = src.status('route')
    meth_state = _dict(_state(src, 'methodology'))
    meth_top = _dict(_get(src.data('project'), 'methodology'))
    if st == 'broken':
        return _unknown(stage, rel)
    if st == 'missing' and not _text(meth_state.get('route')):
        return node(stage, 'pending', summary='尚無 route（無 route.yaml）', evidence=[ev('value', '檔案不存在', rel)])
    route = src.data('route') if st == 'ok' else {}
    name = _text(meth_state.get('route')) or _text(route.get('primary')) or _text(meth_top.get('primary')) or 'unknown'
    candidates = (
        (meth_state.get('at'), f'{REL["project"]}#state.methodology.at'),
        (meth_top.get('routed_at'), f'{REL["project"]}#methodology.routed_at'),
        (route.get('routed_at'), f'{rel}#routed_at'),
        (route.get('confirmed_at'), f'{rel}#confirmed_at'),
        (route.get('at'), f'{rel}#at'),
    )
    date, date_src = '', ''
    for value, source in candidates:
        if _date(value):
            date, date_src = _date(value), source
            break
    evidence = [ev('path', rel, rel)] if st == 'ok' else [ev('value', '檔案不存在，依 state.methodology 判定', rel)]
    evidence.append(ev('value', f'route={name}', f'{REL["project"]}#state.methodology.route' if _text(meth_state.get('route')) else f'{rel}#primary'))
    if date:
        evidence.append(ev('value', f'date 取自 {date_src}', date_src))
    confirmed = route.get('confirmed') if st == 'ok' else meth_top.get('confirmed')
    if confirmed is not None:
        evidence.append(ev('value', f'confirmed={str(bool(confirmed)).lower()}', f'{rel}#confirmed' if st == 'ok' else f'{REL["project"]}#methodology.confirmed'))
    return node(stage, 'done', date, f'route {name}', evidence)


def _state_or_file(src: Sources, stage: str, state_keys: tuple, state_field: str, rel: str,
                   label: str) -> dict:
    """state.<keys>.<field> 非空 → done（date=at）；否則 rel 檔存在 → done；否則 pending。"""
    block = _dict(_state(src, *state_keys))
    value = block.get(state_field)
    state_path = f'{REL["project"]}#state.{".".join(state_keys)}.{state_field}'
    if isinstance(value, dict):
        nonempty = bool(value)
        shown = _text(value.get('result')) or f'{len(value)} 欄'
    else:
        nonempty = bool(_text(value))
        shown = _text(value)
    if nonempty:
        evidence = [ev('value', f'{state_field}={shown}', state_path)]
        if isinstance(value, dict) and _text(value.get('report')):
            evidence.append(ev('path', value.get('report'), f'{state_path}.report'))
        elif _text(block.get('report')):
            evidence.append(ev('path', block.get('report'), state_path.rsplit('.', 1)[0] + '.report'))
        at = (value.get('at') if isinstance(value, dict) else None) or block.get('at')
        return node(stage, 'done', at, f'{label} {shown}', evidence)
    if src.exists(rel):
        return node(stage, 'done', summary=f'{label}（{rel} 存在，state 未記）', evidence=[ev('path', rel, rel), ev('value', 'state 為空', state_path)])
    return node(stage, 'pending', summary=f'尚無{label}', evidence=[ev('value', 'state 為空', state_path), ev('value', '檔案不存在', rel)])


def judge_integrity_check(src: Sources, lane: dict) -> dict:
    return _state_or_file(src, 'integrity-check', ('integrity',), 'prestudy', REL['register'], '完整性檢查 prestudy')


def judge_data_audit(src: Sources, lane: dict) -> dict:
    return _state_or_file(src, 'data-audit', ('data_audit',), 'result', REL['data_audit'], '資料稽核')


def judge_lit_review(src: Sources, lane: dict) -> dict:
    stage = 'lit-review'
    lit = _dict(_state(src, 'literature'))
    updated = _date(lit.get('updated_at'))
    state_path = f'{REL["project"]}#state.literature.updated_at'
    if updated:
        mode = _text(lit.get('mode'))
        return node(stage, 'done', updated, f'文獻回顧 {updated}' + (f'（{mode}）' if mode else ''),
                    [ev('value', f'updated_at={updated}', state_path)])
    files = [f'literature/{n}' for n in src.glob('literature', 'references.bib')]
    files += [f'literature/{n}' for n in src.glob('literature', '*matrix*')]
    if files:
        return node(stage, 'done', summary=f'文獻回顧（{"、".join(files)} 存在，state 未記）',
                    evidence=[ev('path', f, 'literature/') for f in files] + [ev('value', 'state 為空', state_path)])
    return node(stage, 'pending', summary='尚無文獻回顧', evidence=[ev('value', 'state 為空', state_path), ev('value', '無 references.bib／matrix', 'literature/')])


def judge_evidence_synthesis(src: Sources, lane: dict) -> dict:
    return _state_or_file(src, 'evidence-synthesis', ('evidence_synthesis',), 'result', REL['evidence_synthesis'], '證據綜整')


def judge_analyze_data_rerun(src: Sources, lane: dict) -> dict:
    stage = 'analyze-data:rerun'
    rerun = _state(src, 'analysis', 'rerun')
    base = f'{REL["project"]}#state.analysis.rerun'
    if not isinstance(rerun, dict) or not rerun:
        return node(stage, 'pending', summary='尚無 clean rerun', evidence=[ev('value', 'state.analysis.rerun 為空', base)])
    result = _text(rerun.get('result')).lower()
    evidence = [ev('value', f'result={result or "（空）"}', f'{base}.result')]
    for fld in ('fingerprint', 'input_fingerprint', 'results_fingerprint'):
        if _text(rerun.get(fld)):
            evidence.append(ev('hash', rerun.get(fld), f'{base}.{fld}'))
    if _text(rerun.get('report')):
        evidence.append(ev('path', rerun.get('report'), f'{base}.report'))
    mode = _text(rerun.get('mode'))
    if result == 'pass':
        return node(stage, 'done', rerun.get('at'), f'clean rerun pass' + (f'（{mode}）' if mode else ''), evidence)
    if result == 'waived':
        return node(stage, 'done', rerun.get('at'), 'clean rerun waived（豁免，未實跑）', evidence)
    return node(stage, 'blocked', rerun.get('at'), f'clean rerun {result or "結果缺"}', evidence)


def judge_evaluate_full(src: Sources, lane: dict) -> dict:
    stage = 'evaluate:full'
    full = _dict(_state(src, 'last_full_evaluation'))
    base = f'{REL["project"]}#state.last_full_evaluation'
    result = _text(full.get('result')).lower()
    fid = _text(full.get('id'))
    evidence = [ev('value', f'result={result or "（空）"}', f'{base}.result')]
    if fid:
        evidence.append(ev('value', f'id={fid}', f'{base}.id'))
    for name in src.glob('evaluations', '*.md'):
        if 'full' in name or 'goalfit' in name:
            evidence.append(ev('path', f'evaluations/{name}', 'evaluations/'))
    label = f'整體評估 {fid or "?"} {result}'.replace('  ', ' ')
    if result == 'pass':
        return node(stage, 'done', summary=label, evidence=evidence)
    if result == 'fail':
        return node(stage, 'blocked', summary=label, evidence=evidence)
    if result:
        return node(stage, 'unknown', summary=f'整體評估 result 不在 pass／fail 之內（{result}）', evidence=evidence)
    return node(stage, 'pending', summary='尚無整體評估', evidence=evidence)


def judge_figure_design(src: Sources, lane: dict) -> dict:
    stage, rel = 'figure-design', REL['manifest']
    st = src.status('manifest')
    if st == 'missing':
        return node(stage, 'pending', summary='尚無圖表 manifest', evidence=[ev('value', '檔案不存在', rel)])
    if st == 'broken':
        return _unknown(stage, rel)
    doc = src.data('manifest')
    figs = doc.get('figures')
    if isinstance(figs, list):
        n = len(figs)
    elif isinstance(figs, dict):
        n = len(figs)
    else:
        n = len([k for k in doc if not str(k).startswith('_')])
    return node(stage, 'done', summary=f'圖表 manifest {n} 筆', evidence=[ev('path', rel, rel), ev('value', f'{n} 筆', f'{rel}#figures')])


def _max_version(names: list[str]) -> str:
    best, best_n = '', -1
    for n in names:
        m = re.fullmatch(r'v(\d+)\.md', n)
        if m and int(m.group(1)) > best_n:
            best, best_n = f'v{m.group(1)}', int(m.group(1))
    return best


def judge_write_manuscript(src: Sources, lane: dict) -> dict:
    stage = 'write-manuscript'
    latest = _text(_state(src, 'zh_latest'))
    state_path = f'{REL["project"]}#state.zh_latest'
    if latest:
        return node(stage, 'done', summary=f'中文稿 {latest}', evidence=[ev('value', f'zh_latest={latest}', state_path)])
    names = src.glob('manuscript/zh', 'v*.md')
    ver = _max_version(names)
    if ver:
        return node(stage, 'done', summary=f'中文稿 {ver}（依 manuscript/zh/ 檔名，state 未記）',
                    evidence=[ev('path', f'manuscript/zh/{ver}.md', 'manuscript/zh/'), ev('value', 'state 為空', state_path)])
    return node(stage, 'pending', summary='尚無中文稿', evidence=[ev('value', 'state 為空', state_path), ev('value', '無 v*.md', 'manuscript/zh/')])


def judge_write_supplementary(src: Sources, lane: dict) -> dict:
    stage = 'write-supplementary'
    latest = _text(_state(src, 'si_latest'))
    state_path = f'{REL["project"]}#state.si_latest'
    if latest:
        return node(stage, 'done', summary=f'補充材料 {latest}', evidence=[ev('value', f'si_latest={latest}', state_path)])
    return node(stage, 'pending', summary='尚無補充材料', evidence=[ev('value', 'state 為空', state_path)])


def judge_check_consistency(src: Sources, lane: dict) -> dict:
    stage = 'check-consistency'
    lc = _dict(_state(src, 'last_consistency'))
    base = f'{REL["project"]}#state.last_consistency'
    result = _text(lc.get('result')).lower()
    if not result:
        return node(stage, 'pending', summary='尚無一致性檢核', evidence=[ev('value', 'result 為空', f'{base}.result')])
    evidence = [ev('value', f'result={result}', f'{base}.result')]
    for fld in ('version', 'language', 'si'):
        if _text(lc.get(fld)):
            evidence.append(ev('value', f'{fld}={_text(lc.get(fld))}', f'{base}.{fld}'))
    if _text(lc.get('gate_fingerprint')):
        evidence.append(ev('hash', lc.get('gate_fingerprint'), f'{base}.gate_fingerprint'))
    if _text(lc.get('report')):
        evidence.append(ev('path', lc.get('report'), f'{base}.report'))
    label = f'一致性檢核 {result}（{_text(lc.get("language")) or "?"}/{_text(lc.get("version")) or "?"}）'
    if result == 'pass':
        return node(stage, 'done', lc.get('at'), label, evidence)
    if result == 'fail':
        return node(stage, 'blocked', lc.get('at'), label, evidence)
    return node(stage, 'unknown', lc.get('at'), f'一致性檢核 result 不在 pass／fail 之內（{result}）', evidence)


def judge_peer_review(src: Sources, lane: dict) -> dict:
    stage = 'peer-review'
    review = _dict(_state(src, 'review'))
    base = f'{REL["project"]}#state.review'
    try:
        rnd = int(review.get('round') or 0)
    except (TypeError, ValueError):
        rnd = 0
    if rnd > 0:
        decision = _text(review.get('decision')) or 'unknown'
        evidence = [ev('value', f'round={rnd}', f'{base}.round'), ev('value', f'decision={decision}', f'{base}.decision')]
        if review.get('converged') is not None:
            evidence.append(ev('value', f'converged={str(bool(review.get("converged"))).lower()}', f'{base}.converged'))
        return node(stage, 'done', summary=f'第 {rnd} 輪，{decision}', evidence=evidence)
    return node(stage, 'pending', summary='尚無審稿輪', evidence=[ev('value', 'round=0', f'{base}.round')])


def judge_revise(src: Sources, lane: dict) -> dict:
    stage, rel = 'revise', REL['ledger']
    st = src.status('ledger')
    if st == 'missing':
        return node(stage, 'pending', summary='尚無 issue ledger', evidence=[ev('value', '檔案不存在', rel)])
    if st == 'broken':
        return _unknown(stage, rel)
    issues = _list(src.data('ledger').get('issues'))
    return node(stage, 'done', summary=f'issue ledger {len(issues)} 筆', evidence=[ev('path', rel, rel), ev('value', f'{len(issues)} 筆', f'{rel}#issues')])


def judge_translate_en(src: Sources, lane: dict) -> dict:
    stage = 'translate-en'
    en = _dict(_state(src, 'en_final'))
    ver = _text(en.get('version'))
    state_path = f'{REL["project"]}#state.en_final.version'
    if ver:
        evidence = [ev('value', f'version={ver}', state_path)]
        if _text(en.get('source')):
            evidence.append(ev('value', f'source={_text(en.get("source"))}', f'{REL["project"]}#state.en_final.source'))
        return node(stage, 'done', en.get('confirmed_at'), f'英文稿 {ver}', evidence)
    names = src.glob('manuscript/en', 'v*.md')
    fver = _max_version(names)
    if fver:
        return node(stage, 'done', summary=f'英文稿 {fver}（依 manuscript/en/ 檔名，state 未記）',
                    evidence=[ev('path', f'manuscript/en/{fver}.md', 'manuscript/en/'), ev('value', 'state 為空', state_path)])
    return node(stage, 'pending', summary='尚無英文稿', evidence=[ev('value', 'state 為空', state_path), ev('value', '無 v*.md', 'manuscript/en/')])


def _submission(src: Sources, stage: str, field: str, label: str) -> dict:
    block = _state(src, 'submission', field)
    base = f'{REL["project"]}#state.submission.{field}'
    if not isinstance(block, dict) or not block:
        return node(stage, 'pending', summary=f'尚無{label}', evidence=[ev('value', f'{field} 為空', base)])
    evidence = [ev('value', f'{len(block)} 欄', base)]
    for fld in ('result', 'journal', 'format', 'manuscript'):
        if _text(block.get(fld)):
            evidence.append(ev('value', f'{fld}={_text(block.get(fld))}', f'{base}.{fld}'))
    files = block.get('files')
    if isinstance(files, list):
        for f in files:
            evidence.append(ev('path', f, f'{base}.files'))
    shown = _text(block.get('result')) or _text(block.get('format')) or ''
    return node(stage, 'done', block.get('at'), f'{label}' + (f' {shown}' if shown else ''), evidence)


def judge_submission_prep(src: Sources, lane: dict) -> dict:
    return _submission(src, 'submission-prep', 'prep', '投稿準備')


def judge_typeset(src: Sources, lane: dict) -> dict:
    return _submission(src, 'typeset', 'build', '排版')


PROJECT_JUDGES = {
    'project-init': judge_project_init,
    'methodology-router': judge_methodology_router,
    'integrity-check': judge_integrity_check,
    'data-audit': judge_data_audit,
    'lit-review': judge_lit_review,
    'evidence-synthesis': judge_evidence_synthesis,
    'analyze-data:rerun': judge_analyze_data_rerun,
    'evaluate:full': judge_evaluate_full,
    'figure-design': judge_figure_design,
    'write-manuscript': judge_write_manuscript,
    'write-supplementary': judge_write_supplementary,
    'check-consistency': judge_check_consistency,
    'peer-review': judge_peer_review,
    'revise': judge_revise,
    'translate-en': judge_translate_en,
    'submission-prep': judge_submission_prep,
    'typeset': judge_typeset,
}


# ---------- 泳道與註記 ----------

def build_lanes(src: Sources) -> list[dict]:
    lanes: list[dict] = [{'id': 'project', 'kind': 'project', 'label': '專案層', 'question': '',
                          'status': '', 'status_reason': '', 'goal_list': '', 'nodes': [], 'annotations': []}]
    proj = src.data('project') if src.status('project') == 'ok' else {}
    goals = _dict(proj.get('goals'))
    if not _list(goals.get('sub_questions')) and not _list(goals.get('appendix_questions')):
        where = 'project.yaml 不存在' if src.status('project') == 'missing' else 'project.yaml 無 goals'
        src.warnings.append(f'{where}，只有專案層泳道')
    for list_name, kind in (('sub_questions', 'sq'), ('appendix_questions', 'aq')):
        for i, q in enumerate(_list(goals.get(list_name))):
            if not isinstance(q, dict):
                q = {}
            lane_id = _text(q.get('id'))
            if not lane_id:
                lane_id = f'{list_name}[{i}]'
                src.warnings.append(f'goals.{list_name}[{i}] 無 id，以 {lane_id} 作泳道名')
            lanes.append({
                'id': lane_id, 'kind': kind, 'label': lane_id, 'question': _text(q.get('question')),
                'status': _text(q.get('status')), 'status_reason': _text(q.get('status_reason')),
                'goal_list': list_name, 'nodes': [], 'annotations': [],
            })
    return lanes


def judge_lane(src: Sources, lane: dict, next_stage: str) -> None:
    if lane['kind'] == 'project':
        for stage_id, _label in PROJECT_STAGES:
            n = PROJECT_JUDGES[stage_id](src, lane)
            n['current'] = bool(next_stage) and (stage_id == next_stage or stage_id.split(':')[0] == next_stage)
            lane['nodes'].append(n)
    else:
        for stage_id, _label in SQ_STAGES:
            lane['nodes'].append(SQ_JUDGES[stage_id](src, lane))


def attach_annotations(src: Sources, lanes: list[dict]) -> None:
    st = src.status('decisions')
    if st == 'missing':
        src.infos.append('decisions.yaml 不存在，決策註記為空')
        return
    if st == 'broken':
        return  # 已在 Sources 記 WARNING；註記留空
    by_id = {lane['id']: lane for lane in lanes}
    for i, d in enumerate(_list(src.data('decisions').get('decisions'))):
        if not isinstance(d, dict):
            src.warnings.append(f'decisions[{i}] 不是 mapping，略過註記')
            continue
        ann = {
            'id': _text(d.get('id')) or f'decisions[{i}]',
            'date': _date(d.get('date')),
            'stage': _text(d.get('stage')),
            'summary': _clip(_text(d.get('decision')), SUMMARY_MAX),
            'exec_issue': _text(d.get('exec_issue')),
            'method': _text(d.get('method')),
        }
        question = src.alias_of(_text(d.get('question')))
        targets: list[str] = []
        if question in by_id and question != 'project':
            targets = [question]
        elif question in ('', 'main'):
            targets = [t for t in dict.fromkeys(src.alias_of(_text(x)) for x in _list(d.get('links'))) if t in by_id and t != 'project']
        if not targets:
            targets = ['project']
        for t in targets:
            by_id[t]['annotations'].append(dict(ann))


# ---------- 關聯圖（graph IR） ----------

NODE_TYPES = (('question', '問題'), ('method', '方法'), ('validation', '驗證'), ('result', '結果'),
              ('figure', '圖表'), ('decision', '決策'), ('report', '報告'))  # 前六項的順序＝關聯圖欄序（主問題 q:main 另占最左一欄）；report（0.19.0）不另加欄、放圖表欄
COLUMN_TYPES = NODE_TYPES[:6]
MAIN_ID = 'q:main'
N_COLS = len(COLUMN_TYPES) + 1   # 欄 0＝主問題，欄 1..6＝question／method／validation／result／figure／decision
EDGE_TYPES = (('decomposes', '拆解為'), ('plans', '規劃'), ('supersedes', '取代'), ('sensitivity', '敏感性'),
              ('supplements', '敏感性對照'), ('validated_by', '驗證'), ('primary', '驗證（主要）'), ('robustness', '驗證（穩健性）'),
              ('produces', '產出'), ('depicts', '呈現於'), ('cites', '引為證據'), ('refers', '決策關聯'), ('supports', '支撐'),
              ('embedded_in', '嵌入報告'))
SUBTYPES = ('', 'primary', 'sensitivity_group', 'sensitivity', 'secondary', 'undeclared', 'supporting', 'secondary_group')
METHOD_SUBTYPES = ('primary', 'sensitivity_group', 'sensitivity')
RESULT_SUBTYPES = ('primary', 'secondary', 'undeclared', 'supporting', 'secondary_group')
SUB_INDENT = 24
# 縮排子節點與各自的縮排量（0.18.0：敏感性分析群縮一層在所屬 plan 之下、子分析再縮一層；次要結果與支撐結果在結果欄縮一層；
# 0.19.0：次要結果聚合節點 secondary_group 與次要結果同一層）；JS 端 indentOf() 同義
SUB_INDENT_OF = {'sensitivity_group': SUB_INDENT, 'sensitivity': 2 * SUB_INDENT, 'secondary': SUB_INDENT, 'supporting': SUB_INDENT,
                 'secondary_group': SUB_INDENT}
# 0.19.0 宣告粒度（使用者 2026-09-17 裁定，跨專案一致、無門檻、無專案設定）：節點粒度＝plan 的宣告粒度。outputs 逐條宣告的主要結果一條一個
# 節點；敏感性子分析 p:<pid>#R<k> 的 expected_keys 是該子分析的屬性、不是獨立宣告單位，所以有自有次要鍵（result_kind secondary、歸本 plan）
# 的子分析底下一個次要結果聚合節點 r:<pid>#R<k>#secondary（subtype secondary_group、parent＝子分析、鍵全列在 meta.keys），不看鍵數多寡；
# 沒宣告任何次要鍵的子分析沒有「次要結果」這個宣告單位，不建節點也不建邊（至多一個、有則 n_keys ≥ 1）；未宣告鍵維持逐鍵虛線節點
SECONDARY_SUFFIX = '#secondary'
SECONDARY_GROUP_LABEL = '次要結果'        # 多鍵時 label「次要結果 n 鍵」；1 鍵直接顯示鍵名
REPORT_ID = 'o:report'                   # 0.19.0 report.md 節點（type report、圖表欄最後一列、main 區帶、孤兒帶）
REPORT_REL = 'analysis/report.md'        # methodology adapter 沒有另外的 report 路徑欄位（0.19.0 查過七個 adapter），只認這一個
MD_IMG_RE = re.compile(r'!\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+"[^"]*")?\s*\)')
REPORT_UNCITED_BADGE = '報告未引用'      # role=main 且 report.md 存在但沒引用的圖表徽章
INDENTED_SUBTYPES = tuple(SUB_INDENT_OF)
L_EDGE_TYPES = ('sensitivity', 'supports')   # 父 → 子的 L 形線（共用垂直段）：plan → 群、群 → 子分析、主結果 → 支撐結果；JS 端 isL() 同義
# 區帶（由上而下）：main＝主結果鏈（主問題、SQ 及其計畫／驗證／結果／主圖、決策；SQ 的敏感性分析群、子分析與次要結果跟 plan 走）；
# ext＝Extended Data（圖表依 manifest role；0.20.0 起方法／結果／驗證也能放——由 analysis/extended-data.yaml opt-in，只有問題節點不能放，
# 使用者 2026-09-17 裁定）；supp＝補充（附錄問題及其一切、補充圖表）。0.18.0 起群不再固定在 supp
BANDS = ('main', 'ext', 'supp')
BAND_TITLE = {'main': 'Main ｜ 主結果', 'ext': 'Extended Data ｜ 延伸資料', 'supp': 'Supplementary ｜ 補充：附錄問題與補充圖表'}
# 0.20.0 extended-data.yaml 的三個清單 → 節點 id 前綴；每個非問題節點 meta.band_source ∈ {explicit, inherited:<來源節點 id>, derived}
ED_LISTS = (('plans', 'p:'), ('results', 'r:'), ('validation', 'v:'))
BAND_SOURCE_EXPLICIT, BAND_SOURCE_DERIVED, BAND_SOURCE_INHERITED = 'explicit', 'derived', 'inherited:'
CROSS_BAND_VISIBLE = ('decomposes', 'depicts')   # 可以跨區帶預設畫出的邊：主問題→AQ、結果→圖表（0.18.0 起沒有 supplements 邊）
SENSITIVITY_BADGE = '敏感性'   # 有敏感性分析群的 plan 節點徽章「敏感性 n」（與舊版數並列時「v2（1 舊版）｜敏感性 n」）
# manifest role → 圖表節點的區帶與徽章（小寫、去空白後比對）；缺或不認得 → 沿用推導規則（呈現的結果全在 supp 才 supp，否則 main）
FIGURE_ROLE_BAND = {'main': 'main', 'extended': 'ext', 'extended_data': 'ext', 'extended-data': 'ext', 'ed': 'ext',
                    'supplementary': 'supp', 'supp': 'supp', 'si': 'supp'}
FIGURE_ROLE_BADGE = {'main': '主圖', 'ext': '延伸', 'supp': '補充'}
GROUP_SUFFIX = '#S'
RESULT_KIND_ZH = {'primary': '主要', 'secondary': '次要', 'undeclared': '未宣告'}
SUPPORTING_BADGE = '支撐'   # 有 supports 的結果節點徽章；主結果徽章「支撐 n」
EDGE_STYLES = ('solid', 'dashed', 'thin')
NODE_PREFIX = {'question': 'q:', 'method': 'p:', 'validation': 'v:', 'result': 'r:', 'figure': 'f:', 'decision': 'd:', 'report': 'o:'}
GRAPH_COL = {t: i + 1 for i, (t, _) in enumerate(COLUMN_TYPES)}
GRAPH_COL['report'] = GRAPH_COL['figure']   # 0.19.0：report 節點放圖表欄（最後一列），不另加欄


def node_col(nid: str, ntype: str) -> int:
    """主問題獨占欄 0；其餘依 type：question 1、method 2、validation 3、result 4、figure 5（report 也在 5）、decision 6。"""
    return 0 if nid == MAIN_ID else GRAPH_COL[ntype]
NODE_W, NODE_H, COL_PITCH, ROW_GAP, GRAPH_PAD = 260, 36, 380, 48, 20   # COL_PITCH＝欄距（節點寬 260＋走道 120）；JS 端同名常數須同值
BAND_TITLE_H, BAND_GAP, BAND_TITLE_DY = 28, 40, 18   # 區帶標題列高、兩區帶間距、標題文字基線相對標題列頂的偏移；JS 端同名常數須同值
STRIP_GAP = ROW_GAP   # 0.18.1 問題帶：同一區帶內兩條問題帶之間的空隙（1 列高）；區帶標題列與第一條帶之間不另加；JS 端同名常數須同值
ORPHAN_STRIP = ''     # 找不到所屬問題的節點（孤兒）放該區帶最後一條問題帶，strip 為空字串
DOWNSTREAM_TYPES = ('plans', 'sensitivity', 'validated_by', 'primary', 'robustness', 'produces', 'depicts', 'cites', 'supports')
TABLE_ROWS_MAX = 200
EMBED_MAX_BYTES = 5 * 1024 * 1024
IMAGE_MIME = {'.svg': 'image/svg+xml', '.png': 'image/png'}
MD_MARK_RE = re.compile(r'\*{1,2}')
INBOX_KINDS = {'new_question': '新問題', 'new_analysis': '新分析', 'comment': '意見', 'reassign': '降階', 'promote': '升回主問題',
               'set_role': '圖表 role', 'move_plan': '搬方法', 'move_sensitivity': '搬敏感性子分析', 'reorder': '調順序', 'move_result': '搬結果',
               'nest_result': '掛到主結果下', 'demote_plan': '降為敏感性子分析', 'set_tier': 'Extended Data 歸屬', 'batch': '批次'}
INBOX_ACTION_KINDS = ('reassign', 'promote', 'set_role', 'move_plan', 'move_sensitivity', 'reorder', 'move_result', 'nest_result', 'demote_plan', 'set_tier', 'batch')   # 與 ssot_actions_common.ACTIONS 同序；set_tier（0.20.0）、demote_plan（0.18.0）、batch（0.17.0）
INBOX_STATUSES = ('pending', 'done', 'dismissed')
INBOX_FIELDS = ('id', 'at', 'kind', 'target', 'title', 'body', 'author', 'status', 'resolved_by', 'resolved_at', 'note')
DECISION_ID_RE = re.compile(r'D-\d{3}')
PLAN_PATH_RE = re.compile(r'^analysis/plans/([^/]+)\.ya?ml$')
META_MAX = 200
LABEL_MAX = 30
BIG = 10 ** 6
GOAL_STATE = {'addressed': 'done', 'blocked': 'blocked', 'dropped': 'blocked', 'open': 'pending', '': 'pending'}


class Graph:
    """節點以插入順序保存；邊以 (from, to, type) 去重；兩端節點都存在才建邊。"""

    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self._edge_keys: dict[tuple[str, str, str], dict] = {}

    def add_node(self, nid: str, ntype: str, label, title='', state: str = '', meta: dict | None = None,
                 source: str = '') -> dict:
        n = self.nodes.get(nid)
        if n is None:
            n = {'id': nid, 'type': ntype, 'label': _text(label), 'title': _text(title), 'state': state,
                 'meta': dict(meta or {}), 'source': source, 'x': 0, 'y': 0, 'col': node_col(nid, ntype),
                 'order': 0, 'collapsed': False, 'badge': '', 'subtype': '', 'parent': '', 'band': 'main', 'strip': ''}
            self.nodes[nid] = n
        return n

    def add_edge(self, a: str, b: str, etype: str, source: str, label: str = '', meta: dict | None = None,
                 visible: bool = True, style: str = 'solid') -> dict | None:
        """回傳邊（新建或既有）；兩端不存在回 None。同 (from, to, type) 再加時合併 label 與 meta，不畫第二條。"""
        if a not in self.nodes or b not in self.nodes:
            return None
        key = (a, b, etype)
        if key in self._edge_keys:
            e = self._edge_keys[key]
            if label and label not in e['label'].split('、'):
                e['label'] = '、'.join(x for x in (e['label'], label) if x)
            for k, v in (meta or {}).items():
                if k in e['meta'] and e['meta'][k] != v:
                    e['meta'][k] = f'{e["meta"][k]}；{v}'
                else:
                    e['meta'][k] = v
            return e
        e = {'from': a, 'to': b, 'type': etype, 'label': label, 'source': source, 'meta': dict(meta or {}),
             'default_visible': visible, 'style': style}
        self._edge_keys[key] = e
        self.edges.append(e)
        return e


def _plan_doc_meta(doc: dict | None) -> dict:
    if not doc:
        return {}
    out = {}
    for fld in ('timing', 'role', 'adapter'):
        if _text(doc.get(fld)):
            out[fld] = _text(doc.get(fld))
    if _text(doc.get('amendment_reason')):
        out['amendment_reason'] = _clip(_text(doc.get('amendment_reason')), META_MAX)
    pm = _dict(doc.get('primary_model'))
    if pm:
        text = '：'.join(x for x in (_text(pm.get('id')), _text(pm.get('method'))) if x)
        if text:
            out['primary_model'] = _clip(text, META_MAX)
    return out


def _extended_data_sets(src: Sources, g: 'Graph', agg_of_key: dict[str, str]) -> dict[str, set[str]]:
    """讀 analysis/extended-data.yaml（0.20.0；缺檔＝三個清單都空），回 {'p:': {...}, 'r:': {...}, 'v:': {...}} 的節點 id 集合。

    只收「放 ED 的」（opt-in）：plans＝plan id 或敏感性子分析 id（p:<pid>／p:<pid>#R<k>）、results＝主要或未宣告結果鍵、validation＝item id。
    不合規的一筆（清單不是 list、項目不是字串、id 不存在、寫了問題／圖表／群 #S／次要鍵／支撐結果鍵）→ src.warnings 一句、略過那一筆，不 hard fail；
    頂層不是 mapping 由 Sources 記「無法解析」並視同缺檔。"""
    out: dict[str, set[str]] = {prefix: set() for _name, prefix in ED_LISTS}
    if src.status('extended_data') != 'ok':
        return out
    doc = src.data('extended_data')
    rel = REL['extended_data']
    for name, prefix in ED_LISTS:
        raw = doc.get(name)
        if raw is None:
            continue
        if not isinstance(raw, list):
            src.warnings.append(f'{rel}#{name} 須為清單（實際 {type(raw).__name__}），整個清單略過')
            continue
        for i, item in enumerate(raw):
            if not isinstance(item, str) or not item.strip():
                src.warnings.append(f'{rel}#{name}[{i}] 不是非空字串，略過')
                continue
            sid = item.strip()
            nid = prefix + sid
            n = g.nodes.get(nid)
            why = ''
            if sid.startswith('q:') or f'q:{sid}' in g.nodes:
                why = '問題（SQ／AQ）不能放 Extended Data'
            elif sid.startswith('f:') or (prefix == 'r:' and n is None and f'f:{sid}' in g.nodes):
                why = '圖表的區帶由 analysis/figures/manifest.json 的 role 決定，不寫這裡'
            elif sid[:2] in NODE_PREFIX.values() and g.nodes.get(sid) is not None:
                why = f'清單裡寫 id 不寫前綴（{sid!r} 應寫成 {sid[2:]!r}）'
            elif n is None:
                if prefix == 'r:' and sid in agg_of_key:
                    why = f'{sid} 是次要鍵（只在 robustness expected_keys）：次要結果跟子分析走，請改列子分析 id'
                else:
                    why = {'p:': f'index.yaml／plan yaml 無 plan 或子分析 {sid}', 'r:': f'results.json 與各 plan 宣告都沒有結果鍵 {sid}',
                           'v:': f'validation.yaml 無 item {sid}'}[prefix]
            elif prefix == 'p:' and n.get('subtype') == 'sensitivity_group':
                why = '敏感性分析群跟 plan 走，不能單獨列（請列 plan 或個別子分析）'
            elif prefix == 'p:' and n.get('subtype') not in ('primary', 'sensitivity', ''):
                why = f'{sid} 不是 plan 或敏感性子分析'
            elif prefix == 'r:' and n.get('subtype') == 'supporting':
                why = f'{sid} 是 {_text(n["meta"].get("supports"))} 的支撐結果：支撐結果跟主結果走，請改列主結果'
            elif prefix == 'r:' and n.get('subtype') == 'secondary_group':
                why = '次要結果跟子分析走，請改列子分析 id'
            elif prefix == 'r:' and n.get('subtype') not in ('primary', 'undeclared'):
                why = f'{sid} 不是主要或未宣告結果'
            if why:
                src.warnings.append(f'{rel}#{name}[{i}]（{sid}）：{why}，略過')
                continue
            out[prefix].add(nid)
    return out


def build_graph(src: Sources, lanes: list[dict], embed_figures: bool = False) -> dict:
    g = Graph()
    proj = src.data('project') if src.status('project') == 'ok' else {}
    pmeta = _dict(proj.get('project'))
    g.add_node('q:main', 'question', 'main', _text(pmeta.get('research_question')), '', {},
               f'{REL["project"]}#project.research_question')
    goals = _dict(proj.get('goals'))
    question_order = ['q:main']
    q_band: dict[str, str] = {'q:main': 'main'}   # 問題 → 區帶：sub_questions 為 main、appendix_questions 為 supp
    cites: list[tuple[str, str, str]] = []
    for list_name in ('sub_questions', 'appendix_questions'):
        for i, q in enumerate(_list(goals.get(list_name))):
            q = q if isinstance(q, dict) else {}
            qid = _text(q.get('id')) or f'{list_name}[{i}]'
            status = _text(q.get('status')).lower()
            source = f'{REL["project"]}#goals.{list_name}[{qid}]'
            meta = {k: _text(q.get(k)) for k in ('status', 'role', 'why') if _text(q.get(k))}
            if _text(q.get('status_reason')):
                meta['status_reason'] = _clip(_text(q.get('status_reason')), META_MAX)
            g.add_node(f'q:{qid}', 'question', qid, _text(q.get('question')), GOAL_STATE.get(status, 'unknown'), meta, source)
            q_band.setdefault(f'q:{qid}', 'supp' if list_name == 'appendix_questions' else 'main')
            g.add_edge('q:main', f'q:{qid}', 'decomposes', source)
            question_order.append(f'q:{qid}')
            for link in _list(q.get('links')):
                link_s = _text(link)
                if link_s.startswith('results:') and len(link_s) > len('results:'):
                    cites.append((f'q:{qid}', link_s[len('results:'):], f'{source}.links'))

    # 問題 id 別名：舊 sq id → 現行問題（主問題降為附錄問題後，index 舊版／決策 links／validation item 仍寫舊 id）
    aliases = src.question_aliases()
    for old, new in aliases.items():
        qn = g.nodes.get(f'q:{new}')
        if qn is None:
            continue
        qn['meta'].setdefault('aliases', []).append(old)
    for new in dict.fromkeys(aliases.values()):
        qn = g.nodes.get(f'q:{new}')
        if qn is None:
            continue
        olds = qn['meta'].get('aliases', [])
        old_plans = [_text(p.get('plan_id')) for p in _list(_dict(src.data('index') if src.status('index') == 'ok' else {}).get('plans'))
                     if isinstance(p, dict) and _text(p.get('sq')) in olds]
        suffix = f'（原 {"／".join(olds)}；index 舊版 {"／".join(old_plans)}）' if old_plans else f'（原 {"／".join(olds)}）'
        qn['title'] = (qn['title'] + suffix) if qn['title'] else suffix.strip('（）')

    def ensure_question(sq: str, source: str) -> None:
        if f'q:{sq}' not in g.nodes:   # 解析不到別名的孤兒 sq 才造占位節點
            g.add_node(f'q:{sq}', 'question', sq, 'goals 無此問題（僅見於 plans index）', 'unknown', {}, source)
            question_order.append(f'q:{sq}')

    # 方法節點＝計畫版本（index.yaml 全部版本，含 superseded；superseded 收合）
    index = src.data('index') if src.status('index') == 'ok' else {}
    active_map = _dict(index.get('active'))
    entries = [p for p in _list(index.get('plans')) if isinstance(p, dict) and _text(p.get('plan_id'))]
    plan_docs: dict[str, dict | None] = {}
    plan_sq: dict[str, str] = {}
    plan_active: dict[str, bool] = {}
    replaced_targets: set[str] = set()
    decl_order: dict[tuple[str, str], int] = {}   # (plan_id, key) → 在該 plan outputs／robustness 的宣告序
    robustness_of: dict[tuple[str, str], str] = {}
    for entry in entries:
        pid = _text(entry.get('plan_id'))
        sq_raw = _text(entry.get('sq'))
        sq = src.alias_of(sq_raw)   # 舊 id 換成現行問題（例：SQ1 → AQ2）
        status = _text(entry.get('status')).lower()
        is_active = (_text(active_map.get(sq)) == pid) if _text(active_map.get(sq)) else status == 'active'
        rel = _text(entry.get('path')) or f'analysis/plans/{pid}.yaml'
        doc = src.yaml_rel(rel)
        plan_docs[pid] = doc
        plan_sq[pid] = sq
        plan_active[pid] = is_active
        meta = {'version': _plan_version(pid, 0), 'status': status or 'unknown',
                'confirmed_at': _date(entry.get('confirmed_at')), 'content_hash': _text(entry.get('content_hash')),
                'models': [], 'sq': sq}
        if sq_raw != sq:
            meta['sq_original'] = sq_raw
        meta.update(_plan_doc_meta(doc))
        n = g.add_node(f'p:{pid}', 'method', pid, _text(doc.get('question')) if doc else '',
                       'expired' if not is_active else 'pending', meta, f'{REL["index"]}#plans[{pid}]')
        n['collapsed'] = not is_active
        n['subtype'] = 'primary'
        if sq:
            ensure_question(sq, f'{REL["index"]}#plans[{pid}].sq')
            g.add_edge(f'q:{sq}', f'p:{pid}', 'plans', f'{REL["index"]}#plans[{pid}].sq', visible=is_active)
        if _text(entry.get('replaced_by')):
            replaced_targets.add(_text(entry.get('replaced_by')))
    for entry in entries:  # supersedes：index 的 replaced_by 為準；沒有才用 plan yaml 的 supersedes 反推
        pid = _text(entry.get('plan_id'))
        rb = _text(entry.get('replaced_by'))
        if rb:
            g.add_edge(f'p:{pid}', f'p:{rb}', 'supersedes', f'{REL["index"]}#plans[{pid}].replaced_by', visible=False, style='dashed')
        doc = plan_docs.get(pid)
        sup = _text(doc.get('supersedes')) if doc else ''
        if sup and pid not in replaced_targets and f'p:{sup}' in g.nodes:
            g.add_edge(f'p:{sup}', f'p:{pid}', 'supersedes', f'analysis/plans/{pid}.yaml#supersedes', visible=False, style='dashed')
    # 現行版的 superseded_versions 與徽章
    by_sq: dict[str, list[str]] = {}
    for pid, sq in plan_sq.items():
        by_sq.setdefault(sq, []).append(pid)
    for sq, pids in by_sq.items():
        olds = sorted((p for p in pids if not plan_active[p]), key=lambda p: (g.nodes[f'p:{p}']['meta']['version'], p))
        for pid in pids:
            if plan_active[pid]:
                n = g.nodes[f'p:{pid}']
                n['meta']['superseded_versions'] = olds
                if olds:
                    n['badge'] = f'v{n["meta"]["version"]}（{len(olds)} 舊版）'

    # results.json：主要／未宣告鍵逐鍵建節點；plan_id → produces；model_id 歸入方法節點 meta.models。
    # 0.19.0 宣告粒度：次要鍵（只在 robustness expected_keys）不再逐鍵建 r:<key>，改進宣告它的子分析底下唯一的聚合節點 r:<pid>#R<k>#secondary
    results = src.data('results') if src.status('results') == 'ok' else {}
    result_objs = {str(k): v for k, v in results.items() if isinstance(v, dict)}
    vdoc = src.data('validation') if src.status('validation') == 'ok' else {}
    vitems = [(i, it) for i, it in enumerate(_list(vdoc.get('items'))) if isinstance(it, dict)]
    validated_by: dict[str, list[str]] = {}   # 鍵 → 驗過它的 item（primary 或 robustness result_keys 都算）
    primary_keys: set[str] = set()
    vstatus: dict[str, str] = {}              # item id → status（小寫；聚合節點 state 用：有 fail 就 blocked）
    for i, item in vitems:
        vid = _text(item.get('id')) or f'items[{i}]'
        vstatus[vid] = _text(item.get('status')).lower()
        for key in _list(item.get('primary_results')):
            if _text(key):
                primary_keys.add(_text(key))
                if vid not in validated_by.setdefault(_text(key), []):
                    validated_by[_text(key)].append(vid)
        for rob in _list(item.get('robustness')):
            if isinstance(rob, dict):
                for key in _list(rob.get('result_keys')):
                    if _text(key) and vid not in validated_by.setdefault(_text(key), []):
                        validated_by[_text(key)].append(vid)

    def key_base_meta(key: str) -> dict:
        vids = validated_by.get(key, [])
        kind = 'primary' if key in primary_keys else ('robustness' if vids else '')
        return {'validated': bool(vids), 'validated_by': list(vids), 'validation_kind': kind, 'declared_by': []}

    agg_of_key: dict[str, str] = {}   # 次要鍵 → 所屬聚合節點 id（宣告它的子分析底下那一個）

    def result_node(key: str, source: str, missing_title: str, missing_state: str) -> str:
        """主要／未宣告鍵：逐鍵節點 r:<key>（既有就回它）；次要鍵：回所屬聚合節點 id（不建逐鍵節點）。"""
        if key in agg_of_key:
            return agg_of_key[key]
        nid = f'r:{key}'
        if nid in g.nodes:
            return nid
        obj = result_objs.get(key)
        base_meta = key_base_meta(key)
        if obj is not None:
            pid = _text(obj.get('plan_id'))
            pstate = g.nodes.get(f'p:{pid}', {}).get('state', '')
            meta = {k: _text(obj.get(k)) for k in ('plan_id', 'model_id', 'run_id', 'script', 'data_fingerprint', 'type')
                    if _text(obj.get(k))}
            meta.update(base_meta)
            if _text(obj.get('description')):
                meta['description'] = _text(obj.get('description'))
            if obj.get('type') == 'table' or isinstance(obj.get('columns'), list):
                cols = [_text(c) for c in _list(obj.get('columns'))]
                rows = [r for r in _list(obj.get('rows')) if isinstance(r, list)]
                meta['table'] = {'columns': cols, 'rows': rows[:TABLE_ROWS_MAX], 'n_rows': len(rows),
                                 'truncated': len(rows) > TABLE_ROWS_MAX}
            else:
                for fld in ('value', 'display', 'unit'):
                    if fld in obj:
                        meta[fld] = obj.get(fld)
            n = g.add_node(nid, 'result', key, _text(obj.get('description')) or key,
                           'expired' if pstate == 'expired' else 'done', meta, f'{REL["results"]}#{key}')
        else:
            g.add_node(nid, 'result', key, missing_title, missing_state, dict(base_meta), source)
        return nid

    def grouped_targets(keys: list[str], source: str, missing_title: str, missing_state: str) -> list[tuple[str, list[str]]]:
        """鍵清單 → [(目標節點 id, 落在該節點的鍵)]（依首見順序）：主要／未宣告鍵各自一個目標、次要鍵合併到所屬聚合節點。"""
        out: dict[str, list[str]] = {}
        for key in keys:
            out.setdefault(result_node(key, source, missing_title, missing_state), []).append(key)
        return list(out.items())

    out_index: dict[tuple[str, str], int] = {}          # (plan_id, key) → outputs 序
    rob_index: dict[tuple[str, str], tuple[int, int]] = {}   # (plan_id, key) → (子分析序, expected 序)
    sens_of: dict[str, list[str]] = {}                  # plan_id → 子節點 id（R 序）
    group_of: dict[str, str] = {}                       # plan_id → 敏感性分析群節點 id（p:<pid>#S；robustness[] 至少一項才建）
    supports_of: dict[tuple[str, str], str] = {}        # (plan_id, key) → 該 outputs 條目的 supports（主結果鍵；0.16.5）
    declared_by_of: dict[str, list[str]] = {}           # 鍵 → 宣告它的節點（p:<pid> 或 p:<pid>#R<k>，plan 序、outputs 先 robustness 後）
    sub_expected: dict[str, list[str]] = {}             # 子分析 id → expected_keys（宣告序）
    sub_item: dict[str, dict] = {}                      # 子分析 id → robustness 項（evidence_owned_by／evidence_keys 用）
    sub_ri: dict[str, int] = {}                         # 子分析 id → 在該 plan robustness[] 的序
    # 第一遍：只讀宣告、建群與子分析節點（結果節點等分類完再建，次要鍵才知道要進哪個聚合節點）
    for pid, doc in plan_docs.items():
        if not doc:
            continue
        active = plan_active[pid]
        for oi, item in enumerate(_list(doc.get('outputs'))):
            if isinstance(item, dict) and _text(item.get('key')):
                key = _text(item.get('key'))
                out_index.setdefault((pid, key), oi)
                decl_order.setdefault((pid, key), len(decl_order))
                if _text(item.get('supports')):
                    supports_of.setdefault((pid, key), _text(item.get('supports')))   # 0.16.5：本鍵是同 plan 另一鍵的支撐結果
                declared_by_of.setdefault(key, []).append(f'p:{pid}')
        rob_items = [(ri, item) for ri, item in enumerate(_list(doc.get('robustness'))) if isinstance(item, dict)]
        if rob_items:
            # 敏感性分析群（0.18.0 使用者裁定的畫法）：一個 plan 的全部 robustness 子分析收成一個群節點，縮排在所屬 plan 之下（縮一層）、
            # 帶跟 plan 走；plan → 群畫 L 形父子線，群 → 子分析再一層 L 形線；子分析再縮一層
            grp = f'p:{pid}{GROUP_SUFFIX}'
            group_of[pid] = grp
            gn = g.add_node(grp, 'method', f'{pid} 敏感性分析',
                            f'{pid} 的 robustness 子分析共 {len(rob_items)} 項；縮排在所屬 plan 之下、區帶跟 plan 走',
                            'expired' if not active else 'pending',
                            {'plan_id': pid, 'sensitivity_ids': []}, f'analysis/plans/{pid}.yaml#robustness')
            gn['subtype'] = 'sensitivity_group'
            gn['parent'] = f'p:{pid}'
            gn['collapsed'] = not active
            gn['band'] = ''   # 下面的區帶指派：跟 plan
            gn['badge'] = f'{len(rob_items)} 項'
            g.add_edge(f'p:{pid}', grp, 'sensitivity', f'analysis/plans/{pid}.yaml#robustness', '敏感性', visible=active)
        for ri, item in rob_items:
            rid = _text(item.get('id')) or f'R{ri + 1}'
            sub = f'p:{pid}#{rid}'
            change = _text(item.get('change'))
            expected = [_text(k) for k in _list(item.get('expected_keys')) if _text(k)]
            registered = [k for k in expected if k in result_objs]
            executed = item.get('executed')
            meta = {'change': change, 'expected_keys': expected, 'registered_keys': registered,
                    'executed': executed if isinstance(executed, (bool, int, float, str)) or executed is None else _text(executed),
                    'execution_note': _text(item.get('execution_note'))}
            if not active:
                state, badge = 'expired', ''
            elif expected and len(registered) == len(expected):
                state, badge = 'done', ''
            elif registered:
                state, badge = 'pending', '部分'
            else:
                state, badge = 'pending', ''
            n = g.add_node(sub, 'method', f'{rid}：{_clip(change, 24)}' if change else rid, change or rid, state, meta,
                           f'analysis/plans/{pid}.yaml#robustness[{rid}]')
            n['subtype'] = 'sensitivity'
            n['parent'] = group_of[pid]
            n['collapsed'] = not active
            n['band'] = ''   # 下面的區帶指派：跟 plan
            n['badge'] = badge
            sens_of.setdefault(pid, []).append(sub)
            sub_expected[sub] = expected
            sub_item[sub] = item
            sub_ri[sub] = ri
            g.add_edge(group_of[pid], sub, 'sensitivity', f'analysis/plans/{pid}.yaml#robustness[{rid}]', '敏感性', visible=active)
            for ki, key in enumerate(expected):
                rob_index.setdefault((pid, key), (ri, ki))
                robustness_of.setdefault((pid, key), rid)
                decl_order.setdefault((pid, key), len(decl_order))
                declared_by_of.setdefault(key, []).append(sub)
    for pid, subs in sens_of.items():
        pn = g.nodes[f'p:{pid}']
        pn['meta']['sensitivity_ids'] = list(subs)
        pn['meta']['group_id'] = group_of[pid]
        if plan_active[pid]:   # 0.18.0：現行 plan 徽章「敏感性 n」（與舊版數並列時「v2（1 舊版）｜敏感性 n」）；面板可收合群與子分析
            pn['badge'] = '｜'.join(x for x in (pn['badge'], f'{SENSITIVITY_BADGE} {len(subs)}') if x)
        gn = g.nodes[group_of[pid]]
        gn['meta']['sensitivity_ids'] = list(subs)
        states = [g.nodes[s]['state'] for s in subs]
        if not plan_active[pid]:
            gn['state'] = 'expired'
        elif all(s == 'done' for s in states):
            gn['state'] = 'done'
        elif any(s == 'blocked' for s in states):
            gn['state'] = 'blocked'
        else:
            gn['state'] = 'pending'
    # 結果鍵分類（與 0.18.x 逐鍵節點的規則相同，只是提前到建節點之前算）：owner＝results.json 的 plan_id；
    # 0.18.0：results.json 沒登錄（或 plan 不在 index）的鍵，宣告以現行 plan 優先——demote_plan 之後同一鍵會同時在舊版 plan 的 outputs 與現行 plan 的
    # robustness 出現，該鍵應算現行 plan 的次要結果、掛在其子分析之下，而不是沿用已取代 plan 的主要結果宣告
    primary_declared = {k for (_p, k) in out_index}
    secondary_declared = {k for (_p, k) in rob_index} - primary_declared
    primary_active = {k for (p_, k) in out_index if plan_active.get(p_)}
    secondary_active = {k for (p_, k) in rob_index if plan_active.get(p_)} - primary_active

    def owner_of(key: str) -> str:
        obj = result_objs.get(key)
        return _text(obj.get('plan_id')) if obj is not None else ''

    def kind_of(key: str) -> str:
        owner = owner_of(key)
        if (owner, key) in out_index:
            return 'primary'
        if (owner, key) in rob_index:
            return 'secondary'
        if owner not in plan_sq and key in primary_active:
            return 'primary'
        if owner not in plan_sq and key in secondary_active:
            return 'secondary'
        if owner not in plan_sq and key in primary_declared:
            return 'primary'
        if owner not in plan_sq and key in secondary_declared:
            return 'secondary'
        if key in primary_declared:
            return 'primary'
        if key in secondary_declared:
            return 'secondary'
        return 'undeclared'

    def parent_sub_of(key: str) -> str:
        """次要鍵所屬的子分析：先看 results.json 的 plan、再看該問題現行版、再看任一現行 plan、再依宣告順序；同 plan 內取 R 序最小者。"""
        cands = [d for d in declared_by_of.get(key, []) if '#' in d]
        owner = owner_of(key)
        sq = plan_sq.get(owner, '')
        cur = next((pp for pp, ss in plan_sq.items() if ss == sq and plan_active.get(pp)), '') if sq else ''
        pref = {owner: 0, cur: 1}
        cands.sort(key=lambda d: (pref.get(d[2:].split('#')[0], 2 if plan_active.get(d[2:].split('#')[0]) else 3),
                                  rob_index.get((d[2:].split('#')[0], key), (BIG, 0))[0], d))
        return cands[0] if cands else ''

    key_kind: dict[str, str] = {}
    agg_keys: dict[str, list[str]] = {sub: [] for sub in sub_expected}   # 子分析 → 自有次要鍵（宣告序）
    for key in list(declared_by_of) + [k for k in result_objs if k not in declared_by_of]:
        kind = kind_of(key)
        key_kind[key] = kind
        if kind == 'secondary':
            sub = parent_sub_of(key)
            if sub:
                agg_of_key[key] = f'r:{sub[2:]}{SECONDARY_SUFFIX}'
                agg_keys[sub].append(key)
            else:
                key_kind[key] = 'undeclared'   # 理論上不會發生（次要鍵一定有子分析宣告它）；保守退回逐鍵虛線
    for sub, keys in agg_keys.items():   # 聚合節點裡的鍵依該子分析 expected_keys 的順序；別的子分析宣告、歸到這裡的鍵接在後面
        own = [k for k in sub_expected[sub] if agg_of_key.get(k) == f'r:{sub[2:]}{SECONDARY_SUFFIX}']
        keys[:] = own + [k for k in keys if k not in own]
    # 第二遍：依宣告順序建結果節點與 produces 邊——outputs 的主要鍵逐鍵；有自有次要鍵的子分析一個聚合節點（沒有就不建、也不建邊）
    undeclared_of: dict[str, list[str]] = {}   # plan_id → 掛在該 plan 但未宣告的結果節點 id（results.json 序）
    for pid, doc in plan_docs.items():
        if not doc:
            continue
        active = plan_active[pid]
        for item in _list(doc.get('outputs')):
            if isinstance(item, dict) and _text(item.get('key')):
                key = _text(item.get('key'))
                source = f'analysis/plans/{pid}.yaml#outputs[{key}]'
                if key in agg_of_key:
                    continue   # 舊版 outputs 宣告、現已是現行版的次要鍵：歸聚合節點（meta.keys[].declared_by 記本 plan），不另建逐鍵節點
                nid = result_node(key, source, '已宣告、results.json 尚無此鍵', 'pending')
                g.nodes[nid]['meta']['declared_by'].append(f'p:{pid}')
                g.add_edge(f'p:{pid}', nid, 'produces', source, visible=active)
        for sub in sens_of.get(pid, []):
            rid = sub.split('#')[1]
            expected = sub_expected[sub]
            agg = f'r:{sub[2:]}{SECONDARY_SUFFIX}'
            for key in expected:
                source = f'analysis/plans/{pid}.yaml#robustness[{rid}].expected_keys'
                if key in agg_of_key:
                    if agg_of_key[key] != agg:   # 同一鍵也被別的子分析宣告：那個子分析 → 本鍵所屬聚合節點一條 produces（label 記鍵）
                        g.add_edge(sub, agg_of_key[key], 'produces', source, key, visible=active)
                    continue
                nid = result_node(key, source, '已宣告、results.json 尚無此鍵', 'pending')
                g.nodes[nid]['meta']['declared_by'].append(sub)
                g.add_edge(sub, nid, 'produces', source, visible=active)   # 目標為主要／未宣告結果時在結果分類後一律改隱藏（不分區帶）
            # 聚合節點：id r:<pid>#R<k>#secondary、type result、subtype secondary_group、parent＝子分析、帶／帶內位置跟父；
            # 子分析沒有任何自有次要鍵（expected_keys 為空、或只引用本 plan outputs／別 plan 的鍵）→ 沒有這個宣告單位，不建
            keys = agg_keys[sub]
            if not keys:
                continue
            item = sub_item[sub]
            ev_owner = _text(item.get('evidence_owned_by'))
            ev_keys = [_text(k) for k in _list(item.get('evidence_keys')) if _text(k)]
            entries = []
            n_unreg = n_unval = 0
            blocked = False
            for key in keys:
                obj = result_objs.get(key)
                vids = validated_by.get(key, [])
                registered = obj is not None
                entry = {'key': key, 'registered': registered, 'validated': bool(vids), 'validated_by': list(vids),
                         'validation_kind': 'primary' if key in primary_keys else ('robustness' if vids else ''),
                         'declared_by': list(declared_by_of.get(key, [])), 'plan_id': owner_of(key)}
                if registered:
                    if _text(obj.get('model_id')):
                        entry['model_id'] = _text(obj.get('model_id'))
                    if _text(obj.get('description')):
                        entry['description'] = _clip(_text(obj.get('description')), SUMMARY_MAX)
                    if not vids:
                        n_unval += 1
                else:
                    n_unreg += 1
                if ev_owner and key in ev_keys:
                    entry['evidence_owned_by'] = ev_owner
                if any(vstatus.get(v) == 'fail' for v in vids):
                    blocked = True
                entries.append(entry)
            label = keys[0] if len(keys) == 1 else f'{SECONDARY_GROUP_LABEL} {len(keys)} 鍵'
            if not active:
                state = 'expired'
            elif blocked:
                state = 'blocked'
            elif n_unreg == 0:
                state = 'done'
            else:
                state = 'pending'
            badge = '／'.join(x for x in ((f'未登錄 {n_unreg}' if n_unreg else ''), (f'未驗證 {n_unval}' if n_unval else '')) if x)
            title = f'{sub[2:]} 的次要結果（expected_keys 中只在此宣告的鍵）共 {len(keys)} 鍵：' + '、'.join(keys[:8]) + ('…' if len(keys) > 8 else '')
            meta = {'plan_id': pid, 'robustness_id': rid, 'result_kind': 'secondary', 'keys': entries, 'n_keys': len(keys),
                    'n_unregistered': n_unreg, 'n_unvalidated': n_unval, 'validated': n_unval == 0 and n_unreg == 0,
                    'cited_by_figures': [], 'declared_by': [sub]}
            if ev_owner:
                meta['evidence_owned_by'] = ev_owner
                meta['evidence_keys'] = ev_keys
            an = g.add_node(agg, 'result', label, title, state, meta, f'analysis/plans/{pid}.yaml#robustness[{rid}].expected_keys')
            an['subtype'] = 'secondary_group'
            an['parent'] = sub
            an['collapsed'] = bool(g.nodes[sub]['collapsed'])
            an['badge'] = badge
            an['band'] = ''   # 下面的區帶指派：跟父
            g.add_edge(sub, agg, 'produces', f'analysis/plans/{pid}.yaml#robustness[{rid}].expected_keys', visible=active)
    for key, obj in result_objs.items():
        pid = _text(obj.get('plan_id'))
        if pid and f'p:{pid}' not in g.nodes:
            n = g.add_node(f'p:{pid}', 'method', pid, 'index.yaml 無此 plan', 'unknown', {'models': [], 'sq': ''}, f'{REL["results"]}#{key}.plan_id')
            n['subtype'] = 'primary'
            plan_sq[pid] = ''
            plan_active[pid] = False
        nid = result_node(key, f'{REL["results"]}#{key}', '', 'done')
        if pid:
            if (pid, key) not in out_index and (pid, key) not in rob_index:
                # 掛在該 plan 但 outputs／robustness 都沒宣告 → 未宣告（虛線）；次要鍵（別的 plan 宣告）指向其聚合節點、label 記鍵
                decl_order.setdefault((pid, key), len(decl_order))
                g.add_edge(f'p:{pid}', nid, 'produces', f'{REL["results"]}#{key}.plan_id', '未宣告' if key not in agg_of_key else f'未宣告 {key}',
                           visible=plan_active.get(pid, False), style='dashed')
                undeclared_of.setdefault(pid, []).append(nid)
            mid = _text(obj.get('model_id'))
            models = g.nodes[f'p:{pid}']['meta'].setdefault('models', [])
            if mid and mid not in models:
                models.append(mid)
    # 0.18.0：不再建 supplements「敏感性對照」邊（0.15.0–0.17.3 的短垂線畫法已由「群縮排在 plan 之下、plan → 群 L 形線」取代；
    # EDGE_TYPES 仍保留該型別供舊 IR 讀取，validate_graph 對它改為「不得出現」）
    # 0.18.0：附錄問題沒有 active plan（例如 demote_plan 之後）→ 問題節點徽章「無 active plan」、meta.no_active_plan（主問題缺 plan 是 check_plan BLOCKER，
    # 由 state 呈現，不另加徽章）；前端樂觀更新的同名徽章與此一致
    active_qs = {sq for pid, sq in plan_sq.items() if plan_active.get(pid)}
    for qid in question_order:
        if qid.startswith('q:AQ') and qid[2:] not in active_qs and g.nodes[qid]['type'] == 'question':
            g.nodes[qid]['badge'] = '無 active plan'
            g.nodes[qid]['meta']['no_active_plan'] = True
    # 方法節點 label／state／title（models 齊了才算）
    key_count: dict[str, int] = {}
    for obj in result_objs.values():
        pid = _text(obj.get('plan_id'))
        if pid:
            key_count[pid] = key_count.get(pid, 0) + 1
    for pid in list(plan_sq):
        n = g.nodes[f'p:{pid}']
        models = n['meta'].get('models', [])
        n['label'] = _clip(f'{pid} ｜ {"、".join(models)}' if models else pid, LABEL_MAX)
        if n['state'] == 'unknown':
            continue
        if plan_active[pid]:
            if key_count.get(pid, 0) > 0:
                n['state'] = 'done'
            else:
                n['state'] = 'pending'
                n['title'] = (n['title'] + '（方法尚未執行）') if n['title'] else '方法尚未執行'
        else:
            n['state'] = 'expired'
    for nid, n in g.nodes.items():   # 逐鍵結果節點的分類（主要／未宣告；次要鍵已進聚合節點，這裡不會出現）
        if n['type'] != 'result' or n.get('subtype') == 'secondary_group':
            continue
        key = nid[2:]
        owner = _text(n['meta'].get('plan_id'))
        kind = key_kind.get(key) or kind_of(key)
        if kind == 'secondary':
            kind = 'undeclared'
        n['meta']['result_kind'] = kind
        n['badge'] = RESULT_KIND_ZH[kind]
        n['subtype'] = kind
        rid = robustness_of.get((owner, key)) or next((r for (pp, kk), r in sorted(robustness_of.items(), key=lambda t: (0 if plan_active.get(t[0][0]) else 1)) if kk == key), '')
        if rid:
            n['meta']['robustness_id'] = rid
    # 0.16.5 結果主從：outputs[i].supports 指向同 plan 另一個頂層主要結果 → parent＝r:<under>、subtype supporting、縮排、跟主結果收合、
    # 同一區帶（下面 band 依 parent）；主結果徽章「支撐 n」；主結果 → 支撐結果一條 supports L 形線；plan → 支撐結果的 produces 預設不畫
    # （避免交叉；IR 保留）。只認 results.json 所屬 plan（或該問題現行版）的宣告；主結果非頂層或不在同 plan 者不巢狀（check_plan 會擋）
    supporting_of: dict[str, list[str]] = {}
    for nid, n in list(g.nodes.items()):
        if n['type'] != 'result' or n['meta'].get('result_kind') != 'primary':
            continue
        key = nid[2:]
        owner = _text(n['meta'].get('plan_id'))
        under = supports_of.get((owner, key))
        if not under:
            sq = plan_sq.get(owner, '')
            cur = next((pp for pp, ss in plan_sq.items() if ss == sq and plan_active.get(pp)), '') if sq else ''
            under = supports_of.get((cur, key), '') if cur else ''
            if not under:
                continue
            owner = cur
        pn = g.nodes.get(f'r:{under}')
        if pn is None or pn['type'] != 'result' or pn['meta'].get('result_kind') != 'primary' or (owner, under) not in out_index \
                or supports_of.get((owner, under)) or _text(pn['meta'].get('plan_id')) not in (owner, ''):
            n['meta']['supports_invalid'] = under
            continue
        n['parent'] = f'r:{under}'
        n['subtype'] = 'supporting'
        n['badge'] = SUPPORTING_BADGE
        n['meta']['supports'] = under
        n['collapsed'] = bool(pn['collapsed'])
        supporting_of.setdefault(f'r:{under}', []).append(nid)
        g.add_edge(f'r:{under}', nid, 'supports', f'analysis/plans/{owner}.yaml#outputs[{key}].supports', '支撐', visible=plan_active.get(owner, False))
    for pnid, subs in supporting_of.items():
        g.nodes[pnid]['meta']['supporting_ids'] = list(subs)
        g.nodes[pnid]['badge'] = f'{SUPPORTING_BADGE} {len(subs)}'
    # 子分析 → 主要／未宣告結果的 produces 一律預設不畫（plan 自己的 outputs 已涵蓋，不分區帶）；→ 次要結果照舊可見；
    # plan → 支撐結果的 produces 也預設不畫（主結果 → 支撐結果的 L 形線已表達歸屬）
    for e in g.edges:
        if e['type'] == 'produces' and '#' in e['from'] and g.nodes[e['to']].get('subtype') not in ('secondary', 'secondary_group'):
            e['default_visible'] = False
        elif e['type'] == 'produces' and g.nodes[e['to']].get('subtype') == 'supporting':
            e['default_visible'] = False

    # validation items：p → v（validated_by）、v → r（primary）
    top_expired = _text(vdoc.get('status')).lower() == 'expired'
    vrank: dict[str, tuple] = {}
    for i, item in vitems:
        vid = _text(item.get('id')) or f'items[{i}]'
        istatus = _text(item.get('status')).lower()
        state = 'expired' if top_expired else {'pass': 'done', 'qualified': 'done', 'fail': 'blocked'}.get(istatus, 'unknown')
        sq_raw = _text(item.get('sq'))
        meta = {'status': istatus or 'unknown', 'sq': src.alias_of(sq_raw), 'plan_id': _text(item.get('plan_id')),
                'primary_results': [_text(k) for k in _list(item.get('primary_results')) if _text(k)],
                'robustness_keys': list(dict.fromkeys(_text(k) for rob in _list(item.get('robustness')) if isinstance(rob, dict)
                                                      for k in _list(rob.get('result_keys')) if _text(k)))}
        if top_expired:
            meta['expired_at'] = _date(vdoc.get('expired_at'))
        if sq_raw != meta['sq']:
            meta['sq_original'] = sq_raw
        if _text(item.get('limitations')):
            meta['limitations'] = _clip(_text(item.get('limitations')), META_MAX)
        source = f'{REL["validation"]}#items[{vid}]'
        g.add_node(f'v:{vid}', 'validation', vid, f'{meta["sq"] or "?"} 驗證 {istatus or "unknown"}', state, meta, source)
        pid = _text(item.get('plan_id'))
        if pid:
            if f'p:{pid}' not in g.nodes:
                g.add_node(f'p:{pid}', 'method', pid, 'index.yaml 無此 plan', 'unknown', {'models': [], 'sq': meta['sq']}, f'{source}.plan_id')
                plan_sq[pid] = meta['sq']
                plan_active[pid] = False
            g.add_edge(f'p:{pid}', f'v:{vid}', 'validated_by', f'{source}.plan_id', '驗證')
        # 0.19.0：列到次要鍵的 primary／robustness 邊指向聚合節點，一條、label 記鍵數；主要／未宣告鍵照舊逐鍵
        for nid, keys in grouped_targets(meta['primary_results'], f'{source}.primary_results', 'validation 指向的鍵不在 results.json', 'unknown'):
            g.add_edge(f'v:{vid}', nid, 'primary', f'{source}.primary_results',
                       f'驗證（主要）{len(keys)} 鍵' if g.nodes[nid].get('subtype') == 'secondary_group' else '驗證（主要）')
        rob_only = [k for k in meta['robustness_keys'] if k not in meta['primary_results']]   # 同一 item 同一鍵：只畫 primary，不重複
        for nid, keys in grouped_targets(rob_only, f'{source}.robustness[].result_keys', 'validation 指向的鍵不在 results.json', 'unknown'):
            g.add_edge(f'v:{vid}', nid, 'robustness', f'{source}.robustness[].result_keys',
                       f'驗證（穩健性）{len(keys)} 鍵' if g.nodes[nid].get('subtype') == 'secondary_group' else '驗證（穩健性）', style='thin')
        sq = meta['sq'] or plan_sq.get(pid, '')
        vrank[f'v:{vid}'] = (question_order.index(f'q:{sq}') if f'q:{sq}' in question_order else BIG, i)

    # goals links → cites（hidden，與主幹重複）；鍵不在 results.json 視為 dangling
    dangling: set[str] = set()
    cite_rank: dict[str, tuple] = {}
    for ci, (qid, key, source) in enumerate(cites):
        nid = result_node(key, source, 'goals 指向的鍵不在 results.json', 'unknown')
        g.add_edge(qid, nid, 'cites', source, key if nid in agg_of_key.values() else '', visible=False)
        if key not in result_objs:
            dangling.add(key)
        cite_rank.setdefault(nid, (question_order.index(qid), 2, BIG, ci))

    for nid, n in g.nodes.items():   # validation／goals 才建的結果節點：補 result_kind 與徽章
        if n['type'] == 'result' and 'result_kind' not in n['meta']:
            n['meta']['result_kind'] = 'undeclared'
            n['badge'] = RESULT_KIND_ZH['undeclared']
            n['subtype'] = 'undeclared'

    # 結果節點的列序提示：（問題順序, plan 版本序, 主要鍵依 outputs 序 → 各子分析依 R 序及 expected 序 → 未宣告 → goals 引用）
    q_index = {qid: i for i, qid in enumerate(question_order)}
    active_of_sq: dict[str, str] = {sq: pid for pid, sq in plan_sq.items() if plan_active.get(pid)}
    rank_hint: dict[str, tuple] = {}
    for nid, n in g.nodes.items():
        if n['type'] != 'result':
            continue
        if n.get('subtype') == 'secondary_group':   # 0.19.0 聚合節點：所屬子分析的 R 序（在該 plan 的主要鍵之後、未宣告之前）
            pid = _text(n['meta'].get('plan_id'))
            sq = plan_sq.get(pid, '')
            cur = active_of_sq.get(sq, pid)
            ver = g.nodes[f'p:{cur}']['meta'].get('version', BIG) if f'p:{cur}' in g.nodes else BIG
            rank_hint[nid] = (q_index.get(f'q:{sq}', BIG), ver, 1, sub_ri.get(n['parent'], BIG), 0, nid)
            continue
        key = nid[2:]
        owner = _text(n['meta'].get('plan_id'))
        if not (owner and f'p:{owner}' in g.nodes):
            decl = n['meta'].get('declared_by') or []
            owner = decl[0][2:].split('#')[0] if decl else ''
        if owner:
            sq = plan_sq.get(owner, '')
            cur = active_of_sq.get(sq, owner)
            ver = g.nodes[f'p:{cur}']['meta'].get('version', BIG) if f'p:{cur}' in g.nodes else BIG
            for pid in (cur, owner):
                if (pid, key) in out_index:
                    rank_hint[nid] = (q_index.get(f'q:{sq}', BIG), ver, 0, out_index[(pid, key)], 0, key)
                    break
                if (pid, key) in rob_index:
                    ri, ki = rob_index[(pid, key)]
                    rank_hint[nid] = (q_index.get(f'q:{sq}', BIG), ver, 1, ri, ki, key)
                    break
            else:
                rank_hint[nid] = (q_index.get(f'q:{sq}', BIG), ver, 2, BIG, 0, key)
        elif nid in cite_rank:
            rank_hint[nid] = (cite_rank[nid][0], BIG, 3, cite_rank[nid][3], 0, key)
        else:
            rank_hint[nid] = (BIG, BIG, 4, BIG, 0, key)
    for pnid, subs in supporting_of.items():   # 支撐結果緊接主結果之後（主結果 rank + (1, 該鍵 outputs 序)）
        base = rank_hint.get(pnid, (BIG,))
        for snid in subs:
            rank_hint[snid] = base + (1, rank_hint.get(snid, (BIG,) * 6)[3], snid)

    # 圖表節點（analysis/figures/manifest.json）：r → f depicts
    manifest = src.data('manifest') if src.status('manifest') == 'ok' else {}
    figs = manifest.get('figures')
    fig_items = [f for f in figs if isinstance(f, dict)] if isinstance(figs, list) else \
        [dict(v, id=v.get('id') or k) for k, v in figs.items() if isinstance(v, dict)] if isinstance(figs, dict) else []
    fig_rank: dict[str, tuple] = {}
    for fi, fig in enumerate(fig_items):
        fid = _text(fig.get('id')) or f'figures[{fi}]'
        nid = f'f:{fid}'
        source = f'{REL["manifest"]}#figures[{fid}]'
        file_rel = _text(fig.get('file'))
        files = [_text(x) for x in _list(fig.get('files')) if _text(x)]
        status = _text(fig.get('status')).lower()
        caption_raw = _text(fig.get('caption'))
        title = _clip(MD_MARK_RE.sub('', caption_raw), META_MAX)
        exists = bool(file_rel) and src.exists(file_rel)
        if not exists:
            state = 'unknown'
            title = (title + '（檔案不存在）') if title else '檔案不存在'
        elif ('confirmed' in status or 'reviewed' in status) and 'not_reviewed' not in status:
            state = 'done'
        elif 'not_reviewed' in status or 'registered' in status:
            state = 'pending'
            title = '已登錄未審：' + title
        else:
            state = 'pending'
        meta = {'file': file_rel, 'files': files, 'role': _text(fig.get('role')), 'figure_number': _text(fig.get('figure_number')),
                'status': status, 'script': _text(fig.get('script')), 'registered_at': _date(fig.get('registered_at')),
                'results_keys': [_text(k) for k in _list(fig.get('results_keys')) if _text(k)], 'caption': caption_raw,
                'spec': fig.get('spec') if isinstance(fig.get('spec'), (dict, list, str, int, float)) else _text(fig.get('spec'))}
        if embed_figures and exists:
            cand = file_rel if file_rel.lower().endswith('.svg') else next(
                (f for f in files if f.lower().endswith(('.png', '.svg')) and src.exists(f)), '')
            if cand:
                path = src.root / cand
                size = path.stat().st_size
                if size > EMBED_MAX_BYTES:
                    src.warnings.append(f'{cand} 超過 {EMBED_MAX_BYTES // (1024 * 1024)} MB（{size / (1024 * 1024):.1f} MB），不內嵌')
                else:
                    mime = IMAGE_MIME.get(Path(cand).suffix.lower(), 'application/octet-stream')
                    meta['data_uri'] = f'data:{mime};base64,' + base64.b64encode(path.read_bytes()).decode('ascii')
        role = '_'.join(_text(fig.get('role')).lower().split())   # 小寫、去頭尾空白、內部空白視同底線（Extended Data → extended_data）
        role_band = FIGURE_ROLE_BAND.get(role, '')
        meta['role_source'] = 'manifest' if role_band else 'derived'   # band 由 manifest role 決定；缺或不認得 → 由呈現的結果推導
        meta['type'] = _text(fig.get('type'))
        n = g.add_node(nid, 'figure', fid, title, state, meta, source)
        meta = n['meta']
        if role_band:
            n['band'] = role_band
            n['badge'] = '主表' if role_band == 'main' and meta['type'].lower() == 'table' else FIGURE_ROLE_BADGE[role_band]
        keys = meta['results_keys']
        missing = [k for k in keys if f'r:{k}' not in g.nodes and k not in agg_of_key]
        first_rank: tuple = (BIG,)
        targets: dict[str, list[str]] = {}   # 0.19.0：次要鍵合併成「聚合節點 → 圖表」一條 depicts（label「n 鍵」），取代逐鍵
        for k in keys:
            t = agg_of_key.get(k) or (f'r:{k}' if f'r:{k}' in g.nodes else '')
            if t:
                targets.setdefault(t, []).append(k)
        for t, ks in targets.items():
            if g.nodes[t].get('subtype') == 'secondary_group':
                g.add_edge(t, nid, 'depicts', f'{source}.results_keys', f'{len(ks)} 鍵')
                g.nodes[t]['meta']['cited_by_figures'].append(fid)
            else:
                g.add_edge(t, nid, 'depicts', f'{source}.results_keys', '呈現於')
            first_rank = min(first_rank, rank_hint.get(t, (BIG,)))
        keys_badge = ''
        if keys and len(missing) == len(keys):
            keys_badge = '無對應結果鍵'
        if missing:
            src.warnings.append(f'{REL["manifest"]}#figures[{fid}].results_keys 指到不在圖裡的鍵: {"、".join(missing)}')
        elif not keys:
            keys_badge = '無結果鍵'
            src.infos.append(f'{REL["manifest"]}#figures[{fid}] 無 results_keys')
        if keys_badge:
            meta['keys_badge'] = keys_badge          # 徽章以 role 為主，結果鍵狀況留在 meta
            n['badge'] = n['badge'] or keys_badge
        fig_rank[nid] = first_rank + (fi,)

    # 0.19.0 report.md 節點：analysis/report.md 存在才讀（adapter 沒有另外的 report 路徑欄位），取 ![…](path) 引用、以 report.md 所在目錄
    # 與 pipeline root 兩種相對路徑對 manifest 的 path／file／files 比對；一個 type report 節點（圖表欄最後一列、main 區帶、孤兒帶），
    # label「report.md（引用 k／manifest m 張）」；圖表 → report 一條 embedded_in（預設不畫，點選或「顯示全部邊」才顯）；
    # role=main 且未被引用的圖表徽章「報告未引用」（沒有 report.md 就不標）
    report_exists = src.exists(REPORT_REL)
    report_refs: list[str] = []
    report_date = ''
    if report_exists:
        try:
            rtext = (src.root / REPORT_REL).read_text(encoding='utf-8', errors='replace')
        except OSError as exc:
            rtext = ''
            src.warnings.append(f'{REPORT_REL} 無法讀取: {_one_line(exc)}')
        report_refs = list(dict.fromkeys(MD_IMG_RE.findall(rtext)))
        m_date = DATE_RE.search(rtext[:4000])
        report_date = m_date.group(0) if m_date else ''
    rdir = REPORT_REL.rsplit('/', 1)[0]

    def ref_candidates(ref: str) -> set[str]:
        ref = ref.split('#')[0].split('?')[0]
        while ref.startswith('./'):
            ref = ref[2:]
        out = {ref, posixpath.normpath(posixpath.join(rdir, ref))}   # pipeline root 相對、report.md 所在目錄相對（含 ../）兩種都試
        return {x.lstrip('/') for x in out if x and x != '.'}

    fig_paths: dict[str, list[str]] = {}
    for fi, fig in enumerate(fig_items):
        fid = _text(fig.get('id')) or f'figures[{fi}]'
        cands = [_text(fig.get('path')), _text(fig.get('file'))] + [_text(x) for x in _list(fig.get('files'))]
        fig_paths[fid] = [c.lstrip('./') for c in cands if c]
    cited: dict[str, list[str]] = {}   # 圖表 id → 命中的引用路徑
    unmatched_refs: list[str] = []
    for ref in report_refs:
        cs = ref_candidates(ref)
        hit = False
        for fid, paths in fig_paths.items():
            if any(pth in cs for pth in paths):
                cited.setdefault(fid, []).append(ref)
                hit = True
        if not hit:
            unmatched_refs.append(ref)
    n_cited = sum(1 for fid in fig_paths if fid in cited)
    rmeta = {'path': REPORT_REL, 'exists': report_exists, 'generated_at': report_date, 'n_refs': len(report_refs),
             'n_cited': n_cited, 'n_manifest': len(fig_paths), 'cited_figures': [f'f:{fid}' for fid in fig_paths if fid in cited],
             'uncited_main_figures': [], 'unmatched_refs': unmatched_refs[:META_MAX]}
    rn = g.add_node(REPORT_ID, 'report', f'report.md（引用 {n_cited}／manifest {len(fig_paths)} 張）',
                    (f'{REPORT_REL}：引用 manifest 圖表 {n_cited} 張（{len(report_refs)} 個圖片引用' + (f'、{len(unmatched_refs)} 個對不到 manifest' if unmatched_refs else '') + '）'
                     + (f'；產生 {report_date}' if report_date else '')) if report_exists else f'{REPORT_REL} 尚未產生（analyze-data 交付）',
                    'done' if report_exists else 'pending', rmeta, REPORT_REL)
    rn['strip'] = ORPHAN_STRIP
    for fid in fig_paths:
        fn = g.nodes.get(f'f:{fid}')
        if fn is None:
            continue
        fn['meta']['report_cited'] = fid in cited
        if fid in cited:
            g.add_edge(f'f:{fid}', REPORT_ID, 'embedded_in', f'{REPORT_REL}#![]({cited[fid][0]})', '嵌入報告', visible=False)
        elif report_exists and fn['band'] == 'main' and fn['meta'].get('role_source') == 'manifest':
            fn['badge'] = '｜'.join(x for x in (fn['badge'], REPORT_UNCITED_BADGE) if x)
            rmeta['uncited_main_figures'].append(f'f:{fid}')
    if unmatched_refs:
        src.infos.append(f'{REPORT_REL} 有 {len(unmatched_refs)} 個圖片引用對不到 manifest：' + '、'.join(unmatched_refs[:5]) + ('…' if len(unmatched_refs) > 5 else ''))
    if not report_exists:
        src.infos.append(f'{REPORT_REL} 不存在：report 節點為 pending，圖表不標「{REPORT_UNCITED_BADGE}」')

    # decisions → refers／supersedes（全部 hidden）
    decisions = [d for d in _list(src.data('decisions').get('decisions')) if isinstance(d, dict)] \
        if src.status('decisions') == 'ok' else []
    for i, d in enumerate(decisions):
        did = _text(d.get('id')) or f'decisions[{i}]'
        meta = {'date': _date(d.get('date')), 'stage': _text(d.get('stage')), 'checkpoint': _text(d.get('checkpoint')),
                'decision': _clip(_text(d.get('decision')), SUMMARY_MAX), 'method': _text(d.get('method')),
                'exec_issue': _text(d.get('exec_issue'))}
        title = _clip(_text(d.get('decision')), SUMMARY_MAX) or did
        g.add_node(f'd:{did}', 'decision', did, title, '', meta, f'{REL["decisions"]}#decisions[{did}]')
    for i, d in enumerate(decisions):
        did = _text(d.get('id')) or f'decisions[{i}]'
        me = f'd:{did}'
        base = f'{REL["decisions"]}#decisions[{did}]'
        hits = 0
        question = src.alias_of(_text(d.get('question')))
        if question == 'main':
            hits += 1 if g.add_edge(me, 'q:main', 'refers', f'{base}.question', visible=False) else 0
        elif question and f'q:{question}' in g.nodes:
            hits += 1 if g.add_edge(me, f'q:{question}', 'refers', f'{base}.question', visible=False) else 0
        for link in _list(d.get('links')):
            link_s = _text(link)
            target = ''
            if f'q:{src.alias_of(link_s)}' in g.nodes and link_s != 'main':
                target = f'q:{src.alias_of(link_s)}'
            elif DECISION_ID_RE.fullmatch(link_s) and f'd:{link_s}' in g.nodes:
                target = f'd:{link_s}'
            elif link_s.startswith('results.') and f'r:{link_s[len("results."):]}' in g.nodes:
                target = f'r:{link_s[len("results."):]}'
            elif link_s.startswith('results.') and link_s[len('results.'):] in agg_of_key:
                target = agg_of_key[link_s[len('results.'):]]   # 0.19.0：指到次要鍵 → 該鍵所屬的聚合節點
            else:
                m = PLAN_PATH_RE.match(link_s)
                if m and f'p:{m.group(1)}' in g.nodes:
                    target = f'p:{m.group(1)}'
            if target and target != me:
                hits += 1 if g.add_edge(me, target, 'refers', f'{base}.links', visible=False) else 0
        for old in DECISION_ID_RE.findall(_text(d.get('supersedes'))):
            if f'd:{old}' in g.nodes and old != did:
                hits += 1 if g.add_edge(f'd:{old}', me, 'supersedes', f'{base}.supersedes', visible=False, style='dashed') else 0
        if hits == 0:
            g.add_edge(me, 'q:main', 'refers', f'{base}（無對應節點，掛主問題）', visible=False)

    # 區帶指派（main／ext／supp）：問題依來源清單（永遠不是 ext）；plan 跟問題；敏感性分析群與子分析跟所屬 plan（0.18.0；之前一律 supp）；
    # 次要結果跟宣告它的子分析（即跟 plan）、其餘結果跟 owner plan 的問題（沒有 plan 只被 goals 引用 → 第一個引用它的問題）；驗證依 item 的 sq；
    # 圖表只有在它呈現的結果全在同一區帶時才跟去那一帶；決策 main。
    # 0.20.0 Extended Data opt-in（analysis/extended-data.yaml；使用者 2026-09-17 裁定「方法、結果、驗證也要能放 ED，只有 SQ／AQ 不行」）：
    # plans 清單的 plan／子分析、results 清單的主要／未宣告結果、validation 清單的 item → ext（band_source explicit）；跟著走的（群跟 plan、子分析跟 plan、
    # 次要結果跟子分析、支撐結果跟主結果、主要結果跟 owner plan、驗證跟 plan_id 的 plan）→ ext（band_source inherited:<explicit 的來源節點>）；
    # 其餘照原規則（band_source derived）。只有 opt-in、沒有負向覆寫；缺檔＝沒有任何節點放 ED，畫法與 0.19.0 相同。
    ed_sets = _extended_data_sets(src, g, agg_of_key)
    ed_root: dict[str, str] = {}   # 節點 → 讓它落在 ext 的 explicit 來源節點（自己在檔裡就是自己）

    def plan_band(pid: str) -> str:
        return q_band.get(f'q:{plan_sq.get(pid, "")}', 'main')

    def set_band(n: dict, band: str, source: str) -> None:
        n['band'] = band
        n['meta']['band_source'] = source

    def follow(n: dict, src_id: str, fallback_band: str) -> None:
        """跟著來源節點：來源在 ext → ext（inherited:<其 explicit 根>）；否則 fallback（derived）。"""
        sn = g.nodes.get(src_id)
        if sn is not None and sn['band'] == 'ext' and src_id in ed_root:
            ed_root[n['id']] = ed_root[src_id]
            set_band(n, 'ext', BAND_SOURCE_INHERITED + ed_root[src_id])
        else:
            set_band(n, fallback_band, BAND_SOURCE_DERIVED)

    def explicit(n: dict) -> None:
        ed_root[n['id']] = n['id']
        set_band(n, 'ext', BAND_SOURCE_EXPLICIT)

    for nid, n in g.nodes.items():   # 第一輪：問題、頂層 plan（explicit 或跟問題）
        t = n['type']
        if t == 'question':
            n['band'] = q_band.get(nid, 'main')
        elif t == 'method' and '#' not in nid:
            if nid in ed_sets['p:']:
                explicit(n)
            else:
                set_band(n, plan_band(nid[2:]), BAND_SOURCE_DERIVED)
        elif t == 'figure':
            pass                 # 圖表：manifest role 已在建節點時指派；缺或不認得的最後由呈現的結果推導
        elif t in ('decision', 'report'):
            set_band(n, 'main', BAND_SOURCE_DERIVED)   # decision／report 一律 main（版面上不參與區帶計算）
    for nid, n in g.nodes.items():   # 第二輪：群、子分析跟 plan（子分析可自己 explicit）；驗證與頂層結果
        t = n['type']
        if t == 'method' and '#' in nid:
            pid = nid[2:].split('#')[0]
            if nid in ed_sets['p:'] and not nid.endswith(GROUP_SUFFIX):
                explicit(n)
            else:
                follow(n, f'p:{pid}', plan_band(pid))
        elif t == 'result' and n.get('subtype') not in ('secondary', 'secondary_group', 'supporting'):
            if nid in ed_sets['r:']:
                explicit(n)
                continue
            owner = _text(n['meta'].get('plan_id'))
            if not (owner and f'p:{owner}' in g.nodes):
                decl = n['meta'].get('declared_by') or []
                decl = sorted(decl, key=lambda d: 0 if plan_active.get(d[2:].split('#')[0]) else 1)   # 0.18.0：宣告以現行 plan 優先
                owner = decl[0][2:].split('#')[0] if decl else ''
            if owner:
                follow(n, f'p:{owner}', plan_band(owner))
            elif nid in cite_rank:
                set_band(n, q_band.get(question_order[cite_rank[nid][0]], 'main'), BAND_SOURCE_DERIVED)
            else:
                set_band(n, 'main', BAND_SOURCE_DERIVED)
        elif t == 'validation':
            sq = _text(n['meta'].get('sq')) or plan_sq.get(_text(n['meta'].get('plan_id')), '')
            if nid in ed_sets['v:']:
                explicit(n)
            else:
                follow(n, f'p:{_text(n["meta"].get("plan_id"))}', q_band.get(f'q:{sq}', 'main'))
    for nid, n in g.nodes.items():   # 第三輪：支撐結果跟主結果、次要結果（聚合節點）跟宣告它的子分析（即跟 plan）
        if n['type'] == 'result' and n.get('subtype') == 'supporting':
            follow(n, n['parent'], g.nodes[n['parent']]['band'])
        elif n['type'] == 'result' and n.get('subtype') in ('secondary', 'secondary_group'):
            if n.get('parent') and n['parent'] in g.nodes:
                follow(n, n['parent'], g.nodes[n['parent']]['band'])
            else:
                owner = _text(n['meta'].get('plan_id')) or ((n['meta'].get('declared_by') or ['p:'])[0][2:].split('#')[0])
                follow(n, f'p:{owner}', plan_band(owner) if owner else 'main')
    for nid, n in g.nodes.items():   # 圖表（缺 role）：呈現的結果全在同一區帶 → 那一帶（含 ext）；否則 main
        if n['type'] == 'figure' and n['meta'].get('role_source') == 'derived':
            srcs = [g.nodes[e['from']]['band'] for e in g.edges if e['type'] == 'depicts' and e['to'] == nid]
            n['band'] = srcs[0] if srcs and all(b == srcs[0] for b in srcs) else 'main'
    # 0.18.1 問題帶（strip）：每個非決策節點追溯到所屬問題——問題＝自己（q:main 也是自己，但不成帶）；plan／群／子分析＝plan 的 sq；
    # 驗證＝item 的 sq（缺才用 plan_id 的 sq）；結果＝owner plan 的 sq（沒有 plan 只被 goals 引用 → goals 順序最前的引用問題）；
    # 次要／支撐結果跟父；圖表＝呈現的結果的問題中 goals 順序最前者；找不到問題的節點（孤兒）strip 為空字串（ORPHAN_STRIP）。
    # 決策節點不帶 strip（版面上依 refers 邊掛到對應問題那條帶，見 layout_graph 的 _decision_strip）
    strip_qs = set(question_order[1:])

    def strip_of_q(sq: str) -> str:
        return f'q:{sq}' if sq and f'q:{sq}' in strip_qs else ORPHAN_STRIP

    for nid, n in g.nodes.items():
        t = n['type']
        if t == 'question':
            n['strip'] = nid
        elif t == 'method':
            n['strip'] = strip_of_q(plan_sq.get(nid[2:].split('#')[0], ''))
        elif t == 'validation':
            n['strip'] = strip_of_q(_text(n['meta'].get('sq')) or plan_sq.get(_text(n['meta'].get('plan_id')), ''))
        elif t == 'result' and n.get('subtype') not in ('secondary', 'supporting', 'secondary_group'):
            owner = _text(n['meta'].get('plan_id'))
            if not (owner and f'p:{owner}' in g.nodes):
                decl = sorted(n['meta'].get('declared_by') or [], key=lambda d: 0 if plan_active.get(d[2:].split('#')[0]) else 1)
                owner = decl[0][2:].split('#')[0] if decl else ''
            if owner:
                n['strip'] = strip_of_q(plan_sq.get(owner, ''))
            elif nid in cite_rank:
                n['strip'] = strip_of_q(question_order[cite_rank[nid][0]][2:])
            else:
                n['strip'] = ORPHAN_STRIP
    for nid, n in g.nodes.items():   # 次要（聚合）／支撐結果跟父（父不在圖裡就依 owner plan）
        if n['type'] == 'result' and n.get('subtype') in ('secondary', 'supporting', 'secondary_group'):
            if n.get('parent') and n['parent'] in g.nodes:
                n['strip'] = g.nodes[n['parent']]['strip']
            else:
                owner = _text(n['meta'].get('plan_id')) or ((n['meta'].get('declared_by') or ['p:'])[0][2:].split('#')[0])
                n['strip'] = strip_of_q(plan_sq.get(owner, '')) if owner else ORPHAN_STRIP
    for nid, n in g.nodes.items():   # 圖表：呈現的結果所屬問題中 goals 順序最前者；決策不帶 strip 欄位
        if n['type'] == 'figure':
            cands = [g.nodes[e['from']]['strip'] for e in g.edges if e['type'] == 'depicts' and e['to'] == nid]
            cands = [c for c in cands if c in strip_qs]
            n['strip'] = min(cands, key=lambda c: question_order.index(c)) if cands else ORPHAN_STRIP
        elif n['type'] == 'decision':
            n.pop('strip', None)
    # 跨區帶的邊除了 decomposes（主問題 → AQ）、depicts（結果 → 圖表）與 supplements（群 → 所屬 plan）一律預設不畫；
    # IR 仍保留（點選、顯示全部邊時才顯）
    for e in g.edges:
        if g.nodes[e['from']]['band'] != g.nodes[e['to']]['band'] and e['type'] not in CROSS_BAND_VISIBLE:
            e['default_visible'] = False
    # 遞移隱藏：p → r 的 produces 若已有可見的 p → v（validated_by）與 v → r（primary／robustness）覆蓋，預設不畫（IR 保留；點選節點
    # 或「顯示全部邊」仍顯）；沒有任何可見驗證邊覆蓋的結果維持可見（含虛線未宣告）
    vis_val: dict[str, set[str]] = {}    # p → 可見 validated_by 的 v
    vis_res: dict[str, set[str]] = {}    # v → 可見 primary／robustness 的 r
    for e in g.edges:
        if not e['default_visible']:
            continue
        if e['type'] == 'validated_by':
            vis_val.setdefault(e['from'], set()).add(e['to'])
        elif e['type'] in ('primary', 'robustness'):
            vis_res.setdefault(e['from'], set()).add(e['to'])
    for e in g.edges:
        if e['type'] == 'produces' and e['default_visible'] and any(e['to'] in vis_res.get(v, ()) for v in vis_val.get(e['from'], ())):
            e['default_visible'] = False
            e['meta']['via_validation'] = True
    # 0.16.5：驗證 → 支撐結果的 primary／robustness 邊，若同一個驗證 item 已有可見邊連到它的主結果，預設不畫（主結果 → 支撐結果的 L 形線
    # 已表達巢狀；驗證邊從左側進入支撐結果會與 L 形線的垂直段相交）；IR 保留、點選或「顯示全部邊」仍顯。主結果與支撐結果由不同 item
    # 驗證時維持可見（交叉屬資料，不是版面）
    for e in g.edges:
        if e['type'] in ('primary', 'robustness') and e['default_visible']:
            tn = g.nodes[e['to']]
            if tn.get('subtype') == 'supporting' and tn.get('parent') in vis_res.get(e['from'], ()):
                e['default_visible'] = False
                e['meta']['via_main_result'] = tn['parent']

    # shared：問題兩兩沿下游邊（plans／validated_by／primary／produces／cites，含 hidden）走；
    # via 寫 model:<model_id>（比對方法節點 meta.models）、r:<key>、v:<id>
    out_adj: dict[str, list[str]] = {}
    for e in g.edges:
        if e['type'] in DOWNSTREAM_TYPES:
            out_adj.setdefault(e['from'], []).append(e['to'])

    def reach(start: str) -> set[str]:
        seen: set[str] = set()
        stack = [start]
        while stack:
            cur = stack.pop()
            for nxt in out_adj.get(cur, []):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    reaches = {qid: reach(qid) for qid in question_order}

    def models_of(reached: set[str]) -> set[str]:
        out: set[str] = set()
        for nid in reached:
            if nid.startswith('p:'):
                out.update(g.nodes[nid]['meta'].get('models', []))
        return out

    shared = []
    for i, a in enumerate(question_order):
        for b in question_order[i + 1:]:
            via = [f'model:{m}' for m in sorted(models_of(reaches[a]) & models_of(reaches[b]))]
            common = reaches[a] & reaches[b]
            via += sorted(n for n in common if n.startswith('r:'))
            via += sorted(n for n in common if n.startswith('v:'))
            via += sorted(n for n in common if n.startswith('f:'))
            if via:
                kinds = [t for t, pre in (('method', 'model:'), ('result', 'r:'), ('validation', 'v:'), ('figure', 'f:'))
                         if any(v.startswith(pre) for v in via)]
                shared.append({'a': a, 'b': b, 'via': via, 'kinds': kinds})

    # 固定列序（全欄都有）：question 依 lanes；method 依（問題順序, 版本）；validation 依（問題順序, item 序）；
    # result 依（問題順序, primary 先→其他→dangling, 現行 plan 的宣告序）；decision 依 id
    def plan_rank(pid: str) -> tuple:
        sq = plan_sq.get(pid, '')
        return (q_index.get(f'q:{sq}', BIG), g.nodes[f'p:{pid}']['meta'].get('version', BIG), pid)

    rank: dict[str, tuple] = {}
    for i, qid in enumerate(question_order):
        rank[qid] = (i,)
    for pid in plan_sq:
        rank[f'p:{pid}'] = plan_rank(pid) + (0, 0)
        if pid in group_of:
            rank[group_of[pid]] = plan_rank(pid) + (1,)      # 群緊接在 plan 之後、在它的子項之前
        for si, sub in enumerate(sens_of.get(pid, [])):
            rank[sub] = plan_rank(pid) + (1, si + 1)
    rank.update(vrank)
    rank.update(rank_hint)
    rank.update(fig_rank)   # 圖表依（第一個相連結果的列序, manifest 序）
    rank[REPORT_ID] = (BIG, BIG, BIG, BIG, BIG, BIG, REPORT_ID)   # 0.19.0 report 節點：圖表欄最後（孤兒帶）
    for nid, n in g.nodes.items():
        if n['type'] == 'decision':
            rank[nid] = (nid,)
    strips_out = layout_graph(g, rank, question_order, src.infos)

    by_type = {t: 0 for t, _ in NODE_TYPES}
    for n in g.nodes.values():
        by_type[n['type']] += 1
    unvalidated = sum(1 for key in result_objs if key not in validated_by)
    figures_unreviewed = sum(1 for n in g.nodes.values() if n['type'] == 'figure' and n['state'] != 'done')
    secondary = sum(1 for key in result_objs if key in agg_of_key)   # 0.19.0：仍是鍵數（聚合節點數另計 secondary_groups）
    undeclared = sum(1 for key in result_objs if key not in agg_of_key and g.nodes[f'r:{key}']['meta'].get('result_kind') == 'undeclared')
    sensitivity_items = sum(1 for n in g.nodes.values() if n.get('subtype') == 'sensitivity')
    supporting = sum(1 for n in g.nodes.values() if n.get('subtype') == 'supporting')
    sensitivity_groups = sum(1 for n in g.nodes.values() if n.get('subtype') == 'sensitivity_group')
    secondary_groups = sum(1 for n in g.nodes.values() if n.get('subtype') == 'secondary_group')
    figures_uncited = len(rmeta['uncited_main_figures'])
    band_count = {b: sum(1 for n in g.nodes.values() if n['band'] == b) for b in BANDS}
    graph = {
        'node_types': [{'id': t, 'label': lbl} for t, lbl in NODE_TYPES],
        'edge_types': [{'id': t, 'label': lbl} for t, lbl in EDGE_TYPES],
        'nodes': list(g.nodes.values()),
        'edges': g.edges,
        'shared': shared,
        'question_aliases': dict(aliases),
        'strips': strips_out,
    }
    # (C5) 預設檢視的交叉與穿過節點計數：路由一次（與 _svg_graph 同一套、決定性）
    route, shown, _drawn = _default_route(graph)
    by_id = {n['id']: n for n in graph['nodes']}
    crossings, pairs, overlaps = crossing_stats(by_id, shown, default_view_lines(by_id, graph['edges'], route))
    if crossings:
        src.warnings.append(f'關聯圖預設檢視有 {crossings} 處線段交叉（前 {len(pairs)} 對，邊 idx:型別:段）：' + '；'.join(pairs))
    if overlaps:
        src.warnings.append(f'關聯圖預設檢視有 {overlaps} 處線段穿過可見節點')
    graph['stats'] = {'nodes': len(g.nodes), 'edges': len(g.edges), 'by_type': by_type,
                      'shared_pairs': len(shared), 'dangling_result_keys': len(dangling),
                      'unvalidated_result_keys': unvalidated, 'figures_unreviewed': figures_unreviewed,
                      'secondary_result_keys': secondary, 'undeclared_result_keys': undeclared,
                      'sensitivity_items': sensitivity_items, 'sensitivity_groups': sensitivity_groups, 'supporting_result_keys': supporting,
                      'secondary_groups': secondary_groups, 'report_cited_figures': n_cited, 'report_uncited_main_figures': figures_uncited,
                      'band_main_nodes': band_count['main'], 'band_ext_nodes': band_count['ext'], 'band_supp_nodes': band_count['supp'],
                      'crossings': crossings, 'edge_node_overlaps': overlaps, 'strips': len(strips_out)}
    return graph


def band_frame(nodes: list[dict], shown: set[str], extra_rows: dict[str, list[float]] | None = None) -> dict:
    """由已定位的節點算三區帶（依 BANDS 順序累積）的框架，與 layout_graph／JS relayout 同一套定義：
    has[b]＝該區帶有可見節點（或 dummy 列）；has_other＝main 以外任一區帶有可見節點（決定 main 是否畫標題列）；
    y0[b]＝節點起點；bottom[b]＝可見節點（不計決策；含 dummy 列）最低者的下緣；y_div[b]／y_title[b]＝分隔線與標題列頂
    （main 的標題列在 GRAPH_PAD、沒有分隔線）。沒有可見節點的區帶不佔高度：其 y_div／y_title／y0 仍照「接在上一個區帶之後」算
    （JS 對隱藏的元素也寫同樣的值），bottom 維持上一個區帶的 bottom。"""
    extra = extra_rows or {}
    has = {b: any(n['band'] == b and n['id'] in shown for n in nodes) or bool(extra.get(b)) for b in BANDS}
    has_other = any(has[b] for b in BANDS if b != 'main')
    y0: dict[str, float] = {}
    y_div: dict[str, float] = {}
    y_title: dict[str, float] = {}
    bottom: dict[str, float] = {}
    prev = GRAPH_PAD
    for b in BANDS:
        if b == 'main':
            y_title[b] = GRAPH_PAD
            y_div[b] = GRAPH_PAD
            y0[b] = GRAPH_PAD + BAND_TITLE_H if has_other else GRAPH_PAD
        else:
            y_div[b] = prev + BAND_GAP / 2
            y_title[b] = prev + BAND_GAP
            y0[b] = prev + BAND_GAP + BAND_TITLE_H
        ys = [n['y'] for n in nodes if n['band'] == b and n['id'] in shown and n['type'] != 'decision'] + list(extra.get(b, []))
        if ys:
            bottom[b] = max(ys) + NODE_H
        elif b == 'main':
            bottom[b] = y0[b]
        else:
            bottom[b] = prev
        prev = bottom[b]
    return {'has': has, 'has_other': has_other, 'y0': y0, 'y_div': y_div, 'y_title': y_title, 'bottom': bottom}


def _cell_of(n: dict) -> tuple[str, int]:
    return (n['band'], n['col'])


def _top_of(nodes: dict[str, dict], nid: str) -> str:
    """沿 parent 鏈走到最上層祖先（plan／頂層結果／其他頂層節點）。"""
    cur = nid
    while nodes[cur].get('parent') and nodes[cur]['parent'] in nodes:
        cur = nodes[cur]['parent']
    return cur


def _decision_strip(nodes: dict[str, dict], edges: list[dict], did: str) -> str:
    """決策註記所掛的問題帶：沿它的 refers 邊（邊序＝decisions.yaml 的 question 欄先、links 後），第一個指到問題（q:main 除外）或
    plan 的目標決定——問題就是那條帶、plan 取 plan 的 strip；只掛 q:main、指到結果／決策、或沒有 refers 的放該區帶最後（ORPHAN_STRIP）。
    決策節點本身不帶 strip 欄位；JS 端 decisionStrip() 同義。"""
    for e in edges:
        if e['from'] != did or e['type'] != 'refers':
            continue
        t = nodes.get(e['to'])
        if t is None:
            continue
        if t['type'] == 'question' and e['to'] != MAIN_ID:
            return e['to']
        if t['type'] == 'method':
            return t.get('strip') or ORPHAN_STRIP
    return ORPHAN_STRIP


def band_strips(nodes: dict[str, dict], question_order: list[str]) -> dict[str, list[str]]:
    """每個區帶的問題帶順序＝goals 順序（q:main 不成帶）：問題節點在該區帶的問題，以及問題節點在別的區帶、但有節點落在這一帶的問題
    （例如 Extended Data 帶的圖表、manifest 指定 role 的補充圖表——SQ 的帶因此排在 Supplementary 的 AQ 之前、AQ 的帶排在 Main 的
    SQ 之後，靠近它們的來源區帶），最後有孤兒節點才有一條空字串帶。JS 端 stripsOf()／restripStaged() 同義。"""
    out: dict[str, list[str]] = {}
    for b in BANDS:
        present = {n.get('strip', '') for n in nodes.values() if n['band'] == b and n['type'] != 'decision' and n['id'] != MAIN_ID}
        qs = [q for q in question_order[1:] if (q in nodes and nodes[q]['band'] == b) or q in present]
        out[b] = qs + ([ORPHAN_STRIP] if ORPHAN_STRIP in present else [])
    return out


LAYOUT_SWEEP_ROUNDS = 4        # barycenter：初始由左向右一次，之後（由右向左、由左向右）最多幾輪
LAYOUT_SEARCH_EVALS = 600      # 局部搜尋：最多評估幾個候選版面（每次評估＝重排、路由、數交叉，約 3 ms）
LAYOUT_BIG_ITEMS = 2000        # 可見節點＋dummy 列超過此數：只做初始 barycenter（由左向右一次），略過往返掃描與局部搜尋（每次評估已達數十秒）


def layout_graph(g: Graph, rank: dict[str, tuple], question_order: list[str], notes: list[str] | None = None) -> list[dict]:
    """分層版面：欄＝type，三個區帶（main → ext → supp）由上而下累積；0.18.1 起每個區帶內再依問題分成橫向的問題帶（strip）——
    帶序見 band_strips()，帶內各欄（問題／方法／驗證／結果／圖表）從帶的第一列起各自往下排、帶高＝帶內最高那欄的列數，帶與帶之間留
    STRIP_GAP（1 列）；問題節點在帶的第一列；q:main 對 main 區帶問題欄的問題垂直居中。列序先依 rank、再以 barycenter 重排（C3，只在同帶
    同欄內重排）。回傳 graph.strips：[{band, question, y0, y1}]（y0＝帶的第一列頂、y1＝最後一列的下緣）。
    `order` 為同 (band, col) 內含 dummy 列與 collapsed 節點的整數序（沿帶序連續）；x／y 為收合檢視——collapsed 節點不佔列，y 借用同問題
    現行版的列（JS 展開時依 order 重排）。
    跳欄邊（來源與目標 |col 差| ≥ 2 且預設可見）在每個中間欄（目標的區帶與問題帶）預留一個不畫節點的 dummy 列，邊的 `via` 記
    [[col, y], …]、`via_order` 記各 dummy 在該 (band, col) 內的 order，供 JS relayout／路由與測試對帳（C2）。
    barycenter：每個 (band, strip, col) 內以區塊為單位排序——區塊＝同一 plan（含舊版、群、子分析、次要結果）在該格內的節點，區塊內
    維持 rank 序、整體以區塊內第一個有鄰居的節點的 barycenter（鄰欄鄰居含 dummy，只算預設可見的邊；位置＝全圖列序）排，無鄰居的
    區塊維持現位；平手以現行 rank 序為準。問題欄維持 goals 順序、決策欄不參與（決策依 _decision_strip 掛到對應問題帶、從帶的第一列
    起往下疊，前一帶的決策疊過頭就接在其後），只重排方法／驗證／結果／圖表四欄：先由左向右只看左欄鄰居掃一次，之後（由右向左、
    由左向右）各只看該側鄰居，最多 LAYOUT_SWEEP_ROUNDS 輪、穩定即停，每次掃完以 C5 的實際交叉數評估、保留最少的版面；最後做區塊
    搬移的局部搜尋（每格每個區塊試搬到其他位置，只在交叉數減少時採用；交叉 0 或評估次數達 LAYOUT_SEARCH_EVALS 即停）。全程決定性。
    區帶框架：main 標題列只在其他區帶有可見節點時才畫（節點從 GRAPH_PAD + BAND_TITLE_H 起，否則從 GRAPH_PAD 起）；
    ext／supp 各自只在有可見節點時畫分隔線（上一區帶 bottom + BAND_GAP/2）與標題列（+ BAND_GAP），節點從 + BAND_TITLE_H 起；
    沒有可見節點的區帶不佔高度。JS relayout() 為同一套。"""
    nodes = g.nodes
    strips = band_strips(nodes, question_order)
    strip_of: dict[str, str] = {}
    for nid, n in nodes.items():
        if n['type'] == 'decision':
            s = _decision_strip(nodes, g.edges, nid)
            strip_of[nid] = s if s in strips[n['band']] else ORPHAN_STRIP
        elif nid == MAIN_ID:
            strip_of[nid] = MAIN_ID
        else:
            strip_of[nid] = n.get('strip', '') if n.get('strip', '') in strips[n['band']] else ORPHAN_STRIP
    cells: dict[tuple[str, str, int], list[str]] = {(b, s, c): [] for b in BANDS for s in strips[b] for c in range(N_COLS)}
    cells[('main', MAIN_ID, 0)] = []
    for b in BANDS:   # 決策欄的孤兒帶（只掛 q:main／無 refers 的決策）即使該區帶沒有孤兒節點也要有格子：放在全部問題帶之後
        cells.setdefault((b, ORPHAN_STRIP, N_COLS - 1), [])
    for nid, n in nodes.items():
        cells[(n['band'], strip_of[nid], n['col'])].append(nid)
    for ids in cells.values():
        ids.sort(key=lambda nid: (rank.get(nid, (BIG,)), nid))
    for nid, n in nodes.items():
        n['x'] = GRAPH_PAD + n['col'] * COL_PITCH + _indent(n)
    shown = {nid for nid, n in nodes.items() if not n['collapsed'] and n['type'] != 'decision'}
    current_of: dict[str, str] = {}
    for nid, n in nodes.items():
        if n['type'] == 'method' and not n['collapsed']:
            for old in n['meta'].get('superseded_versions', []):
                current_of[f'p:{old}'] = nid
    # 跳欄邊 → dummy 列（每條邊每個中間欄一列，落在目標的區帶與問題帶）；同時建 barycenter 用的鄰接（邊拆成逐欄段）
    dummy: dict[str, dict] = {}
    adj: dict[str, list[str]] = {}
    drawn: list[int] = []
    for i, e in enumerate(g.edges):
        e['via'] = []
        e['via_order'] = []
        if not e['default_visible'] or e['from'] not in shown or e['to'] not in shown:
            continue
        drawn.append(i)
        if e['type'] in L_EDGE_TYPES or e['type'] == 'supplements':
            continue
        a, b = nodes[e['from']], nodes[e['to']]
        step = 1 if b['col'] > a['col'] else -1
        chain = [e['from']]
        for c in range(a['col'] + step, b['col'], step):
            did = f'~{i}@{c}'
            dummy[did] = {'edge': i, 'band': b['band'], 'strip': strip_of[e['to']], 'col': c}
            cells[(b['band'], strip_of[e['to']], c)].append(did)
            chain.append(did)
        chain.append(e['to'])
        for u, v in zip(chain, chain[1:]):
            adj.setdefault(u, []).append(v)
            adj.setdefault(v, []).append(u)

    def block_key(item: str) -> str:
        if item in dummy:
            return item
        top = _top_of(nodes, item)
        return current_of.get(top, top)

    # 區塊：每格依初始（rank）序把同 key 的節點收成區塊（區塊內維持初始序）；區塊初始序＝第一個成員的初始序
    blocks: dict[tuple[str, str, int], list[list[str]]] = {}
    for cell, ids in cells.items():
        by_key: dict[str, list[str]] = {}
        for item in ids:
            by_key.setdefault(block_key(item), []).append(item)
        blocks[cell] = list(by_key.values())
    init_index: dict[tuple[str, str, int], dict[int, int]] = {cell: {id(bl): bi for bi, bl in enumerate(bls)} for cell, bls in blocks.items()}
    # 帶高（列數）與版面上的順序不相干：帶內最高那欄佔列的項目數（可見節點＋dummy；決策與 q:main 不算）；帶的全圖列序起點供 barycenter 比較
    strip_rows: dict[tuple[str, str], int] = {}
    strip_row0: dict[tuple[str, str], int] = {}
    running = 0
    for b in BANDS:
        for s in strips[b]:
            rows = max([sum(1 for x in cells[(b, s, c)] if x in dummy or x in shown) for c in range(N_COLS - 1)] + [0])
            strip_rows[(b, s)] = rows
            strip_row0[(b, s)] = running
            running += rows + 1
    pos: dict[str, int] = {}

    def refresh_pos(cell: tuple[str, str, int]) -> None:
        k = strip_row0.get((cell[0], cell[1]), 0)
        for bl in blocks[cell]:
            for item in bl:
                pos[item] = k
                k += 1

    for cell in blocks:
        refresh_pos(cell)

    def cell_col(item: str) -> int:
        return dummy[item]['col'] if item in dummy else nodes[item]['col']

    def bary(bl: list[str], side: int) -> float | None:
        """區塊的 barycenter＝區塊內第一個有（該側）鄰居的節點的鄰居平均位置（全圖列序）；side：-1 只算左欄、+1 只算右欄。"""
        for item in bl:
            c = cell_col(item)
            nbs = [pos[x] for x in adj.get(item, []) if x in pos and (cell_col(x) - c) * side > 0]
            if nbs:
                return sum(nbs) / len(nbs)
        return None

    def sort_cell(cell: tuple[str, str, int], side: int) -> bool:
        """該側沒有鄰居的區塊固定在原槽位（例如沒有結果鍵的圖表），其餘區塊在剩下的槽位間依 (barycenter, 初始序) 排。"""
        bls = blocks[cell]
        if len(bls) < 2:
            return False
        fixed: dict[int, list[str]] = {}
        movable = []
        for slot, bl in enumerate(bls):
            bv = bary(bl, side)
            if bv is None:
                fixed[slot] = bl
            else:
                movable.append((bv, init_index[cell][id(bl)], bl))
        movable.sort(key=lambda t: (t[0], t[1]))
        it = iter(movable)
        new_bls = [fixed[slot] if slot in fixed else next(it)[2] for slot in range(len(bls))]
        if [id(b) for b in new_bls] != [id(b) for b in bls]:
            blocks[cell] = new_bls
            refresh_pos(cell)
            return True
        return False

    frame_has = {b: any(x in dummy or x in shown for s in strips[b] for c in range(N_COLS) for x in cells[(b, s, c)]) for b in BANDS}
    frame_has['main'] = frame_has['main'] or MAIN_ID in shown
    has_other = any(frame_has[b] for b in BANDS if b != 'main')
    strip_out: list[dict] = []

    def place_all() -> None:
        """依目前的區塊序把 order／y 寫回節點與 dummy（含區帶累積、問題帶累積、collapsed 借列、q:main 居中、決策掛帶）。"""
        for cell, bls in blocks.items():
            cells[cell] = [item for bl in bls for item in bl]
        for b in BANDS:   # order：同 (band, col) 內沿帶序連續（決策欄的孤兒帶接在全部問題帶之後）
            for c in range(N_COLS):
                k = 0
                tail = [ORPHAN_STRIP] if c == N_COLS - 1 and ORPHAN_STRIP not in strips[b] else []
                for s in ([MAIN_ID] if (b, c) == ('main', 0) else []) + strips[b] + tail:
                    for item in cells.get((b, s, c), []):
                        if item in dummy:
                            dummy[item]['order'] = k
                        else:
                            nodes[item]['order'] = k
                        k += 1

        def place(band: str, y0: float) -> float:
            bottom = y0
            y = y0
            dec_y = y0
            for si, s in enumerate(strips[band]):
                if si:
                    y += STRIP_GAP
                rows_max = 0
                for c in range(N_COLS - 1):
                    row = 0
                    last_y = y
                    for item in cells[(band, s, c)]:
                        if item in dummy:
                            dummy[item]['y'] = y + row * ROW_GAP
                            row += 1
                            continue
                        n = nodes[item]
                        if n['collapsed']:
                            n['y'] = last_y
                        else:
                            n['y'] = y + row * ROW_GAP
                            last_y = n['y']
                            row += 1
                    rows_max = max(rows_max, row)
                dec_y = max(dec_y, y)
                for item in cells[(band, s, N_COLS - 1)]:   # 決策：從帶的第一列起往下疊，前一帶疊過頭就接在其後（不算入帶高）
                    nodes[item]['y'] = dec_y
                    dec_y += ROW_GAP
                y1 = y + (rows_max - 1) * ROW_GAP + NODE_H if rows_max else y
                strip_out.append({'band': band, 'question': s, 'y0': y, 'y1': y1})
                if rows_max:
                    bottom = max(bottom, y1)
                y += rows_max * ROW_GAP
            if ORPHAN_STRIP not in strips[band]:   # 只掛 q:main／無 refers 的決策：接在全部問題帶的決策之後
                for item in cells[(band, ORPHAN_STRIP, N_COLS - 1)]:
                    nodes[item]['y'] = dec_y
                    dec_y += ROW_GAP
            return bottom

        strip_out.clear()
        prev = GRAPH_PAD
        for b in BANDS:
            if b == 'main':
                prev = place(b, GRAPH_PAD + BAND_TITLE_H if has_other else GRAPH_PAD)
            elif frame_has[b]:
                prev = place(b, prev + BAND_GAP + BAND_TITLE_H)
        for old, cur in current_of.items():   # collapsed 舊版的 y 借用其現行版（同問題）的列，展開前不佔位
            if old in nodes:
                nodes[old]['y'] = nodes[cur]['y']
        for nid, n in nodes.items():   # 收合舊版的群、子分析、次要結果沿 parent 鏈找到舊版 plan → 現行版 → 借現行版的群（沒有群就借 plan）
            if n['collapsed'] and n.get('parent'):
                top = _top_of(nodes, nid)
                if top in current_of:
                    cur = current_of[top]
                    n['y'] = nodes[cur + GROUP_SUFFIX]['y'] if cur + GROUP_SUFFIX in nodes else nodes[cur]['y']
        if MAIN_ID in nodes:   # 主問題居中：main 區帶問題欄第一筆與最後一筆的中間（AQ 在 supp 區帶、dummy 不算）
            ys = [nodes[i]['y'] for s in strips['main'] for i in cells[('main', s, 1)] if i in nodes and not nodes[i]['collapsed']]
            if ys:
                mid = (min(ys) + max(ys)) / 2
                nodes[MAIN_ID]['y'] = int(mid) if float(mid).is_integer() else mid
            else:
                nodes[MAIN_ID]['y'] = GRAPH_PAD + BAND_TITLE_H if has_other else GRAPH_PAD
        for did, d in dummy.items():   # 跳欄邊的 via（來源 → 目標方向）
            e = g.edges[d['edge']]
            e['via'] = []
            e['via_order'] = []
        for did, d in dummy.items():
            e = g.edges[d['edge']]
            e['via'].append([d['col'], d['y']])
            e['via_order'].append(d['order'])
        for e in g.edges:
            if e['via']:
                rev = nodes[e['to']]['col'] < nodes[e['from']]['col']
                pairs = sorted(zip(e['via'], e['via_order']), key=lambda t: t[0][0], reverse=rev)
                e['via'] = [p_[0] for p_ in pairs]
                e['via_order'] = [p_[1] for p_ in pairs]

    def evaluate() -> int:
        place_all()
        route = route_edges(nodes, [(i, g.edges[i]) for i in drawn])
        return crossing_stats(nodes, shown, default_view_lines(nodes, g.edges, route), count_overlaps=False)[0]

    def snapshot() -> dict[tuple[str, str, int], list[list[str]]]:
        return {cell: list(bls) for cell, bls in blocks.items()}

    def restore(state: dict[tuple[str, str, int], list[list[str]]]) -> None:
        for cell, bls in state.items():
            blocks[cell] = list(bls)
            refresh_pos(cell)

    # 問題欄（欄 1）維持 goals 順序、決策欄不參與；只在同帶同欄內重排方法／驗證／結果／圖表四欄，不跨帶
    sortable = [(b, s, c) for b in BANDS for s in strips[b] for c in range(2, N_COLS - 1)]
    for cell in sortable:            # 初始：由左向右、只看左欄鄰居（把問題順序沿鏈傳下去、dummy 落在來源附近）
        sort_cell(cell, -1)
    n_items = len(shown) + len(dummy)
    if n_items > LAYOUT_BIG_ITEMS:   # 大圖：不做往返掃描與局部搜尋（評估一次即需數十秒）
        if notes is not None:
            notes.append(f'關聯圖版面：可見節點＋dummy 列共 {n_items} 項，超過 LAYOUT_BIG_ITEMS={LAYOUT_BIG_ITEMS}，'
                         'barycenter 只做初始由左向右一次，略過往返掃描與局部搜尋')
        place_all()
        return list(strip_out)
    best_n = evaluate()
    best = snapshot()
    evals = 1
    for _round in range(LAYOUT_SWEEP_ROUNDS):
        if best_n == 0:
            break
        changed = False
        for sweep, side in ((list(reversed(sortable)), 1), (sortable, -1)):
            moved = False
            for cell in sweep:
                moved = sort_cell(cell, side) or moved
            if not moved:
                continue
            changed = True
            n = evaluate()
            evals += 1
            if n < best_n:
                best_n, best = n, snapshot()
        if not changed:
            break
    restore(best)
    # 局部搜尋：每格每個區塊試搬到其他位置（搬移後另試「右鄰欄依左側 barycenter 修補」「再把左鄰欄依右側修補」兩個變體），
    # 交叉數減少就採用；交叉數相同但版面沒走過也採用（沿平台走，靠已走過集合避免打轉）；交叉 0 或評估次數達上限即停（決定性）
    def state_key() -> tuple:
        return tuple(tuple(bl[0] for bl in blocks[cell]) for cell in sortable)

    seen_states = {state_key()}
    cur_n = best_n
    improved = True
    while improved and best_n > 0 and evals < LAYOUT_SEARCH_EVALS:
        improved = False
        for cell in sortable:
            bls = blocks[cell]
            if len(bls) < 2:
                continue
            for i in range(len(bls)):
                if best_n == 0 or evals >= LAYOUT_SEARCH_EVALS:
                    break
                for j in range(len(bls)):
                    if j == i or evals >= LAYOUT_SEARCH_EVALS:
                        continue
                    base = snapshot()
                    trial = list(blocks[cell])
                    bl = trial.pop(i)
                    trial.insert(j, bl)
                    blocks[cell] = trial
                    refresh_pos(cell)
                    for repair in (None, (cell[0], cell[1], cell[2] + 1), (cell[0], cell[1], cell[2] - 1)):
                        if evals >= LAYOUT_SEARCH_EVALS:
                            break
                        if repair is not None:
                            if repair not in sortable or not sort_cell(repair, -1 if repair[2] > cell[2] else 1):
                                continue
                        key = state_key()
                        if key in seen_states:
                            continue
                        seen_states.add(key)
                        n = evaluate()
                        evals += 1
                        if n < cur_n or n == cur_n:
                            cur_n = n
                            improved = True
                            if n < best_n:
                                best_n, best = n, snapshot()
                            break
                    if improved:
                        break
                    restore(base)
                if improved:
                    break
            if improved:
                break
    restore(best)
    place_all()
    return list(strip_out)


def validate_graph(graph) -> list[str]:
    errors: list[str] = []
    if not isinstance(graph, dict):
        return ['IR-11 graph']
    for key in ('node_types', 'edge_types', 'nodes', 'edges', 'shared', 'question_aliases', 'stats', 'strips'):
        if key not in graph:
            errors.append(f'IR-11 graph.{key}')
    if errors:
        return errors
    ntypes = {t.get('id') for t in graph['node_types'] if isinstance(t, dict)}
    etypes = {t.get('id') for t in graph['edge_types'] if isinstance(t, dict)}
    ids: set[str] = set()
    prefixes = set(NODE_PREFIX.values())
    for i, n in enumerate(graph['nodes'] if isinstance(graph['nodes'], list) else []):
        sub = f'graph.nodes[{i}]'
        if not isinstance(n, dict):
            errors.append(f'IR-12 {sub}')
            continue
        nid = n.get('id')
        if not isinstance(nid, str) or nid[:2] not in prefixes or len(nid) <= 2:
            errors.append(f'IR-12 {sub}.id')
        elif nid in ids:
            errors.append(f'IR-12 {sub}.id 重複')
        else:
            ids.add(nid)
        if n.get('type') not in ntypes or NODE_PREFIX.get(n.get('type')) != str(nid)[:2]:
            errors.append(f'IR-12 {sub}.type')
        for k in ('label', 'title', 'source', 'badge'):
            if not isinstance(n.get(k), str):
                errors.append(f'IR-12 {sub}.{k}')
        if n.get('state') not in STATES and n.get('state') != '':
            errors.append(f'IR-12 {sub}.state')
        meta = n.get('meta')
        if not isinstance(meta, dict):
            errors.append(f'IR-12 {sub}.meta')
        else:
            if n.get('type') == 'figure':
                for k in ('files', 'results_keys'):
                    if k in meta and not isinstance(meta[k], list):
                        errors.append(f'IR-12 {sub}.meta.{k}')
                if 'data_uri' in meta and not (isinstance(meta['data_uri'], str) and meta['data_uri'].startswith('data:')):
                    errors.append(f'IR-12 {sub}.meta.data_uri')
            if n.get('type') == 'result' and 'table' in meta:
                t = meta['table']
                if not isinstance(t, dict) or not isinstance(t.get('columns'), list) or not isinstance(t.get('rows'), list) \
                        or not isinstance(t.get('n_rows'), int) or not isinstance(t.get('truncated'), bool):
                    errors.append(f'IR-12 {sub}.meta.table')
        for k in ('x', 'y'):
            if isinstance(n.get(k), bool) or not isinstance(n.get(k), (int, float)):
                errors.append(f'IR-12 {sub}.{k}')
        for k in ('col', 'order'):
            if isinstance(n.get(k), bool) or not isinstance(n.get(k), int):
                errors.append(f'IR-12 {sub}.{k}')
        if n.get('type') in ntypes and n.get('col') != node_col(str(nid), n.get('type')):
            errors.append(f'IR-12 {sub}.col')
        if not isinstance(n.get('collapsed'), bool):
            errors.append(f'IR-12 {sub}.collapsed')
        st_ = n.get('subtype')
        if st_ not in SUBTYPES or (st_ and n.get('type') not in ('method', 'result')) \
                or (n.get('type') == 'method' and st_ not in METHOD_SUBTYPES) or (n.get('type') == 'result' and st_ not in RESULT_SUBTYPES):
            errors.append(f'IR-12 {sub}.subtype')
        if not isinstance(n.get('parent'), str):
            errors.append(f'IR-12 {sub}.parent')
        if n.get('band') not in BANDS:
            errors.append(f'IR-12 {sub}.band')
        elif n.get('type') == 'question' and n.get('band') == 'ext':
            errors.append(f'IR-12 {sub}.band（問題節點不能在 Extended Data 區帶）')   # 0.20.0：只有 SQ／AQ 不能放 ED
        if n.get('type') not in ('question', 'figure') and isinstance(meta, dict):   # 0.20.0：非問題非圖表節點都有 band_source（圖表沿用 role_source）
            bs = meta.get('band_source')
            if not (bs in (BAND_SOURCE_EXPLICIT, BAND_SOURCE_DERIVED) or (isinstance(bs, str) and bs.startswith(BAND_SOURCE_INHERITED) and len(bs) > len(BAND_SOURCE_INHERITED))):
                errors.append(f'IR-12 {sub}.meta.band_source')
            elif n.get('band') == 'ext' and bs == BAND_SOURCE_DERIVED:
                errors.append(f'IR-12 {sub}.meta.band_source（在 Extended Data 的節點須是 explicit 或 inherited:<來源>）')
            elif n.get('band') != 'ext' and bs != BAND_SOURCE_DERIVED:
                errors.append(f'IR-12 {sub}.meta.band_source（不在 Extended Data 的節點須是 derived）')
        if n.get('type') != 'decision':   # 0.18.1 問題帶：非決策節點都有 strip（問題節點是自己；孤兒空字串）；決策不帶
            if not isinstance(n.get('strip'), str):
                errors.append(f'IR-12 {sub}.strip')
            elif n.get('type') == 'question' and n.get('strip') != nid:
                errors.append(f'IR-12 {sub}.strip（問題節點的 strip 須是自己）')
    by_id_v = {n.get('id'): n for n in graph['nodes'] if isinstance(n, dict)} if isinstance(graph['nodes'], list) else {}
    for i, n in enumerate(graph['nodes'] if isinstance(graph['nodes'], list) else []):   # 0.20.0：inherited:<id> 的來源節點須存在、在 ext、且自己是 explicit
        meta = n.get('meta') if isinstance(n, dict) and isinstance(n.get('meta'), dict) else {}
        bs = meta.get('band_source')
        if isinstance(bs, str) and bs.startswith(BAND_SOURCE_INHERITED):
            srcn = by_id_v.get(bs[len(BAND_SOURCE_INHERITED):])
            smeta = srcn.get('meta') if isinstance(srcn, dict) and isinstance(srcn.get('meta'), dict) else {}
            if srcn is None or srcn.get('band') != 'ext' or smeta.get('band_source') != BAND_SOURCE_EXPLICIT:
                errors.append(f'IR-12 graph.nodes[{i}].meta.band_source（inherited 的來源節點須存在、在 Extended Data 且為 explicit）')
    # 0.18.1 graph.strips：[{band, question, y0, y1}]，依 BANDS 順序分組、同帶內 y 範圍遞增不重疊；每個非決策節點（q:main 除外）的
    # (band, strip) 都要有對應的帶、未收合者的 y 落在帶的範圍內、問題節點在帶的第一列
    strip_keys: dict[tuple[str, str], dict] = {}
    strips_v = graph['strips'] if isinstance(graph['strips'], list) else None
    if strips_v is None:
        errors.append('IR-15 graph.strips')
    else:
        last_band_i = -1
        last: dict | None = None
        for i, st in enumerate(strips_v):
            sub = f'graph.strips[{i}]'
            if not isinstance(st, dict) or st.get('band') not in BANDS or not isinstance(st.get('question'), str) \
                    or any(isinstance(st.get(k), bool) or not isinstance(st.get(k), (int, float)) for k in ('y0', 'y1')):
                errors.append(f'IR-15 {sub}')
                continue
            q = st['question']
            if q and (q == MAIN_ID or by_id_v.get(q, {}).get('type') != 'question'):
                errors.append(f'IR-15 {sub}.question')
            if st['y0'] > st['y1']:
                errors.append(f'IR-15 {sub}.y0／y1')
            key = (st['band'], q)
            if key in strip_keys:
                errors.append(f'IR-15 {sub} 重複')
            strip_keys[key] = st
            bi = BANDS.index(st['band'])
            if bi < last_band_i:
                errors.append(f'IR-15 {sub}.band（未依區帶順序）')
            elif bi == last_band_i and last is not None and st['y0'] <= last['y1']:
                errors.append(f'IR-15 {sub}.y0（與前一條帶重疊或交錯）')
            last_band_i, last = bi, st
        for i, n in enumerate(graph['nodes'] if isinstance(graph['nodes'], list) else []):
            if not isinstance(n, dict) or n.get('type') == 'decision' or n.get('id') == MAIN_ID or not isinstance(n.get('strip'), str):
                continue
            st = strip_keys.get((n.get('band'), n.get('strip')))
            if st is None:
                errors.append(f'IR-15 graph.nodes[{i}].strip（graph.strips 無此帶）')
            elif n.get('collapsed') is False and isinstance(n.get('y'), (int, float)):
                if not (st['y0'] <= n['y'] <= st['y1'] - NODE_H):
                    errors.append(f'IR-15 graph.nodes[{i}].y（不在所屬問題帶的範圍內）')
                elif n.get('type') == 'question' and n['y'] != st['y0']:
                    errors.append(f'IR-15 graph.nodes[{i}].y（問題節點須在帶的第一列）')
    for i, n in enumerate(graph['nodes'] if isinstance(graph['nodes'], list) else []):
        if not isinstance(n, dict) or not n.get('parent'):
            continue
        par = by_id_v.get(n.get('parent'))
        nid = str(n.get('id'))
        if par is None:
            errors.append(f'IR-12 graph.nodes[{i}].parent')
        elif n.get('type') == 'result' and n.get('subtype') == 'supporting':
            # 0.16.5 支撐結果：parent 必須是同 plan 的頂層主要結果、meta.supports＝parent 的鍵、同一區帶
            meta = n.get('meta') if isinstance(n.get('meta'), dict) else {}
            pmeta = par.get('meta') if isinstance(par.get('meta'), dict) else {}
            if not (par.get('type') == 'result' and not par.get('parent') and par.get('subtype') == 'primary'
                    and f'r:{meta.get("supports")}' == n.get('parent') and meta.get('result_kind') == 'primary'
                    and (not pmeta.get('plan_id') or not meta.get('plan_id') or pmeta.get('plan_id') == meta.get('plan_id'))):
                errors.append(f'IR-12 graph.nodes[{i}].parent（supports）')
            elif n.get('band') != par.get('band'):
                errors.append(f'IR-12 graph.nodes[{i}].band（支撐結果須與主結果同一區帶）')
        elif n.get('type') == 'result' and not (par.get('type') == 'method' and par.get('subtype') == 'sensitivity'):
            errors.append(f'IR-12 graph.nodes[{i}].parent')
        elif n.get('type') == 'result' and n.get('subtype') == 'secondary_group' and nid != f'r:{str(n.get("parent"))[2:]}{SECONDARY_SUFFIX}':
            errors.append(f'IR-12 graph.nodes[{i}].id（聚合節點 id 須是 r:<子分析>{SECONDARY_SUFFIX}）')
        elif n.get('subtype') == 'sensitivity' and n.get('parent') != nid.split('#')[0] + GROUP_SUFFIX:
            errors.append(f'IR-12 graph.nodes[{i}].parent')   # 子分析的 parent 必須是同 plan 的敏感性分析群
        elif n.get('subtype') == 'sensitivity_group' and not (n.get('parent') == nid[:-len(GROUP_SUFFIX)] and nid.endswith(GROUP_SUFFIX)
                                                              and par.get('type') == 'method' and not par.get('parent')):
            errors.append(f'IR-12 graph.nodes[{i}].parent')   # 群的 parent 必須是所屬的頂層 plan
        elif n.get('band') != par.get('band') and not (n.get('subtype') == 'sensitivity' and n.get('band') == 'ext'
                                                        and (n.get('meta') or {}).get('band_source') == BAND_SOURCE_EXPLICIT):
            # 0.18.0：群與子分析的區帶跟所屬 plan、次要結果跟宣告它的子分析（三者都是「跟父」）；0.20.0：子分析自己列在 extended-data.yaml（explicit）時可獨自在 ext
            errors.append(f'IR-12 graph.nodes[{i}].band（{"敏感性分析群須與所屬 plan" if n.get("subtype") == "sensitivity_group" else "子分析須與群（自己列在 extended-data.yaml 者除外）" if n.get("subtype") == "sensitivity" else "次要結果須與子分析"}同一區帶）')
    # 0.19.0 宣告粒度：每個敏感性子分析至多一個 secondary_group 聚合節點，有則 meta.n_keys ≥ 1（沒自有次要鍵的子分析不該有）；
    # meta.keys 為 [{key, registered, validated, …}]、n_keys 一致、鍵不得重複、已登錄鍵數加總 == stats.secondary_result_keys；report 節點至多一個
    agg_of_sub: dict[str, list[str]] = {}
    seen_keys: dict[str, str] = {}
    n_registered = 0
    n_report = 0
    for i, n in enumerate(graph['nodes'] if isinstance(graph['nodes'], list) else []):
        if not isinstance(n, dict):
            continue
        if n.get('type') == 'report':
            n_report += 1
            if n.get('parent') or n.get('subtype') or n.get('band') != 'main':
                errors.append(f'IR-12 graph.nodes[{i}]（report 節點須在 main 區帶、無 parent／subtype）')
        if n.get('type') != 'result' or n.get('subtype') != 'secondary_group':
            continue
        agg_of_sub.setdefault(str(n.get('parent')), []).append(str(n.get('id')))
        meta = n.get('meta') if isinstance(n.get('meta'), dict) else {}
        keys = meta.get('keys')
        if not isinstance(keys, list) or any(not (isinstance(k, dict) and isinstance(k.get('key'), str) and k.get('key')
                                                  and isinstance(k.get('registered'), bool) and isinstance(k.get('validated'), bool)) for k in keys) \
                or meta.get('n_keys') != len(keys) or meta.get('result_kind') != 'secondary' or not isinstance(meta.get('cited_by_figures'), list):
            errors.append(f'IR-12 graph.nodes[{i}].meta.keys／n_keys／result_kind／cited_by_figures')
            continue
        for k in keys:
            if k['key'] in seen_keys:
                errors.append(f'IR-12 graph.nodes[{i}].meta.keys[{k["key"]}] 已在 {seen_keys[k["key"]]}')
            seen_keys[k['key']] = str(n.get('id'))
            if k['registered']:
                n_registered += 1
        if not keys:
            errors.append(f'IR-12 graph.nodes[{i}].meta.n_keys（聚合節點須至少 1 個自有次要鍵；沒有自有鍵的子分析不建聚合節點）')
        elif len(keys) == 1 and n.get('label') != keys[0]['key']:
            errors.append(f'IR-12 graph.nodes[{i}].label（1 鍵須直接顯示鍵名）')
        elif len(keys) > 1 and n.get('label') != f'{SECONDARY_GROUP_LABEL} {len(keys)} 鍵':
            errors.append(f'IR-12 graph.nodes[{i}].label（多鍵須為「{SECONDARY_GROUP_LABEL} n 鍵」）')
    for nid, n in by_id_v.items():
        if n.get('type') == 'method' and n.get('subtype') == 'sensitivity' and len(agg_of_sub.get(nid, [])) > 1:
            errors.append(f'IR-12 graph.nodes[{nid}]（子分析至多一個次要結果聚合節點，實際 {len(agg_of_sub.get(nid, []))}）')
    for sub, aggs in agg_of_sub.items():
        if by_id_v.get(sub, {}).get('subtype') != 'sensitivity':
            errors.append(f'IR-12 graph.nodes[{aggs[0]}].parent（聚合節點的 parent 須是敏感性子分析）')
    if n_report > 1:
        errors.append(f'IR-12 graph.nodes（report 節點至多一個，實際 {n_report}）')
    if isinstance(graph.get('stats'), dict) and isinstance(graph['stats'].get('secondary_result_keys'), int) \
            and graph['stats']['secondary_result_keys'] != n_registered:
        errors.append(f'IR-14 graph.stats.secondary_result_keys（{graph["stats"]["secondary_result_keys"]}）≠ 聚合節點已登錄鍵數加總（{n_registered}）')
    group_targets: dict[str, list] = {}
    for i, e in enumerate(graph['edges'] if isinstance(graph['edges'], list) else []):
        sub = f'graph.edges[{i}]'
        if not isinstance(e, dict):
            errors.append(f'IR-13 {sub}')
            continue
        if e.get('from') not in ids:
            errors.append(f'IR-13 {sub}.from')
        if e.get('to') not in ids:
            errors.append(f'IR-13 {sub}.to')
        if e.get('type') not in etypes:
            errors.append(f'IR-13 {sub}.type')
        if not isinstance(e.get('source'), str) or not e.get('source'):
            errors.append(f'IR-13 {sub}.source')
        if not isinstance(e.get('label'), str) or not isinstance(e.get('meta'), dict):
            errors.append(f'IR-13 {sub}.label／meta')
        if not isinstance(e.get('default_visible'), bool):
            errors.append(f'IR-13 {sub}.default_visible')
        if e.get('style') not in EDGE_STYLES:
            errors.append(f'IR-13 {sub}.style')
        via, via_order = e.get('via'), e.get('via_order')
        if not isinstance(via, list) or not isinstance(via_order, list) or len(via) != len(via_order) \
                or any(not (isinstance(v, list) and len(v) == 2 and isinstance(v[0], int) and not isinstance(v[0], bool)
                            and 0 <= v[0] < N_COLS and isinstance(v[1], (int, float)) and not isinstance(v[1], bool)) for v in via) \
                or any(isinstance(o, bool) or not isinstance(o, int) for o in via_order):
            errors.append(f'IR-13 {sub}.via／via_order')
        a, b = by_id_v.get(e.get('from')), by_id_v.get(e.get('to'))
        if a is None or b is None:
            continue
        if e.get('type') == 'supports':   # 主結果 → 支撐結果：from 頂層結果、to 的 parent 就是 from 且 subtype supporting
            if not (a.get('type') == 'result' and not a.get('parent') and b.get('type') == 'result' and b.get('subtype') == 'supporting'
                    and b.get('parent') == e.get('from')):
                errors.append(f'IR-13 {sub} supports 邊兩端不是「頂層主結果 → 其支撐結果」')
        if e.get('type') == 'supplements':
            errors.append(f'IR-13 {sub}.type supplements 已停用（0.18.0 起群縮排在所屬 plan 之下，不再有敏感性對照邊）')
        if e.get('type') == 'embedded_in' and not (a.get('type') == 'figure' and b.get('type') == 'report'):
            errors.append(f'IR-13 {sub} embedded_in 邊只能從圖表指向 report 節點')
        if e.get('type') == 'sensitivity' and a.get('type') == 'method' and not a.get('parent') and b.get('subtype') == 'sensitivity_group':
            # 0.18.0：plan → 群的 sensitivity 邊：群的 parent 就是 from；active（未收合）的群恰一條且預設可見
            if b.get('parent') != e.get('from'):
                errors.append(f'IR-13 {sub}.to 非該 plan 的敏感性分析群')
            else:
                group_targets.setdefault(str(b.get('id')), []).append(bool(e.get('default_visible')))
        if a.get('band') != b.get('band') and e.get('type') not in CROSS_BAND_VISIBLE and e.get('default_visible') is True:
            errors.append(f'IR-13 {sub}.default_visible 跨區帶')
        if isinstance(via, list) and via and e.get('default_visible') is not True:
            errors.append(f'IR-13 {sub}.via 只准預設可見的跳欄邊')
    for nid, n in by_id_v.items():   # 每個 active（未收合）的群：所屬 plan → 群恰一條預設可見的 sensitivity 邊（L 形父子線）
        if n.get('subtype') == 'sensitivity_group' and n.get('collapsed') is False:
            if group_targets.get(nid, []) != [True]:
                errors.append(f'IR-13 graph.nodes[{nid}].sensitivity（plan → 群）')
    qa = graph['question_aliases']
    if not isinstance(qa, dict):
        errors.append('IR-14 graph.question_aliases')
    else:
        for old, new in qa.items():   # 舊 id → 現行問題：value 必須是存在的問題節點，key 不得自己也是節點
            if not isinstance(old, str) or not isinstance(new, str) or f'q:{new}' not in ids or f'q:{old}' in ids \
                    or by_id_v.get(f'q:{new}', {}).get('type') != 'question':
                errors.append(f'IR-14 graph.question_aliases[{old}]')
    for i, s in enumerate(graph['shared'] if isinstance(graph['shared'], list) else []):
        sub = f'graph.shared[{i}]'
        if not isinstance(s, dict) or s.get('a') not in ids or s.get('b') not in ids:
            errors.append(f'IR-14 {sub}')
            continue
        via = s.get('via')
        ok = isinstance(via, list) and all(isinstance(v, str) and (v.startswith('model:') or v in ids) for v in via)
        if not ok or not isinstance(s.get('kinds'), list):
            errors.append(f'IR-14 {sub}.via／kinds')
    stats = graph['stats']
    n_edges = len(graph['edges'] if isinstance(graph['edges'], list) else [])
    n_shared = len(graph['shared'] if isinstance(graph['shared'], list) else [])
    if not isinstance(stats, dict) or stats.get('nodes') != len(ids) or stats.get('edges') != n_edges or \
            stats.get('shared_pairs') != n_shared or not isinstance(stats.get('by_type'), dict) or \
            not isinstance(stats.get('dangling_result_keys'), int) or not isinstance(stats.get('unvalidated_result_keys'), int) \
            or not isinstance(stats.get('figures_unreviewed'), int) \
            or any(not isinstance(stats.get(k), int) for k in ('secondary_result_keys', 'undeclared_result_keys', 'sensitivity_items',
                                                                'sensitivity_groups', 'supporting_result_keys', 'band_main_nodes', 'band_ext_nodes',
                                                                'band_supp_nodes', 'crossings', 'edge_node_overlaps', 'strips', 'secondary_groups',
                                                                'report_cited_figures', 'report_uncited_main_figures')) \
            or stats.get('crossings') < 0 or stats.get('edge_node_overlaps') < 0:
        errors.append('IR-14 graph.stats')
    elif stats.get('band_main_nodes') + stats.get('band_ext_nodes') + stats.get('band_supp_nodes') != len(ids):
        errors.append('IR-14 graph.stats.band_main_nodes／band_ext_nodes／band_supp_nodes')
    elif strips_v is not None and stats.get('strips') != len(strips_v):
        errors.append('IR-14 graph.stats.strips')
    return errors


# ---------- 收件匣（唯讀） ----------

def build_inbox(src: Sources, graph: dict) -> dict:
    """讀 PROGRESS.inbox.yaml（唯讀）：回傳 IR 的 inbox 區塊，並把 pending 項掛到圖節點 meta.inbox／badge。"""
    st = src.status('inbox')
    if st == 'missing':
        return {'present': False, 'pending': 0, 'items': []}
    if st == 'broken':
        return {'present': False, 'pending': 0, 'items': []}   # Sources 已記 WARNING；視為無
    items = []
    for i, it in enumerate(_list(src.data('inbox').get('items'))):
        if not isinstance(it, dict):
            src.warnings.append(f'{REL["inbox"]}#items[{i}] 不是 mapping，略過')
            continue
        row = {k: _text(it.get(k)) for k in INBOX_FIELDS}
        row['id'] = row['id'] or f'items[{i}]'
        row['status'] = row['status'] or 'pending'
        # 結構化動作的 payload（0.16.0；只加欄位，schema_version 維持 1）；非 mapping 視為 {}
        row['payload'] = it.get('payload') if isinstance(it.get('payload'), dict) and row['kind'] in INBOX_ACTION_KINDS else {}
        items.append(row)
    by_id = {n['id']: n for n in graph.get('nodes', [])}
    agg_of: dict[str, str] = {}   # 0.19.0：target r:<次要鍵> → 收在該鍵所屬的聚合節點上
    for n in graph.get('nodes', []):
        if n.get('type') == 'result' and n.get('subtype') == 'secondary_group':
            for k in n['meta'].get('keys') or []:
                agg_of.setdefault(f'r:{k.get("key")}', n['id'])
    counts: dict[str, int] = {}
    for row in items:
        tid = row['target'] if row['target'] in by_id else agg_of.get(row['target'], '')
        if row['status'] == 'pending' and tid:
            n = by_id[tid]
            n['meta'].setdefault('inbox', []).append(row['id'])
            counts[tid] = counts.get(tid, 0) + 1
    for nid, k in counts.items():
        n = by_id[nid]
        n['badge'] = '、'.join(x for x in (n['badge'], f'收件 {k}') if x)
    pending = sum(1 for row in items if row['status'] == 'pending')
    return {'present': True, 'pending': pending, 'items': items}


# ---------- 文獻引用 3D 圖（唯讀） ----------

def _lit_empty(source: str, present: bool = False) -> dict:
    return {'source': source, 'present': present, 'demo': False, 'nodes': 0, 'edges': {},
            'max_cin': 0, 'data': {'nodes': [], 'edges': []}}


def _lit_global_citations(raw, nid: str, rel: str, warnings: list[str]) -> dict | None:
    """選填欄位 `global_citations` 的驗證：{count:int≥0, source:非空字串, retrieved:"YYYY-MM-DD"}。

    缺欄位＝常態，回 None 不記話。欄位在但不合格（型別不對、bool 當成 int、負數、缺鍵、日期寫錯）
    記一句 WARNING 並整個丟掉，不讓整張圖失敗——這是向下相容的選填欄位，schema 仍是 @1。
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        warnings.append(f'{rel} 節點 {nid} 的 global_citations 不是 object，丟掉這個欄位')
        return None
    missing = [k for k in LIT_GC_FIELDS if k not in raw]
    if missing:
        warnings.append(f'{rel} 節點 {nid} 的 global_citations 缺 {"、".join(missing)}，丟掉這個欄位')
        return None
    count = raw.get('count')
    if isinstance(count, bool) or not isinstance(count, int):
        warnings.append(f'{rel} 節點 {nid} 的 global_citations.count 不是整數，丟掉這個欄位')
        return None
    if count < 0:
        warnings.append(f'{rel} 節點 {nid} 的 global_citations.count 是負數（{count}），丟掉這個欄位')
        return None
    source = raw.get('source')
    if not isinstance(source, str) or not source.strip():
        warnings.append(f'{rel} 節點 {nid} 的 global_citations.source 不是非空字串，丟掉這個欄位')
        return None
    retrieved = raw.get('retrieved')
    ok_date = isinstance(retrieved, str) and LIT_DATE_RE.match(retrieved) is not None
    if ok_date:
        try:
            dt.date.fromisoformat(retrieved)
        except ValueError:
            ok_date = False
    if not ok_date:
        warnings.append(f'{rel} 節點 {nid} 的 global_citations.retrieved 不是 YYYY-MM-DD 的日期，丟掉這個欄位')
        return None
    return {'count': count, 'source': source.strip(), 'retrieved': retrieved}


def _lit_indegree_counts(nodes: list[dict], edges: list[dict]) -> list[int]:
    """每個節點的圈內被引數：有 `cites` 邊指向它的**不同 literature 來源節點**數。

    只數 `k == 'll'`（cites）的邊，兩端都要是文獻點；自我引用、指向不存在節點的邊、重複的邊在建
    `out_edges` 時就已經排掉，所以這裡直接數。問題點一律 0。跨專案同一條規則，不設門檻。
    """
    counts = [0] * len(nodes)
    for e in edges:
        s, t = e.get('s'), e.get('t')
        if e.get('k') != 'll':
            continue
        if isinstance(s, bool) or isinstance(t, bool) or not isinstance(s, int) or not isinstance(t, int):
            continue
        if not (0 <= s < len(nodes) and 0 <= t < len(nodes)) or s == t:
            continue
        if not isinstance(nodes[s], dict) or not isinstance(nodes[t], dict):
            continue                                   # 驗證時可能收到壞資料，這裡只數得出來的
        if nodes[s].get('q') == 0 and nodes[t].get('q') == 0:
            counts[t] += 1
    return counts


def _lit_indegree(nodes: list[dict], edges: list[dict]) -> int:
    """把圈內被引數寫進每個文獻點的 `cin`，回傳整張圖的最大值（沒有文獻點時 0）。"""
    counts = _lit_indegree_counts(nodes, edges)
    max_cin = 0
    for i, node in enumerate(nodes):
        if node.get('q') == 0:
            node['cin'] = counts[i]
            max_cin = max(max_cin, counts[i])
    return max_cin


def _lit_num(value) -> float | None:
    """只收 int／float（bool 不算）；其餘回 None。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def build_literature(src: Sources, path: Path | None = None) -> dict:
    """讀 literature/citation-graph.json（或 --literature-graph 指定的檔），整成前端可直接畫的資料。

    版面座標由產生資料的那支腳本算好寫在 `layout.coords`，這裡只讀不算——進度頁面每次改檔都重畫，
    600 篇規模的 3D 版面要十幾秒，不能放在渲染路徑上。問題點的說明文字一律取自 project.yaml 的
    goals（sub_questions ∪ appendix_questions），那裡是單一事實來源。

    回傳 {source, present, demo, nodes, edges:{kind: n}, data:{nodes, edges}}。
    缺檔＝空狀態（present False，不記 WARNING）；檔在但有問題（無法解析、schema 不符、邊指向不存在
    的 id、缺座標、問題 id 不在 goals）逐項記 WARNING 並略過那一筆，分頁照常出現。
    """
    p = (src.root / LIT_REL) if path is None else Path(path)
    try:
        rel = p.resolve().relative_to(src.root.resolve()).as_posix()
    except Exception:
        rel = str(p)
    if not p.is_file():
        return _lit_empty(rel)
    try:
        doc = json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(doc, dict):
            raise ValueError(f'頂層不是 object（實際 {type(doc).__name__}）')
    except Exception as exc:
        src.warnings.append(f'{rel} 無法解析: {_one_line(exc)}')
        return _lit_empty(rel, present=True)

    schema = _text(doc.get('schema'))
    if schema != LIT_SCHEMA:
        src.warnings.append(f'{rel} schema 不是 {LIT_SCHEMA}（實際 "{schema}"）；仍照 v1 的欄位讀')

    # 問題全文：project.yaml 的 goals 是單一事實來源
    proj = src.data('project') if src.status('project') == 'ok' else {}
    goals = _dict(proj.get('goals'))
    qtext: dict[str, str] = {}
    for name in ('sub_questions', 'appendix_questions'):
        for q in _list(goals.get(name)):
            qid = _text(_dict(q).get('id'))
            if qid:
                qtext[qid] = _text(_dict(q).get('question'))

    coords = _dict(_dict(doc.get('layout')).get('coords'))
    if not coords:
        src.warnings.append(f'{rel} 缺 layout.coords；沒有座標的點不畫')

    out_nodes: list[dict] = []
    index: dict[str, int] = {}
    for i, raw in enumerate(_list(doc.get('nodes'))):
        if not isinstance(raw, dict):
            src.warnings.append(f'{rel} nodes[{i}] 不是 object，略過')
            continue
        nid = _text(raw.get('id'))
        kind = _text(raw.get('kind'))
        if not nid:
            src.warnings.append(f'{rel} nodes[{i}] 缺 id，略過')
            continue
        if nid in index:
            src.warnings.append(f'{rel} 節點 id 重複: {nid}，略過後出現的那筆')
            continue
        if kind not in LIT_NODE_KINDS:
            src.warnings.append(f'{rel} 節點 {nid} 的 kind "{kind}" 不是 question／literature，略過')
            continue
        xyz = coords.get(nid)
        vals = [_lit_num(v) for v in xyz] if isinstance(xyz, (list, tuple)) and len(xyz) == 3 else []
        if len(vals) != 3 or any(v is None for v in vals):
            src.warnings.append(f'{rel} 節點 {nid} 在 layout.coords 沒有可用的座標，該點不畫')
            continue
        node = {'id': nid, 'q': LIT_NODE_KINDS[kind],
                'x': round(vals[0], 4), 'y': round(vals[1], 4), 'z': round(vals[2], 4)}
        if kind == 'question':
            if nid in qtext:
                node['note'] = qtext[nid]
            else:
                node['note'] = ''
                src.warnings.append(f'{rel} 問題點 {nid} 不在 project.yaml 的 goals，只顯示 id')
            if raw.get('global_citations') is not None:
                src.warnings.append(f'{rel} 問題點 {nid} 帶了 global_citations（只有文獻點能有），丟掉這個欄位')
        else:
            for f in LIT_STR_FIELDS:
                node[f] = _text(raw.get(f))
            year = raw.get('year')
            node['year'] = _text(year) if year is not None else ''
            gc = _lit_global_citations(raw.get('global_citations'), nid, rel, src.warnings)
            if gc is not None:
                node['gc'] = gc
        index[nid] = len(out_nodes)
        out_nodes.append(node)

    out_edges: list[dict] = []
    counts: dict[str, int] = {}
    seen_edges: set[tuple[int, int, str]] = set()
    for i, raw in enumerate(_list(doc.get('edges'))):
        if not isinstance(raw, dict):
            src.warnings.append(f'{rel} edges[{i}] 不是 object，略過')
            continue
        s, t, kind = _text(raw.get('source')), _text(raw.get('target')), _text(raw.get('kind'))
        if kind not in LIT_EDGE_KINDS:
            src.warnings.append(f'{rel} edges[{i}] 的 kind "{kind}" 不是 cited_for／cites，略過')
            continue
        if s not in index or t not in index:
            miss = '、'.join(x for x in (s if s not in index else '', t if t not in index else '') if x)
            src.warnings.append(f'{rel} edges[{i}] 指向不存在的節點 {miss}，略過')
            continue
        if s == t:
            src.warnings.append(f'{rel} edges[{i}] 的兩端都是 {s}，略過')
            continue
        key = (index[s], index[t], LIT_EDGE_KINDS[kind])
        if key in seen_edges:
            continue
        seen_edges.add(key)
        out_edges.append({'s': key[0], 't': key[1], 'k': key[2]})
        counts[kind] = counts.get(kind, 0) + 1

    max_cin = _lit_indegree(out_nodes, out_edges)
    return {'source': rel, 'present': True, 'demo': bool(doc.get('demo')),
            'nodes': len(out_nodes), 'edges': counts, 'max_cin': max_cin,
            'data': {'nodes': out_nodes, 'edges': out_edges}}


# ---------- 投稿檔案（第四個分頁；0.22.0） ----------
# 清單的衍生規則只有 skills/submission-prep/scripts/submission_package_common.py 那一份（derive()）：
# 入口＝manifest 有 role 的圖表／表格 ＋ results.json 的現行結果鍵，各自往回追程式碼、資料、結果與圖表檔。
# 本檔只做兩件事：把關聯圖既有的歸帶結果餵進去（省一次 build_ir），再把回傳值修剪成分頁要用的欄位。
# 規則不在這裡重寫；要改規則改那一份。

SUB_MODULE = 'skills/submission-prep/scripts/submission_package_common.py'
SUB_TIERS = ('main', 'extended', 'supplementary')
SUB_KINDS = ('code', 'data', 'result', 'figure', 'other')
SUB_TIER_LABEL = {'main': '正式文章', 'extended': '延伸資料', 'supplementary': '補充資料'}
SUB_TIER_BAND = {'main': 'main', 'extended': 'ext', 'supplementary': 'supp'}
SUB_KIND_LABEL = {'data': '資料', 'code': '程式碼', 'result': '結果', 'figure': '圖表', 'other': '其他'}
SUB_NODE_FIELDS = ('id', 'path', 'kind', 'tier', 'exists', 'missing', 'external', 'is_dir', 'n_files', 'bytes',
                   'packaged_path', 'entries', 'via', 'origin', 'note', 'badges', 'excluded', 'exclude_reason', 'counted')
SUB_ENTRY_FIELDS = ('id', 'kind', 'tier', 'label', 'type', 'figure_number', 'role', 'caption_first', 'status',
                    'plan_id', 'run_id', 'result_keys', 'badges', 'run_missing', 'excluded', 'exclude_reason', 'source')
SUB_ENTRY_PREFIX = {'figure': 'ef:', 'result': 'er:'}   # 入口 id 在 manifest 與 results.json 之間可能撞名，圖上的節點 id 加前綴
SUB_STAT_KEYS = ('entries', 'entries_excluded', 'entries_by_tier', 'entries_by_kind', 'nodes', 'nodes_excluded',
                 'nodes_by_kind', 'bytes', 'files', 'missing', 'blocking_missing', 'external', 'added')


def _sub_stats_zero() -> dict:
    return {'entries': 0, 'entries_excluded': 0, 'entries_by_tier': {t: 0 for t in SUB_TIERS},
            'entries_by_kind': {'figure': 0, 'result': 0}, 'nodes': 0, 'nodes_excluded': 0,
            'nodes_by_kind': {k: 0 for k in SUB_KINDS}, 'bytes': 0, 'files': 0, 'missing': 0,
            'blocking_missing': 0, 'external': 0, 'added': 0}


def _sub_empty(error: str = '', present: bool = False) -> dict:
    return {'source': SUB_MODULE, 'present': present, 'error': error, 'entries': [], 'nodes': {}, 'refs': [],
            'missing': [], 'blocking_missing': [], 'excluded': [], 'added': [], 'run_missing': {},
            'warnings': [], 'stats': _sub_stats_zero()}


def build_submission(root: Path, graph_nodes: list[dict]) -> dict:
    """投稿檔案分頁的資料（唯讀）：呼叫 derive()，歸帶沿用關聯圖已建好的節點，不重算也不重建 IR。

    模組載不進來、或 derive 出例外時回空狀態＋error：分頁照樣出現、只顯示錯誤訊息，不讓整頁渲染失敗。
    manifest／results.json 缺檔與 package.yaml 不存在都不是錯誤，是空狀態（derive 自己會記 warning）。
    """
    scripts_dir = Path(__file__).resolve().parents[2] / 'submission-prep' / 'scripts'
    try:
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import submission_package_common as SP
        view = SP.derive(root, key_bands=SP.bands_from_ir_nodes(graph_nodes))
    except Exception as exc:
        return _sub_empty(f'投稿清單衍生規則無法執行（{_one_line(exc)}）')
    try:
        out = {
            'source': SUB_MODULE,
            'present': bool(view['entries']),
            'error': '',
            'entries': [dict({k: e.get(k, '') if k not in ('result_keys', 'badges', 'run_missing') else e.get(k) or []
                              for k in SUB_ENTRY_FIELDS},
                             node_id=SUB_ENTRY_PREFIX[e['kind']] + e['id']) for e in view['entries']],
            'nodes': {nid: {k: n[k] for k in SUB_NODE_FIELDS} for nid, n in view['nodes'].items()},
            'refs': [{'from': r['from'], 'to': r['to'], 'via': r['via']} for r in view['edges']],
            'missing': list(view['missing']),
            'blocking_missing': list(view['blocking_missing']),
            'excluded': list(view['excluded']),
            'added': list(view['added']),
            'run_missing': dict(view.get('run_missing') or {}),
            'warnings': list(view['warnings']),
            'stats': {k: view['stats'][k] for k in SUB_STAT_KEYS},
        }
    except Exception as exc:      # derive 的 schema 與這裡的欄位對不上時同樣不讓整頁掛掉
        return _sub_empty(f'投稿清單的欄位與本頁預期不符（{_one_line(exc)}）')
    return out


def _validate_submission(sub) -> list[str]:
    """IR-17：投稿檔案分頁的資料。缺檔＝空狀態也要通過（present False、0 入口 0 節點）；derive 出例外時 error 非空、其餘全空。"""
    errors: list[str] = []
    if not isinstance(sub, dict):
        return ['IR-17 submission']
    for key in ('source', 'error'):
        if not isinstance(sub.get(key), str):
            errors.append(f'IR-17 submission.{key}')
    if not isinstance(sub.get('present'), bool):
        errors.append('IR-17 submission.present')
    for key in ('entries', 'refs', 'missing', 'blocking_missing', 'excluded', 'added', 'warnings'):
        if not isinstance(sub.get(key), list):
            errors.append(f'IR-17 submission.{key}')
    for key in ('nodes', 'run_missing', 'stats'):
        if not isinstance(sub.get(key), dict):
            errors.append(f'IR-17 submission.{key}')
    if errors:
        return errors
    if sub['error'] and (sub['entries'] or sub['nodes']):
        errors.append('IR-17 submission.error 非空時其餘要是空狀態')
    eids: set[str] = set()
    nids: set[str] = set()
    for i, e in enumerate(sub['entries']):
        pre = f'IR-17 submission.entries[{i}]'
        if not isinstance(e, dict) or not isinstance(e.get('id'), str) or not e['id']:
            errors.append(f'{pre}.id')
            continue
        eids.add(e['id'])
        if e.get('kind') not in ('figure', 'result'):
            errors.append(f'{pre}.kind')
        elif e.get('node_id') != SUB_ENTRY_PREFIX[e['kind']] + e['id']:
            errors.append(f'{pre}.node_id')
        elif e['node_id'] in nids:      # 同一個 id 可以同時是 manifest 的圖表與 results.json 的結果鍵，但同分類內必須唯一
            errors.append(f'{pre}.node_id 重複')
        nids.add(e.get('node_id') or '')
        if e.get('tier') not in SUB_TIERS:
            errors.append(f'{pre}.tier')
        if not isinstance(e.get('excluded'), bool):
            errors.append(f'{pre}.excluded')
        if not isinstance(e.get('badges'), list) or not isinstance(e.get('run_missing'), list):
            errors.append(f'{pre}.badges／run_missing')
        if not isinstance(e.get('result_keys'), list):
            errors.append(f'{pre}.result_keys')
        else:
            for j, it in enumerate(e['result_keys']):
                if not isinstance(it, dict) or not isinstance(it.get('key'), str) \
                        or any(not isinstance(it.get(k), bool) for k in ('historical', 'registered', 'is_entry')):
                    errors.append(f'{pre}.result_keys[{j}]')
    for nid, n in sub['nodes'].items():
        pre = f'IR-17 submission.nodes[{nid}]'
        if not isinstance(n, dict) or n.get('id') != nid:
            errors.append(f'{pre}.id')
            continue
        if n.get('kind') not in SUB_KINDS:
            errors.append(f'{pre}.kind')
        if n.get('tier') not in SUB_TIERS:
            errors.append(f'{pre}.tier')
        for key in ('missing', 'external', 'is_dir', 'excluded', 'counted'):
            if not isinstance(n.get(key), bool):
                errors.append(f'{pre}.{key}')
        for key in ('n_files', 'bytes'):
            if not isinstance(n.get(key), int) or isinstance(n.get(key), bool):
                errors.append(f'{pre}.{key}')
        if not isinstance(n.get('entries'), list) or not isinstance(n.get('badges'), list) or not isinstance(n.get('via'), list):
            errors.append(f'{pre}.entries／badges／via')
        elif any(x not in eids for x in n['entries']):
            errors.append(f'{pre}.entries 指到不存在的入口')
        if n.get('origin') not in ('derived', 'added'):
            errors.append(f'{pre}.origin')
    for i, r in enumerate(sub['refs']):
        if not isinstance(r, dict) or r.get('from') not in eids or r.get('to') not in sub['nodes']:
            errors.append(f'IR-17 submission.refs[{i}]')
    for nid in sub['missing'] + sub['blocking_missing']:
        if nid not in sub['nodes']:
            errors.append(f'IR-17 submission.missing {nid} 不在 nodes')
    st = sub['stats']
    for key in SUB_STAT_KEYS:
        if key not in st:
            errors.append(f'IR-17 submission.stats.{key}')
    if not errors:
        if st['missing'] != len(sub['missing']) or st['blocking_missing'] != len(sub['blocking_missing']):
            errors.append('IR-17 submission.stats.missing／blocking_missing')
        if st['added'] != len(sub['added']):
            errors.append('IR-17 submission.stats.added')
        if st['entries'] != sum(1 for e in sub['entries'] if not e['excluded']):
            errors.append('IR-17 submission.stats.entries')
        if st['nodes'] != sum(1 for n in sub['nodes'].values() if not n['excluded']):
            errors.append('IR-17 submission.stats.nodes')
        if set(st['entries_by_tier']) != set(SUB_TIERS) or set(st['nodes_by_kind']) != set(SUB_KINDS):
            errors.append('IR-17 submission.stats 分類鍵')
    return errors


# ---------- IR ----------

def build_ir(root: Path, src: Sources, generated_at: str, embed_figures: bool = False,
             literature_path: Path | None = None) -> dict:
    proj = src.data('project') if src.status('project') == 'ok' else {}
    meta = _dict(proj.get('project'))
    title = _text(meta.get('title_zh')) or _text(meta.get('title_en')) or root.name or str(root)
    next_stage = _text(_get(proj, 'state', 'next_stage'))
    lanes = build_lanes(src)
    for lane in lanes:
        judge_lane(src, lane, next_stage)
    attach_annotations(src, lanes)
    for lane in lanes:
        lane.pop('goal_list', None)
    stages = [{'id': sid, 'label': label, 'scope': 'sq', 'source': SQ_RULES[sid][0], 'rule': SQ_RULES[sid][1]}
              for sid, label in SQ_STAGES]
    stages += [{'id': sid, 'label': label, 'scope': 'project', 'source': PROJECT_RULES[sid][0], 'rule': PROJECT_RULES[sid][1]}
               for sid, label in PROJECT_STAGES]
    by_state = {s: 0 for s in STATES}
    n_nodes = 0
    for lane in lanes:
        for n in lane['nodes']:
            n_nodes += 1
            by_state[n['state']] = by_state.get(n['state'], 0) + 1
    graph = build_graph(src, lanes, embed_figures)
    inbox = build_inbox(src, graph)
    literature = build_literature(src, literature_path)
    submission = build_submission(root, graph['nodes'])
    return {
        'schema_version': SCHEMA_VERSION,
        'generated_at': generated_at,
        'project_root': str(root),
        'project': {'title': title, 'research_question': _text(meta.get('research_question')), 'current_stage': next_stage},
        'stages': stages,
        'lanes': lanes,
        'stats': {'lanes': len(lanes), 'nodes': n_nodes, 'by_state': by_state,
                  'annotations': sum(len(lane['annotations']) for lane in lanes), 'inbox_pending': inbox['pending']},
        'graph': graph,
        'inbox': inbox,
        'literature': literature,
        'submission': submission,
    }


def validate_ir(ir) -> list[str]:
    """IR 的自身 schema 驗證關卡。回傳錯誤清單（空＝通過），每條「IR-xx <主體>」。"""
    errors: list[str] = []
    if not isinstance(ir, dict):
        return ['IR-01 top-level 不是 object']
    for key in ('schema_version', 'generated_at', 'project_root', 'project', 'stages', 'lanes', 'stats', 'graph',
                'inbox', 'literature', 'submission'):
        if key not in ir:
            errors.append(f'IR-01 top-level.{key}')
    if ir.get('schema_version') != SCHEMA_VERSION:
        errors.append('IR-01 schema_version')
    stages = ir.get('stages')
    stage_ids: set[str] = set()
    if not isinstance(stages, list) or not stages:
        errors.append('IR-02 stages')
    else:
        seen: set[str] = set()
        for i, s in enumerate(stages):
            if not isinstance(s, dict) or not all(isinstance(s.get(k), str) and s.get(k) for k in ('id', 'label', 'scope')):
                errors.append(f'IR-02 stages[{i}]')
                continue
            if s['id'] in seen:
                errors.append(f'IR-02 stages[{i}].id 重複')
            seen.add(s['id'])
        stage_ids = seen
    lanes = ir.get('lanes')
    if not isinstance(lanes, list):
        errors.append('IR-03 lanes')
        lanes = []
    for li, lane in enumerate(lanes):
        if not isinstance(lane, dict):
            errors.append(f'IR-03 lanes[{li}]')
            continue
        for key in ('id', 'kind', 'label', 'question', 'status', 'status_reason'):
            if not isinstance(lane.get(key), str):
                errors.append(f'IR-03 lanes[{li}].{key}')
        if lane.get('kind') not in ('sq', 'aq', 'project'):
            errors.append(f'IR-03 lanes[{li}].kind')
        nodes = lane.get('nodes')
        if not isinstance(nodes, list):
            errors.append(f'IR-04 lanes[{li}].nodes')
            nodes = []
        for ni, n in enumerate(nodes):
            sub = f'lanes[{li}].nodes[{ni}]'
            if not isinstance(n, dict):
                errors.append(f'IR-04 {sub}')
                continue
            if n.get('stage') not in stage_ids:
                errors.append(f'IR-04 {sub}.stage')
            if n.get('state') not in STATES:
                errors.append(f'IR-05 {sub}.state')
            date = n.get('date')
            if not isinstance(date, str) or (date and not DATE_RE.fullmatch(date)):
                errors.append(f'IR-06 {sub}.date')
            if not isinstance(n.get('summary'), str):
                errors.append(f'IR-06 {sub}.summary')
            if not isinstance(n.get('current'), bool):
                errors.append(f'IR-06 {sub}.current')
            evidence = n.get('evidence')
            if not isinstance(evidence, list):
                errors.append(f'IR-07 {sub}.evidence')
            else:
                for ei, e in enumerate(evidence):
                    if not isinstance(e, dict) or not all(isinstance(e.get(k), str) for k in ('kind', 'value', 'source')):
                        errors.append(f'IR-07 {sub}.evidence[{ei}]')
                    elif e.get('kind') not in ('path', 'hash', 'run', 'value'):
                        errors.append(f'IR-07 {sub}.evidence[{ei}].kind')
            history = n.get('history')
            if not isinstance(history, list):
                errors.append(f'IR-08 {sub}.history')
            else:
                for hi, h in enumerate(history):
                    if not isinstance(h, dict) or not all(isinstance(h.get(k), str) for k in ('date', 'summary')):
                        errors.append(f'IR-08 {sub}.history[{hi}]')
        anns = lane.get('annotations')
        if not isinstance(anns, list):
            errors.append(f'IR-09 lanes[{li}].annotations')
        else:
            for ai, a in enumerate(anns):
                if not isinstance(a, dict) or not all(isinstance(a.get(k), str) for k in ('id', 'date', 'stage', 'summary', 'exec_issue', 'method')):
                    errors.append(f'IR-09 lanes[{li}].annotations[{ai}]')
    stats = ir.get('stats')
    if not isinstance(stats, dict) or not isinstance(stats.get('by_state'), dict):
        errors.append('IR-10 stats')
    else:
        n_nodes = sum(len(lane.get('nodes') or []) for lane in lanes if isinstance(lane, dict))
        if stats.get('lanes') != len(lanes) or stats.get('nodes') != n_nodes:
            errors.append('IR-10 stats.lanes／nodes')
        if any(k not in stats['by_state'] for k in STATES) or sum(stats['by_state'].get(k, 0) for k in STATES) != n_nodes:
            errors.append('IR-10 stats.by_state')
    errors.extend(validate_graph(ir.get('graph')))
    inbox = ir.get('inbox')
    if not isinstance(inbox, dict) or not isinstance(inbox.get('present'), bool) or not isinstance(inbox.get('pending'), int) \
            or not isinstance(inbox.get('items'), list):
        errors.append('IR-15 inbox')
    else:
        for i, it in enumerate(inbox['items']):
            if not isinstance(it, dict) or any(not isinstance(it.get(k), str) for k in INBOX_FIELDS) \
                    or ('payload' in it and not isinstance(it['payload'], dict)):
                errors.append(f'IR-15 inbox.items[{i}]')
        if sum(1 for it in inbox['items'] if isinstance(it, dict) and it.get('status') == 'pending') != inbox['pending']:
            errors.append('IR-15 inbox.pending')
        if isinstance(stats, dict) and stats.get('inbox_pending') != inbox['pending']:
            errors.append('IR-15 stats.inbox_pending')
    errors.extend(_validate_literature(ir.get('literature')))
    errors.extend(_validate_submission(ir.get('submission')))
    return errors


def _lit_gc_ok(gc) -> bool:
    """IR 裡的 `gc`（全球被引數）形狀是否合格。"""
    if not isinstance(gc, dict) or set(gc) != set(LIT_GC_FIELDS):
        return False
    count, source, retrieved = gc.get('count'), gc.get('source'), gc.get('retrieved')
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        return False
    if not isinstance(source, str) or not source:
        return False
    return isinstance(retrieved, str) and LIT_DATE_RE.match(retrieved) is not None


def _validate_literature(lit) -> list[str]:
    """IR-16：文獻引用 3D 圖的資料。缺檔＝空狀態也要通過（present False、0 點 0 線）。"""
    errors: list[str] = []
    if not isinstance(lit, dict):
        return ['IR-16 literature']
    if not isinstance(lit.get('source'), str) or not lit['source']:
        errors.append('IR-16 literature.source')
    for key in ('present', 'demo'):
        if not isinstance(lit.get(key), bool):
            errors.append(f'IR-16 literature.{key}')
    data = lit.get('data')
    if not isinstance(data, dict) or not isinstance(data.get('nodes'), list) or not isinstance(data.get('edges'), list):
        errors.append('IR-16 literature.data')
        return errors
    nodes, edges = data['nodes'], data['edges']
    if lit.get('nodes') != len(nodes):
        errors.append('IR-16 literature.nodes')
    counts = lit.get('edges')
    if not isinstance(counts, dict) or any(not isinstance(k, str) or not isinstance(v, int) or isinstance(v, bool)
                                           for k, v in counts.items()):
        errors.append('IR-16 literature.edges')
    elif sum(counts.values()) != len(edges):
        errors.append('IR-16 literature.edges 總數')
    elif any(k not in LIT_EDGE_KINDS for k in counts):
        errors.append('IR-16 literature.edges kind')
    max_cin = lit.get('max_cin')
    if isinstance(max_cin, bool) or not isinstance(max_cin, int) or max_cin < 0:
        errors.append('IR-16 literature.max_cin')
        max_cin = None
    want_cin = _lit_indegree_counts(nodes, edges)   # 顏色靠 cin，和邊對不上就是 BLOCKER，不讓它靜靜畫錯
    seen: set[str] = set()
    for i, n in enumerate(nodes):
        sub = f'literature.data.nodes[{i}]'
        if not isinstance(n, dict) or not isinstance(n.get('id'), str) or not n['id']:
            errors.append(f'IR-16 {sub}.id')
            continue
        if n['id'] in seen:
            errors.append(f'IR-16 {sub}.id 重複')
        seen.add(n['id'])
        if n.get('q') not in (0, 1) or isinstance(n.get('q'), bool):
            errors.append(f'IR-16 {sub}.q')
        if any(_lit_num(n.get(k)) is None for k in ('x', 'y', 'z')):
            errors.append(f'IR-16 {sub} 座標')
        if n.get('q') == 1:
            if not isinstance(n.get('note'), str):
                errors.append(f'IR-16 {sub}.note')
            if 'cin' in n or 'gc' in n:
                errors.append(f'IR-16 {sub} 問題點不該有 cin／gc')
        else:
            if any(not isinstance(n.get(k), str) for k in LIT_STR_FIELDS + ('year',)):
                errors.append(f'IR-16 {sub} 書目欄位')
            cin = n.get('cin')
            if isinstance(cin, bool) or not isinstance(cin, int) or cin < 0:
                errors.append(f'IR-16 {sub}.cin')
            elif cin != want_cin[i]:
                errors.append(f'IR-16 {sub}.cin 與邊不符')
            if 'gc' in n and not _lit_gc_ok(n['gc']):
                errors.append(f'IR-16 {sub}.gc')
    if max_cin is not None:
        got = max((n.get('cin', 0) for n in nodes
                   if isinstance(n, dict) and isinstance(n.get('cin'), int) and not isinstance(n.get('cin'), bool)),
                  default=0)
        if got != max_cin:
            errors.append('IR-16 literature.max_cin 不是最大值')
    for i, e in enumerate(edges):
        sub = f'literature.data.edges[{i}]'
        if not isinstance(e, dict):
            errors.append(f'IR-16 {sub}')
            continue
        if any(not isinstance(e.get(k), int) or isinstance(e.get(k), bool) or not (0 <= e[k] < len(nodes))
               for k in ('s', 't')):
            errors.append(f'IR-16 {sub} 端點')
        elif e['s'] == e['t']:
            errors.append(f'IR-16 {sub} 兩端相同')
        if e.get('k') not in set(LIT_EDGE_KINDS.values()):
            errors.append(f'IR-16 {sub}.k')
    return errors


# ---------- HTML ----------

CSS = """
:root{--bg:#fafaf8;--fg:#1f2328;--muted:#5b6470;--line:#d5d9de;--card:#ffffff;--proj:#eef3f7;--panel:#ffffff;
--done:#009e73;--expired:#e69f00;--blocked:#cc79a7;--pending:#8c939b;--unknown:#8c939b;--current:#0072b2;
--badge-blocked:#c2185b;--badge-addressed:#1b7f5c;--badge-open:#6b7280;--badge-dropped:#4b5563;
/* 文獻點的連續色階（0.22.0）：低＝淺、高＝深，每一階對 --card 的對比都 ≥ 3:1；換色只改這一組 */
--lit-ramp-0:#b0842a;--lit-ramp-1:#9a701d;--lit-ramp-2:#845c15;--lit-ramp-3:#6d4811;--lit-ramp-4:#57350e;--lit-ramp-5:#41240a;
--t-question:#4477aa;--t-method:#ccbb44;--t-validation:#228833;--t-result:#ee6677;--t-figure:#aa3377;--t-decision:#bbbbbb;--t-report:#66ccee;--t-lit:#a8751b;--up:#d55e00;--down:#0072b2;--path:#aa3377;--edge:#9aa3ad;--edge-thin:#b9c0c7;--edge-faint:#d3d8dd;--bg-none:#ffffff;--bg-done:#e2f4ee;--bg-expired:#fdf0d5;--bg-blocked:#f9e1ec;--bg-pending:#f2f3f4;--bg-sub:#f7f8f9;--bg-sub-done:#f0f9f5;--bg-sub-expired:#fef8ea;}
@media (prefers-color-scheme: dark){:root{--bg:#14171a;--fg:#e6e9ec;--muted:#a0a8b1;--line:#3a4048;--card:#1c2025;--proj:#1f2a33;--panel:#1c2025;
--done:#2ec4a0;--expired:#f2b134;--blocked:#e38fc4;--pending:#8d949c;--unknown:#8d949c;--current:#56b4e9;
/* 暗色主題反過來：低＝暗、高＝亮，每一階對暗色 --card 的對比一樣 ≥ 3:1 */
--lit-ramp-0:#9a7024;--lit-ramp-1:#b4872c;--lit-ramp-2:#cca03a;--lit-ramp-3:#e0b955;--lit-ramp-4:#eed27f;--lit-ramp-5:#f7e7ae;
--t-question:#6699cc;--t-method:#ddcc66;--t-validation:#44aa66;--t-result:#ee6677;--t-figure:#cc77aa;--t-decision:#888888;--t-report:#66ccee;--t-lit:#ddaa33;--up:#f08c3a;--down:#56b4e9;--path:#d88bbf;--edge:#6b7480;--edge-thin:#565e68;--edge-faint:#3e454d;--bg-none:#1c2025;--bg-done:#173a30;--bg-expired:#3f3418;--bg-blocked:#3f2233;--bg-pending:#262a2e;--bg-sub:#20252a;--bg-sub-done:#1b2f28;--bg-sub-expired:#302b1a;}}
*{box-sizing:border-box}
body{margin:0;padding:16px 20px 40px;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,"Segoe UI","Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif}
h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:22px 0 8px}
header p{margin:2px 0;color:var(--muted)}header .rq{color:var(--fg)}
.notice{font-size:12px;color:var(--muted)}
.controls{display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin:14px 0;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card)}
.controls label{display:inline-flex;align-items:center;gap:4px;cursor:pointer}
.legend{display:flex;flex-wrap:wrap;gap:16px;margin:8px 0 14px;font-size:13px}
.legend span{display:inline-flex;align-items:center;gap:6px}
.wrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--card)}
table.matrix{border-collapse:collapse;width:100%;min-width:640px}
table.matrix th,table.matrix td{border-bottom:1px solid var(--line);border-right:1px solid var(--line);padding:6px 8px;vertical-align:top;text-align:left}
table.matrix th{font-weight:600;font-size:12px;background:var(--proj);white-space:nowrap;position:sticky;top:0}
table.matrix th.lane,table.matrix td.lane{position:sticky;left:0;background:var(--card);min-width:120px;z-index:1}
table.matrix tr.project td.lane,table.matrix tr.project td{background:var(--proj)}
table.matrix th.lane{z-index:2}
.lane-id{font-weight:700}.lane-q{display:block;font-size:12px;color:var(--muted);max-width:220px}
.badge{display:inline-block;font-size:11px;line-height:1.4;padding:0 6px;border-radius:9px;color:#fff;margin-left:4px;vertical-align:middle}
.badge.blocked{background:var(--badge-blocked)}.badge.addressed{background:var(--badge-addressed)}.badge.open{background:var(--badge-open)}.badge.dropped{background:var(--badge-dropped)}
.node{display:flex;flex-direction:column;gap:2px;width:100%;min-width:96px;border:1px solid transparent;border-radius:6px;padding:4px 6px;background:none;color:inherit;font:inherit;text-align:left;cursor:pointer}
.node:hover,.node:focus-visible{border-color:var(--line);outline:none}
.node.current{border:2px solid var(--current)}
.node .cur{font-size:11px;color:var(--current);font-weight:700}
.node .sum{font-size:12px}.node .date{font-size:11px;color:var(--muted)}
.dot{display:inline-block;width:14px;height:14px;border-radius:50%;vertical-align:middle;position:relative;flex:none}
.dot.done{background:var(--done);border:2px solid var(--done)}
.dot.expired{border:2px solid var(--expired);background:linear-gradient(90deg,var(--expired) 50%,transparent 50%)}
.dot.blocked{border:2px solid var(--blocked);background:var(--blocked);color:#fff}
.dot.blocked::after{content:"\\00d7";position:absolute;left:0;right:0;top:-4px;text-align:center;font-size:14px;font-weight:700;line-height:1}
.dot.pending{border:2px solid var(--pending);background:transparent}
.dot.unknown{border:2px dashed var(--unknown);background:transparent}
.node.filtered{opacity:.15;pointer-events:none}
.node.selected{background:var(--proj);border-color:var(--current)}
tr.annot-row td{background:var(--card);font-size:12px;color:var(--muted)}
tr.annot-row details{margin:2px 0}tr.annot-row summary{cursor:pointer}
tr.annot-row dl{margin:4px 0 4px 16px}tr.annot-row dt{font-weight:600;display:inline}tr.annot-row dd{display:inline;margin:0 0 0 4px}
#detail{position:fixed;right:16px;bottom:16px;width:min(440px,calc(100vw - 32px));max-height:70vh;overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;box-shadow:0 6px 24px rgba(0,0,0,.18);z-index:10}
#detail h3{margin:0 0 6px;font-size:15px}#detail .close{float:right;border:1px solid var(--line);background:none;color:inherit;border-radius:6px;cursor:pointer;padding:2px 8px}
#detail dl{margin:6px 0}#detail dt{font-weight:600;margin-top:6px}#detail dd{margin:0 0 0 8px}
#detail ul{margin:2px 0;padding-left:18px}#detail .kind{display:inline-block;font-size:11px;padding:0 5px;border:1px solid var(--line);border-radius:4px;margin-right:4px}
#detail .src{color:var(--muted);font-size:12px}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;font-size:12px}
footer{margin-top:24px;font-size:13px;color:var(--muted)}footer ul{margin:4px 0;padding-left:20px}
@media (max-width:700px){#detail{position:static;width:auto;max-height:none;margin-top:14px}}
"""

JS = """
(function(){
  var raw=document.getElementById('progress-ir');if(!raw)return;
  var ir=JSON.parse(raw.textContent);
  var stageLabel={},stageRule={};ir.stages.forEach(function(s){stageLabel[s.id]=s.label;stageRule[s.id]=(s.rule||'')+(s.source?'（讀 '+s.source+'）':'');});
  var stateZh={done:'完成',expired:'過期',blocked:'受阻',pending:'未到',unknown:'不明'};
  var panel=document.getElementById('detail');var body=document.getElementById('detail-body');
  var selected=null;
  function esc(s){return String(s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function show(laneIdx,nodeIdx){
    var lane=ir.lanes[laneIdx];var n=lane.nodes[nodeIdx];
    var h='<h3>'+esc(lane.label)+' · '+esc(stageLabel[n.stage]||n.stage)+'</h3>';
    h+='<dl><dt>狀態</dt><dd>'+esc(stateZh[n.state]||n.state)+(n.current?'（目前站）':'')+'</dd>';
    h+='<dt>日期</dt><dd>'+esc(n.date||'—')+'</dd>';
    h+='<dt>摘要</dt><dd>'+esc(n.summary||'—')+'</dd>';
    h+='<dt>判定規則（'+esc(n.stage)+'）</dt><dd>'+esc(stageRule[n.stage]||'—')+'</dd>';
    h+='<dt>evidence（'+n.evidence.length+'）</dt><dd>';
    if(n.evidence.length){h+='<ul>';n.evidence.forEach(function(e){
      var v=(e.kind==='hash')?'<span class="mono">'+esc(e.value)+'</span>':esc(e.value);
      h+='<li><span class="kind">'+esc(e.kind)+'</span>'+v+'<br><span class="src">'+esc(e.source)+'</span></li>';});h+='</ul>';}else{h+='—';}
    h+='</dd>';
    if(n.history.length){h+='<dt>history（'+n.history.length+'）</dt><dd><ul>';n.history.forEach(function(x){h+='<li>'+esc(x.date||'—')+'：'+esc(x.summary)+'</li>';});h+='</ul></dd>';}
    if(lane.status_reason){h+='<dt>status_reason</dt><dd>'+esc(lane.status_reason)+'</dd>';}
    h+='</dl>';
    body.innerHTML=h;panel.hidden=false;
    if(selected)selected.classList.remove('selected');
    selected=document.querySelector('.node[data-lane="'+laneIdx+'"][data-node="'+nodeIdx+'"]');
    if(selected)selected.classList.add('selected');
  }
  function close(){panel.hidden=true;if(selected){selected.classList.remove('selected');selected=null;}}
  document.querySelectorAll('.node').forEach(function(btn){btn.addEventListener('click',function(){show(+btn.dataset.lane,+btn.dataset.node);});});
  document.getElementById('detail-close').addEventListener('click',close);
  document.addEventListener('keydown',function(e){if(e.key==='Escape')close();});
  document.querySelectorAll('input[data-state]').forEach(function(cb){cb.addEventListener('change',function(){
    document.querySelectorAll('.node[data-state="'+cb.dataset.state+'"]').forEach(function(el){el.classList.toggle('filtered',!cb.checked);});});});
  var tog=document.getElementById('toggle-annot');
  tog.addEventListener('change',function(){document.querySelectorAll('tr.annot-row').forEach(function(tr){tr.hidden=!tog.checked;});});
})();
"""


def _h(text) -> str:
    return html.escape(_text(text), quote=True)


def _node_cell(lane_idx: int, node_idx: int, n: dict) -> str:
    cls = 'node current' if n['current'] else 'node'
    parts = [f'<button type="button" class="{cls}" data-lane="{lane_idx}" data-node="{node_idx}" data-state="{n["state"]}" title="{_h(n["summary"])}">']
    if n['current']:
        parts.append('<span class="cur">目前</span>')
    parts.append(f'<span><span class="dot {n["state"]}"></span> {_h(STATE_ZH[n["state"]])}</span>')
    parts.append(f'<span class="sum">{_h(_clip(n["summary"], CELL_MAX))}</span>')
    parts.append(f'<span class="date">{_h(n["date"]) or "&nbsp;"}</span>')
    parts.append('</button>')
    return ''.join(parts)


def _lane_cell(lane: dict) -> str:
    out = [f'<td class="lane"><span class="lane-id">{_h(lane["label"])}</span>']
    status = lane['status'].lower()
    if lane['kind'] != 'project':
        badge_cls = status if status in ('blocked', 'addressed', 'open', 'dropped') else 'open'
        out.append(f'<span class="badge {badge_cls}">{_h(status or "open")}</span>')
    if lane['question']:
        out.append(f'<span class="lane-q">{_h(_clip(lane["question"], 60))}</span>')
    out.append('</td>')
    return ''.join(out)


def _annot_row(lane: dict, ncols: int) -> str:
    items = lane['annotations']
    out = [f'<tr class="annot-row" data-lane="{_h(lane["id"])}" hidden><td colspan="{ncols}">']
    if not items:
        out.append('本泳道無決策註記。')
    else:
        out.append(f'決策註記（{len(items)}）：')
        for a in items:
            head = f'{_h(a["id"])} · {_h(a["date"]) or "—"} · {_h(a["stage"]) or "—"} · {_h(a["summary"])}'
            out.append(f'<details><summary>{head}</summary><dl>')
            out.append(f'<div><dt>method</dt><dd>{_h(a["method"]) or "—"}</dd></div>')
            out.append(f'<div><dt>exec_issue</dt><dd>{_h(a["exec_issue"]) or "—"}</dd></div>')
            out.append('</dl></details>')
    out.append('</td></tr>')
    return ''.join(out)


def _matrix(ir: dict, scope: str) -> str:
    stages = [s for s in ir['stages'] if s['scope'] == scope]
    lanes = [(i, lane) for i, lane in enumerate(ir['lanes']) if (lane['kind'] == 'project') == (scope == 'project')]
    out = ['<div class="wrap"><table class="matrix"><thead><tr><th class="lane">泳道</th>']
    for s in stages:
        out.append(f'<th title="{_h(s["id"])}">{_h(s["label"])}</th>')
    out.append('</tr></thead><tbody>')
    for li, lane in lanes:
        out.append(f'<tr class="{lane["kind"]}">' + _lane_cell(lane))
        for ni, n in enumerate(lane['nodes']):
            out.append('<td>' + _node_cell(li, ni, n) + '</td>')
        out.append('</tr>')
        out.append(_annot_row(lane, len(stages) + 1))
    if not lanes:
        out.append(f'<tr><td colspan="{len(stages) + 1}">無研究問題泳道（project.yaml 無 goals）。</td></tr>')
    out.append('</tbody></table></div>')
    return '\n'.join(out)


GRAPH_CSS = """
.tabs{display:flex;gap:6px;margin:12px 0 0;border-bottom:1px solid var(--line)}
.tabs button{border:1px solid var(--line);border-bottom:none;background:var(--card);color:var(--muted);font:inherit;padding:6px 14px;border-radius:8px 8px 0 0;cursor:pointer}
.tabs button.active{color:var(--fg);font-weight:700;background:var(--proj)}
.gcontrols{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;margin:12px 0;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card)}
.gcontrols input[type=search]{font:inherit;padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);min-width:200px}
.gcontrols button{font:inherit;padding:4px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);cursor:pointer}
.gcontrols label{display:inline-flex;align-items:center;gap:4px;cursor:pointer}
.gcontrols .hint{font-size:12px;color:var(--muted);flex-basis:100%}
.glegend{display:flex;flex-wrap:wrap;gap:8px 18px;margin:6px 0 12px;font-size:12px;color:var(--muted)}
.glegend span{display:inline-flex;align-items:center;gap:5px}
.tsw{display:inline-block;width:10px;height:14px;border-radius:2px}
.tsw.question{background:var(--t-question)}.tsw.method{background:var(--t-method)}.tsw.validation{background:var(--t-validation)}.tsw.result{background:var(--t-result)}.tsw.figure{background:var(--t-figure)}.tsw.decision{background:var(--t-decision)}.tsw.report{background:var(--t-report)}
.esw{display:inline-block;width:26px;height:0;border-top:2px solid var(--fg);opacity:.7}
.esw.dashed{border-top-style:dashed}.esw.faint{opacity:.25}.esw.thin{border-top-width:1px;opacity:.35}
#graph-wrap{position:relative;overflow:auto;height:72vh;min-height:360px;border:1px solid var(--line);border-radius:8px;background:var(--card);cursor:grab;user-select:none}
#graph-wrap.dragging{cursor:grabbing}
#graph-svg{display:block}
#graph-svg text{font:12px system-ui,-apple-system,"Segoe UI","Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif;fill:var(--fg);pointer-events:none}
#graph-svg text.badge{font-size:10px;fill:var(--muted);pointer-events:auto;cursor:pointer}
#graph-svg text.st{font-size:11px;fill:var(--muted)}
#graph-svg text.sym{font-size:13px}
.gnode{cursor:pointer}
.gnode .box{fill:var(--bg-none);stroke:var(--pending);stroke-width:1.5}
.gnode.s-done .box{fill:var(--bg-done);stroke:var(--done)}.gnode.s-done .sym{fill:var(--done)}
.gnode.s-expired .box{fill:var(--bg-expired);stroke:var(--expired);stroke-dasharray:6 3}.gnode.s-expired .sym{fill:var(--expired)}
.gnode.s-blocked .box{fill:var(--bg-blocked);stroke:var(--blocked);stroke-width:2.5}.gnode.s-blocked .sym{fill:var(--blocked)}
.gnode.s-pending .box{fill:var(--bg-pending);stroke:var(--pending)}.gnode.s-pending .sym{fill:var(--pending)}
.gnode.s-unknown .box{fill:var(--bg-pending);stroke:var(--unknown);stroke-dasharray:2 3}.gnode.s-unknown .sym{fill:var(--unknown)}
.gnode .tbar{fill:var(--pending)}
.gnode.t-question .tbar{fill:var(--t-question)}.gnode.t-method .tbar{fill:var(--t-method)}.gnode.t-validation .tbar{fill:var(--t-validation)}.gnode.t-result .tbar{fill:var(--t-result)}.gnode.t-figure .tbar{fill:var(--t-figure)}.gnode.t-decision .tbar{fill:var(--t-decision)}.gnode.t-report .tbar{fill:var(--t-report)}
.gnode.gone,path.edge.off{display:none}
path.edge{fill:none;stroke:var(--edge);stroke-width:1.1;marker-end:url(#arrow)}
path.trunk{fill:none;stroke:var(--edge);stroke-width:1.6}
path.edge.st-dashed,path.trunk.st-dashed{stroke-dasharray:6 4}
path.edge.st-thin,path.trunk.st-thin{stroke-width:.9;stroke:var(--edge-thin)}
path.edge.e-supersedes,path.edge.e-cites,path.edge.e-refers,path.trunk.e-supersedes,path.trunk.e-cites,path.trunk.e-refers{stroke:var(--edge-faint)}
path.trunk.up{stroke:var(--up);stroke-width:2.4}path.trunk.down{stroke:var(--down);stroke-width:2.4}path.trunk.onpath{stroke:var(--path);stroke-width:3}
path.trunk.dim{opacity:.08}
path.edge.hov,path.trunk.hov{stroke:var(--current)!important;opacity:1!important}
.gnode.sel .box{stroke:var(--current);stroke-width:4}
.gnode.up .box{stroke:var(--up);stroke-width:3}
.gnode.down .box{stroke:var(--down);stroke-width:3}
.gnode.onpath .box{stroke:var(--path);stroke-width:3}
.gnode.hit .box{stroke:var(--current);stroke-width:3}
path.edge.up{stroke:var(--up);stroke-width:1.8;opacity:1;marker-end:url(#arrow-up)}
path.edge.down{stroke:var(--down);stroke-width:1.8;opacity:1;marker-end:url(#arrow-down)}
path.edge.onpath{stroke:var(--path);stroke-width:3;opacity:1;marker-end:url(#arrow-path)}
path.edge.own{opacity:.9}
.gnode.sub .box{fill:var(--bg-sub)}.gnode.sub.s-done .box{fill:var(--bg-sub-done)}.gnode.sub.s-expired .box{fill:var(--bg-sub-expired)}
.gnode.sub text.lbl{font-size:11px}
#graph-svg text.st.unval{fill:var(--expired);font-weight:700}
path.edge.e-sensitivity{stroke:var(--t-method);opacity:.8;marker-end:none;stroke-width:1.6}
path.edge.e-supports{stroke:var(--t-result);opacity:.8;marker-end:none;stroke-width:1.6}
path.edge.e-embedded_in,path.trunk.e-embedded_in{stroke:var(--t-report);opacity:.85}
path.edge.e-supplements,path.trunk.e-supplements{stroke:var(--t-method);stroke-width:1.6;opacity:.85;marker-end:url(#arrow-method)}
#graph-bands text.band-title{font-size:12px;font-weight:600;fill:var(--muted)}
#graph-bands line.band-divider{stroke:var(--edge-faint);stroke-width:1;stroke-dasharray:6 4}
#graph-bands.off,#graph-bands .off{display:none}
#graph-strips line.strip-divider{stroke:var(--edge-faint);stroke-width:1;stroke-dasharray:2 5;opacity:.7}
.gnode.dim{opacity:.15}path.edge.dim{opacity:.08}
.gnode.filtered{opacity:.15}path.edge.filtered{opacity:.15}
#gdetail{position:fixed;right:16px;bottom:16px;width:min(460px,calc(100vw - 32px));max-height:72vh;overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;box-shadow:0 6px 24px rgba(0,0,0,.18);z-index:10}
#gdetail h3{margin:0 0 6px;font-size:15px}#gdetail .close{float:right;border:1px solid var(--line);background:none;color:inherit;border-radius:6px;cursor:pointer;padding:2px 8px}
#gdetail dl{margin:6px 0}#gdetail dt{font-weight:600;margin-top:6px}#gdetail dd{margin:0 0 0 8px}
#gdetail ul{margin:2px 0;padding-left:18px}#gdetail .src{color:var(--muted);font-size:12px}
#gdetail .goto,#gdetail .expand{color:var(--current);cursor:pointer;text-decoration:underline dotted}
#gdetail .tour{background:var(--proj);border-radius:6px;padding:6px 8px;margin-bottom:8px}
.arrow-default{fill:var(--edge)}.arrow-up{fill:var(--up)}.arrow-down{fill:var(--down)}.arrow-path{fill:var(--path)}.arrow-method{fill:var(--t-method)}
#gdetail{width:min(560px,calc(100vw - 32px))}
#gdetail table.rt{border-collapse:collapse;font-size:11px;margin:4px 0;max-width:100%}
#gdetail .rt-wrap{overflow:auto;max-height:260px;border:1px solid var(--line);border-radius:6px}
#gdetail table.rt th,#gdetail table.rt td{border:1px solid var(--line);padding:2px 5px;text-align:left;white-space:nowrap}
#gdetail table.rt th{background:var(--proj);position:sticky;top:0}
#gdetail .fig{margin:6px 0 10px;padding:6px;border:1px solid var(--line);border-radius:6px}
#gdetail .fig img{max-width:100%;max-height:220px;display:block;cursor:zoom-in;background:#fff}
#gdetail .fig .cap{font-size:12px;margin-top:4px}#gdetail .fig .missing{color:var(--blocked);font-size:12px}
#lightbox{position:fixed;inset:0;background:rgba(0,0,0,.82);z-index:50;display:flex;align-items:center;justify-content:center;cursor:zoom-out}
#lightbox[hidden]{display:none}
#lightbox img{max-width:96vw;max-height:92vh;background:#fff}
#lightbox .lb-cap{position:absolute;left:16px;right:16px;bottom:10px;color:#fff;font-size:12px;text-align:center}
#inbox-banner{margin:10px 0 0;padding:8px 12px;border:1px solid var(--expired);border-radius:8px;background:var(--bg-expired);font-size:13px}
#inbox-banner summary{cursor:pointer;font-weight:600}
#inbox-banner table{border-collapse:collapse;margin-top:6px;font-size:12px}#inbox-banner td,#inbox-banner th{padding:2px 8px;text-align:left;border-bottom:1px solid var(--line)}
.inbox-actions{display:flex;gap:8px;align-items:center;margin:10px 0 0;font-size:13px}
.inbox-actions button,#inbox-form button,.inbox-comment{font:inherit;padding:4px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);cursor:pointer}
.inbox-actions button[disabled],.inbox-comment[disabled]{opacity:.5;cursor:not-allowed}
.inbox-actions .hint{color:var(--muted);font-size:12px}
#inbox-form,#act-form{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:60;display:flex;align-items:center;justify-content:center}
#inbox-form[hidden],#act-form[hidden]{display:none}
#inbox-form form,#act-form form{background:var(--panel);color:var(--fg);border:1px solid var(--line);border-radius:10px;padding:14px 16px;width:min(560px,calc(100vw - 32px));max-height:90vh;overflow:auto}
#inbox-form label,#act-form label{display:block;margin:8px 0 2px;font-size:13px;font-weight:600}
#inbox-form input,#inbox-form select,#inbox-form textarea,#act-form input,#act-form select,#act-form textarea{width:100%;font:inherit;padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);box-sizing:border-box}
#inbox-form textarea{min-height:120px}#act-form textarea{min-height:70px}
#inbox-form .row,#act-form .row{display:flex;gap:8px;justify-content:flex-end;margin-top:12px}
#inbox-form .err,#act-form .err{color:var(--blocked);font-size:12px;margin-top:6px;min-height:1em}
#act-form button{font:inherit;padding:4px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);cursor:pointer}
.gnode.node-drag{opacity:.55}.gnode.node-drag .box{stroke:var(--current);stroke-width:3;stroke-dasharray:4 3}
#graph-wrap.drop-hint .band-divider{stroke:var(--current);stroke-width:2}
/* 拖曳時的即時接線預覽（0.16.1）：候選落點打亮、預覽線只在拖曳中存在 */
.gnode.drop-ok .box{stroke:var(--current);stroke-width:4}.gnode.drop-bad .box{stroke:var(--blocked);stroke-width:4}
#graph-bands text.band-title.drop-ok{fill:var(--current);font-size:14px}#graph-bands text.band-title.drop-bad{fill:var(--blocked);font-size:14px}
#graph-bands line.band-divider.drop-ok{stroke:var(--current);stroke-width:2.5;stroke-dasharray:none}
#drag-preview path.preview{fill:none;stroke-width:2.2;stroke-dasharray:7 5;pointer-events:none}
#drag-preview path.preview.e-plans{stroke:var(--edge)}#drag-preview path.preview.e-sensitivity{stroke:var(--t-method)}#drag-preview path.preview.e-supports{stroke:var(--t-result)}
#drag-preview path.preview.drop-ok{stroke:var(--current)}#drag-preview path.preview.drop-bad{stroke:var(--blocked)}
#drag-preview rect.band-hl{fill:var(--current);opacity:.07;pointer-events:none}#drag-preview rect.band-hl.drop-bad{fill:var(--blocked)}
#drag-preview text.preview-label{font-size:12px;font-weight:600;fill:var(--current);paint-order:stroke;stroke:var(--panel);stroke-width:4px;stroke-linejoin:round;pointer-events:none}
#drag-preview text.preview-label.drop-bad{fill:var(--blocked)}
#actions-panel{margin:10px 0 0;padding:8px 12px;border:1px solid var(--line);border-radius:8px;font-size:13px}
#actions-panel summary{cursor:pointer;font-weight:600}
#actions-panel table{border-collapse:collapse;margin-top:6px;font-size:12px;width:100%}#actions-panel td,#actions-panel th{padding:3px 8px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
#actions-panel button{font:inherit;padding:3px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);cursor:pointer}
#actions-panel button[disabled]{opacity:.5;cursor:not-allowed}
/* 0.17.0 批次暫存：暫存過的節點虛線外框、暫存加的邊虛線；頁首「暫存動作」面板與待套用面板同一套樣式 */
.gnode.staged .box{stroke:var(--current);stroke-width:2.5;stroke-dasharray:6 3}
path.edge.staged{stroke-dasharray:6 3}
#staged-panel{margin:10px 0 0;padding:8px 12px;border:1px dashed var(--current);border-radius:8px;font-size:13px}
#staged-panel summary{cursor:pointer;font-weight:600}
#staged-panel table{border-collapse:collapse;margin-top:6px;font-size:12px;width:100%}#staged-panel td,#staged-panel th{padding:3px 8px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
#staged-panel button{font:inherit;padding:3px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);cursor:pointer}
#staged-panel button[disabled]{opacity:.5;cursor:not-allowed}
#staged-panel .row{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap;align-items:center}
#staged-panel .row label{font-weight:600}#staged-panel #staged-reason{flex:1 1 240px;min-width:160px;font:inherit;padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg)}
#staged-panel .err{color:var(--blocked);font-size:12px;margin-top:6px;min-height:1em}
#staged-panel #staged-apply-why{font-size:12px;color:var(--muted,#777)}
#staged-old{margin:8px 0 0;padding:6px 12px;border:1px dashed var(--line);border-radius:8px;font-size:13px}#staged-old button{font:inherit;padding:3px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);cursor:pointer}#staged-old button[disabled]{opacity:.5;cursor:not-allowed}
pre.act-summary{white-space:pre-wrap;font-size:11px;max-height:320px;overflow:auto;margin:4px 0 0;padding:6px;border:1px solid var(--line);border-radius:6px;background:var(--bg)}
pre.act-summary:empty{display:none}
#act-form .err{white-space:pre-wrap}#act-form #act-preview-box .hint{margin:10px 0 4px}#act-form input:disabled,#act-form select:disabled,#act-form textarea:disabled{opacity:.7}
#actions-panel .hint{color:var(--muted);font-size:12px}
.act-inline{display:inline-flex;gap:6px;align-items:center}.act-inline select,.act-inline button{font:inherit;padding:2px 6px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg)}
.act-inline button{cursor:pointer}.act-inline button[disabled]{opacity:.5;cursor:not-allowed}
.agg-tools{margin:2px 0 4px}.agg-tools input{font:inherit;padding:2px 6px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);min-width:12em}.agg-tools button,.agg-promote{font:inherit;padding:1px 6px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);cursor:pointer}.agg-promote[disabled],.agg-tools button[disabled]{opacity:.5;cursor:not-allowed}ul.agg-list{margin:0;padding-left:1.2em;max-height:24em;overflow:auto}
#toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:var(--fg);color:var(--bg);padding:8px 14px;border-radius:8px;z-index:70;font-size:13px}
#toast[hidden]{display:none}
#toast a.toast-undo{color:var(--bg);text-decoration:underline;margin-left:10px;font-weight:600;cursor:pointer}
@media (max-width:700px){#gdetail{position:static;width:auto;max-height:none;margin-top:14px}}
"""

GRAPH_JS = """
(function(){
  var raw=document.getElementById('progress-ir');if(!raw)return;
  var ir=JSON.parse(raw.textContent);var G=ir.graph;if(!G)return;
  var NODE_W=260,NODE_H=36,COL_PITCH=380,ROW_GAP=48,GRAPH_PAD=20;  // 與 Python 端同名常數同值（測試比對）
  var BAND_TITLE_H=28,BAND_GAP=40,BAND_TITLE_DY=18;  // 區帶標題列高、區帶間距、標題基線偏移；與 Python 端同名常數同值
  var BANDS=['main','ext','supp'];  // 區帶由上而下；與 Python 端 BANDS 同序
  var STRIP_GAP=ROW_GAP;  // 0.18.1 同一區帶內兩條問題帶之間的空隙（1 列）；與 Python 端同名常數同值
  var W=NODE_W,H=NODE_H,PAD=GRAPH_PAD,ROW=ROW_GAP,GAP=COL_PITCH-NODE_W;
  var nodes={};G.nodes.forEach(function(n){nodes[n.id]=n;});
  var typeLabel={},edgeLabel={};G.node_types.forEach(function(t){typeLabel[t.id]=t.label;});G.edge_types.forEach(function(t){edgeLabel[t.id]=t.label;});
  var stateZh={done:'完成',expired:'過期',blocked:'受阻',pending:'未到',unknown:'不明','':'—'};
  var outE={},inE={};G.edges.forEach(function(e,i){(outE[e.from]=outE[e.from]||[]).push(i);(inE[e.to]=inE[e.to]||[]).push(i);});
  var currentOf={};G.nodes.forEach(function(n){if(n.type==='method'&&!n.collapsed)(n.meta.superseded_versions||[]).forEach(function(o){currentOf['p:'+o]=n.id;});});
  var svg=document.getElementById('graph-svg'),root=document.getElementById('graph-root'),wrap=document.getElementById('graph-wrap');
  var nodeEls={};Array.prototype.forEach.call(document.querySelectorAll('.gnode'),function(el){nodeEls[el.getAttribute('data-node-id')]=el;});
  var edgeEls=[];Array.prototype.forEach.call(document.querySelectorAll('path.edge'),function(el){edgeEls[+el.getAttribute('data-idx')]=el;});
  var panel=document.getElementById('gdetail'),body=document.getElementById('gdetail-body');
  var search=document.getElementById('graph-search');
  var boxOld=document.getElementById('toggle-old'),boxDec=document.getElementById('toggle-dec'),boxAll=document.getElementById('toggle-alledges');
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  // ---- 結構化動作（0.16.0）：Main 帶的 SQ 節點與圖表節點；拖放與面板按鈕都只送收件匣，不直接改 SSOT ----
  var ROLE_OPTS=[['main','main（Main 主圖）'],['extended','extended（Extended Data）'],['supplementary','supplementary（Supplementary）']];
  var BAND_ROLE={main:'main',ext:'extended',supp:'supplementary'};
  function isMainSQ(id){var n=nodes[id];return !!(n&&n.type==='question'&&n.band==='main'&&/^q:SQ\d+$/.test(id));}
  function questionKind(id){return /^q:SQ\d+$/.test(id)?'SQ':(/^q:AQ\d+$/.test(id)?'AQ':'');}
  function isActivePlan(id){var n=nodes[id];return !!(n&&n.type==='method'&&!n.parent&&!n.collapsed&&/^p:[^#]+$/.test(id));}
  function isSensItem(id){var n=nodes[id];return !!(n&&n.type==='method'&&n.subtype==='sensitivity'&&!n.collapsed&&/^p:[^#]+#R\d+$/.test(id));}
  function isL(e){return e.type==='sensitivity'||e.type==='supports';}   // 父 → 子的 L 形線（與 Python L_EDGE_TYPES 同義）
  // ---- 0.20.0 Extended Data 歸屬（analysis/extended-data.yaml；使用者 2026-09-17 裁定：方法／結果／驗證也能放 ED，只有 SQ／AQ 不行）----
  // meta.band_source：explicit＝自己列在檔裡、inherited:<來源 id>＝跟 plan／跟父進 ED（來源是那個 explicit 節點）、derived＝原規則；圖表沿用 role_source
  function bandSource(id){var n=nodes[id];return n?String((n.meta||{}).band_source||''):'';}
  function edInherited(id){var s=bandSource(id);return s.indexOf('inherited:')===0?s.slice(10):'';}
  function bandSourceZh(id){var s=bandSource(id);if(!s)return '';if(s==='explicit')return '（列在 analysis/extended-data.yaml）';if(s==='derived')return '（依原規則推導）';return '（跟 '+esc(edInherited(id))+' 進 Extended Data）';}
  function qBand(sq){var q=nodes['q:'+sq];return q?q.band:'main';}
  // 結果的 owner plan（與 Python 同：results.json 的 plan_id 在圖裡就用它，否則宣告以現行 plan 優先）
  function resultOwnerOf(n){var m=n.meta||{},o=String(m.plan_id||'');if(o&&nodes['p:'+o])return o;var decl=(m.declared_by||[]).slice().sort(function(a,b){var pa=nodes[a.split('#')[0]],pb=nodes[b.split('#')[0]];return ((pa&&!pa.collapsed)?0:1)-((pb&&!pb.collapsed)?0:1);});return decl.length?decl[0].slice(2).split('#')[0]:'';}
  // 推導區帶＝從檔裡拿掉後會落到的帶，與它的來源：plan → 問題的帶；群／子分析 → plan 現在的帶；次要（聚合）／支撐結果 → 父現在的帶；主要／未宣告結果 → owner plan 現在的帶（沒有 plan 依問題帶）；驗證 → plan_id 的 plan 現在的帶（沒有依 sq）
  function derivedBandOf(id){var n=nodes[id];if(!n)return {band:'main',from:''};var m=n.meta||{};
    if(n.type==='method'){if(id.indexOf('#')<0)return {band:qBand(String(m.sq||'')),from:'q:'+String(m.sq||'')};var pp='p:'+id.slice(2).split('#')[0];return nodes[pp]?{band:nodes[pp].band,from:pp}:{band:'main',from:''};}
    if(n.type==='result'){if(n.parent&&nodes[n.parent])return {band:nodes[n.parent].band,from:n.parent};var o=resultOwnerOf(n);if(o&&nodes['p:'+o])return {band:nodes['p:'+o].band,from:'p:'+o};var st=n.strip;return {band:(st&&nodes[st])?nodes[st].band:'main',from:st||''};}
    if(n.type==='validation'){var pv='p:'+String(m.plan_id||'');if(nodes[pv])return {band:nodes[pv].band,from:pv};return {band:qBand(String(m.sq||'')),from:'q:'+String(m.sq||'')};}
    return {band:n.band,from:''};}
  function derivedBand(id){return derivedBandOf(id).band;}
  var BAND_ZH={main:'Main',ext:'Extended Data',supp:'Supplementary'};
  // 拖到 Extended Data 帶（進 ED）或從 ED 拖回推導區帶（出 ED）的候選；回 undefined＝不是 ED 情境（走該型別原本的規則：move_result／原有紅線）
  function tierCand(id,b){var n=nodes[id];if(!n)return null;
    if(b==='ext'){if(n.band==='ext')return null;return {kind:'set_tier',ok:true,band:'ext',label:n.label+' 放入 Extended Data',payload:{node:id,tier:'extended'}};}
    if(n.band!=='ext')return undefined;
    var inh=edInherited(id);if(inh)return {kind:'set_tier',ok:false,band:b,reason:'這個節點的 ED 歸屬來自 '+inh+'，請拖那個節點'};
    var d=derivedBandOf(id);
    if(d.band==='ext')return {kind:'set_tier',ok:false,band:b,reason:n.label+' 從 extended-data.yaml 拿掉後仍跟 '+d.from+' 留在 Extended Data，請拖那個節點'};
    if(b===d.band)return {kind:'set_tier',ok:true,band:b,label:n.label+' 移出 Extended Data（回 '+BAND_ZH[b]+' 帶）',payload:{node:id,tier:''}};
    return undefined;}
  var nestHidden={};   // 0.16.5 結果主從：主結果 id → true＝暫時收合它的支撐結果（只在本頁面，不寫任何檔）
  // 0.16.1：問題（SQ／AQ）、方法（active plan）、敏感性子分析、圖表都可拖；0.16.2：結果節點（主要／次要／未宣告，來源 plan 由 results.json plan_id 判、須為 active plan）也可拖；落點由 dragCandidate 依游標位置即時判定
  function resultOwner(id){var n=nodes[id];if(!n||n.type!=='result')return '';var pid=String((n.meta||{}).plan_id||'');return (pid&&isActivePlan('p:'+pid))?pid:'';}
  function isDragResult(id){return !!resultOwner(id);}
  // 0.19.0 宣告粒度：次要結果聚合節點（有自有次要鍵的敏感性子分析一個、沒有就沒有；鍵全列在 meta.keys）——整個節點可拖＝裡面全部鍵一起搬；
  // 樂觀更新把鍵搬進沒有聚合節點的子分析時現做一個（spawnNode＋produces 邊）、搬空了就消失（staged_gone）
  function isAgg(id){var n=nodes[id];return !!(n&&n.type==='result'&&n.subtype==='secondary_group');}
  function aggKeys(id){var n=nodes[id];return (n&&n.meta&&n.meta.keys||[]).map(function(k){return k.key;});}
  function aggOfKey(key){var out='';G.nodes.some(function(n){if(n.type==='result'&&n.subtype==='secondary_group'&&(n.meta.keys||[]).some(function(k){return k.key===key;})){out=n.id;return true;}return false;});return out;}
  function aggLabel(n){var ks=(n.meta.keys||[]);n.meta.n_keys=ks.length;n.label=ks.length===1?ks[0].key:'次要結果 '+ks.length+' 鍵';var ur=0,uv=0;ks.forEach(function(k){if(!k.registered)ur++;else if(!k.validated)uv++;});n.meta.n_unregistered=ur;n.meta.n_unvalidated=uv;
    var badge=[ur?'未登錄 '+ur:'',uv?'未驗證 '+uv:''].filter(Boolean).join('／');n.badge=badge;var el=(typeof nodeEls!=='undefined')?nodeEls[n.id]:null;
    if(el&&el.querySelector){var b=el.querySelector('text.badge');if(b)b.textContent=badge;else if(badge&&typeof setBadge==='function'&&typeof document!=='undefined')setBadge(n.id,badge);var t=el.querySelector('text.lbl');if(t)t.textContent=n.label.length>26?n.label.slice(0,25)+'…':n.label;}}
  function draggable(id){var n=nodes[id];return !!(n&&((n.type==='question'&&questionKind(id))||isActivePlan(id)||isSensItem(id)||n.type==='figure'||isDragResult(id)||n.type==='validation'));}   // 0.20.0：驗證節點可拖（只為 Extended Data 歸屬）
  var ACT_LABEL={reassign:'降為附錄問題',promote:'升回主問題',set_role:'改圖表 role',move_plan:'搬方法',move_sensitivity:'搬敏感性子分析',reorder:'調順序',move_result:'搬結果',nest_result:'掛到主結果下',demote_plan:'降為敏感性子分析',set_tier:'Extended Data 歸屬',batch:'批次'};
  // ---- 分頁 ----
  var tabs={};['milestones','relations','literature','submission'].forEach(function(k){var el=document.getElementById('tab-'+k);if(el)tabs[k]=el;});
  var cur='milestones';
  function showTab(name,writeHash){
    if(!tabs[name])name='milestones';cur=name;
    Object.keys(tabs).forEach(function(k){tabs[k].hidden=(k!==name);var b=document.querySelector('.tabs button[data-tab="'+k+'"]');if(b)b.classList.toggle('active',k===name);});
    var d=document.getElementById('detail');if(d)d.hidden=true;panel.hidden=true;
    if(writeHash){try{if(location.hash!=='#'+name)location.hash='#'+name;}catch(e){}}
    // 文獻分頁的 canvas 要在隱藏時停掉 requestAnimationFrame、顯示時重量尺寸，靠這個事件通知
    try{document.dispatchEvent(new CustomEvent('progress:tab',{detail:{tab:name}}));}catch(e){}
  }
  Array.prototype.forEach.call(document.querySelectorAll('.tabs button'),function(b){b.addEventListener('click',function(){showTab(b.getAttribute('data-tab'),true);});});
  window.addEventListener('hashchange',function(){showTab((location.hash||'').replace('#','')||'milestones',false);});
  showTab((location.hash||'').replace('#','')||'milestones',false);
  // ---- 可見性與版面 ----
  var expanded={},selected=null,pathEdges={},pathNodes=null,tour=null,stateOff={};
  function nodeVisible(id){var n=nodes[id];if(!n)return false;if(n.staged_gone)return false;if(n.type==='decision')return boxDec.checked;if(n.parent){if((n.subtype==='supporting'||n.subtype==='sensitivity_group')&&typeof nestHidden!=='undefined'&&nestHidden[n.parent])return false;return nodeVisible(n.parent);}if(n.collapsed)return boxOld.checked||!!expanded[currentOf[id]];return true;}
  // 0.18.0 縮排量與 Python SUB_INDENT_OF 同值：群縮一層 24、子分析縮兩層 48、次要／支撐結果 24（nodeW／fixX 各自內含同一張表，測試可單獨抽出）
  function nodeW(n){return W-({sensitivity_group:24,sensitivity:48,secondary:24,supporting:24,secondary_group:24}[n.subtype]||0);}
  function lPath(a,b){var x0=a.x+12,y0=a.y+H,yc=b.y+H/2,x2=b.x;var r=Math.min(6,Math.max(0,(yc-y0)/2),Math.max(0,(x2-x0)/2));return 'M'+x0+','+y0+' L'+x0+','+(yc-r)+' Q'+x0+','+yc+' '+(x0+r)+','+yc+' L'+x2+','+yc;}
  function edgeDrawn(i){var e=G.edges[i];if(!nodeVisible(e.from)||!nodeVisible(e.to))return false;if(pathEdges[i])return true;if(selected&&(e.from===selected||e.to===selected))return true;return boxAll.checked||e.default_visible;}
  var bandsEl=document.getElementById('graph-bands'),bandDivs={},bandTitles={};
  Array.prototype.forEach.call(bandsEl.querySelectorAll('.band-divider'),function(el){bandDivs[el.getAttribute('data-band')]=el;});
  Array.prototype.forEach.call(bandsEl.querySelectorAll('.band-title'),function(el){bandTitles[el.getAttribute('data-band')]=el;});
  var dummyY={};  // 跳欄邊 idx → {col: dummy 列 y}（relayout 時依 via_order 與節點一起排列）
  var stagedLayout=false;  // 0.17.2 暫存後由 reorderStaged() 設 true：via_order 是 IR 值，與重算的 order 混排會亂，跳欄邊改直接畫折線（預覽不求 0 交叉）
  function dummyActive(i){if(stagedLayout)return false;var e=G.edges[i];return !!(e.default_visible&&e.via_order&&e.via_order.length&&nodeVisible(e.from)&&nodeVisible(e.to));}
  // 0.18.1 問題帶：qOrder＝問題節點的 IR 序（goals 順序）；stripOrder＝暫存後由 reorderStaged() 重算的各帶帶序（null＝照 IR graph.strips）；
  // stripBoxes＝最近一次 relayout 算出的各帶 {band, question, y0, y1}（與 Python graph.strips 同義，供測試比對）
  var qOrder=G.nodes.filter(function(n){return n.type==='question';}).map(function(n){return n.id;}),qIndex={};qOrder.forEach(function(q,i){qIndex[q]=i;});
  var stripOrder=null,stripBoxes=[],stripsEl=document.getElementById('graph-strips');
  function stripsOf(band){if(stripOrder)return stripOrder[band]||[];return (G.strips||[]).filter(function(s){return s.band===band;}).map(function(s){return s.question;});}
  // 決策註記所掛的帶：沿 refers 邊第一個指到問題（q:main 除外）或 plan 的目標；其餘空字串（放該區帶最後）；與 Python _decision_strip 同義
  function decisionStrip(n){var s='';(outE[n.id]||[]).some(function(ei){var e=G.edges[ei];if(e.type!=='refers')return false;var t=nodes[e.to];if(!t)return false;if(t.type==='question'&&e.to!=='q:main'){s=e.to;return true;}if(t.type==='method'){s=t.strip||'';return true;}return false;});return s;}
  function stripKey(n){var ss=stripsOf(n.band),s=(n.type==='decision')?decisionStrip(n):(n.id==='q:main'?'q:main':(n.strip||''));if(n.id!=='q:main'&&ss.indexOf(s)<0)s='';return s;}
  // 與 Python layout_graph 同一套：三個區帶依 BANDS 順序累積——main 只在其他區帶有可見節點時讓出標題列；ext／supp 只在有可見節點
  // （含 dummy 列）時畫分隔線（上一區帶 bottom+BAND_GAP/2）、標題（+BAND_GAP）、節點從 +BAND_TITLE_H 起，沒有就不佔高度；
  // 區帶內再依問題帶（stripsOf）累積：帶內各欄從帶的第一列起各自往下排、帶高＝最高那欄的列數、帶與帶之間留 STRIP_GAP；
  // 每個 (band, strip, col) 內依 order 排列，跳欄邊的 dummy 列（via_order）落在目標的帶；決策從所屬帶的第一列往下疊（疊過頭接在其後）、
  // 沒有對應帶的決策接在全部帶之後；q:main 對 main 帶問題欄的問題居中；帶之間的淡色細線（#graph-strips）整組重建
  function relayout(){
    var cells={};function push(k,it){(cells[k]=cells[k]||[]).push(it);}
    G.nodes.forEach(function(n){push(n.band+'|'+stripKey(n)+'|'+n.col,{n:n,order:n.order});});
    dummyY={};
    G.edges.forEach(function(e,i){if(!dummyActive(i))return;var t=nodes[e.to],ts=stripKey(t);e.via.forEach(function(v,j){push(t.band+'|'+ts+'|'+v[0],{d:i,col:v[0],order:e.via_order[j]});});});
    var maxY=0,has={};
    BANDS.forEach(function(b){has[b]=false;});
    G.nodes.forEach(function(n){if(n.type!=='decision'&&nodeVisible(n.id))has[n.band]=true;});
    var hasOther=BANDS.some(function(b){return b!=='main'&&has[b];});
    var byOrder=function(a,b){return a.order-b.order;};
    function setY(n,y){var el=nodeEls[n.id];n.y=y;el.setAttribute('transform','translate('+n.x+','+n.y+')');if(y>maxY)maxY=y;}
    function placeCell(k,y0){var list=(cells[k]||[]).slice().sort(byOrder),row=0;
      list.forEach(function(it){if(it.n){var n=it.n,v=nodeVisible(n.id);nodeEls[n.id].classList.toggle('gone',!v);if(v){setY(n,y0+row*ROW);row++;}}
        else{var y=y0+row*ROW;row++;(dummyY[it.d]=dummyY[it.d]||{})[it.col]=y;if(y>maxY)maxY=y;}});return row;}
    function placeDecisions(k,decY){(cells[k]||[]).slice().sort(byOrder).forEach(function(it){var n=it.n,v=nodeVisible(n.id);nodeEls[n.id].classList.toggle('gone',!v);if(v){setY(n,decY);decY+=ROW;}});return decY;}
    stripBoxes=[];
    function place(band,y0){var bottom=y0,y=y0,decY=y0,strips=stripsOf(band).slice();
      if(strips.indexOf('')<0){for(var c0=0;c0<6;c0++){if(cells[band+'||'+c0]){strips.push('');break;}}}   // 帶序沒列到的節點一律進孤兒帶，不漏排
      strips.forEach(function(s,si){if(si)y+=STRIP_GAP;var rows=0;for(var c=0;c<6;c++){var r=placeCell(band+'|'+s+'|'+c,y);if(r>rows)rows=r;}
        decY=placeDecisions(band+'|'+s+'|6',Math.max(decY,y));
        var y1=rows?y+(rows-1)*ROW+H:y;stripBoxes.push({band:band,question:s,y0:y,y1:y1});if(rows&&y1>bottom)bottom=y1;y+=rows*ROW;});
      if(strips.indexOf('')<0)decY=placeDecisions(band+'||6',decY);
      return bottom;}
    var prev=PAD,frame={};
    BANDS.forEach(function(b){
      if(b==='main'){frame[b]={div:PAD,title:PAD,y0:hasOther?PAD+BAND_TITLE_H:PAD};prev=place(b,frame[b].y0);}
      else{frame[b]={div:prev+BAND_GAP/2,title:prev+BAND_GAP,y0:prev+BAND_GAP+BAND_TITLE_H};if(has[b])prev=place(b,frame[b].y0);}
    });
    var main=nodes['q:main'];if(main){var ys=[];stripsOf('main').forEach(function(s){(cells['main|'+s+'|1']||[]).forEach(function(it){if(it.n&&nodeVisible(it.n.id))ys.push(it.n.y);});});
      if(ys.length){main.y=(Math.min.apply(null,ys)+Math.max.apply(null,ys))/2;}else{main.y=frame.main.y0;}nodeEls[main.id].setAttribute('transform','translate('+main.x+','+main.y+')');}
    bandsEl.classList.toggle('off',!hasOther);
    var wdt=+svg.getAttribute('width');
    BANDS.forEach(function(b){var dv=bandDivs[b],tt=bandTitles[b];if(dv){dv.setAttribute('y1',frame[b].div);dv.setAttribute('y2',frame[b].div);dv.setAttribute('x2',wdt-PAD);dv.classList.toggle('off',b==='main'||!has[b]);}
      if(tt){tt.setAttribute('y',frame[b].title+BAND_TITLE_DY);tt.classList.toggle('off',b!=='main'&&!has[b]);}});
    if(stripsEl){while(stripsEl.firstChild)stripsEl.removeChild(stripsEl.firstChild);var pv=null;stripBoxes.forEach(function(s){if(pv&&pv.band===s.band){var ln=document.createElementNS(svg.namespaceURI,'line'),yy=(pv.y1+s.y0)/2;ln.setAttribute('class','strip-divider');ln.setAttribute('data-band',s.band);ln.setAttribute('data-strip',s.question);ln.setAttribute('x1',PAD);ln.setAttribute('y1',yy);ln.setAttribute('x2',wdt-PAD);ln.setAttribute('y2',yy);stripsEl.appendChild(ln);}pv=s;});}
    var h=maxY+H+PAD;svg.setAttribute('height',h);svg.setAttribute('viewBox','0 0 '+svg.getAttribute('width')+' '+h);
    redrawEdges();
  }
  var LANE_GAP=8,CORNER_R=4,TRUNK_MAX_SIDE=Math.floor((0.8*GAP/2)/LANE_GAP),TRUNK_MAX_LANES=2*TRUNK_MAX_SIDE+1;
  function num(v){var r=Math.round(v*100)/100;return String(r);}
  function gapCenter(g){return GRAPH_PAD+g*COL_PITCH+NODE_W+GAP/2;}
  function laneX(g,lane,nLanes){var n=Math.min(nLanes,TRUNK_MAX_LANES);return gapCenter(g)+((lane%TRUNK_MAX_LANES)-(n-1)/2)*LANE_GAP;}
  var SPINE_X=12,SPINE_LANE_GAP=4;  // 對照短垂線 x 偏移與分道間距；與 Python 端同名常數同值
  function spinePath(a,b,lane){var dx=SPINE_X-(lane||0)*SPINE_LANE_GAP,x0=a.x+dx,y0=a.y,x1=b.x+dx,y1=b.y+H;return x0===x1?'M'+num(x0)+','+num(y0)+' V'+num(y1):'M'+num(x0)+','+num(y0)+' L'+num(x1)+','+num(y1);}
  // 與 Python spine_lanes 同一套：L 形線區塊固定第 0 道，對照線依（群 y, idx）序取最小不重疊的一道
  function spineLanes(drawn){var lblocks={},spines=[],i,e;
    for(var di=0;di<drawn.length;di++){i=drawn[di];e=G.edges[i];if(isL(e)){var a=nodes[e.from],b=nodes[e.to],yc=b.y+H/2;if(!lblocks[e.from])lblocks[e.from]=[a.y+H,yc];else if(yc>lblocks[e.from][1])lblocks[e.from][1]=yc;}
      else if(e.type==='supplements'){var g=nodes[e.from],p=nodes[e.to],lo=Math.min(p.y+H,g.y),hi=Math.max(p.y+H,g.y);spines.push([g.y,i,p.col,lo,hi]);}}
    spines.sort(function(x,y){return x[0]!==y[0]?x[0]-y[0]:x[1]-y[1];});
    var taken=[],out={};
    spines.forEach(function(sp){var i=sp[1],col=sp[2],lo=sp[3],hi=sp[4],lane=0;
      for(;;){var busy=taken.some(function(t){return t[0]===col&&t[1]===lane&&!(hi<t[2]||lo>t[3]);});
        if(lane===0&&!busy)busy=Object.keys(lblocks).some(function(gid){var blk=lblocks[gid];return nodes[gid].col===col&&!(hi<blk[0]||lo>blk[1]);});
        if(!busy)break;lane++;}
      taken.push([col,lane,lo,hi]);out[i]=lane;});
    return out;}
  function bendPath(sx,sy,tx,ty,ex){
    if(ty===sy)return 'M'+num(sx)+','+num(sy)+' H'+num(ex);
    var d1=tx>sx?1:-1,v=ty>sy?1:-1,d2=ex>tx?1:-1,r=Math.min(CORNER_R,Math.abs(ty-sy)/2);
    return 'M'+num(sx)+','+num(sy)+' H'+num(tx-d1*r)+' Q'+num(tx)+','+num(sy)+' '+num(tx)+','+num(sy+v*r)+' V'+num(ty-v*r)+' Q'+num(tx)+','+num(ty)+' '+num(tx+d2*r)+','+num(ty)+' H'+num(ex);
  }
  // 與 Python _assign_lanes 同一套：必須在左關係 → 拓樸序（可選時 key 最小、成環時剩餘 key 最小）→ 區間著色
  function trunkCross(L,R){var n=0;L.rightYs.forEach(function(y){if((R.span[0]<y&&y<R.span[1])||R.leftYs.indexOf(y)>=0)n++;});R.leftYs.forEach(function(y){if(L.span[0]<y&&y<L.span[1])n++;});return n;}
  function overlap(a,b){return !(a.span[1]<b.span[0]||a.span[0]>b.span[1]);}
  function minHeapPush(h,v){h.push(v);var i=h.length-1;while(i>0){var p=(i-1)>>1;if(h[p]<=h[i])break;var t=h[p];h[p]=h[i];h[i]=t;i=p;}}
  function minHeapPop(h){var top=h[0],last=h.pop();if(h.length){h[0]=last;var i=0,n=h.length;for(;;){var l=2*i+1,r=l+1,m=i;if(l<n&&h[l]<h[m])m=l;if(r<n&&h[r]<h[m])m=r;if(m===i)break;var t=h[m];h[m]=h[i];h[i]=t;i=m;}}return top;}
  function assignLanes(keys,trunks){keys=keys.slice().sort();var n=keys.length,span=keys.map(function(k){return trunks[k].span;}),nbrs=[],pred=[],i,k;
    for(i=0;i<n;i++){nbrs.push([]);pred.push({});}
    var byStart=[];for(i=0;i<n;i++)byStart.push(i);byStart.sort(function(a,b){return span[a][0]-span[b][0]||a-b;});
    var active=[];
    byStart.forEach(function(ii){var s0=span[ii][0];active=active.filter(function(a){return span[a][1]>=s0;});
      active.forEach(function(a){var j=a<ii?a:ii,kk=a<ii?ii:a,cab=trunkCross(trunks[keys[j]],trunks[keys[kk]]),cba=trunkCross(trunks[keys[kk]],trunks[keys[j]]);
        if(cab<cba)pred[kk][j]=true;else if(cba<cab)pred[j][kk]=true;else if(cab>0)pred[kk][j]=true;nbrs[ii].push(a);nbrs[a].push(ii);});
      active.push(ii);});
    var succ=[],indeg=[];for(i=0;i<n;i++){succ.push([]);indeg.push(0);}
    for(k=0;k<n;k++){Object.keys(pred[k]).forEach(function(j){succ[+j].push(k);indeg[k]++;});}
    var avail=[];for(k=0;k<n;k++)if(indeg[k]===0)minHeapPush(avail,k);
    var done=[],order=[],cursor=0;for(i=0;i<n;i++)done.push(false);
    while(order.length<n){var p;if(avail.length){p=minHeapPop(avail);if(done[p])continue;}else{while(done[cursor])cursor++;p=cursor;}
      done[p]=true;order.push(p);succ[p].forEach(function(s){indeg[s]--;if(indeg[s]===0&&!done[s])minHeapPush(avail,s);});}
    var posn=[];order.forEach(function(kk,idx){posn[kk]=idx;});
    var laneI=[];order.forEach(function(kk){var m=0;nbrs[kk].forEach(function(j){if(posn[j]<posn[kk]&&laneI[j]+1>m)m=laneI[j]+1;});laneI[kk]=m;});
    var lane={};for(i=0;i<n;i++)lane[keys[i]]=laneI[i];return lane;}
  // 與 Python route_edges 同一套：跳欄邊依 dummy 列拆段、同來源併幹線、走道分車道（決定性）
  function routeEdges(drawn){
    var cy=function(n){return n.y+H/2;},right=function(n){return n.x+nodeW(n);};
    var segs=[],segCount={},i,e;
    for(var di=0;di<drawn.length;di++){i=drawn[di];e=G.edges[i];if(isL(e)||e.type==='supplements')continue;
      var chain=[nodes[e.from]];if(dummyActive(i)&&dummyY[i]){e.via.forEach(function(v){var col=v[0];chain.push({id:'~'+i+'@'+col,x:GRAPH_PAD+col*COL_PITCH,y:dummyY[i][col],col:col,subtype:''});});}
      chain.push(nodes[e.to]);segCount[i]=chain.length-1;
      for(var k=0;k<chain.length-1;k++)segs.push({sid:[i,k],e:e,a:chain[k],b:chain[k+1]});}
    var items={},members={},sidKey=function(sid){return sid[0]+'/'+sid[1];},sidCmp=function(x,y){return x[0]!==y[0]?x[0]-y[0]:x[1]-y[1];};
    segs.forEach(function(sg){var a=sg.a,b=sg.b,kind,gap;if(a.col<b.col){kind='fwd';gap=a.col;}else if(a.col>b.col){kind='back';gap=a.col-1;}else{kind='same';gap=a.col;}
      var key=a.id+'|'+b.col+'|'+sg.e.type+'|'+sg.e.style+'|'+kind;items[sidKey(sg.sid)]={sid:sg.sid,e:sg.e,a:a,b:b,kind:kind,gap:gap,key:key};(members[key]=members[key]||[]).push(sg.sid);});
    Object.keys(members).forEach(function(k){members[k].sort(sidCmp);});
    var srcSide={},syOf={};
    Object.keys(members).forEach(function(k){var info=items[sidKey(members[k][0])];var side=info.kind==='back'?'L':'R';var sk=info.a.id+' '+side;(srcSide[sk]=srcSide[sk]||[]).push(k);});
    Object.keys(srcSide).forEach(function(sk){var keys=srcSide[sk];
      var mean=function(k){var ms=members[k],s=0;for(var j=0;j<ms.length;j++)s+=cy(items[sidKey(ms[j])].b);return Math.round(s/ms.length*100)/100;};
      keys.sort(function(x,y){var mx=mean(x),my=mean(y);return mx!==my?mx-my:(x<y?-1:x>y?1:0);});
      var src=items[sidKey(members[keys[0]][0])].a;
      keys.forEach(function(k,ki){syOf[k]=Math.round((src.y+H*(ki+1)/(keys.length+1))*100)/100;});});
    var dstSide={},tyOf={};
    Object.keys(items).forEach(function(ik){var info=items[ik];var side=info.kind==='fwd'?'L':'R';var dk=info.b.id+' '+side;(dstSide[dk]=dstSide[dk]||[]).push(info.sid);});
    Object.keys(dstSide).forEach(function(dk){var sids=dstSide[dk];sids.sort(function(x,y){var ax=cy(items[sidKey(x)].a),ay=cy(items[sidKey(y)].a);return ax!==ay?ax-ay:sidCmp(x,y);});
      var tgt=items[sidKey(sids[0])].b;sids.forEach(function(sid,ki){tyOf[sidKey(sid)]=Math.round((tgt.y+H*(ki+1)/(sids.length+1))*100)/100;});});
    var trunks={};
    Object.keys(members).forEach(function(k){var ms=members[k],info=items[sidKey(ms[0])],sy=syOf[k],tys=ms.map(function(sid){return tyOf[sidKey(sid)];});
      var direct=ms.length===1&&info.kind!=='same'&&sy===tys[0];var all=[sy].concat(tys);var leftYs,rightYs;
      if(info.kind==='fwd'){leftYs=[sy];rightYs=tys.slice();}else if(info.kind==='back'){leftYs=tys.slice();rightYs=[sy];}else{leftYs=[sy].concat(tys);rightYs=[];}
      trunks[k]={gap:info.gap,kind:info.kind,sy:sy,span:[Math.min.apply(null,all),Math.max.apply(null,all)],direct:direct,src:info.a.id,type:info.e.type,style:info.e.style,leftYs:leftYs,rightYs:rightYs};});
    var laneOf={},laneMax={},nLanes={},overflow=[],byGap={};
    Object.keys(trunks).forEach(function(k){if(!trunks[k].direct)(byGap[trunks[k].gap]=byGap[trunks[k].gap]||[]).push(k);});
    Object.keys(byGap).map(Number).sort(function(x,y){return x-y;}).forEach(function(g){var lanes=assignLanes(byGap[g],trunks);var mx=0;Object.keys(lanes).forEach(function(k){laneOf[k]=lanes[k];if(lanes[k]>mx)mx=lanes[k];});laneMax[g]=mx;nLanes[g]=mx+1;if(nLanes[g]>TRUNK_MAX_LANES)overflow.push(g);});
    var segPath={},segTrunk={},trunkOut=[];
    Object.keys(members).forEach(function(k){var t=trunks[k],ms=members[k],src=items[sidKey(ms[0])].a,sx=t.kind==='back'?src.x:right(src),sy=t.sy;
      if(t.direct){var sid=ms[0],bb=items[sidKey(sid)].b,ex=t.kind==='fwd'?bb.x:right(bb);segPath[sidKey(sid)]='M'+num(sx)+','+num(sy)+' L'+num(ex)+','+num(tyOf[sidKey(sid)]);segTrunk[sidKey(sid)]='';return;}
      var lane=laneOf[k],tx=laneX(t.gap,lane,nLanes[t.gap]);
      ms.forEach(function(sid){var bb=items[sidKey(sid)].b,ex=t.kind==='fwd'?bb.x:right(bb);segPath[sidKey(sid)]=bendPath(sx,sy,tx,tyOf[sidKey(sid)],ex);segTrunk[sidKey(sid)]=k;});
      trunkOut.push({key:k,src:t.src,gap:t.gap,lane:lane,span:t.span,type:t.type,style:t.style,d:'M'+num(sx)+','+num(sy)+' H'+num(tx)+' M'+num(tx)+','+num(t.span[0])+' V'+num(t.span[1])});});
    trunkOut.sort(function(x,y){return x.key<y.key?-1:x.key>y.key?1:0;});
    var paths={},trunkOf={};
    Object.keys(segCount).forEach(function(is){var idx=+is,n=segCount[is],d=segPath[idx+'/0'],keys=segTrunk[idx+'/0']?[segTrunk[idx+'/0']]:[];
      for(var k=1;k<n;k++){var bb=items[idx+'/'+(k-1)].b,xr=right(bb),sp=segPath[idx+'/'+k];d+=' H'+num(xr)+' '+sp.substring(sp.indexOf(' ')+1);if(segTrunk[idx+'/'+k])keys.push(segTrunk[idx+'/'+k]);}
      paths[idx]=d;trunkOf[idx]=keys.join(' ');});
    return {paths:paths,trunkOf:trunkOf,trunks:trunkOut,laneMax:laneMax,overflow:overflow};
  }
  var trunkGroup=document.getElementById('graph-trunks');
  function redrawEdges(){
    var drawn=[];G.edges.forEach(function(e,i){var ok=edgeDrawn(i);edgeEls[i].classList.toggle('off',!ok);if(ok)drawn.push(i);});
    var route=routeEdges(drawn),sl=spineLanes(drawn);
    drawn.forEach(function(i){var e=G.edges[i],el=edgeEls[i];if(isL(e)){el.setAttribute('d',lPath(nodes[e.from],nodes[e.to]));el.removeAttribute('data-trunk');return;}
      if(e.type==='supplements'){el.setAttribute('d',spinePath(nodes[e.from],nodes[e.to],sl[i]||0));el.removeAttribute('data-trunk');return;}
      el.setAttribute('d',route.paths[i]);if(route.trunkOf[i])el.setAttribute('data-trunk',route.trunkOf[i]);else el.removeAttribute('data-trunk');});
    while(trunkGroup.firstChild)trunkGroup.removeChild(trunkGroup.firstChild);
    route.trunks.forEach(function(t){var pth=document.createElementNS(svg.namespaceURI,'path');pth.setAttribute('class','trunk e-'+t.type+' st-'+t.style);pth.setAttribute('data-trunk',t.key);pth.setAttribute('data-gap',t.gap);pth.setAttribute('data-lane',t.lane);pth.setAttribute('d',t.d);trunkGroup.appendChild(pth);});
    syncTrunks();
  }
  function trunkKeys(el){var k=el.getAttribute('data-trunk');return k?k.split(' '):[];}
  function syncTrunks(){var byKey={};edgeEls.forEach(function(el){if(!el)return;trunkKeys(el).forEach(function(k){(byKey[k]=byKey[k]||[]).push(el);});});
    Array.prototype.forEach.call(trunkGroup.children,function(tp){var ms=byKey[tp.getAttribute('data-trunk')]||[];['up','down','onpath','own','dim'].forEach(function(c){tp.classList.remove(c);});
      var any=function(c){return ms.some(function(el){return el.classList.contains(c);});};
      if(any('onpath'))tp.classList.add('onpath');else if(any('up'))tp.classList.add('up');else if(any('down'))tp.classList.add('down');
      if(any('own'))tp.classList.add('own');if(ms.length&&ms.every(function(el){return el.classList.contains('dim');}))tp.classList.add('dim');});}
  svg.addEventListener('mouseover',function(e){var t=e.target.closest&&e.target.closest('[data-trunk]');if(!t)return;var ks=trunkKeys(t);Array.prototype.forEach.call(svg.querySelectorAll('[data-trunk]'),function(el){el.classList.toggle('hov',trunkKeys(el).some(function(k){return ks.indexOf(k)>=0;}));});});
  svg.addEventListener('mouseout',function(e){var t=e.target.closest&&e.target.closest('[data-trunk]');if(!t)return;Array.prototype.forEach.call(svg.querySelectorAll('.hov'),function(el){el.classList.remove('hov');});});
  boxOld.addEventListener('change',function(){relayout();if(selected)select(selected,false);});
  boxDec.addEventListener('change',function(){relayout();if(selected)select(selected,false);});
  boxAll.addEventListener('change',function(){redrawEdges();});
  Array.prototype.forEach.call(document.querySelectorAll('input[data-gstate]'),function(cb){cb.addEventListener('change',function(){stateOff[cb.getAttribute('data-gstate')]=!cb.checked;applyFilter();});});
  function applyFilter(){Object.keys(nodeEls).forEach(function(id){nodeEls[id].classList.toggle('filtered',!!stateOff[nodes[id].state]);});
    G.edges.forEach(function(e,i){edgeEls[i].classList.toggle('filtered',!!stateOff[nodes[e.from].state]||!!stateOff[nodes[e.to].state]);});}
  function expandChain(id){var n=nodes[id];if(!n||n.type!=='method'||!(n.meta.superseded_versions||[]).length)return;expanded[id]=!expanded[id];relayout();if(selected)select(selected,false);}
  // ---- 平移／縮放 ----
  var tx=0,ty=0,sc=1;function apply(){root.setAttribute('transform','translate('+tx+' '+ty+') scale('+sc+')');}
  wrap.addEventListener('wheel',function(e){e.preventDefault();var r=wrap.getBoundingClientRect();var mx=e.clientX-r.left+wrap.scrollLeft,my=e.clientY-r.top+wrap.scrollTop;var k=e.deltaY<0?1.1:1/1.1;var ns=Math.min(4,Math.max(.2,sc*k));k=ns/sc;tx=mx-(mx-tx)*k;ty=my-(my-ty)*k;sc=ns;apply();},{passive:false});
  var drag=null,moved=false,nodeDrag=null;
  wrap.addEventListener('mousedown',function(e){if(e.button!==0)return;drag={x:e.clientX,y:e.clientY,tx:tx,ty:ty};moved=false;wrap.classList.add('dragging');});
  function graphXY(e){var r=wrap.getBoundingClientRect();return {x:(e.clientX-r.left+wrap.scrollLeft-tx)/sc,y:(e.clientY-r.top+wrap.scrollTop-ty)/sc};}
  window.addEventListener('mousemove',function(e){if(nodeDrag){var ddx=(e.clientX-nodeDrag.x)/sc,ddy=(e.clientY-nodeDrag.y)/sc;if(Math.abs(ddx)+Math.abs(ddy)>3){moved=true;nodeDrag.moved=true;}var nx=nodeDrag.nx+ddx,ny=nodeDrag.ny+ddy;nodeDrag.el.setAttribute('transform','translate('+nx+','+ny+')');nodeDrag.el.classList.add('node-drag');wrap.classList.add('drop-hint');
      if(nodeDrag.moved){var g=graphXY(e);nodeDrag.cand=dragCandidate(nodeDrag.id,g.x,g.y);drawDragPreview(nodeDrag.id,nodeDrag.cand,nx+nodeW(nodes[nodeDrag.id])/2,ny+H/2);}return;}
    if(!drag)return;var dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>3)moved=true;tx=drag.tx+dx;ty=drag.ty+dy;apply();});
  window.addEventListener('mouseup',function(e){if(nodeDrag){var nd=nodeDrag;nodeDrag=null;nd.el.classList.remove('node-drag');wrap.classList.remove('drop-hint');nd.el.setAttribute('transform','translate('+nd.nx+','+nd.ny+')');clearDragPreview();
      if(nd.moved){var g=graphXY(e);dropTo(nd.id,dragCandidate(nd.id,g.x,g.y));}
      return;}
    drag=null;wrap.classList.remove('dragging');});
  // 由 y 座標判定落在哪個區帶：依可見的分隔線（ext／supp）由上而下比對
  function bandAtY(gy){var band='main';['ext','supp'].forEach(function(b){var el=bandDivs[b];if(el&&!el.classList.contains('off')&&gy>=+el.getAttribute('y1'))band=b;});return band;}
  // ---- 拖曳時的即時接線預覽（0.16.1）：依游標位置判定候選落點；只畫在 #drag-preview，不進 IR、不進 SSOT ----
  var previewG=document.getElementById('drag-preview'),SVGNS=svg.namespaceURI;  // 不寫死網址（頁面不得含外部連結）
  function nodeCenter(n){return {x:n.x+nodeW(n)/2,y:n.y+H/2};}
  function hitNode(gx,gy,pred){var best=null;Object.keys(nodes).forEach(function(id){var n=nodes[id];if(!nodeVisible(id)||!pred(id,n))return;if(gx>=n.x&&gx<=n.x+nodeW(n)&&gy>=n.y&&gy<=n.y+H)best=id;});return best;}
  function activePlanOf(q){var out=null;(outE[q]||[]).forEach(function(ei){var e=G.edges[ei];if(e.type==='plans'&&nodes[e.to]&&!nodes[e.to].collapsed)out=e.to;});return out;}
  function listOrder(band){return G.nodes.filter(function(n){return n.type==='question'&&n.band===band&&questionKind(n.id);}).sort(function(a,b){return a.order-b.order;}).map(function(n){return n.id.slice(2);});}
  // 回 {kind, ok, payload, target?, band?, reason?, label?}；null＝沒有候選（放開後滑回原位、不開表單）
  function dragCandidate(id,gx,gy){var n=nodes[id];if(!n)return null;
    // 0.20.0 的三個輔助函式在舊的 node 測試樁裡不一定有：缺就退回 0.19.0 的行為（沒有 ED 情境）
    var TC=(typeof tierCand==='function')?tierCand:function(){return undefined;},EI=(typeof edInherited==='function')?edInherited:function(){return '';},DB=(typeof derivedBand==='function')?derivedBand:function(k){return nodes[k].band;};
    if(n.type==='question'&&questionKind(id)){
      var q=hitNode(gx,gy,function(k,m){return k!==id&&m.type==='question'&&questionKind(k)&&m.band===n.band;});
      if(q){var order=listOrder(n.band).filter(function(x){return x!==id.slice(2);});order.splice(order.indexOf(q.slice(2))+1,0,id.slice(2));
        return {kind:'reorder',ok:true,target:q,label:'排在 '+nodes[q].label+' 之後',payload:{list:n.band==='main'?'sub_questions':'appendix_questions',order:order}};}
      var band=bandAtY(gy);if(band===n.band)return null;
      if(band==='ext')return {kind:'set_tier',ok:false,band:band,reason:'問題（SQ／AQ）不能放 Extended Data'};   // 0.20.0
      if(n.band==='main'&&band==='supp')return {kind:'reassign',ok:true,band:band,payload:{from:id.slice(2)}};
      if(n.band==='supp'&&band==='main')return {kind:'promote',ok:true,band:band,payload:{from:id.slice(2)}};
      return {kind:n.band==='main'?'reassign':'promote',ok:false,band:band,reason:'主問題只能降到 Supplementary 帶、附錄問題只能升到 Main 帶'};}
    if(isSensItem(id)){var m=/^p:(.+)#(R\d+)$/.exec(id);
      var p=hitNode(gx,gy,function(k,x){return isActivePlan(k)&&k!=='p:'+m[1];});
      if(!p){var tcs=TC(id,bandAtY(gy));return tcs===undefined?null:tcs;}   // 0.20.0：拖到 Extended Data 帶＝單獨放入 ED；從 ED 拖回推導區帶＝移出
      return {kind:'move_sensitivity',ok:true,target:p,payload:{plan:m[1],item:m[2],to_plan:p.slice(2)}};}
    if(isActivePlan(id)){var sq=String(n.meta.sq||'');
      // 0.18.0：active plan 拖到另一個頂層 plan 上 → demote_plan（來源降為目標的敏感性子分析）；來源是主問題的 plan、目標同問題、目標非 active → 紅線
      var tp=hitNode(gx,gy,function(k,x){return x.type==='method'&&!x.parent&&k!==id&&/^p:[^#]+$/.test(k);});
      if(tp){var tsq=String(nodes[tp].meta.sq||'');
        if(nodes[tp].collapsed)return {kind:'demote_plan',ok:false,target:tp,reason:nodes[tp].label+' 不是 active plan（舊版），敏感性子分析只能併入現行版'};
        if(!/^AQ\d+$/.test(sq))return {kind:'demote_plan',ok:false,target:tp,reason:'主問題 '+sq+' 的 active plan 不能降為敏感性子分析（主問題缺 active plan 是 check_plan BLOCKER），請先把 '+sq+' 降為附錄問題'};
        if(tsq===sq)return {kind:'demote_plan',ok:false,target:tp,reason:nodes[tp].label+' 與來源同屬 '+sq+'：同一問題的兩份 plan 不能互降，那是版本取代'};
        return {kind:'demote_plan',ok:true,target:tp,label:'降為 '+nodes[tp].label+' 的敏感性子分析',payload:{plan:id.slice(2),to_plan:tp.slice(2)}};}
      var q2=hitNode(gx,gy,function(k,x){return x.type==='question'&&questionKind(k)&&k!=='q:'+sq;});
      if(!q2){var tcp=TC(id,bandAtY(gy));return tcp===undefined?null:tcp;}   // 0.20.0：plan 放入／移出 Extended Data（群、子分析、結果、驗證跟著走）
      var ap=activePlanOf(q2);
      if(ap)return {kind:'move_plan',ok:false,target:q2,reason:nodes[q2].label+' 已有 active plan '+nodes[ap].label+'：那是合併兩份分析計畫，不是搬移，須另行設計'};
      if(!/^AQ\d+$/.test(sq))return {kind:'move_plan',ok:false,target:q2,reason:'主問題 '+sq+' 的 active plan 不能搬走（主問題缺 active plan 是 check_plan BLOCKER），請先降階'};
      return {kind:'move_plan',ok:true,target:q2,payload:{plan:id.slice(2),to_question:q2.slice(2)}};}
    if(n.type==='figure'){var b=bandAtY(gy);if(b===n.band)return null;return {kind:'set_role',ok:true,band:b,payload:{figure:id.slice(2),role:BAND_ROLE[b]||''}};}
    if(n.type==='validation'){var bv=bandAtY(gy);if(bv===n.band)return null;var tcv=TC(id,bv);return tcv===undefined?null:tcv;}   // 0.20.0：驗證只有 ED 歸屬這一種拖法
    if(typeof isAgg==='function'&&isAgg(id)&&isDragResult(id)){var keysA=aggKeys(id),ownerA=resultOwner(id),nA=keysA.length,mk=function(pl,item){return keysA.map(function(k){return {kind:'move_result',payload:{key:k,to_plan:pl,to_item:item||''}};});};
      // 0.19.0 聚合節點（裡面全部鍵一起搬，順序照 meta.keys）：拖到另一個 active plan 上 → n 筆 move_result{key,to_plan}（A 型，全部升為目標的主要結果）；
      // 拖到別的子分析上 → n 筆 move_result{key,to_plan,to_item}；拖到 Main 帶（所屬 plan 在 Main）→ n 筆 move_result{key,to_plan:<本 plan>}（升回本 plan outputs）；
      // 拖到結果節點上 → 紅線（nest_result 只收主要結果）；紅線規則沿用結果節點
      var rtA=hitNode(gx,gy,function(k,x){return k!==id&&x.type==='result';});
      if(rtA)return {kind:'nest_result',ok:false,target:rtA,reason:n.label+' 是次要結果聚合節點：只有 outputs 的主要結果能掛到主結果下（請先升為主要結果——拖聚合節點到方法上，或在面板逐鍵升級）'};
      var tA=hitNode(gx,gy,function(k,x){return isSensItem(k)||isActivePlan(k);});
      if(!tA){var bA=bandAtY(gy);if(bA==='ext'&&n.band!=='ext')return {kind:'set_tier',ok:false,band:bA,reason:'次要結果跟子分析走，請拖子分析節點'};   // 0.20.0
        if(n.band==='ext'&&bA!=='ext'&&EI(id))return {kind:'set_tier',ok:false,band:bA,reason:'這個節點的 ED 歸屬來自 '+EI(id)+'，請拖那個節點'};
        if(bA==='main'){var oq=String((nodes['p:'+ownerA]||{meta:{}}).meta.sq||'');if(!/^SQ\d+$/.test(oq))return {kind:'move_result',ok:false,band:bA,reason:'所屬 plan '+ownerA+'（'+oq+'）不在 Main 帶：要升為主問題的主要結果請拖到目標方法節點上'};
          if(!nA)return {kind:'move_result',ok:false,band:bA,reason:n.label+'：這個子分析沒有自有的次要鍵可搬'};
          return {kind:'move_result',ok:true,band:bA,label:'放到 Main 帶、'+nA+' 鍵升回本 plan '+ownerA+' 的 outputs',payload:{key:keysA[0],to_plan:ownerA,to_item:''},items:mk(ownerA,'')};}
        return null;}   // Supplementary 帶：次要結果本來就在子分析之下，無事可做
      if(!nA)return {kind:'move_result',ok:false,target:tA,reason:n.label+'：這個子分析沒有自有的次要鍵可搬'};
      if(isSensItem(tA)){var mA=/^p:(.+)#(R\d+)$/.exec(tA);if(tA===n.parent)return null;
        return {kind:'move_result',ok:true,target:tA,label:nA+' 鍵成為 '+mA[1]+' '+mA[2]+' 的次要結果',payload:{key:keysA[0],to_plan:mA[1],to_item:mA[2]},items:mk(mA[1],mA[2])};}
      return {kind:'move_result',ok:true,target:tA,label:nA+' 鍵成為 '+tA.slice(2)+' 的主要結果'+(tA==='p:'+ownerA?'（升回本 plan outputs）':''),payload:{key:keysA[0],to_plan:tA.slice(2),to_item:''},items:mk(tA.slice(2),'')};}
    if(n.type==='result'&&isDragResult(id)){var key=id.slice(2),owner=resultOwner(id),decl=(n.meta.declared_by||[]),rk=String(n.meta.result_kind||'');
      // 0.16.5 結果主從（節點落點最優先）：頂層主要結果或支撐結果拖到同 plan 的另一個頂層主要結果上 → nest_result；跨 plan／次要／已是支撐結果的目標 → 紅
      // 頂層主要結果＝在 outputs、沒有 parent、subtype primary；支撐結果＝subtype supporting（parent 為 r:<主結果>）
      var isTopResult=function(k){var x=nodes[k];return !!(x&&x.type==='result'&&!x.parent&&x.subtype==='primary'&&isDragResult(k));};
      var isSupporting=function(k){var x=nodes[k];return !!(x&&x.type==='result'&&x.subtype==='supporting'&&x.parent);};
      var rt=hitNode(gx,gy,function(k,x){return k!==id&&x.type==='result';});
      if(rt&&rt===n.parent)return null;   // 支撐結果放回自己的主結果上：無事可做、滑回原位
      if(rt&&!(isTopResult(id)||isSupporting(id)))return {kind:'nest_result',ok:false,target:rt,reason:key+' 是'+({secondary:'次要',undeclared:'未宣告'}[rk]||'非主要')+'結果：只有 outputs 的主要結果能掛到主結果下（次要結果請先升為主要結果——拖聚合節點到方法上，或在面板逐鍵升級）'};
      if(rt){var rn=nodes[rt],rown=resultOwner(rt);
        if(!rown||rown!==owner)return {kind:'nest_result',ok:false,target:rt,reason:rn.label+' 屬 '+(rown||'非 active plan')+'、'+key+' 屬 '+owner+'：主從只能在同一份 plan 的 outputs 內宣告'};
        if(String(rn.meta.result_kind||'')!=='primary')return {kind:'nest_result',ok:false,target:rt,reason:rn.label+' 是'+({secondary:'次要',undeclared:'未宣告'}[rn.meta.result_kind]||'非主要')+'結果，不能當主結果（主結果須在 outputs）'};
        if(isSupporting(rt))return {kind:'nest_result',ok:false,target:rt,reason:rn.label+' 自己已是 '+String(rn.meta.supports||'')+' 的支撐結果，不能再當主結果（支撐結果只允許一層）'};
        if((n.meta.supporting_ids||[]).length)return {kind:'nest_result',ok:false,target:rt,reason:key+' 自己是 '+(n.meta.supporting_ids||[]).map(function(x){return x.slice(2);}).join('／')+' 的主結果，掛到別的結果下會變兩層；請先把那些支撐結果拉回頂層'};
        return {kind:'nest_result',ok:true,target:rt,label:(isSupporting(id)?'換主結果：成為 ':'成為 ')+rt.slice(2)+' 的支撐結果（同 plan、同一區帶）',payload:{key:key,under:rt.slice(2)}};}
      if(isSupporting(id)){// 支撐結果：拖到自己所在帶的空白處＝拉回頂層；拖到別帶 → 先拉回頂層（紅）；拖到方法／子分析上照舊走 move_result
        var t0=hitNode(gx,gy,function(k,x){return isSensItem(k)||isActivePlan(k);});
        if(!t0){var b0=bandAtY(gy);if(b0==='ext'&&n.band!=='ext')return {kind:'set_tier',ok:false,band:b0,reason:key+' 是 '+String(n.meta.supports||'')+' 的支撐結果：支撐結果跟主結果走，請拖主結果'};   // 0.20.0
          if(n.band==='ext'&&b0!=='ext'&&EI(id))return {kind:'set_tier',ok:false,band:b0,reason:'這個節點的 ED 歸屬來自 '+EI(id)+'，請拖那個節點'};
          if(b0===n.band)return {kind:'nest_result',ok:true,band:b0,label:'拉回頂層：'+key+' 不再是 '+String(n.meta.supports||'')+' 的支撐結果',payload:{key:key,under:''}};
          return {kind:'move_result',ok:false,band:b0,reason:key+' 是 '+String(n.meta.supports||'')+' 的支撐結果：換帶前請先拉回頂層（拖到目前所在帶的空白處）'};}}
      var t=hitNode(gx,gy,function(k,x){return isSensItem(k)||isActivePlan(k);});
      if(!t){// 0.16.4 區帶落點（節點落點優先）：主要結果 Main → Supplementary、次要（或附錄問題的主要）結果 Supplementary → Main；放開後表單以下拉選確切落點
        var b2=bandAtY(gy);var tcr=TC(id,b2);if(tcr!==undefined)return tcr;   // 0.20.0：進 ED／出 ED；其餘（拖到既非 ext 也非推導區帶的帶）走原本規則，n.band 以推導區帶代入
        var nb=(n.band==='ext')?DB(id):n.band;
        var ownerSq=String((nodes['p:'+owner]||{meta:{}}).meta.sq||''),ownerMain=/^SQ\d+$/.test(ownerSq);
        function planOpts(pred,tag){var o=[];G.nodes.forEach(function(x){if(!isActivePlan(x.id)||decl.indexOf(x.id)>=0||!pred(String((x.meta||{}).sq||''),x.id))return;o.push({label:x.id.slice(2)+' 的 outputs'+(tag||''),payload:{key:key,to_plan:x.id.slice(2),to_item:''}});});return o;}
        if(rk==='primary'&&nb==='main'&&b2==='supp'){var opts=[{label:'新增一個敏感性子分析（補充結果）',payload:{key:key,to_plan:owner,new_item:'補充結果：'+key+' 由主要結果降為次要結果'}}];  // 預設描述與 ssot_actions_common.NEW_ITEM_DEFAULT 同一句
          G.nodes.filter(function(x){return isSensItem(x.id)&&x.id.indexOf('p:'+owner+'#')===0&&decl.indexOf(x.id)<0;}).sort(function(a,b){return (+/#R(\d+)$/.exec(a.id)[1])-(+/#R(\d+)$/.exec(b.id)[1]);})
            .forEach(function(x){var rid=x.id.split('#')[1];opts.push({label:rid+'：'+String((x.meta||{}).change||'').slice(0,40),payload:{key:key,to_plan:owner,to_item:rid}});});
          opts=opts.concat(planOpts(function(sq){return /^AQ\d+$/.test(sq);}));
          return {kind:'move_result',ok:true,band:b2,label:'放到 Supplementary 帶、降為次要結果（放開後選落點）',payload:opts[0].payload,options:opts};}
        if(rk==='primary'&&nb==='supp'&&b2==='supp')return {kind:'move_result',ok:false,band:b2,reason:key+' 已在 Supplementary（附錄問題 '+ownerSq+' 的主要結果）'};
        if((rk==='secondary'||(rk==='primary'&&nb==='supp'))&&b2==='main'){var opts2=[];
          if(ownerMain&&rk==='secondary'&&decl.indexOf('p:'+owner)<0)opts2.push({label:'升回本 plan 的 outputs（'+owner+'）',payload:{key:key,to_plan:owner,to_item:''}});
          opts2=opts2.concat(planOpts(function(sq,pid){return /^SQ\d+$/.test(sq)&&pid!=='p:'+owner;}));
          if(!opts2.length)return {kind:'move_result',ok:false,band:b2,reason:'沒有主問題的 active plan 可以收 '+key+'（Main 帶沒有可放的 outputs）'};
          return {kind:'move_result',ok:true,band:b2,label:'放到 Main 帶、升為主要結果（放開後選落點）',payload:opts2[0].payload,options:opts2};}
        return null;}
      if(isSensItem(t)){var mm=/^p:(.+)#(R\d+)$/.exec(t);
        if(decl.indexOf(t)>=0)return {kind:'move_result',ok:false,target:t,reason:nodes[t].label+' 的 expected_keys 已含 '+key};
        return {kind:'move_result',ok:true,target:t,label:'成為 '+mm[1]+' '+mm[2]+' 的次要結果',payload:{key:key,to_plan:mm[1],to_item:mm[2]}};}
      if(decl.indexOf(t)>=0)return {kind:'move_result',ok:false,target:t,reason:nodes[t].label+' 的 outputs 已含 '+key+(t==='p:'+owner?'，無事可做':'')};
      return {kind:'move_result',ok:true,target:t,label:'成為 '+t.slice(2)+' 的主要結果'+(t==='p:'+owner?'（同一份 plan 出一版）':''),payload:{key:key,to_plan:t.slice(2),to_item:''}};}
    return null;}
  function clearDragPreview(){if(!previewG)return;while(previewG.firstChild)previewG.removeChild(previewG.firstChild);
    Object.keys(nodeEls).forEach(function(k){nodeEls[k].classList.remove('drop-ok','drop-bad');});
    BANDS.forEach(function(b){[bandTitles[b],bandDivs[b]].forEach(function(el){if(el)el.classList.remove('drop-ok','drop-bad');});});}
  function bandRect(b){var top=(b==='main'||!bandDivs[b]||bandDivs[b].classList.contains('off'))?0:+bandDivs[b].getAttribute('y1');var bottom=+svg.getAttribute('height');
    BANDS.forEach(function(o){var d=bandDivs[o];if(o!==b&&d&&!d.classList.contains('off')){var y=+d.getAttribute('y1');if(y>top&&y<bottom)bottom=y;}});
    return {y:top,h:Math.max(0,bottom-top),w:+svg.getAttribute('width')};}
  function drawDragPreview(id,cand,cx,cy){clearDragPreview();if(!cand||!previewG)return;var cls=cand.ok?'drop-ok':'drop-bad';
    if(cand.band){var rc=bandRect(cand.band);var rect=document.createElementNS(SVGNS,'rect');rect.setAttribute('x',0);rect.setAttribute('y',rc.y);rect.setAttribute('width',rc.w);rect.setAttribute('height',rc.h);rect.setAttribute('class','band-hl '+cls);previewG.appendChild(rect);
      [bandTitles[cand.band],bandDivs[cand.band]].forEach(function(el){if(el)el.classList.add(cls);});}
    if(cand.target&&nodes[cand.target]){nodeEls[cand.target].classList.add(cls);var tc=nodeCenter(nodes[cand.target]);var line=document.createElementNS(SVGNS,'path');
      line.setAttribute('d','M'+cx+','+cy+' L'+tc.x+','+tc.y);line.setAttribute('class','preview '+(cand.kind==='nest_result'?'e-supports':(cand.kind==='move_sensitivity'||cand.kind==='demote_plan'||(cand.kind==='move_result'&&cand.payload&&cand.payload.to_item)?'e-sensitivity':'e-plans'))+' '+cls);previewG.appendChild(line);}
    var lbl=document.createElementNS(SVGNS,'text');lbl.setAttribute('x',cx+12);lbl.setAttribute('y',cy-10);lbl.setAttribute('class','preview-label '+cls);
    lbl.textContent=cand.ok?(ACT_LABEL[cand.kind]+(cand.label?'：'+cand.label:'')+(formOnDrop?'（放開後填理由）':'（放開即暫存）')):cand.reason;previewG.appendChild(lbl);}
  // 放開：無候選 → 滑回原位；非法 → toast 說原因；合法 → 0.17.1 預設直接暫存（各 kind 的預設值、理由空；toast 附「復原」），
  // 勾了「放開時先開表單」才開表單（0.17.0 行為：父節點欄位已帶入、唯讀，使用者填理由後加入暫存或單獨送出）
  function dropTo(id,cand){if(!cand)return;if(!cand.ok){toast(cand.reason||'這個位置不能放');return;}
    if(!serverOk){toast('用 progress_server.py 開啟才能送出（file:// 頁面無法送表單）');return;}
    if(cand.items&&cand.items.length>1){stageMany(cand.items);return;}   // 0.19.0 聚合節點多鍵：整批暫存（表單只收一筆，理由在暫存清單填）；1 鍵走原本單筆流程
    if(formOnDrop){openActionForm(cand.kind,cand.payload,cand.options);return;}
    stageDirect(cand);}
  function center(id){var n=nodes[id];if(!n)return;tx=wrap.clientWidth/2-(n.x+W/2)*sc;ty=wrap.clientHeight/2-(n.y+H/2)*sc;apply();}
  // ---- 高亮 ----
  function clearClasses(){Object.keys(nodeEls).forEach(function(id){nodeEls[id].classList.remove('sel','up','down','onpath','hit','dim');});edgeEls.forEach(function(el){if(el)el.classList.remove('up','down','onpath','dim','own');});Array.prototype.forEach.call(trunkGroup.children,function(tp){['up','down','onpath','own','dim'].forEach(function(c){tp.classList.remove(c);});});}
  function walk(start,dir){var seen={},edges={},stack=[start];while(stack.length){var c=stack.pop();var list=(dir>0?outE[c]:inE[c])||[];for(var i=0;i<list.length;i++){var ei=list[i];var e=G.edges[ei];var nxt=dir>0?e.to:e.from;if(!nodeVisible(nxt))continue;edges[ei]=true;if(!seen[nxt]&&nxt!==start){seen[nxt]=true;stack.push(nxt);}}}return {nodes:seen,edges:edges};}
  function select(id,doCenter){
    if(!nodes[id])return;selected=id;pathEdges={};pathNodes=null;clearClasses();redrawEdges();
    var up=walk(id,-1),down=walk(id,1);
    Object.keys(nodeEls).forEach(function(k){var el=nodeEls[k];if(k===id)el.classList.add('sel');else if(up.nodes[k])el.classList.add('up');else if(down.nodes[k])el.classList.add('down');else el.classList.add('dim');});
    edgeEls.forEach(function(el,i){if(!el)return;var e=G.edges[i];if(e.from===id||e.to===id)el.classList.add('own');if(up.edges[i])el.classList.add('up');else if(down.edges[i])el.classList.add('down');else el.classList.add('dim');});
    syncTrunks();renderPanel(id,up,down);if(doCenter)center(id);
  }
  function clearAll(){selected=null;pathEdges={};pathNodes=null;tour=null;clearClasses();redrawEdges();panel.hidden=true;}
  function shortestPath(a,b){
    var prev={};prev[a]=null;var q=[a],qi=0;
    while(qi<q.length){var c=q[qi++];if(c===b)break;var lists=[outE[c]||[],inE[c]||[]];
      for(var d=0;d<2;d++){var list=lists[d];for(var i=0;i<list.length;i++){var ei=list[i];var e=G.edges[ei];var nxt=d===0?e.to:e.from;if(!nodeVisible(nxt))continue;if(!(nxt in prev)){prev[nxt]={n:c,e:ei};q.push(nxt);}}}}
    if(!(b in prev))return null;var nodesP=[],edgesP=[],c=b;while(c!==null){nodesP.unshift(c);var p=prev[c];if(p){edgesP.unshift(p.e);c=p.n;}else c=null;}return {nodes:nodesP,edges:edgesP};
  }
  function showPath(a,b){
    var p=shortestPath(a,b);clearClasses();pathEdges={};
    var h='<h3>路徑：'+esc(nodes[a].label)+' → '+esc(nodes[b].label)+'</h3>';
    if(!p){redrawEdges();Object.keys(nodeEls).forEach(function(k){if(k!==a&&k!==b)nodeEls[k].classList.add('dim');else nodeEls[k].classList.add('sel');});edgeEls.forEach(function(el){if(el)el.classList.add('dim');});h+='<p>無路徑（在目前顯示的節點之間找不到連通路徑）。</p>';}
    else{var onN={};p.nodes.forEach(function(n){onN[n]=true;});p.edges.forEach(function(e){pathEdges[e]=true;});redrawEdges();
      Object.keys(nodeEls).forEach(function(k){nodeEls[k].classList.add(onN[k]?'onpath':'dim');});edgeEls.forEach(function(el,i){if(el)el.classList.add(pathEdges[i]?'onpath':'dim');});
      h+='<p>共 '+p.edges.length+' 步（無向最短路徑，含預設隱藏的邊）：</p><ol>';
      for(var i=0;i<p.edges.length;i++){var e=G.edges[p.edges[i]];var from=p.nodes[i],to=p.nodes[i+1];var dirTxt=(e.from===from)?'→':'←';h+='<li><span class="goto" data-goto="'+esc(from)+'">'+esc(nodes[from].label)+'</span> '+dirTxt+' '+esc(edgeLabel[e.type]||e.type)+' '+dirTxt+' <span class="goto" data-goto="'+esc(to)+'">'+esc(nodes[to].label)+'</span></li>';}
      h+='</ol>';}
    syncTrunks();body.innerHTML=h;panel.hidden=false;
  }
  function plainCaption(c){return String(c||'').replace(/\*{1,2}/g,'');}
  function figSrc(f){return f.meta.data_uri||f.meta.file||'';}
  function figBlock(f){
    var src=figSrc(f);var h='<div class="fig" data-fig="'+esc(f.id)+'">';
    if(src)h+='<img loading="lazy" alt="'+esc(f.id)+'" data-src="'+esc(src)+'" data-cap="'+esc(plainCaption(f.meta.caption))+'">';
    else h+='<div class="missing">找不到檔案：（manifest 未給 file）</div>';
    h+='<div class="cap"><b>'+esc(f.id)+'</b>'+(f.badge?' <span class="src">'+esc(f.badge)+'</span>':'')+'<br>'+esc(plainCaption(f.meta.caption)||'—')+'</div>';
    h+='<div class="src">role '+esc(f.meta.role||'—')+' · status '+esc(f.meta.status||'—')+' · '+esc(f.meta.figure_number||'—')+' · '+esc(stateZh[f.state]||f.state)+'</div>';
    return h+'</div>';
  }
  function tableBlock(t){
    if(!t)return '';var h='<p class="src">共 '+t.n_rows+' 列'+(t.truncated?'（顯示前 '+t.rows.length+'）':'')+'，'+t.columns.length+' 欄</p>';
    h+='<div class="rt-wrap"><table class="rt"><thead><tr>';t.columns.forEach(function(c){h+='<th>'+esc(c)+'</th>';});h+='</tr></thead><tbody>';
    t.rows.forEach(function(r){h+='<tr>';(r||[]).forEach(function(c){h+='<td>'+esc(c===null||c===undefined?'':c)+'</td>';});h+='</tr>';});
    return h+'</tbody></table></div>';
  }
  function bindImages(){Array.prototype.forEach.call(body.querySelectorAll('.fig img[data-src]'),function(img){
    img.addEventListener('error',function(){var d=document.createElement('div');d.className='missing';d.textContent='找不到檔案：'+(img.getAttribute('data-src')||'').slice(0,200);img.replaceWith(d);});
    img.addEventListener('click',function(e){e.stopPropagation();openLightbox(img.getAttribute('data-src'),img.getAttribute('data-cap'));});
    img.src=img.getAttribute('data-src');});}
  var lb=document.getElementById('lightbox'),lbImg=lb.querySelector('img'),lbCap=lb.querySelector('.lb-cap');
  function openLightbox(src,cap){lbImg.src=src;lbImg.alt=cap||'';lbCap.textContent=cap||'';lb.hidden=false;}
  function closeLightbox(){lb.hidden=true;lbImg.removeAttribute('src');}
  lb.addEventListener('click',closeLightbox);
  function metaRows(m,skip){var keys=Object.keys(m||{}).filter(function(k){return skip.indexOf(k)<0&&k!=='inbox'&&k!=='band_source';});if(!keys.length)return '—';var h='<ul>';keys.forEach(function(k){var v=m[k];if(Array.isArray(v))v=v.join('、');if(typeof v==='boolean')v=v?'true':'false';h+='<li><b>'+esc(k)+'</b>：'+esc(v)+'</li>';});return h+'</ul>';}
  function edgeList(list,dir){if(!list||!list.length)return '—';var h='<ul>';list.forEach(function(ei){var e=G.edges[ei];var other=dir>0?e.to:e.from;h+='<li>'+esc(edgeLabel[e.type]||e.type)+(e.label?'（'+esc(e.label)+'）':'')+' '+(dir>0?'→':'←')+' <span class="goto" data-goto="'+esc(other)+'">'+esc(nodes[other].label)+'</span>'+(nodeVisible(other)?'':'（目前隱藏）')+(e.default_visible?'':' <span class="src">預設不畫</span>')+'<br><span class="src">'+esc(e.source)+'</span></li>';});return h+'</ul>';}
  // 0.19.0 聚合節點面板的鍵清單：> AGG_PAGE 筆分頁＋搜尋框；每鍵旁「升為主要結果」（連上 server 才可按）
  var AGG_PAGE=200,aggUi={q:'',page:0};
  function aggKeyList(id){var n=nodes[id],ks=(n&&n.meta&&n.meta.keys)||[],owner=String((n&&n.meta&&n.meta.plan_id)||''),q=aggUi.q.toLowerCase();
    var hit=q?ks.filter(function(k){return k.key.toLowerCase().indexOf(q)>=0||String(k.description||'').toLowerCase().indexOf(q)>=0;}):ks;
    var pages=Math.max(1,Math.ceil(hit.length/AGG_PAGE));if(aggUi.page>=pages)aggUi.page=pages-1;if(aggUi.page<0)aggUi.page=0;var from=aggUi.page*AGG_PAGE,slice=hit.slice(from,from+AGG_PAGE);
    var h='';if(ks.length>AGG_PAGE||q)h+='<div class="agg-tools"><input type="search" class="agg-search" placeholder="搜尋鍵名／描述" value="'+esc(aggUi.q)+'"> <span class="src">'+hit.length+' 筆'+(pages>1?'，第 '+(aggUi.page+1)+'／'+pages+' 頁':'')+'</span>'+(pages>1?' <button type="button" class="agg-page" data-d="-1"'+(aggUi.page===0?' disabled':'')+'>上一頁</button> <button type="button" class="agg-page" data-d="1"'+(aggUi.page>=pages-1?' disabled':'')+'>下一頁</button>':'')+'</div>';
    if(!ks.length)return h+'<span class="src">這個聚合節點沒有鍵（自有次要鍵都已搬走）</span>';
    h+='<ul class="agg-list">'+slice.map(function(k){var st=!k.registered?'未登錄':(k.validated?'已驗證（'+(k.validated_by||[]).join('、')+'）':'未驗證');
      return '<li><code>'+esc(k.key)+'</code>：'+esc(st)+(k.evidence_owned_by?'；evidence_owned_by '+esc(k.evidence_owned_by):'')+(k.description?'<br><span class="src">'+esc(k.description)+'</span>':'')+(owner&&isActivePlan('p:'+owner)?' <button type="button" class="agg-promote" data-key="'+esc(k.key)+'" data-plan="'+esc(owner)+'"'+(serverOk?'':' disabled title="用 progress_server.py 開啟才能暫存"')+'>升為主要結果</button>':'')+'</li>';}).join('')+'</ul>';return h;}
  function renderPanel(id,up,down){
    var n=nodes[id];var h='';
    if(tour!==null)h+=tourLine();
    h+='<h3>'+esc(typeLabel[n.type]||n.type)+' · '+esc(n.label)+(n.badge?' <span class="src">'+esc(n.badge)+'</span>':'')+' <button type="button" class="inbox-comment" data-target="'+esc(id)+'"'+(serverOk?'':' disabled title="用 progress_server.py 開啟才能送出"')+'>＋ 意見</button></h3><dl>';
    if(n.meta.inbox&&n.meta.inbox.length){h+='<dt>收件匣（待處理）</dt><dd>'+n.meta.inbox.map(function(x){var it=(ir.inbox&&ir.inbox.items||[]).filter(function(y){return y.id===x;})[0];return esc(x)+(it?'：'+esc(it.title):'');}).join('<br>')+'</dd>';}
    h+='<dt>title</dt><dd>'+esc(n.title||'—')+'</dd>';
    h+='<dt>state</dt><dd>'+esc(stateZh[n.state]||n.state)+'</dd>';
    h+='<dt>source</dt><dd><span class="src">'+esc(n.source)+'</span></dd>';
    var skip=[];
    var bandZh={main:'Main（主結果鏈）',ext:'Extended Data（延伸資料）',supp:'Supplementary（補充：附錄問題與補充圖表）'};
    h+='<dt>區帶</dt><dd>'+esc(bandZh[n.band]||n.band)+(n.type==='figure'?'（依 '+(n.meta.role_source==='manifest'?'manifest role '+esc(n.meta.role||'—'):'呈現的結果推導')+'）':bandSourceZh(id))+'</dd>';
    if(n.type==='method'&&n.subtype==='sensitivity_group'){skip=['plan_id','sensitivity_ids','supplements'];
      h+='<dt>所屬分析</dt><dd><span class="goto" data-goto="'+esc(n.parent)+'">'+esc(nodes[n.parent]?nodes[n.parent].label:n.parent)+'</span>（0.18.0 起群縮排在所屬 plan 之下、區帶跟 plan；plan → 群為 L 形父子線）</dd>';
      var gids=n.meta.sensitivity_ids||[];h+='<dt>子分析（'+gids.length+'）</dt><dd>'+(gids.length?'<ul>'+gids.map(function(sid){var sn=nodes[sid];return '<li><span class="goto" data-goto="'+esc(sid)+'">'+esc(sn?sn.label:sid)+'</span>'+(sn?'：'+esc(stateZh[sn.state]||sn.state)+(sn.badge?'（'+esc(sn.badge)+'）':''):'')+'</li>';}).join('')+'</ul>':'無')+'</dd>';
      if(n.parent&&nodes[n.parent])h+='<dd><span class="expand" data-nest="'+esc(n.parent)+'">'+(nestHidden[n.parent]?'展開敏感性分析':'收合敏感性分析')+'</span></dd>';}
    else if(n.type==='method'&&n.subtype==='sensitivity'){skip=['change','expected_keys','registered_keys','executed','execution_note'];
      var grp=nodes[n.parent],ownerId=grp&&grp.parent?grp.parent:'';
      h+='<dt>父分析</dt><dd><span class="goto" data-goto="'+esc(n.parent)+'">'+esc(grp?grp.label:n.parent)+'</span></dd>';
      if(ownerId)h+='<dt>所屬分析</dt><dd><span class="goto" data-goto="'+esc(ownerId)+'">'+esc(nodes[ownerId]?nodes[ownerId].label:ownerId)+'</span></dd>';
      h+='<dt>change</dt><dd>'+esc(n.meta.change||'—')+'</dd>';
      var reg={};(n.meta.registered_keys||[]).forEach(function(k){reg[k]=true;});
      h+='<dt>expected_keys（'+(n.meta.expected_keys||[]).length+'）</dt><dd>'+((n.meta.expected_keys||[]).length?'<ul>'+n.meta.expected_keys.map(function(k){return '<li>'+(nodes['r:'+k]?'<span class="goto" data-goto="r:'+esc(k)+'">'+esc(k)+'</span>':esc(k))+'（'+(reg[k]?'已登錄':'未登錄')+'）</li>';}).join('')+'</ul>':'—')+'</dd>';
      h+='<dt>executed</dt><dd>'+esc(n.meta.executed===null||n.meta.executed===undefined?'—':String(n.meta.executed))+'</dd>';
      if(n.meta.execution_note)h+='<dt>execution_note</dt><dd>'+esc(n.meta.execution_note)+'</dd>';
      var secs=G.nodes.filter(function(m){return m.type==='result'&&m.parent===id;});
      h+='<dt>次要結果（'+secs.length+'）</dt><dd>'+(secs.length?secs.map(function(m){return '<span class="goto" data-goto="'+esc(m.id)+'">'+esc(m.label)+'</span>';}).join('、'):'無')+'</dd>';}
    else if(n.type==='method'){skip=['models','superseded_versions','amendment_reason','sensitivity_ids','group_id','sq','sq_original'];
      if(n.meta.sq)h+='<dt>問題</dt><dd>'+(nodes['q:'+n.meta.sq]?'<span class="goto" data-goto="q:'+esc(n.meta.sq)+'">'+esc(n.meta.sq)+'</span>':esc(n.meta.sq))+(n.meta.sq_original?'（index 寫 '+esc(n.meta.sq_original)+'，已併入 '+esc(n.meta.sq)+'）':'')+'</dd>';
      h+='<dt>models</dt><dd>'+esc((n.meta.models||[]).join('、')||'—')+'</dd>';
      var sids=n.meta.sensitivity_ids||[];h+='<dt>敏感性子分析（'+sids.length+'）</dt><dd>'+(sids.length?'<ul>'+sids.map(function(sid){var sn=nodes[sid];return '<li><span class="goto" data-goto="'+esc(sid)+'">'+esc(sn?sn.label:sid)+'</span>'+(sn?'：'+esc(stateZh[sn.state]||sn.state)+(sn.badge?'（'+esc(sn.badge)+'）':''):'')+'</li>';}).join('')+'</ul>'+(n.meta.group_id&&nodes[n.meta.group_id]&&!n.collapsed?'<span class="expand" data-nest="'+esc(id)+'">'+(nestHidden[id]?'展開敏感性分析':'收合敏感性分析')+'</span>（群 <span class="goto" data-goto="'+esc(n.meta.group_id)+'">'+esc(nodes[n.meta.group_id].label)+'</span> 與其子分析、次要結果一起收合）':''):'無')+'</dd>';
      var sv=n.meta.superseded_versions||[];h+='<dt>superseded_versions（'+sv.length+'）</dt><dd>'+(sv.length?sv.map(function(p){return '<span class="goto" data-goto="p:'+esc(p)+'">'+esc(p)+'</span>';}).join('、')+' <span class="expand" data-expand="'+esc(id)+'">'+(expanded[id]?'收合舊版':'展開舊版')+'</span>':'無')+'</dd>';
      if(n.meta.amendment_reason)h+='<dt>amendment_reason</dt><dd>'+esc(n.meta.amendment_reason)+'</dd>';}
    if(isAgg(id)){skip=['keys','n_keys','n_unregistered','n_unvalidated','cited_by_figures','validated','declared_by','result_kind','robustness_id','plan_id','evidence_owned_by','evidence_keys'];
      // 0.19.0 次要結果聚合節點：鍵全列（> 200 筆分頁＋搜尋），每鍵旁「升為主要結果」＝暫存一筆 move_result{key, to_plan:<本 plan>}
      var ownerP='p:'+String(n.meta.plan_id||'');
      h+='<dt>父子分析</dt><dd><span class="goto" data-goto="'+esc(n.parent)+'">'+esc(nodes[n.parent]?nodes[n.parent].label:n.parent)+'</span>（宣告粒度：有次要鍵的敏感性子分析一個次要結果節點，expected_keys 中只在此宣告的鍵全列於下）</dd>';
      if(nodes[ownerP])h+='<dt>所屬 plan</dt><dd><span class="goto" data-goto="'+esc(ownerP)+'">'+esc(nodes[ownerP].label)+'</span></dd>';
      if(n.meta.evidence_owned_by)h+='<dt>evidence_owned_by</dt><dd>'+esc(n.meta.evidence_owned_by)+'（引用鍵 '+esc((n.meta.evidence_keys||[]).join('、')||'—')+'；那些鍵歸該 plan，不在本節點）</dd>';
      var ks=n.meta.keys||[];h+='<dt>鍵（'+ks.length+'；未登錄 '+(n.meta.n_unregistered||0)+'／未驗證 '+(n.meta.n_unvalidated||0)+'）</dt><dd id="agg-keys" data-agg="'+esc(id)+'">'+aggKeyList(id)+'</dd>';
      var cf=n.meta.cited_by_figures||[];h+='<dt>引用的圖表（'+cf.length+'）</dt><dd>'+(cf.length?cf.map(function(f){return '<span class="goto" data-goto="f:'+esc(f)+'">'+esc(nodes['f:'+f]?nodes['f:'+f].label:f)+'</span>';}).join('、'):'無')+'</dd>';
      if(isDragResult(id))h+='<dt>動作</dt><dd><span class="src">拖整個節點到別的方法節點上＝全部鍵升為該 plan 的主要結果（各一筆 move_result）；拖到別的子分析上＝全部鍵改掛該子分析；所屬 plan 在 Main 時拖到 Main 帶＝全部鍵升回本 plan 的 outputs；上面每鍵旁「升為主要結果」＝只升那一鍵</span></dd>';}
    if(n.type==='report'){skip=['cited_figures','uncited_main_figures','unmatched_refs','exists'];
      h+='<dt>檔案</dt><dd><span class="src">'+esc(n.meta.path||'analysis/report.md')+'</span>：'+(n.meta.exists?'存在'+(n.meta.generated_at?'（產生 '+esc(n.meta.generated_at)+'）':''):'不存在（analyze-data 交付後才會有；圖表暫不標「報告未引用」）')+'</dd>';
      var cfs=n.meta.cited_figures||[];h+='<dt>引用的圖表（'+cfs.length+'／manifest '+(n.meta.n_manifest||0)+'）</dt><dd>'+(cfs.length?cfs.map(function(f){return '<span class="goto" data-goto="'+esc(f)+'">'+esc(nodes[f]?nodes[f].label:f)+'</span>';}).join('、'):'無')+'</dd>';
      var ucf=n.meta.uncited_main_figures||[];h+='<dt>role=main 未引用（'+ucf.length+'）</dt><dd>'+(ucf.length?ucf.map(function(f){return '<span class="goto" data-goto="'+esc(f)+'">'+esc(nodes[f]?nodes[f].label:f)+'</span>';}).join('、'):'無')+'</dd>';
      var ur=n.meta.unmatched_refs||[];if(ur.length)h+='<dt>對不到 manifest 的引用（'+ur.length+'）</dt><dd>'+esc(ur.slice(0,20).join('、'))+(ur.length>20?'…':'')+'</dd>';}
    if(n.type==='result'&&!isAgg(id)){skip=['validated','validated_by','robustness_id','validation_kind','table','description','result_kind','declared_by','supports','supporting_ids','supports_invalid','report_cited'];
      var rk=n.meta.result_kind||'';h+='<dt>result_kind</dt><dd>'+esc(rk==='primary'?'primary（主要結果：在 plan outputs）':rk==='secondary'?'secondary（次要結果：只在敏感性子分析的 expected_keys）':'undeclared（未宣告）')+'</dd>';
      if(n.subtype==='supporting')h+='<dt>supports（主結果）</dt><dd><span class="goto" data-goto="'+esc(n.parent)+'">'+esc(nodes[n.parent]?nodes[n.parent].label:n.parent)+'</span>：本鍵是它的支撐結果（縮排在它之下、同一區帶；稿件歸支撐表）</dd>';
      else if(n.parent)h+='<dt>父子分析</dt><dd><span class="goto" data-goto="'+esc(n.parent)+'">'+esc(nodes[n.parent]?nodes[n.parent].label:n.parent)+'</span></dd>';
      var sids=n.meta.supporting_ids||[];if(sids.length)h+='<dt>支撐結果（'+sids.length+'）</dt><dd><ul>'+sids.map(function(sid){var sn=nodes[sid];return '<li><span class="goto" data-goto="'+esc(sid)+'">'+esc(sn?sn.label:sid)+'</span></li>';}).join('')+'</ul><span class="expand" data-nest="'+esc(id)+'">'+(nestHidden[id]?'展開支撐結果':'收合支撐結果')+'</span></dd>';
      if(n.meta.supports_invalid)h+='<dt>supports（無效）</dt><dd>'+esc(n.meta.supports_invalid)+'：不是同 plan 的頂層主要結果，未巢狀（check_plan 會擋）</dd>';
      h+='<dt>declared_by</dt><dd>'+((n.meta.declared_by||[]).length?n.meta.declared_by.map(function(d){return '<span class="goto" data-goto="'+esc(d)+'">'+esc(nodes[d]?nodes[d].label:d)+'</span>';}).join('、'):'無')+'</dd>';
      h+='<dt>validated</dt><dd>'+(n.meta.validated?'是':'<b>否（未驗證）</b>')+'</dd>';
      var vk=n.meta.validation_kind||'';h+='<dt>validation_kind</dt><dd>'+(vk==='primary'?'primary（在 validation item 的 primary_results）':vk==='robustness'?'robustness（只在 robustness result_keys）':'—')+'</dd>';
      h+='<dt>validated_by</dt><dd>'+((n.meta.validated_by||[]).length?n.meta.validated_by.map(function(v){return '<span class="goto" data-goto="v:'+esc(v)+'">'+esc(v)+'</span>';}).join('、'):'無')+'</dd>';
      if(n.meta.robustness_id)h+='<dt>robustness_id</dt><dd>'+esc(n.meta.robustness_id)+'</dd>';
      if(n.meta.description)h+='<dt>description</dt><dd>'+esc(n.meta.description)+'</dd>';}
    if(n.type==='figure'){skip=['caption','files','results_keys','data_uri','spec','role_source','keys_badge','report_cited'];
      if(n.meta.keys_badge)h+='<dt>結果鍵狀況</dt><dd>'+esc(n.meta.keys_badge)+'</dd>';
      if(nodes['o:report'])h+='<dt>報告引用</dt><dd>'+(n.meta.report_cited?'是（<span class="goto" data-goto="o:report">report.md</span> 有 ![…](…) 引用）':(nodes['o:report'].meta.exists?'否'+(String(n.meta.role||'').toLowerCase()==='main'?'（role=main：徽章「報告未引用」）':''):'—（report.md 不存在）'))+'</dd>';
      h+='<dt>圖</dt><dd>'+figBlock(n)+'</dd>';
      h+='<dt>files</dt><dd>'+esc((n.meta.files||[]).join('、')||'—')+'</dd>';
      var rk=(inE[id]||[]).filter(function(ei){return G.edges[ei].type==='depicts';}).map(function(ei){return G.edges[ei].from;});
      h+='<dt>結果鍵</dt><dd>'+(rk.length?rk.map(function(r){return '<span class="goto" data-goto="'+esc(r)+'">'+esc(nodes[r].label)+'</span>';}).join('、'):'無（'+esc((n.meta.results_keys||[]).join('、')||'manifest 未列')+'）')+'</dd>';
      if(n.meta.spec)h+='<dt>spec</dt><dd>'+esc(typeof n.meta.spec==='object'?JSON.stringify(n.meta.spec):n.meta.spec)+'</dd>';}
    if(n.type==='question')skip=skip.concat(['aliases']);
    if(n.type==='question'&&isMainSQ(id)){h+='<dt>動作</dt><dd><span class="act-inline"><button type="button" class="act-reassign" data-q="'+esc(id.slice(2))+'"'+(serverOk?'':' disabled title="用 progress_server.py 開啟才能送出"')+'>降為附錄問題（送收件匣）</button><span class="src">或把節點拖到 Supplementary 帶；拖到同帶另一個問題上＝排在它之後</span></span></dd>';}
    if(n.type==='question'&&questionKind(id)==='AQ'&&n.band==='supp'){h+='<dt>動作</dt><dd><span class="act-inline"><button type="button" class="act-promote" data-q="'+esc(id.slice(2))+'"'+(serverOk?'':' disabled title="用 progress_server.py 開啟才能送出"')+'>升回主問題（送收件匣）</button><span class="src">或把節點拖到 Main 帶；拖到同帶另一個問題上＝排在它之後</span></span></dd>';}
    if(isActivePlan(id)){h+='<dt>動作</dt><dd><span class="src">把這個方法節點拖到別的問題節點上＝搬到該問題之下（目標須沒有 active plan）</span></dd>';}
    if(isSensItem(id)){h+='<dt>動作</dt><dd><span class="src">把這個子分析拖到別的方法節點上＝搬到該 plan（兩邊各出一版）</span></dd>';}
    if(isDragResult(id)&&!isAgg(id)){h+='<dt>動作</dt><dd><span class="src">把這個結果拖到別的方法節點上＝成為該 plan 的主要結果（outputs）；拖到任一敏感性子分析上＝成為它的次要結果（expected_keys）；主要結果拖到 Supplementary 帶（或次要結果拖到 Main 帶）＝放開後從下拉選落點，預設是在本 plan 新增一個敏感性子分析收它；兩邊各出一版、數字不動</span></dd>';}
    if(n.type==='figure'){var curRole=String(n.meta.role||'').toLowerCase();h+='<dt>動作</dt><dd><span class="act-inline"><select class="act-role-sel" data-fig="'+esc(id.slice(2))+'">'+ROLE_OPTS.map(function(o){return '<option value="'+o[0]+'"'+(curRole===o[0]?' selected':'')+'>'+esc(o[1])+'</option>';}).join('')+'</select><button type="button" class="act-setrole" data-fig="'+esc(id.slice(2))+'"'+(serverOk?'':' disabled title="用 progress_server.py 開啟才能送出"')+'>改 role（送收件匣）</button><span class="src">或把節點拖到別的帶</span></span></dd>';}
    h+='<dt>meta</dt><dd>'+metaRows(n.meta,skip)+'</dd>';
    if(n.type==='result'){
      if(n.meta.table&&!isAgg(id))h+='<dt>表</dt><dd>'+tableBlock(n.meta.table)+'</dd>';
      else if(!isAgg(id)&&('display' in n.meta||'value' in n.meta))h+='<dt>值</dt><dd>'+esc(('display' in n.meta&&n.meta.display!==null)?n.meta.display:n.meta.value)+(n.meta.unit?' '+esc(n.meta.unit):'')+'</dd>';
      var figs=(outE[id]||[]).filter(function(ei){return G.edges[ei].type==='depicts';}).map(function(ei){return nodes[G.edges[ei].to];});
      h+='<dt>圖表（'+figs.length+'）</dt><dd>'+(figs.length?figs.map(figBlock).join(''):'無')+'</dd>';}
    h+='<dt>進邊（上游 '+Object.keys(up.nodes).length+' 個節點）</dt><dd>'+edgeList(inE[id],-1)+'</dd>';
    h+='<dt>出邊（下游 '+Object.keys(down.nodes).length+' 個節點）</dt><dd>'+edgeList(outE[id],1)+'</dd>';
    if(n.type==='question'&&(n.meta.aliases||[]).length)h+='<dt>舊 id</dt><dd>'+esc(n.meta.aliases.join('、'))+'（index 舊版、決策 links、validation item 仍寫舊 id，已併入本問題）</dd>';
    if(n.type==='question'){var sh=G.shared.filter(function(s){return s.a===id||s.b===id;});h+='<dt>共用關係</dt><dd>';
      if(!sh.length)h+='無';else{h+='<ul>';sh.forEach(function(s){var other=s.a===id?s.b:s.a;var parts=[];
        var mods=s.via.filter(function(v){return v.indexOf('model:')===0;}).map(function(v){return esc(v.slice(6));});if(mods.length)parts.push('方法 '+mods.join('、'));
        [['result','r:'],['validation','v:'],['figure','f:']].forEach(function(t){var ids=s.via.filter(function(v){return v.indexOf(t[1])===0&&nodes[v];});if(ids.length)parts.push(typeLabel[t[0]]+' '+ids.map(function(v){return '<span class="goto" data-goto="'+esc(v)+'">'+esc(nodes[v].label)+'</span>';}).join('、'));});
        h+='<li>與 <span class="goto" data-goto="'+esc(other)+'">'+esc(nodes[other].label)+'</span> 共用：'+parts.join('；')+'</li>';});h+='</ul>';}
      h+='</dd>';}
    h+='</dl>';body.innerHTML=h;panel.hidden=false;bindImages();
  }
  body.addEventListener('click',function(e){var t=e.target.closest('.goto');if(t&&t.getAttribute('data-goto')){var id=t.getAttribute('data-goto');if(nodes[id]&&!nodeVisible(id)&&(nodes[id].collapsed||nodes[id].parent)){var top=id;while(nodes[top]&&nodes[top].parent)top=nodes[top].parent;if(currentOf[top]){expanded[currentOf[top]]=true;relayout();}}select(id,true);return;}
    var x=e.target.closest('.expand');if(x){if(x.getAttribute('data-nest')){var nid=x.getAttribute('data-nest');nestHidden[nid]=!nestHidden[nid];relayout();if(selected)select(selected,false);return;}expandChain(x.getAttribute('data-expand'));}});
  document.getElementById('gdetail-close').addEventListener('click',clearAll);
  function bindNode(id,el){
    el.addEventListener('mousedown',function(e){if(e.button!==0||!draggable(id)||!nodeVisible(id))return;e.stopPropagation();var n=nodes[id];nodeDrag={id:id,el:el,x:e.clientX,y:e.clientY,nx:n.x,ny:n.y,moved:false};moved=false;});
    el.addEventListener('click',function(e){if(moved)return;e.stopPropagation();if(e.target.classList&&e.target.classList.contains('badge')&&nodes[id].type==='method'){expandChain(id);return;}if(e.shiftKey&&selected&&selected!==id)showPath(selected,id);else select(id,false);});}
  Object.keys(nodeEls).forEach(function(id){bindNode(id,nodeEls[id]);});
  // ---- 搜尋 ----
  var hits=[];
  function runSearch(){var q=search.value.trim().toLowerCase();hits=[];clearClasses();if(!q){document.getElementById('graph-search-count').textContent='';if(selected)select(selected,false);return;}
    G.nodes.forEach(function(n){if(!nodeVisible(n.id))return;if(n.label.toLowerCase().indexOf(q)>=0||n.title.toLowerCase().indexOf(q)>=0)hits.push(n.id);});
    var set={};hits.forEach(function(i){set[i]=true;});Object.keys(nodeEls).forEach(function(k){nodeEls[k].classList.add(set[k]?'hit':'dim');});edgeEls.forEach(function(el){if(el)el.classList.add('dim');});syncTrunks();
    document.getElementById('graph-search-count').textContent=hits.length+' 個命中';}
  search.addEventListener('input',runSearch);
  search.addEventListener('keydown',function(e){if(e.key==='Enter'&&hits.length){select(hits[0],true);search.blur();}if(e.key==='Escape'){search.value='';runSearch();search.blur();}});
  // ---- 導覽 ----
  var chapters=['q:main'].concat(ir.lanes.filter(function(l){return l.kind!=='project';}).map(function(l){return 'q:'+l.id;}).filter(function(id){return !!nodes[id];}));
  function chapterSummary(id){
    var n=nodes[id];if(id==='q:main'){var k=(outE[id]||[]).filter(function(ei){return G.edges[ei].type==='decomposes';}).length;return '主問題 ｜ 拆解為 '+k+' 個問題';}
    var plans=(outE[id]||[]).filter(function(ei){return G.edges[ei].type==='plans';}).map(function(ei){return nodes[G.edges[ei].to];});
    var curP=null;plans.forEach(function(p){if(!p.collapsed&&(!curP||(p.meta.version||0)>(curP.meta.version||0)))curP=p;});
    if(!curP)return n.label+' ｜ 方法 無（'+plans.length+' 個舊版，無現行版）';
    var down=walk(id,1).nodes;
    var vids=[],vst={};(outE[curP.id]||[]).forEach(function(ei){var e=G.edges[ei];if(e.type==='validated_by'){vids.push(nodes[e.to].label);vst[nodes[e.to].meta.status||'unknown']=true;}});
    var kinds={primary:0,secondary:0,undeclared:0},unval=0;
    Object.keys(down).forEach(function(kk){var m=nodes[kk];if(m.type==='result'){kinds[m.meta.result_kind||'undeclared']=(kinds[m.meta.result_kind||'undeclared']||0)+1;if(m.meta.validated===false)unval++;}});
    var models=(curP.meta.models||[]).join('、')||'無 model';var k=(curP.meta.superseded_versions||[]).length;var sc=(curP.meta.sensitivity_ids||[]).length;
    var figs={},fu=0;Object.keys(down).forEach(function(kk){var m=nodes[kk];if(m.type==='figure'){figs[kk]=true;if(m.state!=='done')fu++;}});
    return n.label+' ｜ 方法 '+curP.id.slice(2)+'（'+models+'；'+k+' 舊版；敏感性 '+sc+' 項）→ 驗證 '+(vids.length?Object.keys(vst).join('／'):'無')+'（'+(vids.join('、')||'—')+'）→ 主要結果 '+kinds.primary+' 鍵、次要 '+kinds.secondary+' 鍵、未宣告 '+kinds.undeclared+' 鍵（未驗證 '+unval+'）→ 圖表 '+Object.keys(figs).length+' 張（未審 '+fu+'）';
  }
  function tourLine(){return '<div class="tour">第 '+(tour+1)+'／'+chapters.length+' 章：'+esc(chapterSummary(chapters[tour]))+'<br><span class="src">← → 換章，Esc 離開</span></div>';}
  function tourGo(i){if(!chapters.length)return;tour=((i%chapters.length)+chapters.length)%chapters.length;select(chapters[tour],true);}
  document.getElementById('tour-start').addEventListener('click',function(){tourGo(0);});
  document.getElementById('tour-prev').addEventListener('click',function(){tourGo((tour===null?0:tour)-1);});
  document.getElementById('tour-next').addEventListener('click',function(){tourGo((tour===null?-1:tour)+1);});
  // ---- 鍵盤 ----
  document.addEventListener('keydown',function(e){
    if(cur!=='relations')return;var tag=(e.target&&e.target.tagName||'').toLowerCase();var typing=tag==='input'||tag==='textarea';
    if(e.key==='/'&&!typing){e.preventDefault();search.focus();search.select();return;}
    if(e.key==='Escape'){if(!lb.hidden){closeLightbox();return;}if(typing){search.value='';runSearch();search.blur();}clearAll();return;}
    if(typing)return;
    if(e.key==='p'||e.key==='P'){e.preventDefault();tourGo(tour===null?0:tour);return;}
    if(tour!==null&&e.key==='ArrowRight'){e.preventDefault();tourGo(tour+1);}
    if(tour!==null&&e.key==='ArrowLeft'){e.preventDefault();tourGo(tour-1);}
  });
  // ---- 收件匣表單（只在經 progress_server.py 以 http 開啟時啟用） ----
  var serverOk=false,formEl=document.getElementById('inbox-form'),newBtn=document.getElementById('inbox-new'),hintEl=document.getElementById('inbox-hint');
  var fKind=document.getElementById('inbox-kind'),fTarget=document.getElementById('inbox-target'),fTitle=document.getElementById('inbox-title'),fBody=document.getElementById('inbox-body'),fAuthor=document.getElementById('inbox-author'),fErr=document.getElementById('inbox-err');
  var toastTimer=null;
  function toast(msg){var t=document.getElementById('toast');t.textContent=msg;t.hidden=false;if(toastTimer)clearTimeout(toastTimer);toastTimer=setTimeout(function(){t.hidden=true;},2500);}
  // 0.17.1 附「復原」連結的 toast（暫存後用）：按了就關 toast 並執行 fn；六秒後自動關
  function toastUndo(msg,fn){var t=document.getElementById('toast');t.textContent=msg+' ';var a=document.createElement('a');a.href='#';a.className='toast-undo';a.textContent='復原';
    a.addEventListener('click',function(e){e.preventDefault();t.hidden=true;fn();});t.appendChild(a);t.hidden=false;if(toastTimer)clearTimeout(toastTimer);toastTimer=setTimeout(function(){t.hidden=true;},6000);}
  var actionsOk=false,actionsWhy='server 未開 --allow-apply',nextAq='',nextSq='';   // actionsWhy：「全部套用」停用時顯示在鈕旁的原因（0.17.3）
  function enableInbox(){serverOk=true;newBtn.disabled=false;newBtn.title='';hintEl.textContent='已連上 progress_server.py，送出會寫入 PROGRESS.inbox.yaml（不直接改 SSOT）';Array.prototype.forEach.call(document.querySelectorAll('.inbox-comment,.act-reassign,.act-promote,.act-setrole'),function(b){b.disabled=false;b.title='';});
    Array.prototype.forEach.call(document.querySelectorAll('.act-dismiss-row'),function(b){b.disabled=false;b.title='標 dismissed（代跑 check_inbox.py --dismiss），不改 SSOT';});}   // 0.18.2 面板每列的撤回鈕只要連上 server（不需 --allow-apply）
  function enableActions(){actionsOk=true;var sp=document.getElementById('staged-preview');if(sp){sp.disabled=false;sp.title='';}var hint=document.getElementById('actions-hint');if(hint)hint.textContent='已連上 progress_server.py --allow-apply：「預覽變更」跑腳本 --dry-run（不寫檔），「套用」才跑 --apply（腳本自己備份、失敗還原）。';
    Array.prototype.forEach.call(document.querySelectorAll('.act-preview'),function(b){b.disabled=false;b.title='';});}
  if(location.protocol==='http:'||location.protocol==='https:'){try{fetch('/api/ping',{cache:'no-store'}).then(function(r){return r.json();}).then(function(d){if(d&&d.ok){enableInbox();nextAq=d.next_aq||'';nextSq=d.next_sq||'';if(d.actions_enabled)enableActions();else{var hint=document.getElementById('actions-hint');if(hint)hint.textContent='已連上 progress_server.py，但未開 --allow-apply：這裡只能看，預覽與套用請重啟 server 加 --allow-apply，或由 status skill 跑腳本。';}}else{actionsWhy='未連上 progress_server.py';}renderStaged();}).catch(function(){actionsWhy='未連上 progress_server.py';renderStaged();});}catch(e){}}
  else{actionsWhy='file:// 開啟無法呼叫伺服器';var hint0=document.getElementById('actions-hint');if(hint0)hint0.textContent='file:// 開啟的頁面無法呼叫伺服器：預覽與套用請用 progress_server.py --allow-apply 開啟，或由 status skill 跑腳本。';}
  // ---- 結構化動作表單（九種單動作 kind；0.16.5 加 nest_result、0.18.0 加 demote_plan）：送收件匣後同一個對話框立刻預覽（0.16.3）----
  var actForm=document.getElementById('act-form'),actKind='',actPayload=null,actErr=document.getElementById('act-err');
  var ACT_GROUPS=['reassign','promote','role','move-plan','move-sens','reorder','move-result','nest-result','demote-plan','set-tier'];
  function showActGroup(name){ACT_GROUPS.forEach(function(g){var el=document.getElementById('act-'+g+'-fields');if(el)el.hidden=(g!==name);});}
  function $v(id,val){document.getElementById(id).value=val;}
  function planLabel(pid){var n=nodes['p:'+pid];return n?n.label:pid;}
  function qLabel(q){var n=nodes['q:'+q];return n?(n.label+(n.title?'：'+n.title.slice(0,40):'')):q;}
  function nextAqFromIr(){var n=0;G.nodes.forEach(function(x){var m=/^q:AQ(\d+)$/.exec(x.id);if(m)n=Math.max(n,+m[1]);});(G.question_aliases?Object.keys(G.question_aliases):[]).forEach(function(k){var m=/^AQ(\d+)$/.exec(k);if(m)n=Math.max(n,+m[1]);});return 'AQ'+(n+1);}
  function planModelsFor(sq){var out=[];G.nodes.forEach(function(x){if(x.type==='method'&&!x.parent&&!x.collapsed&&x.meta&&x.meta.sq===sq){var pm=String(x.meta.primary_model||'').split('：')[0].trim();if(pm)out.push(pm);(x.meta.models||[]).forEach(function(m){if(out.indexOf(m)<0)out.push(m);});}});return out;}
  function openReassignForm(sq){if(!serverOk)return;actKind='reassign';actStage('form');actErr.textContent='';document.getElementById('act-form-title').textContent='降為附錄問題（'+sq+'）';
    showActGroup('reassign');
    document.getElementById('act-from').value=sq;document.getElementById('act-to').value=nextAq||nextAqFromIr();
    var sel=document.getElementById('act-pm');sel.innerHTML='<option value="">（不改；只改歸屬）</option>';planModelsFor(sq).forEach(function(m,i){var o=document.createElement('option');o.value=m;o.textContent=m+(i===0?'（現行 primary）':'');sel.appendChild(o);});
    document.getElementById('act-reason').value='';actForm.hidden=false;document.getElementById('act-to').focus();}
  function openRoleForm(fig,role){if(!serverOk)return;actKind='set_role';actStage('form');actErr.textContent='';document.getElementById('act-form-title').textContent='改圖表 role（'+fig+'）';
    showActGroup('role');
    document.getElementById('act-fig').value=fig;var cur=String((nodes['f:'+fig]||{meta:{}}).meta.role||'').toLowerCase();document.getElementById('act-role').value=role||cur||'main';
    document.getElementById('act-reason').value='';actForm.hidden=false;document.getElementById('act-role').focus();}
  function openPromoteForm(aq){if(!serverOk)return;actKind='promote';actStage('form');actErr.textContent='';document.getElementById('act-form-title').textContent='升回主問題（'+aq+'）';
    showActGroup('promote');$v('act-p-from',aq);$v('act-p-to','');document.getElementById('act-p-to').placeholder='留空＝回原號（若空著）或 '+(nextSq||'下一個 SQ 號');
    $v('act-reason','');actForm.hidden=false;document.getElementById('act-p-to').focus();}
  // 拖放後開表單：父節點欄位已帶入、唯讀可見；使用者只填理由（reassign／promote 另可改 to，reassign 另可選 primary_model）
  function nextRid(pid){var n=0;G.nodes.forEach(function(x){var m=/^p:([^#]+)#R(\d+)$/.exec(x.id);if(m&&m[1]===pid&&!x.collapsed)n=Math.max(n,+m[2]);});return 'R'+(n+1);}
  function mrFill(payload){var rn=nodes['r:'+payload.key]||{label:payload.key,meta:{}};var own=String((rn.meta||{}).plan_id||'');
    document.getElementById('act-form-title').textContent='搬結果：'+payload.key+' → '+payload.to_plan+(payload.to_item?' '+payload.to_item:(payload.new_item?' 新增子分析':''));
    $v('act-mr-key',rn.label+(own?'（現屬 '+own+'，'+({primary:'主要',secondary:'次要',undeclared:'未宣告'}[rn.meta.result_kind]||'')+'結果）':''));$v('act-mr-to',planLabel(payload.to_plan));
    $v('act-mr-item',payload.new_item?('新增 '+nextRid(payload.to_plan)+'：'+payload.new_item+'（B 型：成為次要結果；只是歸屬容器，rows 沿用原 run）'):payload.to_item?((nodes['p:'+payload.to_plan+'#'+payload.to_item]||{label:payload.to_item}).label+'（B 型：成為次要結果）'):'（無；A 型：成為 outputs 主要結果）');}
  function openActionForm(kind,payload,options){if(!serverOk)return;actPayload=payload||{};
    if(kind==='reassign'){openReassignForm(payload.from);return;}
    if(kind==='promote'){openPromoteForm(payload.from);return;}
    if(kind==='set_role'){openRoleForm(payload.figure,payload.role);return;}
    actKind=kind;actStage('form');actErr.textContent='';$v('act-reason','');actOptions=options||null;
    if(kind==='move_plan'){document.getElementById('act-form-title').textContent='搬方法：'+payload.plan+' → '+payload.to_question;showActGroup('move-plan');$v('act-mp-plan',planLabel(payload.plan));$v('act-mp-to',qLabel(payload.to_question));}
    else if(kind==='move_sensitivity'){document.getElementById('act-form-title').textContent='搬敏感性子分析：'+payload.plan+' '+payload.item+' → '+payload.to_plan;showActGroup('move-sens');$v('act-ms-plan',planLabel(payload.plan));$v('act-ms-item',(nodes['p:'+payload.plan+'#'+payload.item]||{label:payload.item}).label);$v('act-ms-to',planLabel(payload.to_plan));}
    else if(kind==='demote_plan'){document.getElementById('act-form-title').textContent='降為敏感性子分析：'+payload.plan+' → '+payload.to_plan;showActGroup('demote-plan');$v('act-dp-plan',planLabel(payload.plan));$v('act-dp-to',planLabel(payload.to_plan));}
    else if(kind==='reorder'){document.getElementById('act-form-title').textContent='調順序：goals.'+payload.list;showActGroup('reorder');$v('act-ro-list',payload.list);$v('act-ro-order',payload.order.join(' → '));}
    else if(kind==='set_tier'){var stn=nodes[payload.node]||{label:payload.node};document.getElementById('act-form-title').textContent=(payload.tier==='extended'?'放入 Extended Data：':'移出 Extended Data：')+payload.node;showActGroup('set-tier');
      $v('act-st-node',stn.label+'（'+payload.node+'）');$v('act-st-tier',payload.tier==='extended'?'extended（放入 Extended Data；跟著走：'+(edFollowers(payload.node).filter(function(k){return nodes[k].band!=='ext';}).join('、')||'無')+'）':'（空：從 analysis/extended-data.yaml 移除，回推導區帶 '+(BAND_ZH[derivedBand(payload.node)]||'')+'）');}
    else if(kind==='nest_result'){var kn=nodes['r:'+payload.key]||{label:payload.key,meta:{}},kown=String((kn.meta||{}).plan_id||''),cur=String((kn.meta||{}).supports||'');
      document.getElementById('act-form-title').textContent=payload.under?('掛到主結果下：'+payload.key+' → '+payload.under):('拉回頂層：'+payload.key);showActGroup('nest-result');
      $v('act-nr-key',kn.label+(kown?'（'+kown+' 的主要結果'+(cur?'，現為 '+cur+' 的支撐結果':'，現為頂層')+'）':''));
      $v('act-nr-under',payload.under?((nodes['r:'+payload.under]||{label:payload.under}).label+'（同 plan 的頂層主要結果；'+payload.key+' 縮排在它之下、同一區帶）'):'（空：拉回頂層結果）');}
    else if(kind==='move_result'){showActGroup('move-result');var sel=document.getElementById('act-mr-dest'),dw=document.getElementById('act-mr-dest-wrap');sel.innerHTML='';sel.onchange=null;
      if(options&&options.length){// 0.16.4 區帶落點：下拉選確切落點（新增子分析／既有 R／別的 plan 的 outputs），選什麼就送什麼 payload
        options.forEach(function(o,i){var op=document.createElement('option');op.value=String(i);op.textContent=o.label;sel.appendChild(op);});sel.value='0';actPayload=options[0].payload;
        sel.onchange=function(){actPayload=options[+sel.value].payload;mrFill(actPayload);};dw.hidden=false;}
      else dw.hidden=true;
      mrFill(actPayload);}
    else return;
    actForm.hidden=false;document.getElementById('act-reason').focus();}
  // 對話框兩階段：form（填理由、按「送出並預覽」）→ preview（已進收件匣；顯示 dry-run 摘要；套用／先留在收件匣／撤回）
  var actStageNow='form',actItemId='';
  function actStage(stage,id){actStageNow=stage;actItemId=id||'';document.getElementById('act-preview-box').hidden=(stage!=='preview');document.getElementById('act-submit-row').hidden=(stage==='preview');
    if(stage==='form'){actEditIndex=-1;actOptions=null;document.getElementById('act-stage').textContent='加入暫存';document.getElementById('act-submit').hidden=false;}   // 0.17.1 離開「編輯暫存」模式
    Array.prototype.forEach.call(actForm.querySelectorAll('input,select,textarea'),function(el){el.disabled=(stage==='preview');});
    if(stage==='preview'){document.getElementById('act-item-id').textContent=id;document.getElementById('act-summary').textContent='';var ap=document.getElementById('act-apply');ap.disabled=true;ap.title='先預覽';document.getElementById('act-keep').disabled=false;document.getElementById('act-dismiss').disabled=false;}}
  function closeActForm(){var keep=(actStageNow==='preview');actForm.hidden=true;actStage('form');if(keep)location.reload();}
  document.getElementById('act-cancel').addEventListener('click',closeActForm);
  // 表單 → {kind, payload, reason}（單獨送出與加入暫存共用；錯誤寫進 act-err 並回 null）
  function actFormPayload(){actErr.textContent='';var reason=document.getElementById('act-reason').value.trim();
    if(actKind==='reassign'){var to=document.getElementById('act-to').value.trim();if(to&&!/^AQ\d+$/.test(to)){actErr.textContent='to 須為 AQ<數字> 或留空';return null;}
      return {kind:'reassign',payload:{from:document.getElementById('act-from').value,to:to,primary_model:document.getElementById('act-pm').value},reason:reason};}
    if(actKind==='promote'){var pto=document.getElementById('act-p-to').value.trim();if(pto&&!/^SQ\d+$/.test(pto)){actErr.textContent='to 須為 SQ<數字> 或留空';return null;}
      return {kind:'promote',payload:{from:document.getElementById('act-p-from').value,to:pto},reason:reason};}
    if(actKind==='set_role'){var fig=document.getElementById('act-fig').value,role=document.getElementById('act-role').value;var cur=String((nodes['f:'+fig]||{meta:{}}).meta.role||'').toLowerCase();if(role===cur){actErr.textContent='role 已是 '+role+'，沒有要改的東西';return null;}
      return {kind:'set_role',payload:{figure:fig,role:role},reason:reason};}
    if(actKind==='move_plan'||actKind==='move_sensitivity'||actKind==='reorder'||actKind==='move_result'||actKind==='nest_result'||actKind==='demote_plan'||actKind==='set_tier'){if(!actPayload){actErr.textContent='沒有拖放帶入的內容';return null;}return {kind:actKind,payload:actPayload,reason:reason};}
    actErr.textContent='未知的動作';return null;}
  document.getElementById('act-form-inner').addEventListener('submit',function(e){e.preventDefault();var payload=actFormPayload();if(!payload)return;
    var sb=document.getElementById('act-submit');sb.disabled=true;
    actPost('/api/inbox',payload)
      .then(function(x){sb.disabled=false;if(x.d&&x.d.ok){toast('已送入收件匣 '+x.d.id+'，正在預覽變更');actStage('preview',x.d.id);actPreview(x.d.id,actDialogUi(x.d.id));}else{actErr.textContent=(x.d&&x.d.error)||('HTTP '+x.status);}})
      .catch(function(err){sb.disabled=false;actErr.textContent='送出失敗：'+err;});});
  // 對話框的 ui 物件：摘要區、套用鈕、執行期間停用的兩個鈕；不再彈 confirm（摘要本身就是確認）；409 自動重跑預覽
  function actDialogUi(id){var ui={pre:document.getElementById('act-summary'),apply:document.getElementById('act-apply'),lock:[document.getElementById('act-dismiss'),document.getElementById('act-keep')],confirm:false};ui.onStale=function(){actPreview(id,ui);};return ui;}
  document.getElementById('act-apply').addEventListener('click',function(){if(actStageNow!=='preview'||!actItemId)return;actApply(actItemId,actDialogUi(actItemId));});
  document.getElementById('act-keep').addEventListener('click',function(){closeActForm();});
  document.getElementById('act-dismiss').addEventListener('click',function(){if(actStageNow!=='preview'||!actItemId)return;var id=actItemId,db=document.getElementById('act-dismiss');db.disabled=true;actErr.textContent='';
    actPost(DISMISS_PATH,{id:id,note:'使用者在放開預覽後撤回'}).then(function(x){var d=x.d||{};if(d.ok){toast('已撤回 '+id);closeActForm();}else{db.disabled=false;actErr.textContent='撤回失敗：'+(d.error||('HTTP '+x.status))+(d.summary?'\\n'+d.summary:'');}})
      .catch(function(err){db.disabled=false;actErr.textContent='撤回失敗：'+err;});});
  body.addEventListener('click',function(e){var ap=e.target.closest('.agg-promote');if(ap&&!ap.disabled){if(!serverOk){toast('用 progress_server.py 開啟才能暫存');return;}stageAdd('move_result',{key:ap.getAttribute('data-key'),to_plan:ap.getAttribute('data-plan'),to_item:''},'');return;}
    var pg=e.target.closest('.agg-page');if(pg&&!pg.disabled){var box=document.getElementById('agg-keys');if(box){aggUi.page+=(+pg.getAttribute('data-d')||0);box.innerHTML=aggKeyList(box.getAttribute('data-agg'));}return;}
    var b=e.target.closest('.act-reassign');if(b&&!b.disabled){openReassignForm(b.getAttribute('data-q'));return;}
    var pb=e.target.closest('.act-promote');if(pb&&!pb.disabled){openPromoteForm(pb.getAttribute('data-q'));return;}
    var c=e.target.closest('.act-setrole');if(c&&!c.disabled){var fig=c.getAttribute('data-fig');var sel=body.querySelector('.act-role-sel[data-fig="'+fig.replace(/"/g,'\\"')+'"]');openRoleForm(fig,sel?sel.value:'');}});
  document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!actForm.hidden){closeActForm();}});
  body.addEventListener('input',function(e){var si=e.target.closest('.agg-search');if(!si)return;var box=document.getElementById('agg-keys');if(!box)return;aggUi.q=si.value;aggUi.page=0;box.innerHTML=aggKeyList(box.getAttribute('data-agg'));var s2=box.querySelector('.agg-search');if(s2){s2.focus();try{s2.setSelectionRange(s2.value.length,s2.value.length);}catch(x){}}});
  // ---- 共用：預覽（dry-run）→ 套用（apply，帶 token）。面板每一列與放開後的對話框都走 actPreview／actApply，只有一份 ----
  // ui = {pre: 摘要 <pre>, apply: 套用鈕, lock?: 執行期間停用的鈕, confirm?: 套用前是否再彈 confirm（面板 true、對話框 false）, onStale?: 409 時的處理（對話框自動重跑預覽；面板沒給就讓套用鈕停用）}
  var actTokens={},DISMISS_PATH='/api/inbox/dismiss';
  function actRow(id){return document.querySelector('#actions-panel tr[data-act-id="'+id.replace(/"/g,'\\"')+'"]');}
  function actPost(path,payload,opts){return fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),keepalive:!!(opts&&opts.keepalive)}).then(function(r){return r.json().then(function(d){return {status:r.status,d:d};});});}
  function actBusy(ui,on){(ui.lock||[]).forEach(function(b){if(b)b.disabled=on;});}
  function actPreview(id,ui){actBusy(ui,true);ui.apply.disabled=true;ui.apply.title='先預覽';ui.pre.textContent='預覽中（跑腳本 --dry-run，約 5–10 秒）…';
    return actPost('/api/actions/dry-run',{id:id}).then(function(x){actBusy(ui,false);var d=x.d||{};ui.pre.textContent=(d.summary||d.error||('HTTP '+x.status));
      if(d.ok&&d.token){actTokens[id]=d.token;ui.apply.disabled=false;ui.apply.title='';}else{delete actTokens[id];ui.apply.title=(x.status===403?'server 未開 --allow-apply':'預覽未通過');}return x;})
      .catch(function(err){actBusy(ui,false);delete actTokens[id];ui.pre.textContent='預覽失敗：'+err;return null;});}
  function actApply(id,ui){if(!actTokens[id]){ui.pre.textContent='請先預覽';return Promise.resolve(null);}
    if(ui.confirm!==false&&!window.confirm('確定套用 '+id+'？腳本會改 SSOT（改前備份、失敗還原）並記一筆決策。'))return Promise.resolve(null);
    actBusy(ui,true);ui.apply.disabled=true;ui.pre.textContent='套用中（跑腳本 --apply）…';
    var body={id:id,token:actTokens[id]};if(ui.extra){var ex=ui.extra()||{};Object.keys(ex).forEach(function(k){body[k]=ex[k];});}   // 0.17.3 暫存面板多帶 reason（整批理由，套用時才帶、不進 dry-run）
    return actPost('/api/actions/apply',body).then(function(x){var d=x.d||{};
      if(x.status===409){delete actTokens[id];actBusy(ui,false);ui.pre.textContent='SSOT 已變，重新預覽：'+(d.error||'');if(ui.onStale)ui.onStale();return x;}
      ui.pre.textContent=(d.summary||d.error||('HTTP '+x.status));
      if(d.ok){if(ui.onOk)ui.onOk(d);toast(ui.okText?ui.okText(d):('已套用，決策 '+(d.decision||'')+'；重新載入'));setTimeout(function(){location.reload();},1500);}else{if(ui.onFail)ui.onFail(d);actBusy(ui,false);ui.apply.disabled=false;}return x;})
      .catch(function(err){actBusy(ui,false);ui.apply.disabled=false;ui.pre.textContent='套用失敗：'+err;return null;});}
  // ---- 待套用動作面板（第二入口，行為不變）----
  function actRowUi(id){var row=actRow(id);return {pre:row.querySelector('.act-summary'),apply:row.querySelector('.act-apply'),lock:[row.querySelector('.act-preview'),row.querySelector('.act-dismiss-row')],confirm:true};}
  // 0.18.2 面板每列「撤回」：POST /api/inbox/dismiss（只改收件匣狀態、不動 SSOT、不需 --allow-apply）→ toast 後重新載入；失敗把原因寫在該列摘要區。撤回期間該列三個鈕一起停用
  function actDismissRow(id){var row=actRow(id);if(!row)return Promise.resolve(null);var btns=[row.querySelector('.act-preview'),row.querySelector('.act-apply'),row.querySelector('.act-dismiss-row')],pre=row.querySelector('.act-summary');
    var was=btns.map(function(b){return b?b.disabled:true;});btns.forEach(function(b){if(b)b.disabled=true;});pre.textContent='撤回中（代跑 check_inbox.py --dismiss）…';
    function restore(){btns.forEach(function(b,i){if(b)b.disabled=was[i];});}
    return actPost(DISMISS_PATH,{id:id,note:'使用者在待套用動作面板撤回'}).then(function(x){var d=x.d||{};
      if(d.ok){delete actTokens[id];pre.textContent=d.summary||('已撤回 '+id);toast('已撤回 '+id);setTimeout(function(){location.reload();},1500);}
      else{restore();pre.textContent='撤回失敗：'+(d.error||('HTTP '+x.status))+(d.summary?'\\n'+d.summary:'');}return x;})
      .catch(function(err){restore();pre.textContent='撤回失敗：'+err;return null;});}
  var actPanel=document.getElementById('actions-panel');
  if(actPanel)actPanel.addEventListener('click',function(e){
    var g=e.target.closest('.goto');if(g&&nodes[g.getAttribute('data-goto')]){showTab('relations',true);select(g.getAttribute('data-goto'),true);return;}
    var pv=e.target.closest('.act-preview');if(pv&&!pv.disabled){actPreview(pv.getAttribute('data-id'),actRowUi(pv.getAttribute('data-id')));return;}
    var apb=e.target.closest('.act-apply');if(apb&&!apb.disabled){actApply(apb.getAttribute('data-id'),actRowUi(apb.getAttribute('data-id')));return;}
    var dr=e.target.closest('.act-dismiss-row');if(dr&&!dr.disabled){actDismissRow(dr.getAttribute('data-id'));return;}});
  function fillTargets(sel){fTarget.innerHTML='<option value="">（無）</option>';G.nodes.forEach(function(n){if(n.type!=='question'||n.id==='q:main')return;var o=document.createElement('option');o.value=n.id;o.textContent=n.label+(n.title?'：'+n.title.slice(0,40):'');fTarget.appendChild(o);});
    if(sel&&!Array.prototype.some.call(fTarget.options,function(o){return o.value===sel;})){var o=document.createElement('option');o.value=sel;o.textContent=(nodes[sel]?nodes[sel].label:sel);fTarget.appendChild(o);}fTarget.value=sel||'';}
  function openForm(kind,target){if(!serverOk)return;fErr.textContent='';fKind.value=kind;fillTargets(target||'');fKind.disabled=(kind==='comment');fTarget.disabled=(kind==='comment');
    fTitle.value=(kind==='comment'&&target&&nodes[target])?'意見：'+nodes[target].label:'';fBody.value='';fAuthor.value='';
    document.getElementById('inbox-form-title').textContent=kind==='comment'?'＋ 意見（'+(nodes[target]?nodes[target].label:target)+'）':'＋ 新問題／新分析';formEl.hidden=false;(kind==='comment'?fBody:fTitle).focus();}
  function closeForm(){formEl.hidden=true;fKind.disabled=false;fTarget.disabled=false;}
  newBtn.addEventListener('click',function(){openForm('new_question','');});
  fKind.addEventListener('change',function(){if(fKind.value==='new_question'){fTarget.value='';}});
  document.getElementById('inbox-cancel').addEventListener('click',closeForm);
  document.getElementById('inbox-form-inner').addEventListener('submit',function(e){e.preventDefault();fErr.textContent='';
    var payload={kind:fKind.value,target:fTarget.value||'',title:fTitle.value.trim(),body:fBody.value.trim(),author:fAuthor.value.trim()};
    if(!payload.title){fErr.textContent='title 不得為空';return;}if(!payload.body){fErr.textContent='body 不得為空';return;}
    if(payload.kind==='new_analysis'&&!payload.target){fErr.textContent='新分析請選一個問題節點';return;}
    fetch('/api/inbox',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(function(r){return r.json().then(function(d){return {status:r.status,d:d};});})
      .then(function(x){if(x.d&&x.d.ok){closeForm();toast('已送入收件匣 '+x.d.id);setTimeout(function(){location.reload();},900);}else{fErr.textContent=(x.d&&x.d.error)||('HTTP '+x.status);}})
      .catch(function(err){fErr.textContent='送出失敗：'+err;});});
  body.addEventListener('click',function(e){var b=e.target.closest('.inbox-comment');if(b&&!b.disabled){openForm('comment',b.getAttribute('data-target'));}});
  var banner=document.getElementById('inbox-banner');if(banner)banner.addEventListener('click',function(e){var t=e.target.closest('.goto');if(t&&nodes[t.getAttribute('data-goto')]){showTab('relations',true);var id=t.getAttribute('data-goto');if(nodes[id].collapsed&&!nodeVisible(id)){expanded[currentOf[id]]=true;relayout();}select(id,true);}});
  document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!formEl.hidden){closeForm();}});
  // ---- 0.17.0 批次暫存：放開節點 → 表單 → 「加入暫存」不呼叫 server，推進 staged[]、對本地圖模型做樂觀更新後 relayout()；「全部預覽」才建一筆 batch 進收件匣 ----
  // 樂觀更新只是視覺：節點的 parent／band／subtype 一定改對，邊只改做得到的（plans／produces／sensitivity 的起點、supports 新增）；其餘維持原樣。
  var STAGE_KEY='ap-staged:'+String(ir.project_root||location.pathname);
  var ROLE_BAND={main:'main',extended:'ext',supplementary:'supp'};
  var DOWN_TYPES=['plans','sensitivity','validated_by','primary','robustness','produces','depicts','cites','supports'];   // 與 Python DOWNSTREAM_TYPES 同
  var staged=[],stagedNodes={},stagedBatchId='',stagedAqUsed=0,actEditIndex=-1,actOptions=null;
  // 0.17.1 「放開時先開表單」開關（localStorage，預設不勾）：勾了才回到 0.17.0 的放開 → 表單；不勾＝放開即暫存
  var FORM_ON_DROP_KEY='ap-form-on-drop',formOnDrop=false;try{formOnDrop=localStorage.getItem(FORM_ON_DROP_KEY)==='1';}catch(e){}
  var optFormOnDrop=document.getElementById('opt-form-on-drop');
  if(optFormOnDrop){optFormOnDrop.checked=formOnDrop;optFormOnDrop.addEventListener('change',function(){formOnDrop=optFormOnDrop.checked;try{if(formOnDrop)localStorage.setItem(FORM_ON_DROP_KEY,'1');else localStorage.removeItem(FORM_ON_DROP_KEY);}catch(e){}});}
  var STAGE_REASON_KEY='ap-staged-reason:'+String(ir.project_root||location.pathname),stagedReasonEl=document.getElementById('staged-reason');
  function stagedReason(){return stagedReasonEl?stagedReasonEl.value.trim():'';}
  function stagedReasonSave(){try{var v=stagedReason();if(v)localStorage.setItem(STAGE_REASON_KEY,v);else localStorage.removeItem(STAGE_REASON_KEY);}catch(e){}}
  if(stagedReasonEl){try{stagedReasonEl.value=localStorage.getItem(STAGE_REASON_KEY)||'';}catch(e){}
    stagedReasonEl.addEventListener('input',function(){stagedReasonSave();});}   // 0.17.3：理由不是 dry-run 內容（token 只看 actions），改動只存 localStorage、套用時帶給 server；不作廢批次
  // 0.17.3 已建批次的紀錄（localStorage）：{id, token, actions}＝那筆收件匣 batch 的 id、dry-run token、建它時的 actions JSON；{id, stale:true}＝清單已變、那筆已作廢
  var STAGE_BATCH_KEY='ap-staged-batch:'+String(ir.project_root||location.pathname),stagedStale=false;
  function stagedBatchLoad(){try{var raw=localStorage.getItem(STAGE_BATCH_KEY);var o=raw?JSON.parse(raw):null;return (o&&typeof o==='object'&&o.id)?o:null;}catch(e){return null;}}
  function stagedBatchSave(rec){try{localStorage.setItem(STAGE_BATCH_KEY,JSON.stringify(rec));}catch(e){}}
  function stagedBatchClear(){try{localStorage.removeItem(STAGE_BATCH_KEY);}catch(e){}}
  function stagedActionsJson(){return JSON.stringify(staged.map(function(it){return {kind:it.kind,payload:it.payload,reason:it.reason||''};}));}
  function inboxItem(id){var arr=(ir.inbox&&ir.inbox.items)||[];for(var i=0;i<arr.length;i++)if(arr[i].id===id)return arr[i];return null;}
  function stagedOldBatches(){return ((ir.inbox&&ir.inbox.items)||[]).filter(function(it){return it.kind==='batch'&&(it.status||'pending')==='pending'&&it.id!==stagedBatchId;});}
  function stageLoad(){try{var raw=localStorage.getItem(STAGE_KEY);var arr=raw?JSON.parse(raw):[];return Array.isArray(arr)?arr:[];}catch(e){return [];}}
  function stageSave(){try{if(staged.length)localStorage.setItem(STAGE_KEY,JSON.stringify(staged));else localStorage.removeItem(STAGE_KEY);}catch(e){}}
  function rebuildEdgeIndex(){outE={};inE={};G.edges.forEach(function(e,i){(outE[e.from]=outE[e.from]||[]).push(i);(inE[e.to]=inE[e.to]||[]).push(i);});}
  function addEdge(from,to,type){var e={from:from,to:to,type:type,label:edgeLabel[type]||type,source:'staged',style:'solid',default_visible:true,via:[],via_order:[]};G.edges.push(e);
    var el=document.createElementNS(svg.namespaceURI,'path');el.setAttribute('class','edge e-'+type+' st-solid staged');el.setAttribute('data-idx',String(G.edges.length-1));el.setAttribute('data-from',from);el.setAttribute('data-to',to);el.setAttribute('data-type',type);
    var grp=document.getElementById('graph-edges');if(grp)grp.appendChild(el);edgeEls.push(el);rebuildEdgeIndex();return G.edges.length-1;}
  function fixX(n){n.x=PAD+n.col*COL_PITCH+({sensitivity_group:24,sensitivity:48,secondary:24,supporting:24,secondary_group:24}[n.subtype]||0);if(typeof fixBox==='function')fixBox(n);}
  // 0.18.0 樂觀更新換了 subtype 時同步框寬：.box 寬改為 nodeW，右端的狀態／徽章文字跟著平移；標籤不動
  function fixBox(n){var el=(typeof nodeEls==='undefined')?null:nodeEls[n.id];if(!el||!el.querySelector)return;var box=el.querySelector('rect.box');if(!box)return;var w0=+box.getAttribute('width'),w1=nodeW(n);if(w0===w1)return;box.setAttribute('width',String(w1));
    Array.prototype.forEach.call(el.querySelectorAll('text.st,text.badge'),function(t){t.setAttribute('x',String((+t.getAttribute('x'))+(w1-w0)));});}
  // 0.19.0 樂觀更新用：在本地圖模型新增一個節點（結果欄的主要結果或次要結果聚合節點；SVG 元素照 Python _svg_graph 的結構現做；不進 IR、不寫任何檔）。
  // 新節點視同「被動過」（band0／parent0 空）：reorderStaged 依 anchor（produces 來源或 parent）插入、restripStaged 沿 anchor 取帶
  function makeNodeEl(n){var NS=svg.namespaceURI,el=document.createElementNS(NS,'g'),w=nodeW(n),zh={done:'完成',expired:'過期',blocked:'受阻',pending:'未到',unknown:'不明'},sym={done:'●',expired:'◐',blocked:'✖',pending:'○',unknown:'◌'};
    el.setAttribute('class','gnode t-'+n.type+' s-'+(n.state||'none')+(n.subtype&&n.subtype!=='primary'&&n.subtype!=='undeclared'?' sub':'')+' staged');el.setAttribute('data-node-id',n.id);el.setAttribute('data-type',n.type);el.setAttribute('data-state',n.state);el.setAttribute('data-col',String(n.col));el.setAttribute('data-order',String(n.order));el.setAttribute('data-band',n.band);if(n.parent)el.setAttribute('data-parent',n.parent);el.setAttribute('data-strip',n.strip||'');el.setAttribute('transform','translate('+n.x+','+n.y+')');el.setAttribute('tabindex','0');
    function add(tag,attrs,text){var c=document.createElementNS(NS,tag);Object.keys(attrs).forEach(function(k){c.setAttribute(k,String(attrs[k]));});if(text!==undefined)c.textContent=text;el.appendChild(c);return c;}
    var lbl=String(n.label||'');if(lbl.length>26)lbl=lbl.slice(0,25)+'…';
    add('rect',{'class':'box',width:w,height:H,rx:6});add('rect',{'class':'tbar',x:3,y:3,width:5,height:H-6,rx:2});add('text',{'class':'sym',x:13,y:24},sym[n.state]||'');add('text',{'class':'lbl',x:30,y:23},lbl);
    add('text',{'class':'badge',x:w-8-24-6,y:23,'text-anchor':'end'},n.badge||'');add('text',{'class':'st',x:w-8,y:23,'text-anchor':'end'},zh[n.state]||'—');add('title',{},n.title||n.label);return el;}
  function spawnNode(id,patch){if(nodes[id])return nodes[id];patch=patch||{};var n={id:id,type:patch.type||'result',label:patch.label||id,title:patch.title||'',state:patch.state||'',meta:patch.meta||{},source:'staged',x:0,y:0,col:patch.col!==undefined?patch.col:4,order:1e9,collapsed:false,badge:patch.badge||'',subtype:patch.subtype||'',parent:patch.parent||'',band:patch.band||'main',strip:patch.strip||'',spawned:true};
    n.order0=n.order;n.parent0='';n.band0='';n.anchor0='';n.strip0='';G.nodes.push(n);nodes[id]=n;fixX(n);
    if(typeof document!=='undefined'&&typeof svg!=='undefined'&&svg&&svg.namespaceURI&&typeof nodeW==='function'&&typeof H!=='undefined'){var el=makeNodeEl(n);var grp=document.getElementById('graph-nodes');if(grp&&grp.appendChild)grp.appendChild(el);nodeEls[id]=el;if(typeof bindNode==='function')bindNode(id,el);}   // node 測試樁沒有 W／H／nodeW：只建模型不建元素
    return n;}
  // 0.18.0 問題節點徽章（樂觀更新用；沒有徽章元素就在狀態字左邊補一個）
  function setBadge(id,text){nodes[id].badge=text;var el=(typeof nodeEls==='undefined')?null:nodeEls[id];if(!el||!el.querySelector)return;var b=el.querySelector('text.badge');if(!b){var st=el.querySelector('text.st');b=document.createElementNS(svg.namespaceURI,'text');b.setAttribute('class','badge');b.setAttribute('y','23');b.setAttribute('text-anchor','end');
      var sw=24;try{if(st&&st.getBBox)sw=st.getBBox().width;}catch(e){}b.setAttribute('x',String((st?+st.getAttribute('x'):nodeW(nodes[id])-8)-sw-6));if(el.insertBefore)el.insertBefore(b,st||null);}b.textContent=text;}
  function setBand(id,band){var n=nodes[id];if(!n)return;n.band=band;G.nodes.forEach(function(m){if(m.parent===id)setBand(m.id,band);});}
  function subtree(id){var seen={},stack=[id];while(stack.length){var k=stack.pop();if(seen[k])continue;seen[k]=true;(outE[k]||[]).forEach(function(ei){var e=G.edges[ei];if(DOWN_TYPES.indexOf(e.type)>=0&&!seen[e.to])stack.push(e.to);});G.nodes.forEach(function(m){if(m.parent===k&&!seen[m.id])stack.push(m.id);});}return Object.keys(seen);}
  function bandFollows(m){if(m.type==='decision')return false;if(m.type==='figure')return String((m.meta||{}).role_source||'')==='derived';var bs=String((m.meta||{}).band_source||'');return bs==='derived'||!bs;}   // 0.18.0：群、子分析、次要結果都跟 plan 換帶；0.20.0：列在 extended-data.yaml（explicit）或跟著它進 ED（inherited）的節點留在 Extended Data
  // 0.20.0 樂觀更新 set_tier：跟著 explicit 節點走的節點——plan → 群、子分析、聚合次要結果、owner 為它的主要／未宣告結果與其支撐結果、plan_id 為它的驗證；子分析 → 聚合次要結果；主結果 → 支撐結果；驗證 → 無
  function edFollowers(id){var n=nodes[id],out=[],seen={};if(!n)return out;function add(k){if(!seen[k]&&k!==id){seen[k]=true;out.push(k);}}
    if(n.type==='method'&&id.indexOf('#')<0){var pid=id.slice(2);G.nodes.forEach(function(x){var xm=x.meta||{};
      if(x.type==='method'&&x.id.indexOf('p:'+pid+'#')===0)add(x.id);
      else if(x.type==='result'&&!x.parent&&x.subtype!=='secondary_group'&&resultOwnerOf(x)===pid)add(x.id);
      else if(x.type==='validation'&&String(xm.plan_id||'')===pid)add(x.id);});}
    for(var pass=0;pass<2;pass++)G.nodes.forEach(function(x){if(x.parent&&(x.parent===id||seen[x.parent]))add(x.id);});
    return out;}
  function edSetExplicit(id,marks){var n=nodes[id];n.band='ext';n.meta.band_source='explicit';marks.push(id);
    edFollowers(id).forEach(function(k){var x=nodes[k];if(x.band==='ext')return;x.band='ext';x.meta.band_source='inherited:'+id;marks.push(k);});}
  function edClear(id,marks){var n=nodes[id];n.meta.band_source='derived';n.band=derivedBand(id);marks.push(id);
    var inh=G.nodes.filter(function(x){return String((x.meta||{}).band_source||'')==='inherited:'+id;});inh.forEach(function(x){x.meta.band_source='derived';});
    for(var it=0;it<3;it++)inh.forEach(function(x){x.band=derivedBand(x.id);});   // 跟父的（聚合次要／支撐）要等父先落定，多算幾輪即收斂
    inh.forEach(function(x){marks.push(x.id);});}
  // 缺 role 的圖表：呈現的結果全在同一區帶 → 那一帶（含 ext），否則 main（與 Python 同）
  function edRederiveFigures(marks){G.nodes.forEach(function(f){if(f.type!=='figure'||String((f.meta||{}).role_source||'')!=='derived')return;var bs=[];(inE[f.id]||[]).forEach(function(ei){var e=G.edges[ei];if(e.type==='depicts'&&nodes[e.from])bs.push(nodes[e.from].band);});
    var nb=(bs.length&&bs.every(function(b){return b===bs[0];}))?bs[0]:'main';if(nb!==f.band){f.band=nb;marks.push(f.id);}});}
  function labelOf(id){var el=nodeEls[id];return el?el.querySelector('text.lbl'):null;}
  // 0.17.2 暫存後重排：relayout() 只照 order 排，applyOptimistic 改了 parent／band 後節點會留在原列，這裡對每個 (band, col) 格子重算 order。
  // anchor＝節點的歸屬：parent；頂層 plan 用 plans 邊的來源問題、頂層結果用 produces 邊的來源（plan 或子分析）、驗證用 validated_by 的來源 plan、
  // 圖表用 depicts 的來源結果；問題與決策沒有 anchor。
  function anchorOf(n){if(n.parent)return n.parent;var t={method:'plans',result:'produces',validation:'validated_by',figure:'depicts'}[n.type]||'';if(!t)return '';var a='';(inE[n.id]||[]).forEach(function(ei){var e=G.edges[ei];if(!a&&e.type===t&&nodes[e.from])a=e.from;});return a;}
  // 第一次呼叫時保存 IR 的 order／parent／band／anchor（order0 等）當基準；之後只在 reorder 那一種動作更新 order0
  function snapOrder0(){G.nodes.forEach(function(n){if(n.order0===undefined){n.order0=n.order;n.parent0=n.parent||'';n.band0=n.band;n.anchor0=anchorOf(n);n.strip0=n.strip||'';}});}
  // 節點是否被暫存動作動過：換帶、換 parent、換 anchor、reorder 標記，或其 anchor（同一區帶內、遞迴）被動過——動過的節點才離開 order0 的位置；
  // anchor 在別的區帶就不跟（例：主結果搬去補充帶，留在 Main 帶的圖表不動）
  function nodeMoved(n,depth){depth=depth||0;if(!n||n.order0===undefined||depth>16)return false;if(n.moved0||n.band!==n.band0||(n.parent||'')!==n.parent0)return true;var a=anchorOf(n);if(a!==n.anchor0)return true;return !!(a&&nodes[a]&&nodes[a].band===n.band&&nodeMoved(nodes[a],depth+1));}
  // 每格：頂層節點（parent 為空或 parent 不在同格）照 order0 排，各頂層節點後緊接其子孫（深度不限，各層照 order0、被換過 parent 的子節點排在同層最後）；
  // 動過的頂層節點視為浮動，依 anchor 在其格內的列序（再 order0）逐一插入：排在同格內同 anchor 的既有節點之後；沒有就看 anchor 所在格由上而下的鄰居——
  // 往上找最近一個在本格有節點者、排在其後，往下找最近一個、排在其前；都沒有就排到該格最後。格子依 (band, col) 順序處理，anchor 所在格（較左欄）先算好。
  function reorderStaged(){
    stagedLayout=true;snapOrder0();
    var cellOf=function(n){return n.band+'|'+n.col;},cells={};G.nodes.forEach(function(n){var k=cellOf(n);(cells[k]=cells[k]||[]).push(n);});
    var cmpId=function(a,b){return a.id<b.id?-1:a.id>b.id?1:0;},byOrder0=function(a,b){return (a.order0-b.order0)||cmpId(a,b);},byOrder=function(a,b){return (a.order-b.order)||cmpId(a,b);};
    var anchorOrder=function(n){var a=anchorOf(n);return (a&&nodes[a])?nodes[a].order:Infinity;},byAnchor=function(a,b){return (anchorOrder(a)-anchorOrder(b))||byOrder0(a,b);};
    var keys=Object.keys(cells).sort(function(a,b){var pa=a.split('|'),pb=b.split('|');return (BANDS.indexOf(pa[0])-BANDS.indexOf(pb[0]))||(+pa[1]-+pb[1]);});
    keys.forEach(function(k){
      var list=cells[k],inCell={},kids={},fixed=[],floating=[];list.forEach(function(n){inCell[n.id]=true;});
      list.forEach(function(n){if(n.parent&&inCell[n.parent])(kids[n.parent]=kids[n.parent]||[]).push(n);else if(nodeMoved(n))floating.push(n);else fixed.push(n);});
      fixed.sort(byOrder0);floating.sort(byAnchor);
      var seq=fixed.slice(),lastWith=function(a){var pos=-1;if(a)seq.forEach(function(m,i){if(anchorOf(m)===a)pos=i;});return pos;},firstWith=function(a){var pos=-1;if(a)seq.forEach(function(m,i){if(pos<0&&anchorOf(m)===a)pos=i;});return pos;};
      floating.forEach(function(n){var a=anchorOf(n),pos=lastWith(a);
        if(pos<0&&a&&nodes[a]){var an=nodes[a],col=(cells[cellOf(an)]||[]).slice().sort(byOrder),at=col.indexOf(an);
          for(var i=at-1;i>=0&&pos<0;i--)pos=lastWith(col[i].id);
          for(var j=at+1;j<col.length&&pos<0;j++){var f=firstWith(col[j].id);if(f>=0){seq.splice(f,0,n);return;}}}
        seq.splice(pos<0?seq.length:pos+1,0,n);});
      var out=[],byKid=function(a,b){var ma=(a.parent||'')!==a.parent0?1:0,mb=(b.parent||'')!==b.parent0?1:0;return (ma-mb)||byOrder0(a,b);},walk=function(n){out.push(n);(kids[n.id]||[]).sort(byKid).forEach(walk);};
      seq.forEach(walk);out.forEach(function(n,i){n.order=i;});});
    if(typeof restripStaged==='function')restripStaged();   // 0.18.1（測試可單獨抽 reorderStaged 跑）
  }
  // 0.18.1 暫存後重算每個節點的問題帶：沒被動過的節點維持 IR 的 strip（strip0）；被動過的（nodeMoved）沿 parent／anchor 取新歸屬的帶——
  // reassign／promote 整棵子樹跟問題（帶隨問題換區帶）、move_plan 的 plan 子樹跟新問題、move_result／move_sensitivity／demote_plan 跟目標、
  // nest_result 不變（父是同 plan 的主結果）；圖表取呈現的結果中 goals 順序最前者。之後各帶的帶序（stripOrder）＝該帶問題節點依重算後的 order、
  // 再接問題節點在別帶但有節點落在這一帶的問題（goals 順序）、最後有孤兒才有空字串帶；與 Python band_strips 同義
  function stripNow(n,depth){depth=depth||0;if(n.type==='question')return n.id;if(n.type==='decision')return '';if(depth>16||!nodeMoved(n))return n.strip0||'';
    if(n.type==='figure'){var best='',bi=Infinity;(inE[n.id]||[]).forEach(function(ei){var e=G.edges[ei];if(e.type!=='depicts'||!nodes[e.from])return;var s=stripNow(nodes[e.from],depth+1);if(s&&qIndex[s]!==undefined&&qIndex[s]<bi){bi=qIndex[s];best=s;}});return best;}
    var a=n.parent||anchorOf(n);if(a&&nodes[a])return stripNow(nodes[a],depth+1);return n.strip0||'';}
  function restripStaged(){
    G.nodes.forEach(function(n){if(n.type!=='decision'&&n.id!=='q:main'){n.strip=stripNow(n);var el=nodeEls[n.id];if(el)el.setAttribute('data-strip',n.strip);}});
    stripOrder={};BANDS.forEach(function(b){var present={},native=[],key={};G.nodes.forEach(function(n){if(n.staged_gone||n.band!==b||n.type==='decision'||n.id==='q:main')return;present[n.strip||'']=true;});
      // goals 順序；該帶自己的問題節點之間改依（reorder 後的）order 排：把它們的 goals 序位由小到大重新分配給 order 由小到大者
      G.nodes.filter(function(n){return n.type==='question'&&n.id!=='q:main'&&n.band===b&&!n.staged_gone;}).sort(function(a,c){return (a.order-c.order)||(a.id<c.id?-1:1);}).forEach(function(n){native.push(n.id);});
      var slots=native.map(function(q){return qIndex[q];}).sort(function(a,c){return a-c;});native.forEach(function(q,i){key[q]=slots[i];});
      var qs=qOrder.filter(function(q){return q!=='q:main'&&(present[q]||native.indexOf(q)>=0);}).sort(function(a,c){return (key[a]!==undefined?key[a]:qIndex[a])-(key[c]!==undefined?key[c]:qIndex[c]);});
      stripOrder[b]=qs.concat(present['']?['']:[]);});
  }
  function nextAqStaged(){var base=parseInt(String(nextAq||nextAqFromIr()).replace('AQ',''),10)||1;stagedAqUsed++;return 'AQ'+(base+stagedAqUsed-1);}
  function applyOptimistic(kind,p){var marks=[];p=p||{};snapOrder0();   // 0.17.2 先保存 IR 基準（order0 等），reorderStaged() 據此判定誰被動過
    if(kind==='reassign'||kind==='promote'){var q='q:'+p.from,band=(kind==='reassign')?'supp':'main';if(!nodes[q])return marks;var to=p.to||(kind==='reassign'?nextAqStaged():'');
      subtree(q).forEach(function(k){var m=nodes[k];if(m&&bandFollows(m))m.band=band;});
      var t=labelOf(q);if(t&&to)t.textContent=nodes[q].label+' → '+to;nodes[q].meta.staged_to=to;marks.push(q);}
    else if(kind==='move_plan'){var pid='p:'+p.plan,q2='q:'+p.to_question;if(!nodes[pid]||!nodes[q2])return marks;var band2=nodes[q2].band;
      subtree(pid).forEach(function(k){var m=nodes[k];if(m&&bandFollows(m))m.band=band2;});
      G.edges.forEach(function(e){if(e.type==='plans'&&e.to===pid)e.from=q2;});nodes[pid].meta.sq=p.to_question;rebuildEdgeIndex();marks.push(pid);}
    else if(kind==='move_sensitivity'){var sid='p:'+p.plan+'#'+p.item,grp='p:'+p.to_plan+'#S';if(!nodes[sid])return marks;var np=nodes[grp]?grp:('p:'+p.to_plan);if(!nodes[np])return marks;
      nodes[sid].parent=np;setBand(sid,nodes[np].band);G.edges.forEach(function(e){if(e.type==='sensitivity'&&e.to===sid)e.from=np;});rebuildEdgeIndex();marks.push(sid);}
    else if(kind==='move_result'){var rid='r:'+p.key,tp='p:'+p.to_plan;if(!nodes[tp])return marks;var r=nodes[rid]||null,srcA=aggOfKey(p.key),entry=null;
      // 0.19.0 宣告粒度：來源若是聚合節點裡的鍵 → 從該聚合節點的 meta.keys 移除（空了就消失）；目標是子分析 → 鍵進目標子分析的聚合節點（沒有就現做一個）、
      // 逐鍵節點消失；目標是 plan（A 型）→ 出現一個主要結果節點（既有逐鍵節點就改 parent／subtype／帶，沒有就現做）
      if(srcA&&nodes[srcA]){var sa=nodes[srcA];entry=(sa.meta.keys||[]).filter(function(k){return k.key===p.key;})[0]||null;sa.meta.keys=(sa.meta.keys||[]).filter(function(k){return k.key!==p.key;});aggLabel(sa);if(!sa.meta.keys.length)sa.staged_gone=true;marks.push(srcA);}
      if(!r&&!entry)return marks;
      if(p.to_item||p.new_item){var par=p.to_item?('p:'+p.to_plan+'#'+p.to_item):('p:'+p.to_plan+'#S');if(!nodes[par])par=tp;var aid='r:'+par.slice(2)+'#secondary',ta=nodes[aid];
        if(!ta){ta=spawnNode(aid,{type:'result',subtype:'secondary_group',parent:par,band:nodes[tp].band,state:'done',title:par.slice(2)+' 的次要結果（暫存預覽）',meta:{plan_id:p.to_plan,result_kind:'secondary',keys:[],n_keys:0,cited_by_figures:[],declared_by:[par],validated:true}});addEdge(par,aid,'produces');}   // 目標子分析原本沒有自有次要鍵 → 沒有聚合節點，現做一個並補子分析 → 聚合的 produces 邊
        if(!entry)entry={key:p.key,registered:!!(r&&r.state==='done'),validated:!!(r&&r.meta.validated),validated_by:(r&&r.meta.validated_by)||[],declared_by:(r&&r.meta.declared_by)||[],plan_id:p.to_plan};entry.plan_id=p.to_plan;
        ta.meta.keys=(ta.meta.keys||[]).concat([entry]);ta.staged_gone=false;aggLabel(ta);if(r){r.staged_gone=true;marks.push(rid);}marks.push(aid);}
      else{if(!r){r=spawnNode(rid,{type:'result',subtype:'primary',parent:'',band:nodes[tp].band,label:p.key,badge:'主要',state:(entry&&entry.registered)?'done':'pending',title:(entry&&entry.description)||p.key,meta:{plan_id:p.to_plan,result_kind:'primary',validated:!!(entry&&entry.validated),validated_by:(entry&&entry.validated_by)||[],declared_by:[tp]}});addEdge(tp,rid,'produces');}
        else{r.parent='';r.subtype='primary';setBand(rid,nodes[tp].band);r.meta.plan_id=p.to_plan;r.meta.result_kind='primary';fixX(r);G.edges.forEach(function(e){if(e.type==='produces'&&e.to===rid)e.from=tp;});rebuildEdgeIndex();}
        marks.push(rid);}}
    else if(kind==='nest_result'){var kid='r:'+p.key;if(!nodes[kid])return marks;var kn=nodes[kid];
      if(p.under){var u='r:'+p.under;if(!nodes[u])return marks;kn.parent=u;kn.subtype='supporting';kn.meta.supports=p.under;setBand(kid,nodes[u].band);(nodes[u].meta.supporting_ids=nodes[u].meta.supporting_ids||[]).push(kid);
        G.edges.forEach(function(e){if(e.type==='produces'&&e.to===kid)e.default_visible=false;});addEdge(u,kid,'supports');}
      else{var old=kn.parent;kn.parent='';kn.subtype='primary';kn.meta.supports='';if(old&&nodes[old]&&nodes[old].meta.supporting_ids)nodes[old].meta.supporting_ids=nodes[old].meta.supporting_ids.filter(function(x){return x!==kid;});
        G.edges.forEach(function(e){if(e.type==='supports'&&e.to===kid)e.default_visible=false;if(e.type==='produces'&&e.to===kid)e.default_visible=true;});}
      fixX(kn);marks.push(kid);}
    else if(kind==='demote_plan'){var sp='p:'+p.plan,dp='p:'+p.to_plan;if(!nodes[sp]||!nodes[dp])return marks;var dg=nodes[dp+'#S']?dp+'#S':dp,sn=nodes[sp],sq0='q:'+String(sn.meta.sq||'');
      // 來源 plan 變成目標群下的子分析（parent＝目標群、subtype sensitivity、縮排、帶跟目標）；它自己的群／子分析／次要結果沿 parent 鏈跟著；主要結果變它的次要結果
      sn.parent=dg;sn.subtype='sensitivity';sn.meta.demoted_to=p.to_plan;setBand(sp,nodes[dp].band);fixX(sn);
      // 0.19.0：來源 plan 的主要結果（含支撐結果）全部進一個聚合節點 r:<plan>#secondary（parent＝來源 plan 節點，它現在是子分析）、逐鍵節點消失
      var ents=[];G.nodes.forEach(function(m){if(m.type==='result'&&!m.spawned&&String((m.meta||{}).result_kind||'')==='primary'&&String((m.meta||{}).plan_id||'')===p.plan){ents.push({key:m.id.slice(2),registered:m.state==='done',validated:!!m.meta.validated,validated_by:m.meta.validated_by||[],declared_by:m.meta.declared_by||[],plan_id:p.to_plan});m.staged_gone=true;marks.push(m.id);}});
      var da=spawnNode('r:'+p.plan+'#secondary',{type:'result',subtype:'secondary_group',parent:sp,band:nodes[dp].band,state:'done',title:p.plan+' 降階後的次要結果（暫存預覽）',meta:{plan_id:p.to_plan,result_kind:'secondary',keys:[],n_keys:0,cited_by_figures:[],declared_by:[sp],validated:true}});da.meta.keys=ents;da.staged_gone=false;aggLabel(da);addEdge(sp,da.id,'produces');marks.push(da.id);
      var sg=sp+'#S';if(nodes[sg]){nodes[sg].staged_gone=true;G.nodes.forEach(function(m){if(m.parent===sg){m.parent=dg;setBand(m.id,nodes[dp].band);marks.push(m.id);}});G.edges.forEach(function(e){if(e.type==='sensitivity'&&e.from===sg)e.from=dg;if(e.type==='sensitivity'&&e.to===sg)e.default_visible=false;});}
      G.edges.forEach(function(e){if(e.type==='plans'&&e.to===sp)e.default_visible=false;});addEdge(dg,sp,'sensitivity');
      var gk=nodes[dg].meta.sensitivity_ids;if(gk)gk.push(sp);if(nodes[sq0]){if(typeof setBadge==='function')setBadge(sq0,'無 active plan');else nodes[sq0].badge='無 active plan';marks.push(sq0);}marks.push(sp);}
    else if(kind==='set_tier'){if(!nodes[p.node])return marks;if(p.tier==='extended')edSetExplicit(p.node,marks);else edClear(p.node,marks);edRederiveFigures(marks);}   // 0.20.0
    else if(kind==='set_role'){var figs={};if(p.figures)Object.keys(p.figures).forEach(function(f){figs[f]=p.figures[f];});if(p.figure)figs[p.figure]=p.role;
      Object.keys(figs).forEach(function(f){var fn=nodes['f:'+f];if(!fn)return;var b=ROLE_BAND[String(figs[f]||'').toLowerCase()];if(b){fn.band=b;fn.meta.role=figs[f];}marks.push('f:'+f);});}
    else if(kind==='reorder'){var qs=(p.order||[]).map(function(x){return 'q:'+x;}).filter(function(k){return !!nodes[k];});var ords=qs.map(function(k){var n=nodes[k];return n.order0!==undefined?n.order0:n.order;}).sort(function(a,b){return a-b;});qs.forEach(function(k,i){var n=nodes[k];n.order=ords[i];if(n.order0!==undefined)n.order0=ords[i];n.moved0=true;});marks=qs;}
    marks.forEach(function(k){stagedNodes[k]=true;var el=nodeEls[k];if(el)el.classList.add('staged');});
    return marks;}
  function stagedTitle(it){var p=it.payload||{},k=it.kind;
    if(k==='reassign')return '降階：'+p.from+' → '+(p.to||'（下一個 AQ 號）')+(p.primary_model?'；primary_model '+p.primary_model:'');
    if(k==='promote')return '升回主問題：'+p.from+' → '+(p.to||'（原號或下一個 SQ 號）');
    if(k==='set_role'){var figs=p.figures||{};if(p.figure)figs[p.figure]=p.role;return '圖表 role：'+Object.keys(figs).map(function(f){return f+' → '+figs[f];}).join('、');}
    if(k==='move_plan')return '搬方法：'+p.plan+' → '+p.to_question;
    if(k==='move_sensitivity')return '搬敏感性子分析：'+p.plan+' '+p.item+' → '+p.to_plan;
    if(k==='demote_plan')return '降為敏感性子分析：'+p.plan+' → '+p.to_plan;
    if(k==='reorder')return '調順序：'+p.list+' → '+(p.order||[]).join('、');
    if(k==='move_result')return '搬結果：'+p.key+' → '+p.to_plan+(p.to_item?' '+p.to_item:(p.new_item?' 新增子分析':''));
    if(k==='nest_result')return p.under?('掛到主結果下：'+p.key+' → '+p.under):('拉回頂層：'+p.key);
    if(k==='set_tier')return (p.tier==='extended'?'放入 Extended Data：':'移出 Extended Data：')+p.node;
    return k;}
  function stagedTarget(it){var p=it.payload||{},k=it.kind;if(k==='set_tier')return String(p.node||'');if(k==='reassign'||k==='promote')return 'q:'+p.from;if(k==='set_role')return 'f:'+(p.figure||Object.keys(p.figures||{})[0]||'');if(k==='move_plan'||k==='demote_plan')return 'p:'+p.plan;if(k==='move_sensitivity')return 'p:'+p.plan+'#'+p.item;if(k==='reorder')return 'q:'+((p.order||[])[0]||'');return nodes['r:'+p.key]?'r:'+p.key:(aggOfKey(p.key)||'r:'+p.key);}
  function stagedUi(){return {pre:document.getElementById('staged-summary'),apply:document.getElementById('staged-apply'),lock:[document.getElementById('staged-preview'),document.getElementById('staged-clear')],confirm:false,
    extra:function(){return {reason:stagedReason()};},   // 0.17.3 套用時才帶整批理由（server 對 batch 蓋過 payload 頂層 reason、成功後同步收件匣那筆）
    onStale:function(){if(stagedBatchId)stagedDryRun(stagedBatchId);},
    okText:function(d){return '已套用 '+staged.length+' 步，'+(d.decision||'')+'；重新載入';},
    onOk:function(){staged=[];stageSave();stagedBatchClear();try{localStorage.removeItem(STAGE_REASON_KEY);}catch(e){}},
    onFail:function(d){var m=/第 (\\d+) 步失敗/.exec(String(d.summary||''));if(m){var k=parseInt(m[1],10);if(k>1){staged=staged.slice(k-1);stageSave();}}
      document.getElementById('staged-err').textContent='批次未全部完成：'+(d.error||'')+'（摘要寫明停在哪；已套用的步驟各有 D#、失敗那步已還原；暫存清單只留下未套用的步驟，請重新載入頁面後再處理）';}};}
  function renderStagedOld(){var box=document.getElementById('staged-old');if(!box)return;var old=stagedOldBatches();box.hidden=!old.length;if(!old.length){box.innerHTML='';return;}
    var ids=old.map(function(it){return it.id;});
    box.innerHTML='有 '+old.length+' 筆舊的批次項目（'+esc(ids.slice(0,6).join('、'))+(ids.length>6?'…':'')+'）不是本頁暫存建立的：<button type="button" id="staged-old-dismiss"'+(serverOk?'':' disabled title="未連上 progress_server.py"')+'>撤回它們</button> <span class="src" id="staged-old-msg">只改收件匣狀態（dismissed），不動 SSOT；「待套用動作」面板仍可逐筆預覽／套用</span>';}
  function renderStaged(){renderStagedOld();var panel=document.getElementById('staged-panel');if(!panel)return;panel.hidden=!staged.length;document.getElementById('staged-count').textContent=String(staged.length);
    var tb=document.getElementById('staged-body');tb.innerHTML='';
    staged.forEach(function(it,i){var tr=document.createElement('tr');tr.setAttribute('data-staged-i',String(i));var tgt=stagedTarget(it);
      tr.innerHTML='<td>'+(i+1)+'</td><td>'+esc(ACT_LABEL[it.kind]||it.kind)+'</td><td><span class="goto" data-goto="'+esc(tgt)+'">'+esc(nodes[tgt]?nodes[tgt].label:tgt)+'</span></td><td>'+esc(stagedTitle(it))+'<br><span class="src">'+esc(it.reason||'（未填；用整批理由）')+'</span></td>'
        +'<td><button type="button" class="st-edit" data-i="'+i+'" title="開表單改這一項（to／primary_model／落點／理由），按「更新暫存」取代並重套用">編輯</button> <button type="button" class="st-up" data-i="'+i+'"'+(i===0?' disabled':'')+' title="上移">↑</button> <button type="button" class="st-down" data-i="'+i+'"'+(i===staged.length-1?' disabled':'')+' title="下移">↓</button> <button type="button" class="st-del" data-i="'+i+'" title="刪除這一項（重新載入頁面、重新套用其餘暫存）">刪除</button></td>';
      tb.appendChild(tr);});
    var pv=document.getElementById('staged-preview');pv.disabled=!actionsOk||!staged.length;pv.title=actionsOk?'':'server 未開 --allow-apply';
    var ap=document.getElementById('staged-apply'),why=document.getElementById('staged-apply-why'),ready=!!(stagedBatchId&&actTokens[stagedBatchId]);
    var whyTxt=!actionsOk?actionsWhy:(ready?'':(stagedStale?'暫存清單已變，請重新預覽':'先全部預覽'));   // 0.17.3 停用原因寫在鈕旁，不只放 title
    ap.disabled=!!whyTxt;ap.title=whyTxt;if(why)why.textContent=whyTxt;
    document.getElementById('staged-batch-id').textContent=stagedBatchId?('收件匣 '+stagedBatchId):'';}
  function stageAdd(kind,payload,reason,options){var it={kind:kind,payload:payload,reason:reason||''};if(options&&options.length)it.options=options;   // options（區帶落點的下拉）留著給「編輯」用
    staged.push(it);stagedInvalidate();applyOptimistic(kind,payload);reorderStaged();stageSave();renderStaged();relayout();
    closeActForm();toastUndo('已暫存：'+stagedTitle(it),function(){stageRemove(it);});return it;}
  function stageRemove(it){var i=staged.indexOf(it);if(i<0)return;staged.splice(i,1);stagedInvalidate();stagedReload();}   // 復原＝移除該項、重新載入並重套用其餘暫存（與刪除單項同一套）
  // 0.17.1 放開即暫存：各 kind 的預設值——reassign to＝下一個 AQ 號（已暫存的 reassign 各占一號）、不帶 primary_model；promote to 空（腳本回原號或下一號）；
  // move_result 拖到區帶＝候選的第一個選項（新增子分析、預設描述）、拖到節點照候選；set_role／nest_result／move_plan／move_sensitivity／reorder 照候選；理由空
  function defaultPayload(cand){var p=cand.payload||{};
    if(cand.kind==='reassign'){var used=staged.filter(function(it){return it.kind==='reassign';}).length,base=parseInt(String(nextAq||nextAqFromIr()).replace('AQ',''),10)||1;return {from:p.from,to:'AQ'+(base+used),primary_model:''};}
    if(cand.kind==='promote')return {from:p.from,to:''};
    return p;}
  function stageDirect(cand){stageAdd(cand.kind,defaultPayload(cand),'',cand.options);}
  // 0.19.0：一次暫存多筆（聚合節點拖曳＝裡面全部鍵各一筆 move_result，順序照 meta.keys）；樂觀更新逐筆套、版面只重排一次；復原＝整批移除
  function stageMany(items){var its=items.map(function(x){var it={kind:x.kind,payload:x.payload,reason:''};staged.push(it);return it;});stagedInvalidate();
    its.forEach(function(it){applyOptimistic(it.kind,it.payload);});reorderStaged();stageSave();renderStaged();relayout();closeActForm();
    toastUndo('已暫存 '+its.length+' 筆：'+stagedTitle(its[0])+(its.length>1?' …':''),function(){its.forEach(function(it){var i=staged.indexOf(it);if(i>=0)staged.splice(i,1);});stagedInvalidate();stagedReload();});return its;}
  // 「編輯」：開原本的表單、預填該項；「更新暫存」取代該項並重新載入（重套用全部暫存）
  function stageEdit(i){var it=staged[i];if(!it||!serverOk)return;var p=it.payload||{};
    openActionForm(it.kind,p,it.options);if(actForm.hidden)return;
    if(it.kind==='reassign'){$v('act-to',p.to||'');var pm=document.getElementById('act-pm');pm.value=p.primary_model||'';if(pm.value!==(p.primary_model||''))pm.value='';}
    else if(it.kind==='promote')$v('act-p-to',p.to||'');
    else if(it.kind==='move_result'&&it.options&&it.options.length){var sel=document.getElementById('act-mr-dest'),want=JSON.stringify(p);it.options.forEach(function(o,j){if(JSON.stringify(o.payload)===want){sel.value=String(j);actPayload=o.payload;}});mrFill(actPayload);}
    $v('act-reason',it.reason||'');actEditIndex=i;
    document.getElementById('act-form-title').textContent='編輯暫存第 '+(i+1)+' 項：'+document.getElementById('act-form-title').textContent;
    document.getElementById('act-stage').textContent='更新暫存';document.getElementById('act-submit').hidden=true;}
  // 只有暫存清單本身變了（增刪、上下移、編輯）才呼叫：dismiss 舊項目（keepalive，緊接的 reload 不會取消）、清 stagedBatchId、紀錄改標 stale（重新載入後若那筆仍 pending 會再補 dismiss）
  function stagedInvalidate(){if(stagedBatchId){delete actTokens[stagedBatchId];var old=stagedBatchId;stagedBatchId='';stagedStale=true;stagedBatchSave({id:old,stale:true});actPost(DISMISS_PATH,{id:old,note:'暫存清單已變更，此批次項目作廢'},{keepalive:true}).catch(function(){});}
    var pre=document.getElementById('staged-summary');if(pre)pre.textContent='';}
  function stagedReload(){stageSave();location.reload();}
  document.getElementById('act-stage').addEventListener('click',function(){if(actStageNow!=='form')return;var payload=actFormPayload();if(!payload)return;
    if(actEditIndex>=0&&staged[actEditIndex]){var old=staged[actEditIndex];staged[actEditIndex]={kind:payload.kind,payload:payload.payload,reason:payload.reason};if(old.options)staged[actEditIndex].options=old.options;
      stagedInvalidate();stagedReload();return;}
    stageAdd(payload.kind,payload.payload,payload.reason,actOptions);});
  var stagedPanel=document.getElementById('staged-panel');
  if(stagedPanel)stagedPanel.addEventListener('click',function(e){
    var g=e.target.closest('.goto');if(g&&nodes[g.getAttribute('data-goto')]){showTab('relations',true);select(g.getAttribute('data-goto'),true);return;}
    var b=e.target.closest('button');if(!b||b.disabled)return;var i=parseInt(b.getAttribute('data-i')||'-1',10);
    if(b.classList.contains('st-edit')){stageEdit(i);return;}
    if(b.classList.contains('st-del')){staged.splice(i,1);stagedInvalidate();stagedReload();return;}
    if(b.classList.contains('st-up')&&i>0){var t=staged[i-1];staged[i-1]=staged[i];staged[i]=t;stagedInvalidate();stagedReload();return;}
    if(b.classList.contains('st-down')&&i<staged.length-1){var t2=staged[i+1];staged[i+1]=staged[i];staged[i]=t2;stagedInvalidate();stagedReload();return;}
    if(b.id==='staged-clear'){staged=[];stagedInvalidate();stagedBatchClear();try{localStorage.removeItem(STAGE_REASON_KEY);}catch(e){}stagedReload();return;}
    if(b.id==='staged-preview'){stagedPreview();return;}
    if(b.id==='staged-apply'){if(!stagedBatchId)return;actApply(stagedBatchId,stagedUi());return;}});
  // dry-run 一筆已建的 batch；成功（有 token）就把 {id, token, actions} 存進 localStorage，重新載入後沿用
  function stagedDryRun(id){return actPreview(id,stagedUi()).then(function(x){if(actTokens[id]){stagedStale=false;stagedBatchSave({id:id,token:actTokens[id],actions:stagedActionsJson()});}renderStaged();return x;});}
  function stagedPreview(){if(!staged.length||!actionsOk)return;var err=document.getElementById('staged-err');err.textContent='';var ui=stagedUi();
    var actions=staged.map(function(it){return {kind:it.kind,payload:it.payload,reason:it.reason||''};}),aj=JSON.stringify(actions),rec=stagedBatchLoad();
    if(stagedBatchId&&rec&&rec.id===stagedBatchId&&!rec.stale&&rec.actions===aj){toast('暫存清單沒變，沿用收件匣 '+stagedBatchId+' 重新預覽');stagedDryRun(stagedBatchId);return;}   // 0.17.3 重複預覽不堆積：同清單重用同一筆，只重跑 dry-run
    var go=function(){actBusy(ui,true);ui.pre.textContent='建立批次項目…';
      actPost('/api/inbox',{kind:'batch',payload:{actions:actions,reason:stagedReason()}})   // 0.17.1 整批理由放 payload 頂層；0.17.3 起套用時再帶一次現值蓋過（理由改了不必重建）
        .then(function(x){var d=x.d||{};if(!d.ok){actBusy(ui,false);ui.pre.textContent='';err.textContent='建立批次項目失敗：'+(d.error||('HTTP '+x.status));return;}
          stagedBatchId=d.id;stagedStale=false;stagedBatchSave({id:d.id,token:'',actions:aj});renderStaged();toast('已送入收件匣 '+d.id+'（批次 '+staged.length+' 項），正在預覽');return stagedDryRun(d.id);})
        .catch(function(e2){actBusy(ui,false);err.textContent='建立批次項目失敗：'+e2;});};
    if(stagedBatchId){var old=stagedBatchId;stagedBatchId='';delete actTokens[old];actPost(DISMISS_PATH,{id:old,note:'重新預覽，前一筆批次項目作廢'}).then(go,go);}else go();}
  // 0.17.3 舊批次項目一鍵撤回：不是本頁暫存建立（stagedBatchId 以外）的 pending batch 逐筆 dismiss，note 固定，完成後重新載入
  var stagedOldBox=document.getElementById('staged-old');
  if(stagedOldBox)stagedOldBox.addEventListener('click',function(e){var b=e.target.closest('#staged-old-dismiss');if(!b||b.disabled)return;var ids=stagedOldBatches().map(function(it){return it.id;});if(!ids.length)return;
    b.disabled=true;var msg=document.getElementById('staged-old-msg'),done=0,fail=[];
    var step=function(i){if(i>=ids.length){msg.textContent='已撤回 '+done+' 筆'+(fail.length?'；失敗：'+fail.join('、'):'')+'；重新載入';setTimeout(function(){location.reload();},1200);return;}
      msg.textContent='撤回 '+ids[i]+'（'+(i+1)+'／'+ids.length+'）…';
      actPost(DISMISS_PATH,{id:ids[i],note:'舊批次項目，由頁面一鍵撤回'}).then(function(x){if(x.d&&x.d.ok)done++;else fail.push(ids[i]);step(i+1);},function(){fail.push(ids[i]);step(i+1);});};
    step(0);});
  // 測試用唯讀鉤子：回某節點在本地圖模型的 parent／band／subtype／座標與暫存清單長度（不改任何狀態）
  window.__apNode=function(id){var n=nodes[id];return n?{parent:n.parent||'',band:n.band,subtype:n.subtype||'',x:n.x,y:n.y,order:n.order,staged:!!stagedNodes[id],supports:String((n.meta||{}).supports||''),label:n.label,gone:!!n.staged_gone,keys:(n.meta&&n.meta.keys)?n.meta.keys.map(function(k){return k.key;}):null}:null;};
  window.__apStaged=function(){return staged.map(function(it){return {kind:it.kind,payload:it.payload,reason:it.reason};});};
  window.__apFormOnDrop=function(){return formOnDrop;};
  window.__apBatch=function(){return {id:stagedBatchId,token:actTokens[stagedBatchId]||'',stale:stagedStale,rec:stagedBatchLoad(),old:stagedOldBatches().map(function(it){return it.id;})};};
  // 還原暫存（重新載入後）：依序重做樂觀更新；套用成功或清空後 localStorage 已清
  staged=stageLoad();
  if(staged.length){staged.forEach(function(it){try{applyOptimistic(it.kind,it.payload);}catch(e){}});reorderStaged();}
  // 0.17.3 還原已建的批次：那筆仍 pending 且 actions 與暫存清單相同 → 沿用 id 與 token（token 若因 SSOT 變動失效，套用回 409 → onStale 重跑 dry-run）；
  // 否則（清單變了、那筆已處理、或紀錄已標 stale）→ 仍 pending 就補 dismiss、清單非空時標 stale 顯示「暫存清單已變，請重新預覽」
  (function(){var rec=stagedBatchLoad();if(!rec)return;var it=inboxItem(rec.id),pend=!!(it&&it.kind==='batch'&&(it.status||'pending')==='pending');
    if(!rec.stale&&pend&&staged.length&&rec.actions===stagedActionsJson()){stagedBatchId=rec.id;if(rec.token)actTokens[rec.id]=rec.token;return;}
    if(pend)actPost(DISMISS_PATH,{id:rec.id,note:'暫存清單已變更，此批次項目作廢'}).catch(function(){});
    if(staged.length){stagedStale=true;stagedBatchSave({id:rec.id,stale:true});}else stagedBatchClear();})();
  renderStaged();
  relayout();
})();
"""

# ---------- 文獻分頁（第三個分頁） ----------

LIT_CSS = """
.lit3d-wrap{margin:0}
.lit3d-demo{margin:10px 0 8px;font-size:13px;color:var(--muted)}
.lit3d-empty{margin:18px 0;color:var(--muted)}
.lit3d-legend{display:flex;flex-wrap:wrap;gap:5px 16px;margin:10px 0 6px;padding:0;list-style:none;font-size:12.5px;color:var(--muted)}
.lit3d-legend li{display:flex;align-items:center;gap:6px}
.lit3d-dot{width:11px;height:11px;border-radius:50%;flex:0 0 auto}
.lit3d-dot.is-q{background:var(--t-question)}
.lit3d-legend li.lit3d-scale{flex-direction:column;align-items:flex-start;gap:3px}
.lit3d-scale-row{display:flex;align-items:center;gap:7px;padding-bottom:15px}
.lit3d-ramp{position:relative;width:96px;height:9px;border-radius:5px;flex:0 0 auto;border:1px solid var(--line);
background:linear-gradient(90deg,var(--lit-ramp-0),var(--lit-ramp-1),var(--lit-ramp-2),var(--lit-ramp-3),var(--lit-ramp-4),var(--lit-ramp-5))}
.lit3d-tick{position:absolute;top:calc(100% + 1px);width:1px;height:3px;background:var(--line)}
.lit3d-tick i{position:absolute;top:3px;left:50%;transform:translateX(-50%);font-style:normal;
font-size:11px;line-height:1.1;font-variant-numeric:tabular-nums}
.lit3d-tick.is-first i{left:0;transform:none}
.lit3d-tick.is-last i{left:auto;right:0;transform:none}
.lit3d-dot.is-lo{width:9px;height:9px;background:var(--lit-ramp-0)}
.lit3d-dot.is-hi{width:14px;height:14px;background:var(--lit-ramp-5)}
.lit3d-bar{width:20px;height:2px;border-radius:1px;flex:0 0 auto}
.lit3d-bar.is-q{background:var(--t-question);opacity:.6}
.lit3d-bar.is-c{background:var(--edge)}
.lit3d-hint{margin:0 0 10px;font-size:12.5px;color:var(--muted)}
.lit3d-stage{position:relative;width:100%;max-width:100%;border:1px solid var(--line);border-radius:10px;background:var(--card);overflow:hidden}
.lit3d-canvas{display:block;width:100%;height:min(78vh,760px);touch-action:none;cursor:grab}
.lit3d-canvas:active{cursor:grabbing}
.lit3d-canvas:focus{outline:2px solid var(--current);outline-offset:-3px}
.lit3d-canvas:focus:not(:focus-visible){outline:none}
.lit3d-canvas:focus-visible{outline:2px solid var(--current);outline-offset:-3px}
.lit3d-tip{position:absolute;left:0;top:0;z-index:5;pointer-events:none;max-width:min(320px,calc(100% - 20px));
padding:9px 11px;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--fg);
box-shadow:0 6px 22px rgba(15,20,25,.18);font-size:12.5px;line-height:1.55}
.lit3d-tip[hidden]{display:none}
.lit3d-tip .lit3d-tip-id{font-size:13.5px;font-weight:650;color:var(--t-question)}
.lit3d-tip .lit3d-tip-title{margin:3px 0;font-weight:600}
.lit3d-tip .lit3d-tip-sub{color:var(--muted)}
.lit3d-tip .lit3d-tip-meta{margin-top:4px;padding-top:4px;border-top:1px solid var(--line);color:var(--muted)}
@media (max-width:520px){.lit3d-legend{gap:4px 12px}}
"""

# 互動與原型一致：自動慢轉、拖曳旋轉、滾輪／雙指縮放、hover 或點擊高亮加 tooltip、鍵盤、prefers-reduced-motion。
# 與原型的差別：資料改讀頁面既有的 progress-ir；拿掉會和分頁 hash 打架的裸 token 深層連結，改開 window.lit3dSelect(id)；
# 分頁隱藏時停掉 requestAnimationFrame（隱藏時 canvas 量到的尺寸是 0，切回來要先重量一次）。
LIT_JS = """
(function(){
  "use strict";
  var raw = document.getElementById("progress-ir");
  var section = document.getElementById("tab-literature");
  var canvas = document.getElementById("lit3d-canvas");
  if (!raw || !section || !canvas) return;
  var LIT = JSON.parse(raw.textContent).literature || {};
  var DATA = LIT.data || {nodes:[], edges:[]};
  var MAXCIN = (typeof LIT.max_cin === "number" && LIT.max_cin > 0) ? LIT.max_cin : 0;
  var NODES = DATA.nodes || [], EDGES = DATA.edges || [], N = NODES.length;
  if (!N) return;
  var stage = document.getElementById("lit3d-stage");
  var tip = document.getElementById("lit3d-tip");
  var ctx = canvas.getContext("2d");
  if (!ctx) return;
  var FONT = 'system-ui,-apple-system,"Segoe UI","Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif';

  /* ---- 相鄰關係 ---- */
  /* 被引數不在這裡算：IR 的 nd.cin 已經是圈內被引數（只算 cites、去重、排掉自我引用與懸空邊） */
  var nbr = [], cites = [], qOf = [], litCount = {};
  for (var i = 0; i < N; i++){ nbr.push({}); cites.push(0); qOf.push([]); }
  for (var ei = 0; ei < EDGES.length; ei++){
    var e = EDGES[ei], s = e.s, t = e.t;
    nbr[s][t] = 1; nbr[t][s] = 1;
    if (e.k === "ll"){ cites[s]++; }
    else { qOf[s].push(NODES[t].id); litCount[t] = (litCount[t] || 0) + 1; }
  }

  /* ---- 主題色：canvas 不繼承 CSS，需自己讀 token ---- */
  var C = {};
  function hex2rgb(h, fb){
    h = (h || "").trim();
    if (h.charAt(0) === "#"){
      if (h.length === 4) h = "#" + h[1] + h[1] + h[2] + h[2] + h[3] + h[3];
      if (h.length === 7){
        return [parseInt(h.substr(1,2),16), parseInt(h.substr(3,2),16), parseInt(h.substr(5,2),16)];
      }
    }
    return fb;
  }
  function rgba(c, a){ return "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + a.toFixed(3) + ")"; }
  function readTheme(){
    var cs = getComputedStyle(document.documentElement);
    function g(k){ return cs.getPropertyValue(k); }
    C.bg = hex2rgb(g("--bg"), [250,250,248]);
    C.fg = hex2rgb(g("--fg"), [31,35,40]);
    C.edge = hex2rgb(g("--edge"), [154,163,173]);
    C.q = hex2rgb(g("--t-question"), [68,119,170]);
    C.lit = hex2rgb(g("--t-lit"), [168,117,27]);
    C.cur = hex2rgb(g("--current"), [0,114,178]);
    C.ramp = readRamp(g);
  }
  /* 色階只定義在 CSS 的 --lit-ramp-0…N（亮暗各一組），這裡讀到沒有為止，JS 不寫死階數 */
  function readRamp(g){
    var stops = [];
    for (var i = 0; i < 64; i++){
      var v = (g("--lit-ramp-" + i) || "").trim();
      if (!v) break;
      var c = hex2rgb(v, null);
      if (c) stops.push(c);
    }
    return stops.length ? stops : [C.lit];
  }
  /* 文獻點的顏色與大小共用同一條刻度：圈內被引數取對數後對到 0–1（最大值 0 時一律 0，不除以零）。
     被引數本來就偏斜，線性刻度會讓低端幾乎同色同大。 */
  function litT(cin){
    return MAXCIN > 0 ? Math.min(1, Math.max(0, Math.log(1 + cin) / Math.log(1 + MAXCIN))) : 0;
  }
  function litColor(cin){
    var st = C.ramp, n = st.length - 1;
    if (n <= 0) return st[0];
    var t = litT(cin);
    var p = t * n, i = Math.min(n - 1, Math.floor(p)), f = p - i;
    var a = st[i], b = st[i + 1];
    return [Math.round(a[0] + (b[0] - a[0]) * f),
            Math.round(a[1] + (b[1] - a[1]) * f),
            Math.round(a[2] + (b[2] - a[2]) * f)];
  }
  /* 刻度值與主題無關，開場算一次就好；問題點不吃這條刻度 */
  var litTv = new Float64Array(N);
  for (var i = 0; i < N; i++) litTv[i] = NODES[i].q ? 0 : litT(NODES[i].cin || 0);
  /* 點的基準半徑（螢幕 px，畫的時候還要乘投影縮放）：問題點固定，文獻點隨刻度放大，
     最大 4.5 * (1 + 0.6) = 7.2，同深度下是問題點的 0.8 倍 */
  var R_Q = 9, R_LIT = 4.5, R_GAIN = 0.6;
  var litRGB = new Array(N);
  function refreshTheme(){
    readTheme();
    for (var i = 0; i < N; i++) litRGB[i] = NODES[i].q ? C.q : litColor(NODES[i].cin || 0);
  }
  refreshTheme();
  var mqDark = window.matchMedia("(prefers-color-scheme: dark)");
  if (mqDark.addEventListener) mqDark.addEventListener("change", refreshTheme);
  else if (mqDark.addListener) mqDark.addListener(refreshTheme);

  /* ---- 取景半徑：座標已歸一化到半徑 1，但少數離群點會讓整團縮太小，
         改用第 95 百分位半徑取景，離群點超出邊界時由 stage 裁掉，縮小即可看全 ---- */
  var FITR = (function(){
    var rs = [];
    for (var i = 0; i < N; i++){
      var nd = NODES[i];
      rs.push(Math.sqrt(nd.x * nd.x + nd.y * nd.y + nd.z * nd.z));
    }
    rs.sort(function(a, b){ return a - b; });
    var r = rs[Math.min(rs.length - 1, Math.floor(rs.length * 0.95))] || 1;
    return Math.min(1, Math.max(0.5, r));
  })();

  /* ---- 視角狀態 ---- */
  var rotX = -0.30, rotY = 0.55, zoom = 1.0;
  var ZMIN = 0.45, ZMAX = 4.0;
  var CAM = 3.2;
  var hoverIdx = -1, pinIdx = -1, tipAnchor = "cursor";
  var dragging = false, moved = false, resumeAt = 0, lastX = 0, lastY = 0;
  var W = 0, H = 0, dpr = 1;
  var sx = new Float64Array(N), sy = new Float64Array(N);
  var sd = new Float64Array(N), sr = new Float64Array(N);
  var order = new Int32Array(N), eOrder = new Int32Array(EDGES.length);
  var mqMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  function resize(){
    var r = canvas.getBoundingClientRect();
    if (!r.width || !r.height) return;   /* 分頁隱藏時量到 0，維持上次的尺寸 */
    dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
    W = r.width; H = r.height;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
  }
  if (window.ResizeObserver) new ResizeObserver(function(){ if (running) resize(); }).observe(stage);
  window.addEventListener("resize", function(){ if (running) resize(); });

  function activeIdx(){ return pinIdx >= 0 ? pinIdx : hoverIdx; }

  /* ---- 繪製 ---- */
  var depthBuf = new Float64Array(EDGES.length);
  function draw(){
    if (!W || !H) { resize(); if (!W || !H) return; }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    var cx = W / 2, cy = H / 2;
    var base = Math.min(W, H) * 0.44 * zoom / FITR;
    var cY = Math.cos(rotY), sY = Math.sin(rotY);
    var cX = Math.cos(rotX), sX = Math.sin(rotX);
    var act = activeIdx();
    var hasAct = act >= 0;
    var near = nbr[act] || {};

    for (var i = 0; i < N; i++){
      var nd = NODES[i];
      var x1 = nd.x * cY + nd.z * sY;
      var z1 = nd.z * cY - nd.x * sY;
      var y2 = nd.y * cX - z1 * sX;
      var z2 = nd.y * sX + z1 * cX;
      var depth = CAM - z2;
      if (depth < 0.25) depth = 0.25;
      var kk = base * CAM / depth;
      sx[i] = cx + x1 * kk;
      sy[i] = cy - y2 * kk;
      sd[i] = depth;
      var ss = CAM / depth;
      sr[i] = (nd.q ? R_Q : R_LIT * (1 + R_GAIN * litTv[i])) * ss;
      order[i] = i;
    }

    /* 連線：由遠到近 */
    var EL = EDGES.length;
    for (var a = 0; a < EL; a++){
      depthBuf[a] = (sd[EDGES[a].s] + sd[EDGES[a].t]) * 0.5;
      eOrder[a] = a;
    }
    var eArr = Array.prototype.slice.call(eOrder);
    eArr.sort(function(p, q){ return depthBuf[q] - depthBuf[p]; });
    for (var m = 0; m < eArr.length; m++){
      var idx = eArr[m], ed = EDGES[idx];
      var fade = 1 - Math.min(1, Math.max(0, (depthBuf[idx] - (CAM - 1)) / 2));
      var on = !hasAct || ed.s === act || ed.t === act;
      var dim = on ? 1 : 0.15;
      var al, col, lw;
      if (ed.k === "lq"){
        col = C.q; lw = 0.9; al = (0.14 + 0.24 * fade) * (on && hasAct ? 3.0 : 1) * dim;
      } else {
        col = C.edge; lw = 0.8; al = (0.12 + 0.20 * fade) * (on && hasAct ? 3.0 : 1) * dim;
      }
      if (al > 0.92) al = 0.92;
      if (al < 0.012) continue;
      ctx.strokeStyle = rgba(col, al);
      ctx.lineWidth = lw;
      ctx.beginPath();
      ctx.moveTo(sx[ed.s], sy[ed.s]);
      ctx.lineTo(sx[ed.t], sy[ed.t]);
      ctx.stroke();
    }

    /* 節點：由遠到近 */
    var nArr = Array.prototype.slice.call(order);
    nArr.sort(function(p, q){ return sd[q] - sd[p]; });
    var labels = [];
    for (var v = 0; v < nArr.length; v++){
      var j = nArr[v];
      var node = NODES[j];
      var f2 = 1 - Math.min(1, Math.max(0, (sd[j] - (CAM - 1)) / 2));
      var lit = !hasAct || j === act || near[j];
      var alpha = (0.34 + 0.66 * f2) * (lit ? 1 : 0.15);
      var rr = sr[j];
      if (j === act) rr *= 1.45;
      ctx.fillStyle = rgba(litRGB[j] || (node.q ? C.q : C.lit), alpha);
      ctx.beginPath();
      ctx.arc(sx[j], sy[j], rr, 0, 6.283185307179586);
      ctx.fill();
      if (j === act){
        ctx.strokeStyle = rgba(C.cur, 0.95);
        ctx.lineWidth = 2;
        ctx.stroke();
      }
      if (node.q) labels.push([j, rr, alpha]);
    }
    for (var L = 0; L < labels.length; L++){
      var li = labels[L][0], lr = labels[L][1], la = labels[L][2];
      ctx.font = "600 12.5px " + FONT;
      ctx.textBaseline = "middle";
      ctx.lineWidth = 3.4;
      ctx.strokeStyle = rgba(C.bg, Math.min(0.92, la));
      ctx.strokeText(NODES[li].id, sx[li] + lr + 5, sy[li]);
      ctx.fillStyle = rgba(C.fg, la);
      ctx.fillText(NODES[li].id, sx[li] + lr + 5, sy[li]);
    }

    if (!tip.hidden && tipAnchor === "node" && act >= 0) placeTip(sx[act], sy[act]);
  }

  /* ---- 動畫：只在本分頁顯示時跑 ---- */
  var running = false, rafId = 0, prevTs = 0;
  function frame(ts){
    if (!running) return;
    var dt = prevTs ? Math.min(0.05, (ts - prevTs) / 1000) : 0;
    prevTs = ts;
    var auto = !mqMotion.matches && !dragging && activeIdx() < 0 && ts >= resumeAt;
    if (auto) rotY += 0.12 * dt;
    draw();
    rafId = requestAnimationFrame(frame);
  }
  function start(){
    if (running) return;
    running = true; prevTs = 0;
    resize();          /* 分頁剛顯示，尺寸要重量一次 */
    rafId = requestAnimationFrame(frame);
  }
  function stop(){
    running = false;
    if (rafId) cancelAnimationFrame(rafId);
    rafId = 0;
  }
  document.addEventListener("progress:tab", function(ev){
    var name = (ev && ev.detail && ev.detail.tab) || "";
    if (name === "literature") start(); else stop();
  });
  document.addEventListener("visibilitychange", function(){
    if (document.hidden) stop(); else if (!section.hidden) start();
  });
  if (!section.hidden) start();   /* 一開頁 hash 就是 #literature 時，showTab 已經跑過 */

  /* ---- tooltip ---- */
  function esc(s){
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function thousands(n){ return String(n).replace(/\\B(?=(\\d{3})+(?!\\d))/g, ","); }
  function tipHTML(i){
    var nd = NODES[i];
    if (nd.q){
      var note = nd.note ? esc(nd.note) : "（project.yaml 的 goals 沒有這個 id）";
      return '<div class="lit3d-tip-id">' + esc(nd.id) + '</div>' +
             '<div class="lit3d-tip-sub">' + note + '</div>' +
             '<div class="lit3d-tip-meta">連到 ' + (litCount[i] || 0) + ' 篇文獻</div>';
    }
    var qs = qOf[i].length ? qOf[i].join("、") : "（無）";
    var head = [esc(nd.authors), nd.year ? "（" + esc(nd.year) + "）" : ""].join("");
    var gc = nd.gc;
    var world = gc ? '<br>' + esc(gc.source) + ' 被引 ' + thousands(gc.count) + ' 次（' + esc(gc.retrieved) + ' 取得）' : '';
    return '<div class="lit3d-tip-sub">' + (head || esc(nd.id)) + '</div>' +
           '<div class="lit3d-tip-title">' + esc(nd.title || nd.id) + '</div>' +
           '<div class="lit3d-tip-sub">' + esc(nd.journal) + '　' + esc(nd.doi) + '</div>' +
           '<div class="lit3d-tip-meta">連到問題：' + esc(qs) +
           '<br>引用 ' + cites[i] + ' 篇' +
           '<br>本圖內被引 ' + (nd.cin || 0) + ' 次' + world + '</div>';
  }
  function placeTip(px, py){
    var sw = stage.clientWidth, sh = stage.clientHeight;
    var tw = tip.offsetWidth, th = tip.offsetHeight;
    var x = px + 14, y = py + 14;
    if (x + tw > sw - 8) x = px - 14 - tw;
    if (x < 8) x = Math.max(8, Math.min(sw - tw - 8, px - tw / 2));
    if (y + th > sh - 8) y = py - 14 - th;
    if (y < 8) y = 8;
    tip.style.left = Math.round(x) + "px";
    tip.style.top = Math.round(y) + "px";
  }
  function showTip(i, anchor, px, py){
    tip.innerHTML = tipHTML(i);
    tip.hidden = false;
    tipAnchor = anchor;
    placeTip(px, py);
  }
  function hideTip(){ tip.hidden = true; }

  /* ---- 命中判定：投影後 (半徑 + 6px) 內，重疊時取最近；半徑就是畫出來的那一顆（文獻點放大後也指得到）---- */
  function pick(px, py){
    var best = -1, bestDepth = Infinity;
    for (var i = 0; i < N; i++){
      var dx = px - sx[i], dy = py - sy[i];
      var lim = sr[i] + 6;
      if (dx * dx + dy * dy <= lim * lim && sd[i] < bestDepth){
        best = i; bestDepth = sd[i];
      }
    }
    return best;
  }
  function localPt(ev){
    var r = canvas.getBoundingClientRect();
    return [ev.clientX - r.left, ev.clientY - r.top];
  }

  /* ---- 指標互動 ---- */
  var pointers = {}, pinchDist = 0, pinchZoom = 1;
  canvas.addEventListener("pointerdown", function(ev){
    pointers[ev.pointerId] = ev;
    if (Object.keys(pointers).length === 2){
      var ps = [];
      for (var k in pointers) ps.push(pointers[k]);
      pinchDist = Math.hypot(ps[0].clientX - ps[1].clientX, ps[0].clientY - ps[1].clientY);
      pinchZoom = zoom;
      dragging = false;
      return;
    }
    dragging = true; moved = false;
    lastX = ev.clientX; lastY = ev.clientY;
    if (canvas.setPointerCapture) { try { canvas.setPointerCapture(ev.pointerId); } catch (x) {} }
    canvas.focus({ preventScroll:true });
  });
  canvas.addEventListener("pointermove", function(ev){
    if (pointers[ev.pointerId]) pointers[ev.pointerId] = ev;
    var ids = Object.keys(pointers);
    if (ids.length === 2 && pinchDist > 0){
      var a = pointers[ids[0]], b = pointers[ids[1]];
      var d = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
      zoom = Math.min(ZMAX, Math.max(ZMIN, pinchZoom * (d / pinchDist)));
      resumeAt = performance.now() + 3000;
      return;
    }
    if (dragging){
      var dx = ev.clientX - lastX, dy = ev.clientY - lastY;
      if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
      lastX = ev.clientX; lastY = ev.clientY;
      rotY += dx * 0.0072;
      rotX = Math.min(1.45, Math.max(-1.45, rotX + dy * 0.0072));
      return;
    }
    if (ev.pointerType === "mouse"){
      var p = localPt(ev);
      var hit = pick(p[0], p[1]);
      if (hit !== hoverIdx){
        hoverIdx = hit;
        if (hit >= 0 && pinIdx < 0) showTip(hit, "cursor", p[0], p[1]);
        else if (pinIdx < 0) hideTip();
      } else if (hit >= 0 && pinIdx < 0 && tipAnchor === "cursor"){
        placeTip(p[0], p[1]);
      }
    }
  });
  function endPointer(ev){
    delete pointers[ev.pointerId];
    if (Object.keys(pointers).length < 2) pinchDist = 0;
    if (!dragging) return;
    dragging = false;
    resumeAt = performance.now() + 3000;
    if (!moved && ev.pointerType !== "mouse"){
      var p = localPt(ev);
      var hit = pick(p[0], p[1]);
      if (hit >= 0){ pinIdx = hit; showTip(hit, "node", sx[hit], sy[hit]); }
      else { pinIdx = -1; hideTip(); }
    }
  }
  canvas.addEventListener("pointerup", endPointer);
  canvas.addEventListener("pointercancel", endPointer);
  canvas.addEventListener("pointerleave", function(ev){
    if (ev.pointerType === "mouse" && pinIdx < 0){ hoverIdx = -1; hideTip(); }
  });
  canvas.addEventListener("wheel", function(ev){
    ev.preventDefault();
    zoom = Math.min(ZMAX, Math.max(ZMIN, zoom * Math.exp(-ev.deltaY * 0.0016)));
  }, { passive:false });

  /* ---- 鍵盤 ---- */
  canvas.addEventListener("keydown", function(ev){
    var k = ev.key, used = true;
    if (k === "ArrowLeft") rotY -= 0.12;
    else if (k === "ArrowRight") rotY += 0.12;
    else if (k === "ArrowUp") rotX = Math.max(-1.45, rotX - 0.12);
    else if (k === "ArrowDown") rotX = Math.min(1.45, rotX + 0.12);
    else if (k === "+" || k === "=") zoom = Math.min(ZMAX, zoom * 1.12);
    else if (k === "-" || k === "_") zoom = Math.max(ZMIN, zoom / 1.12);
    else if (k === "Escape"){ pinIdx = -1; hoverIdx = -1; hideTip(); }
    else used = false;
    if (used){ ev.preventDefault(); resumeAt = performance.now() + 3000; }
  });

  /* ---- 對外：選一個點並釘住 tooltip（測試與之後的跨分頁跳轉用）---- */
  window.lit3dSelect = function(id){
    for (var i = 0; i < N; i++){
      if (NODES[i].id === id){
        pinIdx = i; hoverIdx = -1;
        resize();
        draw();
        showTip(i, "node", sx[i], sy[i]);
        return true;
      }
    }
    return false;
  };

  /* ---- 對外：讀一個點的刻度與投影幾何（只讀，測試用；頁面本身不呼叫）---- */
  window.lit3dProbe = function(id){
    for (var i = 0; i < N; i++){
      if (NODES[i].id !== id) continue;
      return {t: litTv[i], x: sx[i], y: sy[i], r: sr[i], depth: sd[i],
              q: NODES[i].q ? 1 : 0, cin: NODES[i].cin || 0,
              rq: R_Q, rl: R_LIT, gain: R_GAIN, cam: CAM, maxcin: MAXCIN};
    }
    return null;
  };
})();
"""


def _lit_tick_pos(v: int, max_cin: int) -> float:
    """刻度值在漸層條上的位置（0–1），和前端的 litT 同一條式子。"""
    return math.log(1 + v) / math.log(1 + max_cin) if max_cin > 0 else 0.0


def _lit_ticks(max_cin: int) -> list[int]:
    """圖例的對數刻度值：0 與最大值，再加上把 log(1+v) 切三等分的那兩個整數點。

    跨專案同一條規則，不設門檻、沒有逐專案設定；四捨五入後落在 0..max 之外或重複的就丟掉。
    例：max=12 → [0, 1, 5, 12]；max=2 → [0, 1, 2]；max=1 → [0, 1]；max=0 → [0]。
    """
    if max_cin <= 0:
        return [0]
    vals = {0, int(max_cin)}
    for k in (1, 2):
        v = int(round((1 + max_cin) ** (k / 3) - 1))
        if 0 <= v <= max_cin:
            vals.add(v)
    return sorted(vals)


def _literature_tab(ir: dict) -> list[str]:
    """第三個分頁「文獻」。缺檔或沒有可畫的點時只出一行說明，其他分頁不受影響。"""
    lit = ir.get('literature') or {}
    source = _h(lit.get('source') or LIT_REL)
    lines = ['<section id="tab-literature" hidden>', '<div class="lit3d-wrap">']
    if not lit.get('nodes'):
        why = '不存在' if not lit.get('present') else '沒有可畫的節點'
        lines += [f'<p class="lit3d-empty">尚無文獻引用資料（{source} {why}）</p>', '</div>', '</section>']
        return lines
    counts = lit.get('edges') or {}
    max_cin = lit.get('max_cin', 0)
    if lit.get('demo'):
        lines.append('<p class="lit3d-demo">示範資料：點與連線都是隨機產生的</p>')
    ticks = _lit_ticks(max_cin)
    marks = ''.join(
        '<b class="lit3d-tick{cls}" style="left:{pos:.2f}%"><i>{v}</i></b>'.format(
            cls=(' is-first' if i == 0 else (' is-last' if i == len(ticks) - 1 else '')),
            pos=_lit_tick_pos(v, max_cin) * 100, v=v)
        for i, v in enumerate(ticks))
    lines += [
        '<ul class="lit3d-legend">',
        '<li><span class="lit3d-dot is-q"></span>問題點</li>',
        '<li class="lit3d-scale">'
        '<span>文獻點的顏色與大小＝被本圖其他文獻引用的次數（對數刻度）</span>'
        '<span class="lit3d-scale-row"><span class="lit3d-dot is-lo"></span>'
        f'<span class="lit3d-ramp">{marks}</span>'
        '<span class="lit3d-dot is-hi"></span></span></li>',
        '<li><span class="lit3d-bar is-q"></span>文獻—問題</li>',
        '<li><span class="lit3d-bar is-c"></span>文獻引用文獻</li>',
        '</ul>',
        '<p class="lit3d-hint">拖曳旋轉・滾輪或雙指縮放・指到點看文獻・方向鍵旋轉、加減號縮放、Esc 取消選取</p>',
        '<div class="lit3d-stage" id="lit3d-stage">',
        '<canvas id="lit3d-canvas" class="lit3d-canvas" tabindex="0" role="img" '
        f'aria-label="文獻引用 3D 圖。文獻點的顏色越醒目、點畫得越大，代表被本圖其他文獻引用越多次，'
        f'從 0 次到 {max_cin} 次；刻度取對數，低次數之間分得比較開。'
        f'方向鍵旋轉，加減號縮放，Esc 取消選取。"></canvas>',
        '<div class="lit3d-tip" id="lit3d-tip" hidden></div>',
        '</div>',
        f'<p class="notice">來源：<code>{source}</code>；節點 {lit.get("nodes", 0)}、'
        f'文獻—問題 {counts.get("cited_for", 0)} 條、文獻引用文獻 {counts.get("cites", 0)} 條；'
        f'文獻點的顏色與大小都是圈內被引數（被本圖其他文獻引用的次數，最多 {max_cin} 次），刻度取對數。'
        f'版面座標由產生資料的腳本算好寫在 layout，本頁只讀不重算。</p>',
        '</div>',
        '</section>',
    ]
    return lines


STATE_SYMBOL = {'done': '●', 'expired': '◐', 'blocked': '✖', 'pending': '○', 'unknown': '◌', '': ''}


def _tw(text: str, size: float = 12.0) -> float:
    """粗估文字寬度（px）：CJK 一個字寬約等於字級，其餘約 0.57 倍。"""
    return sum(size if ord(ch) > 0x2E80 else size * 0.62 for ch in text)


def _fit(text: str, max_px: float, size: float = 12.0) -> str:
    if _tw(text, size) <= max_px:
        return text
    out = ''
    for ch in text:
        if _tw(out + ch + '…', size) > max_px:
            break
        out += ch
    return out + '…'


def _indent(n: dict) -> int:
    return SUB_INDENT_OF.get(n.get('subtype') or '', 0)


def _node_w(n: dict) -> int:
    return NODE_W - _indent(n)


def _num(v: float) -> str:
    """路徑座標：四捨五入到小數兩位，整數不帶小數（與 JS 端 String(Math.round(v*100)/100) 一致）。"""
    r = round(float(v), 2)
    return str(int(r)) if r == int(r) else repr(r)


def _l_path(a: dict, b: dict) -> str:
    """父→子的 L 形短線：從父節點左緣下方垂下，到子節點中線再右轉進子節點左緣（不走欄間走道、不占出入口）。"""
    x0 = a['x'] + 12
    y0 = a['y'] + NODE_H
    yc = b['y'] + NODE_H / 2
    x2 = b['x']
    r = min(6, max(0, (yc - y0) / 2), max(0, (x2 - x0) / 2))
    return f'M{_num(x0)},{_num(y0)} L{_num(x0)},{_num(yc - r)} Q{_num(x0)},{_num(yc)} {_num(x0 + r)},{_num(yc)} L{_num(x2)},{_num(yc)}'


SPINE_X = 12       # 對照短垂線的 x 偏移（相對節點左緣）；與 L 形線的垂直段同一條線
SPINE_LANE_GAP = 4  # 同欄多條對照線（或與別的群的 L 形線）垂直範圍重疊時，往左各錯開 4px 一道


def _spine_path(grp: dict, plan: dict, lane: int = 0) -> str:
    """敏感性分析群 → 所屬 plan 的敏感性對照短垂線：從群上緣 (x+12, y) 垂直向上到 plan 下緣 (x+12, y+NODE_H)，箭頭指向 plan；
    同欄、不走走道、不進 route_edges（經過中間節點時位於節點之下）。lane > 0 時往左錯開 lane × SPINE_LANE_GAP（見 spine_lanes）。
    與 GRAPH_JS 的 spinePath 同一套。"""
    dx = SPINE_X - lane * SPINE_LANE_GAP
    x0, y0 = grp['x'] + dx, grp['y']
    x1, y1 = plan['x'] + dx, plan['y'] + NODE_H
    if x0 == x1:
        return f'M{_num(x0)},{_num(y0)} V{_num(y1)}'
    return f'M{_num(x0)},{_num(y0)} L{_num(x1)},{_num(y1)}'


def spine_lanes(nodes: dict[str, dict], edges: list[tuple[int, dict]]) -> dict[int, int]:
    """同一欄的對照短垂線分道（與 GRAPH_JS 的 spineLanes 同一套、決定性）：每條線的垂直範圍 [plan 下緣, 群上緣]；
    L 形線的垂直段（群下緣 → 最後一個子節點的中線，x+12）固定占第 0 道；對照線依（群 y, 邊 idx）序取最小的一道，
    條件是該道上沒有範圍重疊（閉區間）的對照線、且第 0 道另要沒有範圍重疊的 L 形線區塊。回傳 {邊 idx: lane}。
    edges 為要畫的邊（含 sensitivity 與 supplements）。"""
    lblocks: dict[str, list[float]] = {}   # 群 id → [上緣, 下緣]（L 形線垂直段）
    for _i, e in edges:
        if e['type'] in L_EDGE_TYPES and e['from'] in nodes and e['to'] in nodes:
            a, b = nodes[e['from']], nodes[e['to']]
            yc = b['y'] + NODE_H / 2
            blk = lblocks.setdefault(e['from'], [a['y'] + NODE_H, yc])
            blk[1] = max(blk[1], yc)
    spines = []
    for i, e in edges:
        if e['type'] == 'supplements' and e['from'] in nodes and e['to'] in nodes:
            grp, plan = nodes[e['from']], nodes[e['to']]
            lo, hi = sorted((plan['y'] + NODE_H, grp['y']))
            spines.append((grp['y'], i, plan['col'], lo, hi))
    spines.sort()
    taken: list[tuple[int, int, float, float]] = []   # (col, lane, lo, hi)
    out: dict[int, int] = {}
    for _gy, i, col, lo, hi in spines:
        lane = 0
        while True:
            busy = any(c == col and ln == lane and not (hi < a or lo > b) for c, ln, a, b in taken)
            if lane == 0 and not busy:
                busy = any(nodes[g]['col'] == col and not (hi < a or lo > b) for g, (a, b) in lblocks.items())
            if not busy:
                break
            lane += 1
        taken.append((col, lane, lo, hi))
        out[i] = lane
    return out


LANE_GAP = 8
CORNER_R = 4
TRUNK_MAX_SIDE = int((0.8 * (COL_PITCH - NODE_W) / 2) // LANE_GAP)   # 走道寬 120 → 每側最多 6 條車道
TRUNK_MAX_LANES = 2 * TRUNK_MAX_SIDE + 1                             # 含中央共 13 條


def _gap_center(gap: int) -> float:
    return GRAPH_PAD + gap * COL_PITCH + NODE_W + (COL_PITCH - NODE_W) / 2


def _lane_x(gap: int, lane: int, n_lanes: int) -> float:
    """車道 x：全部用到的車道（n_lanes 條、超過上限時折回成 TRUNK_MAX_LANES 條）以 LANE_GAP 等距、置中於走道，x 隨車道索引單調遞增。"""
    n = min(n_lanes, TRUNK_MAX_LANES)
    return _gap_center(gap) + (lane % TRUNK_MAX_LANES - (n - 1) / 2) * LANE_GAP


def _bend_path(sx: float, sy: float, tx: float, ty: float, ex: float) -> str:
    """M 來源緣 H 幹線x V 目標y H 目標緣，兩個轉角 4px 圓角（與 GRAPH_JS 的 bendPath 同一套）。"""
    if ty == sy:
        return f'M{_num(sx)},{_num(sy)} H{_num(ex)}'
    d1 = 1 if tx > sx else -1
    v = 1 if ty > sy else -1
    d2 = 1 if ex > tx else -1
    r = min(CORNER_R, abs(ty - sy) / 2)
    return (f'M{_num(sx)},{_num(sy)} H{_num(tx - d1 * r)} Q{_num(tx)},{_num(sy)} {_num(tx)},{_num(sy + v * r)} '
            f'V{_num(ty - v * r)} Q{_num(tx)},{_num(ty)} {_num(tx + d2 * r)},{_num(ty)} H{_num(ex)}')


def _trunk_crossings(left: dict, right: dict) -> int:
    """left 幹線在左、right 在右時的交叉數：left 往右的橫段（分支）落在 right 的垂直開區間內，或 right 往左的橫段（來源出口）
    落在 left 的垂直開區間內。"""
    n = 0
    for y in left['right_ys']:
        if right['span'][0] < y < right['span'][1] or y in right['left_ys']:   # 同 y 的左右橫段共線相接也算
            n += 1
    for y in right['left_ys']:
        if left['span'][0] < y < left['span'][1]:
            n += 1
    return n


def _overlap(a: dict, b: dict) -> bool:
    return not (a['span'][1] < b['span'][0] or a['span'][0] > b['span'][1])


def _assign_lanes(keys: list[str], trunks: dict[str, dict]) -> dict[str, int]:
    """同一走道內的車道指派（C4；與 GRAPH_JS 的 assignLanes 同一套、決定性）：
    (1) 兩兩判定「必須在左」——垂直區間（閉區間）重疊的兩條幹線，比較兩種左右擺法的交叉數，少者為準；兩向都不交叉→無關係，
    兩向相同且都交叉→key 小者在左；(2) 對此關係做拓樸排序（可選時取 key 最小；成環時取剩餘中 key 最小者）；
    (3) 在此序下做區間著色：lane(k) = 1 + max(lane(j)) over 序在前且區間重疊的 j，沒有則 0。
    實作：(1) 以區間起點排序的掃描線只比較重疊的幹線對；(2) Kahn 拓樸排序（可用者以堆積取 key 最小、成環時以游標取剩餘最小）；
    (3) 只看 (1) 記下的重疊鄰居。結果與逐對比較版完全相同，幹線數 K 大時不再是 O(K²)。"""
    keys = sorted(keys)
    n = len(keys)
    span = [trunks[k]['span'] for k in keys]
    nbrs: list[list[int]] = [[] for _ in range(n)]
    pred: list[set[int]] = [set() for _ in range(n)]
    active: list[int] = []
    for i in sorted(range(n), key=lambda i_: (span[i_][0], i_)):
        s0 = span[i][0]
        active = [a for a in active if span[a][1] >= s0]   # 起點已排序：留下的都與 i 重疊（閉區間）
        for a in active:
            j, k = (a, i) if a < i else (i, a)
            cjk, ckj = _trunk_crossings(trunks[keys[j]], trunks[keys[k]]), _trunk_crossings(trunks[keys[k]], trunks[keys[j]])
            if cjk < ckj:
                pred[k].add(j)
            elif ckj < cjk:
                pred[j].add(k)
            elif cjk > 0:
                pred[k].add(j)
            nbrs[i].append(a)
            nbrs[a].append(i)
        active.append(i)
    succ: list[list[int]] = [[] for _ in range(n)]
    indeg = [0] * n
    for k in range(n):
        for j in pred[k]:
            succ[j].append(k)
        indeg[k] = len(pred[k])
    avail = [k for k in range(n) if indeg[k] == 0]
    heapq.heapify(avail)
    done = [False] * n
    order: list[int] = []
    cursor = 0
    while len(order) < n:
        if avail:
            p = heapq.heappop(avail)
            if done[p]:
                continue
        else:   # 成環：取剩餘中 key 最小者
            while done[cursor]:
                cursor += 1
            p = cursor
        done[p] = True
        order.append(p)
        for s in succ[p]:
            indeg[s] -= 1
            if indeg[s] == 0 and not done[s]:
                heapq.heappush(avail, s)
    posn = [0] * n
    for idx, k in enumerate(order):
        posn[k] = idx
    lane = [0] * n
    for k in order:
        lane[k] = max([lane[j] + 1 for j in nbrs[k] if posn[j] < posn[k]] + [0])
    return {keys[i]: lane[i] for i in range(n)}


def _dummy_node(col: int, y: float, idx: int) -> dict:
    return {'id': f'~{idx}@{col}', 'x': GRAPH_PAD + col * COL_PITCH, 'y': y, 'col': col, 'subtype': '', 'dummy': True}


def route_edges(nodes: dict[str, dict], edges: list[tuple[int, dict]]) -> dict:
    """同來源合併成幹線＋分支，走道分車道（與 GRAPH_JS 的 routeEdges 同一套演算法；決定性）。

    nodes: id → 節點（x／y／col／subtype）；edges: [(idx, edge)]（sensitivity 的 L 形線與 supplements 的對照短垂線由呼叫端另畫，
    這裡略過）。帶 `via`（[[col, y], …]，C2 的 dummy 列）的跳欄邊拆成逐欄段——每段的中繼端是一個寬 NODE_W 的隱形節點
    `~<idx>@<col>`，各段獨立走該走道的幹線／車道機制，整條邊輸出一條連續折線（段與段之間以水平線穿過 dummy 列）。
    步驟：(1) 每段依 (來源欄, 目標欄) 定方向與走道——正向走來源右側走道、反向走來源左側走道、同欄走右側走道；
    (2) 同 (來源, 目標欄, type, style, 方向) 併成一條幹線；(3) 出口：來源每側依幹線平均目標 y 排序均分；入口：目標每側依
    來源 y 排序均分；(4) 幹線只有一個目標且出口 y == 入口 y → 直線，不占車道；(5) 每個走道以 _assign_lanes 指派車道
    （必須在左關係 → 拓樸序 → 區間著色），車道 x 由左到右單調遞增、置中於走道，超過走道 80% 寬則折回重用並回報；
    (6) 每條邊輸出完整折線 d，每條幹線輸出「來源水平線＋垂直幹線」的 d；另回傳全部線段（供交叉計數）。
    回傳 {'paths': {idx: d}, 'trunk_of': {idx: 以空白分隔的幹線 key 或 ''}, 'trunks': [...], 'lane_max': {gap: 最大車道索引},
    'overflow': [gap], 'lines': [{'edge': idx 或 None, 'trunk': key 或 '', 'kind': ..., 'seg': ((x1, y1), (x2, y2))}]}。
    """
    def cy(n: dict) -> float:
        return n['y'] + NODE_H / 2

    def right(n: dict) -> float:
        return n['x'] + _node_w(n)

    segs: list[tuple[tuple[int, int], dict, dict, dict]] = []   # (segment id, edge, from node, to node)
    seg_count: dict[int, int] = {}
    pseudo: dict[str, dict] = {}
    for idx, e in edges:
        if e['type'] in L_EDGE_TYPES or e['type'] == 'supplements':
            continue
        chain = [nodes[e['from']]]
        for col, y in (e.get('via') or []):
            d = _dummy_node(int(col), y, idx)
            pseudo[d['id']] = d
            chain.append(d)
        chain.append(nodes[e['to']])
        seg_count[idx] = len(chain) - 1
        for k, (u, v) in enumerate(zip(chain, chain[1:])):
            segs.append(((idx, k), e, u, v))
    items: dict[tuple[int, int], dict] = {}
    members: dict[str, list[tuple[int, int]]] = {}
    for sid, e, a, b in segs:
        if a['col'] < b['col']:
            kind, gap = 'fwd', a['col']
        elif a['col'] > b['col']:
            kind, gap = 'back', a['col'] - 1
        else:
            kind, gap = 'same', a['col']
        key = f"{a['id']}|{b['col']}|{e['type']}|{e['style']}|{kind}"
        items[sid] = {'e': e, 'a': a, 'b': b, 'kind': kind, 'gap': gap, 'key': key}
        members.setdefault(key, []).append(sid)
    for key in members:
        members[key].sort()
    # 出口：來源每側（R＝正向與同欄、L＝反向）依幹線平均目標 y 排序
    src_side: dict[tuple[str, str], list[str]] = {}
    for key, ms in members.items():
        info = items[ms[0]]
        side = 'L' if info['kind'] == 'back' else 'R'
        src_side.setdefault((info['a']['id'], side), []).append(key)
    sy_of: dict[str, float] = {}
    for (sid_, _side), keys in src_side.items():
        keys.sort(key=lambda k: (round(sum(cy(items[i]['b']) for i in members[k]) / len(members[k]), 2), k))
        src = items[members[keys[0]][0]]['a']
        for k_i, k in enumerate(keys):
            sy_of[k] = round(src['y'] + NODE_H * (k_i + 1) / (len(keys) + 1), 2)
    # 入口：目標每側（L＝正向、R＝反向與同欄）依來源 y 排序
    dst_side: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for sid, info in items.items():
        side = 'L' if info['kind'] == 'fwd' else 'R'
        dst_side.setdefault((info['b']['id'], side), []).append(sid)
    ty_of: dict[tuple[int, int], float] = {}
    for (_tid, _side), sids in dst_side.items():
        sids.sort(key=lambda i: (cy(items[i]['a']), i))
        tgt = items[sids[0]]['b']
        for k_i, i in enumerate(sids):
            ty_of[i] = round(tgt['y'] + NODE_H * (k_i + 1) / (len(sids) + 1), 2)
    # 幹線：直線判定、垂直區間、左右橫段 y（供車道指派的交叉判定）
    trunks: dict[str, dict] = {}
    for key, ms in members.items():
        info = items[ms[0]]
        sy = sy_of[key]
        tys = [ty_of[i] for i in ms]
        direct = len(ms) == 1 and info['kind'] != 'same' and sy == tys[0]
        if info['kind'] == 'fwd':
            left_ys, right_ys = [sy], list(tys)
        elif info['kind'] == 'back':
            left_ys, right_ys = list(tys), [sy]
        else:
            left_ys, right_ys = [sy] + list(tys), []
        trunks[key] = {'gap': info['gap'], 'kind': info['kind'], 'sy': sy, 'span': (min([sy] + tys), max([sy] + tys)),
                       'direct': direct, 'src': info['a']['id'], 'type': info['e']['type'], 'style': info['e']['style'],
                       'left_ys': left_ys, 'right_ys': right_ys}
    # 車道：每個走道各自指派
    lane_of: dict[str, int] = {}
    lane_max: dict[int, int] = {}
    n_lanes: dict[int, int] = {}
    overflow: list[int] = []
    by_gap: dict[int, list[str]] = {}
    for key, t in trunks.items():
        if not t['direct']:
            by_gap.setdefault(t['gap'], []).append(key)
    for gap in sorted(by_gap):
        lanes = _assign_lanes(by_gap[gap], trunks)
        lane_of.update(lanes)
        lane_max[gap] = max(lanes.values())
        n_lanes[gap] = lane_max[gap] + 1
        if n_lanes[gap] > TRUNK_MAX_LANES:
            overflow.append(gap)
    # 路徑（逐段），再把同一條邊的段接成一條折線
    seg_path: dict[tuple[int, int], str] = {}
    seg_trunk: dict[tuple[int, int], str] = {}
    trunk_out: list[dict] = []
    lines: list[dict] = []
    for key, t in trunks.items():
        ms = members[key]
        src = items[ms[0]]['a']
        sx = src['x'] if t['kind'] == 'back' else right(src)
        sy = t['sy']
        if t['direct']:
            i = ms[0]
            b = items[i]['b']
            ex = b['x'] if t['kind'] == 'fwd' else right(b)
            seg_path[i] = f'M{_num(sx)},{_num(sy)} L{_num(ex)},{_num(ty_of[i])}'
            seg_trunk[i] = ''
            lines.append({'edge': i[0], 'trunk': '', 'kind': 'direct', 'type': t['type'], 'seg': ((sx, sy), (ex, ty_of[i]))})
            continue
        lane = lane_of[key]
        tx = _lane_x(t['gap'], lane, n_lanes[t['gap']])
        for i in ms:
            b = items[i]['b']
            ex = b['x'] if t['kind'] == 'fwd' else right(b)
            seg_path[i] = _bend_path(sx, sy, tx, ty_of[i], ex)
            seg_trunk[i] = key
            lines.append({'edge': i[0], 'trunk': key, 'kind': 'branch', 'type': t['type'], 'seg': ((tx, ty_of[i]), (ex, ty_of[i]))})
        s0, s1 = t['span']
        lines.append({'edge': None, 'trunk': key, 'kind': 'stub', 'type': t['type'], 'seg': ((sx, sy), (tx, sy))})
        lines.append({'edge': None, 'trunk': key, 'kind': 'vertical', 'type': t['type'], 'seg': ((tx, s0), (tx, s1))})
        trunk_out.append({'key': key, 'src': t['src'], 'gap': t['gap'], 'lane': lane, 'span': [s0, s1], 'type': t['type'],
                          'style': t['style'], 'd': f'M{_num(sx)},{_num(sy)} H{_num(tx)} M{_num(tx)},{_num(s0)} V{_num(s1)}'})
    trunk_out.sort(key=lambda t: t['key'])
    paths: dict[int, str] = {}
    trunk_of: dict[int, str] = {}
    for idx, n_seg in seg_count.items():
        d = seg_path[(idx, 0)]
        keys_used = [seg_trunk[(idx, 0)]] if seg_trunk[(idx, 0)] else []
        for k in range(1, n_seg):
            b = items[(idx, k - 1)]['b']            # 上一段的目標＝這一段的來源 dummy：水平線穿過 dummy 列
            xr = right(b)
            d += f' H{_num(xr)} ' + seg_path[(idx, k)].split(' ', 1)[1]
            lines.append({'edge': idx, 'trunk': '', 'kind': 'dummy', 'type': items[(idx, k)]['e']['type'],
                          'seg': ((b['x'], ty_of[(idx, k - 1)]), (xr, ty_of[(idx, k - 1)]))})
            if seg_trunk[(idx, k)]:
                keys_used.append(seg_trunk[(idx, k)])
        paths[idx] = d
        trunk_of[idx] = ' '.join(keys_used)
    return {'paths': paths, 'trunk_of': trunk_of, 'trunks': trunk_out, 'lane_max': lane_max, 'overflow': overflow, 'lines': lines}


def _seg_cross(p: tuple, q: tuple) -> bool:
    """兩線段是否「真正交叉」：內部相交（共端點、只在端點相碰的 T 形不算），或共線且重疊長度 > 0。"""
    (ax, ay), (bx, by) = p
    (cx, cy_), (dx, dy) = q

    def orient(ox, oy, px_, py_, qx, qy):
        v = (px_ - ox) * (qy - oy) - (py_ - oy) * (qx - ox)
        return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)

    o1, o2 = orient(ax, ay, bx, by, cx, cy_), orient(ax, ay, bx, by, dx, dy)
    o3, o4 = orient(cx, cy_, dx, dy, ax, ay), orient(cx, cy_, dx, dy, bx, by)
    if o1 * o2 < 0 and o3 * o4 < 0:
        return True
    if o1 == 0 and o2 == 0 and o3 == 0 and o4 == 0:   # 共線：投影到主軸看重疊長度
        if abs(bx - ax) + abs(dx - cx) >= abs(by - ay) + abs(dy - cy_):
            lo, hi = max(min(ax, bx), min(cx, dx)), min(max(ax, bx), max(cx, dx))
        else:
            lo, hi = max(min(ay, by), min(cy_, dy)), min(max(ay, by), max(cy_, dy))
        return hi - lo > 1e-9
    return False


def _seg_in_rect(seg: tuple, x: float, y: float, w: float, h: float) -> bool:
    """線段是否穿過矩形內部（開區域；只沿邊緣或只碰到邊緣不算）。"""
    (ax, ay), (bx, by) = seg
    t0, t1 = 0.0, 1.0
    dx, dy = bx - ax, by - ay
    for pnum, qden in ((-dx, ax - x), (dx, x + w - ax), (-dy, ay - y), (dy, y + h - ay)):
        if abs(pnum) < 1e-9:
            if qden <= 1e-9:
                return False
            continue
        t = qden / pnum
        if pnum < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 >= t1 - 1e-9:
            return False
    return (t1 - t0) * (abs(dx) + abs(dy)) > 1e-6


def default_view_lines(by_id: dict[str, dict], edges: list[dict], route: dict) -> list[dict]:
    """預設檢視的全部可見線段：route_edges 的幹線出口／垂直／分支／直線／dummy 段，加上 sensitivity 的 L 形線與 supplements 的
    對照短垂線（後兩者從 path 座標拆成直線段）。"""
    lines = list(route['lines'])
    shown_edges = [(i, e) for i, e in enumerate(edges) if e['default_visible'] and e['from'] in by_id and e['to'] in by_id]
    lanes = spine_lanes(by_id, shown_edges)
    for i, e in shown_edges:
        a, b = by_id[e['from']], by_id[e['to']]
        if e['type'] in L_EDGE_TYPES:   # 同一父節點的 L 形線共用垂直段，視同同一幹線（群 → 子分析、主結果 → 支撐結果）
            x0, y0, yc, x2 = a['x'] + SPINE_X, a['y'] + NODE_H, b['y'] + NODE_H / 2, b['x']
            lines.append({'edge': i, 'trunk': 'L:' + e['from'], 'kind': 'lshape', 'type': e['type'], 'seg': ((x0, y0), (x0, yc))})
            lines.append({'edge': i, 'trunk': 'L:' + e['from'], 'kind': 'lshape', 'type': e['type'], 'seg': ((x0, yc), (x2, yc))})
        elif e['type'] == 'supplements':
            dx = SPINE_X - lanes.get(i, 0) * SPINE_LANE_GAP
            lines.append({'edge': i, 'trunk': '', 'kind': 'spine', 'type': e['type'],
                          'seg': ((a['x'] + dx, a['y']), (b['x'] + dx, b['y'] + NODE_H))})
    return lines


def _region_of(seg: tuple) -> int:
    """線段所在的水平區域（同一區域內才可能相交）：偶數 2c＝欄 c 的節點區、奇數 2c+1＝欄 c 右側的走道；跨區域的線段回 -1。"""
    (ax, _ay), (bx, _by) = seg
    lo, hi = min(ax, bx), max(ax, bx)
    ra = int((lo - GRAPH_PAD) // COL_PITCH)
    ra = 2 * ra + (1 if lo - GRAPH_PAD - ra * COL_PITCH >= NODE_W else 0)
    hi_adj = hi - 1e-6 if hi > lo else hi
    rb = int((hi_adj - GRAPH_PAD) // COL_PITCH)
    rb = 2 * rb + (1 if hi_adj - GRAPH_PAD - rb * COL_PITCH >= NODE_W else 0)
    return ra if ra == rb else -1


_SEG_EPS = 1e-6


def _group_crossing_pairs(r_lines: list[dict], cross_pair) -> list[tuple[int, int]]:
    """同一組線段內全部「真正交叉」的線段對 (i, j)（i < j 為在 r_lines 內的索引）。候選對以軸對齊索引產生——水平 × 垂直：水平線依 y
    排序、每條垂直線二分取 y 在其區間內者再看 x；同 y 的水平線／同 x 的垂直線：排序後掃描重疊；斜線：外框篩選——再以 cross_pair
    精確判定，與逐對比較的結果相同。"""
    hs: list[tuple[float, float, float, int]] = []
    vs: list[tuple[float, float, float, int]] = []
    ds: list[tuple[float, float, float, float, int]] = []
    for idx, ln in enumerate(r_lines):
        (ax, ay), (bx, by) = ln['seg']
        if abs(ay - by) < 1e-9:
            hs.append((ay, min(ax, bx), max(ax, bx), idx))
        elif abs(ax - bx) < 1e-9:
            vs.append((ax, min(ay, by), max(ay, by), idx))
        else:
            ds.append((min(ax, bx), max(ax, bx), min(ay, by), max(ay, by), idx))
    hs.sort()
    vs.sort()
    h_ys = [h[0] for h in hs]
    v_xs = [v[0] for v in vs]
    found: list[tuple[int, int]] = []

    def hit(a: int, b: int) -> None:
        if a > b:
            a, b = b, a
        if cross_pair(r_lines[a], r_lines[b]):
            found.append((a, b))

    for vx, vy0, vy1, vi in vs:   # 水平 × 垂直
        for t in range(bisect.bisect_left(h_ys, vy0 - _SEG_EPS), bisect.bisect_right(h_ys, vy1 + _SEG_EPS)):
            _hy, hx0, hx1, hi = hs[t]
            if hx0 - _SEG_EPS <= vx <= hx1 + _SEG_EPS:
                hit(hi, vi)
    i = 0
    while i < len(hs):   # 同 y 的水平線：共線重疊
        j = i
        while j < len(hs) and abs(hs[j][0] - hs[i][0]) < 1e-9:
            j += 1
        act: list[tuple[float, float, int]] = []
        for t in range(i, j):
            _hy, x0, x1, idx = hs[t]
            act = [o for o in act if o[1] >= x0 - _SEG_EPS]
            for _o0, _o1, oidx in act:
                hit(oidx, idx)
            act.append((x0, x1, idx))
        i = j
    i = 0
    while i < len(vs):   # 同 x 的垂直線：共線重疊
        j = i
        while j < len(vs) and abs(vs[j][0] - vs[i][0]) < 1e-9:
            j += 1
        act = []
        for t in range(i, j):
            _vx, y0, y1, idx = vs[t]
            act = [o for o in act if o[1] >= y0 - _SEG_EPS]
            for _o0, _o1, oidx in act:
                hit(oidx, idx)
            act.append((y0, y1, idx))
        i = j
    for di, (x0, x1, y0, y1, idx) in enumerate(ds):   # 斜線：外框篩選
        for t in range(bisect.bisect_left(h_ys, y0 - _SEG_EPS), bisect.bisect_right(h_ys, y1 + _SEG_EPS)):
            _hy, hx0, hx1, hi = hs[t]
            if hx1 >= x0 - _SEG_EPS and hx0 <= x1 + _SEG_EPS:
                hit(hi, idx)
        for t in range(bisect.bisect_left(v_xs, x0 - _SEG_EPS), bisect.bisect_right(v_xs, x1 + _SEG_EPS)):
            _vx, vy0, vy1, vi = vs[t]
            if vy1 >= y0 - _SEG_EPS and vy0 <= y1 + _SEG_EPS:
                hit(vi, idx)
        for ox0, ox1, oy0, oy1, oidx in ds[di + 1:]:
            if ox1 >= x0 - _SEG_EPS and ox0 <= x1 + _SEG_EPS and oy1 >= y0 - _SEG_EPS and oy0 <= y1 + _SEG_EPS:
                hit(oidx, idx)
    return found


def crossing_stats(by_id: dict[str, dict], shown: set[str], lines: list[dict], count_overlaps: bool = True) -> tuple[int, list[str], int]:
    """(C5) 精確線段相交計數：共端點不算、同一條邊自己的段不算、同一幹線的段彼此不算、只在端點相碰不算。
    另算線段穿過可見節點矩形的次數（對照短垂線刻意從中間節點底下經過，不計）。回傳 (交叉數, 前 10 對的描述, 穿過節點數)。
    候選對由 _group_crossing_pairs 以索引產生（不再逐對比較）；跨區域的線段與每個區域的線段比、彼此只在第一個區域比一次，
    最後再與逐對版相同地另計一次跨區域線段彼此的交叉。"""
    def desc(ln: dict) -> str:
        return f'{ln["edge"] if ln["edge"] is not None else "-"}:{ln["type"]}:{ln["kind"]}'

    crossings = 0
    pairs: list[str] = []
    groups: dict[int, list[dict]] = {}
    spanning: list[dict] = []
    for ln in lines:
        r = _region_of(ln['seg'])
        if r < 0:
            spanning.append(ln)
        else:
            groups.setdefault(r, []).append(ln)

    def cross_pair(li: dict, lj: dict) -> bool:
        if li['edge'] is not None and li['edge'] == lj['edge']:
            return False
        if li['trunk'] and li['trunk'] == lj['trunk']:
            return False
        return _seg_cross(li['seg'], lj['seg'])

    first = True
    for r in sorted(groups):
        r_lines = groups[r] + spanning
        n_reg = len(groups[r])
        found = _group_crossing_pairs(r_lines, cross_pair)
        if not first:
            found = [(a, b) for a, b in found if a < n_reg]
        first = False
        crossings += len(found)
        if len(pairs) < 10:
            for a, b in sorted(found)[:10 - len(pairs)]:
                pairs.append(f'{desc(r_lines[a])} × {desc(r_lines[b])}')
    found = _group_crossing_pairs(spanning, cross_pair)
    crossings += len(found)
    if len(pairs) < 10:
        for a, b in sorted(found)[:10 - len(pairs)]:
            pairs.append(f'{desc(spanning[a])} × {desc(spanning[b])}')
    overlaps = 0
    if count_overlaps:
        by_col: dict[int, list[tuple[float, float, int, int]]] = {}
        for nid, n in by_id.items():
            if nid in shown:
                by_col.setdefault(int((n['x'] - GRAPH_PAD) // COL_PITCH), []).append((n['y'], n['x'], _node_w(n), NODE_H))
        for rs in by_col.values():
            rs.sort()
        col_ys = {c: [r_[0] for r_ in rs] for c, rs in by_col.items()}
        for ln in lines:
            if ln['kind'] == 'spine':
                continue
            (ax, ay), (bx, by) = ln['seg']
            lx0, lx1, ly0, ly1 = min(ax, bx), max(ax, bx), min(ay, by), max(ay, by)
            c_lo = int(math.floor((lx0 - NODE_W - GRAPH_PAD) / COL_PITCH)) - 1
            c_hi = int(math.floor((lx1 - GRAPH_PAD) / COL_PITCH)) + 1
            for c in range(c_lo, c_hi + 1):
                rs = by_col.get(c)
                if not rs:
                    continue
                ys = col_ys[c]
                for t in range(bisect.bisect_left(ys, ly0 - NODE_H - _SEG_EPS), bisect.bisect_right(ys, ly1 + _SEG_EPS)):
                    y, x, w, h = rs[t]
                    if _seg_in_rect(ln['seg'], x, y, w, h):
                        overlaps += 1
    return crossings, pairs, overlaps


def _default_route(graph: dict) -> tuple[dict, set[str], list[int]]:
    """預設檢視：可見節點集合、預設畫出的邊 idx、route_edges 結果（build_graph 算 stats 與 _svg_graph 畫圖共用；決定性）。"""
    nodes = graph['nodes']
    by_id = {n['id']: n for n in nodes}
    shown = {n['id'] for n in nodes if not n['collapsed'] and n['type'] != 'decision'}
    drawn = [i for i, e in enumerate(graph['edges']) if e['default_visible'] and e['from'] in shown and e['to'] in shown]
    return route_edges(by_id, [(i, graph['edges'][i]) for i in drawn]), shown, drawn


def _strip_lines_svg(strips: list[dict], width: int) -> str:
    """0.18.1 問題帶分隔：同一區帶內相鄰兩條帶之間各一條淡色細線（在空隙正中），第一條帶之前、區帶標題列之後不畫、也不加標題；
    `<g id="graph-strips">` 由 JS relayout() 整組重建（帶數在暫存後可能改變）。"""
    parts = ['<g id="graph-strips">']
    prev: dict | None = None
    for s in strips:
        if prev is not None and prev['band'] == s['band']:
            y = (prev['y1'] + s['y0']) / 2
            parts.append(f'<line class="strip-divider" data-band="{s["band"]}" data-strip="{_h(s["question"])}" x1="{GRAPH_PAD}" y1="{y:g}" '
                         f'x2="{width - GRAPH_PAD}" y2="{y:g}"></line>')
        prev = s
    parts.append('</g>')
    return ''.join(parts)


def _svg_graph(graph: dict, notes: list[str] | None = None) -> str:
    nodes = graph['nodes']
    by_id = {n['id']: n for n in nodes}
    route, shown, drawn = _default_route(graph)
    drawn_set = set(drawn)
    hidden_route = route_edges(by_id, [(i, dict(e, via=[])) for i, e in enumerate(graph['edges']) if i not in drawn_set])
    for gap in route['overflow']:
        if notes is not None:
            notes.append(f'關聯圖走道 {gap} 的幹線超過 {TRUNK_MAX_LANES} 條車道，折回重用')
    vis_nodes = [n for n in nodes if n['id'] in shown]
    dummy_rows: dict[str, list[float]] = {}
    for i in drawn:
        e = graph['edges'][i]
        for _col, y in e.get('via') or []:
            dummy_rows.setdefault(by_id[e['to']]['band'], []).append(y)
    width = int(max([n['x'] for n in nodes] + [0]) + NODE_W + GRAPH_PAD)
    height = int(max([n['y'] for n in vis_nodes] + [y for ys in dummy_rows.values() for y in ys] + [0]) + NODE_H + GRAPH_PAD)
    frame = band_frame(nodes, shown, dummy_rows)
    out = [f'<svg id="graph-svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="關聯圖">',
           '<defs>']
    for mid, cls in (('arrow', 'arrow-default'), ('arrow-up', 'arrow-up'), ('arrow-down', 'arrow-down'), ('arrow-path', 'arrow-path'),
                     ('arrow-method', 'arrow-method')):
        out.append(f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                   f'<path class="{cls}" d="M0,0 L10,5 L0,10 z"></path></marker>')
    # 區帶：每個區帶一條分隔線＋一個標題（main 的分隔線永遠 off；沒有可見節點的區帶兩者都 off）；main 以外都沒有可見節點時整組 off
    # （JS 展開舊版後若其他區帶出現節點會再打開並重算 y）
    parts = [f'<g id="graph-bands" class="bands{"" if frame["has_other"] else " off"}">']
    for b in BANDS:
        div_off = ' off' if (b == 'main' or not frame['has'][b]) else ''
        title_off = ' off' if (b != 'main' and not frame['has'][b]) else ''
        parts.append(f'<line class="band-divider{div_off}" data-band="{b}" x1="{GRAPH_PAD}" y1="{frame["y_div"][b]:g}" '
                     f'x2="{width - GRAPH_PAD}" y2="{frame["y_div"][b]:g}"></line>'
                     f'<text class="band-title{title_off}" data-band="{b}" x="{GRAPH_PAD}" y="{frame["y_title"][b] + BAND_TITLE_DY:g}">'
                     f'{_h(BAND_TITLE[b])}</text>')
    parts.append('</g>' + _strip_lines_svg(graph.get('strips') or [], width) + '<g id="graph-trunks">')
    out.append('</defs><g id="graph-root">' + ''.join(parts))
    for t in route['trunks']:
        out.append(f'<path class="trunk e-{t["type"]} st-{t["style"]}" data-trunk="{_h(t["key"])}" data-gap="{t["gap"]}" data-lane="{t["lane"]}" d="{t["d"]}"></path>')
    out.append('</g><g id="graph-edges">')
    lanes = spine_lanes(by_id, [(i, graph['edges'][i]) for i in drawn])
    for i, e in enumerate(graph['edges']):
        a, b = by_id[e['from']], by_id[e['to']]
        if e['type'] in L_EDGE_TYPES:
            d = _l_path(a, b)
            trunk = ''
        elif e['type'] == 'supplements':
            d = _spine_path(a, b, lanes.get(i, 0))
            trunk = ''
        elif i in drawn_set:
            d = route['paths'][i]
            trunk = route['trunk_of'][i]
        else:
            d = hidden_route['paths'].get(i, '')
            trunk = ''
        off = '' if i in drawn_set else ' off'
        dec = ' dec' if a['type'] == 'decision' or b['type'] == 'decision' else ''
        title = f'{e["type"]}{"（" + e["label"] + "）" if e["label"] else ""}：{e["source"]}'
        out.append(f'<path class="edge e-{e["type"]} st-{e["style"]}{dec}{off}" data-idx="{i}" data-from="{_h(e["from"])}" '
                   f'data-to="{_h(e["to"])}" data-type="{e["type"]}"' + (f' data-trunk="{_h(trunk)}"' if trunk else '') +
                   f' d="{d}"><title>{_h(title)}</title></path>')
    out.append('</g><g id="graph-nodes">')
    for n in nodes:
        gone = ' gone' if n['id'] not in shown else ''
        dec = ' dec' if n['type'] == 'decision' else ''
        sub = _indent(n) > 0
        w = _node_w(n)
        state_zh = STATE_ZH.get(n['state'], '—') if n['state'] else '—'
        st_w = _tw(state_zh, 11)
        unval = n['type'] == 'result' and n['meta'].get('validated') is False and n.get('subtype') != 'secondary_group'   # 聚合節點以徽章「未驗證 n」呈現
        unval_w = _tw('未驗證', 11) + 6 if unval else 0
        badge_w = _tw(n['badge'], 10) + 6 if n['badge'] else 0
        label_max = w - 30 - st_w - unval_w - 8 - badge_w - 8
        label = _fit(n['label'], label_max, 11 if sub else 12)
        if n['type'] == 'method' and label.endswith('…') and ' ｜ ' in n['label']:
            # 0.18.0：plan 徽章變長（「v15（14 舊版）｜敏感性 5」）時先捨 model 部分、保住 plan id（「SQ5-v15」比「SQ5-v1…」有用）
            label = _fit(n['label'].split(' ｜ ')[0], label_max, 11 if sub else 12)
        st_x = w - 8
        unval_x = st_x - st_w - 6
        badge_x = (unval_x - unval_w + 6 if unval else st_x - st_w) - 6
        cls = f'gnode t-{n["type"]} s-{n["state"] or "none"}{" sub" if sub else ""}{dec}{gone}'
        out.append(f'<g class="{cls}" data-node-id="{_h(n["id"])}" data-type="{n["type"]}" data-state="{n["state"]}" '
                   f'data-col="{n["col"]}" data-order="{n["order"]}" data-band="{n["band"]}"' + (f' data-parent="{_h(n["parent"])}"' if n.get('parent') else '') +
                   (f' data-strip="{_h(n.get("strip", ""))}"' if n['type'] != 'decision' else '') +
                   f' transform="translate({n["x"]:g},{n["y"]:g})" tabindex="0">'
                   f'<rect class="box" width="{w}" height="{NODE_H}" rx="6"></rect>'
                   f'<rect class="tbar" x="3" y="3" width="5" height="{NODE_H - 6}" rx="2"></rect>'
                   f'<text class="sym" x="13" y="24">{_h(STATE_SYMBOL.get(n["state"], ""))}</text>'
                   f'<text class="lbl" x="30" y="23">{_h(label)}</text>'
                   + (f'<text class="badge" x="{badge_x:g}" y="23" text-anchor="end">{_h(n["badge"])}</text>' if n['badge'] else '')
                   + (f'<text class="st unval" x="{unval_x:g}" y="23" text-anchor="end">未驗證</text>' if unval else '')
                   + f'<text class="st" x="{st_x}" y="23" text-anchor="end">{_h(state_zh)}</text>'
                   f'<title>{_h(n["title"] or n["label"])}</title></g>')
    out.append('</g><g id="drag-preview"></g></g></svg>')   # 拖曳時的即時接線預覽：Python 只出空骨架，JS 畫、不進 IR 與 SSOT
    return '\n'.join(out)


# ---------- 投稿檔案分頁（第四個分頁；0.22.0） ----------
# 版面沿用關聯圖既有的排版引擎：欄距／列距／區帶框架（band_frame）、走道車道與幹線合併（route_edges）、
# 跳欄借一列 dummy 穿過、交叉計數（crossing_stats）都是同一套，不另寫第二份。
# 欄序由左到右固定四欄：資料 → 程式碼 → 結果 → 圖表；區帶由上而下 Main → Extended Data → Supplementary。

SUB_COLS = (('data', '資料'), ('code', '程式碼'), ('result', '結果'), ('figure', '圖表'))
SUB_COL_OF = {'data': 0, 'code': 1, 'result': 2, 'other': 2, 'figure': 3}
SUB_CHILD_SUBTYPE = 'secondary'   # 只借 SUB_INDENT_OF 的縮排寬度，與關聯圖的次要結果無關
SUB_BADGE_SHORT = {'缺檔': '缺檔', 'root 外': 'root 外', '手動加入': '手動', '已移除': '已移除',
                   'historical': 'historical', 'run 資料夾不存在': 'run 缺'}
SUB_SWEEPS = 8            # barycenter 往返掃描輪數（掃描便宜，節點數在千位以下）
SUB_FIG_FIELDS = ('files', 'script', 'values_snapshot', 'registered_sources', 'unregistered_sources')
RUNS_DIR_PREFIX = 'analysis/runs/'   # 資料檔 → 所屬 run 的 scripts 節點（只做顯示用的連線，衍生規則不在這裡）
SUB_BAND_TITLE = {b: BAND_TITLE[b].split('：')[0] for b in BANDS}   # 沿用關聯圖的帶標籤（去掉關聯圖專屬的補述）


def _sub_node(nid: str, kind: str, col: int, band: str, label: str, *, parent: str = '',
              entry: str = '', ref: str = '') -> dict:
    return {'id': nid, 'kind': kind, 'col': col, 'band': band, 'label': label, 'parent': parent,
            'subtype': SUB_CHILD_SUBTYPE if parent else '', 'entry': entry, 'ref': ref,
            'x': 0.0, 'y': 0.0, 'order': 0, 'type': kind}


def _sub_label(node: dict) -> str:
    """檔案節點的顯示名：檔名（資料夾補「/」）；同名檔多時補上一層資料夾。"""
    name = node['path'].rstrip('/').rsplit('/', 1)[-1] or node['path']
    return name + '/' if node['is_dir'] else name


def _sub_badges(node: dict, hist: bool) -> list[str]:
    out = [SUB_BADGE_SHORT.get(b, b) for b in node['badges']]
    if hist and 'historical' not in out:
        out.append('historical')
    return out


SUB_FAN_MIN = 3   # 同一個目標、同一個走道的邊到幾條才收束成扇形（2 條分開畫還看得清）


def _sub_fan(nodes: dict[str, dict], edges: list[dict]) -> dict:
    """多對一的扇形收束：同一個目標、同一個走道的邊（≥ SUB_FAN_MIN 條）合成一條共用垂直線＋逐來源水平線。

    route_edges 的幹線是按「同一個來源」合併的（扇出）；扇入沒有東西可合，幾十條線各佔一條車道就會互相交叉上千次
    （一個 run 的 input_snapshot 動輒幾十個資料檔，全部指向同一個 scripts/ 節點）。這裡自己畫：走道裡一條共用垂直線，
    每個來源一段水平線接上去，最後一段水平線進目標。水平線只在端點碰到垂直線，不算交叉。
    回 {'paths': {edge idx: d}, 'spines': [{'d', 'type', 'style', 'key'}], 'lines': [...], 'handled': {idx}}。
    """
    def cy(n: dict) -> float:
        return n['y'] + NODE_H / 2

    groups: dict[int, list[tuple[tuple, list[int]]]] = {}
    cand: dict[tuple, list[int]] = {}
    for i, e in enumerate(edges):
        a, b = nodes[e['from']], nodes[e['to']]
        if b['col'] - a['col'] != 1:
            continue
        cand.setdefault((a['col'], e['to'], e['type'], e['style']), []).append(i)
    def span(key: tuple) -> tuple:
        ys = [cy(nodes[edges[i]['from']]) for i in cand[key]] + [cy(nodes[key[1]])]
        return (round((min(ys) + max(ys)) / 2, 2), round(max(ys) - min(ys), 2), key[1])

    # 車道由左到右依「這一束的 y 中心」排：y 範圍互不重疊的束彼此不會交叉，重疊的也讓包住別人的那一束靠右
    for key in sorted(cand, key=span):
        if len(cand[key]) >= SUB_FAN_MIN:
            groups.setdefault(key[0], []).append((key, cand[key]))
    paths: dict[int, str] = {}
    spines: list[dict] = []
    lines: list[dict] = []
    handled: set[int] = set()
    for gap, items in sorted(groups.items()):
        for lane, (key, idxs) in enumerate(items):
            x = _lane_x(gap, lane, len(items))
            tgt = nodes[key[1]]
            ty = cy(tgt)
            ys = [cy(nodes[edges[i]['from']]) for i in idxs] + [ty]
            key_s = f'fan|{key[0]}|{key[1]}|{key[2]}|{key[3]}'
            spines.append({'d': f'M{_num(x)},{_num(min(ys))} L{_num(x)},{_num(max(ys))}',
                           'type': key[2], 'style': key[3], 'key': key_s})
            lines.append({'edge': None, 'trunk': key_s, 'kind': 'vertical', 'type': key[2],
                          'seg': ((x, min(ys)), (x, max(ys)))})
            lines.append({'edge': None, 'trunk': key_s, 'kind': 'stub', 'type': key[2],
                          'seg': ((x, ty), (tgt['x'], ty))})
            spines.append({'d': f'M{_num(x)},{_num(ty)} L{_num(tgt["x"])},{_num(ty)}',
                           'type': key[2], 'style': key[3], 'key': key_s, 'head': True})
            for i in idxs:
                src = nodes[edges[i]['from']]
                sx, sy = src['x'] + _node_w(src), cy(src)
                paths[i] = f'M{_num(sx)},{_num(sy)} L{_num(x)},{_num(sy)}'
                lines.append({'edge': i, 'trunk': key_s, 'kind': 'stub', 'type': key[2],
                              'seg': ((sx, sy), (x, sy))})
                handled.add(i)
    return {'paths': paths, 'spines': spines, 'lines': lines, 'handled': handled}


def _sub_primary_code(code: list[str], nodes: dict[str, dict]) -> str:
    """一個入口的代表腳本節點：優先 run 的 `scripts/` 資料夾，其次路徑最前面的那一支。"""
    if not code:
        return ''
    dirs = sorted(x for x in code if nodes[x]['is_dir'])
    return dirs[0] if dirs else sorted(code)[0]


def _sub_run_scripts(node: dict, nodes: dict[str, dict]) -> str:
    """資料檔所屬 run 的 scripts 節點（從自己的路徑或被追到的欄位裡取 run 名）；沒有就回空字串。"""
    cands = [node['path']] + list(node.get('via') or [])
    for text in cands:
        i = text.find(RUNS_DIR_PREFIX)
        if i < 0:
            continue
        rest = text[i + len(RUNS_DIR_PREFIX):]
        run = rest.split('/', 1)[0]
        nid = f'f:{RUNS_DIR_PREFIX}{run}/scripts'
        if run and nid in nodes:
            return nid
    return ''


def _sub_graph(sub: dict) -> dict:
    """節點、邊與座標。回 {'nodes', 'edges', 'l_edges', 'route', 'width', 'height', 'frame', 'dummy_rows', 'stats'}。

    節點：入口自己是節點（圖表入口在圖表欄、結果鍵入口在結果欄）；檔案節點依 kind 落欄（其他 → 結果欄）；
    kind=figure 的檔案不另開節點，改在圖表節點的面板逐檔列出。結果鍵入口的 run 輸出檔（report.md、status.json、
    values_snapshot…）縮排掛在該入口之下，以 L 形線相連。
    邊：資料 → 程式碼 → 結果 → 圖表；產圖腳本可跳過結果欄直接進圖表（在結果欄借一列 dummy 穿過）；
    結果鍵入口 → 引用它的圖表入口。邊只從 derive 的節點—入口關係推出來，衍生規則不在這裡重寫。
    """
    entries = sub['entries']
    by_id: dict[str, list[dict]] = {}
    for e in entries:
        by_id.setdefault(e['id'], []).append(e)
    eorder = {e['id']: i for i, e in enumerate(entries)}
    for eid, group in by_id.items():
        eorder[eid] = min(entries.index(x) for x in group)

    def has_kind(eid: str, kind: str) -> bool:
        return any(x['kind'] == kind for x in by_id.get(eid, []))
    hist_keys = {it['key'] for e in entries for it in e['result_keys'] if it['historical']}
    cur_keys = {it['key'] for e in entries for it in e['result_keys'] if not it['historical']}
    nodes: dict[str, dict] = {}

    # ---- 入口節點 ----
    for e in entries:
        band = SUB_TIER_BAND[e['tier']]
        label = (f'{e["figure_number"]} ｜ {e["id"]}' if e['kind'] == 'figure' and e['figure_number'] else e['id'])
        n = _sub_node(e['node_id'], 'entry_figure' if e['kind'] == 'figure' else 'entry_result',
                      3 if e['kind'] == 'figure' else 2, band, label, entry=e['id'], ref=e['id'])
        n.update({'is_dir': False, 'bytes': 0, 'n_files': 0, 'missing': False, 'excluded': e['excluded'],
                  'badges': [SUB_BADGE_SHORT.get(b, b) for b in e['badges']] + (['已移除'] if e['excluded'] else []),
                  'path': e['source'], 'tier': e['tier']})
        nodes[n['id']] = n

    # ---- 檔案節點 ----
    for nid, fn in sorted(sub['nodes'].items()):
        owners = [x for x in fn['entries'] if x in by_id]
        fig_owners = [x for x in owners if has_kind(x, 'figure')]
        if fn['kind'] == 'figure' and fig_owners:
            continue        # 圖表自己的 svg／pdf／png：面板逐檔列，不另開節點
        band = SUB_TIER_BAND[fn['tier']]
        parent = ''
        if fn['kind'] in ('result', 'other'):
            res_owners = [x for x in owners if any(y['kind'] == 'result' and SUB_TIER_BAND[y['tier']] == band
                                                   for y in by_id[x])]
            if res_owners:
                parent = 'er:' + min(res_owners, key=lambda x: eorder[x])
        via_hist = any(f'results_keys[{k}]' in v for v in fn['via'] for k in hist_keys)
        via_cur = any(not v.startswith('results_keys[') for v in fn['via']) or \
            any(f'results_keys[{k}]' in v for v in fn['via'] for k in cur_keys)
        n = _sub_node(f'f:{nid}', fn['kind'], SUB_COL_OF.get(fn['kind'], 2), band, '', parent=parent, ref=nid)
        n.update({k: fn[k] for k in ('path', 'tier', 'is_dir', 'bytes', 'n_files', 'missing', 'excluded', 'external',
                                     'origin', 'packaged_path', 'note', 'entries', 'via', 'counted')})
        n['badges'] = _sub_badges(fn, via_hist and not via_cur)
        n['label'] = _sub_label(n)
        nodes[n['id']] = n
    for n in nodes.values():
        if n['parent'] and n['parent'] not in nodes:
            n['parent'] = ''
            n['subtype'] = ''

    # ---- 邊 ----
    edges: list[dict] = []
    l_edges: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(a: str, b: str, etype: str, style: str = 'solid') -> None:
        if a == b or a not in nodes or b not in nodes or (a, b) in seen:
            return
        seen.add((a, b))
        edges.append({'from': a, 'to': b, 'type': etype, 'style': style, 'label': '', 'source': ''})

    by_entry: dict[str, list[str]] = {}
    for nid, n in nodes.items():
        for eid in n.get('entries') or []:
            by_entry.setdefault(eid, []).append(nid)
    for e in entries:
        target = e['node_id']
        # 已經有連線的結果鍵入口
        key_entries = [it['key'] for it in e['result_keys'] if it['is_entry'] and has_kind(it['key'], 'result')]
        mine = by_entry.get(e['id'], [])
        code = [x for x in mine if nodes[x]['kind'] == 'code']
        data = [x for x in mine if nodes[x]['kind'] == 'data']
        res = [x for x in mine if nodes[x]['kind'] in ('result', 'other', 'figure')]
        for x in code:
            add(x, target, 'produces')
        # 資料 → 程式碼只連一條：優先連「這個資料檔自己那個 run 的 scripts/」，否則連這個入口的代表腳本
        # （每個資料檔對每個入口都畫到所有腳本的話，線會多到看不出東西）
        primary = _sub_primary_code(code, nodes)
        for x in data:
            c = _sub_run_scripts(nodes[x], nodes) or primary
            if c:
                add(x, c, 'feeds')
            else:
                add(x, target, 'feeds')
        for x in res:
            if nodes[x]['parent'] == target:
                l_edges.append((target, x))
            elif e['kind'] == 'figure' and not nodes[x]['parent']:
                # 這個結果檔是靠圖表的 results_keys 追到的，而那個鍵本身已經有節點連過來了：
                # 不再從檔案另拉一條，否則同一條關係會畫兩次、線也會多到看不出東西
                vias = nodes[x]['via'] or []
                via_key = any(v.startswith(f'results_keys[{k}]') for v in vias for k in key_entries)
                via_direct = any(v.split('.')[0] in SUB_FIG_FIELDS for v in vias)
                if via_key and not via_direct:
                    continue
                add(x, target, 'depicts')
            elif e['kind'] == 'result':
                add(target, x, 'produces', 'thin')
        if e['kind'] == 'figure':
            for it in e['result_keys']:
                if it['is_entry'] and has_kind(it['key'], 'result'):
                    add('er:' + it['key'], target, 'depicts')

    # ---- 列序：同一入口的檔案排在一起，再以 barycenter 往返掃描（只在同帶同欄內重排）----
    blocks: dict[tuple[str, int], list[list[str]]] = {}
    members: dict[str, list[str]] = {}
    for nid, n in nodes.items():
        head = n['parent'] or nid
        members.setdefault(head, [])
        if head != nid:
            members[head].append(nid)
    for head, kids in members.items():
        kids.sort()
    for nid, n in nodes.items():
        if n['parent']:
            continue
        key = (n['band'], n['col'])
        blocks.setdefault(key, []).append([nid] + members.get(nid, []))

    def anchor(nid: str) -> tuple:
        if nid not in nodes:        # 跳欄借的空列：起點跟著目標節點，之後由 barycenter 微調
            a = anchor(edges[dummies[nid]['edge']]['to'])
            return (a[0], 'zz~', nid)
        n = nodes[nid]
        own = [eorder[x] for x in (n.get('entries') or []) if x in eorder]
        if n['kind'].startswith('entry_'):
            own = [eorder.get(n['entry'], 10 ** 6)]
        return (min(own) if own else 10 ** 6, n['kind'], nid)

    for key in blocks:
        blocks[key].sort(key=lambda blk: anchor(blk[0]))

    # 跳欄邊的 dummy 列：一條邊每個中間欄借一列，落在目標節點的區帶（與關聯圖同一套）
    dummies: dict[str, dict] = {}
    for i, e in enumerate(edges):
        a, b = nodes[e['from']], nodes[e['to']]
        if abs(b['col'] - a['col']) <= 1:
            continue
        step = 1 if b['col'] > a['col'] else -1
        for col in range(a['col'] + step, b['col'], step):
            did = f'~{i}@{col}'
            dummies[did] = {'id': did, 'col': col, 'band': b['band'], 'edge': i, 'y': 0.0}
            blocks.setdefault((b['band'], col), []).append([did])

    adj: dict[str, list[str]] = {}
    for e in edges:
        adj.setdefault(e['from'], []).append(e['to'])
        adj.setdefault(e['to'], []).append(e['from'])
    for did, d in dummies.items():
        e = edges[d['edge']]
        adj.setdefault(did, []).extend([e['from'], e['to']])
        adj.setdefault(e['from'], []).append(did)
        adj.setdefault(e['to'], []).append(did)

    pos: dict[str, int] = {}

    def repos() -> None:
        """全圖列序（barycenter 比較用）：區帶依序累積，帶高＝該帶最高那欄的列數，帶與帶之間留一列。"""
        off = 0
        for band in BANDS:
            rows = 0
            for c in range(len(SUB_COLS)):
                row = 0
                for blk in blocks.get((band, c), []):
                    for nid in blk:
                        pos[nid] = off + row
                        row += 1
                rows = max(rows, row)
            off += rows + 1

    def col_of(nid: str) -> int:
        return nodes[nid]['col'] if nid in nodes else dummies[nid]['col']

    repos()
    for rnd in range(SUB_SWEEPS):
        cols = range(len(SUB_COLS)) if rnd % 2 == 0 else reversed(range(len(SUB_COLS)))
        for c in cols:
            for key, blks in blocks.items():
                if key[1] != c or len(blks) < 2:
                    continue
                def bary(blk: list[str]) -> tuple:
                    vals = [pos[x] for nid in blk for x in adj.get(nid, []) if abs(col_of(x) - c) == 1 and x in pos]
                    return (0, sum(vals) / len(vals)) if vals else (1, float(pos[blk[0]]))
                blks.sort(key=lambda blk: (bary(blk), anchor(blk[0])))
                repos()

    # ---- y：每個區帶內各欄從帶的第一列起往下排，帶高＝最高那欄的列數（與 band_frame 同一套定義）----
    has_other = any(key[0] != 'main' and blks for key, blks in blocks.items())
    prev = GRAPH_PAD
    for band in BANDS:
        y0 = (GRAPH_PAD + BAND_TITLE_H if has_other else GRAPH_PAD) if band == 'main' else prev + BAND_GAP + BAND_TITLE_H
        rows_max = 0
        for c in range(len(SUB_COLS)):
            row = 0
            for blk in blocks.get((band, c), []):
                for nid in blk:
                    y = y0 + row * ROW_GAP
                    if nid in nodes:
                        nodes[nid]['y'] = y
                        nodes[nid]['order'] = row
                        nodes[nid]['x'] = GRAPH_PAD + c * COL_PITCH + _indent(nodes[nid])
                    else:
                        dummies[nid]['y'] = y
                    row += 1
            rows_max = max(rows_max, row)
        prev = y0 + (rows_max - 1) * ROW_GAP + NODE_H if rows_max else (prev if band != 'main' else y0)

    for i, e in enumerate(edges):
        a, b = nodes[e['from']], nodes[e['to']]
        if abs(b['col'] - a['col']) <= 1:
            continue
        step = 1 if b['col'] > a['col'] else -1
        e['via'] = [[col, dummies[f'~{i}@{col}']['y']] for col in range(a['col'] + step, b['col'], step)]

    fan = _sub_fan(nodes, edges)
    route = route_edges(nodes, [(i, e) for i, e in enumerate(edges) if i not in fan['handled']])
    shown = set(nodes)
    crossings, pairs, overlaps = crossing_stats(nodes, shown, route['lines'] + fan['lines'])
    dummy_rows: dict[str, list[float]] = {}
    for d in dummies.values():
        dummy_rows.setdefault(d['band'], []).append(d['y'])
    frame = band_frame(list(nodes.values()), shown, dummy_rows)
    width = int(max([n['x'] + _node_w(n) for n in nodes.values()] + [GRAPH_PAD + len(SUB_COLS) * COL_PITCH]) + GRAPH_PAD)
    height = int(max([frame['bottom'][b] for b in BANDS] + [GRAPH_PAD]) + GRAPH_PAD)
    return {'nodes': nodes, 'edges': edges, 'l_edges': l_edges, 'route': route, 'fan': fan, 'dummies': dummies,
            'width': width, 'height': height, 'frame': frame, 'dummy_rows': dummy_rows,
            'stats': {'graph_nodes': len(nodes), 'graph_edges': len(edges) + len(l_edges),
                      'crossings': crossings, 'edge_node_overlaps': overlaps, 'dummy_rows': len(dummies),
                      'fans': len([s for s in fan['spines'] if not s.get('head')]), 'fan_edges': len(fan['handled']),
                      'crossing_pairs': pairs[:5], 'lane_overflow': list(route['overflow'])}}


SUB_HEAD_H = 26          # 欄標題列（在區帶框架之上，另外算高度）
SUB_BADGE_CLASS = {'缺檔': 'miss', 'root 外': 'ext', '手動': 'add', '已移除': 'gone',
                   'historical': 'hist', 'run 缺': 'runmiss'}


def _sub_human(n: int) -> str:
    v = float(n)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if v < 1024 or unit == 'GB':
            return f'{v:.0f} {unit}' if unit == 'B' else f'{v:.1f} {unit}'
        v /= 1024.0
    return f'{v:.1f} GB'


def _sub_size_text(n: dict) -> str:
    if n['kind'].startswith('entry_'):
        return ''
    if n['missing']:
        return '—'
    if n.get('is_dir'):
        return f'{n["n_files"]} 檔 {_sub_human(n["bytes"])}'
    return _sub_human(n['bytes'])


def _sub_node_svg(n: dict) -> str:
    w = _node_w(n)
    size = _sub_size_text(n)
    size_w = _tw(size, 11)
    badges = n['badges'][:2] + ([f'+{len(n["badges"]) - 2}'] if len(n['badges']) > 2 else [])
    bw = [_tw(b, 10) + 6 for b in badges]
    label = _fit(n['label'], w - 22 - size_w - sum(bw) - 6 * len(bw) - 8, 11 if n['parent'] else 12)
    parts = [f'<g class="subnode k-{n["kind"]}{" sub" if n["parent"] else ""}{" is-miss" if n["missing"] else ""}'
             f'{" is-gone" if n["excluded"] else ""}" data-snode="{_h(n["id"])}" data-kind="{n["kind"]}" '
             f'data-band="{n["band"]}" data-col="{n["col"]}" data-order="{n["order"]}" '
             f'transform="translate({n["x"]:g},{n["y"]:g})" tabindex="0" role="button">'
             f'<rect class="box" width="{w}" height="{NODE_H}" rx="6"></rect>'
             f'<rect class="kbar" x="3" y="3" width="5" height="{NODE_H - 6}" rx="2"></rect>'
             f'<text class="lbl" x="16" y="23">{_h(label)}</text>']
    x = w - 8 - size_w - (6 if size else 0)
    for b, bwi in zip(reversed(badges), reversed(bw)):
        x -= bwi
        parts.append(f'<text class="bdg b-{SUB_BADGE_CLASS.get(b, "other")}" x="{x:g}" y="23">{_h(b)}</text>')
        x -= 4
    if size:
        parts.append(f'<text class="sz" x="{w - 8}" y="23" text-anchor="end">{_h(size)}</text>')
    title = f'{n["label"]}（{SUB_KIND_LABEL.get(n["kind"], n["kind"])}）\n{n["path"]}'
    if n['badges']:
        title += '\n' + '、'.join(n['badges'])
    parts.append(f'<title>{_h(title)}</title></g>')
    return ''.join(parts)


def _svg_submission(g: dict) -> str:
    nodes, route = g['nodes'], g['route']
    width, height, frame = g['width'], g['height'] + SUB_HEAD_H, g['frame']
    out = [f'<svg id="sub-svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="投稿檔案關係圖：四欄由左到右資料、程式碼、結果、圖表；三個區帶由上而下正式文章、延伸資料、補充資料">',
           '<defs><marker id="sub-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
           'orient="auto-start-reverse"><path class="sub-arrow-head" d="M0,0 L10,5 L0,10 z"></path></marker></defs>',
           '<g id="sub-view"><g id="sub-cols">']
    for c, (_cid, label) in enumerate(SUB_COLS):
        out.append(f'<text class="colhead" x="{GRAPH_PAD + c * COL_PITCH}" y="{SUB_HEAD_H - 9}">{_h(label)}</text>')
    out.append(f'</g><g id="sub-root" transform="translate(0,{SUB_HEAD_H})"><g id="sub-bands">')
    for b in BANDS:
        off = '' if frame['has'][b] else ' off'
        if b != 'main':
            out.append(f'<line class="band-divider{off}" data-band="{b}" x1="{GRAPH_PAD}" y1="{frame["y_div"][b]:g}" '
                       f'x2="{width - GRAPH_PAD}" y2="{frame["y_div"][b]:g}"></line>')
        out.append(f'<text class="band-title{off}" data-band="{b}" x="{GRAPH_PAD}" '
                   f'y="{frame["y_title"][b] + BAND_TITLE_DY:g}">{_h(SUB_BAND_TITLE[b])}</text>')
    out.append('</g><g id="sub-trunks">')
    for t in route['trunks']:
        out.append(f'<path class="subtrunk e-{t["type"]} st-{t["style"]}" data-trunk="{_h(t["key"])}" d="{t["d"]}"></path>')
    for s in g['fan']['spines']:
        out.append(f'<path class="subtrunk e-{s["type"]} st-{s["style"]}{" head" if s.get("head") else ""}" '
                   f'data-trunk="{_h(s["key"])}" d="{s["d"]}"></path>')
    out.append('</g><g id="sub-edges">')
    for i, e in enumerate(g['edges']):
        d = g['fan']['paths'].get(i) or route['paths'].get(i, '')
        fanned = ' fanned' if i in g['fan']['handled'] else ''
        out.append(f'<path class="subedge e-{e["type"]} st-{e["style"]}{fanned}" data-idx="{i}" data-from="{_h(e["from"])}" '
                   f'data-to="{_h(e["to"])}" d="{d}"></path>')
    for a, b in g['l_edges']:
        out.append(f'<path class="subedge e-owns" data-from="{_h(a)}" data-to="{_h(b)}" '
                   f'd="{_l_path(nodes[a], nodes[b])}"></path>')
    out.append('</g><g id="sub-nodes">')
    for nid in sorted(nodes, key=lambda x: (nodes[x]['band'], nodes[x]['col'], nodes[x]['order'])):
        out.append(_sub_node_svg(nodes[nid]))
    out.append('</g></g></g></svg>')
    return '\n'.join(out)


def _sub_cmd(plugin: Path, root: str, script: str, tail: str) -> str:
    return f'python3 {plugin}/skills/submission-prep/scripts/{script} {root} {tail}'


def _submission_tab(ir: dict, notes: list[str] | None = None) -> list[str]:
    """第四個分頁「投稿檔案」（唯讀檢視）：摘要列、四欄三帶的關係圖、節點面板。

    面板與摘要列的「移除／還原／加入檔案／打包」在這一版全部 disabled，旁邊寫等效命令；伺服器端動作登記與按鈕
    接線是下一棒。按鈕的 data 屬性即為接線契約：data-saction（動作種類）、data-node（圖上的節點 id）、
    data-ref（SSOT 的識別：入口 id 或相對 root 的路徑）、data-tier、data-kind、data-cmd（等效命令）。
    """
    sub = ir.get('submission') or _sub_empty()
    plugin = Path(__file__).resolve().parents[3]
    root = ir['project_root']
    lines = [f'<section id="tab-submission" hidden data-plugin="{_h(str(plugin))}" data-root="{_h(root)}">']
    if sub['error']:
        lines += [f'<p class="sub-empty">投稿檔案清單這次算不出來：{_h(sub["error"])}。'
                  f'其他分頁不受影響；修好 <code>{_h(sub["source"])}</code> 後重跑本頁即可。</p>', '</section>']
        return lines
    st = sub['stats']
    build_cmd = _sub_cmd(plugin, root, 'build_submission_package.py', '--dry-run')
    blocked = st['blocking_missing'] > 0
    lines += [
        '<div class="sub-summary">',
        '<div class="sub-figs">',
        '<span class="sub-fig"><b>入口</b> ' + '、'.join(
            f'{SUB_TIER_LABEL[t]} {st["entries_by_tier"].get(t, 0)}' for t in SUB_TIERS)
        + f'（圖表／表格 {st["entries_by_kind"].get("figure", 0)}、結果鍵 {st["entries_by_kind"].get("result", 0)}）</span>',
        '<span class="sub-fig"><b>檔案節點</b> ' + '、'.join(
            f'{SUB_KIND_LABEL[k]} {st["nodes_by_kind"].get(k, 0)}' for k in SUB_KINDS if st['nodes_by_kind'].get(k))
        + '</span>',
        f'<span class="sub-fig"><b>總計</b> {st["files"]} 個檔、{_sub_human(st["bytes"])}</span>',
        f'<span class="sub-fig"><b>root 外</b> {st["external"]}</span>',
        f'<span class="sub-fig"><b>手動加入</b> {st["added"]}</span>',
        f'<span class="sub-fig"><b>已移除</b> 入口 {st["entries_excluded"]}、節點 {st["nodes_excluded"]}</span>',
        ('<span class="sub-fig is-bad"><b>缺檔（擋打包）</b> ' + str(st['blocking_missing']) + '</span>'
         if blocked else '<span class="sub-fig is-ok"><b>缺檔（擋打包）</b> 0</span>'),
        '</div>',
        '<div class="sub-act">',
        f'<button type="button" id="sub-build" data-saction="build" data-cmd="{_h(build_cmd)}" disabled>打包</button>',
        '<span class="sub-cmd">下一棒才接線；等效命令：<code>' + _h(build_cmd) + '</code></span>',
    ]
    if blocked:
        lines.append(f'<span class="sub-why">有 {st["blocking_missing"]} 個納入中的缺檔，打包會被拒絕（exit 1）：'
                     '先用 package_edit.py 移除，或補上替代檔。</span>')
    lines.append('</div>')
    if blocked:
        lines.append('<ul class="sub-missing">')
        for nid in sub['blocking_missing'][:8]:
            lines.append(f'<li><a href="#" class="sub-goto" data-sgoto="f:{_h(nid)}"><code>{_h(nid)}</code></a></li>')
        if st['blocking_missing'] > 8:
            lines.append(f'<li class="notice">…另有 {st["blocking_missing"] - 8} 個（完整清單在 PROGRESS.ir.json 的 submission.blocking_missing）</li>')
        lines.append('</ul>')
    if sub['warnings']:
        lines.append(f'<details class="sub-warn"><summary>衍生時的提醒 {len(sub["warnings"])} 條</summary><ul>')
        lines += [f'<li>{_h(w)}</li>' for w in sub['warnings'][:40]]
        if len(sub['warnings']) > 40:
            lines.append(f'<li class="notice">…另有 {len(sub["warnings"]) - 40} 條</li>')
        lines.append('</ul></details>')
    lines.append('</div>')
    if not sub['present']:
        lines += ['<p class="sub-empty">還沒有可以列的投稿檔案：'
                  '<code>analysis/figures/manifest.json</code> 沒有標 role 的圖表，<code>analysis/results.json</code> 也沒有現行結果鍵。'
                  '兩者其中之一有內容後重跑本頁就會出現。</p>', '</section>']
        return lines
    g = _sub_graph(sub)
    gs = g['stats']
    if notes is not None:
        for gap in gs['lane_overflow']:
            notes.append(f'投稿檔案分頁走道 {gap} 的幹線超過 {TRUNK_MAX_LANES} 條車道，折回重用')
    lines += [
        '<div class="sub-legend">',
        '<span>欄序由左到右：' + ' → '.join(label for _cid, label in SUB_COLS) + '</span>',
        '<span>區帶由上而下：' + '、'.join(SUB_BAND_TITLE[b] for b in BANDS) + '（節點落在自己的帶，跨帶的線照畫）</span>',
    ]
    for kind, label in SUB_COLS:
        lines.append(f'<span><span class="ksw k-{kind}"></span>{label}</span>')
    lines += [
        '<span><span class="ksw k-entry_result"></span>結果鍵入口</span>',
        '<span><span class="ksw k-entry_figure"></span>圖表／表格入口</span>',
        '<span>縮排＝該結果鍵 run 的輸出檔（report.md、status.json、快照表…），以 L 形線連回入口</span>',
        '<span>徽章：<span class="bsw b-miss">缺檔</span>擋打包・<span class="bsw b-runmiss">run 缺</span>run 資料夾不存在'
        '（不擋）・<span class="bsw b-ext">root 外</span>・<span class="bsw b-add">手動</span>手動加入・'
        '<span class="bsw b-gone">已移除</span>整個節點變灰但仍列出・<span class="bsw b-hist">historical</span>只被歷史鍵引用</span>',
        '<span>點節點看來源路徑、打包後路徑與引用它的入口；圖表節點逐檔列出 files</span>',
        '<span>滾輪縮放、拖曳平移、Esc 關面板</span>',
        '</div>',
        '<div id="sub-wrap">',
        _svg_submission(g),
        '</div>',
        f'<p class="notice">投稿檔案圖：節點 {gs["graph_nodes"]}（入口 {st["entries"] + st["entries_excluded"]}、檔案節點'
        f' {len(sub["nodes"])}，其中圖表自己的 files 不另開節點）、邊 {gs["graph_edges"]}、跳欄借用的空列'
        f' {gs["dummy_rows"]}；線段交叉 {gs["crossings"]}、穿過節點 {gs["edge_node_overlaps"]}。'
        f'清單與帶的規則來自 <code>{_h(sub["source"])}</code>（derive()），歸帶沿用關聯圖同一套；本頁只讀不改 SSOT。</p>',
        '<aside id="sub-detail" hidden><button type="button" class="close" id="sub-detail-close">關閉（Esc）</button>',
        '<div id="sub-detail-body"></div>',
        '<form id="sub-include-form" class="sub-form">',
        '<h4>加入檔案（下一棒才接線）</h4>',
        '<label>路徑 <input type="text" name="path" placeholder="相對 root；root 外用絕對路徑" disabled></label>',
        '<label>帶 <select name="tier" disabled>'
        + ''.join(f'<option value="{t}">{SUB_TIER_LABEL[t]}</option>' for t in SUB_TIERS) + '</select></label>',
        '<label>分類 <select name="kind" disabled>'
        + ''.join(f'<option value="{k}">{SUB_KIND_LABEL[k]}</option>' for k in SUB_KINDS) + '</select></label>',
        '<label>掛到哪個入口 <select name="attach_to" disabled><option value="">（不掛）</option>'
        + ''.join(f'<option value="{_h(e["id"])}">{_h(e["id"])}</option>' for e in sub['entries']) + '</select></label>',
        '<label>備註 <input type="text" name="note" disabled></label>',
        f'<button type="button" data-saction="include" data-cmd="{_h(_sub_cmd(plugin, root, "package_edit.py", "--include <路徑> --tier <帶> --kind <分類> --dry-run"))}" disabled>加入檔案</button>',
        '<p class="sub-cmd">等效命令：<code>'
        + _h(_sub_cmd(plugin, root, 'package_edit.py', '--include <路徑> --tier <帶> --kind <分類> --dry-run')) + '</code></p>',
        '</form>',
        '</aside>',
        '</section>',
    ]
    return lines


SUB_CSS = """
.sub-summary{margin:12px 0;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card)}
.sub-figs{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:13px}
.sub-fig b{font-weight:600;color:var(--muted);margin-right:4px}
.sub-fig.is-bad{color:var(--badge-blocked);font-weight:600}
.sub-fig.is-ok{color:var(--done)}
.sub-act{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-top:10px}
.sub-act button{border:1px solid var(--line);background:var(--proj);color:inherit;border-radius:6px;padding:4px 12px;font:inherit}
.sub-act button[disabled]{opacity:.55;cursor:not-allowed}
.sub-cmd{font-size:11px;color:var(--muted)}
.sub-cmd code{font-size:11px;word-break:break-all}
.sub-why{font-size:12px;color:var(--badge-blocked)}
.sub-missing{margin:8px 0 0;padding-left:18px;font-size:12px}
.sub-missing code{word-break:break-all}
.sub-missing a{color:var(--badge-blocked)}
.sub-warn{margin-top:8px;font-size:12px;color:var(--muted)}
.sub-warn ul{margin:4px 0;padding-left:18px}
.sub-warn li{margin:2px 0}
.sub-empty{margin:16px 0;padding:12px;border:1px dashed var(--line);border-radius:8px;color:var(--muted)}
.sub-legend{display:flex;flex-wrap:wrap;gap:8px 16px;margin:8px 0 10px;font-size:12px;color:var(--muted)}
.sub-legend span{display:inline-flex;align-items:center;gap:5px}
.ksw{display:inline-block;width:10px;height:14px;border-radius:2px;background:var(--pending)}
.ksw.k-data{background:var(--t-validation)}.ksw.k-code{background:var(--t-method)}
.ksw.k-result{background:var(--t-result)}.ksw.k-figure{background:var(--t-figure)}
.ksw.k-entry_result{background:var(--t-result);outline:2px solid var(--current);outline-offset:1px}
.ksw.k-entry_figure{background:var(--t-figure);outline:2px solid var(--current);outline-offset:1px}
.bsw{border-radius:3px;padding:0 4px;font-size:11px;border:1px solid var(--line)}
.bsw.b-miss{color:var(--badge-blocked);border-color:var(--badge-blocked)}
.bsw.b-runmiss{color:var(--expired);border-color:var(--expired)}
.bsw.b-ext{color:var(--current);border-color:var(--current)}
.bsw.b-add{color:var(--done);border-color:var(--done)}
.bsw.b-gone{color:var(--muted)}
.bsw.b-hist{color:var(--t-lit);border-color:var(--t-lit)}
#sub-wrap{position:relative;overflow:auto;height:72vh;min-height:360px;border:1px solid var(--line);border-radius:8px;background:var(--card);cursor:grab;user-select:none}
#sub-wrap.dragging{cursor:grabbing}
#sub-svg{display:block}
#sub-cols text.colhead{font-size:12px;font-weight:600;fill:var(--muted)}
#sub-bands text.band-title{font-size:12px;font-weight:600;fill:var(--muted)}
#sub-bands line.band-divider{stroke:var(--edge-faint);stroke-width:1;stroke-dasharray:6 4}
#sub-bands .off{display:none}
.subnode{cursor:pointer}
.subnode .box{fill:var(--bg-none);stroke:var(--pending);stroke-width:1.2}
.subnode .kbar{fill:var(--pending)}
.subnode .lbl{font-size:12px;fill:var(--fg)}
.subnode.sub .lbl{font-size:11px}
.subnode .sz{font-size:11px;fill:var(--muted)}
.subnode .bdg{font-size:10px;fill:var(--muted)}
.subnode .bdg.b-miss{fill:var(--badge-blocked);font-weight:700}
.subnode .bdg.b-runmiss{fill:var(--expired);font-weight:700}
.subnode .bdg.b-ext{fill:var(--current)}
.subnode .bdg.b-add{fill:var(--done)}
.subnode .bdg.b-hist{fill:var(--t-lit)}
.subnode.k-data .kbar{fill:var(--t-validation)}
.subnode.k-code .kbar{fill:var(--t-method)}
.subnode.k-result .kbar,.subnode.k-other .kbar{fill:var(--t-result)}
.subnode.k-figure .kbar{fill:var(--t-figure)}
.subnode.k-entry_result .kbar{fill:var(--t-result)}
.subnode.k-entry_figure .kbar{fill:var(--t-figure)}
.subnode.k-entry_result .box,.subnode.k-entry_figure .box{stroke:var(--current);stroke-width:1.8;fill:var(--proj)}
.subnode.is-miss .box{stroke:var(--badge-blocked);stroke-dasharray:5 3}
.subnode.is-gone{opacity:.45}
.subnode.is-gone .box{stroke-dasharray:3 3}
.subnode.on .box{stroke:var(--current);stroke-width:2.6}
.subnode.dim{opacity:.28}
.subnode:focus{outline:none}.subnode:focus .box{stroke:var(--current);stroke-width:2.6}
path.subedge{fill:none;stroke:var(--edge);stroke-width:1.1;marker-end:url(#sub-arrow)}
path.subtrunk{fill:none;stroke:var(--edge);stroke-width:1.6}
path.subedge.st-thin,path.subtrunk.st-thin{stroke-width:.9;stroke:var(--edge-thin)}
path.subedge.e-owns{stroke:var(--edge-thin);stroke-width:1;marker-end:none}
path.subedge.fanned{marker-end:none}
path.subtrunk.head{marker-end:url(#sub-arrow)}
path.subedge.on,path.subtrunk.on{stroke:var(--current);stroke-width:2}
path.subedge.dim,path.subtrunk.dim{stroke:var(--edge-faint)}
.sub-arrow-head{fill:var(--edge)}
#sub-detail{position:fixed;right:16px;bottom:16px;width:min(520px,calc(100vw - 32px));max-height:76vh;overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;box-shadow:0 6px 24px rgba(0,0,0,.18);z-index:10}
#sub-detail h3{margin:0 0 6px;font-size:15px}
#sub-detail h4{margin:10px 0 4px;font-size:13px}
#sub-detail .close{float:right;border:1px solid var(--line);background:none;color:inherit;border-radius:6px;cursor:pointer;padding:2px 8px}
#sub-detail dl{margin:6px 0}#sub-detail dt{font-weight:600;margin-top:6px;font-size:12px;color:var(--muted)}
#sub-detail dd{margin:0 0 0 8px;font-size:13px;word-break:break-all}
#sub-detail ul{margin:2px 0;padding-left:18px;font-size:12px}
#sub-detail li{margin:2px 0}
#sub-detail .row{display:flex;align-items:center;gap:6px;justify-content:space-between}
#sub-detail button[data-saction]{border:1px solid var(--line);background:var(--proj);color:inherit;border-radius:6px;padding:1px 8px;font-size:12px}
#sub-detail button[disabled]{opacity:.55;cursor:not-allowed}
#sub-detail .goto{color:var(--current);cursor:pointer;text-decoration:underline dotted}
#sub-detail .sub-form{margin-top:10px;padding-top:8px;border-top:1px solid var(--line)}
#sub-detail .sub-form label{display:block;font-size:12px;margin:4px 0;color:var(--muted)}
#sub-detail .sub-form input,#sub-detail .sub-form select{font:inherit;font-size:12px;padding:2px 4px;max-width:100%;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:4px}
#sub-detail .sub-form button{border:1px solid var(--line);background:var(--proj);color:inherit;border-radius:6px;padding:3px 10px;font-size:12px;margin-top:4px}
"""

SUB_JS = r"""
/* 投稿檔案分頁（唯讀）：節點面板、缺檔跳轉、滾輪縮放與拖曳平移。
   面板與表單裡所有 data-saction 的按鈕這一版一律 disabled，只顯示等效命令；下一棒接 server 動作。 */
(function(){
  var src=document.getElementById('progress-ir'); if(!src) return;
  var ir; try{ir=JSON.parse(src.textContent);}catch(e){return;}
  var sub=ir.submission; if(!sub) return;
  var section=document.getElementById('tab-submission'); if(!section) return;
  var svg=document.getElementById('sub-svg'), wrap=document.getElementById('sub-wrap');
  var detail=document.getElementById('sub-detail'), body=document.getElementById('sub-detail-body');
  var PLUGIN=section.getAttribute('data-plugin')||'', ROOT=section.getAttribute('data-root')||'';
  var EDIT='python3 '+PLUGIN+'/skills/submission-prep/scripts/package_edit.py '+ROOT;
  var TIER={main:'正式文章',extended:'延伸資料',supplementary:'補充資料'};
  var KIND={data:'資料',code:'程式碼',result:'結果',figure:'圖表',other:'其他',
            entry_result:'結果鍵入口',entry_figure:'圖表／表格入口'};
  var WHY={'缺檔':'引用它的欄位指到這個路徑，但檔案不存在；打包會被拒絕',
           'run 資料夾不存在':'結果鍵的 run_id 只是標籤，資料夾從未存在；script 欄找得到檔，所以不擋打包',
           'root 外':'來源在專案根之外，打包時放進 external/',
           '手動加入':'submission/package.yaml 的 include 加的，不是衍生出來的',
           '已移除':'submission/package.yaml 的 exclude 移掉了，仍列出以便還原',
           'historical':'只被 status=historical 的結果鍵引用（該鍵本身不是入口）'};
  var entries={},byId={}; (sub.entries||[]).forEach(function(e){entries[e.node_id]=e;
    (byId[e.id]=byId[e.id]||[]).push(e.node_id);});
  var nodes=sub.nodes||{};
  function h(s){var d=document.createElement('div');d.textContent=(s==null?'':String(s));return d.innerHTML;}
  function q(s){return String(s).replace(/\\/g,'\\\\').replace(/"/g,'\\"');}
  function human(n){var v=n||0,u=['B','KB','MB','GB'],i=0;
    while(v>=1024&&i<3){v/=1024;i++;} return (i?v.toFixed(1):v.toFixed(0))+' '+u[i];}
  function btn(action,ref,label,cmd,extra){
    return '<button type="button" data-saction="'+h(action)+'" data-ref="'+h(ref)+'" data-cmd="'+h(cmd)+'"'+
      (extra||'')+' disabled>'+h(label)+'</button>';}
  function cmdline(cmd){return '<p class="sub-cmd">等效命令：<code>'+h(cmd)+'</code></p>';}
  function gotoLink(id,label){return '<span class="goto" data-sgoto="'+h(id)+'">'+h(label)+'</span>';}
  function dl(pairs){var out='<dl>';pairs.forEach(function(p){
      if(p[1]===''||p[1]===null||p[1]===undefined)return;
      out+='<dt>'+h(p[0])+'</dt><dd>'+p[1]+'</dd>';});return out+'</dl>';}
  function badgeList(bs){ if(!bs||!bs.length) return '';
    return '<ul>'+bs.map(function(b){return '<li><span class="bsw">'+h(b)+'</span> '+h(WHY[b]||'')+'</li>';}).join('')+'</ul>';}
  function filesOf(eid){var out=[];Object.keys(nodes).forEach(function(k){var n=nodes[k];
      if(n.kind==='figure'&&(n.entries||[]).indexOf(eid)>=0)out.push(n);});return out;}
  function fileRow(n){
    return '<li><div class="row"><span><code>'+h(n.path)+'</code> '+(n.missing?'<span class="bsw b-miss">缺檔</span>':h(human(n.bytes)))+'</span>'+
      '<span>'+btn('exclude',n.path,'移除',EDIT+' --exclude '+n.path+' --dry-run')+
      btn('restore',n.path,'還原',EDIT+' --restore '+n.path+' --dry-run')+'</span></div></li>';}
  function nodePanel(id){
    var n=nodes[id.slice(2)]; if(!n) return '';
    var refs=[];(n.entries||[]).forEach(function(x){
      (byId[x]||[]).forEach(function(nid){refs.push(gotoLink(nid,x+'（'+(KIND[entries[nid].kind==='figure'?'entry_figure':'entry_result'])+'）'));});
      if(!byId[x])refs.push(h(x));});
    refs=refs.join('、');
    var out='<h3>'+h(n.path.split('/').pop()||n.path)+'</h3>'+
      dl([['分類',h(KIND[n.kind]||n.kind)+'／'+h(TIER[n.tier]||n.tier)],
          ['來源路徑','<code>'+h(n.path)+'</code>'+(n.external?'（專案根之外）':'')],
          ['打包後路徑',n.missing?'—（缺檔不會被複製）':'<code>'+h(n.packaged_path)+'</code>'],
          ['大小',n.missing?'—':(n.is_dir?(n.n_files+' 個檔、'+human(n.bytes)):human(n.bytes))+
                 (n.counted?'':'（已含在上層資料夾節點內，不重複計）')],
          ['引用它的入口',refs||'（沒有入口引用，來自手動加入）'],
          ['被哪些欄位追到','<ul><li>'+(n.via||[]).map(h).join('</li><li>')+'</li></ul>'],
          ['備註',n.note?h(n.note):''],
          ['徽章',badgeList(n.badges)]]);
    out+='<div class="row"><span>'+(n.excluded?'已移除：'+h(n.exclude_reason||''):'納入打包')+'</span><span>'+
      btn('exclude',n.path,'移除',EDIT+' --exclude '+n.path+' --reason <理由> --dry-run')+
      btn('restore',n.path,'還原',EDIT+' --restore '+n.path+' --dry-run')+'</span></div>'+
      cmdline(EDIT+' --exclude '+n.path+' --dry-run');
    return out;}
  function entryPanel(id){
    var e=entries[id]; if(!e) return '';
    var keys=(e.result_keys||[]).map(function(it){
      var tgt=(byId[it.key]||[]).filter(function(x){return x.indexOf('er:')===0;})[0];
      return '<li>'+(it.is_entry&&tgt?gotoLink(tgt,it.key):'<code>'+h(it.key)+'</code>')+
        (it.historical?' <span class="bsw b-hist">historical</span>':'')+
        (it.registered?'':' <span class="bsw b-miss">不在 results.json</span>')+'</li>';}).join('');
    var rows=[['類型',h(e.kind==='figure'?(e.type||'figure'):'結果鍵'+(e.type?'（'+e.type+'）':''))],
              ['帶',h(TIER[e.tier]||e.tier)+(e.role?'（manifest role：'+h(e.role)+'）':'')],
              ['編號',h(e.figure_number||'')],
              ['計畫／run',[e.plan_id,e.run_id].filter(Boolean).map(h).join(' ／ ')],
              ['說明',h(e.caption_first||'')],
              ['來源','<code>'+h(e.source)+'</code>'],
              ['結果鍵',keys?'<ul>'+keys+'</ul>':''],
              ['run 資料夾不存在',(e.run_missing||[]).length?'<ul><li><code>'+(e.run_missing||[]).map(h).join('</code></li><li><code>')+'</code></li></ul>':''],
              ['徽章',badgeList(e.badges)]];
    var out='<h3>'+h(e.figure_number?e.figure_number+' ｜ '+e.id:e.id)+'</h3>'+dl(rows);
    if(e.kind==='figure'){
      var fs=filesOf(e.id);
      out+='<h4>圖表檔（'+fs.length+'）</h4>'+(fs.length?'<ul>'+fs.map(fileRow).join('')+'</ul>':'<p class="sub-cmd">manifest 的 files 沒有列任何檔</p>');}
    out+='<div class="row"><span>'+(e.excluded?'整個入口已移除：'+h(e.exclude_reason||''):'納入打包')+'</span><span>'+
      btn('exclude-entry',e.id,'移除入口',EDIT+' --exclude-entry '+e.id+' --reason <理由> --dry-run')+
      btn('restore',e.id,'還原',EDIT+' --restore '+e.id+' --dry-run')+'</span></div>'+
      cmdline(EDIT+' --exclude-entry '+e.id+' --dry-run');
    return out;}
  var cur='';
  function select(id,scroll){
    var g=svg.querySelector('.subnode[data-snode="'+q(id)+'"]');
    Array.prototype.forEach.call(svg.querySelectorAll('.subnode'),function(x){x.classList.remove('on');x.classList.remove('dim');});
    Array.prototype.forEach.call(svg.querySelectorAll('.subedge,.subtrunk'),function(x){x.classList.remove('on');x.classList.remove('dim');});
    if(!g){detail.hidden=true;cur='';return;}
    cur=id;g.classList.add('on');
    var near={};near[id]=1;
    Array.prototype.forEach.call(svg.querySelectorAll('.subedge'),function(p){
      var f=p.getAttribute('data-from'),t=p.getAttribute('data-to');
      if(f===id||t===id){p.classList.add('on');near[f]=1;near[t]=1;}else{p.classList.add('dim');}});
    Array.prototype.forEach.call(svg.querySelectorAll('.subtrunk'),function(p){p.classList.add('dim');});
    Array.prototype.forEach.call(svg.querySelectorAll('.subnode'),function(x){
      if(!near[x.getAttribute('data-snode')])x.classList.add('dim');});
    body.innerHTML=(id.indexOf('f:')===0?nodePanel(id):entryPanel(id));
    detail.hidden=false;
    if(scroll&&g.getBoundingClientRect){var r=g.getBoundingClientRect(),w=wrap.getBoundingClientRect();
      wrap.scrollLeft+=r.left-w.left-w.width/3;wrap.scrollTop+=r.top-w.top-w.height/3;}
    try{g.focus({preventScroll:true});}catch(err){}}
  function clear(){detail.hidden=true;cur='';
    Array.prototype.forEach.call(svg.querySelectorAll('.on,.dim'),function(x){x.classList.remove('on');x.classList.remove('dim');});}
  svg.addEventListener('click',function(ev){var g=ev.target.closest('.subnode');
    if(!g){clear();return;} var id=g.getAttribute('data-snode'); if(id===cur){clear();}else{select(id,false);}});
  svg.addEventListener('keydown',function(ev){var g=ev.target.closest('.subnode');
    if(g&&(ev.key==='Enter'||ev.key===' ')){ev.preventDefault();select(g.getAttribute('data-snode'),false);}});
  section.addEventListener('click',function(ev){
    var t=ev.target.closest('[data-sgoto]');
    if(t){ev.preventDefault();select(t.getAttribute('data-sgoto'),true);}});
  var close=document.getElementById('sub-detail-close');
  if(close)close.addEventListener('click',clear);
  document.addEventListener('keydown',function(ev){if(ev.key==='Escape'&&!detail.hidden&&!section.hidden)clear();});
  /* 縮放與平移：viewBox 不動，只改 svg 的 width／height */
  var W0=+svg.getAttribute('width')||1, H0=+svg.getAttribute('height')||1, z=1;
  wrap.addEventListener('wheel',function(ev){
    ev.preventDefault();
    var r=wrap.getBoundingClientRect(), ox=ev.clientX-r.left, oy=ev.clientY-r.top;
    var px=(wrap.scrollLeft+ox)/(W0*z), py=(wrap.scrollTop+oy)/(H0*z);
    z=Math.min(2.5,Math.max(0.2,z*(ev.deltaY<0?1.12:1/1.12)));
    svg.setAttribute('width',Math.round(W0*z));svg.setAttribute('height',Math.round(H0*z));
    wrap.scrollLeft=px*W0*z-ox;wrap.scrollTop=py*H0*z-oy;},{passive:false});
  var drag=null;
  wrap.addEventListener('pointerdown',function(ev){
    if(ev.target.closest('.subnode'))return;
    drag={x:ev.clientX,y:ev.clientY,sl:wrap.scrollLeft,st:wrap.scrollTop};wrap.classList.add('dragging');});
  window.addEventListener('pointermove',function(ev){if(!drag)return;
    wrap.scrollLeft=drag.sl-(ev.clientX-drag.x);wrap.scrollTop=drag.st-(ev.clientY-drag.y);});
  window.addEventListener('pointerup',function(){drag=null;wrap.classList.remove('dragging');});
})();
"""


def _relations_tab(ir: dict, notes: list[str] | None = None) -> list[str]:
    graph = ir['graph']
    st = graph['stats']
    lines = [
        '<section id="tab-relations" hidden>',
        '<div class="gcontrols">',
        '<label><input type="search" id="graph-search" placeholder="搜尋 label／title（/ 聚焦）" autocomplete="off"> <span id="graph-search-count" class="src"></span></label>',
        '<span>state：</span>',
    ]
    for s in STATES:
        lines.append(f'<label><input type="checkbox" data-gstate="{s}" checked> <span class="dot {s}"></span> {STATE_ZH[s]}</label>')
    lines += [
        '<label><input type="checkbox" id="toggle-old"> 顯示舊版計畫</label>',
        '<label><input type="checkbox" id="toggle-alledges"> 顯示全部邊</label>',
        '<label><input type="checkbox" id="toggle-dec"> 顯示決策</label>',
        '<label title="預設不勾：放開節點直接加進暫存（各 kind 的預設值、理由留給暫存面板整批填）；勾了回到放開先開表單（填理由、加入暫存或單獨送出）"><input type="checkbox" id="opt-form-on-drop"> 放開時先開表單</label>',
        '<button type="button" id="tour-start">導覽（P）</button><button type="button" id="tour-prev">← 上一章</button><button type="button" id="tour-next">下一章 →</button>',
        '<span class="hint">/ 搜尋 · 點節點看上下游（該節點全部邊都顯示）· 點徽章展開該問題的舊版 · Shift+點 找路徑 · P 導覽 · Esc 清除 · 滾輪縮放、拖曳平移</span>',
        '</div>',
        '<div class="glegend">',
    ]
    for t, lbl in NODE_TYPES:
        if t != 'decision':
            lines.append(f'<span><span class="tsw {t}"></span>{lbl}</span>')
    lines.append('<span><span class="tsw decision"></span>決策（開關）</span>')
    lines += [
        '<span>｜</span>',
        '<span>● 完成</span><span>◐ 過期</span><span>✖ 受阻</span><span>○ 未到</span><span>◌ 不明</span>',
        '<span>｜</span>',
        '<span><span class="esw"></span>主幹（規劃／產出／驗證）；同來源的線合併成幹線＋分支，滑過任一分支整束高亮</span>',
        '<span>三個區帶由上而下：Main（主結果鏈）、Extended Data（延伸資料：圖表依 manifest role，方法／結果／驗證依 analysis/extended-data.yaml；問題不能放）、Supplementary（附錄問題及其一切、補充圖表）；每個區帶內再依問題分成橫向的問題帶——同一個問題延伸出來的方法／驗證／結果／圖表在各欄從帶的第一列起對齊、帶與帶之間留一列空隙（淡色細線分隔）；每組敏感性分析群縮排在所屬分析之下、區帶跟它走，其餘跨區的邊除主問題→附錄問題、結果→圖表外預設不畫，點選節點或「顯示全部邊」才顯示</span>',
        '<span>已由驗證鏈覆蓋的方法→結果產出線預設不畫；跳欄的線在中間欄留一列空位穿過，不與該欄節點交錯</span>',
        '<span>縮排子節點＝敏感性子分析與其次要結果、敏感性分析群（群縮一層、子分析再縮一層；方法欄 plan→群→子分析 L 形線；結果欄靠產出邊連結）；plan 徽章「敏感性 n」，點選 plan 可暫時收合群與子分析</span>',
        '<span>結果主從（outputs 的 supports）：支撐結果縮排在主結果之下、同一區帶，以一條結果色的 L 形線（支撐）連自主結果；主結果徽章「支撐 n」，點選主結果可暫時收合；plan→支撐結果的產出線預設不畫</span>',
        '<span><span class="esw dashed"></span>虛線＝未宣告（results.json 掛在此 plan 但 outputs／robustness 都沒宣告）</span>',
        '<span><span class="esw thin"></span>細線＝驗證（穩健性）</span>',
        '<span><span class="st unval" style="color:var(--expired);font-weight:700">未驗證</span>＝結果沒有任何驗證邊</span>',
        '<span><span class="esw"></span>結果 → 圖表＝呈現於（depicts）；次要結果聚合節點 → 圖表一條、標「n 鍵」</span>',
        '<span>宣告粒度（0.19.0）：有次要鍵的敏感性子分析底下一個次要結果節點（1 鍵直接顯示鍵名、多鍵「次要結果 n 鍵」；徽章「未登錄 a／未驗證 b」；沒宣告次要鍵的子分析不建），鍵全列在面板，整個節點可拖（裡面的鍵一起搬）；未宣告鍵仍逐鍵虛線</span>',
        '<span>report.md 節點（圖表欄最後一列）：圖表 → report＝嵌入報告（embedded_in，點選才顯）；role=main 且 report.md 沒引用的圖表徽章「報告未引用」</span>',
        '<span><span class="esw faint"></span>取代／引用／決策（點選或「顯示全部邊」才顯）</span>',
        '<span>可拖：問題拖到另一個帶或同帶另一個問題上；方法拖到問題上；敏感性子分析拖到別的方法上；結果可拖到別的方法或敏感性子分析（成為其主要／次要結果），或拖到 Main／Supplementary 帶再從下拉選落點（新增子分析、既有 R、別的 plan 的 outputs）；頂層主要結果拖到同 plan 的另一個頂層主要結果上＝掛到主結果下（成為支撐結果），支撐結果拖到所在帶的空白處＝拉回頂層、拖到別的結果上＝換主結果；active plan 拖到另一個問題的 active plan 上＝降為它的敏感性子分析（來源整份成為 R&lt;n+1&gt;、其結果變次要、來源問題無 active plan）；圖表拖到別的帶——放開後只送收件匣，或按「加入暫存」先留在本頁、連拖多次後一次預覽套用（虛線外框＝已暫存）</span>',
        '</div>',
        '<div id="graph-wrap">',
        _svg_graph(graph, notes),
        '</div>',
        f'<p class="notice">關聯圖：節點 {st["nodes"]}、邊 {st["edges"]}、問題間共用 {st["shared_pairs"]} 組、goals 指向不存在的結果鍵 {st["dangling_result_keys"]}、次要結果鍵 {st["secondary_result_keys"]}（聚合節點 {st.get("secondary_groups", 0)}）、未宣告 {st["undeclared_result_keys"]}、未驗證 {st["unvalidated_result_keys"]}、敏感性子分析 {st["sensitivity_items"]} 項、圖表 {st["by_type"].get("figure", 0)} 張（未審 {st["figures_unreviewed"]}；report.md 引用 {st.get("report_cited_figures", 0)}、主圖未引用 {st.get("report_uncited_main_figures", 0)}）；區帶 main {st["band_main_nodes"]} 節點、ext {st["band_ext_nodes"]} 節點、supp {st["band_supp_nodes"]} 節點、問題帶 {st.get("strips", 0)}、敏感性分析群 {st["sensitivity_groups"]} 組{"、支撐結果 " + str(st["supporting_result_keys"]) + " 鍵" if st.get("supporting_result_keys") else ""}；預設檢視線段交叉 {st["crossings"]}、穿過節點 {st["edge_node_overlaps"]}。欄序：主問題 → 問題（SQ／AQ）→ 方法（計畫版本；縮排＝敏感性子分析）→ 驗證 → 結果（主要逐鍵／有次要鍵的子分析一個次要結果節點／未宣告逐鍵）→ 圖表（最後一列 report.md）→ 決策；區帶由上而下 Main → Extended Data → Supplementary；舊版計畫預設收合。</p>',
        '<aside id="gdetail" hidden><button type="button" class="close" id="gdetail-close">關閉（Esc）</button><div id="gdetail-body"></div></aside>',
        '<div id="lightbox" hidden><img alt=""><div class="lb-cap"></div></div>',
        '</section>',
    ]
    return lines


def _inbox_block(ir: dict) -> list[str]:
    """頁首的收件匣狀態（兩個分頁共用）＋表單骨架；伺服器不在時按鈕 disabled。"""
    inbox = ir['inbox']
    labels = {n['id']: n['label'] for n in ir['graph']['nodes']}
    lines = []
    if inbox['present']:
        lines.append(f'<details id="inbox-banner"><summary>收件匣待處理 {inbox["pending"]} 筆（PROGRESS.inbox.yaml，共 {len(inbox["items"])} 筆）</summary>')
        pend = [it for it in inbox['items'] if it['status'] == 'pending']
        if pend:
            lines.append('<table><thead><tr><th>id</th><th>kind</th><th>target</th><th>title</th><th>at</th></tr></thead><tbody>')
            for it in pend:
                tgt = (f'<span class="goto" data-goto="{_h(it["target"])}">{_h(labels.get(it["target"], it["target"]))}</span>'
                       if it['target'] else '—')
                lines.append(f'<tr><td>{_h(it["id"])}</td><td>{_h(INBOX_KINDS.get(it["kind"], it["kind"]))}</td><td>{tgt}</td>'
                             f'<td>{_h(_clip(it["title"], 60))}</td><td>{_h(it["at"])}</td></tr>')
            lines.append('</tbody></table>')
        else:
            lines.append('<p class="src">沒有待處理的項目。</p>')
        lines.append('<p class="src">處理方式：status skill 逐筆呈使用者裁決後進 SSOT，再以 check_inbox.py --resolve／--dismiss 結案；'
                     '降階／圖表 role 兩種結構化項目由 reassign_question.py／set_figure_role.py 確定性執行（見下方「待套用動作」）。</p></details>')
    lines += _actions_panel(ir, labels)
    lines += [
        '<div class="inbox-actions"><button type="button" id="inbox-new" disabled title="用 progress_server.py 開啟才能送出">＋ 新問題／新分析</button>'
        '<span class="hint" id="inbox-hint">用 progress_server.py 開啟才能送出（file:// 頁面無法送表單）</span></div>',
        '<div id="inbox-form" hidden><form id="inbox-form-inner" autocomplete="off">',
        '<h3 id="inbox-form-title">送入收件匣</h3>',
        '<label for="inbox-kind">kind</label><select id="inbox-kind"><option value="new_question">新問題</option><option value="new_analysis">新分析</option><option value="comment">意見</option></select>',
        '<label for="inbox-target">target（節點）</label><select id="inbox-target"><option value="">（無）</option></select>',
        '<label for="inbox-title">title（一句話）</label><input id="inbox-title" maxlength="200">',
        '<label for="inbox-body">body（需求或意見全文）</label><textarea id="inbox-body" maxlength="5000"></textarea>',
        '<label for="inbox-author">author（選填）</label><input id="inbox-author" maxlength="100">',
        '<div class="err" id="inbox-err"></div>',
        '<div class="row"><button type="button" id="inbox-cancel">取消</button><button type="submit" id="inbox-submit">送出</button></div>',
        '</form></div>',
        '<div id="toast" hidden></div>',
    ]
    return lines


def _actions_panel(ir: dict, labels: dict) -> list[str]:
    """「待套用動作」面板（0.16.0；0.16.1 起六種 kind；0.16.2 起七種；0.16.5 起八種；0.18.0 起十種含 batch；0.20.0 起十一種）：列 pending 的結構化項目，每筆「預覽變更」「套用」「撤回」（0.18.2；撤回只要連上 server，不需 --allow-apply）；伺服器未開 --allow-apply
    或 file:// 開啟時按鈕停用並說明原因（JS 依 /api/ping 的 actions_enabled 啟用）。另附共用表單的骨架（每種 kind 一組欄位），0.16.3 起表單多一個
    預覽區 #act-preview-box（#act-summary 摘要、#act-dismiss 撤回／#act-keep 先留在收件匣／#act-apply 套用），送出後在同一個對話框顯示 dry-run 摘要。"""
    inbox = ir['inbox']
    acts = [it for it in inbox['items'] if it['status'] == 'pending' and it['kind'] in INBOX_ACTION_KINDS]
    kinds_txt = '／'.join(INBOX_KINDS[k] for k in INBOX_ACTION_KINDS)
    lines = ['<details id="staged-panel" open hidden><summary>暫存動作 <span id="staged-count">0</span> 項（只在本頁暫存、尚未送出；圖已先重排）</summary>',
             '<p class="hint">放開節點就直接列在這裡（各 kind 用預設值、圖立刻重排；要改 to／落點／理由按「編輯」；關聯圖控制列勾「放開時先開表單」則回到放開先填表單）。'
             '清單存在瀏覽器 localStorage，重新載入後還原。理由整批填一次、預覽後再填也可以（套用時才帶給 server；各項自己在「編輯」填的理由優先；都空則 D# 寫「使用者於進度頁面批次拖放（IN-xxx）」）。「全部預覽」把整串以一筆 batch 送進收件匣並在'
             '同一個工作區依序真跑（版本接力：後面的步驟自動改指前面步驟封出的新版）；「全部套用」才寫 SSOT——每步各記一筆 D#，中間不重畫、最後重畫一次。</p>',
             '<table><thead><tr><th>#</th><th>kind</th><th>target</th><th>內容</th><th>動作</th></tr></thead><tbody id="staged-body"></tbody></table>',
             '<div class="row"><label for="staged-reason">理由（整批，可空）</label><input id="staged-reason" maxlength="2000" placeholder="寫進每一步的 D# reason">'
             '<button type="button" id="staged-preview" disabled title="server 未開 --allow-apply">全部預覽</button>'
             '<button type="button" id="staged-apply" disabled title="先全部預覽">全部套用</button><span id="staged-apply-why">先全部預覽</span>'
             '<button type="button" id="staged-clear">清空暫存</button><span class="src" id="staged-batch-id"></span></div>',
             '<pre id="staged-summary" class="act-summary"></pre><div class="err" id="staged-err"></div></details>',
             '<div id="staged-old" hidden></div>',
             f'<details id="actions-panel" open><summary>待套用動作 {len(acts)} 筆（{kinds_txt}；由腳本確定性執行）</summary>',
             '<p class="hint" id="actions-hint">用 progress_server.py --allow-apply 開啟才能預覽與套用；預設 server 只寫收件匣。</p>',
             '<p class="hint" id="actions-dismiss-hint">撤回只改收件匣狀態，不動 SSOT（代跑 check_inbox.py --dismiss；不需 --allow-apply，連上 progress_server.py 就能用）。</p>']
    if acts:
        lines.append('<table><thead><tr><th>id</th><th>kind</th><th>target</th><th>內容</th><th>動作</th></tr></thead><tbody>')
        for it in acts:
            tgt = (f'<span class="goto" data-goto="{_h(it["target"])}">{_h(labels.get(it["target"], it["target"]))}</span>' if it['target'] else '—')
            lines.append(f'<tr data-act-id="{_h(it["id"])}"><td>{_h(it["id"])}</td><td>{_h(INBOX_KINDS.get(it["kind"], it["kind"]))}</td><td>{tgt}</td>'
                         f'<td>{_h(_clip(it["title"], 80))}<br><span class="src">{_h(_clip(it["body"], 160))}</span></td>'
                         f'<td><button type="button" class="act-preview" data-id="{_h(it["id"])}" disabled title="server 未開 --allow-apply">預覽變更</button> '
                         f'<button type="button" class="act-apply" data-id="{_h(it["id"])}" disabled title="先預覽">套用</button> '
                         f'<button type="button" class="act-dismiss-row" data-id="{_h(it["id"])}" disabled title="用 progress_server.py 開啟才能撤回（file:// 或未連上伺服器）">撤回</button>'
                         f'<pre class="act-summary" data-id="{_h(it["id"])}"></pre></td></tr>')
        lines.append('</tbody></table>')
    else:
        lines.append('<p class="src">沒有待套用的結構化項目。在關聯圖拖節點就會產生一筆：問題拖到另一個帶（降階／升回）或同帶另一個問題上（調順序）、'
                     '方法拖到問題上（搬方法）、方法拖到別的方法上（降為敏感性子分析）、敏感性子分析拖到別的方法上（搬敏感性子分析）、結果拖到別的方法或敏感性子分析上（搬結果）、圖表拖到別的帶（改 role）、'
                     '方法／敏感性子分析／主要結果／驗證拖到 Extended Data 帶（放入 ED）或從 ED 帶拖回原帶（移出 ED；問題節點不能放）；'
                     '連續拖放多次可先「加入暫存」，最後在「暫存動作」面板一次預覽、一次套用（batch）。</p>')
    lines.append('</details>')
    lines += [
        '<div id="act-form" hidden><form id="act-form-inner" autocomplete="off">',
        '<h3 id="act-form-title">降為附錄問題</h3>',
        '<div id="act-reassign-fields"><label for="act-from">from（主問題）</label><input id="act-from" readonly>',
        '<label for="act-to">to（附錄問題 id；留空＝下一個 AQ 號）</label><input id="act-to" maxlength="10" placeholder="AQ5">',
        '<label for="act-pm">primary_model（選填；改主結果、原 primary 降為敏感度）</label><select id="act-pm"><option value="">（不改）</option></select></div>',
        '<div id="act-promote-fields" hidden><label for="act-p-from">from（附錄問題）</label><input id="act-p-from" readonly>',
        '<label for="act-p-to">to（主問題 id；留空＝回原號（若空著）或下一個 SQ 號）</label><input id="act-p-to" maxlength="10" placeholder="SQ2"></div>',
        '<div id="act-move-plan-fields" hidden><label for="act-mp-plan">plan（要搬的 active plan）</label><input id="act-mp-plan" readonly>',
        '<label for="act-mp-to">to_question（目標問題；須沒有 active plan）</label><input id="act-mp-to" readonly></div>',
        '<div id="act-move-sens-fields" hidden><label for="act-ms-plan">plan（來源）</label><input id="act-ms-plan" readonly>',
        '<label for="act-ms-item">item（要搬的 robustness 項目）</label><input id="act-ms-item" readonly>',
        '<label for="act-ms-to">to_plan（目標 plan；追加為 R&lt;n+1&gt;）</label><input id="act-ms-to" readonly></div>',
        '<div id="act-demote-plan-fields" hidden><label for="act-dp-plan">plan（要降階的附錄問題 active plan）</label><input id="act-dp-plan" readonly>',
        '<label for="act-dp-to">to_plan（目標 active plan；來源整份成為其 R&lt;n+1&gt;，來源自己的子分析接在後面）</label><input id="act-dp-to" readonly></div>',
        '<div id="act-set-tier-fields" hidden><label for="act-st-node">node（方法／敏感性子分析／主要或未宣告結果／驗證的節點 id）</label><input id="act-st-node" readonly>',
        '<label for="act-st-tier">tier（extended＝放入 Extended Data；空＝移出、回推導區帶）</label><input id="act-st-tier" readonly></div>',
        '<div id="act-move-result-fields" hidden><label for="act-mr-key">key（要搬的結果鍵）</label><input id="act-mr-key" readonly>',
        '<label for="act-mr-to">to_plan（目標 plan）</label><input id="act-mr-to" readonly>',
        '<div id="act-mr-dest-wrap" hidden><label for="act-mr-dest">放到哪裡（拖到區帶時選）</label><select id="act-mr-dest"></select></div>',
        '<label for="act-mr-item">to_item（目標敏感性子分析；空＝搬到 outputs；新增子分析時為新的 R）</label><input id="act-mr-item" readonly></div>',
        '<div id="act-nest-result-fields" hidden><label for="act-nr-key">key（要掛的結果鍵）</label><input id="act-nr-key" readonly>',
        '<label for="act-nr-under">under（主結果的鍵；空＝拉回頂層）</label><input id="act-nr-under" readonly></div>',
        '<div id="act-reorder-fields" hidden><label for="act-ro-list">list</label><input id="act-ro-list" readonly>',
        '<label for="act-ro-order">order（新順序）</label><input id="act-ro-order" readonly></div>',
        '<div id="act-role-fields" hidden><label for="act-fig">figure</label><input id="act-fig" readonly>',
        '<label for="act-role">role</label><select id="act-role"><option value="main">main（Main 主圖）</option><option value="extended">extended（Extended Data）</option><option value="supplementary">supplementary（Supplementary）</option></select></div>',
        '<label for="act-reason">理由（選填，寫進收件匣與決策 reason）</label><textarea id="act-reason" maxlength="2000"></textarea>',
        '<p class="src">按「送出並預覽」先在 PROGRESS.inbox.yaml 加一筆，接著立刻代跑腳本 --dry-run（不寫檔）把變更摘要顯示在這裡；看過摘要再決定套用、先留在收件匣或撤回。</p>',
        '<div class="err" id="act-err"></div>',
        '<div class="row" id="act-submit-row"><button type="button" id="act-cancel">取消</button>'
        '<button type="button" id="act-stage" title="不呼叫 server：推進本頁的暫存清單、圖立刻重排；之後在頁首「暫存動作」面板一次預覽、一次套用">加入暫存</button>'
        '<button type="submit" id="act-submit" title="只送這一項進收件匣並立刻預覽（0.16.3 的單動作流程）">單獨送出並預覽</button></div>',
        '<div id="act-preview-box" hidden><p class="hint">已送入收件匣 <b id="act-item-id"></b>。變更預覽（腳本 --dry-run 的輸出，還沒寫任何檔）：</p>',
        '<pre id="act-summary" class="act-summary"></pre>',
        '<div class="row"><button type="button" id="act-dismiss" title="標 dismissed（代跑 check_inbox.py --dismiss），不改 SSOT">撤回</button>'
        '<button type="button" id="act-keep" title="關掉對話框，項目留在收件匣 pending；之後可在「待套用動作」面板預覽與套用">先留在收件匣</button>'
        '<button type="button" id="act-apply" disabled title="先預覽">套用</button></div></div>',
        '</form></div>',
    ]
    return lines


def _current_label(stage_id: str, stage_label: dict) -> str:
    if not stage_id:
        return '（state.next_stage 未填）'
    # 專案層若有同名站（analyze-data:rerun／evaluate:full），以專案層 label 為準，與「目前」外框一致
    label = stage_label.get(stage_id + ':rerun') or stage_label.get(stage_id + ':full') or stage_label.get(stage_id, '')
    return f'{_h(label)}（{_h(stage_id)}）' if label else _h(stage_id)


def render_html(ir: dict, root: Path, notes: list[str] | None = None) -> str:
    p = ir['project']
    st = ir['stats']
    by = st['by_state']
    payload = json.dumps(ir, ensure_ascii=False, indent=2).replace('<', '\\u003c')
    stage_label = {s['id']: s['label'] for s in ir['stages']}
    lines = [
        f'<!DOCTYPE html>',
        '<html lang="zh-Hant">',
        '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>{_h(p["title"])} 研究問題里程圖</title>',
        f'<style>{CSS}{GRAPH_CSS}{LIT_CSS}{SUB_CSS}</style>',
        '</head>',
        '<body>',
        '<header>',
        f'<h1>{_h(p["title"])} 研究問題里程圖</h1>',
        f'<p class="rq">主問題：{_h(p["research_question"]) or "（project.yaml 未填 research_question）"}</p>',
        f'<p>目前站：{_current_label(p["current_stage"], stage_label)}</p>',
        f'<p>產生時間：{_h(ir["generated_at"])}</p>',
        f'<p>來源路徑：<code>{_h(ir["project_root"])}</code></p>',
        f'<p class="notice">本檔由 {SCRIPT_REL} 自動產生，請勿手動編輯；要改內容請改對應的 SSOT 檔再重跑。</p>',
        '</header>',
        *_inbox_block(ir),
        '<nav class="tabs"><button type="button" data-tab="milestones" class="active">里程</button><button type="button" data-tab="relations">關聯</button><button type="button" data-tab="literature">文獻</button><button type="button" data-tab="submission">投稿檔案</button></nav>',
        '<section id="tab-milestones">',
        '<div class="controls">',
        '<span>顯示 state：</span>',
    ]
    for s in STATES:
        lines.append(f'<label><input type="checkbox" data-state="{s}" checked> <span class="dot {s}"></span> {STATE_ZH[s]}</label>')
    lines += [
        '<label style="margin-left:auto"><input type="checkbox" id="toggle-annot"> 顯示決策註記</label>',
        '</div>',
        '<div class="legend">',
        '<span><span class="dot done"></span> 完成（實心）</span>',
        '<span><span class="dot expired"></span> 過期（半圓）</span>',
        '<span><span class="dot blocked"></span> 受阻（叉）</span>',
        '<span><span class="dot pending"></span> 未到（空心）</span>',
        '<span><span class="dot unknown"></span> 不明（虛線）</span>',
        '<span>外框藍色＝目前站</span>',
        '</div>',
        f'<h2>專案層（{len(PROJECT_STAGES)} 站）</h2>',
        _matrix(ir, 'project'),
        f'<h2>研究問題（每條 {len(SQ_STAGES)} 站）</h2>',
        _matrix(ir, 'sq'),
        '<aside id="detail" hidden><button type="button" class="close" id="detail-close">關閉（Esc）</button><div id="detail-body"></div></aside>',
        '</section>',
    ]
    lines += _relations_tab(ir, notes)
    lines += _literature_tab(ir)
    lines += _submission_tab(ir, notes)
    gs = ir['graph']['stats']
    lines += [
        '<footer>',
        f'<p>泳道 {st["lanes"]}、節點 {st["nodes"]}：完成 {by["done"]}、過期 {by["expired"]}、受阻 {by["blocked"]}、未到 {by["pending"]}、不明 {by["unknown"]}；決策註記 {st["annotations"]}。</p>',
        f'<p>關聯圖：節點 {gs["nodes"]}、邊 {gs["edges"]}、問題間共用 {gs["shared_pairs"]} 組、goals 指向不存在的結果鍵 {gs["dangling_result_keys"]}、未驗證的結果鍵 {gs["unvalidated_result_keys"]}、次要 {gs["secondary_result_keys"]}（聚合節點 {gs.get("secondary_groups", 0)}）、未宣告 {gs["undeclared_result_keys"]}、敏感性子分析 {gs["sensitivity_items"]} 項、圖表 {gs["by_type"].get("figure", 0)} 張（未審 {gs["figures_unreviewed"]}；report.md 引用 {gs.get("report_cited_figures", 0)}）；區帶 main {gs["band_main_nodes"]} 節點、ext {gs["band_ext_nodes"]} 節點、supp {gs["band_supp_nodes"]} 節點、敏感性分析群 {gs["sensitivity_groups"]} 組{"、支撐結果 " + str(gs["supporting_result_keys"]) + " 鍵" if gs.get("supporting_result_keys") else ""}；預設檢視線段交叉 {gs["crossings"]}、穿過節點 {gs["edge_node_overlaps"]}。</p>',
        '<p>資料維護狀況：</p><ul>',
    ]
    for lane in ir['lanes']:
        done = sum(1 for n in lane['nodes'] if n['state'] == 'done')
        lines.append(f'<li>{_h(lane["label"])}：完成 {done}／{len(lane["nodes"])} 站</li>')
    lines += [
        '</ul>',
        '</footer>',
        '<script id="progress-ir" type="application/json">',
        payload,
        '</script>',
        f'<script>{JS}</script>',
        f'<script>{GRAPH_JS}</script>',
        f'<script>{LIT_JS}</script>',
        f'<script>{SUB_JS}</script>',
        '</body>',
        '</html>',
    ]
    return '\n'.join(lines) + '\n'


# ---------- 統計與主程式 ----------

def stats_line(ir: dict) -> str:
    st = ir['stats']
    by = st['by_state']
    gs = ir['graph']['stats']
    return (f'泳道 {st["lanes"]}、節點 {st["nodes"]}：完成 {by["done"]}、過期 {by["expired"]}、'
            f'受阻 {by["blocked"]}、未到 {by["pending"]}、不明 {by["unknown"]}；決策註記 {st["annotations"]}。'
            f'關聯圖：節點 {gs["nodes"]}、邊 {gs["edges"]}、問題間共用 {gs["shared_pairs"]} 組、'
            f'goals 指向不存在的結果鍵 {gs["dangling_result_keys"]}、未驗證的結果鍵 {gs["unvalidated_result_keys"]}、'
            f'次要 {gs["secondary_result_keys"]}（聚合節點 {gs.get("secondary_groups", 0)}）、未宣告 {gs["undeclared_result_keys"]}、敏感性子分析 {gs["sensitivity_items"]} 項、'
            f'圖表 {gs["by_type"].get("figure", 0)} 張（未審 {gs["figures_unreviewed"]}；report.md 引用 {gs.get("report_cited_figures", 0)}）；'
            f'區帶 main {gs["band_main_nodes"]} 節點、ext {gs["band_ext_nodes"]} 節點、supp {gs["band_supp_nodes"]} 節點、'
            f'問題帶 {gs.get("strips", 0)}、敏感性分析群 {gs["sensitivity_groups"]} 組' + (f'、支撐結果 {gs["supporting_result_keys"]} 鍵' if gs.get('supporting_result_keys') else '')
            + f'；預設檢視線段交叉 {gs["crossings"]}、穿過節點 {gs["edge_node_overlaps"]}。'
            f'收件匣待處理 {ir["inbox"]["pending"]}。'
            + _lit_stats_line(ir.get('literature') or {}))


def _lit_stats_line(lit: dict) -> str:
    if not lit.get('present'):
        return f'文獻圖：{lit.get("source", LIT_REL)} 不存在（分頁顯示空狀態）。'
    counts = lit.get('edges') or {}
    demo = '（示範資料）' if lit.get('demo') else ''
    edges = '、'.join(f'{k} {v} 條' for k, v in sorted(counts.items())) or '無連線'
    return f'文獻圖{demo}：節點 {lit.get("nodes", 0)}、{edges}。'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='研究問題里程圖：唯讀 SSOT → PROGRESS.ir.json → PROGRESS.html')
    parser.add_argument('root', help='academic-pipeline 專案根目錄')
    parser.add_argument('--dry-run', action='store_true', help='不寫檔；單獨使用時把 HTML 印到 stdout')
    parser.add_argument('--json', action='store_true', help='stdout 改印 IR JSON')
    parser.add_argument('--ir-only', action='store_true', help='只寫 PROGRESS.ir.json、不寫 PROGRESS.html')
    parser.add_argument('--embed-figures', action='store_true',
                        help='把圖檔（svg／png，單檔 ≤ 5 MB）以 data URI 內嵌進圖表節點 meta.data_uri；預設不內嵌')
    parser.add_argument('--literature-graph', default=None, metavar='PATH',
                        help=f'文獻引用 3D 圖的資料檔；預設 <root>/{LIT_REL}。缺檔時分頁照出、顯示空狀態')
    args = parser.parse_args(argv)

    quiet_stdout = args.dry_run or args.json
    diag = sys.stderr if quiet_stdout else sys.stdout

    root = Path(args.root)
    if not root.is_dir():
        print(f'BLOCKER 專案根目錄不存在: {args.root}', file=diag)
        return 2
    root = root.resolve()
    if not quiet_stdout:
        print(f'=== render_progress: {root} ===')

    src = Sources(root)
    generated_at = dt.datetime.now().astimezone().isoformat(timespec='seconds')
    lit_path = Path(args.literature_graph).expanduser() if args.literature_graph else None
    ir = build_ir(root, src, generated_at, args.embed_figures, lit_path)
    for w in src.warnings:
        print(f'WARNING {w}', file=diag)
    for i in src.infos:
        print(f'INFO {i}', file=diag)

    errors = validate_ir(ir)
    if errors:
        for e in errors:
            print(f'BLOCKER IR 驗證失敗: {e}', file=diag)
        return 2

    ir_text = json.dumps(ir, ensure_ascii=False, indent=2) + '\n'
    notes: list[str] = []
    html_text = render_html(ir, root, notes) if not (args.json and args.dry_run) else ''
    for note in notes:
        print(f'INFO {note}', file=diag)
    if args.json:
        sys.stdout.write(ir_text)
        sys.stdout.flush()
    elif args.dry_run:
        sys.stdout.write(html_text)
        sys.stdout.flush()
    if args.dry_run:
        return 0

    ir_path = root / IR_NAME
    ir_path.write_text(ir_text, encoding='utf-8', newline='\n')
    if not args.json:
        print(f'{IR_NAME} 已寫入: {ir_path}')
    if not args.ir_only:
        html_path = root / HTML_NAME
        html_path.write_text(html_text, encoding='utf-8', newline='\n')
        if not args.json:
            print(f'{HTML_NAME} 已寫入: {html_path}')
    if not args.json:
        print(stats_line(ir))
        print('結果: 完成')
    return 0


if __name__ == '__main__':
    sys.exit(main())
