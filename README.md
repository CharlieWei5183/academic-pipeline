# academic-pipeline

`academic-pipeline` 是一套以 artifacts、獨立角色與確定性檢核構成的研究—論文 pipeline，涵蓋從專案初始化、方法學路由、資料分析，到中英文稿撰寫、虛擬同儕審查、投稿與排版的全流程。設計目標是可稽核、可重現、能跨 Cowork session 穩定執行的 agent 驅動研究流程；所有輸出為繁體中文。

核心原則：`project.yaml` 的 `state` 只是快取；protocol、plans、results、validation、claims、audit reports 等 artifacts 才是狀態真相。任何承重來源變動，都必須使下游 pass 狀態失效。

## Pipeline 主流程

橙色圓角＝人工確認關卡（不確認就不往下走）；青色＝確定性腳本 gate，由 checker 機械判定；
灰色虛線＝選用站點，未安裝或略過不報錯；其餘為 skill 步驟。

```mermaid
flowchart TD
    classDef step  fill:#f8fafc,stroke:#94a3b8,stroke-width:1.5px,color:#0f172a
    classDef gate  fill:#fdf1e3,stroke:#c2703d,stroke-width:2.5px,color:#7c2d12
    classDef mech  fill:#e8f3f2,stroke:#2b7a78,stroke-width:2px,color:#134e4a
    classDef opt   fill:#f8fafc,stroke:#a8b3c1,stroke-width:1.5px,stroke-dasharray:6 4,color:#64748b
    classDef phase fill:#ffffff,stroke:#e2e8f0,stroke-width:1px,color:#64748b

    subgraph PH1["① 立案與設計"]
        direction TB
        A1["project-init<br/>建立專案 · 拆解 goals"]
        A2["methodology-router<br/>選定方法 adapter"]
        H1(["人工確認 route<br/>推翻建議記 D#"])
        A3["integrity-check<br/>prestudy 倫理與資料治理"]
        A4["study-design<br/>protocol ＋ 版本化 plans"]
        H2(["人工逐項確認 → 封存<br/>sealed plan 不可原地改"])
        A1 --> A2 --> H1 --> A3 --> A4 --> H2
    end

    subgraph PH2["② 資料與證據生產"]
        direction TB
        B1["data-audit<br/>缺失 · 重複 · 洩漏 · provenance"]
        H3(["處置人工確認<br/>剔除／插補／切分記 D#"])
        FORK{{"依 route adapter 分流"}}
        B2["analyze-data<br/>執行封存的分析計畫"]
        B3["clean-room rerun<br/>rerun_all.py"]
        B4["code-review<br/>reviewer-methods"]
        B5["validate-results<br/>穩健性 · 診斷 · 獨立重算"]
        H4(["人工確認結果契合<br/>確認後 SQ 才轉 addressed"])
        C1["lit-review<br/>literature-scout"]
        C2["evidence-synthesis<br/>風險偏誤 · 引用 entailment"]
        B1 --> H3 --> FORK
        FORK --> B2 --> B3 --> B4 --> B5 --> H4
        FORK --> C1 --> C2
    end

    subgraph PH3["③ 判讀與主張"]
        direction TB
        D1["evaluate（full）<br/>目標覆蓋裁決"]
        D2["interpret-results<br/>interpreter 草擬 claims"]
        D3["claim-audit<br/>claim-critic 反方審查"]
        H5(["人工確認 claims<br/>claims.yaml confirmed: true"])
        D1 --> D2 --> D3 --> H5
    end

    subgraph PH4["④ 撰稿"]
        direction TB
        E1["figure-design<br/>figure story · 出版級圖表"]
        H6(["圖表驗收確認"])
        E2["write-manuscript<br/>繁體中文稿"]
        H7(["人工確認後才成稿"])
        E3["write-supplementary<br/>SI 收尾"]
        E4["check-consistency（zh）<br/>check_gate.py"]
        E1 --> H6 --> E2 --> H7 --> E3 --> E4
    end

    subgraph PH5["⑤ 審查與潤稿"]
        direction TB
        F1["peer-review<br/>persona panel ＋ editor"]
        F2["revise<br/>issue-ledger 逐點結案"]
        F3["chinese-academic-editing<br/>中文潤稿 · 內建選用"]
        H8(["★ 中文人工定稿<br/>state.zh_final"])
        F4["translate-en<br/>translator ＋ reviewer-language"]
        F5["academic-english-editing<br/>英文潤稿 · 內建選用"]
        H9(["★ 英文人工確認"])
        F6["check-consistency（en）<br/>全量重跑"]
        F1 -->|"major／minor"| F2 -->|"未收斂"| F1
        F2 -->|"accept／覆核通過"| F3 --> H8 --> F4 --> F5 --> H9 --> F6
    end

    subgraph PH6["⑥ 投稿"]
        direction TB
        G1["submission-prep<br/>cover letter · 重現性打包"]
        H10(["【請人工補】區塊逐項確認"])
        G2["integrity-check<br/>presubmission"]
        G3["最終 gate 檢查"]
        G4["typeset<br/>docx／LaTeX · 雙匿名 · 行號"]
        H11(["收尾人工確認<br/>state.submission.build"])
        G1 --> H10 --> G2 --> G3 --> G4 --> H11
    end

    JM["journal-match<br/>選刊 · cascade"]

    H2 --> B1
    H4 --> D1
    C2 --> D1
    H5 --> E1
    E4 --> F1
    F6 --> G1
    F2 -->|"reject"| JM --> F1
    H11 --> SUB(["投稿（使用者）"])

    class A1,A2,A3,A4,B1,B2,B5,C1,C2,D1,D2,D3,E1,E2,E3,F1,F2,F4,G1,G2,G4,JM,FORK step
    class B3,B4,E4,F6,G3 mech
    class F3,F5 opt
    class H1,H2,H3,H4,H5,H6,H7,H8,H9,H10,H11,SUB gate
    class PH1,PH2,PH3,PH4,PH5,PH6 phase

    linkStyle default stroke:#94a3b8,stroke-width:1.4px
```

`status` 不在流程線上——任何時點都能呼叫它掃描 artifacts、重算 fingerprint，指出第一個未通過或已過期的 gate 並導向對應 skill。route adapter 可把定量 `analyze-data` 換成質性 audit trail、proof audit、systematic-review synthesis 或 mixed-method integration，required gates 仍由 route 機械檢查。

`debug-pipeline` 同屬流程線外：當任一執行、clean-room rerun 或 checker 失敗且根因未知時反應式觸發，做單一根因定位與最小修補後，把因修補而失效的下游 gate 交回 `status` 重新分診；它不改 sealed plan、不覆寫正式結果。

### 人工確認關卡

| # | 關卡 | 所屬 skill | 確認什麼 | 不確認的後果 |
|---|---|---|---|---|
| 1 | route 確認 | `methodology-router` | 方法 adapter、required gates、interpretation limits | 不得進入 study-design 之後的硬關卡 |
| 2 | protocol／plan 封存 | `study-design` | 逐項確認後才 seal，取得 content hash | 無 sealed plan，results 無法宣告鍵歸屬 |
| 3 | 資料處置 | `data-audit` | 剔除／插補／重編碼／切分／用途限制 | 方向性選擇未留紀錄，分析失去可稽核性 |
| 4 | 結果契合 | `analyze-data` | validation 限制、report 與圖表 | SQ 不得轉 `addressed` |
| 5 | claims 確認 | `interpret-results` → `claim-audit` | 逐條主張、最強反方、限定語、evidence | `claims.yaml` 不得設 `confirmed: true`，不能開始寫稿 |
| 6 | 圖表驗收 | `figure-design` | 訊息單一、自足、解析度、色盲檢視、有效位數 | manifest 的 `spec` 未定，submission-prep 無依據 |
| 7 | 中文成稿 | `write-manuscript` | 全稿內容與數字標註 | 不成稿 |
| 8 | ★ 中文定稿 | `peer-review`／`revise` 收斂後 | 中文最終版本 | `state.zh_final` 不成立，不得翻譯 |
| 9 | ★ 英文確認 | `translate-en` 之後 | 英文稿語意與術語 | 不得進 check-consistency(en) |
| 10 | 投稿包補件 | `submission-prep` | README 的【請人工補】區塊 | 重現性包留空出包 |
| 11 | 排版收尾 | `typeset` | 產物清單、check_build、自引清單 | `state.submission.build` 不寫入 |

★ 兩處是語言定稿點：潤稿站（`chinese-academic-editing`／`academic-english-editing`）可以略過，但**不能取代**這兩個人工確認。潤稿只改語言呈現，不得動數字、markers、citekey、claim strength 或 validation boundary；潤稿後必須建立新版本並重跑該語言的完整 consistency。

除上表外，多數 skill 另有取捨性質的確認（`lit-review` 的搜尋關鍵字、`evaluate` 的 SQ 狀態變更、`evidence-synthesis` 的 protocol 封存、`write-supplementary` 的素材取捨、`journal-match` 的 target 與 cascade）。上表只列不確認就無法往下走的硬關卡。

## 核心設計

**版本化研究與分析計畫**：`study-design` skill 與 `research-designer` agent 把研究設計落地為 `protocol/study-protocol.yaml`、`analysis/plans/<SQ>-vN.yaml` 與 `analysis/plans/index.yaml`。confirmed plan 以 content hash 封存；修改須建立新版本並標示 `supersedes`、`amendment_reason` 與差異，不得原地改寫。每筆 result 必須連回 active `plan_id`、`model_id` 與 `data_fingerprint`。

**clean-room rerun**：`analyze-data` 強制「執行 sealed plan → schema/manifest 檢核 → clean-room rerun → code-review → validate-results → 人工確認」。`rerun_all.py` 只複製 inputs，fingerprint 涵蓋 raw data、完整 `analysis/scripts/`、run-order、protocol／active plans、data profile/audit、manifest、方法路由與環境 lock；未從零重建輸出即失敗。

**獨立結果驗證**：`validate-results` skill 與 `statistical-validator` agent 以 `analysis/validation.yaml` 記錄模型診斷、影響點、替代規格、缺失值、多重比較、穩定性與承重結果的獨立重算；質性／系統性回顧／混合方法／理論研究改用對應 adapter validation artifacts。

**獨立主張反方審查**：`interpreter` 只能起草 `claims.yaml`；`claim-audit` skill 與 `claim-critic` agent 逐條攻擊 entailment、主張強度、反證、適用邊界與探索轉驗證問題。任一上游 fingerprint 漂移都會擋下舊 audit。

**英文定稿後的完整一致性 gate**：`translate-en` 後強制執行完整 `check-consistency(en)`，重查上游 route/plans/audit/validation、數字表格引用圖文、中英 claim strength 與方法語意。`check_gate.py` 以 gate fingerprint 防止沿用過期 pass。

**治理與方法 adapter**：`methodology-router`、`data-audit`、`evidence-synthesis`、`integrity-check` 提供一般研究所需治理；內建七種 adapter——`quantitative-inference`、`predictive-ml`、`qualitative`、`mixed-methods`、`systematic-review-meta-analysis`、`simulation-computational`、`theoretical-mathematical`——各自定義 required gates、plan／validation／results 契約、interpretation limits 與 reporting guideline。

**主問題與附錄問題分離**：`goals` 分為 `sub_questions`（問「現象」：X 與 Y 是否關聯、機制、邊界）與 `appendix_questions`（問「分析本身」：換方法／換設定下主結果是否維持）。目標覆蓋只以 `sub_questions` 判定主問題是否答足；附錄問題不計入主覆蓋，但同受 `check_coverage.py` 的逐項 integrity 檢查。

**內建英文潤稿站**：`academic-english-editing` 為內建 skill，源自 `academic-humanizer` v0.3.3（MIT）的 Layer 1／2／3／5，逐節標註來源；刻意不含會改動 claim strength 的 Layer 4（發現 over-claim 只標記回 `claim-audit`）。掛點只改語言呈現，不得動數字、markers、citekey、claim strength、validation boundary 或方法語意，潤稿後重跑對應語言的 full consistency。

**內建中文潤稿站**：`chinese-academic-editing` 為內建 skill，與英文站同一套掛點合約，但語域基準是「像期刊論文」而非「像人整理過」——去 AI 味不往口語走。另含 Layer 4「結果與討論的陳述規格」：效果量與不確定度同時報、不以裸 p 值作主句、數字精度以 `display` 為準、限制節不得改成正面語氣、摘要不得移除正文保留的核心限定，並以強度對照表限制「同級可換、跨級不動」。該層錨定 `write-manuscript` 第 4／5／6 步與 `check_numbers.py` 的既有豁免定義，不新增契約。外部 user skill `chinese-deai-editing` 退出 pipeline 掛點（語域基準不同），仍可獨立用於非稿件的中文材料。

## 元件

### Skills（26）

`project-init`、`methodology-router`、`integrity-check`、`study-design`、`data-audit`、`analyze-data`、`validate-results`、`lit-review`、`evidence-synthesis`、`evaluate`、`interpret-results`、`claim-audit`、`figure-design`、`write-manuscript`、`write-supplementary`、`check-consistency`、`peer-review`、`revise`、`chinese-academic-editing`、`translate-en`、`academic-english-editing`、`submission-prep`、`journal-match`、`status`、`debug-pipeline`、`typeset`。

### Agents（18）

含七席獨立審查角色：`methodology-router`、`research-designer`、`data-auditor`、`statistical-validator`、`evidence-auditor`、`claim-critic`、`integrity-officer`。角色專責分工：設計者不審自己的設計、分析者不驗自己的結果、主張起草者不審自己的主張。

### 確定性腳本

機械檢核歸 scripts、領域判斷歸 agents、人工確認與方向性取捨寫入 `decisions.yaml`，各 stage 收尾另記一筆階段收尾條目（`checkpoint: 階段收尾`，含 `question`／`exec_issue`／`method`／`evidence`），作為進度時間軸的資料來源；一筆決策落在主問題（`question: main`）、子問題（`question: SQ2` 等 id）或某個問題之下的執行問題（該 `question` 再加 `exec_issue`）三層之一，`method` 只有一欄、意義跟著那一層走。主要腳本涵蓋 route（`check_route.py`）、protocol／plans（`init_protocol.py`、`init_plan.py`、`seal_artifact.py`、`check_plan.py`）、data audit（`profile_data.py`、`check_data_audit.py`）、results（`check_results_schema.py`、`rerun_all.py`）、validation（`check_validation.py`、`check_adapter_validation.py`）、evidence（`seal_evidence_protocol.py`、`check_evidence.py`）、claims（`check_claims.py`、`check_claim_audit.py`）、integrity（`check_integrity.py`）、consistency（`check_gate.py`）、review state（`record_review_score.py`）與 progress（`render_progress.py`）。

## 審稿分數與潤稿掛點

`agents/editor.md` 的四段分數帶（1–3／4–5／6–7／8–10）是跨輪共同基準。每次完整 panel 裁決末尾必須有唯一 `REVIEW_SCORE` YAML block，peer-review 隨即執行：

```bash
python3 skills/revise/scripts/record_review_score.py \
  project.yaml reviews/roundN/editor-decision.md
```

minor re-check 不建立新 score；下一個完整 panel 輪才新增，寫入後再跑 `check_ledger.py` 計算邊際遞減。中文潤稿站 `chinese-academic-editing` 為內建選用 skill（0.10.0 起隨附）；與英文站同樣只改語言呈現，潤稿後須重跑 full `check-consistency(zh)`，且不能取代★中文人工定稿。

## 主要事實與治理 artifacts

```text
project.yaml
methodology/route.yaml
protocol/study-protocol.yaml
analysis/plans/index.yaml + active plans
analysis/data-profile.json
analysis/data-audit.yaml
analysis/data-manifest.yaml
analysis/results.json 或 adapter findings artifact
analysis/validation.yaml 或 adapter validation artifact
literature/evidence-protocol.yaml
literature/evidence-synthesis.yaml
analysis/claims.yaml
analysis/claim-audit.yaml
integrity/register.yaml
analysis/exploration-log.yaml
reviews/issue-ledger.yaml
decisions.yaml
PROGRESS.md
```

`PROGRESS.md` 由 `skills/status/scripts/render_progress.py` 從 `decisions.yaml` 自動產生（一張記錄表＋一個 mermaid timeline；問題欄＝`question`，有執行問題時寫成「question › exec_issue」），不是事實來源；要改內容請改 `decisions.yaml` 再重跑 renderer。

## 相容性與升級

沒有 `pipeline.version >= 0.7` 的舊專案，新增 checker 以相容模式運作：`check_gate.py` 對完全沒有 last_consistency 的專案只輸出 INFO，對已跑過 v0.6 consistency 的專案只驗既有 `result` 與 `version`。只有 `--strict` 或升版到 0.7.x 後才啟用完整 fingerprint gate。升級請先備份，再依 [`MIGRATION-v0.7.md`](MIGRATION-v0.7.md) 補 route、integrity、protocol/plans、audit、validation、evidence 與 claim-audit。

## 測試

```bash
python3 -m compileall -q agents skills tests
python3 tests/run_v07_smoke.py
python3 tests/run_v071_regressions.py
python3 tests/run_v072_regressions.py
python3 tests/run_v073_regressions.py
python3 tests/run_v080_regressions.py
python3 tests/run_v081_regressions.py
python3 tests/run_v0110_regressions.py
```

`tests/mini-project` 保留黃金答案；smoke 測試動態建立 v0.7 專案，驗證七種 adapter 的 plan／validation 契約、clean-room 重跑、資料稽核、results schema、evidence fingerprint、claim-audit、integrity 與中英文 consistency 的 source-staleness gate。腳本需要 Python 3.10+ 與 PyYAML；排版另依 typeset 說明使用 pandoc／LaTeX。

## 出處與致謝

本 plugin 絕大多數 skills、agents、確定性腳本與 pipeline 設計為作者（Charlie）自行開發。三處明確參考了外部 plugin／skill，範圍如下、其餘均為自行開發：

- **`debug-pipeline`**（v0.9.0）：診斷程序主體（四階段診斷流程、多元件邊界取證、三振後質疑架構）改寫自 `superpowers` v6.1.1（MIT，Jesse Vincent／obra）的 `systematic-debugging`；本 skill 的撰寫規範（frontmatter／description 紀律、trigger-eval 測試法）參考其 `writing-skills`、規格化過程（先判斷該不該拆、先推薦再列選項、分節逐段確認）參考其 `brainstorming`。fingerprint 分層定位、manifest 樣本流向守恆、`analysis/validation/` 隔離、「不得縮小稽核範圍換轉綠」、治理接 `decisions.yaml` D#／`study-design` amendment、複用 `reviewer-methods` 與流程線外定位為本 plugin 專屬新增。
- **`academic-english-editing`**（v0.8.0）：Layer 1／2／3／5、核心原則與流程源自 user skill `academic-humanizer` v0.3.3（MIT）；掛點合約與「不含 Layer 4」為本 plugin 專屬新增。
- **`chinese-academic-editing`**（v0.10.0）：層級骨架（Layer 1／2／3／5）、核心原則與流程對稱自本 plugin 的 `academic-english-editing`（其源頭為 `academic-humanizer` v0.3.3，MIT），中文語境的 pattern、例句與規則為重新撰寫；中文 AI tell 清單與台灣書面語正規化部分參考作者自有的 user skill `chinese-deai-editing`。掛點合約與 Layer 4（結果與討論的陳述規格）為本 plugin 專屬新增。

## 版本歷程

完整逐版變更請見 [`CHANGELOG.md`](CHANGELOG.md)。
