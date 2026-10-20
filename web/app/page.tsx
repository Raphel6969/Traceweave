"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type State = "Observed" | "Inferred" | "Unknown";
type Claim = {
  subject: string;
  predicate: string;
  object: string;
  epistemic_state: State;
  confidence?: { score: number; factors: unknown };
  limitations?: string[];
  rule?: string;
  provenance?: string[];
  claim_id?: string;
};
type Event = { id?: string; event_id?: string; event_type: string; occurred_at: string; summary?: string; state?: State; source?: string; [key: string]: unknown };
type Summary = { id: string; title: string; description?: string; status?: string; progress?: { processed?: number; total?: number; status?: string } };
type CaseData = Summary & { events: Event[]; claims: Claim[]; records: unknown[]; graph?: unknown; contradictions: unknown[]; gaps: unknown[]; limitations: string[]; chain_valid?: boolean; chain_head?: string };

const empty: CaseData = { id: "", title: "No case selected", events: [], claims: [], records: [], contradictions: [], gaps: [], limitations: [] };
const arr = <T,>(value: unknown): T[] => (Array.isArray(value) ? value as T[] : []);
const badge = (state: State) => <span className={`badge ${state.toLowerCase()}`}>{state}</span>;

function request(url: string, key: string, init?: RequestInit) {
  return fetch(url, { ...init, headers: { ...(init?.headers || {}), ...(key ? { "X-API-Key": key, Authorization: `Bearer ${key}` } : {}) } }).then(async response => {
    if (!response.ok) throw Error(`${response.status} ${await response.text()}`);
    return response.status === 204 ? null : response.json();
  });
}

export default function Home() {
  const api = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
  const [key, setKey] = useState("");
  const [cases, setCases] = useState<Summary[]>([]);
  const [selected, setSelected] = useState("");
  const [current, setCurrent] = useState(empty);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  const [tab, setTab] = useState("timeline");
  const [active, setActive] = useState<Claim | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [maps, setMaps] = useState<Record<string, string>>({});
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState("");

  useEffect(() => setKey(localStorage.getItem("traceweave-api-key") || ""), []);

  const loadCases = useCallback(async () => {
    if (!api) { setLoading(false); setError("API URL is not configured. Set NEXT_PUBLIC_API_URL to connect."); return; }
    setLoading(true); setError("");
    try {
      const payload = await request(`${api}/cases`, key);
      const list = arr<Summary>(payload?.cases ?? payload);
      setCases(list);
      setSelected(value => value && list.some(item => item.id === value) ? value : list[0]?.id || "");
    } catch (reason) { setError(`Unable to load cases: ${(reason as Error).message}`); }
    finally { setLoading(false); }
  }, [api, key]);

  useEffect(() => { loadCases(); }, [loadCases]);

  const loadCase = useCallback(async (id: string) => {
    if (!id || !api) return;
    setLoading(true); setError("");
    try {
      const [detail, timeline, claims, gaps, contradictions, integrity] = await Promise.all([
        request(`${api}/cases/${id}`, key), request(`${api}/cases/${id}/timeline`, key), request(`${api}/cases/${id}/claims`, key),
        request(`${api}/cases/${id}/gaps`, key), request(`${api}/cases/${id}/contradictions`, key), request(`${api}/cases/${id}/integrity`, key),
      ]);
      const loaded = { ...detail, events: arr<Event>(timeline), claims: arr<Claim>(claims), records: arr(detail.records), gaps: arr(gaps), contradictions: arr(contradictions), limitations: arr(detail.limitations), chain_valid: integrity.verified } as CaseData;
      setCurrent(loaded); setActive(loaded.claims[0] || null);
    } catch (reason) { setCurrent(empty); setError(`Unable to hydrate case: ${(reason as Error).message}`); }
    finally { setLoading(false); }
  }, [api, key]);

  useEffect(() => { loadCase(selected); }, [selected, loadCase]);

  useEffect(() => {
    if (!selected || !api || typeof EventSource === "undefined") return;
    const query = key ? `?api_key=${encodeURIComponent(key)}` : "";
    const source = new EventSource(`${api}/cases/${selected}/progress${query}`);
    source.onmessage = event => { try { const value = JSON.parse(event.data); setProgress(`Processing: ${value.processed ?? 0}/${value.total ?? "?"} (${value.status ?? "running"})`); } catch { setProgress(event.data); } };
    source.onerror = () => source.close();
    return () => source.close();
  }, [api, selected, key]);

  const saveKey = (value: string) => { setKey(value); localStorage.setItem("traceweave-api-key", value); };
  const visible = useMemo(() => current.events.filter(event => `${event.event_type} ${event.summary || ""} ${event.source || ""}`.toLowerCase().includes(filter.toLowerCase())), [current.events, filter]);

  const upload = async (selectedFiles: File[]) => {
    if (!api || !selectedFiles.length) return;
    setUploading(true); setError("");
    const body = new FormData(); selectedFiles.forEach(file => body.append("files", file));
    const configs: Record<string, unknown> = {};
    try {
      selectedFiles.forEach(file => {
        let mapping: unknown = {};
        try { mapping = maps[file.name + "field mapping"] ? JSON.parse(maps[file.name + "field mapping"]) : {}; } catch { throw Error(`Invalid JSON field mapping for ${file.name}`); }
        configs[file.name] = { timezone: maps[file.name + "timezone"] || "UTC", known_clock_offset_seconds: Number(maps[file.name + "clock offset"] || 0), field_mappings: mapping };
      });
    } catch (reason) { setError((reason as Error).message); setUploading(false); return; }
    body.append("config", JSON.stringify(configs));
    try { const result = await request(`${api}/cases`, key, { method: "POST", body }); setProgress(`Uploaded ${result.file_count ?? selectedFiles.length} file(s); ${result.record_count ?? ""} records indexed.`); await loadCases(); setSelected(result.id); setTab("timeline"); }
    catch (reason) { setError(`Upload failed: ${(reason as Error).message}`); }
    finally { setUploading(false); }
  };

  const loadSimulator = async () => {
    if (!api) { setError("API URL is not configured. The simulator requires the backend."); return; }
    try { const result = await request(`${api}/simulator/files`, key, { method: "POST" }); await upload(arr<{ name: string; content: string }>(result.files).map(file => new File([file.content], file.name))); }
    catch (reason) { setError(`Simulator failed: ${(reason as Error).message}`); }
  };

  const deleteCase = async () => {
    if (!selected || !confirm("Delete this case and its evidence?")) return;
    try { await request(`${api}/cases/${selected}`, key, { method: "DELETE" }); setSelected(""); await loadCases(); }
    catch (reason) { setError(`Case deletion failed: ${(reason as Error).message}`); }
  };

  const reviewCount = current.claims.filter(claim => claim.epistemic_state !== "Observed").length + current.gaps.length + current.contradictions.length;
  return <main className="shell">
    <header className="topbar"><div><p className="eyebrow">TRACEWEAVE / INVESTIGATIONS</p><h1>Evidence workbench</h1></div><span className="connection"><i /> {api ? "API configured" : "API configuration required"}</span></header>
    <section className="toolbar"><label htmlFor="case">Case</label><select id="case" value={selected} onChange={event => setSelected(event.target.value)}><option value="">Select a case</option>{cases.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select><button onClick={() => setTab("upload")}>Upload evidence</button><button onClick={loadSimulator}>Load simulated attack</button>{selected && <button className="danger" onClick={deleteCase}>Delete case</button>}<button onClick={loadCases}>Retry</button><input aria-label="API key" type="password" placeholder="API key (optional)" value={key} onChange={event => saveKey(event.target.value)} /></section>
    {loading && <p className="loading" role="status">Loading case evidence…</p>}{error && <div className="error" role="alert">{error} <button onClick={loadCases}>Retry</button></div>}{progress && <p className="success" role="status">{progress}</p>}
    {!loading && !selected && !error && <section className="empty-state"><h2>No cases loaded</h2><p>Upload evidence or load a simulated attack to begin.</p></section>}
    {selected && <><section className="case-header"><div><p className="eyebrow">CASE IDENTITY</p><h2>{current.title}</h2><p>{current.description}</p></div><div className="review"><strong>{reviewCount}</strong><span>review-needed items</span></div></section>
      <nav className="tabs" aria-label="Case views">{["timeline", "claims", "findings", "graph", "integrity", "upload"].map(view => <button className={tab === view ? "active" : ""} key={view} onClick={() => setTab(view)}>{view}</button>)}</nav>
      {tab === "upload" && <section className="panel upload"><h2>Upload evidence</h2><p>Attach one or more logs with optional per-source metadata.</p><input type="file" multiple onChange={event => setFiles(Array.from(event.target.files || []))} />{files.map(file => <div className="file-row" key={file.name}><strong>{file.name}</strong>{["timezone", "clock offset", "field mapping"].map(label => <label key={label}>{label}<input placeholder={label} value={maps[file.name + label] || ""} onChange={event => setMaps({ ...maps, [file.name + label]: event.target.value })} /></label>)}</div>)}<button disabled={uploading || !files.length} onClick={() => upload(files)}>{uploading ? "Uploading…" : "Upload files"}</button></section>}
      {tab === "timeline" && <section className="panel"><div className="panel-head"><h2>Timeline</h2><span className="muted">{visible.length} of {current.events.length} · UTC</span></div><input className="search" aria-label="Filter events" placeholder="Filter events" value={filter} onChange={event => setFilter(event.target.value)} />{visible.length ? <ol className="timeline">{visible.map((event, index) => <li key={event.id || event.event_id || index}><time>{event.occurred_at}</time><h3>{event.event_type}</h3><p>{event.summary || "No event summary supplied."}</p><span className="muted">{event.source || "Source not recorded"}</span></li>)}</ol> : <p className="empty">No timeline events match this filter.</p>}</section>}
      {tab === "claims" && <section className="panel"><h2>Claims ({current.claims.length})</h2><div className="claim-list">{current.claims.map((claim, index) => <button className="claim" key={claim.claim_id || index} onClick={() => setActive(claim)}>{claim.subject} <b>{claim.predicate}</b> {String(claim.object)} {badge(claim.epistemic_state)}</button>)}</div>{active && <div className="provenance"><h3>Provenance</h3>{(active.provenance || []).map(value => <code key={value}>{value}</code>)}{active.rule && <p>Rule: {active.rule}</p>}{active.confidence && <p>Confidence: {active.confidence.score}; factors are decomposed in the report.</p>}{(active.limitations || []).map(value => <p key={value}>Limitation: {value}</p>)}</div>}</section>}
      {tab === "findings" && <section className="panel"><h2>Gaps & contradictions</h2><h3>Contradictions ({current.contradictions.length})</h3>{current.contradictions.map((value, index) => <p className="notice contradiction" key={index}>{JSON.stringify(value)}</p>)}<h3>Evidence gaps ({current.gaps.length})</h3>{current.gaps.map((value, index) => <p className="notice gap" key={index}>{JSON.stringify(value)}</p>)}<h3>Limitations ({current.limitations.length})</h3>{current.limitations.map(value => <p className="notice limitation" key={value}>{value}</p>)}</section>}
      {tab === "graph" && <section className="panel"><h2>Graph</h2><pre className="raw">{JSON.stringify(current.graph ?? null, null, 2)}</pre></section>}
      {tab === "integrity" && <section className="panel"><h2>Integrity & reports</h2><p>Chain: <strong>{current.chain_valid === true ? "verified" : current.chain_valid === false ? "failed" : "not reported"}</strong></p><p>Records: {current.records.length} · Claims: {current.claims.length}</p><code>{current.chain_head || "No chain head reported"}</code><div className="reports"><a href={`${api}/cases/${selected}/report?format=json${key ? `&api_key=${encodeURIComponent(key)}` : ""}`}>Evidence JSON ↗</a><a href={`${api}/cases/${selected}/report?format=html${key ? `&api_key=${encodeURIComponent(key)}` : ""}`}>HTML report ↗</a></div></section>}
    </>}
    <footer>TraceWeave · local-first, evidence before conclusions</footer>
  </main>;
}
