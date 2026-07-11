"""
check_translation.py — 譯稿品質關卡（每章翻完後跑一次，不合格打回重譯）

用真本書《Spencer, Education》驗過的六個實際病灶都在查：
  1. 抽稿／濃縮：段落數相對頁數過低（原本 60 頁的章節只給 9 段，就是這樣被抓到的）
  2. 缺原文對照：.para 裡有 .zh 卻沒有 .orig（或 .orig 是空的）
  3. 頁碼跳號／缺頁／逆行：<div class="pgmark"> 應逐頁連續，不可跳號
  4. 頁界腰斬句子：某段 .orig 結尾非終止標點、下一段開頭卻是小寫字母，代表同一句
     被硬切成兩個 .para——這是「逐頁批次翻譯」（每頁一個 API 呼叫，段落單位錯用
     成頁面單位）的典型症狀，實測真書抓到近半數段落中招，比抽稿更隱蔽也更常見。
  5. 英文連接詞洩漏：中文譯文裡混進未翻譯的 " and "/" the "/" of " 等——實測抓到
     過「大學 and 學校」這種殘留，通常是批次翻譯漏翻某個子句造成的。
  6. 簡體字混入：預設用精選高信心字表（只收絕對是簡體字、無異體字爭議的字），
     零假警報但涵蓋不到罕見簡體字。想要更廣的偵測可加 --use-opencc，改用
     OpenCC 逐字元比對（涵蓋更廣，但依上下文詞頻可能誤判合法異體字/專有名詞
     為簡體字，如 布/佈、系/係、面/靣、干/幹、夸/誇——出現時請人工判斷）。

可以直接吃單一 build/secNN.html，或吃合併後的整份 out/*.html（會自動按
<section class="sec"> 逐章分開報告）。

用法：
    python scripts/check_translation.py build/sec02.html
    python scripts/check_translation.py build/sec*.html
    python scripts/check_translation.py "out/整合版.html"
    python scripts/check_translation.py build/sec02.html --min-page 93 --max-page 167
    python scripts/check_translation.py build/sec02.html --use-opencc   # 更廣但較吵

    # 想更嚴格（簡體字/中度病灶也視為失敗、CI 用）：
    python scripts/check_translation.py build/sec02.html --strict

退出碼：有 ❌ FAIL 則回傳 1（可用於腳本串接，卡住不合格章節）。
相依：opencc-python-reimplemented（選用，只有加 --use-opencc 才需要）
    pip install opencc-python-reimplemented
"""
import argparse
import re
import sys
from html import unescape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paper_utils import extract_sections

# 精選高信心簡體字表（預設偵測法）：每個字都經 OpenCC s2tw 單字（非整段文字）
# 測試驗證「確實會被轉換」才收錄，非憑印象手打——手打曾誤收 你/假/化/呼/婚
# 等繁簡通用字，已用此方法抓出並移除。同時刻意排除 台/里/只/布/系/面/念/干/
# 污/注/夸/托/背/克/局/岩/戚/爲/游/占/制/了/群 等：這些字在繁體中文裡本身
# 合法（度量衡音譯字、專有名詞、或常見異體字），單字測試雖可能通過，但在真實
# 語句中易被上下文詞語切分誤導，寧可漏抓也不要洗版假警報
# （更廣的覆蓋見 --use-opencc，但那是較低信心、需人工複核的模式）。
CURATED_SIMP_CHARS = set(
    "万与东丝两严丧个为丽举义乐习乡书买乱争亏产亲们优会伟传伤伪侧侨债偿"
    "关兴农务动劳区医华却双变国场坏块处备复够奋奖妈娱孙学宁实宾对寻"
    "导寿将尔尝尽层属岁币师带帮并广库应开异弃张弥弯归当录彻总恋恶战护"
    "报担拟择挂挤换据摆敌数断无旧时术机杀条来杨极构汇现电确称见视觉"
    "认让该语说达这长门问题风"
)

PLACEHOLDER_MARKERS = ("TODO", "TBD", "[待譯]", "(untranslated)", "待翻譯", "尚未翻譯")

BLOCK_RE = re.compile(
    r'<div class="pgmark"[^>]*>(?P<pg>.*?)</div>'
    r'|<div class="para"[^>]*>(?P<para>.*?)'
    r'(?=<div class="para"|<div class="pgmark"|<h1|<h2|<h3|<figure|<div class="poem"|</section>|\Z)'
    r'|(?P<other><figure[^>]*>|<div class="poem"[^>]*>|<h1|<h2|<h3)',
    re.DOTALL)

# 段落被「頁界」腰斬的判定：.orig 結尾不是終止標點，且緊接著的下一段 .orig
# 開頭是小寫字母 —— 這是英文句子被硬生生切成兩截最可靠的訊號（合法的非終止結尾，
# 如引言前的冒號 "...old song:—"，下一段開頭一定是大寫或引號，不會被誤判）。
_TERM_PUNCT = ('.', '?', '!', '"', '”', '’', '」', '』', ':', ';', ')', '）')


def _ends_midsentence(orig_text):
    t = orig_text.rstrip()
    return bool(t) and not t.endswith(_TERM_PUNCT)


def _starts_lowercase(orig_text):
    m = re.search(r'[A-Za-z]', orig_text.lstrip())
    return bool(m) and m.group().islower()


def strip_tags(html):
    html = re.sub(r'<[^>]+>', '', html)
    return unescape(html).strip()


def first_div(html, cls):
    m = re.search(r'<div class="%s"[^>]*>(.*?)</div>' % cls, html, re.DOTALL)
    return m.group(1) if m else None


def scan_section(sec_html):
    """回傳 events：[('page', n), ('para', zh_raw, orig_raw_or_None), ('other', None), ...]
    依文件順序。'other' 標記詩歌/圖/標題等非 para 內容的出現位置，供「頁界腰斬句子」
    判定用來確認兩個 para 是否真的緊鄰（中間沒有隔著詩歌或圖表）。"""
    events = []
    for m in BLOCK_RE.finditer(sec_html):
        if m.group('pg') is not None:
            # 支援頁碼範圍標記「p.89–92」：範圍內每一頁都展開為 page 事件
            # （B2 units 轉出的跨頁段落會產生 p.177–179 這類三頁以上範圍，
            #   只發起訖兩點會被誤判成中間跳號）。
            nums = [int(n) for n in re.findall(r'\d+', m.group('pg'))]
            if len(nums) == 2 and nums[0] < nums[1] <= nums[0] + 50:
                for n in range(nums[0], nums[1] + 1):
                    events.append(('page', n))
            else:
                for n in nums:
                    events.append(('page', n))
        elif m.group('para') is not None:
            body = m.group('para')
            zh = first_div(body, 'zh')
            orig = first_div(body, 'orig')
            if zh is not None:
                events.append(('para', zh, orig))
        elif m.group('other') is not None:
            events.append(('other', None))
    return events


def check_pages(events, min_page=None, max_page=None):
    """回傳 (marks, issues) — issues 為 (level, msg) 清單。"""
    marks = [e[1] for e in events if e[0] == 'page']
    issues = []
    if not marks:
        issues.append(('FAIL', '完全沒有 <div class="pgmark"> 頁碼標記，無法核對頁數涵蓋範圍'))
        return marks, issues
    prev = None
    for n in marks:
        if prev is not None:
            if n < prev:
                issues.append(('FAIL', f'頁碼逆行：p.{prev} 之後出現 p.{n}'))
            elif n - prev > 1:
                issues.append(('WARN', f'頁碼跳號：p.{prev} → p.{n}（缺 p.{prev+1}–{n-1}）'))
        prev = n
    if min_page is not None and marks[0] > min_page:
        issues.append(('WARN', f'起始頁 p.{marks[0]} 晚於預期 p.{min_page}，開頭可能缺頁'))
    if max_page is not None and marks[-1] < max_page:
        issues.append(('FAIL', f'結束頁 p.{marks[-1]} 早於預期 p.{max_page}，疑似未譯完或漏頁'))
    return marks, issues


def check_density(para_count, marks, warn_ratio, fail_ratio, min_abs_paras):
    if not marks:
        return []
    pages = max(marks) - min(marks) + 1
    ratio = para_count / pages if pages else 0
    issues = []
    msg = f'段落密度 {para_count} 段 / {pages} 頁 = {ratio:.2f} 段/頁'
    if ratio < fail_ratio or (pages > 15 and para_count < min_abs_paras):
        issues.append(('FAIL', f'{msg} —— 遠低於門檻，高度疑似抽稿／濃縮摘要，非逐段全譯'))
    elif ratio < warn_ratio:
        issues.append(('WARN', f'{msg} —— 偏低，請人工抽查是否有整段跳過'))
    return issues


def check_orig_coverage(paras, fail_pct):
    total = len(paras)
    missing = [(zh, orig) for zh, orig in paras if not orig or not strip_tags(orig)]
    if not missing:
        return [], []
    pct = 100 * len(missing) / total if total else 0
    level = 'FAIL' if pct > fail_pct else 'WARN'
    issue = (level, f'缺原文對照：{len(missing)}/{total} 段（{pct:.0f}%）沒有 .orig 或內容為空')
    samples = [strip_tags(zh)[:40] for zh, _ in missing[:5]]
    return [issue], samples


def check_placeholders(paras):
    issues = []
    for zh, orig in paras:
        zh_txt = strip_tags(zh)
        for marker in PLACEHOLDER_MARKERS:
            if marker in zh_txt:
                issues.append(('FAIL', f'發現未譯占位字串「{marker}」：{zh_txt[:40]}…'))
    return issues


# 英文連接詞/介系詞直接洩漏進中文譯文（未翻譯就原樣留著），實測真書抓到過
# "大學 and 學校"這種殘留。<span class="en">術語附註</span>是合法用法，比對前先剔除。
_LEAK_WORDS = (' and ', ' the ', ' of ', ' or ', ' with ', ' which ', ' that ')


def check_leaked_english(paras):
    issues, examples = [], []
    n = 0
    for zh, orig in paras:
        zh_no_en = re.sub(r'<span class="en">.*?</span>', '', zh, flags=re.DOTALL)
        zh_txt = strip_tags(zh_no_en)
        for w in _LEAK_WORDS:
            for m in re.finditer(re.escape(w), zh_txt):
                n += 1
                if len(examples) < 8:
                    i = m.start()
                    examples.append(f'…{zh_txt[max(0,i-12):i+12]}…')
    if n:
        issues.append(('FAIL', f'偵測到 {n} 處英文連接詞/介系詞直接洩漏進中文譯文（未翻譯就原樣留著）'))
    return issues, examples


def _find_examples(all_zh, chars_found, cap=15):
    examples = []
    for ch in sorted(chars_found)[:cap]:
        idx = all_zh.find(ch)
        ctx = all_zh[max(0, idx - 8):idx + 9].replace("\n", " ")
        examples.append(f'「{ch}」→ …{ctx}…')
    return examples


def check_simplified(paras, use_opencc=False):
    """預設：精選字表，零已知假警報但覆蓋較窄。
    --use-opencc：額外用 OpenCC s2tw 逐字元比對，覆蓋更廣，但依上下文詞頻
    可能把合法異體字／專有名詞音譯字（如 布/佈、系/係、干/幹、夸/誇）
    也判成簡體字——這部分結果會標成「較低信心」，請人工判斷。"""
    all_zh = "\n".join(strip_tags(zh) for zh, _ in paras)
    if not all_zh.strip():
        return [], []

    issues, examples = [], []
    curated_found = {c for c in all_zh if c in CURATED_SIMP_CHARS}
    if curated_found:
        issues.append(('WARN', f'偵測到 {len(curated_found)} 個高信心簡體字：'
                                f'{"".join(sorted(curated_found))}'))
        examples += _find_examples(all_zh, curated_found)

    if use_opencc:
        try:
            from opencc import OpenCC
        except ImportError:
            issues.append(('WARN', '--use-opencc 已指定但未安裝 opencc-python-reimplemented，略過此項'))
            return issues, examples
        cc = OpenCC('s2tw')  # 字元級、台灣標準；勿用 s2t，會把 群/台/裡 等合法字誤轉成罕用異體字
        # 已知即使 s2tw 也會誤轉的「風格差異」字對，不視為簡體字
        skip_pairs = {('台', '臺'), ('里', '裡'), ('只', '隻')}
        converted = cc.convert(all_zh)
        if len(converted) == len(all_zh):
            diffs = {a for a, b in zip(all_zh, converted)
                     if a != b and (a, b) not in skip_pairs and a not in curated_found}
            if diffs:
                issues.append(('WARN', f'OpenCC 額外抓到 {len(diffs)} 個字元差異（較低信心，'
                                        f'常見假警報如專有名詞音譯字/合法異體字，請人工判斷）：'
                                        f'{"".join(sorted(diffs))}'))
                examples += _find_examples(all_zh, diffs)
    return issues, examples


def check_pagesplit(events, fail_frac=0.05):
    """偵測段落被「頁界」腰斬：某段 .orig 結尾非終止標點，且緊鄰（中間沒有隔詩歌/圖/
    標題）的下一段 .orig 開頭是小寫字母——這是英文句子被硬生生切成兩個 .para 最可靠的
    訊號（合法的非終止結尾，如引言前的「...old song:—」，下一段一定是大寫/引號開頭，
    不會被這個組合條件誤判）。真實案例：逐頁批次翻譯會把每一頁包成一個 .para，句子
    跨頁就被腰斬——這是本檢查存在的直接原因。"""
    para_events = [(i, e) for i, e in enumerate(events) if e[0] == 'para']
    cut_pairs = []
    for k in range(len(para_events) - 1):
        i, cur = para_events[k]
        j, nxt = para_events[k + 1]
        if any(events[x][0] == 'other' for x in range(i + 1, j)):
            continue  # 中間隔著詩歌/圖/標題，不是真的緊鄰段落
        cur_orig = strip_tags(cur[2]) if cur[2] else ''
        nxt_orig = strip_tags(nxt[2]) if nxt[2] else ''
        if cur_orig and nxt_orig and _ends_midsentence(cur_orig) and _starts_lowercase(nxt_orig):
            cut_pairs.append((cur_orig[-50:], nxt_orig[:50]))

    total = len(para_events)
    if not cut_pairs or not total:
        return [], []
    frac = len(cut_pairs) / total
    level = 'FAIL' if frac > fail_frac else 'WARN'
    issue = (level, f'疑似段落被頁界腰斬（同一句被硬切成兩個 .para）：'
                     f'{len(cut_pairs)}/{total} 處交界（{frac*100:.0f}%）——'
                     f'常見於逐頁批次翻譯，違反「翻譯單位是段落不是頁」的硬規則')
    examples = [f'…{a} ‖ {b}…' for a, b in cut_pairs[:6]]
    return [issue], examples


def report_section(sec_id, sec_html, args):
    events = scan_section(sec_html)
    paras = [(e[1], e[2]) for e in events if e[0] == 'para']
    marks, page_issues = check_pages(events, args.min_page, args.max_page)

    all_issues = list(page_issues)
    density_issues = check_density(len(paras), marks, args.warn_ratio, args.fail_ratio, args.min_paras)
    all_issues += density_issues
    orig_issues, orig_samples = check_orig_coverage(paras, args.orig_fail_pct)
    all_issues += orig_issues
    all_issues += check_placeholders(paras)
    split_issues, split_examples = check_pagesplit(events)
    all_issues += split_issues
    leak_issues, leak_examples = check_leaked_english(paras)
    all_issues += leak_issues
    simp_issues, simp_examples = check_simplified(paras, use_opencc=args.use_opencc)
    if args.strict:
        simp_issues = [('FAIL', m) if lvl == 'WARN' else (lvl, m) for lvl, m in simp_issues]
    all_issues += simp_issues

    print(f"\n{'='*72}\n{sec_id}\n{'='*72}")
    print(f"  段落數：{len(paras)}   頁碼範圍：p.{min(marks) if marks else '?'}"
          f"–{max(marks) if marks else '?'}（{len(marks)} 個標記）")

    if not all_issues:
        print("  ✅ 未發現問題")
        return True

    for level, msg in all_issues:
        icon = "❌" if level == "FAIL" else "⚠️ "
        print(f"  {icon} [{level}] {msg}")
    if orig_samples:
        print("  缺原文的段落樣本：")
        for s in orig_samples:
            print(f"    · {s}…")
    if split_examples:
        print("  頁界腰斬句子樣本（‖ 標記兩個 .para 的交界）：")
        for s in split_examples:
            print(f"    · {s}")
    if leak_examples:
        print("  英文連接詞洩漏樣本：")
        for s in leak_examples:
            print(f"    · {s}")
    if simp_examples:
        print("  簡體字出現位置樣本：")
        for s in simp_examples:
            print(f"    · {s}")

    has_fail = any(lvl == "FAIL" for lvl, _ in all_issues)
    print(f"  {'❌ 本章判定：不合格，須修正後重驗' if has_fail else '⚠️  本章判定：有疑慮，建議人工複核'}")
    return not has_fail


def main():
    ap = argparse.ArgumentParser(description="譯稿品質關卡：抽稿/缺原文/跳頁/頁界腰斬句子/簡體字")
    ap.add_argument("files", nargs="+", help="build/secNN.html 或合併後的 out/*.html（可多檔/萬用字元）")
    ap.add_argument("--min-page", type=int, help="預期起始書頁（不足視為缺頭）")
    ap.add_argument("--max-page", type=int, help="預期結束書頁（不足視為缺尾/未譯完）")
    ap.add_argument("--warn-ratio", type=float, default=0.35, help="段/頁 低於此值 WARN（預設 0.35）")
    ap.add_argument("--fail-ratio", type=float, default=0.15, help="段/頁 低於此值 FAIL（預設 0.15）")
    ap.add_argument("--min-paras", type=int, default=15, help="章節跨頁>15頁時，段落數低於此絕對值直接 FAIL")
    ap.add_argument("--orig-fail-pct", type=float, default=15.0, help="缺原文比例超過此百分比 FAIL（預設 15）")
    ap.add_argument("--strict", action="store_true", help="簡體字等預設 WARN 的項目一併視為 FAIL")
    ap.add_argument("--use-opencc", action="store_true",
                    help="簡體字偵測額外加 OpenCC 逐字元比對（覆蓋更廣但較吵，需 pip install opencc-python-reimplemented）")
    args = ap.parse_args()

    all_ok = True
    n_sections = 0
    for fp in args.files:
        p = Path(fp)
        if not p.exists():
            print(f"⚠ 找不到檔案：{fp}")
            all_ok = False
            continue
        html = p.read_text(encoding="utf-8")
        secs = extract_sections(html)
        if not secs:
            print(f"⚠ {p.name}：沒找到 <section class=\"sec\">，略過")
            continue
        for sec_html in secs:
            idm = re.search(r'id="([^"]+)"', sec_html[:200])
            sec_id = f"{p.name} § {idm.group(1) if idm else '?'}"
            ok = report_section(sec_id, sec_html, args)
            all_ok = all_ok and ok
            n_sections += 1

    print(f"\n{'='*72}")
    print(f"共檢查 {n_sections} 個 section。{'✅ 全數通過' if all_ok else '❌ 有章節未通過，見上方 FAIL 項目'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
