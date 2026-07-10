# 執行手冊（給任何 agent / 模型照著跑）

這份手冊讓**任何具備檔案操作與執行 shell 能力的 agent**（Claude、Gemini、GPT、本地模型，
搭配 Cursor / Cline / Aider / 各家 CLI）都能獨立跑完整個流程，不依賴特定廠商。

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

- [ ] `build/meta.html` 書目 header 已建（作者/單位/出處/年份/DOI/ISBN）
- [ ] `.para/.zh/.orig` 結構完整，三態切換能運作
- [ ] 換頁 `pgmark` **逐頁連續、無跳號**（放在該頁內容開始處）
- [ ] 譯文由**執行的模型親自逐段翻譯**，未呼叫任何機器翻譯工具/API 代翻
- [ ] 換頁 `pgmark` 標記齊全，可回查原書頁碼
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
