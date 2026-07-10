"""
render_pages.py — Phase 1.5：整頁渲染（掃描檔 B/C 類用）

把 PDF 每頁渲染成高解析圖片，供兩種用途：
  1. C 類（無文字層）：我用 Read 工具直接看這些圖來「視覺直譯」，
     不經過 OCR，避免辨識錯字污染翻譯。
  2. B 類（已 OCR）：翻文字流時對照這些圖校對可疑處。
  3. 對照視圖的「原文」欄，掃描檔直接放頁面原圖。

輸出：
    build/pages/p{idx:03d}.png   逐頁圖檔（給我看）
    build/pages/pages.json       頁碼對照（idx → 書頁）
    build/pages_b64/p{idx:03d}.txt  （選用）base64 data URI，給 combine 內嵌原圖

用法：
    python render_pages.py paper.pdf --offset 0 --pages 0-10 --zoom 3.0
    python render_pages.py paper.pdf --offset 0 --b64      # 同時輸出 base64 供內嵌
"""
import argparse
import json
import sys
from pathlib import Path

try:
    import fitz
except ImportError:
    sys.exit("需要 PyMuPDF：pip install pymupdf")

sys.path.insert(0, str(Path(__file__).parent))
from paper_utils import book_page, render_page_b64


def parse_pages(spec, total):
    if not spec:
        return list(range(total))
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return [p for p in out if 0 <= p < total]


def main():
    ap = argparse.ArgumentParser(description="整頁渲染（掃描檔）")
    ap.add_argument("pdf")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--pages", help="0-10 或 0,3,5（0-indexed）")
    ap.add_argument("--zoom", type=float, default=3.0, help="渲染倍率（看圖直譯建議 3.0+）")
    ap.add_argument("--out", default="build/pages")
    ap.add_argument("--b64", action="store_true", help="同時輸出 base64 data URI（供內嵌原圖）")
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    idxs = parse_pages(args.pages, len(doc))
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    b64dir = Path("build/pages_b64")
    if args.b64:
        b64dir.mkdir(parents=True, exist_ok=True)

    mapping = {}
    mat = fitz.Matrix(args.zoom, args.zoom)
    for i in idxs:
        page = doc[i]
        pix = page.get_pixmap(matrix=mat, alpha=False)
        fp = outdir / f"p{i:03d}.png"
        pix.save(str(fp))
        mapping[i] = book_page(i, args.offset)
        if args.b64:
            (b64dir / f"p{i:03d}.txt").write_text(
                render_page_b64(page, zoom=2.0, fmt="jpeg", jpg_quality=78),
                encoding="utf-8")
        print(f"  p{i:03d}  → {fp.name}  (書頁 p.{mapping[i]})")

    (outdir / "pages.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDone → {outdir}  ({len(idxs)} pages)")
    print("接著：用 Read 工具逐張看 build/pages/p*.png，邊看邊翻成 sec*.html。")


if __name__ == "__main__":
    main()
