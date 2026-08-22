"use client";

import { type FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { useOrganization } from "@/lib/organization";

const writeRoles = ["organization_owner", "organization_admin", "project_manager"];

function defaultValidUntil() {
  const value = new Date();
  value.setDate(value.getDate() + 30);
  return value.toISOString().slice(0, 10);
}

export function EstimateCreateForm({ projectId, onCreated }: { projectId: string; onCreated: () => Promise<void> }) {
  const { me, organizationId } = useOrganization();
  const roles = me?.organizations.find((item) => item.id === organizationId)?.roles || [];
  const canWrite = roles.some((role) => writeRoles.includes(role));
  const [estimateNumber, setEstimateNumber] = useState(`EST-${new Date().toISOString().slice(0, 10).replaceAll("-", "")}`);
  const [validUntil, setValidUntil] = useState(defaultValidUntil);
  const [description, setDescription] = useState("要件ヒアリング・設計・開発");
  const [unitPrice, setUnitPrice] = useState("100000");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  if (!canWrite) return null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await api(`/projects/${projectId}/estimates`, {
        method: "POST",
        body: JSON.stringify({
          estimate_number: estimateNumber,
          currency: "JPY",
          valid_until: validUntil,
          items: [{
            item_type: "manual_work",
            phase: "estimate",
            description,
            quantity: "1",
            unit: "式",
            unit_price: unitPrice,
            source_type: "manual",
          }],
          include_ai_runs: false,
          include_artifacts: false,
        }),
      });
      await onCreated();
    } catch (value) {
      setError((value as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return <form className="card" onSubmit={submit}>
    <h2>見積の下書きを作成</h2>
    {error && <p role="alert" className="error">{error}</p>}
    <label htmlFor="estimate-number">見積番号</label>
    <input id="estimate-number" value={estimateNumber} onChange={(event) => setEstimateNumber(event.target.value)} required/>
    <label htmlFor="valid-until">有効期限</label>
    <input id="valid-until" type="date" value={validUntil} onChange={(event) => setValidUntil(event.target.value)} required/>
    <label htmlFor="estimate-description">明細</label>
    <input id="estimate-description" value={description} onChange={(event) => setDescription(event.target.value)} required/>
    <label htmlFor="unit-price">金額（税抜・円）</label>
    <input id="unit-price" type="number" min="0" step="1" value={unitPrice} onChange={(event) => setUnitPrice(event.target.value)} required/>
    <button disabled={submitting}>{submitting ? "作成中…" : "下書きを作成"}</button>
  </form>;
}
