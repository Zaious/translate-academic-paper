"""
units_to_section.py — Phase 2-B2：translation units JSON → 標準 secNN.html

把 B2 批次流程的正典資料層（units JSON，schema 見 runbook §B2）轉成
本 skill 標準的 section HTML（.para/.zh/.orig + pgmark），之後照常走
check_translation.py / combine_paper.py / export_docx.py / export_txt.py。

用法：
    python units_to_section.py batch01.units.json batch02.units.json --out build/sec02.html
    # 多個批次檔按參數順序串接；section_id / 標題取自第一個檔

type 對應：
    paragraph → <div class="para">…
    footnote  → <div class="para footnote">…（.zh 前加「〔註〕」）
    heading   → <h3>（若為全檔第一個 unit 則升 <h2> 作章標題）
    epigraph  → <div class="para poem">…（" / " 轉 <br>）
    caption   → <div class="para caption">…

pgmark：每遇到 unit 覆蓋到尚未標記的書頁，於該 unit 前輸出
    <div class="pgmark">原書 p.N</div>（連續多頁合併成 p.N–M）
"""
import argparse
import json
import pathlib
import sys


def esc_min(s):
    """最小跳脫：只處理裸 & 與 <>（保留 <span class="en"> 與 <br>）。"""
    out = s.replace("&", "&amp;")
    # 還原允許的 tag
    for tag in ('<span class="en">', "</span>", "<br>", "<br/>"):
        out = out.replace(tag.replace("&", "&amp;"), tag)
    return out


def pgmark(pages):
    if len(pages) == 1:
        return f'<div class="pgmark">原書 p.{pages[0]}</div>'
    return f'<div class="pgmark">原書 p.{pages[0]}–{pages[-1]}</div>'


def verse_html(text):
    return "<br>".join(part.strip() for part in text.split(" / "))


def unit_html(u, is_first):
    t = u.get("type", "paragraph")
    orig = esc_min(u.get("orig", "").strip())
    zh = esc_min(u.get("zh", "").strip())
    if t == "heading":
        tag = "h2" if is_first else "h3"
        label = zh or orig
        if zh and orig:
            label = f'{zh}<span class="en">{orig}</span>'
        return f"<{tag}>{label}</{tag}>"
    cls = {"paragraph": "para", "footnote": "para footnote",
           "epigraph": "para poem", "caption": "para caption"}.get(t, "para")
    if t == "epigraph":
        zh, orig = verse_html(zh), verse_html(orig)
    if t == "footnote" and zh and not zh.startswith(("〔註〕", "*")):
        zh = "〔註〕" + zh
    return (f'    <div class="{cls}">\n'
            f'      <div class="zh">{zh}</div>\n'
            f'      <div class="orig">{orig}</div>\n'
            f'    </div>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("units", nargs="+", help="units JSON files, in batch order")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", help="override section title (zh)")
    args = ap.parse_args()

    batches = [json.load(open(f, encoding="utf-8")) for f in args.units]
    head = batches[0]
    sec_id = head.get("section_id", "sec01")
    title_zh = args.title or head.get("title_zh", "")
    title_en = head.get("title_en", "")

    all_units = []
    for b in batches:
        if b.get("section_id") != sec_id:
            sys.exit(f"section_id mismatch: {b.get('section_id')} != {sec_id}")
        all_units.extend(b.get("units", []))
    if not all_units:
        sys.exit("no units found")

    body = []
    seen_pages = set()
    first_is_heading = all_units[0].get("type") == "heading"
    if not first_is_heading and title_zh:
        label = title_zh + (f'<span class="en">{title_en}</span>' if title_en else "")
        body.append(f"<h2>{label}</h2>")

    for i, u in enumerate(all_units):
        new_pages = [p for p in u.get("pages", []) if p not in seen_pages]
        if new_pages:
            seen_pages.update(new_pages)
            # 連續頁合併一個 pgmark；不連續就拆多個
            runs, run = [], [new_pages[0]]
            for p in new_pages[1:]:
                if p == run[-1] + 1:
                    run.append(p)
                else:
                    runs.append(run); run = [p]
            runs.append(run)
            for r in runs:
                body.append(pgmark(r))
        body.append(unit_html(u, is_first=(i == 0 and first_is_heading)))

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>{title_zh or sec_id}</title>
<style>/* 單獨預覽用；正式樣式由 combine_paper.py 提供 */
body{{font-family:serif;max-width:42em;margin:2em auto;line-height:1.8}}
.pgmark{{color:#999;font-size:.85em;margin:1em 0 .3em}}
.orig{{color:#666;font-size:.92em;margin-top:.4em}}
.para{{margin:1em 0}} .poem .zh,.poem .orig{{padding-left:2em}}
.footnote{{font-size:.9em;border-left:3px solid #ddd;padding-left:1em}}
.en{{color:#888;font-size:.85em;margin-left:.3em}}</style>
</head>
<body>
<section class="sec" id="{sec_id}">
{chr(10).join(body)}
</section>
</body>
</html>
"""
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    pages = sorted(seen_pages)
    print(f"Wrote {out}  ({len(all_units)} units, pages p.{pages[0]}–p.{pages[-1]})")


if __name__ == "__main__":
    main()
