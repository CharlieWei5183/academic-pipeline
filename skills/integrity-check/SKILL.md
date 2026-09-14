---
name: integrity-check
description: >
  This skill should be used when the user asks to 「研究倫理檢查」、「資料治理」、「投稿前完整性檢查」、
  「作者資格與利益衝突」、「integrity-check」，or at the pre-study and pre-submission gates
  of an academic-pipeline project.
metadata:
  version: "0.7.0"
---

# 研究完整性、倫理與治理關卡

同一 skill 有兩種模式：`prestudy` 防止未取得權限就分析／收集資料；`presubmission` 防止作者、聲明、權限與完整性問題留到投稿系統才發現。

## 共通原則

plugin 不能核發倫理許可、替全體作者同意、或自行宣稱通過正式抄襲／相似度系統。沒有證據就標 pending/manual-required，不能用看似肯定的文字填空。

## prestudy 模式

1. 讀 methodology route、protocol、資料來源與治理需求。
2. 若 `integrity/register.yaml` 不存在，以模板建檔。
3. 委派 integrity-officer 檢查：human/animal/biosafety scope、consent/waiver、資料權利、隱私與存取、註冊、保存政策。
4. required 項逐項向使用者索取真實 evidence；不適用必填 rationale。倫理或授權 pending 是 blocker。
5. 產出 `reviews/integrity-prestudy-<序>.md`，更新 register，再跑：

   ```bash
   python3 <skill路徑>/scripts/check_integrity.py <專案根> --stage prestudy
   ```

6. 更新 `state.integrity.prestudy`。pass/合規的 conditional 才能封存可執行 protocol 與正式分析。

## presubmission 模式

1. 在 submission-prep 前執行，讀英文定稿、SI、作者資訊、聲明、圖表、repro package 與期刊規範。
2. 委派 integrity-officer 檢查：作者資格／CRediT／全體核可、COI、原創性與無一稿多投、第三方權限、圖像處理、data/code availability、AI disclosure、reporting guideline、正式相似度／抄襲檢查狀態。
3. 外部相似度項只能以 `external-verified` 或 `manual-verified` 通過，必須記 evidence；不得由 LLM 自我認證。
4. 產出 `reviews/integrity-presubmission-<序>.md`，再跑：

   ```bash
   python3 <skill路徑>/scripts/check_integrity.py <專案根> --stage presubmission
   ```

5. 更新 `state.integrity.presubmission`；投稿前只接受 pass，不接受 conditional。

## 版本與失效

作者名單、資料／程式可用性、AI 使用方式、圖像或投稿期刊規範改變時，presubmission 檢查失效，須重跑。prestudy 的核可範圍若不涵蓋 plan amendment，也須先補治理再分析。

## 收尾

申報：「本階段更新：state.integrity.<stage> → <result>；下一站：<study-design / submission-prep>」。

收尾必記一筆 D#：追加 `decisions.yaml` 條目，`stage: integrity-check`、`checkpoint: 階段收尾`，並填 `question`（本階段對應的問題層：`main` 或子問題 id 如 `SQ2`）、`issue`（只在這筆是該問題之下的執行問題時填，一句話）、`method`（對應該層的方法：main＝研究設計、SQ＝分析方法、有 issue＝解決該執行問題的做法）、`evidence`（本階段的指令、腳本路徑、fingerprint 或輸出檔路徑清單）；照建議原樣通過也要記。這一筆是進度時間軸的資料來源，沒記就不會出現在時間軸上。
