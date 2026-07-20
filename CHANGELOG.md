# CHANGELOG

## 0.8.1（2026-07-20）

兩個確定性缺陷的修補。skills（24）、agents（18）與管線階段不變，無新功能、無破壞性變更，故為 PATCH bump。

1. **`check_results_schema.py`：`output_contract` 排除被取代的 plan**。建 contract 時只走 `index.yaml` 的 `plans` 清單而未看 `status`／`active`（`active_ids` 有過濾、contract 沒有），被 `seal_artifact.py` 標為 `superseded` 的舊版仍能宣告結果鍵歸屬。因 `output_contract` 是 dict、後寫覆蓋前寫，而 index 是 append 累積，跨 SQ 撞鍵時較晚封存的 superseded 版本會把歸屬從 active plan 手上搶走，報出 `plan_id 應為 <舊版>` 這種指向錯方向的 blocker——殘留在 index，訊息卻在指控 result。新增 `plan_owns_keys()`：`status: superseded` 或不在 `active` map 內的 plan 一律不得宣告鍵；所有版本仍載入 `plan_docs`，讓「plan_id 非 active plan」保有精確診斷。舊 index 無 `status` 欄或無 `active` map 時兩條件皆不成立，回溯相容。
   - 副作用值得記一筆：此 bug 當時的唯一解法是把鍵移出 `results.json`，而那等於把數字移出稽核範圍——`check_numbers.py` 不再對稿件比值、clean-room rerun 不再逐鍵比對、該鍵退出 `results_fingerprint`。一個要靠縮小稽核範圍才能轉綠的關卡，失敗方向是錯的那一邊。
2. **YAML 裸日期序列化崩潰：所有吃 YAML 的雜湊點一律加 `default=str`**。`routed_at: 2026-07-20` 不加引號會被 `yaml.safe_load` 解析成 `datetime.date`，`json.dumps` 直接拋 TypeError 崩潰，而不是回報 blocker。這不是單點問題——追下去共有六支腳本的雜湊點暴露在 YAML 輸入上，其中三處實測會崩潰：
   - `rerun_all.py`（`project.yaml#analysis-subset`，涵蓋 `pipeline`／`project`／`goals`／`data`／`analysis`／`methodology` 任一裸日期，不只 `routed_at`）；
   - `check_gate.py`（`canonical_hash`／`add_semantic`，其 `project.yaml#consistency-subset` 同樣含 `methodology`——只修 rerun_all 等於只修好回報路徑的一半）；
   - `plan_common.py::content_hash`（封存計畫的內容雜湊，而 `analysis-plan-template.yaml` 教的 `created_at` 正是裸日期）；
   - 另同步加固 `check_claim_audit.py`、`check_evidence.py`／`seal_evidence_protocol.py`、`check_coverage.py --update-snapshot` 等 YAML 輸入路徑。

   對現行可序列化的輸入 `default` 永不觸發，既有 hash／fingerprint 位元不變；而加引號與不加引號會產生相同結果，事後補引號不會使既有 fingerprint 或封存 `content_hash` 失效。
3. **文件與範本不再教出會崩潰的寫法**。`methodology-router/SKILL.md` 的 `routed_at: 2026-07-14` 正是觸發缺陷 2 的寫法；`study-protocol-template.yaml`、`analysis-plan-template.yaml` 的 `created_at` 與 `exploration-log-template.yaml` 的 `date` 同樣是裸日期。全部改為字串並在 SKILL.md 說明原因（腳本端已兜底，但寫入端仍以字串為準）。
4. **測試**：新增 `tests/run_v081_regressions.py`（10 項）——以**實際執行腳本**（非錨點字串）斷言：superseded plan 不再搶走跨 SQ 撞鍵的歸屬、未宣告鍵的 blocker 改為指向 plan、無 `status`／無 `active` map 的舊 index 回溯相容、裸日期不再讓 `rerun_all`／`check_gate`／`content_hash` 崩潰、有無引號產生相同 fingerprint 與相同 `content_hash`、全 repo 掃描無殘留的裸日期範本、SKILL.md 已改寫、`plugin.json` 精確為 `0.8.1`。所有新斷言均先對未修補版本執行確認會失敗（測試有牙），mini-project 黃金答案不變。`run_v080_regressions.py::test_docs_and_version` 由精確 `== "0.8.0"` 改為單調 `>= (0,8,0)`，當期精確版號改由 `run_v081` pin（沿用 0.7.3→0.8.0 的既有慣例）。既有五支測試全部通過。
   - 為何既有測試沒擋下缺陷 2：`tests/run_v07_smoke.py` 寫入的是 `"routed_at": "2026-07-14"`（Python 字串，序列化成有引號的 YAML），跑的是有引號路徑；SKILL.md 教的卻是無引號路徑。測試與文件互相矛盾，全綠不代表文件所教的用法可行。

## 0.8.0（2026-07-16）

英文潤稿站由「選用外部 user skill」升為**本 plugin 內建 skill**。skills（23→**24**）；agents（18）與管線階段不變。無破壞性變更，故為 MINOR bump。

1. **新增 `skills/academic-english-editing`**：內建英文學術潤稿站，清除 AI 生成痕跡（AI tells）、對齊學術慣例與期刊語域、貼合作者語氣。內容來源逐節標註：Layer 1／2／3／5、核心原則與流程源自 user skill `academic-humanizer` v0.3.3（MIT），以〔來源：academic-humanizer v0.3.3 · …〕標示；掛點合約與「不含 Layer 4」兩節為 academic-pipeline 專屬新增，標為〔來源：academic-pipeline 潤稿站合約〕。
2. **刻意不納入 Layer 4（claim-evidence discipline）**：原 Layer 4 會降級動詞、softening 過度主張，**改變 claim strength**，違反潤稿站「只改語言呈現」合約；其職責在 pipeline 內本就由 `claim-audit`／`interpret-results`／`check_numbers.py` 承擔。本站發現 over-claim 只標記回 claim-audit，不自行改稿。
3. **掛點內建化**：`translate-en` 第 6 步與 `status` 的潤稿站敘述由「外部 user skill、未安裝自動略過」改為「本 plugin 內建、選用」；掛點合約（不得改數字／`<!-- -->` markers／`[@citekey]`／claim strength／validation boundary／方法語意；潤稿後重跑 `check_markers.py`＋跨語意回查＋reviewer-language＋人工英文確認＋full `check-consistency(en)`）與後續 gate 完全不變。中文潤稿站 `chinese-deai-editing` 維持外部選用，未動。
4. **提案模式抽出、不隨 plugin**：`academic-humanizer` 的 Layer 6（NSF／NIH 提案模式，含 6.1–6.5 claim↔feasibility）與線性研究→投稿流程正交，抽為獨立 skill `grant-proposal-editing` 單獨交付。
5. **測試**：新增 `tests/run_v080_regressions.py`——驗內建 skill 存在、掛點合約與 provenance 標註、Layer 4 排除、translate-en／status 措辭改為內建、中文潤稿站仍為外部、`plugin.json` 版本精確為 `0.8.0`。`run_v073_regressions.py::test_version_bump` 由精確 `== "0.7.3"` 改為單調 `>= (0,7,3)`，當期精確版號改由 `run_v080` pin；既有四支回歸測試全部通過。

## 0.7.3（2026-07-15）

主問題與附錄問題（穩健性／敏感度／跨方法）在 `goals` 中結構分離、不混列。skills（23）與 agents（18）數量不變，無新增管線階段。

1. **`goals.appendix_questions` 新區塊**：`project-template.yaml` 於 `goals` 下新增 `appendix_questions`（預設 `[]`，欄位結構同 `sub_questions`，id 用 `AQ#`）。判準：問「現象」（關聯／機制／邊界）→ `sub_questions`；問「分析本身」（換方法／換設定下主結果是否維持、跨方法收斂或分歧）→ `appendix_questions`。附錄問題 defend 主答案而非產生新答案，報在附錄／SI。`pipeline.version` → 0.7.3；缺此鍵對舊專案回溯相容（視同 `[]`）。
2. **拆解與覆蓋只認 `sub_questions`**：`project-init` 分解步驟新增「主問題與附錄問題分離、不得混進 `sub_questions` 灌大 SQ 數」規則；`evaluate` 的 `decomposition-review` 與 `full` 目標覆蓋限縮於 `sub_questions`，附錄問題不計入主覆蓋、不能以其 `addressed` 補主問題缺口。
3. **附錄問題仍受機械把關**：`check_coverage.py` 讀 `appendix_questions`，套用同一套逐項 integrity 檢查（終態、links 有效、`addressed` 須有 links），在報告另段呈示，並納入 `--snapshot` 竄改偵測；不進裁決史與稿件收錄檢查。證據鏈斷不斷不因層級豁免。
4. **快照格式升級且回溯相容**：`--snapshot` 可讀舊版裸 list（僅 `sub_questions`）；`--update-snapshot` 起寫為 `{sub_questions, appendix_questions}` 物件。`run_v072_regressions.py::test_version_bump` 改為單調 `>=` 斷言，當期精確版號改由最新一支回歸測試 pin。
5. **測試**：新增 `tests/run_v073_regressions.py`——驗 schema 區塊與分離語意、project-init/evaluate 規則錨點、`check_coverage.py` 對附錄問題的 integrity（links 斷→BLOCKER）／另段呈示／不頂替主問題／無鍵回溯相容／快照涵蓋與讀舊快照。回歸測試現有四支全部通過。

## 0.7.2（2026-07-14）

以 v0.6 的文件結構與規則密度為基準，回填 v0.7.0 重寫核心 SKILL／agent 時流失、且不在 0.7.1 自承四項之列的條款；並修掉兩個實質功能缺口。skills（23）與 agents（18）數量不變，無新增管線階段。

### 回填的規則條款（v0.6 有、v0.7.1 無）

1. **code-review 不得用風格擋路**：`agents/reviewer-methods.md` 回填「查核限縮在正確性——程式是否忠實實作預先宣告的計畫；命名／排版／重構等風格類意見一律 suggestion，不得列 blocker」，並回填 strictness（normal／harsh）與 emphasis 加重規則。
2. **evaluate 的短路規則**：`full` 模式下第一層腳本有 blocker → 直接判未通過，不啟動 evaluator agent。一併回填 Fallback（無 subagent 時逐項自評並標「⚠ 自評」）、「拆解審不是凍結關卡」、收尾 `--update-snapshot`，以及「評估結果中立」「SQ 迴圈不設保險閥硬停」兩條設計理由。
3. **decisions.yaml 的三類記錄規則與 D# 觸發條件**：`project-init` 回填完整 schema（人工確認點的取捨／推翻 agent 建議／方向性選擇）與「推翻既有決策先呈示原 D# 條目、經確認才以 supersedes 落地」的跨 session 防翻案機制。
4. **write-manuscript 的數字標註豁免清單**：v0.7.1 刪了撰稿端規則但 `check_numbers.py` 照舊執法。本版依**現行腳本行為**（非 v0.6 原文）重寫豁免清單：`display` 優先、結構性編號與程式碼區塊完全豁免、裸整數與「同句有 citekey 的他人數值」降級為 warning、無 citekey 的資料型數字為 blocker。
5. **data-analyst 四條核心原則**：前提假設必檢、不確定度必報（模擬附收斂性檢查）、承重敏感度必做（改為執行 active plan 的 `robustness` 宣告，未宣告則回 study-design 建 amendment）、一切數字經 script 產出（禁止手算／心算／對話估算）。
6. **fact-checker 的能力與門檻**：`tools` 回填 Bash（系統性比對需寫臨時 script）、回填「blocker 未清空即為未通過」與「機械比對已由四支腳本完成，不重複逐字比對」的分工前提。
7. **reviewer 席位**：回填 strictness／emphasis、範圍凍結的操作定義（未變更段落的新意見至多 suggestion）、「不得空泛讚美、不得只挑格式小錯充數」。
8. **interpreter／interpret-results**：回填無錨主張處置（confirmed 無錨為 warning 而非 blocker；`origin: E#` 轉正 SQ 從嚴）、分級不對稱（調降隨時可以、調升須有依據）、null 需 equivalence 時回呼 analyze-data、權限邊界。八級 strength 為 v0.7 刻意設計，維持不動。
9. **analyze-data 的資料品質關卡**：回填 `init_manifest.py` 建檔與「有疑慮（如可疑離群值）必須先問使用者，不得自行剔除資料」；與 data-audit 的分工寫死（data-audit 管獨立稽核與 data-profile，analyze-data 管 manifest 的樣本流向與筆數守恆），並修掉 `data-audit/SKILL.md` 對 `init_manifest.py` 的懸空引用。
10. **submission-prep／translate-en**：回填「動手前上網查證期刊最新 author guidelines」、repro package 四項防呆（README【請人工補】逐項確認、依賴掃描、隨機種子 warning、`data/` 不自動隨包）、增量重譯禁令（整篇重翻成本失控）、`[TERM?]` 暫定標記、回譯每節抽 2–3 句、SI 需再跑一次 `check_markers`。
11. **project-template.yaml 註解密度**：v0.7.1 把模板註解幾乎刪光（6.8KB → 3.1KB）。本版逐欄回填（10.6KB），欄位集合與 v0.7.1 完全相同（missing 0、added 0），含 goals 兩條硬規則、`rounding`＋`display` 覆寫、`rerun` 三檔與 off 需 D#、`review.panel` 的 S1–S4／persona 結構／指定學者須核可、`converged` 語意，並替 v0.7 新欄位補上註解。

### 修掉的功能缺口

12. **文獻型 SQ 的 `cite:` links 沒有 producer（實質 bug）**：v0.6 由 lit-review 收尾把 `cite:<citekey>` 寫進 `goals[].links`；v0.7.1 壓縮後此步驟消失，但 `evaluate` 的 full 硬前置與 `check_coverage.py` 仍要求 links——`evidence: [literature]` 的 SQ 一旦 addressed 就必然 BLOCKER，永遠過不了 full 評估。本版把寫入者寫死為單一責任：`focused` 模式由 lit-review 收尾寫入，`systematic`／`scoping`／`meta-analysis` 模式由 evidence-synthesis 寫入。
13. **未經審查的 citekey 可充當證據鏈**：`check_coverage.py` 新增 `--evidence <evidence-synthesis.yaml>`——傳入時，每個 `cite:<key>` 的 citekey 必須出現在 `studies[].citekey`（即已過篩選與偏誤評估），否則 BLOCKER；未傳旗標或檔案不存在則略過（focused 模式與舊專案回溯相容）。這是唯一的腳本修改。
14. **`display` 欄位的孤兒功能**：`check_numbers.py` 強制「稿件數字與 `display` 完全一致」，但 v0.7.1 已無任何 agent／skill 被要求產生此欄位。本版把契約接回 data-analyst（產生端）、write-manuscript（使用端）與 project-template（`rounding` 註解）。

### 測試

15. 新增 `tests/run_v072_regressions.py`：以跨檔案錨點驗證上述回填條款（agent 紅線、短路規則、決策日誌、數字豁免、模板註解），並實測 `check_coverage.py --evidence` 的四種情境（不傳旗標、已審查、未審查、檔案不存在）。回歸測試現有三支：`run_v07_smoke.py`、`run_v071_regressions.py`、`run_v072_regressions.py`，全部通過。

## 0.7.1（2026-07-14）

1. **修正 legacy consistency 反向相容 bug**：`check_gate.py` 改以 `pipeline.version` 選擇相容／strict 分支；v0.6 已有 `{result, version}` 的 pass state 不再因缺 `gate_fingerprint` 或 `report` 被擋。新增 populated legacy、empty legacy、explicit strict 三類回歸測試。
2. **恢復 review score producer contract**：新增 `record_review_score.py`，驗證 editor 的固定 `REVIEW_SCORE` YAML block，對每個完整 panel 輪依 round 去重寫入 `state.review.scores`；minor re-check 不新增。分數落帳後再次執行 `check_ledger.py`，使邊際遞減保險閥實際可觸發。
3. **恢復中文潤稿外部掛點**：`chinese-deai-editing` 回到 README、status、peer-review 與 revise 路由；未安裝自動略過，潤稿後重跑 full consistency。英文 `academic-english-editing` 掛點同步補回完整防護條款。
4. **恢復 editor 分數帶定錨**：補回 1–3／4–5／6–7／8–10 共同基準、contribution 的新穎性／定位敘事子問題、跨模型不可比規則與 machine-readable score block。
5. **補語意回歸測試**：新增 `tests/run_v071_regressions.py`，檢查上述四項跨檔案契約，避免只靠 file-count／frontmatter／新功能 smoke test 判定無退步。

## 0.7.0（2026-07-14）

1. **方法學路由與七種 adapter**：新增 methodology-router skill/agent，支援定量推論、預測／ML、質性、混合方法、系統性回顧／統合分析、模擬計算、理論數學；每個 adapter 定義 gates、plan/data/validation contract 與 interpretation limits。
2. **版本化 study-design**：新增 research-designer、protocol 與 per-SQ plans；confirmed artifacts 以 content hash 封存，plan amendment 以新版本與 supersedes 管理；新增 init/seal/check scripts。
3. **獨立 data-audit**：新增 data-auditor、raw-data fingerprint/profile、資料語意與治理檢核；audit 過期與未解 blocker 機械擋下正式分析。
4. **clean-room rerun 改寫與順序修正**：rerun 移至 code-review 前；暫存環境不複製 baseline results/derived/figures/reports/validation/manuscripts；fingerprint 納入 data、完整 scripts surface、run-order declared inputs、plans、audit/config/environment，輸出 machine-readable report。
5. **results schema 強化**：每筆 result 必須連 plan/model/data fingerprint；推論結果使用結構化 CI/SE/statistic/p/multiplicity 欄位；新增 schema checker。
6. **獨立 validate-results**：新增 statistical-validator 與 results-based validation contract 與完整 source fingerprint；另提供 qualitative/review/mixed/proof adapter validation contract 與 source fingerprint。
7. **可重現 evidence-synthesis**：新增 evidence-auditor、可封存搜尋 protocol、screening/risk-of-bias/certainty/conflicting evidence/citation-entailment artifacts 與 checker。
8. **獨立 claim-audit**：新增 claim-critic；interpreter 只起草，audit 以 claims 語意 + 上游 source fingerprints 防止過期；confirmed claim 強制 boundary、counterevidence 與 validation links。
9. **研究完整性雙關卡**：新增 integrity-officer 與 prestudy/presubmission 模式；倫理、資料權利、作者／CRediT／COI、圖像、data/code/AI disclosure、外部相似度狀態皆有明確 evidence contract。
10. **英文全量一致性 gate**：英文人工確認後強制 full check-consistency(en)；新增 gate fingerprint，任何稿件或承重 artifact 變動即使舊 pass 失效；排除 presubmission register 的循環失效但保留稿件／設定變更偵測。
11. **狀態路由整合**：project-init、analyze-data、evaluate、interpret-results、write、review、translate、submission-prep、status 皆更新；決策日誌認得所有 v0.7 新 skill。
12. **測試與相容**：保留 v0.6 黃金答案；新增 v0.7 七 adapter 與端到端 smoke tests。舊專案未升版時，新 checker 僅提示，不無條件阻擋。

## 0.6.0（2026-07-13）

依《academic-pipeline 修改規格（整合版 v3）》全批施工，涵蓋十三項功能：

1. **三席全文 persona 審稿**：reviewer-domain／reviewer-writing 移除，單一 `agents/reviewer.md` 承接全席；席位可指定學者（著作萃取 profile、使用者核可、記 D#）、editor 於引用網絡內提名、或內建通用三席（persona profile 隨 plugin 附）。三條紅線（disclaimer、禁第一人稱冒名、profile 經人核可）；互補性呈示；matrix 新鮮度檢查。
2. **editor 七維評分卡與裁決函數**：守門地板（method／argument／goal_fit）＋contribution 兼 reject 判準（新穎性 vs 定位敘事兩子問題，對照 novelty statement）；合議缺口 editor 補查；裁決依序 reject／major／accept／minor。
3. **議題帳本與終止機制**：`reviews/issue-ledger.yaml`＋`check_ledger.py`；minor 快速通道（不重啟三席、round 不遞增）；範圍凍結通則；保險閥（max_rounds、邊際遞減）；converged 語意。
4. **決策日誌** `decisions.yaml`＋`check_decisions.py`（append-only、supersedes、editor 打分材料明確排除）。
5. **探索模式** `analysis/exploration-log.yaml`＋`check_exploration.py`（分艙；promoted 轉正掛 origin: E#；資料雙重使用檢查）。
6. **data-manifest** `analysis/data-manifest.yaml`＋`init_manifest.py`／`check_manifest.py`（筆數守恆；方法節樣本流向查核；repro README 資料處理段）。
7. **rerun 與 code-review**：`rerun_all.py`（暫存目錄重跑、顯示精度比對、種子硬關卡、fingerprint、full／spot／off）＋reviewer-methods 的 code-review 模式（風格限 suggestion）。
8. **lit_anchors**：claims 增文獻錨點欄；check_claims 增驗（含稿件層錨點引用）；無錨主張人工確認。
9. **英文潤稿站掛點**（translate-en 步驟 6.5；academic-english-editing 未安裝時行為不變）。
10. **作者方意見入口**（revise 第三來源；A 前綴雙池分列，不影響裁決與保險閥）。
11. **status 可觀測性三則**：統一收尾申報句（全部 skill）、`state.literature` 時戳、SQ 裁決史（check_coverage 解析固定裁決區塊；連續同因未通過強制分流建議）。
12. **agent 模型分層**：frontmatter model 欄依指派表（editor／reviewer-methods／interpreter／evaluator＝opus；其餘 sonnet；不使用 fable）；例行輕檔委派降級；報告標頭模型行；跨模型分數差不入邊際遞減。
13. **排版輸出站 typeset**（唯一新 skill）：build_docx／build_latex（pandoc＋CSL＋lineno；舊 pandoc 優雅降級）、anonymize（雙匿名；自引列示不代改）、check_build；build 產物唯讀單向。
14. **SQ 拆解審與文獻後目標回訪**：evaluate 新 rubric 檔別 decomposition-review（五判準；project-init 步驟 3 與 goals 結構性增修觸發；有條件通過即放行）；lit-review 全模式收尾 novelty statement＋目標回訪（三類檢視）。

**回溯相容**：無新帳本／新產物時行為與 0.5.0 相同（僅提示可補建）；唯一例外為審稿席位改制（見 README）。

### 門檻校準紀錄（2.3）

- 初始值：major < 50、accept ≥ 60、守門地板 major ≤ 5／accept ≥ 7——依「6 分＝可修」定錨推出。跑過二至三個實際專案後，依「editor 裁決與使用者事後判斷的落差」回頭校準，紀錄於此（須註明打分模型；模型換代視同重新校準起點）。

## 0.5.0

前版基線：15 skills、12 agents、8 條確定性腳本、五個單一事實來源。
