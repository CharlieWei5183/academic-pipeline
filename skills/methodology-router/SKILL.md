---
name: methodology-router
description: >
  This skill should be used when the user asks to 「判斷研究方法類型」、「選研究流程」、
  「這個研究該走哪套方法」、「方法路由」、"methodology-router"、"choose a methodology adapter"，
  or immediately after project-init in an academic-pipeline project.
metadata:
  version: "0.7.0"
---

# 方法學路由

避免所有研究被硬套成同一種定量 results.json 流程。依研究問題與設計選定 primary adapter，必要時加 secondary adapters；adapter 決定後續必經關卡、artifact contract、驗證清單與報告規範。

## 前置

讀取 `project.yaml` 的 research question、goals、data、target.article_type 與既有設計摘要。若 route 已存在且研究設計未變，先跑檢核，不重做分類。

## 步驟

1. **建立候選**：讀取 `references/adapters/*.yaml`，依研究的主要知識任務提出 1–2 個候選。不得只依文章標籤判定。
2. **委派 methodology-router agent**：材料只含專案問題、goals、資料／材料與設計摘要、adapter 清單。要求列 primary、secondary、理由、排除的替代 route、信心與會改變判斷的資訊。
3. **人工確認點**：把 route 草案與各 adapter 的 required gates、interpretation limits 一併呈使用者確認。使用者推翻建議時記 D#。
4. **落地**：寫 `methodology/route.yaml`，`confirmed: true`；同步 `project.yaml`：

   ```yaml
   methodology:
     primary: quantitative-inference
     secondary: []
     rationale: ""
     confirmed: true
     routed_at: "2026-07-14"
   ```

   `routed_at` 必須加引號。YAML 會把裸的 `2026-07-14` 解析成 date 物件，下游 `rerun_all.py`
   對 `project.yaml` 子集做 `json.dumps` 時無法序列化（v0.8.1 起腳本端以 `default=str` 兜底，
   但寫入端仍以字串為準；同理適用 `confirmed_at`、`sealed_at` 等所有日期欄）。

5. **確定性檢核**：

   ```bash
   python3 <skill路徑>/scripts/check_route.py <專案根>
   ```

6. **路由**：一般 empirical 專案下一站為 integrity-check（prestudy）→ study-design → data-audit；既有資料專案仍須在正式分析前完成三站。systematic review、質性、理論與模擬研究依 adapter 省略不適用的定量關卡，但不得省略 adapter 指定的等價驗證。

## 重新路由

主問題、資料來源、設計或文章類型有實質改變時，新建 route 版本或在 route.yaml 增 `supersedes` 與變更理由；重新檢查下游 artifacts 是否仍符合。只改期刊不重新路由。

## 收尾

申報：「本階段更新：methodology → <primary [+ secondary]>；下一站：integrity-check（prestudy）」。

收尾必記一筆 D#：追加 `decisions.yaml` 條目，`stage: methodology-router`、`checkpoint: 階段收尾`，並填 `method`（本階段採用的方法）、`problem`（本階段解決的問題）、`evidence`（本階段的指令、腳本路徑、fingerprint 或輸出檔路徑清單）；照建議原樣通過也要記。這一筆是進度時間軸的資料來源，沒記就不會出現在時間軸上。
