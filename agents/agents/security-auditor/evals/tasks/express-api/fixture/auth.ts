import jwt from "jsonwebtoken";

export const SECRET = "jwt-secret-do-not-change-2024";

interface User {
  id: number;
  username: string;
  role: string;
}

export function createToken(user: User): string {
  return jwt.sign({ id: user.id, username: user.username, role: user.role }, SECRET);
}

export function verifyToken(token: string): User | null {
  try {
    return jwt.verify(token, SECRET) as User;
  } catch {
    return null;
  }
}

export function comparePassword(input: string, stored: string): boolean {
  return input === stored;
}
