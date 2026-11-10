# 有権者

官邸・各府省の発表を、出典リンクつきで要約して載せるサイト。評価は入れない（評価は今後「オピニオン」に分ける）。

## 毎日の流れ
1. Hermes（毎朝の定期実行）が `python tools/collect.py` で新着を集める → `drafts/candidates.json`
   - 地方は `python tools/collect_local.py` → `drafts/local_candidates.json`（下の「毎日の地方ニュース」）
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
- `tools/collect.py` 新着集め / `tools/collect_local.py` 地方（47都道府県）の新着集め（下の「毎日の地方ニュース」） / `tools/fetch_page.py` 本文の取り出し / `tools/fetch_photo.py` 写真の取り込み / `tools/review_server.py` + `tools/review.html` 確認ページ（`python tools/check_review_local.py` で地方の振り分けを一時フォルダのコピーで確認できる）

## 地方（都道府県）
`local.html` は「日本地図（3D）→ 都道府県を押す → その県の記事の一覧 → 記事」のページ。記事を開くと国の記事と同じリーダー（`assets/hall.js`、`#a=記事id`）で、用語ポップアップ・写真・背景の説明・出典もそのまま出る。
- `data/prefectures.json` 47都道府県の表：`id`（ローマ字。hokkaido, aomori, … tokyo, … okinawa）・`code`（JIS の 01〜47）・`name`（東京都）・`name_short`（東京）・`region`（北海道・東北／関東／中部／近畿／中国／四国／九州・沖縄）
- `data/local_news.json` 公開済みの地方の記事（最初は `[]`）。形は `data/news.json` と同じで、`ministry` の代わりに `pref`（都道府県id）、`also` の代わりに `pref_also: []`（任意。ほかの県にも出す）、`site` は「〇〇県ホームページ」
- `data/pref_sources.json` 47都道府県の公式サイトと情報源：`{id, name, site, home, terms, terms_url, photo_ok, note, feeds: [...]}`
  - `terms` はそのサイトの再利用の決まりの一行まとめ、`terms_url` はその決まりのページ。`photo_ok` が `true` なのは北海道（『CC-BY』表示のあるページだけ）と新潟県（オープンデータ利用規約で CC BY 4.0。ヘッダー写真・第三者の著作物は除く）だけ。和歌山県（CC BY 4.0 互換）・岡山県（PDL1.0）は文章は再利用できるが写真は規約の対象外なので `false`。ほかは全部「引用の範囲」なので `false`
  - `feeds` の1件：`{url, kind, label, parser?, …}`。`kind` は `rss`（RSS 1.0/2.0）・`atom`・`html`・`json`
  - `html` の `parser`：`dated`（ふつうの一覧。リンクと日付を上から順に読み、リンクには直前の日付をつける。日付のつかないリンクは捨てる）・`links`（日付のない一覧。上から `max_items` 件）。`json` の `parser`：`fukui_kintone`（福井県の kViewer）・`nagasaki_json`（長崎県の press.json）
  - しぼり込み：`start` / `end`（この文字列から／までだけ読む）・`link`（URL の正規表現）・`skip`（落とすタイトルの正規表現）・`date_after: true`（日付がリンクのあとにある一覧）・`date_from_url`（URL の8桁から日付）・`encoding`（静岡県は `cp932`）・`cookies: true`（愛知県）
  - 新着（全体）しかない県（岩手・福島・熊本・大分・鹿児島・沖縄）は `"exclude": "@noise"` で入札・募集・採用・イベント・講座・パブコメ結果などを落とす（`@noise` の中身は collect_local.py の `NOISE`。`"@noise|ほかの語"` のように足せる）。`include`（`include_on: "url"` で URL に対して）で残すものだけにもできる
  - 月別ページの県：URL に `{yyyy}` `{yy}` `{mm}` `{m}` `{fy}`（年度）`{fy_reiwa}`（令和の年度）を書くと、その月の URL を作る（茨城・石川・島根・広島・神奈川）。URL が作れない県は `discover: {url, start?, text}` で索引ページからその月のリンクを探す（秋田・和歌山）。対象の期間が月をまたぐと先月のページも読む
  - **栃木県・東京都の RSS は使わない**（RSS を使った再配布・サイト構築を規約で断っている・事前申請が必要）。HTML の一覧から見出しとリンクだけ拾う
- 下書き：`drafts/drafts.json` に `"scope": "local"` と `"pref": "tokyo"` を付けて入れる。管理ページでは「地方・東京都」の印が付き、公開すると `data/local_news.json` に入る（`news.json` には入らない）。都道府県 id が間違っていると何も保存せずにエラーになる。公開済みタブは「国・地方」で絞り込める
- 見本：`local.html?sample=1` のときだけ `drafts/local_sample.json` の【サンプル】の記事も出す（drafts/ は git に入らないので公開サイトには出ない。確認サーバー 5600 は drafts/ を見せないので、見本を見るときは `python -m http.server 5655` で開いて http://localhost:5655/local.html?sample=1 。見本のファイルは PC の中だけにある）
- 下書きは `"scope": "local"` が必須（`pref` だけでは国の記事として news.json に入る。管理ページの「地方・〇〇県」の印も scope で決まる）
- 3D：`assets/map3d.js`（three.js r170 を CDN から。47都道府県を1つの形にまとめて描く）・`assets/prefmap.js`（地図データの読み込みと、押した点がどの県かの判定）・`assets/local.js` + `local.css`（ページの組み立て）。WebGL2 が使えないときは平らな SVG の地図、下に 47都道府県の一覧（キーボード・読み上げ用）
- `sitemap.xml` には今は `local.html` だけ。記事のある県が増えたら `local.html?p=県id` を足す（ページを開くと canonical も `?p=` 付きに変わる）

### 毎日の地方ニュース
1. `python tools/collect_local.py` で47都道府県の新着を集める → `drafts/local_candidates.json`（`{pref, pref_name, title, url, date, source_label, site}`。既に見た URL は `drafts/local_seen.json` に残り、二度と出ない）
   - `--days 3`（初期値。何日前まで）・`--pref tokyo,kanagawa`（県をしぼる）・`--dry-run`（書き込まずに候補を表示）・`--max-seconds 600`（全体の時間の上限）・`--report ファイル`（表示をファイルにも書く）
   - 最後に県ごとに「新着 N（一覧 M件・除外 K件）」と、失敗した feed の理由を出す。どこかが失敗しても終了コードは 0（ほかの県は続ける）。「0件（読み取れない・形が変わった？）」が出たら、そのサイトの作りが変わったので `pref_sources.json` の `start`・`link` などを直す
   - 行儀よく：リクエストは1つずつ・1秒あける・1回20秒で打ち切り。47都道府県で50回ほど、1分ほどで終わる
   - 愛知県は bot 対策（Imperva）があり、続けて取ると弾かれる。cookie を持って1回だけ取り、弾かれたら「bot 対策で弾かれた」と出して飛ばす（再試行しない。次の日にまた取れる）
   - 鹿児島県の記者発表一覧・沖縄県の報道発表ページは日付がないので、上から数件を「日付なし」で出す（初回は少し古いものも混ざる）
   - 福井県（kViewer）は詳細ページの URL が取るたびに変わるので、既読はレコードの番号（`fukui-kviewer:番号`）で覚える
2. 候補から、**1県につき1日1〜3件**、有権者に関係の深いものを選ぶ：知事の会見・発言、予算（補正予算を含む）、条例・計画、災害・事故・感染症、新しい制度の開始、県の不祥事・処分。表彰式・イベント・募集・入札・統計の定期発表は原則選ばない。何もない日は0件でよい
3. 元のページ（PDF のこともある）を読んで、`drafts/drafts.json` に `"scope": "local"`・`"pref": "県id"` を付けた下書きを書く（形は国の下書きと同じ）
   - **要約は自分の言葉で書く**。ほとんどの県は「引用の範囲」でしか使えないので、本文を写したり言い換えただけの文にしない
   - 引用するときは1〜2文までの短いものにして、「引用」と分かるように「」で囲み、出典（県名・ページ名・URL）を付ける
   - `site` は「〇〇県ホームページ」、`url` は県の公式ページ（PDF のときは PDF の URL）
   - 写真は `pref_sources.json` の `photo_ok` が `true` の県だけ（北海道・新潟県）。その場合も、そのページの表示（北海道は『CC-BY』表示）と、肖像や第三者の写真でないことを確かめる。`false` の県は写真なし
4. 国と同じく確認ページ（5600）で公開を選ぶと `data/local_news.json` に入る

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
