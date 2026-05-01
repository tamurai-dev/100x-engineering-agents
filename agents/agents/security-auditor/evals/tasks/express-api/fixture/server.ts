import express from "express";
import cors from "cors";
import { pool } from "./db";
import { createToken, SECRET } from "./auth";

const app = express();
app.use(express.json());
app.use(cors({ origin: "*" }));

// ユーザー取得
app.get("/api/users/:id", async (req, res) => {
  const query = `SELECT * FROM users WHERE id = ${req.params.id}`;
  const result = await pool.query(query);
  res.json(result.rows[0]);
});

// ログイン
app.post("/api/login", async (req, res) => {
  const { username, password } = req.body;
  const query = `SELECT * FROM users WHERE username = '${username}' AND password = '${password}'`;
  const result = await pool.query(query);

  if (result.rows.length > 0) {
    const token = createToken(result.rows[0]);
    res.json({ token, user: result.rows[0] });
  } else {
    res.status(401).json({ error: "Invalid credentials" });
  }
});

// プロフィール画像取得
app.get("/api/avatar", async (req, res) => {
  const imageUrl = req.query.url as string;
  const response = await fetch(imageUrl);
  const buffer = await response.arrayBuffer();
  res.send(Buffer.from(buffer));
});

// エラーハンドラ
app.use((err: Error, req: express.Request, res: express.Response, next: express.NextFunction) => {
  console.error("Error:", err.message, err.stack);
  res.status(500).json({ error: err.message, stack: err.stack });
});

app.listen(3000);
