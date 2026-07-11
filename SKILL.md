---
name: translate-academic-paper
description: |
  Full workflow for translating an academic paper PDF into a polished, self-contained HTML
  with a three-way view toggle (Chinese-only / bilingual / original-only). Covers document
  triage (native vs OCR'd-scan vs no-text-layer scan), column-aware text extraction, glossary
  building with web-verified standard term translations (Traditional Chinese, Taiwan usage),
  figure/table capture, equation screenshot embedding, and combining into one distributable file.
  Use whenever the user wants to: translate a research paper / academic PDF, convert a paper to
  bilingual HTML, localize a journal/conference paper into Traditional Chinese, or continue an
  existing paper-translation project. Also triggers for: "幫我翻譯論文", "論文翻譯",
  "把論文做成中英對照", "翻譯這篇 paper", or continuation of a prior session.
---

# 學術論文翻譯工作流程

## 大方向

輸入一篇論文 PDF，輸出一個**單一自包含 HTML**（圖片/公式/掃描原頁全 base64 內嵌、CSS inline），
頂部可切換 **純中文 / 中英對照 / 純原文** 三種檢視。每節先產生 `build/sec01.html … secNN.html`，
最後 `combine_paper.py` 合併成 `build/論文_中譯.html`。

翻譯輸出**繁體中文（台灣用語）**。工具鏈：PyMuPDF (fitz)、Python 字串操作、WebSearch（查術語）。

與 TRPG 版的差異：論文求**精確可對回原文**而非文學再創作；術語**查標準譯法**而非創譯；
沒有角色卡/NPC 肖像，改處理**圖表、公式、參考文獻、雙欄、掃描檔**。

**適用範圍不限「論文」**：現代技術論文、人文/社科經典（如哲學論說文、歷史文獻）都適用，
差別只在**語域**——技術論文求精確簡潔；人文論說文求思辨流暢、保留修辭節奏（見 methodology.md）。

```
安裝依賴： pip install pymupdf pillow          # 核心
          pip install python-docx             # 選用：要輸出 .docx 才需要
```

### 執行環境與廠商中立
本 skill 為**廠商中立**：規則（references/）+ 腳本（scripts/）+ 這份 SKILL.md 自成一套，
任何能操作檔案、跑 shell 的 agent（Claude / Gemini / GPT / 本地模型，搭配 Cursor / Cline /
Aider / 各家 CLI）都能照 **`references/runbook.md`** 獨立跑完。

- **建議用視覺（多模態）模型**：掃描檔要「看頁面圖翻譯」；非視覺模型只能退回 OCR 文字流。
- **敏感史料注意**：翻譯 19 世紀以前經典時，原文常含當時殖民/種族/性別用語，這是正當的
  公有領域學術翻譯，但**某些代管 API 的輸出過濾器會誤判並回傳 400 擋掉輸出**。對策見 runbook：
  縮小輸出塊（一次一段、直接寫檔）、或把「逐段翻譯」這步交給過濾較寬鬆的模型執行。其餘步驟不受影響。

---

## 🚫 絕對規則：翻譯必須由你（執行的模型）親自逐段產出

**這條凌駕一切。違反即等於任務失敗。**

- **不得呼叫任何機器翻譯服務或工具代翻**：Google Translate / DeepL / 百度・有道翻譯 /
  `translate` CLI / 任何 MT 函式庫 / 另開一個 LLM API 去跑翻譯。翻譯本身**就是**這個任務。
- **不得把整段、整節、整章丟給翻譯工具再貼回**。外包會摧毀術語一致性、語域、頁碼對位與
  忠實度，交出來的是 Google 翻譯等級的東西——這正是本 skill 存在要避免的。
- **「我的 context 不夠」不是藉口**：本 skill 就是設計成**逐段／逐節增量進行**——
  一次翻一節、寫進 `build/secNN.html`、釋放 context 再繼續下一節。**你永遠不需要一次
  容納整本書**。分批做，不要為了省事偷吃步。
- **唯一允許呼叫外部工具的時機**：Phase 0 用 WebSearch **查術語的標準中譯**。
  那是「查證」不是「代翻」——查完仍由你自己下筆。
- 自我檢查：每寫完一節問自己「這段中文是我讀著原文親手譯的，還是我叫工具譯的？」
  若是後者，作廢重譯。

---

## Phase 0：領域理解 + 詞庫（⚠️ 翻譯前必做）

**最不能跳過的一步。** 術語第一節翻錯，後面全要回頭改。詳見 `references/glossary-guide.md`。

### 0-A：掌握領域與主題
1. 快速讀摘要、引言、各節標題、結論，掌握這篇在做什麼、屬哪個領域、方法論流派、核心貢獻。
2. 必要時 WebSearch 查領域背景。
3. 輸出 150–300 字「領域與主題摘要」，記在 `build/glossary.md` 最上方，作為全文用詞的語域錨點。

### 0-B：建立詞庫（三層）
- **第一層 領域核心術語**：反覆出現、決定理解的詞。**逐個 WebSearch 查主流中譯**
  （教育部學術名詞網 → 中文教科書/維基 → 社群慣例）。
- **第二層 本文自訂概念 / 模型名 / 縮寫**：模型與系統專名多**保留原文**（BERT、Transformer 不譯）；
  作者自造詞查無標準譯法就進「待確認」。
- **第三層 人名 / 機構 / 資料集 / 工具**：資料集與工具名**保留原文**（ImageNet、PyTorch）。

### 0-C：術語決策規則
- **唯一主流譯法** → 直接鎖定，不打擾使用者。
- **兩岸差異** → 取台灣繁中（最佳化 not 优化、演算法 not 算法、資訊 not 信息，見 methodology.md 對照表）。
- **≥2 種台灣譯法並存，或論文自造新詞** → 放「待確認」，翻該節前**一次問使用者**。
- 鎖定後全文一致，遇到照用不重決定。

---

## Phase 1：偵察 + 文件分類

```bash
python scripts/inspect_pdf.py paper.pdf              # 總覽：A/B/C 判定、欄數、圖表/公式/文獻
python scripts/inspect_pdf.py paper.pdf --page 3     # 細看某頁 block 座標
python scripts/inspect_pdf.py paper.pdf --fonts      # 字型統計（找 body/標題/caption 字型）
```

**必確認：**
1. **文件類型 A / B1 / B2 / C**（腳本判 A/B/C；B 類**必須加做髒度判級**）：
   - **A 原生電子檔** → 走 Phase 2 文字流。
   - **B1 乾淨掃描**（OCR 可信）→ 走 Phase 2，OCR 當底稿，翻譯時對照頁圖校對錯字。
   - **B2 髒掃描**（OCR 不可信）→ 走 **Phase 2-B2 批次流程**（見 runbook §B2）：
     **OCR = 只當定位器（locator only）**，乾淨原文必須逐頁看圖校訂，
     以 translation units 為正典資料層，批次推進、批批 QA。
   - **C 無文字層掃描檔** → 走 **Phase 1.5**，看圖直譯；長書可比照 B2 分層，原文層改看圖轉錄。

   **B1/B2 判級（兩分鐘）**：render 3 頁樣本 → 看圖數 OCR 錯字。
   **≲3 處/頁 → B1；>3 處/頁 → B2**。另見即判 B2 訊號：19 世紀老字體、
   手寫批註/圈線、頁面破損污漬、腳註密集。**只升不降**——B1 翻到一半
   發現錯誤密度超標，當場升 B2，已完成部分照 B2 標準重驗。
2. **offset**：書本印刷頁碼 = PDF page index + offset。核實一頁比對。
3. **欄數**：單欄/雙欄（會議論文常雙欄）。**輸出一律重排成單欄**。
4. **參考文獻起始頁**（之後不翻）。
5. 圖表 caption、編號公式的大致數量。
6. **書目資訊**：從標題頁／版權頁（或 DOI 查 Crossref）擷取**作者、單位(Affiliation)、
   出處(期刊·卷期·頁／出版社)、年份、DOI/ISBN**，寫成 `build/meta.html`（論文與專著都要，
   模板見 css-template.md 的「書目資訊 header」）。combine 會自動放在成品最上方。

---

## Phase 1.5：掃描檔整頁渲染（僅 B/C 類）

```bash
python scripts/render_pages.py paper.pdf --offset 0 --pages 0-12 --zoom 3.0
# C 類同時輸出可內嵌的原文頁圖：
python scripts/render_pages.py paper.pdf --offset 0 --b64
```

- 產生 `build/pages/p*.png`。**用 Read 工具逐張看這些圖，邊看邊翻**成 `sec*.html`——
  這是「人肉 OCR + 翻譯」一步到位，不跑 Tesseract（老掃描檔錯字會污染翻譯）。
- C 類的「原文」檢視欄直接放頁面原圖（`--b64` 產生的 data URI，見 css-template.md）。

---

## Phase 2：逐節翻譯

### 先取乾淨原文（A/B1 類；B2 走 Phase 2-B2，不用這步）
```bash
python scripts/extract_structure.py paper.pdf --offset 0 --out build/source.txt
```
產生**欄位還原、閱讀順序正確**的原文（雙欄直接 get_text 會左右串行），並標出
`[FIGURE]/[TABLE]/[EQ]/[REFERENCES]` 位置，讓你知道哪裡插圖/插公式/停止翻譯。

### section HTML 結構（關鍵）
每個 `build/secNN.html` 是完整 HTML，body 內含 `<section class="sec" id="secNN">`。
**段落一律用對照結構**（純中文檢視只是把 `.orig` 隱藏，原文不遺失）：

```html
<div class="para">
  <div class="zh">中文翻譯，術語首見附<span class="en">term</span>。引用標記 [12] 原樣保留。</div>
  <div class="orig">Original sentence, citation [12] kept verbatim.</div>
</div>
```

- 圖：放占位 `<figure class="fig" data-label="Figure 1"><figcaption>圖 1：中文圖說…</figcaption></figure>`
- 公式：獨立行 `<div class="eq" data-num="1"></div>`；行內 `<span class="eq" data-num="2"></span>`
- 參考文獻：`<section class="sec" id="sec-ref">` + `.references`，**原樣不翻**

完整模板見 `references/css-template.md`。

### 翻譯規則（摘要，詳見 `references/methodology.md`）
- 繁體中文、**台灣用語**。精確 > 通順 > 優雅。
- **引用標記 `[12]`、`(Smith, 2020)`、數值、單位、統計量 `p<0.05`、符號**：一律原樣保留。
- **領域術語首見**：`中文<span class="en">English</span>`，**純中版也附**。
- **模型/資料集/工具專名**：保留原文。**參考文獻**：整段不翻。
- 被動語態轉中文主動或無主句，別硬翻「被…」。
- 用詞照 Phase 0 詞庫，不重新決定。

### Phase 2.5：每章翻完立刻跑品質關卡（強制）

```bash
python scripts/check_translation.py build/secNN.html --min-page N1 --max-page N2
python scripts/check_fidelity.py   build/secNN.html   # 忠實度：數值/引用/長度比
```

`check_translation.py` 保**結構**（抽稿/缺原文/跳頁/腰斬句/簡體字）；
`check_fidelity.py` 補**內容忠實的客觀部分**——逐段比對 zh vs orig 的數值、引用標記
掉落與長度比離群，圈出疑似幻覺（漏譯/捏造/改寫）供人優先複核。兩者皆為機器層，
**語意錯譯（數字對、引用在、長度正常卻翻反意思）兩者都抓不到，仍須人工抽查對圖**。

實測抓過真的失敗案例：長章節被悄悄濃縮成幾段摘要交差（60 頁章節只給 9 段）。
**不要等全書合併完才靠肉眼抓，每章翻完當場跑這個腳本**，一併查抽稿／缺原文對照／
頁碼跳號逆行／簡體字混入四項。❌ FAIL 就打回重譯該章，通過才進下一章。詳見 runbook.md §4.5。

---

## Phase 2-B2：髒掃描批次流程（僅 B2 類；細節見 runbook §B2）

**核心原則：`頁面圖 = 證據；OCR = 定位器；乾淨原文 = 看圖校訂的轉錄；中文 = 逐段親譯`。**

分層產物（每層獨立存檔，HTML 只能由 units 生成）：
```
00 來源快照 → 01 頁面圖 → 02 page map → 03 乾淨原文 → 04 translation units(JSON)
→ 05 輸出(HTML/DOCX) → 06 QA 報告
```

**批次是常態**：~10 頁一批，**邊界必以完整段落收口**（跨頁段落跟到段尾）。
每批 JSON 記 `coverage.full_pages / partial_pages`；下一批開工先驗接縫
（前批尾段＋本批首段能無縫接上）。**每批 QA 通過才進下一批**——
batch 不是分工量，是「可驗證、可重做」的檢查點：壞了只重做一批，不會壞整章。

units 規則：
- `type`: `paragraph` / `footnote` / `heading` / `epigraph` / `caption`
- **跨頁腳註**合併為單一 footnote unit，`pages` 記實際跨頁，緊跟其出處段落
- **手寫批註/圈線/邊註一律不得進 orig**——那是前任讀者的痕跡，不是原文
- 題詩/歌謠用 `epigraph`，行間用 ` / ` 分隔
- 乾淨原文的校訂建議用**修正清單模式**（模型只輸出 OCR 底稿的 diff，不重打全文）：
  省 token、也可避開代管 API 對「大量輸出書籍原文」的過濾器誤判

units JSON → `units_to_section.py` 轉成標準 `build/secNN.html`（.para/.zh/.orig 結構）
→ 之後與 A/B1 共用 Phase 3–5（圖表、公式、combine）。

## Phase 3：圖表擷取

論文圖多為向量繪圖、表為排版表格（非點陣 xref），用 **caption 錨點 + 渲染整塊區域**。

```bash
# 1) 先看擷取對不對（強烈建議）
python scripts/place_figures.py paper.pdf --offset 0 --dry-run
# 抽看 build/figs/*.png，確認沒框錯

# 2) 注入某節（<figure data-label="Figure 3"> 會被填圖）
python scripts/place_figures.py paper.pdf --offset 0 --inject build/sec02.html
# 表格 caption 在表格上方的排版加 --table-above
```

- Figure 預設在 caption 上方、Table 在下方。
- **務必用 Read 抽看幾張 `build/figs/*.png`**——配錯比沒有更糟。
- 注入冪等，可反覆重跑調參。詳見 `references/pipeline-notes.md`。

---

## Phase 4：公式（原圖截圖內嵌）

公式一律截原圖，保證與原文一致、不重排。

```bash
python scripts/render_equations.py paper.pdf --dry-run             # 先看抓到哪些編號公式
python scripts/render_equations.py paper.pdf --auto --inject build/sec02.html
# 沒編號的置中公式，或多行公式沒截全，用手動：
python scripts/render_equations.py paper.pdf --manual 5:220-260 --out build/eq_x.png
```

- `--auto` 抓右對齊 `(N)` 編號公式。多行公式 / 無編號公式用 `--manual page:y0-y1`
  （y 座標用 `inspect_pdf.py --page N` 讀）。
- 行內純文字小公式（`x_i`）可直接打字，不必截圖。

---

## Phase 5：合併與輸出

**成品建議輸出到獨立目錄（如 `out/`），與工作檔 `build/` 分開。**

```bash
# HTML：三態切換（純中/對照/純原文）、浮動 TOC、全內嵌、內建列印樣式
python scripts/combine_paper.py --build build --out "out/論文_中譯.html" \
    --title "論文標題 — 中譯" --default-view both

# （選用）Word .docx：docx 無切換，用 --view 選版本（需 pip install python-docx）
python scripts/export_docx.py --build build --out "out/論文_中譯.docx" --view zh
python scripts/export_docx.py --build build --out "out/論文_對照.docx" --view both

# （保底）純文字對照：零依賴，裝不了 python-docx 時用
python scripts/export_txt.py --build build --out "out/論文_對照.txt" --view both
```

- **樣式由 combine 內建**（單一真相）：`.pgmark/.poem/.en/figure/.eq/.abstract` 等元件
  不論出現在哪一節都有樣式；section 檔的 `<style>` 只為單獨預覽用。要客製用 `--css`。
- **列印**：切到想要的檢視再列印，`@media print` 會隱藏 TOC/工具列、避免段落被切斷。

---

## 快速清單

**Phase 0（領域＋詞庫）**
- [ ] 讀摘要/引言/結論，寫 150–300 字領域摘要
- [ ] 建 `build/glossary.md`，第一層術語**逐個 WebSearch 查標準譯法**
- [ ] 兩岸差異取台灣繁中；模型/資料集名保留原文
- [ ] ≥2 種譯法或自造詞 → 待確認，一次問使用者

**Phase 1（偵察）**
- [ ] 確認 A/B1/B2/C 文件類型（inspect 判 A/B/C；B 類抽 3 頁對圖判 B1/B2）
- [ ] 確認 offset、欄數、參考文獻起始頁
- [ ] B/C 類 → 跑 render_pages；**B2 → 走批次流程（Phase 2-B2）**

**Phase 2–5**
- [ ] 寫 `build/meta.html` 書目 header（作者/單位/出處/年份/DOI/ISBN）
- [ ] extract_structure 取乾淨原文（A/B）
- [ ] 逐節翻成 sec*.html（用 .para/.zh/.orig 結構）
- [ ] **每章翻完跑 check_translation.py（結構）＋ check_fidelity.py（忠實度），FAIL 打回重譯，fidelity 疑點對圖複核，通過才繼續**
- [ ] place_figures --dry-run 眼睛確認 → --inject
- [ ] render_equations --auto/--manual 內嵌公式
- [ ] combine_paper 合併，開三態切換抽查

## 可執行腳本（scripts/）

| 腳本 | 用途 |
|------|------|
| `inspect_pdf.py` | Phase 1：A/B/C 分類、欄數、字型、圖表/公式/文獻偵測 |
| `render_pages.py` | Phase 1.5：整頁渲染（掃描檔看圖直譯 / 內嵌原頁）|
| `extract_structure.py` | Phase 2：欄位還原、閱讀順序正確的原文 + 結構標記 |
| `check_translation.py` | **Phase 2.5（強制）**：結構關卡——抽稿/缺原文/跳頁/腰斬句/簡體字，FAIL 即退出碼 1 |
| `check_fidelity.py` | **Phase 2.5**：忠實度——數值/引用掉落、長度比離群，圈疑似幻覺供人複核 |
| `units_to_section.py` | **Phase 2-B2**：translation units JSON → 標準 secNN.html |
| `export_txt.py` | Phase 5（保底）：零依賴純文字對照輸出 |
| `place_figures.py` | Phase 3：caption 錨點擷取圖表並注入 |
| `render_equations.py` | Phase 4：編號/手動公式原圖截圖內嵌 |
| `combine_paper.py` | Phase 5：合併 + 三態檢視切換 + TOC + 列印樣式（內建正典 CSS）|
| `export_docx.py` | Phase 5（選用）：另外輸出 Word .docx（--view zh/both/orig，需 python-docx）|
| `paper_utils.py` | 共用函式（被上面 import）|

## 詳細參考資料

- `references/runbook.md` — **可攜執行手冊**（給任何 agent/模型照著跑；視覺/非視覺兩路徑、交付檢查、過濾器對策）
- `references/methodology.md` — **翻譯方法論**（學術文體、被動語態、台灣術語、反翻譯腔、常見陷阱）
- `references/glossary-guide.md` — 詞庫建立與標準譯法查證流程
- `references/css-template.md` — section HTML 結構、對照/圖/公式/文獻模板、CSS
- `references/pipeline-notes.md` — 腳本原理、A/B/C 判定、雙欄坑、圖表/公式調參
