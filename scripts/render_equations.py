"""
render_equations.py — Phase 4：公式原圖截圖內嵌

依你的選擇：公式一律以「原圖截圖」保留，保證與原文一模一樣。

兩種模式：
  --auto   自動抓「編號公式」：找右側對齊的 (N) 標記，渲染其所在 block
           （含 (N) 的排版 block 通常就是整條 display equation）
  --manual 手動指定區域：page:y0-y1[,col]，處理沒有編號的置中公式

配對方式：HTML 裡放 <span class="eq" data-num="3"></span>（行內）或
          <div class="eq" data-num="3"></div>（獨立行），腳本填入圖片。

用法：
    python render_equations.py paper.pdf --dry-run                 # 先看抓到哪些
    python render_equations.py paper.pdf --auto --inject build/sec02.html
    python render_equations.py paper.pdf --manual 5:220-260 --out build/eq_extra.png
"""
import argparse
import base64
import re
import sys
from pathlib import Path

try:
    import fitz
except ImportError:
    sys.exit("需要 PyMuPDF：pip install pymupdf")

sys.path.insert(0, str(Path(__file__).parent))
from paper_utils import (
    detect_columns, column_bounds, text_blocks, which_column,
    render_clip_b64, EQNUM_RE,
)

PAD = 3


def find_numbered(page):
    """回傳 [(num, block_bbox_widened_to_column), ...]。"""
    ncols = detect_columns(page)
    bounds = column_bounds(page, ncols)
    out = []
    for b in text_blocks(page):
        num = None
        for line in b.get("lines", []):
            lt = "".join(s["text"] for s in line["spans"]).strip()
            m = EQNUM_RE.match(lt)
            if m:
                num = m.group(1)
                break
        if not num:
            continue
        x0, y0, x1, y1 = b["bbox"]
        ci = which_column((x0 + x1) / 2, bounds)
        cx0, cx1 = bounds[ci]
        rect = fitz.Rect(min(x0, cx0) - PAD, y0 - PAD, max(x1, cx1) + PAD, y1 + PAD)
        out.append((num, rect))
    return out


def collect_auto(doc, zoom):
    found = {}
    for i, page in enumerate(doc):
        for num, rect in find_numbered(page):
            if num in found:
                continue
            try:
                found[num] = (render_clip_b64(page, rect, zoom=zoom, fmt="png"), i, rect)
            except Exception as e:
                print(f"  ⚠ eq({num}) p{i} 失敗：{e}")
    return found


def inject(html_path, found):
    html = Path(html_path).read_text(encoding="utf-8")

    def repl(m):
        tag, attrs = m.group(1), m.group(2)
        nm = re.search(r'data-num="([^"]+)"', attrs)
        if not nm:
            return m.group(0)
        num = nm.group(1)
        entry = found.get(num)
        if not entry:
            print(f"  · eq({num}): HTML 有占位但未擷取到，跳過")
            return m.group(0)
        print(f"  ✓ eq({num}): 注入（PDF p{entry[1]}）")
        cls = "eq-img" + (" eq-inline" if tag == "span" else "")
        return f'<{tag}{attrs}><img class="{cls}" src="{entry[0]}" alt="equation {num}"></{tag}>'

    html = re.sub(r'<(span|div)([^>]*class="eq"[^>]*)>.*?</\1>', repl, html, flags=re.DOTALL)
    Path(html_path).write_text(html, encoding="utf-8")
    print(f"Done → {html_path}")


def manual(doc, spec, out, zoom):
    """spec: 'page:y0-y1' 或 'page:y0-y1,col'（col 0-indexed）。"""
    m = re.match(r'(\d+):(\d+)-(\d+)(?:,(\d+))?$', spec)
    if not m:
        sys.exit("格式：page:y0-y1[,col]  例 5:220-260 或 5:220-260,1")
    pi, y0, y1 = int(m.group(1)), int(m.group(2)), int(m.group(3))
    page = doc[pi]
    bounds = column_bounds(page, detect_columns(page))
    if m.group(4) is not None:
        cx0, cx1 = bounds[int(m.group(4))]
    else:
        cx0, cx1 = 0, page.rect.width
    rect = fitz.Rect(cx0 - PAD, y0 - PAD, cx1 + PAD, y1 + PAD)
    b64 = render_clip_b64(page, rect, zoom=zoom, fmt="png")
    data = base64.b64decode(b64.split(",", 1)[1])
    Path(out).write_bytes(data)
    print(f"Done → {out}  (p{pi} y{y0}-{y1})")
    print("把它的 base64 貼進 HTML，或改成 <div class='eq' data-num='X'> 後用 --auto 流程。")


def main():
    ap = argparse.ArgumentParser(description="公式原圖截圖")
    ap.add_argument("pdf")
    ap.add_argument("--auto", action="store_true", help="自動抓編號公式 (N)")
    ap.add_argument("--manual", help="手動區域 page:y0-y1[,col]")
    ap.add_argument("--inject", help="要注入的 section HTML")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default="build/eq_manual.png")
    ap.add_argument("--zoom", type=float, default=3.5)
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    if args.manual:
        manual(doc, args.manual, args.out, args.zoom)
        return

    found = collect_auto(doc, args.zoom)
    print(f"抓到編號公式 {len(found)} 條：{', '.join('('+n+')' for n in sorted(found))}")
    if args.dry_run or not args.inject:
        eqdir = Path("build/eqs")
        eqdir.mkdir(parents=True, exist_ok=True)
        for num, (b64, pi, rect) in found.items():
            data = base64.b64decode(b64.split(",", 1)[1])
            (eqdir / f"eq_{num}.png").write_bytes(data)
            print(f"  ({num}) p{pi} rect={tuple(round(x) for x in rect)} → eqs/eq_{num}.png")
        print("\n⚠ 抽看幾張 build/eqs/*.png，確認邊界沒切到內文或漏掉多行公式。")
        print("沒編號的置中公式用 --manual page:y0-y1 補。")
    else:
        inject(args.inject, found)


if __name__ == "__main__":
    main()
