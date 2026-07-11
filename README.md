# translate-academic-paper

把**學術論文或人文專著的 PDF**，翻譯成一份**單一自包含的 HTML**——頂部可切換
**純中文 / 中英對照 / 純原文**三種檢視，圖片、公式、掃描原頁全部 base64 內嵌，零外部相依，
可直接傳給任何人。輸出為**繁體中文（台灣用語）**。

原為 [Claude Code](https://claude.com/claude-code) 的 skill，但**廠商中立**：任何能操作檔案、
執行 shell 的 agent（Claude / Gemini / GPT / 本地模型，搭配 Cursor / Cline / Aider / 各家 CLI）
都能照 [`references/runbook.md`](references/runbook.md) 獨立跑完。

> ⚠️ **硬規則：譯文必須由執行的模型親自逐段翻譯，禁止外包給機器翻譯 API/工具。**
> 部分 coding agent 會為「效率」偷接 MT 服務或另開 LLM 代翻，也會在長章節上悄悄
> 濃縮成摘要交差（實測真的發生過：60 頁章節只給 9 段）。交接時請一併貼上
> [`runbook.md` 的「交接強化句」](references/runbook.md)，並在**每章翻完後強制跑**
> `scripts/check_translation.py` 品質關卡，FAIL 就打回重譯，不要靠事後肉眼複查整本。

> ⚠️ **不建議在 Claude（Anthropic 代管 API）上執行翻譯與原文轉錄步驟。**
> 實測會踩到**兩個彼此獨立的輸出端過濾器**，皆回 400 攔截輸出（連寫檔都被擋）：
> 1. **敏感語彙誤判**：19 世紀公有領域經典含當時的殖民/種族/性別用語、體罰描述，
>    翻譯輸出會被反覆誤攔；
> 2. **書籍逐字複製攔截**：大量逐字輸出書籍原文（即使是 1894 年公版書、即使只是
>    純英文轉錄不含翻譯）也會觸發防複製過濾器——實測開全新 session 做純提取同樣被擋。
>
> 偵察、腳本、QA、合併等其餘步驟不受影響，「修正清單模式」（只輸出 OCR 底稿的 diff，
> 見 runbook §B2）可大幅降低第 2 類觸發率。**翻譯與整頁轉錄請交給過濾較寬鬆的模型執行**
> （本 skill 廠商中立，照 runbook 即可交接）；現代技術論文通常無此問題。

## 概念驗證（PoC）狀態

本 skill 的 B2 批次流程已於 **GPT-5.5（Codex）環境**下，以
**Spencer《Education: Intellectual, Moral, and Physical》(D. Appleton, 1894)**
——309 頁、19 世紀老字體、含前任讀者手寫批註的掃描書——完成概念驗證：
sec03 試譯批（p.177–182，含跨頁段落與跨頁腳註）與 sec02 兩個正式批（p.94–112）
經對照頁面圖逐段驗收通過（忠實度、段落邊界、腳註歸位、批註排除）。

各分級實測狀況：

| 級別 | 定義 | 驗證狀況 |
|------|------|----------|
| **A** 原生電子檔 | 有正常文字層 | ✅ 已驗證（現代論文，本 skill 原始流程）|
| **B1** 乾淨掃描 | OCR 錯誤 ≲3 處/頁 | ⚠️ 流程同 A + 對圖抽查，尚無完整實測案例 |
| **B2** 髒掃描 | OCR 錯誤 >3 處/頁、老字體、手寫批註 | ✅ 已驗證（Spencer 1894，GPT-5.5 環境）|
| **C** 無文字層 | 掃描無 OCR | ⚠️ 看圖直譯流程可用，尚無整本書實測 |

成品效果（第二章開頭，中英對照檢視）：

![第二章中英對照渲染](docs/demo_sec02_bilingual.png)

**B2 能力示範**——左：原書 p.180 掃描頁（前任讀者的鉛筆圈線、打勾、邊註，
且腳註從 p.179 跨頁而來）；右：成品對應段落（批註完全排除、跨頁腳註正確合併歸位）：

![手寫批註頁 vs 成品對照](docs/demo_b2_annotated_page.png)

## 特色

- **文件分類 A/B1/B2/C**：原生電子檔 / 乾淨掃描 / 髒掃描 / 無文字層，自動判定＋髒度判級分流。
- **B2 批次流程**：老書掃描走「OCR=定位器、頁面圖=證據」的分層批次管線（translation units JSON 為正典、批批 QA、接縫驗證），詳見 runbook §B2。
- **看圖直譯**：掃描檔用頁面圖翻譯（不跑 Tesseract，避免 OCR 錯字污染），適合古籍與低品質掃描。
- **雙欄還原**：會議論文的雙欄版面自動還原正確閱讀順序，輸出統一單欄。
- **術語詞庫**：先查標準譯法（台灣繁中慣例）再鎖定，全文一致；模型/資料集專名保留原文。
- **圖表 / 公式**：caption 錨點擷取圖表；公式以原圖截圖內嵌，保證與原文一致。
- **書目 header**：論文（作者/單位/期刊·卷期/DOI）與專著（出版社/出版地/版次/ISBN）皆可。
- **三態檢視**：一份 HTML，純中 / 對照 / 純原文即時切換；內建列印樣式。
- **多格式輸出**：自包含 HTML 為主，另可選擇輸出 Word `.docx`（純中 / 對照 / 純原文）。
- **品質關卡**：每章翻完自動檢查抽稿／缺原文對照／頁碼跳號逆行／簡體字混入，不合格擋下重譯。

## 給不熟技術的老師：三步開始

如果你不會用命令列、看到 `git` `pip` 這些字就頭痛，別擔心——**這些都交給 AI 處理，
你只要準備 PDF、最後驗收成品**。

**第 1 步｜準備一個「能操作你電腦檔案的 AI 助手」。**
不是網頁版 ChatGPT/Gemini（那種只能聊天，不能在你電腦上跑程式、讀寫檔案）。
要用能「動手做事」的版本，例如：
[Claude Code](https://claude.com/claude-code)、Codex CLI、Gemini CLI、
[Cursor](https://cursor.com)、Cline 等。裝好其中一個、打開它、確認它能看到你的資料夾即可。

**第 2 步｜把下面這整段話複製、貼給你的 AI 助手：**

```text
我要把一份 PDF（學術論文或古書）翻譯成中英對照的網頁，請用這個開源工具：
https://github.com/Zaious/translate-academic-paper

請你幫我：
1. 把這個 repo 下載到我電腦上（git clone），並安裝它需要的套件。
2. 讀裡面的 SKILL.md 和 references/runbook.md，之後完全照它的流程做。
3. 開始前先問我這幾件事：PDF 檔放在哪、要翻成什麼語言、整本還是某幾章、
   成品要 HTML 還是也要一份 Word。

請務必遵守這個工具寫明的規則：
- 翻譯要你自己一段一段親手翻，不可以偷偷丟給 Google 翻譯或別的翻譯 API。
- 長章節要完整翻，不可以縮寫成摘要。
- 每翻完一章就跑一次它的品質檢查腳本，沒通過就重翻那一章。
```

**第 3 步｜照它問你的回答。**
把 PDF 檔給它、選好語言與範圍，剩下的它會自己跑。跑完你會拿到一份可以直接用瀏覽器
打開、也能傳給別人的網頁檔。

> 💡 **小提醒**：如果你要翻的是**十九世紀以前的老書**、而你的 AI 助手是 **Claude 系**，
> 翻譯那一步可能會被系統的安全過濾器誤擋（原因見上方警告）。遇到這種情況，
> 把**翻譯這一步**改用 GPT 系或 Gemini 系的助手跑就行，其他步驟不受影響。

---

## 快速開始（技術版）

> 給熟悉命令列的使用者或 AI agent；上面「三步開始」其實就是讓 AI 幫你跑完這一節。

```bash
pip install pymupdf pillow

# 1) 偵察：判定 A/B/C、offset、欄數、章節、書目
python scripts/inspect_pdf.py "TARGET.pdf"

# 2) 依 references/runbook.md 逐段翻成 build/secNN.html（翻譯單位是「段落」）
#    書目寫成 build/meta.html
#    每章翻完立刻跑品質關卡（強制）：
python scripts/check_translation.py build/secNN.html --min-page N1 --max-page N2

# 3) 合併成單一 HTML（建議輸出到 out/，與 build/ 分開）
python scripts/combine_paper.py --build build --out "out/成品_中譯.html" --default-view both

# 3b) （選用）另外輸出 Word .docx
python scripts/export_docx.py --build build --out "out/成品_中譯.docx" --view zh
```

完整流程見 [`SKILL.md`](SKILL.md)；照著跑的操作手冊見 [`references/runbook.md`](references/runbook.md)。

## 結構

```
SKILL.md                  主工作流程
references/
  runbook.md              可攜執行手冊（任何 agent 照著跑）
  methodology.md          翻譯方法論（技術論文 vs 人文論說文；敏感史料）
  glossary-guide.md       詞庫建立與標準譯法查證
  css-template.md         HTML 結構、書目 header、對照/圖/公式模板
  pipeline-notes.md       腳本原理、A/B/C 判定、雙欄與圖表調參
scripts/                  8 支腳本（偵察 / 抽文 / 渲染 / 品質關卡 / 圖表 / 公式 / 合併 / docx）
```

## 目標語言

目前核心針對**繁體中文（台灣用語）**最佳化（兩岸用語對照、學術名詞查證、Noto Serif TC 字型）。
架構為語言中立的管線 + 可插拔的語言設定，未來要支援其他目標語言時，新增一份方法論與字型設定即可，
毋須改動抽取／合併流程。歡迎 PR。

## 授權

[MIT](LICENSE) © 2026 Zaious。可自由取用、修改、散布，惟須保留著作權聲明。
