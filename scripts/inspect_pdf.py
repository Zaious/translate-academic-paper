"""
inspect_pdf.py — Phase 1 偵察工具（論文版）

掃描 PDF，回報：
  1. 這篇是 A（原生電子檔）/ B（已 OCR 掃描檔）/ C（無文字層掃描檔）
  2. 每頁單欄 / 雙欄
  3. 字型 × 字級分布（找 body / 標題 / caption 字型）
  4. 偵測到的圖表標題（Figure/Table）與編號公式 (N)
  5. 參考文獻起始頁

用法：
    python inspect_pdf.py paper.pdf                 # 總覽
    python inspect_pdf.py paper.pdf --page 3        # 細看第 3 頁 (0-indexed)
    python inspect_pdf.py paper.pdf --fonts         # 字型統計
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

try:
    import fitz
except ImportError:
    sys.exit("需要 PyMuPDF：pip install pymupdf")

sys.path.insert(0, str(Path(__file__).parent))
from paper_utils import (
    classify_pdf, detect_columns, reading_order_blocks, block_text,
    text_coverage, caption_kind_label, EQNUM_RE,
)

REF_HEADINGS = ("references", "bibliography", "參考文獻", "引用文獻", "works cited")


def dump_page(doc, idx):
    page = doc[idx]
    ncols = detect_columns(page)
    print(f"\n{'='*72}\nPDF page {idx}  size {page.rect.width:.0f}×{page.rect.height:.0f}  "
          f"columns={ncols}  text-coverage={text_coverage(page):.3f}\n{'='*72}")
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            print(f"  [IMAGE] bbox={tuple(round(x) for x in b['bbox'])}")
            continue
        for line in b["lines"]:
            for span in line["spans"]:
                txt = span["text"].strip()
                if not txt:
                    continue
                x0, y0 = span["bbox"][0], span["bbox"][1]
                print(f"  font={span['font'][:22]:22s} sz={span['size']:4.1f} "
                      f"@({x0:4.0f},{y0:4.0f})  '{txt[:52]}'")


def font_stats(doc):
    counter = Counter()
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for line in b["lines"]:
                for span in line["spans"]:
                    if span["text"].strip():
                        counter[(span["font"], round(span["size"]))] += len(span["text"])
    print(f"\n{'字型':<30} {'字級':>5} {'字元數':>10}")
    print("-" * 50)
    for (font, size), n in counter.most_common(30):
        print(f"{font[:30]:<30} {size:>5} {n:>10}")
    print("\n提示：字元數最多的通常是 body；大字級低頻率的是標題；")
    print("     介於中間、常出現在圖表下方的中字級字型多半是 caption。")


def overview(doc):
    kind, diag = classify_pdf(doc)
    label = {"A": "A 原生電子檔（有文字層）",
             "B": "B 已 OCR 掃描檔（滿版影像＋文字層，注意辨識錯字）",
             "C": "C 無文字層掃描檔（需整頁渲染後視覺直譯）"}[kind]
    print(f"\n■ 文件類型判定：{label}")
    print(f"  依據：{diag}")
    print(f"  → {'走 Phase 2 文字流' if kind=='A' else '走 Phase 2 + 看圖校對' if kind=='B' else '走 Phase 1.5：render_pages.py 整頁渲染，我看圖直譯'}")

    # 欄位分布
    cols = Counter(detect_columns(p) for p in doc)
    print(f"\n■ 欄位分布：{dict(cols)}（1=單欄, 2=雙欄）→ 輸出一律重排成單欄")

    # 圖表 / 公式 / 參考文獻
    caps, eqs, ref_page = [], 0, None
    for i, page in enumerate(doc):
        for b in reading_order_blocks(page):
            t = block_text(b).strip()
            k, lbl = caption_kind_label(t)
            if lbl:
                caps.append((i, lbl))
            for line in b.get("lines", []):
                lt = "".join(s["text"] for s in line["spans"]).strip()
                if EQNUM_RE.match(lt):
                    eqs += 1
            if ref_page is None and t[:40].lower().startswith(REF_HEADINGS):
                ref_page = i
    print(f"\n■ 偵測到圖表標題 {len(caps)} 個：")
    for pi, lbl in caps[:40]:
        print(f"    p{pi}: {lbl}")
    if len(caps) > 40:
        print(f"    …（共 {len(caps)} 個）")
    print(f"\n■ 偵測到編號公式 (N) 約 {eqs} 個")
    print(f"■ 參考文獻起始：{'PDF page ' + str(ref_page) if ref_page is not None else '未自動偵測到（請人工確認）'}")
    print("\n下一步：確認 offset（書本頁碼 = PDF page + offset），"
          "再跑 extract_structure.py 產生 source。")


def main():
    ap = argparse.ArgumentParser(description="論文 PDF 偵察工具")
    ap.add_argument("pdf")
    ap.add_argument("--page", type=int, help="細看單頁（0-indexed）")
    ap.add_argument("--fonts", action="store_true", help="字型統計")
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    print(f"Total pages: {len(doc)}")
    if args.fonts:
        font_stats(doc)
    elif args.page is not None:
        dump_page(doc, args.page)
    else:
        overview(doc)


if __name__ == "__main__":
    main()
