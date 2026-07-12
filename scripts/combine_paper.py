"""
combine_paper.py — Phase 5：合併全文為單一自包含 HTML

把 build/sec*.html 合併成一份可直接傳人的 HTML：
  - 頂部三態切換：純中文 / 中英對照 / 純原文
  - 浮動側邊 TOC（依 h1/h2 自動生成錨點）
  - 所有圖片、公式、掃描原頁全部 base64 內嵌 → 零外部相依

前提：每個 sec*.html 是「完整 HTML」，body 內含一個以上
      <section class="sec" id="secNN"> …，段落用對照結構：
      <div class="para"><div class="zh">中文</div><div class="orig">原文</div></div>

用法：
    python combine_paper.py --build build --out "build/論文_中譯.html" \
        --title "論文標題 — 中譯" --default-view both
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paper_utils import extract_sections

TOOLBAR = """
<div id="viewbar">
  <span class="vb-label">檢視</span>
  <button data-view="zh">純中文</button>
  <button data-view="both">中英對照</button>
  <button data-view="orig">純原文</button>
</div>
<script>
(function(){
  function setView(v){
    document.body.className = document.body.className
      .replace(/\\bview-\\w+\\b/g,'').trim() + ' view-' + v;
    document.querySelectorAll('#viewbar button').forEach(function(b){
      b.classList.toggle('active', b.dataset.view===v);
    });
    try{ localStorage.setItem('paperView', v); }catch(e){}
  }
  window.__setView = setView;
  document.addEventListener('DOMContentLoaded', function(){
    document.querySelectorAll('#viewbar button').forEach(function(b){
      b.addEventListener('click', function(){ setView(b.dataset.view); });
    });
    var saved = null; try{ saved = localStorage.getItem('paperView'); }catch(e){}
    setView(saved || document.body.dataset.defaultView || 'both');
  });
})();
</script>
"""

BASE_CSS = """
  /* ── 正典樣式（combine 擁有的單一真相；section 檔不必自帶元件樣式）── */
  :root {
    --ink:#1d1c1a; --muted:#7c766c; --rule:#e4ded3; --accent:#2f5b8a;
    --bg:#faf8f3; --card:#fffdf8; --tag:#eef3f8;
  }
  * { box-sizing:border-box; }
  body {
    margin:0; background:var(--bg); color:var(--ink);
    font-family:"Noto Serif TC","Source Han Serif TC","PMingLiU",serif;
    line-height:1.9; font-size:16.5px;
  }
  .sec { margin-bottom:44px; }
  h1 { font-family:"Noto Sans TC",sans-serif; font-size:26px; font-weight:900; margin:.2em 0 .5em; }
  h2 { font-family:"Noto Sans TC",sans-serif; font-size:19px; font-weight:800;
       color:var(--accent); margin:28px 0 8px; }
  h3 { font-family:"Noto Sans TC",sans-serif; font-size:16px; font-weight:700; margin:20px 0 4px; }
  .booktitle { font-family:"Noto Sans TC",sans-serif; font-size:14px; font-weight:700;
    color:var(--muted); letter-spacing:.22em; margin:0 0 4px; }
  .chapno { font-family:"Noto Sans TC",sans-serif; font-size:13px; color:var(--accent);
    letter-spacing:.28em; margin:8px 0 24px; }

  /* 術語首見附原文 */
  .en { font-family:"Noto Sans TC",sans-serif; font-size:.82em; font-weight:400;
        color:var(--muted); margin-left:1px; }
  .en::before { content:"（"; } .en::after { content:"）"; }

  .para { margin:0 0 18px; }

  /* 腳註（type=footnote；緊跟其出處段落，較正文小、灰階、左細線）*/
  .para.footnote { font-size:.88em; color:#5a5750; border-left:2px solid var(--rule);
    padding-left:14px; margin-top:-6px; }
  .para.footnote .orig { font-style:normal; }
  body.view-both .para.footnote { padding-left:0; border-left:none; }
  body.view-both .para.footnote .zh { border-left:2px solid var(--rule); padding-left:14px; }

  /* 獨立圖說 / 說明（type=caption）*/
  .para.caption { font-size:.9em; color:var(--muted); text-align:center; }

  /* 換頁標記：置於「該頁內容開始處」，逐頁不跳號 */
  .pgmark { display:block; text-align:center; color:var(--muted);
    font-family:"Noto Sans TC",sans-serif; font-size:11.5px; letter-spacing:.22em;
    padding:5px 0; margin:24px 0; border-top:1px dashed var(--rule);
    border-bottom:1px dashed var(--rule); }

  /* 詩歌 / 引詩：中英可並列 */
  .poem { margin:18px 0; padding-left:2em; line-height:1.7; }
  .poem .stanza + .stanza { margin-top:10px; }
  .poem .line { display:block; }
  .poem .zh { color:var(--ink); }
  .poem .orig { color:var(--muted); font-style:italic; }
  body.view-zh   .poem .orig { display:none; }
  body.view-orig .poem .zh   { display:none; }

  /* 摘要 */
  .abstract { background:var(--tag); border-radius:8px; padding:16px 20px; margin:18px 0; }
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

  /* 資料表 */
  table.data { border-collapse:collapse; width:100%; font-size:14px; margin:14px 0; }
  table.data th, table.data td { border:1px solid var(--rule); padding:6px 10px; text-align:left; }

  /* 參考文獻（不翻，原樣）*/
  .references { font-size:13.5px; line-height:1.7; }
  .references .ref { padding-left:2em; text-indent:-2em; margin-bottom:6px;
    font-family:"Noto Sans TC",sans-serif; color:#444; }
"""

LAYOUT_CSS = """
  /* ── 全文佈局 ── */
  body { display:flex; gap:0; }
  #toc {
    width:230px; min-width:230px; position:sticky; top:0;
    height:100vh; overflow-y:auto; background:var(--card);
    border-right:1px solid var(--rule); padding:24px 16px; flex-shrink:0;
    font-family:"Noto Sans TC",sans-serif;
  }
  #toc h2 { font-size:13px; letter-spacing:.25em; color:var(--muted);
    margin:0 0 14px; text-transform:uppercase; }
  #toc ol { margin:0; padding:0; list-style:none; }
  #toc a { display:block; padding:5px 8px; border-radius:6px; color:var(--ink);
    text-decoration:none; font-size:13px; line-height:1.4; transition:background .15s; }
  #toc a.lvl2 { padding-left:20px; font-size:12px; color:var(--muted); }
  #toc a:hover { background:var(--rule); }
  .main-content { flex:1; overflow-y:auto; }
  .wrap { max-width:1200px; margin:0 auto; padding:64px 28px 96px; }
  h1[id],h2[id],h3[id] { scroll-margin-top:70px; }

  /* ── 三態檢視切換 ── */
  #viewbar {
    position:fixed; top:0; right:0; left:230px; z-index:50;
    display:flex; align-items:center; gap:8px;
    background:var(--card); border-bottom:1px solid var(--rule);
    padding:8px 20px; font-family:"Noto Sans TC",sans-serif;
  }
  .vb-label { font-size:12px; letter-spacing:.2em; color:var(--muted); margin-right:6px; }
  #viewbar button {
    border:1px solid var(--rule); background:var(--bg); color:var(--ink);
    padding:5px 14px; border-radius:20px; font-size:13px; cursor:pointer;
    font-family:inherit; transition:all .15s;
  }
  #viewbar button:hover { border-color:var(--accent); }
  #viewbar button.active { background:var(--accent); color:#fff; border-color:var(--accent); }

  /* 純中文：藏原文 */
  body.view-zh  .para .orig { display:none; }
  /* 純原文：藏中文 */
  body.view-orig .para .zh { display:none; }
  body.view-orig .para .orig { display:block; }
  /* 對照：左右並排 */
  body.view-both .para {
    display:grid; grid-template-columns:1fr 1fr; gap:28px;
    align-items:start; margin:0 0 4px;
  }
  body.view-both .para .orig {
    display:block;
    color:var(--muted); font-size:.94em; border-left:2px solid var(--rule);
    padding-left:16px;
  }
  @media (max-width:900px){ body.view-both .para { grid-template-columns:1fr; } }

  /* ── 書目資訊 header（論文/專著共用，有值才顯示）── */
  .docmeta {
    border:1px solid var(--rule); border-radius:12px; background:var(--card);
    padding:24px 28px; margin:0 0 40px;
    box-shadow:0 1px 0 rgba(0,0,0,.03), 0 18px 40px -30px rgba(0,0,0,.25);
  }
  .docmeta .dm-type {
    display:inline-block; font-family:"Noto Sans TC",sans-serif; font-size:11.5px;
    letter-spacing:.22em; color:#fff; background:var(--accent);
    padding:3px 12px; border-radius:20px; margin-bottom:12px;
  }
  .docmeta .dm-title {
    font-family:"Noto Sans TC",sans-serif; font-size:22px; font-weight:900;
    margin:0 0 4px; line-height:1.4;
  }
  .docmeta .dm-title-en {
    display:block; font-size:14px; font-weight:400; color:var(--muted);
    font-style:italic; margin-top:2px;
  }
  .docmeta .dm-fields { margin:16px 0 0; padding:0; display:grid;
    grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:6px 28px; }
  .docmeta .dm-fields > div { display:flex; gap:10px; padding:5px 0;
    border-bottom:1px solid var(--rule); font-size:14px; }
  .docmeta dt { font-family:"Noto Sans TC",sans-serif; color:var(--muted);
    min-width:56px; flex-shrink:0; margin:0; }
  .docmeta dd { margin:0; }
  .docmeta dd a { color:var(--accent); word-break:break-all; }
  .docmeta .dm-note { margin:14px 0 0; font-size:12.5px; color:var(--muted);
    font-family:"Noto Sans TC",sans-serif; line-height:1.7; }

  /* ── 頁尾工具出處（可移除）── */
  .credit {
    margin:56px 0 0; padding:18px 20px; border-top:1px solid var(--rule);
    font-family:"Noto Sans TC",sans-serif; font-size:12.5px; line-height:1.8;
    color:var(--muted); text-align:center;
  }
  .credit a { color:var(--accent); text-decoration:none; }
  .credit a:hover { text-decoration:underline; }

  /* ── 列印：以目前檢視狀態列印，隱藏 TOC/工具列，避免段落被切斷 ── */
  @media print {
    #toc, #viewbar { display:none !important; }
    body { display:block; }
    .main-content { overflow:visible; }
    .wrap { max-width:100%; padding:0 12mm; }
    .para, .poem, figure.fig, .docmeta, .references .ref { break-inside:avoid; }
    h1, h2, h3 { break-after:avoid; }
    .credit { break-before:avoid; }
    a { color:inherit; text-decoration:none; }
    body.view-both .para { gap:16px; }
  }
"""

CREDIT = """
  <footer class="credit">
    本譯本以開源翻譯工具製作。工具原始碼與使用說明見
    <a href="https://github.com/Zaious/translate-academic-paper">github.com/Zaious/translate-academic-paper</a>，
    歡迎自由取用、修改與散布。
  </footer>"""


def slugify(text, i):
    s = re.sub(r'[^\w一-鿿]+', '-', text).strip('-').lower()
    return (s or f'h{i}')[:40]


def build_toc(sections_html):
    """給所有 h1/h2 注入 id，回傳 (改寫後的 html, toc_html)。"""
    items, counter = [], [0]

    def repl(m):
        tag, attrs, inner = m.group(1), m.group(2), m.group(3)
        clean = re.sub(r'<span class="en">.*?</span>', '', inner, flags=re.DOTALL)
        clean = re.sub(r'<[^>]+>', '', clean).strip()
        idm = re.search(r'id="([^"]+)"', attrs)
        if idm:
            anchor = idm.group(1)
            out = m.group(0)
        else:
            counter[0] += 1
            anchor = slugify(clean, counter[0])
            out = f'<{tag}{attrs} id="{anchor}">{inner}</{tag}>'
        if clean:
            items.append((tag, anchor, clean))
        return out

    html = re.sub(r'<(h[12])([^>]*)>(.*?)</\1>', repl, sections_html, flags=re.DOTALL)
    lis = []
    for tag, anchor, clean in items:
        cls = "lvl2" if tag == "h2" else "lvl1"
        lis.append(f'    <li><a class="{cls}" href="#{anchor}">{clean}</a></li>')
    toc = f'<nav id="toc">\n  <h2>目錄</h2>\n  <ol>\n' + "\n".join(lis) + '\n  </ol>\n</nav>'
    return html, toc


def main():
    ap = argparse.ArgumentParser(description="合併論文 section 成單一 HTML")
    ap.add_argument("--build", default="build")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="論文中譯")
    ap.add_argument("--default-view", default="both", choices=["zh", "both", "orig"])
    ap.add_argument("--css", help="附加自訂 CSS 檔（接在正典樣式之後，可覆寫）")
    ap.add_argument("--meta", help="書目資訊 header 片段（預設自動找 build/meta.html）")
    ap.add_argument("--no-credit", action="store_true", help="不加頁尾工具出處")
    args = ap.parse_args()

    build_dir = Path(args.build)
    files = sorted(build_dir.glob("sec*.html"))
    if not files:
        sys.exit(f"找不到 {build_dir}/sec*.html")

    # 書目 header：--meta 指定，或自動抓 build/meta.html
    meta_path = Path(args.meta) if args.meta else (build_dir / "meta.html")
    meta_html = ""
    if meta_path.exists():
        raw_meta = meta_path.read_text(encoding="utf-8")
        m = re.search(r'<header[^>]*class="docmeta"[^>]*>.*?</header>', raw_meta, re.DOTALL)
        meta_html = m.group(0) if m else raw_meta.strip()
        print(f"書目 header：{meta_path.name} ✓")
    else:
        print(f"書目 header：無（可建 {build_dir}/meta.html 補上作者/出版/DOI 等）")

    all_sections = []
    for f in files:
        raw = f.read_text(encoding="utf-8")
        secs = extract_sections(raw)
        if not secs:
            print(f"  ⚠ {f.name}: 沒找到 <section class=\"sec\">，略過")
        all_sections.extend(secs)
    print(f"合併 {len(files)} 檔、{len(all_sections)} 個 section")

    # 正典樣式由 combine 擁有（BASE + LAYOUT），不再依賴 sec01 的 <style>，
    # 確保任何元件（詩歌/圖/公式/摘要）不論出現在哪一節都有樣式。
    # --css 指定的檔案會「附加」在最後，可覆寫或補充。
    css = BASE_CSS + "\n" + LAYOUT_CSS
    if args.css:
        css += "\n/* --- 自訂 CSS --- */\n" + Path(args.css).read_text(encoding="utf-8")

    body_html = "\n\n".join(all_sections)
    body_html, toc = build_toc(body_html)
    # #5 給原文欄補 lang="en"（利於斷字、螢幕閱讀器、回溯）；已有 lang 的略過
    body_html = re.sub(r'<div class="orig"(?![^>]*\blang=)', '<div class="orig" lang="en"', body_html)

    full = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{args.title}</title>
<style>
{css}
</style>
</head>
<body data-default-view="{args.default_view}">
{toc}
<div class="main-content">
{TOOLBAR}
<div class="wrap">
{meta_html}
{body_html}
{"" if args.no_credit else CREDIT}
</div>
</div>
</body>
</html>
"""
    out = Path(args.out)
    out.write_text(full, encoding="utf-8")
    print(f"Done → {out}  ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
