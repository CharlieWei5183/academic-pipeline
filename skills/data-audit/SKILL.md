---
name: data-audit
description: >
  This skill should be used when the user asks to 「資料稽核」、「正式分析前檢查資料」、
  「檢查缺失、重複或洩漏」、「data-audit」，or after study-design and before analyze-data
  in an academic-pipeline project.
metadata:
  version: "0.7.2"
---

# 資料稽核

把「看一下缺失值與離群值」提升成獨立、可稽核的資料品質關卡。data-auditor 與 data-analyst 分離；原始資料永遠唯讀。

## 前置

讀取 project.yaml、methodology/route.yaml、protocol、active analysis plans、data-manifest（已有時）與 data/。計畫尚未封存仍可先稽核，但 audit 發現若影響 estimand、納排或模型，必須回 study-design amendment。

## 步驟

1. **確定性 profile 與 raw fingerprint**：

   ```bash
   python3 <skill路徑>/scripts/profile_data.py <專案根>
   ```

   產出 `analysis/data-profile.json`：檔案 hash、大小、常見表格的列欄、缺失與重複摘要；不輸出原始 cell values。fingerprint 改變會使 plan review、rerun 與 validation 過期。
2. **data-manifest 骨架**：尚無 manifest 時，以 analyze-data 的建檔腳本產生骨架
   （`python3 <plugin>/skills/analyze-data/scripts/init_manifest.py <專案根>`，見 analyze-data 步驟 2）；
   此階段只補來源、欄位、單位、known issues，不執行正式清理。樣本流向（flow／steps）與筆數守恆由 analyze-data 維護。
3. **委派 data-auditor**：材料含 profile、raw files 的必要結構、protocol、plans、adapter、manifest。產出 `analysis/data-audit.yaml` 草案與 `reviews/data-audit-<序>.md`。
4. **處置人工確認點**：blocker 的剔除、插補、重編碼、資料切分或用途限制逐項呈使用者；方向性選擇記 D#。任何轉換仍由 analyze-data 的 script 寫入 derived/ 與 manifest，data-auditor 不改 raw data。
5. **更新 audit**：resolved／accepted-limitation 與條件寫回；只有無未解 blocker 才可 `status: pass` 或 `conditional`、`confirmed: true`。
6. **檢核**：

   ```bash
   python3 <skill路徑>/scripts/check_data_audit.py <專案根>
   ```

7. 更新 `state.data_audit: {result, profile_fingerprint, report, at}`。下一站 analyze-data；若 audit 改變 plan，先回 study-design。

## 一般研究的 adapter 差異

- predictive-ml：entity/split 重複、target/temporal leakage、label quality、dataset shift。
- qualitative：同意範圍、去識別、逐字稿完整性、翻譯保真、取樣覆蓋。
- systematic review：重複報告、重疊 cohort、擷取一致性與 outcome 定義。
- simulation：參數來源、邊界條件、benchmark 與 code version。

## 回溯相容

舊專案無 pipeline.version 0.7 時，check_data_audit 只提示；新專案 blocker 未清不得進正式分析。

## 收尾

申報：「本階段更新：state.data_audit → <pass/conditional>（fingerprint <...>）；下一站：analyze-data」。
