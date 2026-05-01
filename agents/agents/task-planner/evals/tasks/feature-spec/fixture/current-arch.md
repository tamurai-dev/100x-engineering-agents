# 現在のアーキテクチャ概要

## ディレクトリ構造

```
src/
├── routes/          # Express ルートハンドラ
│   ├── auth.ts      # POST /api/auth/login, /api/auth/register
│   ├── users.ts     # CRUD /api/users
│   └── orders.ts    # CRUD /api/orders
├── middleware/
│   ├── auth.ts      # JWT 認証ミドルウェア
│   └── validation.ts
├── models/          # Sequelize ORM モデル
│   ├── User.ts
│   ├── Order.ts
│   └── index.ts
├── services/        # ビジネスロジック
│   ├── UserService.ts
│   └── OrderService.ts
├── config/
│   └── database.ts
└── app.ts           # Express アプリケーションエントリポイント
```

## データベーススキーマ（主要テーブル）

- `users`: id, username, email, password_hash, created_at
- `orders`: id, user_id, status, total, created_at

## 認証フロー

1. `POST /api/auth/login` → JWT トークン発行
2. クライアントが `Authorization: Bearer <token>` ヘッダーで API にアクセス
3. `auth.ts` ミドルウェアがトークンを検証し `req.user` にユーザー情報を設定

## 既存の Redis 使用

- セッション情報のキャッシュ（TTL: 1時間）
- レートリミット（express-rate-limit + ioredis）
