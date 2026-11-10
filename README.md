# 有権者

官邸・各府省の発表を、出典リンクつきで要約して載せるサイト。評価は入れない（評価は今後「オピニオン」に分ける）。

## 毎日の流れ
1. Hermes（毎朝の定期実行）が `python tools/collect.py` で新着を集める → `drafts/candidates.json`
2. Hermes が大切なものを選び、元のページを読んで要約 → `drafts/drafts.json`（下書き）
3. Roy が「確認ページを開く.cmd」をダブルクリック → http://localhost:5600/review で「公開する／公開しない」を選ぶ
4. 公開したものだけ `data/news.json` に入り、サイトに出る（gitにコミット。GitHubとつなげば自動で公開）
   - 地方の下書き（`"scope": "local"`）は `data/local_news.json` に入る（下の「地方（都道府県）」を参照）

## フォルダ
- `index.html` トップ（夜の海と天の川のスクロールページ。府省ごとの章 → 物体をひらくと記事ビュー） / `ministries.html` 省庁別 / `local.html` 地方（3D の日本地図から都道府県を選ぶと、その県の記事が並ぶ。`?p=県id` でその県を直接開ける。下の「地方（都道府県）」を参照） / `pledges.html` 公約チェッカー（直近の衆院選で各党が約束したことと、その後の行動・達成率。`data/pledges.json` から `assets/pledges.js` + `pledges.css` で組み立てる。`#p=公約id` で詳細を直接開ける。3D の配色は `?v=a/b/c` の試作） / `opinion.html` オピニオン（準備中） / `about.html` このサイトについて
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
- `tools/collect.py` 新着集め / `tools/fetch_page.py` 本文の取り出し / `tools/fetch_photo.py` 写真の取り込み / `tools/review_server.py` + `tools/review.html` 確認ページ（`python tools/check_review_local.py` で地方の振り分けを一時フォルダのコピーで確認できる）

## 地方（都道府県）
`local.html` は「日本地図（3D）→ 都道府県を押す → その県の記事の一覧 → 記事」のページ。記事を開くと国の記事と同じリーダー（`assets/hall.js`、`#a=記事id`）で、用語ポップアップ・写真・背景の説明・出典もそのまま出る。
- `data/prefectures.json` 47都道府県の表：`id`（ローマ字。hokkaido, aomori, … tokyo, … okinawa）・`code`（JIS の 01〜47）・`name`（東京都）・`name_short`（東京）・`region`（北海道・東北／関東／中部／近畿／中国／四国／九州・沖縄）
- `data/local_news.json` 公開済みの地方の記事（最初は `[]`）。形は `data/news.json` と同じで、`ministry` の代わりに `pref`（都道府県id）、`also` の代わりに `pref_also: []`（任意。ほかの県にも出す）、`site` は「〇〇県ホームページ」
- `data/pref_sources.json` 47都道府県の公式サイト：`{id, name, site, home, feeds: [], type, note}`（`home` は公式トップの URL を確認済み。`feeds`・`type` はあとで入れる）
- 下書き：`drafts/drafts.json` に `"scope": "local"` と `"pref": "tokyo"` を付けて入れる。管理ページでは「地方・東京都」の印が付き、公開すると `data/local_news.json` に入る（`news.json` には入らない）。都道府県 id が間違っていると何も保存せずにエラーになる。公開済みタブは「国・地方」で絞り込める
- 見本：`local.html?sample=1` のときだけ `drafts/local_sample.json` の【サンプル】の記事も出す（drafts/ は git に入らないので公開サイトには出ない）
- 3D：`assets/map3d.js`（three.js r170 を CDN から。47都道府県を1つの形にまとめて描く）・`assets/prefmap.js`（地図データの読み込みと、押した点がどの県かの判定）・`assets/local.js` + `local.css`（ページの組み立て）。WebGL2 が使えないときは平らな SVG の地図、下に 47都道府県の一覧（キーボード・読み上げ用）
- `sitemap.xml` には今は `local.html` だけ。記事のある県が増えたら `local.html?p=県id` を足す（ページを開くと canonical も `?p=` 付きに変わる）

### 地図のデータとクレジット
- `data/prefmap.json`（約65KB）は `python tools/make_prefmap.py 元のTopoJSON data/prefmap.json` で作る。元は [スマートニュース メディア研究所「japan-topography」](https://github.com/smartnews-smri/japan-topography) の都道府県ファイル（`data/municipality/topojson/s0010/prefectures.json`）で、これは国土交通省「国土数値情報（行政区域データ）」（2021年）を簡素化したもの
- 国土数値情報の行政区域データ（2021年）はオープンデータ（政府標準利用規約2.0版。CC BY 4.0 互換、商用も可）。加工したことと出典を書く決まりなので、`local.html` のフッターに次のとおり書いている：
  「地図：「国土数値情報（行政区域データ）」（国土交通省）（https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-2021.html）をもとに有権者が加工して作成」
  （国が作ったように見える書き方はしない。japan-topography 側はクレジット不要だが、念のため名前を出している）
- 加工の内容：境界線をさらに簡単にした・とても小さい島を省いた・東京都の小笠原諸島など北緯30度より南の島を省いた・沖縄県と奄美（鹿児島県）の島々を左上の枠に移した
- 県章などの公式マークは使わない

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
