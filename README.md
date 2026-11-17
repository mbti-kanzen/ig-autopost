# Instagram 自動投稿（@16type_kanzen_manual）

予約表（`queue/queue.csv`）に並んだリール動画を、決まった時刻に Instagram の公式API で投稿する仕組みです。
PCの電源が切れていても、GitHub のサーバーが15分ごとに動いて投稿します。

## しくみ（ひとことで）

| 役割 | 使うもの | 費用 |
|---|---|---|
| 動画とカバーを、ネット上の「誰でも取りに来られる場所」に置く | GitHub Pages（`docs/media`） | 無料 |
| 決まった時間にプログラムを動かす | GitHub Actions（15分ごと） | 無料（公開リポジトリ） |
| Instagram へ投稿する | Instagram API with Instagram Login | 無料 |
| 合言葉（アクセストークン）の保管 | GitHub の Secrets（暗号化された保管場所） | 無料 |

投稿の流れ：予約時刻の約25分前に起動 →「入れ物（コンテナ）」を作る → 動画の処理完了を待つ → 予約時刻ちょうどに公開 → `state/posted.json` に記録。

- 予約時刻を3時間過ぎても投稿できなかった分は、変な時間に出ないようにスキップして記録します（GitHubから失敗メールが届きます）。
- 失敗したら1回だけやり直し、2回失敗したら止めて記録します。

---

## 初回の準備（黒田さんの作業・30〜60分）

> **アクセストークンは、Claude とのチャットに貼らないでください。** パスワードと同じくらい大事な合言葉です。GitHub の Secrets にだけ貼ります。

### 1. Meta のアプリを作る（Meta for Developers）
1. https://developers.facebook.com/ を開き、Facebook アカウントでログインして開発者登録をする。
2. 「アプリを作成」→ 用途（ユースケース）は **「Instagramでメッセージとコンテンツを管理」**（Manage messaging & content on Instagram）を選ぶ。種類を聞かれたら **ビジネス**。アプリ名は何でもよい（例：`mbti-autopost`）。
3. 左メニュー「Instagram」→ **「Instagramログインを使用したAPI設定」**（API setup with Instagram login）を開く。
4. 権限に `instagram_business_basic` と `instagram_business_content_publish` が入っていることを確認する。
5. 「アクセストークンを生成」の欄で **「アカウントを追加」** → @16type_kanzen_manual でログイン → 許可。
   - 「テスターの招待が必要」と出たら：左メニュー「アプリの役割」→「役割」→「Instagramテスター」に `16type_kanzen_manual` を招待 → Instagram アプリの「設定 → ウェブサイトのアクセス許可 → アプリとウェブサイト → テスターへの招待」で承認 → 5. に戻る。
6. アカウントの横の **「トークンを生成」** を押す。表示された長い文字（`IGAA…` で始まる）を **すぐに** コピーする（一度しか表示されません）。このトークンは60日間有効です。
7. そのまま次の「2. GitHub」の Secrets に貼る。メモ帳などに保存しない。

### 2. GitHub の準備
1. https://github.com/ でアカウントを作る（あればそのまま）。
2. 右上「＋」→「New repository」→ 名前 `ig-autopost`、**Public（公開）** を選んで作成。
   - 公開にするのは、無料で動画置き場（GitHub Pages）を使うためです。公開前の動画と投稿文が、URLを知っている人には先に見える点だけご了承ください。
3. **作ったら Claude に「作った」と伝える。** 中身（このフォルダ一式）は Claude が入れます。
   - 自分で入れる場合：リポジトリの画面で「uploading an existing file」→ このフォルダの中身をすべてドラッグ＆ドロップ → Commit。
4. リポジトリの「Settings」→「Pages」→ Source を **Deploy from a branch**、Branch を **main / docs** にして Save。
5. 「Settings」→「Secrets and variables」→「Actions」→「New repository secret」
   - Name：`IG_ACCESS_TOKEN`
   - Secret：1-6 でコピーしたトークン
6. 「Actions」タブを開き、ワークフローを有効にする（緑のボタンが出たら押す）。

### 3. 動作確認（公開はしない）
1. 「Actions」→「Instagram自動投稿」→「Run workflow」→ mode = **check** → Run。
   緑のチェックが付き、ログに「アカウント確認OK: @16type_kanzen_manual」と出ればOK。
2. 同じく mode = **dry-run** → Run。
   ログに「ドライラン：入れ物の作成と動画の処理まで成功」と出ればOK（投稿はされません）。
3. ここまで成功したら、あとは自動で予約どおりに投稿されます。最初の1本（11/18 20:15）は、Instagram アプリで投稿文の崩れやカバーを確認してください。

---

## トークン更新（60日ごと）

- 毎週月曜 3:40 に「アクセストークン更新」が自動で動きます。
- **自動で入れ替えるには、もう1つ合言葉 `GH_PAT` が必要です（任意）。**
  1. GitHub 右上のアイコン →「Settings」→「Developer settings」→「Personal access tokens」→「Fine-grained tokens」→「Generate new token」
  2. Repository access：`ig-autopost` だけ／Permissions：**Secrets を Read and write**／有効期限：1年
  3. できた文字を、リポジトリの Secrets に `GH_PAT` という名前で登録
- `GH_PAT` を入れない場合：発行から45日目ごろに、上の「1-6」でトークンを作り直して `IG_ACCESS_TOKEN` を上書きしてください（カレンダーに予定を入れておくと安心です）。
- トークンが漏れたかもと思ったら：Meta の管理画面で作り直し → Secrets を上書き。

## 新しい投稿を追加するとき

Claude に「新しい投稿キューを自動投稿に入れて」と頼めば、`scripts/build_queue.py` で取り込んで追加します。
自分でやる場合（Python と Pillow が必要）：

```
python scripts/build_queue.py "E:\ClaudeCode\mbti_manual\成果物\<日付>_投稿キュー\Instagram" --year 2026
```

`_予約表.md` の「予約」欄が ☐ の行だけを取り込みます（✔ は Business Suite で予約済みなので除外）。

## 手動で動かすとき（Actions →「Run workflow」）

| mode | 何をするか |
|---|---|
| check | トークンとアカウントの確認、投稿上限の確認 |
| dry-run | 次の1本の入れ物を作り、動画処理の成功まで確認（公開しない） |
| now | id 欄に書いた投稿を、今すぐ公開（予約時刻を無視） |
| auto | 通常と同じ動き |

## 注意
- 投稿の上限は24時間で100件（公式の記載）。1日2本なので余裕があります。
- API で投稿すると、Instagram の音楽ライブラリは付けられません。BGM は動画に入れてあるので問題ありません。
- GitHub の定時実行は混雑時に数分〜十数分遅れることがあります。そのため予約時刻の25分前から準備を始め、時刻ちょうどに公開する作りにしています。
- Meta の API の決まり（上限・トークンの期間など）は変わることがあります。
- 中身のファイル：`scripts/post_due.py`（投稿）、`scripts/refresh_token.py`（トークン更新）、`scripts/build_queue.py`（予約表づくり）、`.github/workflows/`（予約実行の設定）
