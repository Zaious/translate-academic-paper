"""
check_fidelity.py — 半自動忠實度檢查（縮小人工抽查範圍，不取代人工對圖）

check_translation.py / check_units.py 保「結構完整」，本腳本補「內容忠實」的
**客觀可查部分**——逐段比對 zh vs orig，圈出留有客觀痕跡的疑似幻覺：

  1. 數字/年份掉落：orig 的「該保留數值」（年份、≥3 位數、含小數/統計量如 0.05）
     未出現在 zh —— 可能漏掉整句、或譯錯數字。反向（zh 多出 orig 沒有的數值）
     則疑似捏造。（zh 以國字書寫數字屬正常，本腳本會降級提示。）
  2. 引用標記掉落：orig 的 [12] / (Smith, 2020) 未原樣出現在 zh —— skill 規定
     引用標記一律原樣保留，缺失代表漏譯或改寫。
  3. 長度比離群：以「本章所有段落 zh/orig 字元比的中位數」為基線，某段偏離
     過大（預設 <0.5× 或 >2× 中位數）—— 過短疑漏譯、過長疑加譯/贅述。
     自適應中位數，避免不同語言對/文本的基線差異造成整片假警報。

**定位不是定罪**：全部是 WARN 性質——機器先幫你圈可疑段落，判對錯仍靠人眼對圖。
真正的語意錯譯（數字對、引用在、長度正常，但意思翻反了）本腳本抓不到，
runbook「每章人工抽查 2–3 段對圖」仍不可省。

吃兩種輸入（自動辨識副檔名）：
  - units JSON（B2 流程，最早可驗）：python check_fidelity.py sec02_batch01.units.json
  - secNN.html（轉檔後）：            python check_fidelity.py build/sec02.html

  --strict     把 WARN 升為 FAIL（exit 1），CI 用
  --ratio-lo / --ratio-hi   長度比離群倍數（預設 0.5 / 2.0，相對中位數）

退出碼：預設一律 0（純提示，不擋流程）；--strict 時有疑慮回 1。
"""
import argparse
import json
import re
import sys
from statistics import median
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check_translation import scan_section, strip_tags, first_div
from paper_utils import extract_sections

# ── 數值抽取 ──────────────────────────────────────────────
NUM_RE = re.compile(r'\d[\d,]*\.?\d*')
CJK_NUM = set("一二三四五六七八九十百千萬万兩两零壹貳參肆伍陸柒捌玖拾佰仟")


def norm_num(s):
    return s.replace(",", "").rstrip(".")


def sig_numbers(text):
    """回傳『該原樣保留』的數值集合：年份、≥3 位整數、含小數（統計量）。
    刻意排除 1–2 位小數字——最常被合法寫成國字（如 one-half→一半）。"""
    out = set()
    for m in NUM_RE.finditer(text):
        n = norm_num(m.group())
        if not n:
            continue
        digits = n.replace(".", "")
        if len(digits) >= 3 or "." in n:
            out.add(n)
    return out


# ── 引用標記抽取 ──────────────────────────────────────────
CITE_RE = re.compile(
    r'\[\d+(?:\s*[-,]\s*\d+)*\]'                       # [12] [1,2] [1-3]
    r'|\((?:[A-Z][A-Za-z.\'-]+(?:\s+(?:et\s+al\.?|&|and)\s+[A-Z][A-Za-z.\'-]+)*'
    r'(?:\s+et\s+al\.?)?,\s*)?\d{4}[a-z]?\)')          # (Smith, 2020) (2020) (Smith & Lee, 2020a)


def citations(text):
    return set(m.group().replace(" ", "") for m in CITE_RE.finditer(text))


# ── 逐段檢查 ──────────────────────────────────────────────
def check_para(label, zh, orig, warns):
    o_nums, z_nums = sig_numbers(orig), sig_numbers(zh)
    missing = o_nums - z_nums
    if missing:
        has_cjk_num = any(c in CJK_NUM for c in zh)
        hint = "（zh 含國字數字，可能以國字書寫，請人工確認）" if has_cjk_num else ""
        warns.append((label, "num_drop",
                      f"orig 數值未見於 zh：{sorted(missing)}{hint}"))
    extra = z_nums - o_nums
    if extra:
        warns.append((label, "num_add",
                      f"zh 出現 orig 沒有的數值（疑似捏造）：{sorted(extra)}"))

    o_cites = citations(orig)
    missing_c = o_cites - citations(zh)
    if missing_c:
        warns.append((label, "cite_drop",
                      f"引用標記未原樣保留於 zh：{sorted(missing_c)}"))


def check_length_ratios(items, lo_mult, hi_mult, warns):
    """items: [(label, zh, orig)]，用中位數自適應找離群長度比。"""
    ratios = []
    for label, zh, orig in items:
        lo, lz = len(orig.strip()), len(zh.strip())
        if lo >= 40:                       # 太短的段落（標題/單句）不納入基線
            ratios.append((label, lz / lo, lz, lo))
    if len(ratios) < 4:                    # 樣本太少，中位數不可靠，跳過
        return
    med = median(r for _, r, _, _ in ratios)
    for label, r, lz, lo in ratios:
        if r < lo_mult * med:
            warns.append((label, "len_short",
                          f"zh/orig 長度比 {r:.2f} 遠低於本章中位數 {med:.2f}"
                          f"（{lz}/{lo} 字元）——疑似漏譯"))
        elif r > hi_mult * med:
            warns.append((label, "len_long",
                          f"zh/orig 長度比 {r:.2f} 遠高於本章中位數 {med:.2f}"
                          f"（{lz}/{lo} 字元）——疑似加譯/贅述"))


# ── 輸入載入 ──────────────────────────────────────────────
def load_units(path):
    d = json.load(open(path, encoding="utf-8"))
    items = []
    for u in d.get("units", []):
        if u.get("type") not in (None, "paragraph", "footnote", "epigraph", "caption"):
            continue
        orig, zh = (u.get("orig") or "").strip(), (u.get("zh") or "").strip()
        if orig and zh:
            items.append((u.get("id", "<no-id>"), zh, orig))
    return d.get("section_id", Path(path).stem), items


def load_html(path):
    html = open(path, encoding="utf-8").read()
    secs = extract_sections(html) or [html]
    results = []
    for si, sec in enumerate(secs):
        m = re.search(r'id="([^"]+)"', sec)
        sid = m.group(1) if m else f"sec{si+1}"
        items, pg, idx = [], "?", 0
        for ev in scan_section(sec):
            if ev[0] == "page":
                pg = ev[1]
            elif ev[0] == "para":
                idx += 1
                zh = strip_tags(ev[1]) if ev[1] else ""
                orig = strip_tags(ev[2]) if ev[2] else ""
                if zh and orig:
                    items.append((f"{sid} p.{pg} #{idx}", zh, orig))
        results.append((sid, items))
    return results


# ── 主程序 ────────────────────────────────────────────────
def run_one(sid, items, args, all_warns):
    warns = []
    for label, zh, orig in items:
        check_para(label, zh, orig, warns)
    check_length_ratios(items, args.ratio_lo, args.ratio_hi, warns)

    print("=" * 68)
    print(f"§ {sid}   段落數 {len(items)}")
    if not warns:
        print("  ✅ 未發現忠實度疑點（數值/引用/長度比皆正常）")
    for label, kind, msg in warns:
        print(f"  ⚠️  [{kind}] {label}")
        print(f"        {msg}")
    all_warns.extend(warns)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="units .json 或 sec*.html")
    ap.add_argument("--strict", action="store_true", help="WARN 升為 FAIL（exit 1）")
    ap.add_argument("--ratio-lo", type=float, default=0.5, help="長度比下界（×中位數）")
    ap.add_argument("--ratio-hi", type=float, default=2.0, help="長度比上界（×中位數）")
    args = ap.parse_args()

    all_warns = []
    for path in args.inputs:
        if path.lower().endswith(".json"):
            sid, items = load_units(path)
            run_one(sid, items, args, all_warns)
        else:
            for sid, items in load_html(path):
                run_one(sid, items, args, all_warns)

    print("=" * 68)
    n = len(all_warns)
    if n == 0:
        print("✅ 無忠實度疑點。")
    else:
        by = {}
        for _, k, _ in all_warns:
            by[k] = by.get(k, 0) + 1
        summary = "、".join(f"{k}×{v}" for k, v in sorted(by.items()))
        print(f"⚠️  共 {n} 個疑點（{summary}）——請人工對圖複核這些段落。")
    print("提醒：本檢查只圈客觀痕跡；語意錯譯仍須人工抽查對圖（runbook）。")
    sys.exit(1 if (all_warns and args.strict) else 0)


if __name__ == "__main__":
    main()
