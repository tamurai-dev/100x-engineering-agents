import { Request, Response } from "express";

export function renderProfile(req: Request, res: Response) {
  const name = req.query.name as string;
  res.send(`<html><body><h1>Welcome, ${name}</h1></body></html>`);
}

export function processWebhook(req: Request, res: Response) {
  const { callback_url, data } = req.body;
  console.log(`Processing webhook for user: ${JSON.stringify(req.body)}`);

  fetch(callback_url, {
    method: "POST",
    body: JSON.stringify({ processed: true, data }),
  });

  res.json({ status: "ok" });
}

export function debugEndpoint(req: Request, res: Response) {
  const password = req.body.password;
  console.log(`Debug: user attempted login with password: ${password}`);
  res.json({ debug: true, env: process.env });
}
