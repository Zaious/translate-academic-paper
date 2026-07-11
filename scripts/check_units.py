"""
check_units.py — Phase 2-B2：translation units 批次 QA（每批必跑）

驗 units JSON 的結構與批次接縫。與 check_translation.py 分工：
本腳本管 units 資料層（批次進行中），check_translation 管最終 HTML（章節完成後）。

用法：
    python check_units.py batch01.units.json                      # 單批結構檢查
    python check_units.py batch01.units.json batch02.units.json   # 依序驗批次接縫
    # exit 0 = 通過；1 = 有 FAIL

檢查項目：
  1. JSON 結構：section_id / units 存在；每 unit 有非空 orig、zh、pages、type 合法
  2. coverage：full_pages 被 units 完整覆蓋；partial_pages 誠實（不在 full 裡）
  3. 頁碼連續：批內 units 頁碼無跳號、無逆行
  4. 批次接縫：後批首頁 ≦ 前批尾頁+1（無縫或重疊，不得跳頁）
  5. 簡體字（複用 check_translation 的核可字表）
  6. OCR 殘渣模式：頁眉殘留、控制字元、常見誤辨形（\\v、EDUOATION 等）
  7. 可疑壓縮：paragraph 平均長度異常短（<200 字元 orig）時警告
"""
import json
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from check_translation import CURATED_SIMP_CHARS

ALLOWED_TYPES = {"paragraph", "footnote", "heading", "epigraph", "caption"}
OCR_GARBAGE = [
    (re.compile(r'\\v|\\n[a-z]'), "反斜線殘渣（\\v 等）"),
    (re.compile(r'\b(EDU[O0]AT|EDUCAT[I1]O[KN]\b(?<!EDUCATION)|KNOWLEDG[I]\s|MOSl|WOllTB|WORTH\')'), "頁眉殘留"),
    (re.compile(r'[·•~§]{2,}|\.{4,}'), "連續雜訊符號"),
    (re.compile(r'\b\w*[0-9]\w*[a-z]{3,}\b(?<!\dth)(?<!\dst)(?<!\dnd)(?<!\drd)'), "數字混入單字"),
    (re.compile(r"[a-z]'[A-Z]|[a-z]{2}\.\.[a-z]"), "OCR 斷字殘形"),
]

fails, warns = [], []


def fail(msg): fails.append(msg)
def warn(msg): warns.append(msg)


def unit_pages(u):
    p = u.get("pages") or ([u["page"]] if "page" in u else [])
    return sorted(p)


def check_batch(path, data):
    name = pathlib.Path(path).name
    if "section_id" not in data:
        fail(f"{name}: 缺 section_id")
    units = data.get("units", [])
    if not units:
        fail(f"{name}: units 為空"); return

    seen_pages = set()
    for u in units:
        uid = u.get("id", "<no-id>")
        if u.get("type") not in ALLOWED_TYPES:
            fail(f"{name}/{uid}: type 不合法：{u.get('type')!r}")
        for field in ("orig", "zh"):
            if not str(u.get(field, "")).strip():
                fail(f"{name}/{uid}: {field} 為空")
        pgs = unit_pages(u)
        if not pgs:
            fail(f"{name}/{uid}: 缺 pages")
        seen_pages.update(pgs)

        zh = u.get("zh", "")
        simp = {c for c in zh if c in CURATED_SIMP_CHARS}
        if simp:
            fail(f"{name}/{uid}: 疑似簡體字：{''.join(sorted(simp))}")
        orig = u.get("orig", "")
        if u.get("type") == "heading":
            continue          # 標題常含全大寫書名/章名，跳過殘渣模式檢查
        for pat, label in OCR_GARBAGE:
            m = pat.search(orig)
            if m:
                warn(f"{name}/{uid}: orig 疑似 OCR 殘渣（{label}）：…{m.group(0)}…")

    # coverage 檢查
    cov = data.get("coverage")
    if isinstance(cov, dict):
        full = set(cov.get("full_pages", []))
        partial = set(cov.get("partial_pages", []))
        if full & partial:
            fail(f"{name}: full_pages 與 partial_pages 重疊：{sorted(full & partial)}")
        missing = full - seen_pages
        if missing:
            fail(f"{name}: full_pages 宣稱覆蓋但無 unit 觸及：{sorted(missing)}")
    elif "coverage_pages" in data:
        warn(f"{name}: 使用舊制扁平 coverage_pages，無法區分完整/部分覆蓋，"
             f"建議改用 coverage.full_pages/partial_pages")

    # 批內頁碼連續
    pages_sorted = sorted(seen_pages)
    for a, b in zip(pages_sorted, pages_sorted[1:]):
        if b - a > 1:
            fail(f"{name}: 批內頁碼跳號 p.{a} → p.{b}")

    # 可疑壓縮
    paras = [u for u in units if u.get("type") == "paragraph"]
    if paras:
        avg = sum(len(u.get("orig", "")) for u in paras) / len(paras)
        n_pages = max(len(seen_pages), 1)
        if len(paras) / n_pages < 0.5:
            warn(f"{name}: 每頁平均段落數 {len(paras)/n_pages:.1f} 偏低，檢查是否漏段/壓縮")
        if avg < 200:
            warn(f"{name}: paragraph orig 平均僅 {avg:.0f} 字元，檢查是否被截斷")
    return seen_pages


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    batches = []
    for f in sys.argv[1:]:
        data = json.load(open(f, encoding="utf-8"))
        pages = check_batch(f, data)
        batches.append((f, data, pages or set()))

    # 批次接縫
    for (f1, d1, p1), (f2, d2, p2) in zip(batches, batches[1:]):
        if not p1 or not p2:
            continue
        tail, head = max(p1), min(p2)
        if head > tail + 1:
            fail(f"批次接縫跳頁：{pathlib.Path(f1).name} 止於 p.{tail}，"
                 f"{pathlib.Path(f2).name} 始於 p.{head}（缺 p.{tail+1}–{head-1}）")
        # 提醒人工驗語意接縫
        warn(f"接縫 p.{tail}↔p.{head}：請人工確認前批尾段與本批首段語意銜接"
             f"（QA 只驗頁碼，不驗內容）")

    print("=" * 60)
    for w in warns:
        print(f"  ⚠️  [WARN] {w}")
    for f in fails:
        print(f"  ❌ [FAIL] {f}")
    if not fails and not warns:
        print("  ✅ 未發現問題")
    print("=" * 60)
    total_units = sum(len(d.get('units', [])) for _, d, _ in batches)
    print(f"共 {len(batches)} 批 / {total_units} units。"
          + ("❌ 有 FAIL，修正後重跑" if fails else "✅ 通過"))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
