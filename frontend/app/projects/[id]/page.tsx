"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Shell } from "@/components/Shell";
import { AsyncState } from "@/components/AsyncState";
import { api } from "@/lib/api";
import type { ApiRecord, CursorPage } from "@/lib/contracts";
import { useOrganization } from "@/lib/organization";

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { me, organizationId } = useOrganization();
  const [project, setProject] = useState<ApiRecord>();
  const [counts, setCounts] = useState<Record<string, number | null>>({});
  const [relatedWarning, setRelatedWarning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>();
  const [startingEstimate, setStartingEstimate] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const roles = me?.organizations.find((item) => item.id === organizationId)?.roles || [];
  const canStartEstimate = roles.some((role) => ["organization_owner", "organization_admin", "project_manager"].includes(role));
  const canDelete = roles.some((role) => ["organization_owner", "organization_admin"].includes(role));

  useEffect(() => {
    sessionStorage.setItem("sn.project", id);
    setLoading(true);
    setError(undefined);
    setRelatedWarning(false);

    api<ApiRecord>(`/projects/${id}`)
      .then(async (value) => {
        setProject(value);
        const [estimates, rooms] = await Promise.allSettled([
          api<CursorPage>(`/projects/${id}/estimates`),
          api<ApiRecord[]>(`/projects/${id}/chat-rooms`),
        ]);
        setCounts({
          estimates: estimates.status === "fulfilled" ? estimates.value.items.length : null,
          chat_rooms: rooms.status === "fulfilled" ? rooms.value.length : null,
        });
        setRelatedWarning(estimates.status === "rejected" || rooms.status === "rejected");
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, [id]);

  const countText = (value: number | null | undefined) =>
    value == null ? "閲覧権限なし" : `${value}件`;

  async function startEstimate() {
    if (!project?.id || typeof project.version !== "number") return;
    setStartingEstimate(true);
    setError(undefined);
    try {
      const updated = await api<ApiRecord>(`/projects/${project.id}/start-estimate`, {
        method: "POST",
        body: JSON.stringify({ version: project.version }),
      });
      setProject(updated);
      router.push("/estimates");
    } catch (value) {
      setError(value);
      setStartingEstimate(false);
    }
  }

  async function deleteProject() {
    if (!project?.id || typeof project.version !== "number" || !window.confirm("削除しますか？")) return;
    setDeleting(true);
    setError(undefined);
    try {
      await api("/projects/" + project.id, {
        method: "DELETE",
        body: JSON.stringify({ version: project.version }),
      });
      sessionStorage.removeItem("sn.project");
      router.push("/projects");
    } catch (value) {
      setError(value);
      setDeleting(false);
    }
  }

  return <Shell title="案件詳細">
    <AsyncState loading={loading} error={error}/>
    {project && <>
      {relatedWarning && <p role="status" className="card">権限により一部の関連情報は表示されません。</p>}
      <section className="card projectDetailCard">
        {canDelete && <button className="dangerButton projectDeleteButton" disabled={deleting || startingEstimate} onClick={deleteProject}>
          {deleting ? "削除中…" : "案件を削除"}
        </button>}
        <h2>{String(project.name)}</h2>
        <dl>
          <dt>案件コード</dt><dd>{String(project.project_code)}</dd>
          <dt>状態・工程</dt><dd>{String(project.status)} / {String(project.current_phase)}</dd>
          <dt>version</dt><dd>{String(project.version)}</dd>
        </dl>
        {canStartEstimate && project.current_phase === "hearing" && <button disabled={startingEstimate || deleting} onClick={startEstimate}>
          {startingEstimate ? "見積工程へ移動中…" : "見積作成へ進む"}
        </button>}
      </section>
      <div className="grid">
        <Link href="/estimates" className="card"><h2>見積</h2><p>{countText(counts.estimates)}</p></Link>
        <section className="card"><h2>チャットルーム</h2><p>{countText(counts.chat_rooms)}</p></section>
      </div>
    </>}
  </Shell>;
}
