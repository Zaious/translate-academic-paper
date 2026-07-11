"""
export_txt.py — Phase 5（保底）：零依賴純文字對照輸出

不需要任何第三方套件（只用標準庫），裝不了 python-docx 時的保底輸出。
讀 build/sec*.html（與 export_docx.py 同一來源），輸出純文字。

用法：
    python export_txt.py --build build --out "out/成品_對照.txt" --view both
    # --view zh   純中文
    # --view orig 純原文
    # --view both 中英對照（預設）
"""
import argparse
import pathlib
import re


def strip_tags(html):
    html = re.sub(r'<br\s*/?>', '\n', html)
    html = re.sub(r'<span class="en">(.*?)</span>', r'（\1）', html, flags=re.DOTALL)
    html = re.sub(r'<[^>]+>', '', html)
    html = html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r'[ \t]+', ' ', html).strip()


TOKEN_RE = re.compile(
    r'<h([123])[^>]*>(.*?)</h\1>'
    r'|<div class="pgmark">(.*?)</div>'
    r'|<div class="(para[^"]*)">(.*?)</div>\s*</div>',
    re.DOTALL)
ZH_RE = re.compile(r'<div class="zh">(.*?)</div>', re.DOTALL)
ORIG_RE = re.compile(r'<div class="orig">(.*?)$', re.DOTALL)


def section_lines(sec_html, view):
    lines = []
    for m in TOKEN_RE.finditer(sec_html):
        if m.group(1):                                   # heading
            lines += ["", "=" * 8 + " " + strip_tags(m.group(2)) + " " + "=" * 8, ""]
        elif m.group(3) is not None:                     # pgmark
            lines.append("―― " + strip_tags(m.group(3)) + " ――")
        else:                                            # para
            inner = m.group(5)
            zh_m, orig_m = ZH_RE.search(inner), ORIG_RE.search(inner)
            zh = strip_tags(zh_m.group(1)) if zh_m else ""
            orig = strip_tags(orig_m.group(1)) if orig_m else ""
            if view == "zh" and zh:
                lines += [zh, ""]
            elif view == "orig" and orig:
                lines += [orig, ""]
            elif view == "both":
                if zh:
                    lines.append("【中】" + zh)
                if orig:
                    lines.append("【原】" + orig)
                lines.append("")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="build")
    ap.add_argument("--out", required=True)
    ap.add_argument("--view", choices=["zh", "orig", "both"], default="both")
    args = ap.parse_args()

    build = pathlib.Path(args.build)
    sec_files = sorted(build.glob("sec*.html"))
    if not sec_files:
        raise SystemExit(f"no sec*.html found in {build}")

    out_lines = []
    meta = build / "meta.html"
    if meta.exists():
        out_lines += [strip_tags(meta.read_text(encoding="utf-8")), "", "=" * 40, ""]

    for f in sec_files:
        html = f.read_text(encoding="utf-8")
        m = re.search(r'<section[^>]*class="sec"[^>]*>(.*?)</section>', html, re.DOTALL)
        out_lines += section_lines(m.group(1) if m else html, args.view)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(out_lines).strip() + "\n", encoding="utf-8")
    print(f"Wrote {out}  ({len(sec_files)} sections, view={args.view})")


if __name__ == "__main__":
    main()
