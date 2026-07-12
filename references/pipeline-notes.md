# 腳本原理、調參與踩過的坑

## 文件分類 A / B / C（paper_utils.classify_pdf）

- **A 原生電子檔**：有正常文字層。`text_coverage` 明顯 > 0，滿版影像少。走文字流。
- **B 已 OCR 掃描檔**：頁面是掃描影像（滿版 image）＋一層 OCR 文字。文字層常有錯字
  （l/1/O/0、缺字、亂序）。用文字層加速，但**翻譯時對照 `render_pages` 的頁圖校對**。
- **C 無文字層掃描檔**：`get_text` 幾乎空白。**不要跑 Tesseract**——老掃描檔錯誤率高會污染翻譯。
  改用 `render_pages.py` 渲染整頁，我用 Read 工具**看圖直譯**（人肉 OCR＋翻譯一步到位），
  對古籍、非拉丁文字、手寫混排更耐操。

判定是 heuristic，**務必用 `inspect_pdf.py` 覆核**。臨界個案（掃描品質很好、文字覆蓋率中等）
可能誤判 A/B，看 overview 的診斷數字自行決定走哪條。

## 欄位偵測與閱讀順序（雙欄論文的頭號坑）

`detect_columns` 用文字 block 水平中心的左右分布判斷。**滿寬 block（標題、跨欄表格、
跨欄公式）會被排除**，否則會干擾判斷。

`reading_order_blocks` 對雙欄採「左欄整欄由上到下，再右欄」。這對絕大多數兩欄論文正確，
但有幾個已知失敗模式：
- **跨欄元素**（標題橫幅、寬表格）中心接近頁面中線，可能被分到某一欄，順序略亂。
- **三欄或不規則排版**：目前只支援 1/2 欄，三欄會判成 2 欄，需手動處理。
- 若某頁順序明顯錯，用 `inspect_pdf.py --page N` 看 block 座標，必要時手動重排該頁原文。

`column_bounds` 用各欄 block 的 x 極值估欄寬，給 figure/equation 渲染定水平邊界。

## 圖表擷取（place_figures）

論文的圖多是**向量繪圖**、表是**排版表格**，都不是單張點陣 xref。所以不抓 xref，
改「以 caption 為錨點、渲染整塊區域」——向量、點陣、表格統一處理。

區域推算：
- **Figure**：圖在 caption **上方**。區域 = caption 上緣 → 同欄前一段內文下緣（沒有就到頁上緣）。
- **Table**：預設表在 caption **下方**（`--table-above` 可反轉，因為 IEEE/ACM 常 caption 在表上）。
- **跨欄大圖**：caption block 寬度 > 0.7 頁寬 → 區域取整頁寬。

已知坑：
- **上下堆疊多張圖**共用一段前文時，可能把兩張一起框進去 → `--dry-run` 抽看 `build/figs/`。
- **子圖 (a)(b)(c)**：整組會被當一張大圖擷取，通常是對的（子圖本就一起看）。
- **配錯比沒有更糟**：務必 Read 幾張 `build/figs/*.png` 眼睛確認再 `--inject`。

注入是**冪等**的：`<figure data-label="X">` 內舊的 `<img class="fig-img">` 會先被清掉再填，
可反覆重跑調參。

## 公式截圖（render_equations）

依需求：公式一律**原圖截圖**，保證與原文一致、不重排。

- `--auto`：抓**編號公式**。找右對齊的 `(N)`，渲染其所在排版 block（含 `(N)` 的 block
  通常就是整條 display equation），widen 到整欄寬。
- **多行公式**：若一條公式跨多個 block（PyMuPDF 有時把 align 環境拆行），`(N)` 只在最後一行，
  可能只截到最後一行 → 用 `--manual page:y0-y1` 補足完整範圍。
- **沒編號的置中公式**：`--auto` 抓不到，一律用 `--manual`。用 `inspect_pdf.py --page N`
  讀出公式的 y 座標範圍。
- 行內小公式若原文是純文字（如 `x_i`），可直接打字不用截圖；是圖才截。

配對：`<span class="eq" data-num="N">`（行內）或 `<div class="eq" data-num="N">`（獨立行），
`--inject` 填圖。同樣冪等。

## 合併（combine_paper）

- 只取**第一個** section 檔的 `<style>` 當全域 CSS（論文各節共用同一套樣式，
  不像 TRPG 角色卡有獨有 CSS，所以不需逐檔合併 CSS）。若某節有特殊樣式，
  把它放進第一個檔的 `<style>`，或用 `--css` 指定一份主 CSS。
- 三態切換靠 `.para/.zh/.orig` 結構 + `body.view-*` class。**寫 section 時務必用這結構**，
  否則對照/純中/純原文切換會失效。
- TOC 自動掃 `h1/h2` 注入 id。中文標題 slug 用 `[\w一-鿿]`，中文字會保留。

## 掃描檔原文欄內嵌（render_pages --b64）

C 類的「原文」檢視放整頁 JPEG（zoom 2.0、quality 78 已足夠閱讀又不爆檔案）。
渲染給我看圖直譯的 `build/pages/*.png` 則用 zoom 3.0 求清晰。兩者分開，別混用。

## 依賴

```
pip install pymupdf pillow
```

Pillow 目前非必需（本版腳本未用到白度計算），但保留以備擴充。PyMuPDF 是核心。

## 輸出樣式回歸樣本（改 CSS / 加 type 前後必看）

輸出 template 的「單一真相」是 `combine_paper.py` 的 `BASE_CSS + LAYOUT_CSS`——
section 檔**不該自帶元件樣式**，agent 也**不該每次手動微調成品 CSS**。若你發現某元件
（腳註/圖說/題詩/頁碼標記…）渲染不對，正解是**補進 BASE_CSS**，不是改單一成品。

根因通常是：`units_to_section.py` 產出了某個 class（如 `.para.footnote`、`.para.caption`），
但 BASE_CSS 沒有對應樣式 → 該元件吃到 `.para` 預設、跟正文沒區分。這種「孤兒 class」
就是「每次都要微調」的來源。

`tests/template_sample.units.json` 是一份**涵蓋全部 type**的樣本
（heading / paragraph / epigraph / footnote / caption / 跨頁 pgmark / 術語附原文）。
改動 CSS 或新增 unit type 後，跑一遍對照截圖確認每個元件都有樣式：

```bash
python scripts/units_to_section.py tests/template_sample.units.json --out /tmp/t/build/sec01.html
python scripts/combine_paper.py --build /tmp/t/build --out /tmp/t/all.html --default-view both --no-credit
# 用瀏覽器（或 headless 截圖）逐一比對：docs/template_all_elements.png 是基準樣貌
```

三態（純中/對照/純原文）都要掃一遍——`.orig`/`.zh` 顯隱由 view class 控制，
元件本身的字級/顏色/縮排則與 view 無關，兩者都不該破。
