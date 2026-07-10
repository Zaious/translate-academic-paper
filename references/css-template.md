# HTML/CSS 模板（論文版）

## 書目資訊 header（build/meta.html）

**論文與專著都要在成品最上方放一個書目 header**，記錄作者、單位、出版來源、年份、DOI/ISBN 等。
做法：把下面的 `<header class="docmeta">…</header>` 存成 **`build/meta.html`**，`combine_paper.py`
會自動抓它放在全文最前面（樣式由 combine 內建，不必自己寫 CSS）。**有值才填，沒有的欄位整列刪掉**，
不要留空或填「N/A」。資料來源：PDF 標題頁／版權頁，或用 DOI 查 Crossref。

### 論文（期刊/會議）
```html
<header class="docmeta">
  <div class="dm-type">期刊論文 · Journal Article</div>
  <h1 class="dm-title">中文標題翻譯<span class="dm-title-en">Original English Title</span></h1>
  <dl class="dm-fields">
    <div><dt>作者</dt><dd>Jane Doe, John Smith</dd></div>
    <div><dt>單位</dt><dd>Stanford University；MIT</dd></div>
    <div><dt>出處</dt><dd>Nature Machine Intelligence, 5(3), 210–225</dd></div>
    <div><dt>年份</dt><dd>2023</dd></div>
    <div><dt>DOI</dt><dd><a href="https://doi.org/10.1038/xxxxx">10.1038/xxxxx</a></dd></div>
  </dl>
  <p class="dm-note">原文語言：英文。本譯本為中文翻譯，僅供研讀；正式引用請以原文為準。</p>
</header>
```

### 專著（書籍）
```html
<header class="docmeta">
  <div class="dm-type">專著 · Monograph</div>
  <h1 class="dm-title">教育論：智育・德育・體育<span class="dm-title-en">Education: Intellectual, Moral, and Physical</span></h1>
  <dl class="dm-fields">
    <div><dt>作者</dt><dd>Herbert Spencer</dd></div>
    <div><dt>出版</dt><dd>New York: L. Burt Company</dd></div>
    <div><dt>出版地</dt><dd>New York</dd></div>
    <div><dt>年份</dt><dd>1894</dd></div>
    <div><dt>版次</dt><dd>—</dd></div>
    <div><dt>ISBN</dt><dd>—</dd></div>
  </dl>
  <p class="dm-note">原文語言：英文。公有領域文本；中文翻譯僅供研讀。</p>
</header>
```

常用欄位：`作者 / 單位(Affiliation) / 出處(期刊·卷期·頁) / 出版(出版社) / 出版地 / 年份 /
版次 / DOI / ISBN / 譯者 / 原文語言`。論文重 DOI 與期刊卷期；專著重出版社與版次。

## 每個 section 檔的結構

每個 `build/secNN.html` 是**完整 HTML**（可單獨在瀏覽器打開檢查），
body 內含一個以上 `<section class="sec" id="secNN">`。合併時 `combine_paper.py`
會抽出這些 `<style>` 與 `<section>`，加上三態切換與 TOC。

**核心：段落用「對照結構」`.para`，內含 `.zh`（中文）與 `.orig`（原文）。**
combine 的三態切換靠這個結構運作，所以**即使你偏好純中文閱讀，也要照這結構寫**——
純中文檢視只是把 `.orig` 隱藏，原文不會遺失。

> **樣式由 combine 擁有（單一真相）**：`combine_paper.py` 內建整套正典 CSS
> （`.para/.zh/.orig`、`.pgmark`、`.poem`、`.en`、`figure.fig`、`.eq`、`.abstract`、
> `table.data`、三態切換、書目 header、頁尾、列印樣式）。因此**任何元件不論第一次出現在
> 哪一節都有樣式**，不會因為只有 sec01 帶了 CSS 而讓後面章節的詩歌/圖/公式裸奔。
> section 檔的 `<style>` 只為「單獨預覽該檔」用，可極簡或省略；要客製整體樣式用
> `combine_paper.py --css custom.css`（附加在正典之後可覆寫）。

> **原文欄標語言**：`.orig` 請寫成 `<div class="orig" lang="en">`（原文語言代碼）。
> 有助於瀏覽器斷字、螢幕閱讀器與回溯原文。combine 也會自動替沒標的補上 `lang="en"`。

> **換頁標記約定**：`<div class="pgmark">原書 p.N</div>` 放在**「該頁內容開始處」**
> （即「以下為原書第 N 頁」），且**逐頁連續、不可跳號**。段落跨頁時，標記插在跨頁後
> 那一段的前面（句子中間換頁就近似取段界）。交付前檢查頁碼有無斷號。

```html
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>論文標題 — 第 2 節</title>
<style>
  :root {
    --ink:#1d1c1a; --muted:#7c766c; --rule:#e4ded3; --accent:#2f5b8a;
    --bg:#faf8f3; --card:#fffdf8; --tag:#eef3f8;
  }
  * { box-sizing:border-box; }
  body {
    margin:0; background:var(--bg); color:var(--ink);
    font-family:"Noto Serif TC","Source Han Serif TC","PMingLiU",serif;
    line-height:1.9; font-size:16px;
  }
  .wrap { max-width:820px; margin:0 auto; padding:48px 28px 96px; }
  .sec { margin-bottom:40px; }

  h1 { font-family:"Noto Sans TC",sans-serif; font-size:26px; font-weight:900; margin:.2em 0 .6em; }
  h2 { font-family:"Noto Sans TC",sans-serif; font-size:19px; font-weight:800;
       color:var(--accent); margin:28px 0 8px; }
  h3 { font-family:"Noto Sans TC",sans-serif; font-size:16px; font-weight:700; margin:20px 0 4px; }

  /* 術語首見附原文（純中文檢視也保留）*/
  .en { font-family:"Noto Sans TC",sans-serif; font-size:.82em; font-weight:400;
        color:var(--muted); margin-left:2px; }
  .en::before { content:"（"; } .en::after { content:"）"; }

  /* 對照段落（預設單欄流；對照檢視由 combine 的 body.view-both 轉兩欄）*/
  .para { margin:0 0 14px; }
  .para .orig { display:none; }        /* 單檔預覽時預設只看中文；combine 會覆寫 */

  /* 摘要 */
  .abstract { background:var(--tag); border-radius:8px; padding:18px 22px; margin:18px 0; }
  .abstract h2 { margin-top:0; }

  /* 圖表 */
  figure.fig { margin:22px 0; text-align:center; }
  figure.fig .fig-img { max-width:100%; height:auto; border-radius:6px;
    box-shadow:0 1px 10px rgba(0,0,0,.12); }
  figure.fig figcaption { font-size:13px; color:var(--muted); margin-top:8px;
    font-family:"Noto Sans TC",sans-serif; line-height:1.6; }

  /* 公式（原圖截圖）*/
  .eq { display:block; text-align:center; margin:18px 0; }
  .eq .eq-img { max-width:92%; height:auto; }
  .eq .eq-img.eq-inline { display:inline; vertical-align:middle; max-height:1.4em; margin:0 2px; }

  /* 參考文獻：原樣、等寬、不翻 */
  .references { font-size:13.5px; line-height:1.7; }
  .references .ref { padding-left:2em; text-indent:-2em; margin-bottom:6px;
    font-family:"Noto Sans TC",sans-serif; color:#444; }

  /* 引用標記、數值保持原樣，不特別樣式化 */
  table.data { border-collapse:collapse; width:100%; font-size:14px; margin:14px 0; }
  table.data th, table.data td { border:1px solid var(--rule); padding:6px 10px; text-align:left; }
</style>
</head>
<body>
<div class="wrap">

  <section class="sec" id="sec02">
    <h2>2. 方法<span class="en">Methods</span></h2>

    <div class="para">
      <div class="zh">我們提出一種基於注意力機制<span class="en">attention</span>的模型，
        在 GLUE 基準<span class="en">GLUE benchmark</span>上取得顯著提升 [12]。</div>
      <div class="orig" lang="en">We propose an attention-based model that achieves significant
        improvements on the GLUE benchmark [12].</div>
    </div>

    <!-- 詩歌 / 引詩：可中英並列（純中/純原文檢視各自顯示）-->
    <div class="poem">
      <div class="stanza">
        <span class="line zh">縱使人能確信</span>
        <span class="line orig" lang="en">Could a man be secure</span>
      </div>
    </div>

    <!-- 公式占位：render_equations.py --auto --inject 會填圖 -->
    <div class="eq" data-num="1"></div>

    <div class="para">
      <div class="zh">其中 <span class="eq" data-num="2"></span> 表示第 i 層的隱藏狀態。</div>
      <div class="orig">where <span class="eq" data-num="2"></span> denotes the hidden state of layer i.</div>
    </div>

    <!-- 圖占位：place_figures.py --inject 會把 <img class="fig-img"> 塞進來 -->
    <figure class="fig" data-label="Figure 1">
      <figcaption>圖 1：模型架構總覽。<span class="en">Figure 1: Overview of the model architecture.</span></figcaption>
    </figure>
  </section>

</div>
</body>
</html>
```

## 參考文獻 section（不翻）

```html
<section class="sec" id="sec-ref">
  <h2>參考文獻<span class="en">References</span></h2>
  <div class="references">
    <div class="ref">[1] Vaswani, A., et al. (2017). Attention is All You Need. NeurIPS.</div>
    <div class="ref">[2] Devlin, J., et al. (2019). BERT: Pre-training of Deep Bidirectional Transformers. NAACL.</div>
  </div>
</section>
```

## 掃描檔（C 類）的原文欄放頁面原圖

C 類沒有可靠文字層，`.orig` 直接放整頁圖（`render_pages.py --b64` 產生）：

```html
<div class="para">
  <div class="zh">（我看著頁面圖翻出的中文）……</div>
  <div class="orig"><img src="data:image/jpeg;base64,..." alt="原文頁面" style="max-width:100%"></div>
</div>
```

## 配色語義

論文版預設用**冷色學術調**（`--accent:#2f5b8a` 藍），跟 TRPG 版的暖紅區隔。
要換色改 `:root` 即可。深色模式非必要，論文多用於列印/PDF 匯出，維持淺底即可。

## 三態切換（combine 自動加）

`combine_paper.py` 會在頂部加「純中文 / 中英對照 / 純原文」按鈕，
靠切換 `body.view-zh` / `.view-both` / `.view-orig` 控制 `.para .zh` / `.orig` 顯隱。
你在寫 section 時**不用管切換邏輯**，只要照 `.para/.zh/.orig` 結構寫即可。
