"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useOrganization } from "@/lib/organization";

const links = [
  ["/development", "ダッシュボード"], ["/development/projects", "案件"], ["/development/estimates", "見積"],
  ["/development/contracts", "契約"], ["/development/payments", "Mock決済"], ["/development/artifacts", "成果物"],
  ["/development/reviews", "レビュー"], ["/development/chat", "チャット"], ["/development/change-requests", "修正依頼"],
  ["/development/notifications", "通知"], ["/development/ai-settings", "AI設定"], ["/development/maintenance", "保守"],
  ["/development/users", "組織管理"], ["/development/audit-logs", "監査ログ"], ["/development/dead-letters", "Dead letter"],
];

type LocalUser = { id: string; display_name: string; email: string };

export function Shell({ children, title }: { children: ReactNode; title: string }) {
  const path = usePathname();
  const router = useRouter();
  const { me, organizationId, switchOrganization } = useOrganization();
  const localAuthEnabled = process.env.NEXT_PUBLIC_LOCAL_AUTH_ENABLED === "true";
  const [localUsers, setLocalUsers] = useState<LocalUser[]>([]);
  const [switchingUser, setSwitchingUser] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!localAuthEnabled) return;
    api<LocalUser[]>("/auth/local/users").then(setLocalUsers).catch((value) => setError(value.message));
  }, [localAuthEnabled]);

  async function switchUser(userId: string) {
    if (!userId || userId === me?.id) return;
    setSwitchingUser(true);
    setError("");
    try {
      await api("/auth/local/login", {
        method: "POST",
        body: JSON.stringify({ user_id: userId }),
      });
      sessionStorage.clear();
      window.location.assign("/");
    } catch (value) {
      setError((value as Error).message);
      setSwitchingUser(false);
    }
  }

  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
      sessionStorage.clear();
      router.push("/login");
    } catch (value) {
      setError((value as Error).message);
    }
  }

  return <div className="layout">
    <a className="skip" href="#main">本文へ移動</a>
    <header>
      <div><strong>SystemNavigator AI</strong><small>AIと人が、システム開発を完成までナビゲート。</small></div>
      <div className="headerActions">
        <Link aria-label="通知" href="/notifications">🔔</Link>
        {localAuthEnabled && <select
          aria-label="テストユーザー切替"
          value={me?.id || ""}
          disabled={switchingUser || !me}
          onChange={(event) => switchUser(event.target.value)}
        >
          {!me && <option value="">読み込み中</option>}
          {localUsers.map((user) => <option key={user.id} value={user.id}>
            {user.display_name} ({user.email})
          </option>)}
        </select>}
        <select aria-label="組織切替" value={organizationId} onChange={(event) => switchOrganization(event.target.value).catch((value) => setError(value.message))}>
          {me?.organizations.map((organization) => <option key={organization.id} value={organization.id}>{organization.name}</option>)}
        </select>
        <span>{switchingUser ? "切替中…" : me?.display_name}</span>
        <button onClick={logout}>ログアウト</button>
      </div>
    </header>
    <aside aria-label="メインナビゲーション">
      {links.map(([href, label]) => <Link className={path === href ? "active" : ""} key={href} href={href}>{label}</Link>)}
    </aside>
    <main id="main">
      <nav aria-label="パンくず">ホーム / {title}</nav>
      {error && <div role="alert" className="error">{error}</div>}
      <h1>{title}</h1>
      {children}
    </main>
  </div>;
}
