# 從 v0.6 升級到 v0.7.1

## 原則

不要只把 `pipeline.version` 改成 `0.7.1`。v0.7 的版本號代表新硬關卡已具備可驗證 artifacts；未完成遷移前保留舊版本，checker 會以相容模式提示缺項。


## 升版前的 consistency 相容性

在保留 v0.6 版本期間，`check_gate.py` 預設只使用舊契約：

- 已有 `state.last_consistency: {result: pass, version: vN}` 的專案可繼續進入既有 peer-review；缺少 v0.7 的 `gate_fingerprint`、`report`、`language` 不構成 blocker。
- 完全沒有有效 last_consistency 時，新 checker 只提示 INFO；是否先補做舊版一致性檢核仍由既有流程與使用者決定。
- 使用 `--strict` 可在正式升版前試跑完整 gate；此時缺新欄位會正常阻擋。
- 一旦設定 `pipeline.version >= 0.7`，相容豁免停止，必須建立完整 consistency report 與 fingerprint。

升版前也要保留既有 review 歷史：若 `reviews/roundN/editor-decision.md` 已存在但 `state.review.scores` 缺該輪，可用 `record_review_score.py` 回填；不得臆造沒有 editor scorecard 的輪次。

## 建議順序

1. 備份整個專案與既有 results、manuscripts、reviews。
2. 以新的 project template 合併 `pipeline`、`methodology` 與新增 state 欄位；不要覆寫 goals 或既有狀態。
3. 執行 methodology-router，建立並人工確認 `methodology/route.yaml`。
4. 建立 `integrity/register.yaml`，完成 prestudy gate；既有資料也要確認二次使用權利、同意範圍與隱私治理。
5. 建立／補寫 study protocol；把原本對話中的分析約定轉成每個 SQ 的 `analysis/plans/<SQ>-v1.yaml`。誠實標示 `retrospective-before-analysis`，不要追溯偽裝成 prospective。
6. 執行 `profile_data.py` 與 data-audit；資料處置若改變納排、分析單位或模型，建立 plan amendment。
7. 將 results 改為 v0.7 schema，加入 `plan_id`、`model_id`、`data_fingerprint` 與結構化不確定度。
8. 建立 `analysis/scripts/run-order.txt` 與環境 lock；將非標準設定／模型以 `; inputs=...` 登記，執行 clean-room rerun，再做 code-review。
9. 以獨立 validator 建立 `analysis/validation.yaml` 或 route 專屬 validation artifact。
10. 建立並封存 evidence protocol；完成 evidence synthesis 與 citation-entailment audit。
11. 將 claims 擴充為含 `validation`、`boundary`、`counterevidence`，再完成 claim-audit 與人工確認。
12. 對目前中文稿跑完整 consistency；翻譯或英文確認後再對英文稿跑完整 consistency。
13. 完成 presubmission integrity 後，才建立投稿包與排版輸出。
14. 全部通過後，將 `pipeline.version` 設為 `0.7.1`；或先設版本並逐項修 blocker，但期間不得宣稱 pipeline 已完成。

## 已確認計畫的處理

v0.7 不允許原地改寫 confirmed plan。舊計畫轉入後首次封存為 `SQx-v1`；後續變更建立 `SQx-v2`，填 `supersedes`、`amendment_reason`、`changes`。舊結果若基於舊 plan，保留原 `plan_id`，不得改標成新 plan。

## 失效傳播

以下變更至少使 rerun、validation、claims audit 與 consistency 過期：raw data、active plan、analysis settings、任一 analysis script/helper、run-order/declared inputs、results、validation、references/screening/evidence synthesis。作者名單、COI、權限、AI disclosure 或目標期刊規範變更，會使 presubmission integrity 過期。
