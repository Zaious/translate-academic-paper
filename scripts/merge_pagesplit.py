"""
merge_pagesplit.py — 修復「段落被頁界腰斬」的結構缺陷

背景：逐頁批次翻譯（每頁一次 API 呼叫、頁與頁之間無上下文）會把每一頁包成一個
`.para`，導致跨頁的句子被硬切成兩個獨立 `.para`。check_translation.py 的
「頁界腰斬句子」檢查就是抓這個。本腳本做結構修復：

  1. 掃描 secNN.html，找出「.orig 結尾非終止標點 + 緊鄰下一段開頭是小寫字母」的
     相鄰 .para（同一組可能連續好幾段，如 p.74→75→76 同一句切成三截）。
  2. 把整組相鄰段落合併成一個 .para：.zh 與 .orig 分別直接串接（中間補一個空格），
     被吸收掉的中間 pgmark 一併刪除，段落開頭的 pgmark 改成頁碼範圍（如
     "原書 p.74–76"）。

⚠️ 這只修「結構」（把腰斬的句子接回同一個 .para），不修「譯文品質」。合併後的
中文在接縫處通常語意連貫（逐頁翻譯本身品質尚可，只是被結構切散），但**務必用
--dry-run 先看 diff、合併後再人工／AI 抽查接縫處**（重複詞、代名詞不連貫、
語氣斷裂）——這正是 check_translation.py 抓不到、需要人讀的部分。

用法：
    python scripts/merge_pagesplit.py build/sec01.html --dry-run   # 先看會合併哪些
    python scripts/merge_pagesplit.py build/sec01.html             # 就地修改（先備份！）
    python scripts/merge_pagesplit.py build/sec01.html --out build/sec01.merged.html
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paper_utils import extract_sections
import check_translation as ct


def find_para_blocks(sec_html):
    """回傳 [(full_match_text, pgmark_before_or_None, zh_raw, orig_raw), ...] 依序，
    並保留每個 para 在原始字串中的 (start, end) 供之後重組。"""
    blocks = []
    for m in re.finditer(
        r'(?:(?P<pg><div class="pgmark"[^>]*>.*?</div>)\s*)?'
        r'(?P<para><div class="para"[^>]*>.*?)'
        r'(?=<div class="para"|<div class="pgmark"|<h1|<h2|<h3|<figure|<div class="poem"|</section>|\Z)',
        sec_html, re.DOTALL,
    ):
        para_text = m.group('para')
        zh = ct.first_div(para_text, 'zh')
        orig = ct.first_div(para_text, 'orig')
        if zh is None:
            continue
        blocks.append({
            'start': m.start(), 'end': m.end(),
            'pg_text': m.group('pg'),
            'zh': zh, 'orig': orig,
        })
    return blocks


def group_runs(blocks):
    """把「彼此腰斬相連」的 block 分組成 run；不相連的自成一組（長度1）。"""
    runs, current = [], [blocks[0]] if blocks else []
    for prev, nxt in zip(blocks, blocks[1:]):
        prev_orig = ct.strip_tags(prev['orig']) if prev['orig'] else ''
        nxt_orig = ct.strip_tags(nxt['orig']) if nxt['orig'] else ''
        connected = (prev_orig and nxt_orig
                     and ct._ends_midsentence(prev_orig)
                     and ct._starts_lowercase(nxt_orig))
        if connected:
            current.append(nxt)
        else:
            runs.append(current)
            current = [nxt]
    if current:
        runs.append(current)
    return runs


def page_nums_of(block):
    if not block['pg_text']:
        return []
    return [int(n) for n in re.findall(r'\d+', block['pg_text'])]


def render_merged(run):
    pages = []
    for b in run:
        pages += page_nums_of(b)
    if len(pages) >= 2:
        pg_label = f'<div class="pgmark">原書 p.{pages[0]}–{pages[-1]}</div>\n    '
    elif len(pages) == 1:
        pg_label = f'<div class="pgmark">原書 p.{pages[0]}</div>\n    '
    else:
        pg_label = ''
    zh = " ".join(ct.strip_tags(b['zh']) for b in run)
    orig_parts = [ct.strip_tags(b['orig']) for b in run if b['orig']]
    orig = " ".join(orig_parts)
    orig_html = f'\n      <div class="orig" lang="en">{orig}</div>' if orig else ''
    return (f'{pg_label}<div class="para">\n'
            f'      <div class="zh">{zh}</div>{orig_html}\n'
            f'    </div>\n')


def process_section(sec_html, max_run=4):
    """max_run：一組最多合併幾段。超過的長鏈視為「疑似深層損壞」，不動它，
    原樣保留並回報在 skipped_long 讓使用者知道還有哪些需要人工重譯。"""
    blocks = find_para_blocks(sec_html)
    if not blocks:
        return sec_html, 0, [], []

    runs = group_runs(blocks)
    merged_count = 0
    preview, skipped_long = [], []
    out_parts = [sec_html[:blocks[0]['start']]]
    for run in runs:
        if len(run) > 1 and len(run) <= max_run:
            merged_count += 1
            preview.append({
                'pages': [p for b in run for p in page_nums_of(b)],
                'zh_after': " ".join(ct.strip_tags(b['zh']) for b in run)[:160],
            })
            out_parts.append(render_merged(run))
        elif len(run) > max_run:
            pages = [p for b in run for p in page_nums_of(b)]
            skipped_long.append((pages[0] if pages else '?', pages[-1] if pages else '?', len(run)))
            for b in run:
                out_parts.append(sec_html[b['start']:b['end']])
        else:
            b = run[0]
            out_parts.append(sec_html[b['start']:b['end']])
    out_parts.append(sec_html[blocks[-1]['end']:])
    return "".join(out_parts), merged_count, preview, skipped_long


def main():
    ap = argparse.ArgumentParser(description="合併被頁界腰斬的相鄰段落（短鏈自動合併，長鏈跳過交人工重譯）")
    ap.add_argument("file", help="build/secNN.html")
    ap.add_argument("--out", help="輸出到新檔（預設就地覆寫，會先備份成 .bak）")
    ap.add_argument("--dry-run", action="store_true", help="只顯示會合併哪些，不寫檔")
    ap.add_argument("--max-run", type=int, default=4,
                    help="一組最多合併幾段（預設4）；超過視為疑似深層損壞，原樣跳過不動")
    args = ap.parse_args()

    path = Path(args.file)
    html = path.read_text(encoding="utf-8")
    secs = extract_sections(html)
    if not secs:
        sys.exit(f"{path}：找不到 <section class=\"sec\">")

    new_secs = []
    total_merged = 0
    all_preview, all_skipped = [], []
    for sec in secs:
        new_sec, n, preview, skipped = process_section(sec, max_run=args.max_run)
        new_secs.append((sec, new_sec))
        total_merged += n
        all_preview += preview
        all_skipped += skipped

    print(f"共發現 {total_merged} 組短鏈（≤{args.max_run}段）將自動合併")
    for p in all_preview[:20]:
        pages = p['pages']
        print(f"\n  頁 {pages[0]}–{pages[-1]}（合併 {len(pages)} 段 → 1 段）:")
        print(f"    合併後開頭：{p['zh_after'][:80]}…")
    if len(all_preview) > 20:
        print(f"\n  …（共 {len(all_preview)} 組，只顯示前 20）")

    if all_skipped:
        print(f"\n⚠ 另有 {len(all_skipped)} 組長鏈（>{args.max_run}段）疑似深層損壞，本次未動，需人工/重譯：")
        for a, b, n in all_skipped:
            print(f"    p.{a}–{b}（{n} 段）")

    if args.dry_run:
        print("\n（--dry-run，未寫檔）")
        return

    new_html = html
    for old_sec, new_sec in new_secs:
        new_html = new_html.replace(old_sec, new_sec, 1)

    out_path = Path(args.out) if args.out else path
    if not args.out:
        bak = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, bak)
        print(f"\n原檔已備份 → {bak}")
    out_path.write_text(new_html, encoding="utf-8")
    print(f"Done → {out_path}")
    print("⚠ 請務必人工／AI 抽查合併後的接縫處（重複詞、代名詞不連貫），"
          "再跑 check_translation.py 確認 FAIL 已消失。")


if __name__ == "__main__":
    main()
