# Phone Caller — AI 電話エージェント カスタムスキル

TAM が提供するカスタムスキル。ユーザーの代わりに AI が電話をかけ、人間のように自然な会話を行う。

---

## アーキテクチャ概要

```
ユーザー（Agent Sheet / CLI）
  │
  │  "○○さんに電話して、△△の件を確認して"
  ▼
phone-caller Agent（100x-engineering-agents）
  │
  │  1. 通話目的・相手情報・シナリオを構築
  │  2. ElevenLabs Eleven Agents API でボイスエージェント作成
  │  3. Twilio 経由で発信
  ▼
┌─────────────────────────────────────────────┐
│  ElevenLabs Eleven Agents                    │
│  ┌─────────────┐    ┌──────────────────┐    │
│  │ TTS Engine   │    │ Conversation LLM │    │
│  │ (Flash v2)   │    │ (System Prompt)  │    │
│  └──────┬──────┘    └────────┬─────────┘    │
│         │                    │               │
│         ▼                    ▼               │
│  ┌─────────────────────────────────────┐    │
│  │      Twilio Voice (WebSocket)       │    │
│  │  架電 → 通話 → 録音 → 文字起こし    │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
  │
  ▼
通話結果（構造化データ）
  - 通話サマリー
  - 文字起こし全文
  - 評価結果（目的達成度）
  - 収集データ（相手の回答）
```

## テナント管理方式: TAM 一括管理（Twilio Subaccounts）

```
TAM マスター Twilio アカウント（親）
  ├── Subaccount: テナント A
  │     └── 電話番号: +81-50-xxxx-xxxx（購入済み）
  ├── Subaccount: テナント B
  │     └── 電話番号: +81-50-yyyy-yyyy（購入済み）
  └── ...（最大 1,000 Subaccount / デフォルト）
```

**設計判断:**
- 通話料は TAM マスターアカウントに一括請求 → テナントへの課金に転嫁
- 電話番号の購入・管理は TAM 側で一元化
- テナントは Twilio アカウント不要（セットアップのハードルを排除）
- Subaccount 間のデータは完全分離（セキュリティ）

---

## 前提条件

### 必須アカウント・API キー

| サービス | 用途 | 環境変数 |
|---------|------|---------|
| Twilio | 電話発信・受信・通話制御 | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` |
| ElevenLabs | 音声合成（TTS）+ 会話 AI + 音声認識（STT） | `ELEVENLABS_API_KEY` |

### 必須パッケージ

```bash
pip install twilio elevenlabs python-dotenv
```

---

## ワークフロー

### Phase 1: 通話準備

1. ユーザー入力を解析し、以下を構造化する:
   - `callee_name`: 通話相手の名前
   - `callee_phone`: 通話相手の電話番号（E.164 形式: `+81XXXXXXXXXX`）
   - `purpose`: 通話の目的（1〜2文）
   - `scenario`: 会話シナリオ（分岐条件含む）
   - `data_to_collect`: 通話中に収集すべき情報
   - `max_duration_seconds`: 最大通話時間（デフォルト: 300秒）
   - `language`: 通話言語（デフォルト: `ja`）

2. テナントの Twilio Subaccount SID / Auth Token を取得する

3. テナントに紐づく発信元電話番号を取得する

### Phase 2: ElevenLabs エージェント作成

ElevenLabs Conversational AI API でボイスエージェントを作成する。

**API エンドポイント:** `POST https://api.elevenlabs.io/v1/convai/agents/create`

```python
from elevenlabs.client import ElevenLabs

client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

agent = client.conversational_ai.agents.create(
    name=f"phone-call-{callee_name}-{timestamp}",
    tags=["phone-caller", "outbound"],
    conversation_config={
        "tts": {
            "voice_id": "<selected_voice_id>",
            "model_id": "eleven_flash_v2",
        },
        "asr": {
            "quality": "high",
            "provider": "elevenlabs",
            "user_input_audio_format": "ulaw_8000",
            "keywords": [],  # domain-specific keywords for better recognition
        },
        "agent": {
            "first_message": first_message,  # e.g. "お忙しいところ恐れ入ります。TAMの○○と申します。"
            "prompt": {
                "prompt": system_prompt,  # scenario-based conversation instructions
            },
            "language": language,
        },
        "conversation": {
            "max_duration_seconds": max_duration_seconds,
        },
    },
    platform_settings={
        "evaluation": {
            "criteria": [
                {
                    "id": "purpose_achieved",
                    "name": "目的達成",
                    "description": "通話の目的が達成されたかどうか",
                }
            ],
        },
        "data_collection": {
            "items": [
                {"type": "string", "id": key, "description": desc}
                for key, desc in data_to_collect.items()
            ],
        },
    },
)
```

### Phase 3: Twilio 経由で発信

ElevenLabs の Twilio ネイティブ統合 API で発信する。

**API エンドポイント:** `POST https://api.elevenlabs.io/v1/convai/twilio/outbound-call`

```python
import requests

response = requests.post(
    "https://api.elevenlabs.io/v1/convai/twilio/outbound-call",
    headers={"xi-api-key": os.getenv("ELEVENLABS_API_KEY")},
    json={
        "agent_id": agent.agent_id,
        "agent_phone_number_id": phone_number_id,   # ElevenLabs に登録済みの番号ID
        "to_number": callee_phone,                   # E.164 format
    },
)
```

### Phase 4: 通話モニタリング・結果取得

1. 通話完了を待機（ポーリングまたは Webhook）
2. 通話履歴 API から結果を取得:
   - `GET https://api.elevenlabs.io/v1/convai/conversations/{conversation_id}`
3. 結果を構造化データとして出力

### Phase 5: 結果報告

```json
{
  "status": "completed",
  "duration_seconds": 127,
  "summary": "○○様に△△の件を確認。来週月曜の午前中に訪問可能とのこと。",
  "transcript": [
    {"role": "agent", "text": "お忙しいところ恐れ入ります。TAMの..."},
    {"role": "user", "text": "はい、○○です。"},
    ...
  ],
  "evaluation": {
    "purpose_achieved": "success",
    "rationale": "通話目的の確認事項について明確な回答を取得できた"
  },
  "collected_data": {
    "available_date": "来週月曜日 午前中",
    "contact_preference": "電話"
  }
}
```

---

## Twilio Subaccount 管理 API

### テナント用 Subaccount 作成

```python
from twilio.rest import Client

master_client = Client(
    os.getenv("TWILIO_ACCOUNT_SID"),
    os.getenv("TWILIO_AUTH_TOKEN"),
)

# Subaccount creation
subaccount = master_client.api.accounts.create(
    friendly_name=f"TAM-tenant-{tenant_id}"
)
# subaccount.sid  → Subaccount SID
# subaccount.auth_token → Subaccount Auth Token
```

### テナント用電話番号の購入

```python
sub_client = Client(subaccount.sid, subaccount.auth_token)

# Available numbers search (Japan)
available = sub_client.available_phone_numbers("JP").local.list(limit=1)

# Purchase
number = sub_client.incoming_phone_numbers.create(
    phone_number=available[0].phone_number,
    friendly_name=f"TAM-tenant-{tenant_id}-outbound",
)
```

### ElevenLabs への電話番号登録

ElevenLabs ダッシュボードまたは API で、購入した Twilio 番号を登録する:
- Phone Number: 購入した番号
- Twilio SID: Subaccount の SID
- Twilio Token: Subaccount の Auth Token

---

## 音声設定ガイドライン

### 日本語通話向け推奨設定

| 項目 | 推奨値 | 理由 |
|------|--------|------|
| TTS Model | `eleven_flash_v2` | 低レイテンシ（電話会話に必須） |
| ASR Quality | `high` | 日本語の認識精度向上 |
| ASR Format | `ulaw_8000` | Twilio の標準オーディオ形式 |
| Voice | ビジネス向け日本語音声を選択 | 自然で信頼感のある応対 |
| Max Duration | 300秒（5分） | コスト管理 + タイムアウト防止 |

### 会話品質基準

- **応答レイテンシ**: 1秒以内（`eleven_flash_v2` で達成可能）
- **認識精度**: 日本語固有名詞は `keywords` パラメータでブースト
- **自然さ**: 相槌（「はい」「承知しました」）を system prompt に明記
- **エラーハンドリング**: 聞き取れなかった場合の再確認フロー

---

## セキュリティ要件

1. **認証情報の管理**: Twilio SID / Auth Token / ElevenLabs API Key はすべて環境変数経由。ハードコード禁止
2. **テナント分離**: Subaccount 間のデータアクセスは Twilio が構造的に防止
3. **通話録音**: テナントの同意を取得した上で有効化。録音データは暗号化保存
4. **個人情報保護**: 通話内容の文字起こしデータは適切な保持期間後に削除
5. **発信元表示**: 正規の Twilio 番号からのみ発信（スパム防止）

---

## コスト構造

| 項目 | 料金目安 | 課金単位 |
|------|---------|---------|
| Twilio 電話番号（日本） | ¥150/月 | 番号あたり |
| Twilio 発信（日本固定） | ¥3〜5/分 | 通話時間 |
| Twilio 発信（日本携帯） | ¥15〜20/分 | 通話時間 |
| ElevenLabs TTS | $0.30/1K文字 (Scale) | 生成文字数 |
| ElevenLabs Conversational AI | 分課金（プランによる） | 通話時間 |

**5分の通話コスト概算**: ¥100〜200（固定電話）/ ¥200〜400（携帯電話）+ ElevenLabs 分課金
