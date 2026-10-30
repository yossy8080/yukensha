# 有権者

官邸・各府省の発表を、出典リンクつきで要約して載せるサイト。評価は入れない（評価は今後「オピニオン」に分ける）。

## 毎日の流れ
1. Hermes（毎朝の定期実行）が `python tools/collect.py` で新着を集める → `drafts/candidates.json`
2. Hermes が大切なものを選び、元のページを読んで要約 → `drafts/drafts.json`（下書き）
3. Roy が「確認ページを開く.cmd」をダブルクリック → http://localhost:5600/review で「公開する／公開しない」を選ぶ
4. 公開したものだけ `data/news.json` に入り、サイトに出る（gitにコミット。GitHubとつなげば自動で公開）

## フォルダ
- `index.html` トップ（夜の海と天の川のスクロールページ。府省ごとの章 → 物体をひらくと記事ビュー） / `ministries.html` 省庁別 / `local.html` 地方（東京都・準備中） / `pledges.html` 公約トラッカー（準備中） / `opinion.html` オピニオン（準備中） / `about.html` このサイトについて
  - `assets/home.js` + `home.css` トップの組み立て・スクロール演出 / `assets/hall.js` + `hall.css` 記事ビュー（`index.html#m=府省id`、`#a=記事id` で直接開ける）
  - 3D（Three.js r170 を CDN から。WebGL2 が使えない・読み込みに失敗・「動きを減らす」設定のときは CSS の明朝1文字のエンブレムに切り替わる）
    - `assets/scene3d.js` 全体のまとめ（カメラ・スクロールとの対応・クリック判定）
    - `assets/models3d.js` 府省を表す物体の形（プリミティブ・押し出し・Lathe・Tube で手作り。外部のモデルファイルは使わない）
    - `assets/morph3d.js` 光の粒子でできた物体と、府省から府省への変形（天の川に巻き込まれて渦を巻き、次の形に集まる）
    - `assets/galaxy3d.js` + `band3d.js` 天の川の帯（星・星雲のにじみ・塵の筋・府省の節）/ `assets/sea3d.js` 夜の海と空
  - `tools/models.html` 物体の一覧（確認用。`http://localhost:…/tools/models.html` で全部の形を並べて見られる）
  - `assets/glossary.js` + `glossary.css` + `data/glossary.json` 用語ポップアップ（難しい用語の簡単な説明。語を足すときは glossary.json に追加）
  - `assets/glyphs.json` 象徴の1文字の字形（`python tools/make_glyphs.py フォント.ttf` で作る。今のトップの 3D では使っていない）
- `data/sources.json` 集める発表元の一覧（府省を足すときはここに追加。`emblem` = フォールバック用の1文字、`model` = トップの 3D の物体。下の表を参照）
- `data/news.json` 公開済みの記事
- `drafts/` 下書き・候補（gitに入れない）
- `assets/photos/` 記事の写真（下の「写真」を参照）
- `tools/collect.py` 新着集め / `tools/fetch_page.py` 本文の取り出し / `tools/fetch_photo.py` 写真の取り込み / `tools/review_server.py` + `tools/review.html` 確認ページ

## トップの 3D の物体（`data/sources.json` の `model`）
公式ロゴ・紋章（桐紋など）と赤十字のマークは権利の問題があるので使わず、その府省を代表する「物」で表しています。
差し替えるときは、sources.json の `model` を下のキーのどれかに変えるだけです（新しい形を足すときは `assets/models3d.js` の `BUILD` に追加）。

| id | 府省 | model | 物体 |
|---|---|---|---|
| hatsugen | 総理・官房長官の発言 | diet | 国会議事堂（中央の塔と階段状のピラミッド屋根、左右に翼棟） |
| kantei | 首相官邸 | kantei | 首相官邸の建物（ガラス張りの低層棟と、大きく張り出した水平の庇） |
| cao | 内閣府 | compass | 羅針盤（方位磁針） |
| digital | デジタル庁 | phone | スマートフォン（画面に格子状のアイコン） |
| soumu | 総務省 | tower | 電波塔（格子の鉄塔とアンテナ） |
| moj | 法務省 | scales | 天秤 |
| mofa | 外務省 | globe | 地球儀（経線・緯線・陸地と台座） |
| mof | 財務省 | coins | 積み重ねた硬貨 |
| mext | 文部科学省 | book | 開いた本 |
| mhlw | 厚生労働省 | heart | 手のひらに乗ったハート（十字は使わない） |
| maff | 農林水産省 | rice | 稲穂 |
| meti | 経済産業省 | gear | 噛み合う歯車 |
| mlit | 国土交通省 | bridge | アーチ橋 |
| env | 環境省 | leaf | 葉（葉脈つき） |
| mod | 防衛省 | shield | 盾（武器は出さない） |

`hidden` の府省（国会会議録）はトップに出ないので `model` はありません。

## 写真
記事には写真を付けられます（`photos` 欄・任意）。写真のファイルは `assets/photos/<記事id>-1.jpg` のように置きます。
```
"photos": [{"src": "assets/photos/<記事id>-1.jpg", "alt": "写っているものの説明（日本語）",
            "credit": "写真：首相官邸ホームページ", "page_url": "写真が載っている公式ページのURL",
            "license": "PDL1.0", "people": true,
            "ok_license": false, "ok_people": false}]
```
- **サイトに出る条件**：`ok_license` が true、かつ（`people` が false か `ok_people` が true）。確認が済んでいない写真は news.json に入っていても出ない
- `ok_license`（ライセンスOK）・`ok_people`（人物OK）は Roy が管理ページでチェックする。Hermes は false のまま入れる
- 1枚目は見出しのすぐ下、2枚目からはポイントの下に出る。写真の下にクレジットと「出典ページ ↗」のリンク
- 書き直しの下書きに `photos` 欄が無いときは、公開中の記事の写真（確認の結果も）をそのまま引き継ぐ。写真を全部外すときは `"photos": []`
- 公開・修正を保存すると、どれかの記事が使っている `assets/photos/` のファイルだけ git に入る（使っていない写真は入らない）
- 取ってくる：`python tools/fetch_photo.py 画像のURL assets/photos/<記事id>-1.jpg --referer 写真が載っているページ`（手元のファイルでも可）。長い辺1600px・JPEG・EXIFなしにして「OK 幅x高さ バイト数」と出る（`width` `height` を photos に書いておくと読み込み中に文字がずれない）
- **使ってよい写真**：首相官邸・各府省のサイトの写真で、PDL1.0 または政府標準利用規約（2.0版）で使えるものだけ。クレジットは「写真：〇〇ホームページ」と書く
- **使わない写真**：通信社・報道機関・第三者のクレジットが付いた写真（例：「写真：共同通信」）、ロゴ・紋章・シンボルマーク。JAXA の写真は事前の許可が必要なので使わない

## ルール
- 一次情報（政府の発表）だけを使う。新聞記事の本文は使わない
- 全記事に出典リンク。「〜をもとに有権者が要約して作成」と書く（政府の利用規約 PDL1.0 のルール）
- 首相官邸のRSSは再配布が禁止されているので使わない（官邸は新着ページのHTMLから集める）
- 事実だけを書く。良い・悪いの評価は書かない
- 公開前に必ず Roy が確認する
