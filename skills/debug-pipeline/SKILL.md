---
name: debug-pipeline
description: >
  This skill should be used when the user asks 「除錯」、「這支腳本為什麼報錯」、
  「rerun 重跑不出來」、「fingerprint 為什麼變了」、「跨階段筆數對不上」、
  「Python 傳給 R 少了資料」、"debug-pipeline"，or when an analyze-data run,
  a clean-room rerun, or a checker fails and the root cause is unknown in an
  academic-pipeline project. 不用於結果穩健性驗證（validate-results）、稿件
  數字一致性（check-consistency）或進度分診（status）。
metadata:
  version: "0.9.0"
---

# Pipeline 執行期故障的根因定位

把「腳本壞了慢慢試」提升成可稽核的單一根因流程。目標是找到一個根因並最小修補，不是拼湊到轉綠。復現與診斷程式一律放 `analysis/validation/` 或暫存目錄，不得污染正式 `analysis/scripts/`、`derived/` 或 `results.json`（沿用 statistical-validator 的隔離慣例）。本 skill 是流程線外工具，不改 sealed plan、不覆寫正式結果。

## 何時進來 / 不適用

進來：`analyze-data` 執行、clean-room `rerun_all.py`、或任一 checker（`check_*.py`）失敗，且根因未知。
不適用：結果已可重建、只問穩不穩健 → `validate-results`；稿件數字／引用 → `check-consistency`；只想知道卡在哪一關 → `status`。

## 前置

讀取失敗當下的完整錯誤輸出、`project.yaml.state`（僅快取）、`methodology/route.yaml`、active plans、`analysis/data-manifest.yaml`、最近一次 `analysis/data-profile.json` 與環境 lock。state 與 artifact 衝突時以 artifact 為準。

## 診斷步驟

〔來源：superpowers · systematic-debugging——步驟 1–6 為其診斷程序與「多元件邊界取證」「三振後質疑架構」之改寫。Phase 4 首步由原「先寫 failing test」改為統計 pipeline 對應的「最小復現腳本」；步驟 3、4 的 fingerprint／manifest 對象與步驟 6 的治理接點為 academic-pipeline 專屬。〕

1. **讀完整錯誤**：traceback 或 checker blocker 原文全讀，逐字理解它在指控什麼，不從症狀猜根因。checker 的 blocker 訊息可能指錯方向（見 CHANGELOG 0.8.1 的 superseded-plan 案例），必要時回讀它的判定邏輯再定位。
2. **穩定復現**：縮到最小可重現單位——單一 SQ 腳本、或 `rerun_all.py` 的一個子集——能一鍵重跑重現。無法穩定復現前不動修補。
3. **定位近期變更**：以 `check_validation.py <root> --source-fingerprint-only` 取當前 `source_fingerprint`，比對上次通過值，判斷是 raw data／完整 `analysis/scripts/`／active plan／manifest／方法路由／環境 lock 哪一層漂了。fingerprint 沒漂卻失敗 → 指向環境或非確定性因素（seed、外部相依、浮點）。
4. **元件邊界取證**：在每個 stage/script handoff（含 Python↔R 交接）落最小診斷輸出——進出筆數、鍵值域、join 前後列數——對照 manifest 的樣本流向（flow/steps）守恆，定位掉列／型別轉換／編碼發生在哪個邊界。
5. **單一假說 → 最小改動驗證**：先形成單一根因假說再改，一次只改一處。修補必須（a）通過步驟 2 的復現、（b）不縮小稽核範圍、（c）不使既有 `source_fingerprint` 或封存 `content_hash` 失效。**警訊**：若「唯一解」是把某鍵移出 `results.json`、關掉某項檢查或放寬 gate，代表失敗方向錯了——停手改查真因。
6. **收斂或升級**：同一故障連做三次最小修補仍無效 → 停手，不試第四次。記 `decisions.yaml` 一筆 D# 或呈使用者裁決；若根因是方法／計畫設定而非機械 bug，回 `study-design` 建 amendment（新版本＋`supersedes`＋`amendment_reason`），不在此自行改設計。需要新 context 的第二意見時，委派既有 `reviewer-methods`（不新增 agent）。

## 修補後

任何觸及 raw data、`analysis/scripts/`、active plan、manifest 或環境 lock 的修補，都會使下游 rerun／validation／consistency 的 pass 失效。修完不宣稱完成，交回 `status` 重新分診，讓對應 gate 依新 fingerprint 重跑。

## 收尾

固定申報：「根因：<...>；修補：<檔案／改動>；稽核範圍未縮小；觸發：<D#／study-design amendment／無>；已失效下游 gate：<...>，交回 status 分診。」

## 出處

- 診斷程序、多元件邊界取證、三振後質疑架構：改寫自 `superpowers` v6.1.1（MIT）的 `systematic-debugging`。
- 本 skill 的撰寫規範（frontmatter／description 紀律、trigger-eval 測試法）：參考 `superpowers` 的 `writing-skills`。
- 規格化過程（先判斷該不該拆、先推薦再列選項、分節逐段確認）：參考 `superpowers` 的 `brainstorming`。
- fingerprint 分層定位、manifest 樣本流向守恆、`analysis/validation/` 隔離、「不得縮小稽核範圍換轉綠」、治理接 `decisions.yaml` D#／`study-design` amendment、複用 `reviewer-methods`、流程線外定位與 `status` 路由：academic-pipeline 專屬。
