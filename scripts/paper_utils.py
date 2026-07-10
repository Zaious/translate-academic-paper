"""
paper_utils.py — 學術論文翻譯共用工具

被 inspect_pdf.py / extract_structure.py / place_figures.py /
render_equations.py / render_pages.py / combine_paper.py 匯入。
本身不做事，只提供純函式。

相依：PyMuPDF (fitz)、Pillow (PIL, 選用)
    pip install pymupdf pillow
"""
import re
import base64

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None
try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None


# ── 頁碼處理 ──────────────────────────────────────────────────

def book_page(pdf_index, offset):
    """PDF 0-indexed page → 書本印刷頁碼。book = pdf_index + offset"""
    return pdf_index + offset


# ── 掃描檔偵測 (A / B / C) ────────────────────────────────────

def text_coverage(page):
    """該頁文字 block 覆蓋的面積比例 (0.0–1.0)。掃描檔幾乎為 0。"""
    area = page.rect.width * page.rect.height
    if area <= 0:
        return 0.0
    covered = 0.0
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        x0, y0, x1, y1 = b["bbox"]
        covered += max(0, x1 - x0) * max(0, y1 - y0)
    return covered / area


def has_fullpage_image(page, frac=0.55):
    """頁面是否含近乎滿版的影像（掃描頁的特徵）。"""
    area = page.rect.width * page.rect.height
    for img in page.get_images(full=True):
        try:
            for r in page.get_image_rects(img[0]):
                if r.width * r.height > frac * area:
                    return True
        except Exception:
            continue
    return False


def classify_pdf(doc, sample=10):
    """
    判斷 PDF 屬於哪一類，回傳 ('A'|'B'|'C', 診斷字串)。
      A 原生電子檔      ：有正常文字層
      B 已 OCR 的掃描檔 ：滿版影像 + 有文字層（常有辨識錯字）
      C 無文字層掃描檔  ：幾乎沒有可取文字
    heuristic，務必用 inspect_pdf.py 覆核。
    """
    n = len(doc)
    if n == 0:
        return "C", "empty pdf"
    step = max(1, n // sample)
    idxs = list(range(0, n, step))[:sample]
    covs, textpages, imgpages = [], 0, 0
    for i in idxs:
        p = doc[i]
        c = text_coverage(p)
        covs.append(c)
        if c > 0.008:
            textpages += 1
        if has_fullpage_image(p):
            imgpages += 1
    avg = sum(covs) / len(covs)
    diag = (f"sampled {len(idxs)} pages: avg text-coverage={avg:.3f}, "
            f"text pages={textpages}/{len(idxs)}, fullpage-image pages={imgpages}/{len(idxs)}")
    if avg < 0.012 and textpages <= len(idxs) // 3:
        return "C", diag
    if imgpages >= len(idxs) // 2 and textpages >= 1:
        return "B", diag
    return "A", diag


# ── 欄位偵測與閱讀順序 ────────────────────────────────────────

def text_blocks(page):
    """該頁所有文字 block（type==0）。"""
    return [b for b in page.get_text("dict")["blocks"] if b["type"] == 0]


def block_text(b):
    """把一個 block 的所有 span 併成純文字（保留換行）。"""
    lines = []
    for line in b.get("lines", []):
        lines.append("".join(s["text"] for s in line["spans"]))
    return "\n".join(lines)


def detect_columns(page, wide_frac=0.7):
    """
    回傳 1 或 2。以文字 block 水平中心分布判斷是否雙欄。
    滿寬 block（標題、跨欄表格）不列入計算。
    """
    W = page.rect.width
    mid = W / 2
    left = right = 0
    for b in text_blocks(page):
        x0, y0, x1, y1 = b["bbox"]
        if (x1 - x0) > wide_frac * W:
            continue
        c = (x0 + x1) / 2
        if c < mid:
            left += 1
        else:
            right += 1
    if left >= 3 and right >= 3 and min(left, right) >= 0.5 * max(left, right):
        return 2
    return 1


def column_bounds(page, ncols):
    """回傳每欄的 (x0, x1) 水平界線清單，長度 = ncols。"""
    W = page.rect.width
    blocks = text_blocks(page)
    if ncols == 2:
        mid = W / 2
        L = [b for b in blocks if (b["bbox"][0] + b["bbox"][2]) / 2 < mid]
        R = [b for b in blocks if (b["bbox"][0] + b["bbox"][2]) / 2 >= mid]

        def bounds(bs, dflt):
            if not bs:
                return dflt
            return (min(b["bbox"][0] for b in bs), max(b["bbox"][2] for b in bs))
        return [bounds(L, (0, mid)), bounds(R, (mid, W))]
    if not blocks:
        return [(0, W)]
    return [(min(b["bbox"][0] for b in blocks), max(b["bbox"][2] for b in blocks))]


def which_column(x, bounds):
    """點 x 落在哪一欄，回傳欄 index（找不到回 0）。"""
    for i, (x0, x1) in enumerate(bounds):
        if x0 - 2 <= x <= x1 + 2:
            return i
    # 退而求其次：找中心最近的欄
    return min(range(len(bounds)),
               key=lambda i: abs(x - (bounds[i][0] + bounds[i][1]) / 2))


def reading_order_blocks(page, ncols=None):
    """依欄位還原正確閱讀順序（左欄由上到下，再右欄）。回傳 block 清單。"""
    if ncols is None:
        ncols = detect_columns(page)
    blocks = text_blocks(page)
    if ncols == 2:
        mid = page.rect.width / 2
        left = sorted([b for b in blocks if (b["bbox"][0] + b["bbox"][2]) / 2 < mid],
                      key=lambda b: b["bbox"][1])
        right = sorted([b for b in blocks if (b["bbox"][0] + b["bbox"][2]) / 2 >= mid],
                       key=lambda b: b["bbox"][1])
        return left + right
    return sorted(blocks, key=lambda b: b["bbox"][1])


def reading_order_text(page, ncols=None):
    """整頁的正確閱讀順序純文字。"""
    return "\n\n".join(block_text(b) for b in reading_order_blocks(page, ncols)).strip()


# ── 影像渲染 ──────────────────────────────────────────────────

def render_clip_b64(page, rect, zoom=3.0, fmt="png", jpg_quality=82):
    """把頁面某矩形區域渲染成 base64 data URI（png 清晰 / jpeg 省空間）。"""
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, clip=rect, alpha=False)
    if fmt == "jpeg":
        data = pix.tobytes("jpeg", jpg_quality=jpg_quality)
        return "data:image/jpeg;base64," + base64.b64encode(data).decode()
    data = pix.tobytes("png")
    return "data:image/png;base64," + base64.b64encode(data).decode()


def render_page_b64(page, zoom=2.2, fmt="jpeg", jpg_quality=80):
    """整頁渲染（掃描檔原文視圖 / C 類直譯用）。"""
    return render_clip_b64(page, page.rect, zoom=zoom, fmt=fmt, jpg_quality=jpg_quality)


# ── HTML 解析 ─────────────────────────────────────────────────

def extract_sections(html):
    """抽出所有 <section class="sec">…</section>（非貪婪，可跨行）。"""
    return re.findall(r'<section[^>]*class="sec"[^>]*>.*?</section>', html, re.DOTALL)


def extract_css(html):
    """抽出第一個 <style> 區塊內容。"""
    m = re.search(r'<style[^>]*>(.*?)</style>', html, re.DOTALL)
    return m.group(1) if m else ""


def extract_title(html):
    """抽出第一個 <h1> 的純文字（去 tag、去 .en 附標）。"""
    m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
    if not m:
        return ""
    inner = re.sub(r'<span class="en">.*?</span>', '', m.group(1), flags=re.DOTALL)
    return re.sub(r'<[^>]+>', '', inner).strip()


# ── 標籤正規化（figure / table / equation） ─────────────────

CAPTION_RE = re.compile(
    r'^\s*(fig(?:ure|\.)?|table|圖|表)\s*\.?\s*(\d+(?:\.\d+)?)', re.I)
EQNUM_RE = re.compile(r'^\(\s*(\d+(?:[.\-]\d+)?)\s*\)\s*$')


def caption_kind_label(text):
    """判斷一段文字是否為圖/表標題，回傳 (kind, label) 或 (None, None)。
    kind ∈ {'figure','table'}；label 如 'Figure 3' / 'Table 1'。"""
    m = CAPTION_RE.match(text)
    if not m:
        return None, None
    word, num = m.group(1).lower(), m.group(2)
    kind = "table" if word in ("table", "表") else "figure"
    label = f"{'Table' if kind == 'table' else 'Figure'} {num}"
    return kind, label
