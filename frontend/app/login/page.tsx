"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type LocalUser = { id: string; display_name: string; email: string };

export default function Login() {
  const localAuthEnabled = process.env.NEXT_PUBLIC_LOCAL_AUTH_ENABLED !== "false";
  const [users, setUsers] = useState<LocalUser[]>([]);
  const [id, setId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!localAuthEnabled) return;
    api<LocalUser[]>("/auth/local/users")
      .then((items) => {
        setUsers(items);
        setId(items[0]?.id || "");
      })
      .catch(() => setError("LocalAuthは利用できません"));
  }, [localAuthEnabled]);

  if (!localAuthEnabled) {
    return <main>
      <h1>SystemNavigator AI</h1>
      <p>LocalAuthはステージングでは無効です。承認済みの認証プロバイダーを使用してください。</p>
    </main>;
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      await api("/auth/local/login", { method: "POST", body: JSON.stringify({ user_id: id }) });
      // A full same-origin navigation remounts the auth provider after the HttpOnly cookie is set.
      window.location.assign("/");
    } catch {
      setError("ログインできませんでした");
    }
  }

  return <main>
    <h1>SystemNavigator AI ローカルログイン</h1>
    <p>AIと人が、システム開発を完成までナビゲート。</p>
    {error && <p role="alert" className="error">{error}</p>}
    <form onSubmit={submit}>
      <label htmlFor="user">テストユーザー</label>
      <select id="user" value={id} onChange={(event) => setId(event.target.value)}>
        {users.map((user) => <option key={user.id} value={user.id}>{user.display_name} ({user.email})</option>)}
      </select>
      <button type="submit" disabled={!id}>ログイン</button>
    </form>
  </main>;
}
