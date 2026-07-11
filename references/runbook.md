# 執行手冊（給任何 agent / 模型照著跑）

這份手冊讓**任何具備檔案操作與執行 shell 能力的 agent**（Claude、Gemini、GPT、本地模型，
搭配 Cursor / Cline / Aider / 各家 CLI）都能獨立跑完整個流程，不依賴特定廠商。

## 交接強化句（把這段直接貼進你給執行 agent 的指令）

> 部分 agent（Codex/GPT、Antigravity/Gemini）會為了「效率」偷偷去接機器翻譯 API 或
> 另開 LLM 代翻，尤其在它覺得 context 不夠時。文件雖已明令禁止，但交接時在 prompt 層
> 再壓一次最保險。**複製下框：**

```text
翻譯這份 PDF 請讀 translate-academic-paper/SKILL.md 並嚴格遵守。
硬規則：所有中文譯文必須由你自己逐段翻譯。絕對禁止呼叫 Google Translate、DeepL、
任何機器翻譯工具，或另開 LLM API 代翻，也不可把整段丟工具再貼回。若你覺得 context
不夠，就一次只翻一節、寫進 secNN.html 再繼續——不要外包翻譯。唯一可用外部工具的時機
是用搜尋查術語標準譯法。另外，長章節不可濃縮成摘要交差，必須逐段全譯；每章翻完
立刻跑 python scripts/check_translation.py build/secNN.html --min-page N1 --max-page N2，
FAIL 就打回重譯該章，通過才可以進下一章。動工前先確認你理解以上規則。
```

> 實務：跑的時候瞄一眼它的 tool calls；看到它要接 translation API / MT 套件 / 開子模型
> 翻譯就中止並重貼上框。**check_translation.py 是客觀關卡，不是建議**——它 FAIL 時
> 不要接受「已經很接近了」之類的說法，堅持打回重譯到通過為止。

## 0. 前置

```bash
pip install pymupdf pillow
```

- **建議使用視覺（多模態）模型**：掃描檔（B/C 類）要「看頁面圖翻譯」，非視覺模型只能退回 OCR 文字。
- 工作目錄：在 PDF 旁建一個專案資料夾，內含 `build/`。所有產物放 `build/`。
- 把本 skill 整個資料夾（`scripts/` + `references/` + `SKILL.md`）一起帶著，供執行者讀規則、跑腳本。

## 1. 偵察（一定先做）

```bash
python scripts/inspect_pdf.py "TARGET.pdf"
```
記下：**文件類型 A/B/C**、**offset**（書頁 = PDF index + offset）、**欄數**、**參考文獻起始頁**、章節邊界。

**同時擷取書目資訊**（論文與專著都要）：從標題頁／版權頁（或 DOI 查 Crossref）取
**作者、單位、出處（期刊·卷期·頁／出版社）、年份、DOI/ISBN**，照 `css-template.md` 的
「書目資訊 header」寫成 **`build/meta.html`**。combine 會自動放在成品最上方（有值才填，缺的欄位刪列）。

## 2. 選執行路徑

| 情況 | 路徑 |
|------|------|
| **A 類**（原生電子檔） | `extract_structure.py` 取文字流 → 翻譯 |
| **B 類**（掃描+OCR，掃描清晰） | **當成 C 類做**：render 頁面、看圖翻譯（OCR 錯字太多不可信）|
| **B 類**（OCR 品質好） | 用文字流，翻譯時抽查頁圖校對 |
| **C 類**（無文字層） | render 頁面、看圖翻譯 |
| **執行者非視覺模型** | 只能用 `extract_structure.py` 文字流；掃描檔品質會受 OCR 限制，需人工校對 |

判斷「掃描清晰但 OCR 差」：跑 `extract_structure.py` 抽一頁看文字，若出現 `dOlninant`、
`WB.ATKNOWLBGDE` 這類亂碼，就改走看圖路徑。

## 3. 取得原文

**看圖路徑（B/C）：**
```bash
python scripts/render_pages.py "TARGET.pdf" --offset N --pages 4-9 --zoom 3.0
```
產出 `build/pages/p*.png`。執行者用「讀圖片」能力逐張看，邊看邊翻。

**文字路徑（A）：**
```bash
python scripts/extract_structure.py "TARGET.pdf" --offset N --out build/source.txt
```

## 4. 逐段翻譯 → 寫成 build/secNN.html

> 🚫 **硬規則：翻譯由你（執行的模型）親自產出，禁止外包給機器翻譯。**
> 不得呼叫 Google Translate / DeepL / MT 函式庫 / 另開 LLM API 代翻，不得把整段丟工具再貼回。
> **「context 不夠」不是理由**——這一步本來就一次只做一節：翻完一節寫進 `secNN.html`、
> 釋放 context 再做下一節，永遠不需要一次裝下整本書。唯一可呼叫外部工具的是 Phase 0
> 用 WebSearch 查術語標準譯法（查證，非代翻）。違反即任務失敗，須重譯。

**翻譯單位是「段落」，不是「頁」**（作者的段落常跨頁；按頁切會截斷論證）。
頁碼用行內標記保留：段落中間遇換頁就插 `<div class="pgmark">原書 p.6</div>`。

每個 `secNN.html` 是完整 HTML，body 內 `<section class="sec" id="secNN">`，段落一律用對照結構：
```html
<div class="para">
  <div class="zh">中文翻譯……術語首見附<span class="en">term</span>。</div>
  <div class="orig">校對過的乾淨原文（不是生 OCR）。</div>
</div>
```
> 「原文」欄放**執行者看圖校對過的乾淨原文**（修掉 OCR 錯字），而非未整理的 OCR。
> 完整結構、圖/公式/參考文獻寫法見 `css-template.md`。HTML 骨架可直接複製既有的 secNN.html。

**翻譯規則見 `methodology.md`**（依文本類型選語域：技術論文求精確；哲學/人文論說文求
思辨流暢）。術語一致性靠 `glossary.md`（見 `glossary-guide.md`），**先建詞庫再翻**。

## 4.5 每章翻完立刻跑品質關卡（強制，不可跳過）

> 這一步存在的理由：長章節（如 60+ 頁）容易被悄悄濃縮成幾段摘要交差——一本書實測
> 真的發生過（60 頁章節只給 9 段）。不要等全書合併完才用肉眼抓，**每章翻完當場跑**：

```bash
python scripts/check_translation.py build/secNN.html --min-page <該章起始書頁> --max-page <該章結束書頁>
```

- ❌ **FAIL**（退出碼非 0）：**打回重譯該章**，修完再跑一次，直到通過才能進下一章。
  常見 FAIL 原因：段落數相對頁數過低（抽稿／濃縮摘要）、大量 `.para` 缺 `.orig`、
  頁碼跳號過多或逆行、結尾頁碼早於預期（未譯完）。
- ⚠️ **WARN**：人工抽查判斷是否可接受（例如原書本身有跨頁插圖造成的頁碼小跳號）。
- 若懷疑有簡體字混入但預設模式沒抓到，可加 `--use-opencc` 做更廣（但較吵、需人工複核）的補充掃描。

全書譯完，對合併後的 `out/成品.html` 再跑一次同一支腳本（不必給 `--min-page/--max-page`），
確認整體一致。

## 5. 圖表 / 公式（若有）

```bash
python scripts/place_figures.py   "TARGET.pdf" --offset N --dry-run        # 先看
python scripts/place_figures.py   "TARGET.pdf" --offset N --inject build/secXX.html
python scripts/render_equations.py "TARGET.pdf" --auto --inject build/secXX.html
```
純文字的人文書（如 Spencer《教育論》）沒有圖表公式，跳過本步。

## 6. 合併與輸出

**建議把成品輸出到獨立目錄**（如 `out/`），與工作檔 `build/` 分開，避免混雜。

```bash
# 單一自包含 HTML（三態切換 / 浮動 TOC / 全內嵌 / 內建列印樣式）
python scripts/combine_paper.py --build build --out "out/成品_中譯.html" \
    --title "書名 — 中譯" --default-view both

# （選用）另外輸出 Word .docx —— docx 無切換，用 --view 選版本
python scripts/export_docx.py --build build --out "out/成品_中譯.docx"   --view zh
python scripts/export_docx.py --build build --out "out/成品_對照.docx"   --view both
```

- 樣式由 `combine_paper.py` 內建（單一真相），section 檔不必自帶元件 CSS。
- 列印：在瀏覽器切到想要的檢視再列印，`@media print` 會自動隱藏 TOC/工具列、避免段落被切斷。
- docx 需要 `pip install python-docx`。

## 每節交付檢查

- [ ] `python scripts/check_translation.py build/secNN.html` **通過（exit 0）**——
      涵蓋抽稿/缺原文/頁碼連續三項自動檢查，取代下面手動勾選的對應項目
- [ ] `build/meta.html` 書目 header 已建（作者/單位/出處/年份/DOI/ISBN）
- [ ] 譯文由**執行的模型親自逐段翻譯**，未呼叫任何機器翻譯工具/API 代翻
- [ ] 術語與 `glossary.md` 一致（無同詞多譯）
- [ ] 數字、專有名詞、引用標記無誤；參考文獻原樣未翻
- [ ] 抽幾段開「中英對照」比對原文，無漏譯、無誤植

---

## 敏感史料與輸出過濾器（重要）

翻譯**十九世紀以前的人文/社科經典**時，原文常含當時的殖民、種族、性別用語
（如 `savage`、`barbarian`、`wild tribes`、`aboriginal`、裸體或體罰描述）。這是**正當的
公有領域學術翻譯**，但**某些代管 API 的「輸出端內容過濾器」會誤判並回傳 400 擋掉輸出**。

若遇到輸出被擋：
1. **縮小輸出塊**：一次只翻一段、直接寫進檔案（用檔案編輯工具），不要在對話裡整段複述原文。
2. **改用輸出過濾較寬鬆的模型／端點**執行翻譯（本 skill 本就設計成廠商中立，可換家跑）。
3. 保持原文忠實，不因過濾而竄改或刪節；被擋只是傳輸問題，不是內容不當。

> 實務建議：規則設計、偵察、腳本除錯可在任一模型做；若某模型對特定史料反覆誤擋，
> 把「逐段翻譯」這一步交給不會誤判的模型執行，其餘步驟不受影響。

---

## §B2 髒掃描批次流程（B2 類專用完整操作）

> 適用：19 世紀老書、手寫批註、OCR 錯誤 >3 處/頁的掃描檔。
> 實戰驗證：Spencer《Education》(1894)——OCR 直翻曾造成整章損毀，本流程即其修正。

### 核心原則（一行記住）

```
頁面圖 = 證據   OCR = 定位器   乾淨原文 = 看圖校訂的轉錄   中文 = 逐段親譯
```

OCR 可輔助快速定位行文，**不得直接進 orig、更不得驅動翻譯**。

### 分層目錄（每層獨立產物，成品只能由 units 生成）

```
project/
├─ 00_source/          原 PDF、glossary、skill 快照、hash
├─ 01_pages/           整頁渲染圖 pNNN.png（NNN = PDF index）
├─ 02_page_map/        page_map.json：PDF index ↔ 書頁碼 ↔ 章節（⚠️ 用書底印刷頁碼核對，防 off-by-one）
├─ 03_english_clean/   看圖校訂後的乾淨原文（修正清單 or 全文轉錄）
├─ 04_translation_units/  secNN_pXXX_pYYY_batchNN.units.json（正典資料）
├─ 05_outputs/         HTML/DOCX（只從 units 生成，不得手改 HTML 當正本）
└─ 06_qa_reports/      每批 QA 結果
```

### 批次規則（常態，不是例外）

- **~10 頁一批**；邊界**必以完整段落收口**——目標範圍 p.94–103，若尾段跨到 p.104 就跟到段尾，下一批從下個完整段落開始。
- 每批 JSON 記 `coverage: {full_pages: [...], partial_pages: [...]}`——
  **邊界頁只覆蓋部分段落必須誠實記 partial**，QA 據此驗批次接縫（前批尾段＋本批首段無縫）。
- **每批 QA 通過才進下一批**。batch 是檢查點：壞了重做一批，不會壞整章。

### units JSON schema（正典資料層）

```json
{
  "section_id": "sec02",
  "title_en": "...", "title_zh": "...",
  "source": {"pdf_index": "93-102", "book_pages": "94-103", "images": "01_pages/p093.png-p102.png"},
  "coverage": {"full_pages": [94,95,...], "partial_pages": [], "notes": {}},
  "status": "draft",
  "units": [
    {"id": "sec02-p094-001", "type": "paragraph", "pages": [94,95],
     "orig": "看圖校訂過的乾淨英文。", "zh": "親手翻譯的繁體中文。"}
  ]
}
```

`type` 允許值與規則：
- `paragraph`：一般段落。跨頁段落一個 unit，`pages` 記實際跨頁。
- `footnote`：**跨頁腳註合併為單一 unit**，緊跟其出處段落之後（非頁面順序）。
- `heading` / `epigraph` / `caption`：標題／題詩（行間用 ` / ` 分隔）／圖說。
- **手寫批註、圈線、邊註一律不進 orig**——前任讀者的痕跡不是原文。

### 乾淨原文：修正清單模式（推薦）

不重打全文，讓模型只輸出 OCR 底稿的**差異**：

```
[p.25]
FIX: Hving consciousness => living consciousness     ← 錯字修正
DEL: EDUOA.TION.                                     ← 頁眉殘渣
PARA: This, however, is by no means                  ← 段落起點（OCR 丟失縮排）
TAIL: <錨點> => <整段替換文字>                        ← 批註毀損區：錨點後到頁尾整段重寫
HEAD: <錨點> => <整段替換文字>                        ← 頁首到錨點前整段重寫
```

好處：① 省 token ② 修正可審計、可重放 ③ **避開代管 API 對「大量輸出書籍原文」
的過濾器誤判**（模型輸出的是 diff，不是成篇原文）。
腳本套用修正 → 拼頁 → 按 PARA 切段 → 標 `[p.N]`／`[p.N–M]` 頁碼。
跨頁連字複合詞（如 `mechanically-` + `justified`）注意：接頁去連字號邏輯會誤拼，
遇到時把完整複合詞寫進前頁的 FIX。

### 轉 HTML 與後續

```bash
python scripts/units_to_section.py 04_translation_units/sec02_*.units.json --out build/sec02.html
python scripts/check_translation.py build/sec02.html --min-page 94 --max-page 168
# 之後與 A/B1 共用：combine_paper.py / export_docx.py / export_txt.py
```

### 每批 QA 清單

- [ ] JSON valid；每 unit 有非空 `orig`、`zh`、`pages`
- [ ] 頁碼落在 page_map 章節範圍內；`full_pages` 被 units 完整覆蓋
- [ ] 與**前一批**接縫無縫（前批尾段 + 本批首段）
- [ ] 無簡體字、無 OCR 殘渣模式（`EDUOATION`、`\v`、`1'0` 等）
- [ ] 段落數對照頁面圖 plausible，無可疑壓縮、無佔位文字
- [ ] 腳註齊全且緊跟出處段落
- [ ] 跑 `check_fidelity.py`（單批 units 或轉出的 HTML 皆可）：數值/引用掉落、長度比離群 → 圈出的段落優先對圖看
- [ ] **人工抽查 2–3 段對圖**：機器只圈客觀痕跡，語意錯譯（意思翻反）必須人眼抽檢
