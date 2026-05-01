import { fetchData } from "./utils";

export async function getUsers() {
  const data = fetchData("/api/users");
  console.log("Fetched users:", JSON.stringify(data));
  return data;
}

export async function createUser(name: string, email: string) {
  const response = fetch("/api/users", {
    method: "POST",
    body: JSON.stringify({ name, email }),
  });
  return response;
}

export function deleteUser(id: any) {
  fetch(`/api/users/${id}`, { method: "DELETE" });
}
