---
name: academic-english-editing
description: >
  英文學術稿件的潤稿站：清除 AI 生成痕跡（AI tells）、對齊學術慣例、貼合作者與期刊語氣，
  一律不動數字、標記、citekey、claim strength、validation boundary 與方法／限制語意。
  Use when 英文潤稿、潤飾英文稿、去英文 AI 味、English academic editing、de-AI the English
  manuscript、polish the English draft，或在 academic-pipeline 的 translate-en 之後、英文
  人工確認之前。內容源自 academic-humanizer v0.3.3 的 Layer 1/2/3/5；claim-evidence 改寫
  （原 Layer 4）刻意不納入，改由上游 claim-audit 負責；提案模式（原 Layer 6）另出獨立 skill。
license: MIT
metadata:
  version: "0.8.0"
allowed-tools: [Read, Write, Edit, Grep, Glob, AskUserQuestion]
---

# 英文潤稿站（academic-english-editing）

本 plugin 內建的英文學術潤稿站（0.8.0 起隨附）。在 translate-en 產出英文稿之後、人工英文確認之前選用：把 AI 生成的英文痕跡清掉、對齊學術慣例並貼近作者與期刊語氣，同時保住學術寫作本來就正確的精確、證據綁定語氣。技術寫作裡「中性而精準」就是人的聲音，不要注入意見、幽默或第一人稱個性。

## 掛點合約〔來源：academic-pipeline 潤稿站合約〕

- 這是**選用**站：可略過，但**不能取代**人工英文確認。
- **只可動語言呈現**；不得改數字、`<!-- results.* -->`／`<!-- table:* -->`／`<!-- claims.* -->` markers、`[@citekey]`、claim strength、validation boundary、方法或限制語意。
- 潤稿產生新英文版本 `manuscript/en/vN.md`（有 SI 時同步新版本）。
- 潤稿後重跑 `check_markers.py`、fact-checker 跨語意回查（每節抽 2–3 句回譯比對）與 reviewer-language；之後仍須**人工英文確認**與 full `check-consistency(en)`。
- 任何涉及 claim 強度、數字解讀、方法或限制的更動，**回上游來源 artifact**（claim-audit／interpret-results／validation），不在本站裁定。

### 為何不含 claim-evidence 改寫（原 academic-humanizer Layer 4）

academic-humanizer 的 Layer 4（把動詞降級到證據強度、替無依據主張補指標或 softening）會**改變 claim strength**，違反上面「只動呈現」的合約；而且走到本站時，claims 已在 claim-audit 審定並經人工確認。因此本站**不做** Layer 4 改寫：發現 over-claim 只**標記**並回報給 claim-audit／interpret-results，不自行改稿。原 Layer 4 的精神在 pipeline 內已由 claim-audit 的 entailment／強度攻擊與 `check_numbers.py` 落實。

## 何時用

編修英文學術散文：論文各節、摘要、rebuttal、related work。**不用於**部落格、行銷、個人隨筆，也**不是**規避 AI 使用揭露的工具。若要處理**經費／研究提案**（NSF、NIH 等），改用獨立 skill `grant-proposal-editing`（提案語域不同，賣的是願景與可行性，論文層的緊縮不適用）。

## 核心原則〔來源：academic-humanizer v0.3.3 · Core principle〕

學術寫作已經有正確的人聲：中性、精準、第三人稱複數（"we"）、每個主張都綁到證據。本站的工作是（1）在**不口語化**的前提下清掉 AI *tells*；（2）守住一般 humanizer 會漏掉的紀律——**保留每個數字、結果與引用，不讓任何動詞強過它的證據**（但改稿只在「呈現」層；證據強度的裁定屬 claim-audit）。

## 流程〔來源：academic-humanizer v0.3.3 · Process，依掛點合約調整〕

1. **Read**：讀英文稿與（若有）作者既有論文樣本；記下目標期刊語域。
2. **Audit（先不改）**：逐一列出偵測到的 pattern（位置＋建議改法）。涉及 claim 強度或數字解讀者標「→ 回 claim-audit」，不進本站改寫清單。
3. **Rewrite**：結構與內容不變，所有數字、markers、citekey、claim 標記保留，去除 tells、保留合法 hedging。
4. **Report**：輸出潤飾稿＋簡短 change log（移除的 pattern 類型、語氣／語域註記），並確認未動任何數字、方程式或引用。涵蓋原文涵蓋的一切：原本五段，改寫也五段。

---

以下 Layer 1／2／3／5 內容源自 `academic-humanizer` v0.3.3，逐層標註來源；僅去除與提案模式（原 Layer 6）相關的交叉引用。

## Layer 1：通用 AI-tell 清單〔來源：academic-humanizer v0.3.3 · Layer 1〕

掃描並修正這些通用 pattern，但受 Layer 3 的學術例外約束：
inflated significance（"marking a pivotal moment"）；superficial "-ing" tails that fake depth（"..., highlighting..."）；promotional／figurative language（"rich", "vibrant", "groundbreaking"）；vague attributions（"experts argue" with no cite）；AI vocabulary（*delve, underscore, intricate, tapestry, testament, landscape (abstract), pivotal, showcase, foster, leverage (filler), realm, seamless*）；copula avoidance（"serves as" → "is"）；negative parallelisms（"not just X, but Y"）；rule-of-three padding；elegant variation（cycling synonyms for one referent）；filler（"it is worth noting that", "in order to"）；**overlong, clause-stacked sentences（split them; 見 2.11）**；以及 **em-dashes（整個移除；改以逗號、冒號、括號或分句重寫）**。

**Before:** *Additionally, an enduring testament to the method's value is its ability to delve into intricate dependencies, showcasing a seamless integration that underscores its pivotal role.*
**After:** *The method also captures higher-order dependencies, which the baselines miss (Table 2).*

## Layer 2：學術 AI tells（移除或修正）〔來源：academic-humanizer v0.3.3 · Layer 2〕

### 2.1 Over-claiming verbs
實證工作 *shows* / *provides evidence*，不 *prove* / *demonstrate* 普世真理。
**Watch:** demonstrate, prove, establish, confirm, guarantee；"significantly" 無檢定／數字。
**Before:** *We prove that our method significantly outperforms all prior approaches.*
**After:** *Our method improves held-out accuracy by 4--7 points over the strongest prior approach (Table 3); the gain is significant at p < 0.01 by a paired test.*
（註：本站只在「呈現」層調語氣；若實際證據不足以支持動詞，屬 claim 強度問題，**標記回 claim-audit**，不在本站改寫。）

### 2.2 Significance hype
**Watch:** paves the way for, a crucial/pivotal step toward, has the potential to revolutionize, opens new avenues, sheds light on, of paramount importance, bridges the gap.
**Before:** *This work paves the way for a new paradigm and sheds light on a problem of paramount importance.*
**After:** *This work addresses one failure mode of prior methods: error accumulation under long-horizon rollout (Section 4).*

### 2.3 Empty intensifiers
**Watch:** extensive/comprehensive/thorough experiments, a wide range of, numerous, various.
**Before:** *We conduct extensive experiments on a wide range of datasets.*
**After:** *We evaluate on three datasets (ImageNet, CIFAR-100, and iNaturalist).*

### 2.4 Novelty padding
**Watch:** "novel" 每節超過一次；"to the best of our knowledge"；"for the first time".
**Before:** *We propose a novel framework and, to the best of our knowledge, are the first to study this.*
**After:** *We study online calibration under delayed labels, which prior calibration work (offline) does not address.*

### 2.5 Formulaic openers
**Watch:** "In recent years, X has attracted increasing attention"；"With the rapid development of..."；"Despite recent advances,...".
**Before:** *In recent years, tabular deep learning has attracted increasing attention.*
**After:** *Tabular deep learning has a structural limitation: most models discard feature-type metadata and must relearn it from data.*

### 2.6 Connective overuse
別讓連續句子都以 Moreover／Furthermore／Additionally／In particular 起頭；讓邏輯自己承接。
**Before:** *Moreover, the method is fast. Furthermore, it is simple. Additionally, it scales.*
**After:** *The method is fast and simple, and it scales to one million rows (Section 5).*

### 2.7 Contribution-list cliches
每條貢獻點名*具體*結果，不是重述摘要。
**Before:** *Our contributions are: (1) a novel method; (2) extensive experiments; (3) strong results.*
**After:** *We (1) introduce a metadata-aware encoder that reaches 0.91 AUROC vs 0.86 for the strongest baseline; (2) show it stays within 2 points under 20% label noise where the baseline drops 9; (3) release the benchmark.*

### 2.8 Citation dumping
引一兩篇真正相關的並說明為何，而非一串方括號。
**Before:** *Many methods exist [3, 7, 9, 12, 15].*
**After:** *The closest prior method is TabNet [7], which encodes all features jointly; we instead condition on feature-type metadata.*

### 2.9 Hedging-by-vagueness
**Watch:** somewhat, relatively, fairly, to some extent, quite. 量化或刪掉。
**Before:** *Performance is somewhat better and relatively robust.*
**After:** *Accuracy is 3 points higher and varies by less than 1 point across five seeds.*

### 2.10 Boilerplate emphasis
**Watch:** "It is worth noting that", "It should be emphasized that", "Notably,", "Importantly,". 若真重要，句子自己會顯示。
**Before:** *It is worth noting that, importantly, the gain holds across scenarios.*
**After:** *The gain holds across all three scenarios (Table 4).*

### 2.11 Overlong, clause-stacked sentences
AI 偏好用 "which"／"that"／"while"／"with" 串三四個子句的長句。拆開：一句一個意思，砍掉不承重的子句。**Watch:** 超過約 30 字、或 3＋子句的句子。
**Before:** *Existing methods, though promising, are largely empirical, with unclear principles underpinning their behavior, which limits their reliability and further progress.*
**After:** *Existing methods stay empirical. Their principles are unclear, which limits reliability and progress.*

## Layer 3：保留、不要過度矯正〔來源：academic-humanizer v0.3.3 · Layer 3〕

一般 humanizer 會抹平正當的學術構造，這些要留：

- **Evidence-tied hedging 是正確且必要的。** 當主張確實不確定時，保留 "suggests", "is consistent with", "we hypothesize that", "may indicate", "appears to"。*錯誤修法：*把 *"the results suggest X"* 改成 *"the results prove X"*——那是製造 over-claim。保留校準過的動詞。
- **被動語態**在動作者無關時沒問題：*"Samples were normalized to total protein."*
- **第一人稱複數 "we"** 是標準，不要為了避開它而重寫。
- **分號與偶爾的三連**適量可用。Em-dashes 是例外：整個移除（Layer 1），改以逗號、冒號、括號或分句重寫。
- **形式定義、具名方法／指標、術語、方程式與符號**照原樣保留。
- **絕不發明、刪除或更動任何數字、方程式或引用**；保留每個 cite key。（本站由 pipeline 的 `check_markers.py`／`check_numbers.py`／`check_citations.py` 與 full `check-consistency(en)` 機械把關。）

## Layer 5：語氣與期刊語域對齊〔來源：academic-humanizer v0.3.3 · Layer 5〕

若作者提供既有論文，先讀樣本，記下句子節奏、連接詞習慣、hedging 的程度與位置、如何開節、記號與慣用語，然後對齊。也對齊期刊語域（例如 ICLR／NeurIPS：簡練、直接、results-forward；Nature／PNAS：較說明性）。沒有樣本時，預設乾淨、精準、合乎期刊語域的散文，不要一般 humanizer 那種口語、帶意見的聲音。

---

## 來源與衍生說明（Provenance）

- **Layer 1／2／3／5、核心原則、流程、何時用**：源自 user skill `academic-humanizer` v0.3.3（MIT），逐節以〔來源：academic-humanizer v0.3.3 · …〕標註；文字大致照搬，僅移除與提案模式相關的交叉引用，並在 2.1／Layer 3 補上「改稿只在呈現層、證據強度回 claim-audit」的掛點註記。
- **「掛點合約」與「為何不含 claim-evidence 改寫」**：academic-pipeline 專屬新增〔來源：academic-pipeline 潤稿站合約〕，對齊 translate-en／status 對潤稿站的既有規範。
- **未納入**：academic-humanizer 的 Layer 4（claim-evidence discipline）不進本站；其職責在 pipeline 內由 claim-audit／interpret-results／`check_numbers.py` 承擔。
- **另行抽出**：academic-humanizer 的 Layer 6（NSF／NIH 提案模式，含 6.1–6.5）抽為獨立 skill `grant-proposal-editing`，不隨本 plugin（正交於研究→投稿流程）。

## Output

輸出潤飾後英文稿與簡短 change report：移除的 pattern（分類）、claim 相關但未改而標記回 claim-audit 的項目、語氣／語域註記，並確認無數字、方程式或引用遭更動。
