"""
place_figures.py — Phase 3：圖表擷取與配對

論文的圖/表常是向量繪圖或排版表格，不是單張點陣 xref，硬抓 xref 會漏。
本腳本改用「caption 當錨點、渲染整塊圖形區域」：
  1. 找出每個 Figure/Table caption 的位置
  2. 圖形區域 = 該欄中，caption 與相鄰內文段落之間的空白帶
     （Figure 預設在 caption 上方；Table 預設在 caption 下方）
  3. 把該區域渲染成 PNG，配對到 HTML 裡 data-label 相符的 <figure>

先 --dry-run 看擷取結果（存到 build/figs/），眼睛確認後再 --inject。

用法：
    # 1) 先看擷取對不對（強烈建議）
    python place_figures.py paper.pdf --offset 0 --dry-run
    # 2) 注入某個 section 檔（<figure data-label="Figure 3"> 會被填圖）
    python place_figures.py paper.pdf --offset 0 --inject build/sec02.html
    # 表格 caption 在表格上方的排版：加 --table-above
"""
import argparse
import re
import sys
from pathlib import Path

try:
    import fitz
except ImportError:
    sys.exit("需要 PyMuPDF：pip install pymupdf")

sys.path.insert(0, str(Path(__file__).parent))
from paper_utils import (
    detect_columns, column_bounds, text_blocks, block_text, which_column,
    caption_kind_label, render_clip_b64,
)

TOP_MARGIN = 40      # 區域上界最多到頁面上緣多少 pt
BOT_MARGIN = 40
PAD = 4


def find_captions(page):
    """回傳該頁所有 caption：[(kind, label, bbox), ...]。"""
    out = []
    for b in text_blocks(page):
        t = block_text(b).strip()
        kind, label = caption_kind_label(t)
        if label:
            out.append((kind, label, b["bbox"]))
    return out


def graphic_rect(page, cap_bbox, kind, table_above=False):
    """依 caption 位置推算圖形區域 Rect。"""
    W, H = page.rect.width, page.rect.height
    ncols = detect_columns(page)
    bounds = column_bounds(page, ncols)
    cx0, cy0, cx1, cy1 = cap_bbox
    cap_wide = (cx1 - cx0) > 0.7 * W

    if cap_wide or ncols == 1:
        gx0, gx1 = min(cx0, 40), max(cx1, W - 40)
    else:
        ci = which_column((cx0 + cx1) / 2, bounds)
        gx0, gx1 = bounds[ci]

    # 圖形在 caption 的哪一側
    above = (kind == "figure") or (kind == "table" and table_above)

    # 同欄、與 caption 不同的內文 block，作為區域另一端界線
    same_col_blocks = [b for b in text_blocks(page)
                       if abs((b["bbox"][0] + b["bbox"][2]) / 2 - (gx0 + gx1) / 2) < (gx1 - gx0)
                       and b["bbox"] != cap_bbox]
    if above:
        aboves = [b["bbox"][3] for b in same_col_blocks if b["bbox"][3] <= cy0 + 2]
        gy1 = cy0 - PAD
        gy0 = (max(aboves) + PAD) if aboves else TOP_MARGIN
    else:
        belows = [b["bbox"][1] for b in same_col_blocks if b["bbox"][1] >= cy1 - 2]
        gy0 = cy1 + PAD
        gy1 = (min(belows) - PAD) if belows else (H - BOT_MARGIN)

    if gy1 - gy0 < 20:   # 太薄，放寬到半頁
        gy0, gy1 = (TOP_MARGIN, cy0 - PAD) if above else (cy1 + PAD, H - BOT_MARGIN)
    return fitz.Rect(gx0 - PAD, gy0, gx1 + PAD, gy1)


def collect(doc, offset, table_above, zoom):
    """掃全書，回傳 {label: (b64, page_idx)}。"""
    found = {}
    for i, page in enumerate(doc):
        for kind, label, bbox in find_captions(page):
            if label in found:
                continue  # 同 label 只取第一次
            rect = graphic_rect(page, bbox, kind, table_above)
            try:
                b64 = render_clip_b64(page, rect, zoom=zoom, fmt="png")
                found[label] = (b64, i, rect)
            except Exception as e:
                print(f"  ⚠ {label} (p{i}) render 失敗：{e}")
    return found


def inject(html_path, found):
    """把 <figure ... data-label="X"> 填入對應圖片（冪等：先清舊 img）。"""
    html = Path(html_path).read_text(encoding="utf-8")

    def repl(m):
        full, attrs = m.group(0), m.group(1)
        lm = re.search(r'data-label="([^"]+)"', attrs)
        if not lm:
            return full
        label = lm.group(1)
        entry = found.get(label)
        # 先移除舊注入的 img
        inner = re.sub(r'<img class="fig-img"[^>]*>\s*', '', m.group(2))
        if not entry:
            print(f"  · {label}: HTML 有 <figure> 但 PDF 未擷取到，跳過")
            return f'<figure{attrs}>{inner}</figure>'
        b64 = entry[0]
        print(f"  ✓ {label}: 注入（來自 PDF p{entry[1]}）")
        return f'<figure{attrs}><img class="fig-img" src="{b64}" alt="{label}">{inner}</figure>'

    html = re.sub(r'<figure([^>]*)>(.*?)</figure>', repl, html, flags=re.DOTALL)
    Path(html_path).write_text(html, encoding="utf-8")
    print(f"Done → {html_path}")


def main():
    ap = argparse.ArgumentParser(description="論文圖表擷取與注入")
    ap.add_argument("pdf")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--inject", help="要注入的 section HTML 檔")
    ap.add_argument("--dry-run", action="store_true", help="只把擷取結果存 build/figs/ 供眼睛檢查")
    ap.add_argument("--table-above", action="store_true", help="表格 caption 在表格上方的排版")
    ap.add_argument("--zoom", type=float, default=3.0)
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    found = collect(doc, args.offset, args.table_above, args.zoom)
    print(f"擷取到 {len(found)} 個圖表：{', '.join(sorted(found))}")

    if args.dry_run or not args.inject:
        import base64
        figdir = Path("build/figs")
        figdir.mkdir(parents=True, exist_ok=True)
        for label, (b64, pi, rect) in found.items():
            data = base64.b64decode(b64.split(",", 1)[1])
            safe = label.replace(" ", "_")
            (figdir / f"{safe}.png").write_bytes(data)
            print(f"  {label}: p{pi}  rect={tuple(round(x) for x in rect)} → figs/{safe}.png")
        print("\n⚠ 務必用 Read 工具抽看幾張 build/figs/*.png，配錯比沒有更糟。")
        print("確認 OK 後：python place_figures.py <pdf> --offset N --inject build/secXX.html")
    else:
        inject(args.inject, found)


if __name__ == "__main__":
    main()
