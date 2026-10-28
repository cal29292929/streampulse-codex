<!-- Reviewed by OpenAI Codex (gpt-6-luna) | Session ID: 01a17db5-d802-7142-af5d-1f98c633b614 | Timestamp: 2026-10-27T23:15:02+09:00 -->

このレビューは、提示された文書の範囲（§5.4の途中まで）に基づきます。§6以降の実装詳細やAppendixの内容は提示されていないため、そこに記載されているとされる仕様は検証できません。

# Architecture & Security Review — `DESIGN_OPUS55.md`

**対象:** Codex x TwitchCon Hackathon / StreamPulse Codex  
**判定:** **要修正。現状の仕様をそのまま実装すると、Twitch API契約、ライブ時の権限・障害処理、認証境界、再現可能なデモの要件で重大な不整合が出る。**  
**優先度:** P0 はライブ接続や秘密情報の安全性に関わる必須修正、P1 はデモ・要件達成・運用の信頼性に関わる必須修正。

## 総評

「EventSub → beat detection → human approval → overlay」という中心ループは、Audience Participation と Streamer Collaboration のテーマに合い、デモにも説明しやすい。一方、設計書は、仕様の確定度が異なる要素を同じ完成度で記述している。特に以下は、実装前に契約を修正する必要がある。

- EventSub WebSocket のサブスクリプション作成条件と再接続フロー
- OAuth Device Code Flow とチャット読み書きの権限モデル
- Twitch Channel Points の redemption 更新条件
- token のブラウザへの露出と REST/SSE/MCP の認証設計
- LLM、検索、画像 API のタイムアウト、再試行、プロバイダ障害時の境界
- 「決定的シミュレーション」と「バイト単位の成果物再現」の両立
- Hackathon の必須提出物・Stage One 要件・Devpost 証跡の確認方法

この仕様だけでは、README、デモ動画、成果物、submission URL などの提出要件が実装タスクとして閉じていない。また、「約90テスト」「5秒未満」「初回1コマンド」を合格条件として掲げる一方、具体的な受け入れ基準や実行コマンド、失敗時の扱いは不十分である。

## 重大な設計・契約上の問題

### P0 — EventSub WebSocket の認証・再接続契約を修正する

§3.3 は、WebSocket の `session_welcome` 後に Helix でサブスクリプションを作成する方式を記述している。subscription type ごとに必要な OAuth scope、token のユーザー、condition の整合性を事前検証する仕様がない。認証不足や broadcaster/user 不一致は一部の subscription だけを失敗させ、部分稼働に見える可能性がある。

さらに §3.4 は、`session_reconnect` 時に既存 subscription が引き継がれるとしながら、同じ節の末尾では予期しない close 後に新セッション用 subscription を作成するとしている。異なる接続イベントに対する処理が混在しており、二重登録・イベント欠落の原因になる。

**実装前に必要な修正:**

- `session_reconnect` と通常切断後の新規接続を別状態遷移として仕様化する。
- 新接続への切り替え完了まで旧接続を維持し、重複通知は `message_id` で抑止する。
- 通常切断後は再接続後に必要な subscription を再作成し、結果を subscription 単位で記録する。
- 失敗した subscription を deck に明示し、全 subscription が有効でない状態を `live-ready` と表示しない。
- Welcome から subscription 作成までの時間制限、HTTP timeout、429/401/403/5xx、部分失敗時の backoff と再試行上限を定義する。

### P0 — OAuth のトークン種別・scope・保管を一貫させる

§3.2 は Device Code Flow と `tokens.json` を示す一方、client secret が必要な「confidential app」にも触れている。§4.1 では `TWITCH_CLIENT_ID` と保存済み user token だけで Twitch を live 扱いする。トークンが期限切れ、無効、scope 不足でも live モードが選ばれるため、起動後に機能が部分的に失敗する。

`0600` は POSIX 環境での最低限のファイル権限にすぎず、Windows、バックアップ、例外ログ、CLI の出力、複数ユーザー実行環境まで保護しない。

**実装前に必要な修正:**

- 認証方式を Public Client の Device Code Flow に固定するのか、別方式もサポートするのかを決め、client secret の要否を整理する。
- 起動時に token の期限と Twitch validation 結果を確認し、必須 scope と broadcaster/user ID の整合性を検証する。
- scope 不足・期限切れ・validation 失敗時は、該当機能を disabled として表示し、自動で成功扱いにしない。
- 保存時は atomic write、ファイル権限設定、可能なら OS credential store を仕様化する。token をエラー、audit、manifest、ブラウザレスポンスに含めない。
- `.gitignore` は漏えい防止策ではない。誤コミット検出や secret scanning を提出前チェックに加える。

### P0 — Deck / Overlay / SSE のブラウザ認証を再設計する

`DECK_TOKEN` と `OVERLAY_TOKEN` を `tokens.json` に保存し、URL query token で SSE にアクセスする設計は、URL・ブラウザ履歴・OBS設定画面・アクセスログ・画面共有への漏えいを招く。`GET /api/state` の「deck or overlay」認証方式も定義されていない。CORS、Origin、CSRF、ブラウザからの bearer token の扱いも未指定である。

加えて `/api/meta` と `/healthz` が無認証で、`/api/meta` は `codex_session_id` を含む。session ID は公開データとして扱う根拠がなく、実行環境を識別する情報を不要に公開する。

**実装前に必要な修正:**

- `/api/meta` から `codex_session_id` を除く。Codex 利用の証跡は、明示的に公開を承認できる静的な build provenance に分離する。
- Overlay を公開読み取りにする場合は、許可するイベントとフィールドを固定した read-only view を作り、匿名で状態全体を返さない。
- Deck 操作には認証に加え、Origin 検証と CSRF 対策を適用する。全 API に認証要件を endpoint 単位で列挙する。
- SSE の認証は URL query token を避け、短命・限定スコープの接続資格情報などを仕様化する。ログ、エラー、Referer に秘密が残らないことを確認する。
- HTTP `/mcp` は deck token と共有せず、専用 scope の資格情報と読み取り専用／状態変更操作の権限分離を設ける。
- `ThreadingHTTPServer` をネットワーク公開する場合の bind address、TLS終端、Host/Origin検証、要求サイズ上限を規定する。

### P0 — Channel Points redemption の更新権限と所有条件を明確化する

§3.7 は、`setup-rewards` が作成した reward のみ fulfill/refund 可能と正しく触れているが、§3.2 の scope 記載と redemption API の条件が曖昧である。既存 reward を使う運用、reward 作成失敗、権限不足、二重処理時の挙動が定義されていない。Chaos Ticket による自由入力を overlay や LLM に渡す前の制限も不足している。

**実装前に必要な修正:**

- reward ID と broadcaster ID の所有関係を検証し、所有権を確認できない reward は更新しない。
- redemption ID 単位の idempotency を実装し、重複通知・再試行で二重 fulfill/refund しない。
- fulfillment/refund の状態遷移と、API失敗時に再試行する条件を定義する。結果不明時に反対操作へ進まない。
- `user_input` を不信入力として扱い、長さ制限、制御文字除去、HTML/JS エスケープ、LLM prompt injection 対策を行う。
- Ticket の自動 fulfil を行う前に、提案の採用・拒否・期限切れの対応を明示する。

### P0 — 「承認必須」と Autopilot の意味を厳密化する

設計では「すべての AI 提案は承認を通る」と説明する一方、Autopilot は action class の whitelist で承認なしに実行できる。これは説明上の矛盾であり、誤設定時に視聴者投稿や外部 MCP 呼び出しが直接配信に到達しうる。

**実装前に必要な修正:**

- Autopilot を既定無効にし、ライブ時の有効化には Control Deck 上の明示操作を要求する。
- 許可可能な action を固定 enum にし、poll、game、chat announcement、reward processing を別々に制御する。
- LLM/MCP が Autopilot の設定自体を変更できないようにする。
- 自動実行の期間、対象 broadcaster、最大頻度、最大報酬コスト、即時停止手段を定義する。
- デモ・ライブの表示と audit に、各 action が手動承認か Autopilot 実行かを記録する。

### P1 — Helix API の rate-limit と送信失敗処理を実用的にする

`remaining < 5` で pre-emptive sleep するだけでは、複数スレッドから同時に API を呼ぶ場合の競合、`Ratelimit-Reset` の単位、429応答、retry-after、リクエスト失敗時の不確定な送信状態を処理できない。ローカルの 20 messages / 30 s token bucket も、アカウント状態や他クライアントの送信を考慮しないため、Twitch 側の制限を保証しない。

**実装前に必要な修正:**

- Helix client を共有し、rate-limit 状態の更新と送信予約を thread-safe にする。
- 429、5xx、接続切断、timeout を分け、Twitch 応答ヘッダーと再試行可能性に従う。チャット送信は結果不明時に無条件再送しない。
- deadline/cancellation を設定し、rate-limit 待ちで request thread や provider worker を占有し続けない。
- UI には送信成功、未送信、抑制、結果不明を区別して表示する。
- token bucket の値を「保守的上限」と断定せず、APIの応答と実際の broadcaster/bot 権限に基づく設定可能な制限として扱う。

### P1 — 全外部呼び出しに timeout・retry budget・circuit breaker を定義する

§2.3 は provider 呼び出しを worker pool に分離するが、pool が2 worker のため LLM・Tavily・YouCam の遅延が重なるとキューが詰まりうる。§3.8 の「JSON/guard失敗時に一度 repair」は、通信timeout、429、5xx、無効認証にも適用されるか不明。§4.2 の「失敗時は Sim twin に degrade」も、何を失敗と判定するか、遅延中に fallback を返すかがない。

**実装前に必要な修正:**

- 各 provider に connect/read timeout、総 deadline、最大試行回数、指数 backoff と jitter、429/Retry-After 処理を定義する。
- JSON repair retry は通信 retry と別枠にする。401/403 や schema の恒常エラーを同じ形で再試行しない。
- 遅延上限を超えた時点で deterministic fallback を返し、遅れて届いた応答が採用済み状態を書き換えないよう generation ID を使う。
- bounded queue、同種要求の coalescing、circuit breaker、shutdown 時のキャンセルを設ける。
- Tavily 結果は外部不信データとして LLM に明示的に隔離し、指示として扱わない。
- `Sim*` fallback と live 成功を監査上で区別し、ユーザーに live AI が使われたと誤認させない。

### P1 — Webhook の重複排除・時刻検証・応答順序を補強する

§3.5 は署名検証、600秒 replay window、message ID dedupe を挙げるが、timestamp parsing、body 上限、message ID の TTL/capacity、並行要求での atomic dedupe、遅延キュー満杯時の応答が未定義である。受信イベントを非同期処理する前に 204 を返すと、プロセス停止や queue overflow で通知を失う。

**実装前に必要な修正:**

- timestamp を厳密に parse し、未来時刻、欠落ヘッダー、巨大 body、不正 JSON を拒否する。
- dedupe の確認と登録を atomic にする。イベント種別に応じた idempotency key と保持期間を定義する。
- 204 を返す前に永続キューへ格納するか、プロセス内キューなら overflow 時に再送可能なエラーを返す。
- Challenge、notification、revocation ごとの署名検証・応答コードを個別に受け入れテストする。
- Webhook secret の生成・保存・ローテーション・ログ除外を規定する。

### P1 — “standard library only” と WebSocket 実装範囲を限定する

RFC 6455 の「minimal client」を自前実装しながら TLS、masking、fragmentation、ping/pong、close handshake、frame length、安全な再接続まで担うのは、ライブイベントの信頼性と実装時間のリスクが高い。標準ライブラリ限定と Twitch WebSocket 対応の両立について、対応範囲と拒否条件が示されていない。

**実装前に必要な修正:**

- 自作 WebSocket の対応 RFC 範囲と、上限サイズ、非対応 opcode、fragment、compression の挙動を明記する。
- handshake と frame parser の境界値・不正 frame のテストを必須にする。
- 5秒デモの主要経路を WebSocket の自作実装に依存させない。ライブ接続が失敗した場合に操作可能な sim demo へ切り替える。
- 依存追加を許可する場合は「core」ではなく「live extra」などの区分とライセンスを明示する。

## 要件カバレッジと提出物

### Hackathon 要件・Prize 最適化

Audience Participation と Streamer Collaboration の両テーマを一つのデモで見せる狙いは良い。一方、Stage One を「Twitch + Codex の利用」とする根拠や、評価対象の提出条件がこの仕様内では確認できない。Devpost challenge 31742 の正式要件、提出形式、動画要件、期限のタイムゾーンは文書だけでは確定できない。

また、YouCam、Tavily、Nebius の API 契約が曖昧なまま「sponsor/track prize optimization」に含まれている。スポンサー API の利用が必須か任意か、各 API の実在する endpoint・認証方式・quota・申請可否が仕様化されていない。§3.10 は契約を環境変数で後から差し替えるとするため、実装時に API 接続できない可能性が残る。

**必須対応:**

- Hackathon brief を正として、Stage One gate、必須ツール、提出物、動画長、リポジトリ公開条件を一次資料から確認し、要件ごとに実装箇所と提出証跡を対応づける。
- deadline を PT/JST/UTC の絶対日時で統一し、DST を考慮した変換根拠を記録する。本文内の「2026-11-02 14:00 PT」「2026-11-03 07:00 JST」の一致を提出前に機械検証する。
- Devpost の提出物として少なくとも README、短い説明文、デモ動画、動作 GIF/スクリーンショット、再現手順、環境変数例、ライセンス、Codex provenance evidence、完成した submission checklist を明示する。
- API key がなくても提出デモが完走する fallback と、利用可能時に sponsor API がどう加点価値を生むかを切り分けて説明する。
- 価格・賞金・テーマ重み付けなど変わりうる情報を仕様に固定せず、確認日と一次資料への参照を付ける。

### デモ・シミュレーションの実装可能性

§4.3 の Poisson 生成・複数チャンネル・全成果物の「byte-identical」主張は、時刻、辞書順、OS、Python バージョン、JSON float 表現、audit timestamp、artifact 出力順を固定しないと成立しない。さらに固定された7 phase の合計は505秒であり、「full 10-minute stream arc」と一致しない。単一 RNG から sub-stream を作る方針は良いが、subsystem 内でのイベント順序や tie-breaker も決定的にする必要がある。

**必須対応:**

- phase 合計と10分 arcの仕様を一致させる。終了時刻・tick境界を定義し、残り時間をどう扱うか固定する。
- sim 内で wall-clock、UUID、thread scheduling、外部 provider、OS依存順序を使わない。
- JSON canonicalization、float丸め、sort key、改行、encoding、timestamp起点を固定し、同一 seed の digest を同一環境・複数 Python バージョンで検証する。
- RNG の派生方式、event tie-breaker、provider fallback 選択を仕様化する。
- 「実行5秒未満」は保証値と目標値を分け、指定環境・イベント数・許容差を明記する。CIの hard limit は測定ぶれを踏まえた余裕を設ける。
- `speed=0` の API と CLI の意味、sim を一時停止する動作、出力先、既存 artifacts の上書き方針を定義する。
- `--seed 42` がネットワークアクセスを一切行わないことを、socket禁止のテストで確認する。

## API・データモデル・エラー契約

### Internal REST / SSE

Internal API は認証欄が `deck`、`overlay` と抽象化され、403/401/404/409/429/5xx、request ID、入力サイズ、JSON schema、並行更新競合が未定義である。`POST /api/simulate` がサーバー上の共有 Engine を変更するか、別の isolated simulation を走らせるかも不明。SSE は 512件の ring buffer と `Last-Event-ID` replay を掲げるが、欠落した ID の扱い、clientごとのフィルタ、接続上限到達時の HTTP 応答、heartbeat、proxy buffering、token期限切れ時の切断がない。

**必須対応:**

- 全 endpoint に認証、role、入力 schema、成功・エラー status code、idempotency、side effect を記載する。
- deck/overlay/MCP を capability ごとに分離する。権限不足と無効な状態遷移はそれぞれ 403/409 などで一貫させる。
- SSE に heartbeat、再接続時の replay gap 検出、イベント順序、接続数上限、認証期限、queue overflow、イベントの個人情報フィルタを定義する。
- `/api/simulate` は本番 Engine と分離するか、共有状態変更を伴うことを明示して承認・排他制御を設ける。
- すべてのブラウザ出力で user-generated text を context-appropriate に escape し、overlay の DOM に `innerHTML` で直接挿入しない。

### LLM response schema

§3.8 の例では `action: start_poll` に対して poll options が4つある一方、user constraint の `options: [2,4]` が「選択肢数」なのか別の意味なのか曖昧である。モデルの `DirectorPlan` 定義は提示範囲にないため、`start_poll` 以外のaction、null/追加field、文字種、禁止内容、duration、option数の境界を検証できない。JSON mode は JSON Schema 検証や安全性を保証しない。

**必須対応:**

- 全 action の discriminated union schema を定義し、action と payload の不整合を拒否する。
- prompt の constraints と validator の条件を同一ソースから生成し、option数・文字数・durationの境界を合わせる。
- LLM出力、Tavily内容、Channel Points入力はすべて不信入力として扱う。HTML、URL、制御文字、過剰長、重複 option、禁止語、prompt injection の受け入れテストを行う。
- guard 失敗時に自動で提案を表示せず、fallback template を通じて同じ validator を必ず適用する。
- 人間の edit 内容も承認後に再検証し、approve と state transition を一つの lock 下で原子的に行う。

## Testability — 実装時に必須の決定的テスト

「約90 unit tests」はテスト計画ではない。Twitch/Nebius/Tavily/YouCam を実ネットワークに接続せず、契約・セキュリティ・再現性を判定できる具体的なテスト項目が必要である。開発者指示に従い、このレビューではテストを実行していない。

### Mandatory test matrix

- **EventSub WebSocket:** welcome timeout、期限内/期限外 subscription 作成、session_reconnect の切替、通常切断、重複 notification、revocation、部分 subscription 失敗。
- **Webhook:** 正しい署名、1byte改変、timestamp境界・未来時刻・不正形式、challenge、重複ID競合、queue overflow、巨大body。
- **Helix:** 401/403/429/5xx、`Retry-After` / `Ratelimit-Reset` 欠落・不正値、送信結果不明、chat `drop_reason`、redemption再送。
- **OAuth/token:** expiry、scope不足、broadcaster不一致、atomic token write、ログ・manifest・SSEへの秘密漏えい不在。
- **REST/SSE/MCP:** roleごとの認可、CSRF/Origin、invalid JSON/schema、oversized input、SSE reconnect/replay gap/overflow、MCP invalid JSON-RPC、unknown tool、disabled live `ingest_event`、domain errorの `isError`。
- **Concurrency:** 同時 approve の二重実行防止、同一 EventSub ID の二重処理防止、SSE slow client、provider queue saturation、shutdown時の worker 回収。
- **LLM/safety:** malformed JSON、追加field、action/payload不整合、XSS文字列、Unicode境界、prompt injection、Tavily poison、unsafe Ticket、fallback schema再検証。
- **Simulation:** 同一 seed digest一致、異なるseedの期待差、ネットワーク不使用、phase合計・イベント数、wall-clock独立性、成果物上書き挙動。
- **Golden artifacts:** README記載のコマンドをクリーン環境で実行し、run manifest、report、SVG/overlay screenshot が期待値と一致する。

テストでは `time`、HTTP transport、RNG、UUID、保存先、clock を注入可能にし、実時刻や実APIを呼ぶテストを通常CIから排除する。

## Mandatory Fixes for Implementation (Sakura `preview/Kimi-K2.7-Code`)

以下を実装開始前に設計へ反映し、コード・UI・テスト・提出物まで一貫させること。

### P0 — 着手前に必須

- [ ] Twitch EventSub の subscription 作成・再接続を状態機械として定義し、`session_reconnect` と通常切断を分離する。部分失敗を可視化し、未登録状態を Live Ready と表示しない。
- [ ] Twitch OAuth を一つの実装可能な方式に固定し、token expiry、validation、scopes、user/broadcaster IDを起動時に検証する。期限切れやscope不足は明示的な degraded/disabled 状態にする。
- [ ] Token、Deck、Overlay、MCP の権限境界を再設計する。`codex_session_id` を無認証 `/api/meta` から除き、URL query tokenを避け、CSRF/Origin/Host/body-size対策を記載する。
- [ ] Channel Points redemption の所有条件、idempotency、状態遷移、API失敗時の扱いを定義する。`user_input` は不信入力として制限・escape・検証する。
- [ ] Autopilot を既定無効にし、権限を action class ごとに限定する。LLM/MCPから設定変更不可、期間・頻度・停止操作・audit表記を実装する。
- [ ] Hackathon の一次資料で deadline、Stage One、必須ツール、提出形式を照合し、README、デモ動画、GIF/画像、実行手順、環境変数例、Codex provenance、Devpost checklist を完成条件にする。
- [ ] `CODEX_SESSION_ID` の取得・公開方法を決定し、秘密または個人データを含むセッション識別子を公開 artifact に埋め込まない。Codex利用証跡は安全な形で説明する。

### P1 — ライブ・デモの信頼性に必須

- [ ] Helix、Nebius、Tavily、YouCam 全呼び出しに timeout、deadline、限定 retry、backoff/jitter、429処理、shutdown cancellationを設定する。遅延応答は採用済み状態を上書きできないようにする。
- [ ] Provider poolをboundedにし、queue saturation、同一要求のcoalescing、circuit breaker、fallback発動条件を定義する。
- [ ] Helix rate limitをthread-safeに管理し、429・結果不明・`drop_reason`を区別する。結果不明のchat送信を無条件再送しない。
- [ ] Webhookで厳密なtimestamp/body検証、atomic dedupe、secret管理、queue overflow時の応答を定義する。非永続queueならイベント損失を成功扱いしない。
- [ ] SSEに認証、heartbeat、replay gap、接続上限、overflow、期限切れ、個人情報フィルタを実装する。ブラウザでは user-generated content を常にescapeする。
- [ ] Internal REST/MCP全操作に schema、role、status code、状態遷移、並行実行時のidempotencyを定義する。approve と実行を原子的に処理する。
- [ ] LLM、Tavily、Chaos Ticket、viewer textを不信入力として扱い、共通validatorを使う。prompt injection/XSS/Unicode/長さ/重複/禁止内容のテストを加える。
- [ ] Simulationのphaseを10分と一致させ、virtual clock、canonical JSON、float丸め、event順、timestamp、UUIDを固定する。同一seedのartifact digest一致とネットワーク不使用を決定的にテストする。
- [ ] 独自 WebSocket client の対応範囲を限定し、frame/handshake境界値、malformed frame、サイズ上限、再接続をテストする。ライブ接続失敗時もsim demoを継続可能にする。
- [ ] API契約テストをmock transportで実施し、実ネットワークやwall clockに依存しない。最低限、レビューで列挙したOAuth/EventSub/Webhook/Helix/REST/SSE/MCP/LLM/fallbackの境界ケースをCI対象にする。

## 最終判定

中心アイデアはHackathon向けに有望だが、提示設計は「実装可能な契約」としては未完成である。P0の認証・EventSub・redemption・Autopilot・提出要件を設計段階で確定し、P1の障害処理と決定性をテスト可能な受け入れ条件に落としてから実装に進むべきである。
