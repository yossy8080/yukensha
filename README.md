# 有権者

官邸・各府省の発表を、出典リンクつきで要約して載せるサイト。評価は入れない（評価は今後「オピニオン」に分ける）。

## 毎日の流れ
1. Hermes（毎朝の定期実行）が `python tools/collect.py` で新着を集める → `drafts/candidates.json`
2. Hermes が大切なものを選び、元のページを読んで要約 → `drafts/drafts.json`（下書き）
3. Roy が「確認ページを開く.cmd」をダブルクリック → http://localhost:5600/review で「公開する／公開しない」を選ぶ
4. 公開したものだけ `data/news.json` に入り、サイトに出る（gitにコミット。GitHubとつなげば自動で公開）

## フォルダ
- `index.html` トップ（夜の海のスクロールページ。府省ごとの章 → 象徴をひらくと記事ビュー） / `ministries.html` 省庁別 / `local.html` 地方（東京都・準備中） / `pledges.html` 公約トラッカー（準備中） / `opinion.html` オピニオン（準備中） / `about.html` このサイトについて
  - `assets/home.js` + `home.css` トップの組み立て・スクロール演出 / `assets/scene3d.js` 3D（Three.js r170 を CDN から。失敗したら CSS の表示に切り替わる） / `assets/hall.js` + `hall.css` 記事ビュー（`index.html#m=府省id`、`#a=記事id` で直接開ける）
  - `assets/glossary.js` + `glossary.css` + `data/glossary.json` 用語ポップアップ（難しい用語の簡単な説明。語を足すときは glossary.json に追加）
  - `assets/glyphs.json` 象徴の1文字の字形（`python tools/make_glyphs.py フォント.ttf` で作る）
- `data/sources.json` 集める発表元の一覧（府省を足すときはここに追加。`emblem` = 府省を象徴する1文字。足したら make_glyphs.py を実行）
- `data/news.json` 公開済みの記事
- `drafts/` 下書き・候補（gitに入れない）
- `tools/collect.py` 新着集め / `tools/fetch_page.py` 本文の取り出し / `tools/review_server.py` + `tools/review.html` 確認ページ

## ルール
- 一次情報（政府の発表）だけを使う。新聞記事の本文は使わない
- 全記事に出典リンク。「〜をもとに有権者が要約して作成」と書く（政府の利用規約 PDL1.0 のルール）
- 首相官邸のRSSは再配布が禁止されているので使わない（官邸は新着ページのHTMLから集める）
- 事実だけを書く。良い・悪いの評価は書かない
- 公開前に必ず Roy が確認する
