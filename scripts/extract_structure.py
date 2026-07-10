"""
extract_structure.py — Phase 2 前置：抽出乾淨、閱讀順序正確的原文

把 PDF 依「欄位還原」抽成單一 source 檔，讓翻譯時有正確順序的原文可用
（雙欄論文若直接 get_text 會左右串行）。同時標出圖表標題、公式、參考文獻界線，
方便翻譯時知道哪裡要插圖 / 插公式 / 停止翻譯。

輸出：
    build/source.txt   每頁一段，含頁碼標記與 [FIGURE]/[TABLE]/[EQ]/[REFERENCES] 標記

用法：
    python extract_structure.py paper.pdf --offset 0 --out build/source.txt
    python extract_structure.py paper.pdf --offset 0 --pages 0-8   # 只抽部分頁
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
    book_page, detect_columns, reading_order_blocks, block_text,
    caption_kind_label, EQNUM_RE,
)

REF_HEADINGS = ("references", "bibliography", "參考文獻", "引用文獻", "works cited")


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


def annotate_block(b):
    """把一個 block 轉成標記過的文字。"""
    t = block_text(b).strip()
    if not t:
        return ""
    kind, label = caption_kind_label(t)
    if label:
        return f"[{kind.upper()} — {label}] {t}"
    # 純編號公式行
    for line in b.get("lines", []):
        lt = "".join(s["text"] for s in line["spans"]).strip()
        if EQNUM_RE.match(lt):
            return f"[EQ {EQNUM_RE.match(lt).group(1)}] {t}"
    return t


def main():
    ap = argparse.ArgumentParser(description="抽出閱讀順序正確的論文原文")
    ap.add_argument("pdf")
    ap.add_argument("--offset", type=int, default=0, help="書本頁碼 = PDF page + offset")
    ap.add_argument("--pages", help="只抽指定頁，如 0-8 或 0,2,5（0-indexed）")
    ap.add_argument("--out", default="build/source.txt")
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    idxs = parse_pages(args.pages, len(doc))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    chunks, ref_hit = [], False
    for i in idxs:
        page = doc[i]
        ncols = detect_columns(page)
        header = (f"\n\n{'='*70}\n"
                  f"PDF page {i}  |  書頁 p.{book_page(i, args.offset)}  |  {ncols} 欄\n"
                  f"{'='*70}\n")
        parts = []
        for b in reading_order_blocks(page, ncols):
            t = block_text(b).strip()
            if not ref_hit and t[:40].lower().startswith(REF_HEADINGS):
                ref_hit = True
                parts.append("\n[REFERENCES ↓ 以下參考文獻不翻，原樣保留]\n")
            parts.append(annotate_block(b))
        chunks.append(header + "\n\n".join(p for p in parts if p))

    out.write_text("".join(chunks), encoding="utf-8")
    print(f"Done → {out}  ({out.stat().st_size // 1024} KB, {len(idxs)} pages)")
    print("提示：雙欄頁若順序仍怪，用 inspect_pdf.py --page N 檢查欄位切割。")


if __name__ == "__main__":
    main()
