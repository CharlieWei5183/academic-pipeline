---
name: check-consistency
description: >
  This skill should be used when the user asks to 「檢核一致性」、「查核稿件」、「檢查數字」、
  「檢查英文定稿」、"check-consistency"、"verify the manuscript"，or before peer review,
  submission preparation, or typesetting in an academic-pipeline project.
metadata:
  version: "0.7.1"
---

# 全量一致性檢核

中文稿與英文稿使用同一套完整關卡。翻譯後的 marker／語言檢查不能取代數字、引用、主張、方法、validation、evidence 與圖文一致性。未通過的稿件不得 peer-review、submission-prep 或 typeset。

## 對象

指定 `manuscript/<zh|en>/vN.md`；同語言 SI 一併檢核。英文確認後必須對 `state.en_final.version` 跑全量檢核，而不是直接投稿。

## 第一層：上游 artifact 關卡

依 route.required_gates 執行適用項；定量／ML／模擬一般包含：

```bash
python3 <plugin>/skills/methodology-router/scripts/check_route.py <root>
python3 <plugin>/skills/study-design/scripts/check_plan.py <root> --require-confirmed --results analysis/results.json
python3 <plugin>/skills/data-audit/scripts/check_data_audit.py <root>
python3 <plugin>/skills/analyze-data/scripts/check_results_schema.py <root>
python3 <plugin>/skills/validate-results/scripts/check_validation.py <root>
python3 <plugin>/skills/validate-results/scripts/check_adapter_validation.py <root>
python3 <plugin>/skills/evidence-synthesis/scripts/check_evidence.py <root>
python3 <plugin>/skills/interpret-results/scripts/check_claims.py analysis/claims.yaml project.yaml \
  analysis/results.json literature/references.bib --manuscript <稿件.md> \
  --exploration analysis/exploration-log.yaml --validation analysis/validation.yaml
python3 <plugin>/skills/claim-audit/scripts/check_claim_audit.py <root>
```

兩支 validation checker 都可執行：不適用者回 INFO；mixed-methods 必須同時通過 results-based 定量 strand 與 joint-display adapter validation。缺少 route 指定的質性／proof／review validation artifact 是 blocker。

## 第二層：稿件確定性檢核

正文與 SI 各跑：

```bash
python3 <skill路徑>/scripts/check_numbers.py <稿件.md> analysis/results.json
python3 <skill路徑>/scripts/check_citations.py <稿件.md> literature/references.bib
python3 <plugin>/skills/analyze-data/scripts/check_manifest.py analysis/data-manifest.yaml <root> \
  --decisions decisions.yaml --results analysis/results.json
```

若 analysis rerun 適用：

```bash
python3 <plugin>/skills/analyze-data/scripts/rerun_all.py <root> --fingerprint-only \
  --state-fingerprint <state.analysis.rerun.fingerprint>
```

fingerprint 不一致即重跑 clean rerun，再重做 code-review/validate-results；不能只更新 state。

## 第三層：fact-checker 語意檢核

腳本零 blocker 後才委派 fact-checker，檢查：

1. warning 裁定與引用—敘述 entailment；
2. 方法節 vs protocol/plans/scripts/manifest/data-audit；時序與 amendment 描述；
3. 結果、圖表、caption、SI、摘要與正文一致；
4. claim wording vs strength、claim-audit boundary/counterargument、validation limitations；
5. evidence synthesis 的 certainty、conflicting evidence 與稿件文獻定位；
6. adapter 專屬報告邊界與 reporting guideline；
7. 英文稿另查翻譯是否弱化／強化原 claim、刪除限定或改變數字語境。

## gate fingerprint 與狀態

所有檢核通過後計算：

```bash
python3 <skill路徑>/scripts/check_gate.py <root> --manuscript <稿件.md> [--si <SI.md>] \
  --require-language <zh|en> --fingerprint-only
```

將輸出的 `gate_fingerprint` 寫入：

```yaml
state:
  last_consistency:
    version: "en/v2"
    language: en
    si: "si-v1"
    result: pass
    gate_fingerprint: "..."
    report: "reviews/consistency-en-v2.md"
    at: "..."
```

再以非 fingerprint 模式執行 `check_gate.py` 自驗。fingerprint 納入稿件／SI、raw data、analysis scripts／environment lock、results、validation evidence、adapter-native source artifacts、claims、claim-audit、evidence synthesis 來源、plans、manifest、bibliography／screening、實際 figure files、clean-rerun identity、prestudy integrity 與 target 設定；任一承重來源變更都會使舊 pass 過期。presubmission integrity 不直接納入，以避免「一致性先通過才可投稿檢核、投稿檢核又令一致性失效」的循環；它要求的稿件／設定修改仍會由相應 hash 捕捉。

報告存 `reviews/consistency-<lang>-<version>.md`。未通過寫 fail 並修正後全量重跑；不得只重跑先前失敗的單項後沿用舊 semantic audit。

## 舊專案相容模式

`check_gate.py` 的相容分支以 `pipeline.version` 判定，**不能以 last_consistency 是否為空判定**：

- `pipeline.version < 0.7` 且未加 `--strict`：只檢查 v0.6 已存在的 `result` 與 `version`；不要求 `gate_fingerprint`、`report`、`language` 或 `en_final.confirmed_at`。
- 舊專案完全沒有有效 `last_consistency`：輸出 INFO 並 exit 0，符合「新增 checker 不因缺新 artifact 阻擋」的相容承諾。
- 舊專案已有 `{result: pass, version: vN}`：應以 legacy contract 通過，不能因缺 v0.7 欄位失敗。
- `pipeline.version >= 0.7` 或明確加 `--strict`：完整 fingerprint gate 生效。

## 收尾

申報：「本階段更新：state.last_consistency → <lang/version, pass, fingerprint>；下一站：peer-review／submission-prep」。

收尾必記一筆 D#：追加 `decisions.yaml` 條目，`stage: check-consistency`、`checkpoint: 階段收尾`，並填 `question`（本階段對應的問題層：`main` 或子問題 id 如 `SQ2`）、`exec_issue`（只在這筆是該問題之下的執行問題時填，一句話）、`method`（對應該層的方法：main＝研究設計、SQ＝分析方法、有 exec_issue＝解決該執行問題的做法）、`evidence`（本階段的指令、腳本路徑、fingerprint 或輸出檔路徑清單）；照建議原樣通過也要記。這一筆是進度時間軸的資料來源，沒記就不會出現在時間軸上。
