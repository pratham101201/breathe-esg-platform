import { useState, useEffect, useCallback } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell
} from "recharts";

// ── Mock data (replace with real API calls) ──────────────────────────────────
const MOCK_SUMMARY = {
  total_records: 142,
  pending: 38,
  suspicious: 12,
  scope_totals: [
    { scope: 1, total_kgco2e: 284500, count: 48 },
    { scope: 2, total_kgco2e: 163200, count: 61 },
    { scope: 3, total_kgco2e: 42800,  count: 33 },
  ],
  status_counts: [
    { status: "PENDING",  count: 38 },
    { status: "FLAGGED",  count: 12 },
    { status: "APPROVED", count: 74 },
    { status: "LOCKED",   count: 18 },
  ],
};

const MOCK_RECORDS = [
  { id:"r1", facility_name:"Pune Plant (IN01)", scope:1, category:"FUEL",        activity_value:"5000", activity_unit:"L",     kgco2e:"13400.00", period_start:"2024-04-01", period_end:"2024-04-30", status:"PENDING",  is_suspicious:false, is_edited:false },
  { id:"r2", facility_name:"Mumbai Office",     scope:2, category:"ELECTRICITY", activity_value:"48500",activity_unit:"kWh",   kgco2e:"39770.00", period_start:"2024-04-01", period_end:"2024-04-30", status:"FLAGGED",  is_suspicious:true,  is_edited:false },
  { id:"r3", facility_name:"Pune Plant (IN01)", scope:3, category:"TRAVEL",      activity_value:"1148", activity_unit:"km",    kgco2e:"293.74",   period_start:"2024-04-03", period_end:"2024-04-05", status:"APPROVED", is_suspicious:false, is_edited:true  },
  { id:"r4", facility_name:"Delhi Office",      scope:2, category:"ELECTRICITY", activity_value:"12300",activity_unit:"kWh",   kgco2e:"10086.00", period_start:"2024-04-01", period_end:"2024-04-30", status:"LOCKED",   is_suspicious:false, is_edited:false },
  { id:"r5", facility_name:"Frankfurt (DE03)",  scope:1, category:"FUEL",        activity_value:"1200", activity_unit:"KG",    kgco2e:"3852.00",  period_start:"2024-04-10", period_end:"2024-04-12", status:"PENDING",  is_suspicious:true,  is_edited:false },
  { id:"r6", facility_name:"Mumbai Office",     scope:3, category:"TRAVEL",      activity_value:"4",    activity_unit:"nights",kgco2e:"82.40",    period_start:"2024-04-10", period_end:"2024-04-14", status:"PENDING",  is_suspicious:false, is_edited:false },
  { id:"r7", facility_name:"Pune Plant (IN01)", scope:1, category:"FUEL",        activity_value:"200",  activity_unit:"GAL",   kgco2e:"1753.80",  period_start:"2024-04-05", period_end:"2024-04-08", status:"FLAGGED",  is_suspicious:true,  is_edited:false },
  { id:"r8", facility_name:"Bangalore Hub",     scope:3, category:"TRAVEL",      activity_value:"9320", activity_unit:"km",    kgco2e:"3630.90",  period_start:"2024-04-10", period_end:"2024-04-14", status:"APPROVED", is_suspicious:false, is_edited:true  },
];

const MOCK_BATCHES = [
  { id:"b1", source_name:"SAP Production",     source_type:"SAP",     uploaded_by_name:"Rahul Mehta",  uploaded_at:"2024-04-15T09:32:00Z", filename:"ME2M_APR2024.csv",       status:"DONE",    row_count:48, error_count:2  },
  { id:"b2", source_name:"MSEDCL Portal",      source_type:"UTILITY", uploaded_by_name:"Anita Desai",  uploaded_at:"2024-04-16T11:05:00Z", filename:"MSEDCL_APR2024.csv",     status:"DONE",    row_count:61, error_count:0  },
  { id:"b3", source_name:"Concur Travel",      source_type:"TRAVEL",  uploaded_by_name:"Vikram Nair",  uploaded_at:"2024-04-17T14:22:00Z", filename:"concur_q1_2024.csv",     status:"DONE",    row_count:33, error_count:3  },
  { id:"b4", source_name:"SAP Production",     source_type:"SAP",     uploaded_by_name:"Rahul Mehta",  uploaded_at:"2024-04-18T08:10:00Z", filename:"MB51_APR2024.csv",       status:"FAILED",  row_count:12, error_count:12 },
];

// ── Design tokens ─────────────────────────────────────────────────────────────
const T = {
  scope1: "#C04828", scope2: "#185FA5", scope3: "#0F6E56",
  pending: "#BA7517", flagged: "#A32D2D", approved: "#3B6D11", locked: "#534AB7",
  bg: "#F8F7F4", card: "#FFFFFF", border: "#E2E0D8",
  text: "#1A1A18", muted: "#6B6A63", accent: "#185FA5",
};

const SCOPE_COLOR = { 1: T.scope1, 2: T.scope2, 3: T.scope3 };
const STATUS_COLOR = { PENDING: T.pending, FLAGGED: T.flagged, APPROVED: T.approved, LOCKED: T.locked };
const STATUS_BG = {
  PENDING:  "#FAEEDA", FLAGGED: "#FCEBEB", APPROVED: "#EAF3DE", LOCKED: "#EEEDFE"
};

const fmt = (n) => Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const fmtCO2 = (n) => {
  const v = Number(n);
  return v >= 1000 ? `${(v/1000).toFixed(1)} tCO₂e` : `${Math.round(v)} kgCO₂e`;
};

// ── Components ────────────────────────────────────────────────────────────────

function StatusPill({ status }) {
  return (
    <span style={{
      background: STATUS_BG[status] || "#eee",
      color: STATUS_COLOR[status] || T.muted,
      fontSize: 11, fontWeight: 600, letterSpacing: "0.04em",
      padding: "2px 8px", borderRadius: 20,
      textTransform: "uppercase", whiteSpace: "nowrap",
    }}>{status}</span>
  );
}

function ScopeBadge({ scope }) {
  const colors = { 1: { bg:"#FAECE7", fg: T.scope1 }, 2: { bg:"#E6F1FB", fg: T.scope2 }, 3: { bg:"#E1F5EE", fg: T.scope3 } };
  const c = colors[scope] || colors[1];
  return (
    <span style={{
      background: c.bg, color: c.fg,
      fontSize: 11, fontWeight: 700, padding: "2px 7px",
      borderRadius: 20, whiteSpace: "nowrap",
    }}>S{scope}</span>
  );
}

function Card({ children, style = {} }) {
  return (
    <div style={{
      background: T.card, border: `1px solid ${T.border}`,
      borderRadius: 12, padding: "20px 24px", ...style
    }}>{children}</div>
  );
}

function MetricCard({ label, value, sub, color }) {
  return (
    <Card style={{ flex: 1, minWidth: 160 }}>
      <div style={{ color: T.muted, fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color: color || T.text, lineHeight: 1.1 }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: T.muted, marginTop: 4 }}>{sub}</div>}
    </Card>
  );
}

function ActionBtn({ label, color, onClick, disabled }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      background: disabled ? "#eee" : color,
      color: disabled ? T.muted : "#fff",
      border: "none", borderRadius: 6, padding: "5px 12px",
      fontSize: 12, fontWeight: 600, cursor: disabled ? "not-allowed" : "pointer",
      transition: "opacity .15s",
    }}
    onMouseOver={e => !disabled && (e.target.style.opacity = "0.85")}
    onMouseOut={e => (e.target.style.opacity = "1")}
    >{label}</button>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export default function AnalystDashboard() {
  const [tab, setTab]               = useState("records");
  const [records, setRecords]       = useState(MOCK_RECORDS);
  const [filterStatus, setFilterStatus] = useState("ALL");
  const [filterScope, setFilterScope]   = useState("ALL");
  const [filterSus, setFilterSus]       = useState(false);
  const [search, setSearch]             = useState("");
  const [selected, setSelected]         = useState(null);
  const [flagNote, setFlagNote]         = useState("");
  const [toast, setToast]               = useState(null);

  const showToast = (msg, ok = true) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3000);
  };

  const updateRecord = useCallback((id, patch) => {
    setRecords(rs => rs.map(r => r.id === id ? { ...r, ...patch } : r));
    if (selected?.id === id) setSelected(s => ({ ...s, ...patch }));
  }, [selected]);

  const approve = (id) => {
    updateRecord(id, { status: "APPROVED" });
    showToast("Record approved ✓");
  };
  const flag = (id) => {
    if (!flagNote.trim()) { showToast("Add a note before flagging", false); return; }
    updateRecord(id, { status: "FLAGGED", is_suspicious: true });
    setFlagNote("");
    showToast("Record flagged");
  };
  const lock = (id) => {
    const r = records.find(r => r.id === id);
    if (r?.status !== "APPROVED") { showToast("Only approved records can be locked", false); return; }
    updateRecord(id, { status: "LOCKED" });
    showToast("Record locked for audit ✓");
  };

  const filtered = records.filter(r => {
    if (filterStatus !== "ALL" && r.status !== filterStatus) return false;
    if (filterScope !== "ALL" && String(r.scope) !== filterScope) return false;
    if (filterSus && !r.is_suspicious) return false;
    if (search && !r.facility_name.toLowerCase().includes(search.toLowerCase()) &&
        !r.category.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const totalCO2 = records.reduce((s, r) => s + Number(r.kgco2e), 0);

  return (
    <div style={{ fontFamily: "'DM Sans', 'Segoe UI', sans-serif", background: T.bg, minHeight: "100vh", color: T.text }}>
      {/* Header */}
      <div style={{ background: T.card, borderBottom: `1px solid ${T.border}`, padding: "0 32px" }}>
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", height: 56 }}>
          <div style={{ display:"flex", alignItems:"center", gap: 10 }}>
            <div style={{ width: 28, height: 28, background: "#1A4D2E", borderRadius: 8, display:"flex", alignItems:"center", justifyContent:"center" }}>
              <span style={{ color:"#7ED99A", fontSize: 14, fontWeight: 800 }}>B</span>
            </div>
            <span style={{ fontWeight: 700, fontSize: 16, letterSpacing:"-0.02em" }}>Breathe ESG</span>
            <span style={{ color: T.muted, fontSize: 13, marginLeft: 4 }}>/ Analyst Dashboard</span>
          </div>
          <div style={{ display:"flex", gap: 6 }}>
            {["records","batches","summary"].map(t => (
              <button key={t} onClick={() => setTab(t)} style={{
                background: tab === t ? "#EAF3DE" : "transparent",
                color: tab === t ? T.approved : T.muted,
                border: "none", borderRadius: 6, padding: "6px 14px",
                fontSize: 13, fontWeight: 600, cursor: "pointer",
                textTransform: "capitalize",
              }}>{t}</button>
            ))}
          </div>
          <div style={{ background:"#E8F5F0", color:"#1A4D2E", fontSize:12, fontWeight:600, padding:"4px 12px", borderRadius:20 }}>
            ACME Manufacturing · FY2024
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 1280, margin: "0 auto", padding: "28px 32px" }}>

        {/* Toast */}
        {toast && (
          <div style={{
            position:"fixed", top:20, right:24, zIndex:999,
            background: toast.ok ? "#3B6D11" : "#A32D2D",
            color:"#fff", borderRadius:8, padding:"10px 18px",
            fontSize:13, fontWeight:600, boxShadow:"0 4px 16px rgba(0,0,0,.15)",
            animation: "fadeIn .2s ease",
          }}>{toast.msg}</div>
        )}

        {/* ── RECORDS TAB ── */}
        {tab === "records" && (
          <div style={{ display:"flex", gap: 24 }}>
            {/* Left: list */}
            <div style={{ flex: 1, minWidth: 0 }}>
              {/* Filters */}
              <div style={{ display:"flex", gap: 8, marginBottom: 16, flexWrap:"wrap", alignItems:"center" }}>
                <input
                  placeholder="Search facility or category…"
                  value={search} onChange={e => setSearch(e.target.value)}
                  style={{ padding:"7px 12px", border:`1px solid ${T.border}`, borderRadius:8, fontSize:13, flex:1, minWidth:160, outline:"none" }}
                />
                <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
                  style={{ padding:"7px 10px", border:`1px solid ${T.border}`, borderRadius:8, fontSize:12, cursor:"pointer" }}>
                  <option value="ALL">All statuses</option>
                  {["PENDING","FLAGGED","APPROVED","LOCKED"].map(s => <option key={s}>{s}</option>)}
                </select>
                <select value={filterScope} onChange={e => setFilterScope(e.target.value)}
                  style={{ padding:"7px 10px", border:`1px solid ${T.border}`, borderRadius:8, fontSize:12, cursor:"pointer" }}>
                  <option value="ALL">All scopes</option>
                  <option value="1">Scope 1</option>
                  <option value="2">Scope 2</option>
                  <option value="3">Scope 3</option>
                </select>
                <button onClick={() => setFilterSus(f => !f)} style={{
                  padding:"7px 12px", borderRadius:8, fontSize:12, fontWeight:600,
                  border:`1.5px solid ${filterSus ? T.flagged : T.border}`,
                  background: filterSus ? "#FCEBEB" : T.card,
                  color: filterSus ? T.flagged : T.muted, cursor:"pointer",
                }}>⚠ Suspicious only</button>
                <span style={{ color:T.muted, fontSize:12, marginLeft:4 }}>{filtered.length} records</span>
              </div>

              {/* Table */}
              <Card style={{ padding:0, overflow:"hidden" }}>
                <table style={{ width:"100%", borderCollapse:"collapse", fontSize:13 }}>
                  <thead>
                    <tr style={{ background:"#F4F3EF", borderBottom:`1px solid ${T.border}` }}>
                      {["Scope","Category","Facility","Activity","CO₂e","Period","Status",""].map(h => (
                        <th key={h} style={{ padding:"10px 14px", textAlign:"left", fontSize:11, fontWeight:700, color:T.muted, textTransform:"uppercase", letterSpacing:"0.04em", whiteSpace:"nowrap" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((r, i) => (
                      <tr key={r.id}
                        onClick={() => setSelected(r)}
                        style={{
                          background: selected?.id === r.id ? "#EFF6FF" : i%2===0 ? T.card : "#FAFAF8",
                          borderBottom:`1px solid ${T.border}`,
                          cursor:"pointer", transition:"background .1s",
                        }}
                        onMouseOver={e => e.currentTarget.style.background = "#F0F5FF"}
                        onMouseOut={e => e.currentTarget.style.background = selected?.id === r.id ? "#EFF6FF" : i%2===0 ? T.card : "#FAFAF8"}
                      >
                        <td style={{ padding:"10px 14px" }}><ScopeBadge scope={r.scope}/></td>
                        <td style={{ padding:"10px 14px", color:T.muted, fontSize:12 }}>{r.category}</td>
                        <td style={{ padding:"10px 14px", fontWeight:500 }}>
                          {r.facility_name}
                          {r.is_suspicious && <span style={{ marginLeft:6, color:T.flagged, fontSize:11 }}>⚠</span>}
                          {r.is_edited && <span style={{ marginLeft:4, color:T.muted, fontSize:10 }}>✎</span>}
                        </td>
                        <td style={{ padding:"10px 14px", fontVariantNumeric:"tabular-nums" }}>{fmt(r.activity_value)} {r.activity_unit}</td>
                        <td style={{ padding:"10px 14px", fontWeight:600, fontVariantNumeric:"tabular-nums" }}>{fmtCO2(r.kgco2e)}</td>
                        <td style={{ padding:"10px 14px", color:T.muted, fontSize:12, whiteSpace:"nowrap" }}>{r.period_start.slice(0,7)}</td>
                        <td style={{ padding:"10px 14px" }}><StatusPill status={r.status}/></td>
                        <td style={{ padding:"10px 14px" }}>
                          <div style={{ display:"flex", gap:4 }}>
                            {r.status === "PENDING" && <ActionBtn label="Approve" color={T.approved} onClick={e => { e.stopPropagation(); approve(r.id); }}/>}
                            {r.status === "APPROVED" && <ActionBtn label="Lock" color={T.locked} onClick={e => { e.stopPropagation(); lock(r.id); }}/>}
                          </div>
                        </td>
                      </tr>
                    ))}
                    {filtered.length === 0 && (
                      <tr><td colSpan={8} style={{ padding:"40px", textAlign:"center", color:T.muted }}>No records match the current filters.</td></tr>
                    )}
                  </tbody>
                </table>
              </Card>
            </div>

            {/* Right: detail panel */}
            {selected && (
              <div style={{ width: 340, flexShrink:0 }}>
                <Card style={{ position:"sticky", top:20 }}>
                  <div style={{ display:"flex", justifyContent:"space-between", alignItems:"start", marginBottom:16 }}>
                    <div>
                      <div style={{ fontSize:11, fontWeight:700, color:T.muted, textTransform:"uppercase", letterSpacing:"0.05em", marginBottom:4 }}>Record detail</div>
                      <div style={{ fontWeight:700, fontSize:15 }}>{selected.facility_name}</div>
                    </div>
                    <button onClick={() => setSelected(null)} style={{ background:"none", border:"none", cursor:"pointer", color:T.muted, fontSize:18 }}>×</button>
                  </div>

                  <div style={{ display:"flex", gap:8, marginBottom:16, flexWrap:"wrap" }}>
                    <ScopeBadge scope={selected.scope}/>
                    <StatusPill status={selected.status}/>
                    {selected.is_edited && <span style={{ fontSize:11, color:T.muted, background:"#F0F0EC", padding:"2px 8px", borderRadius:20 }}>Edited</span>}
                  </div>

                  {[
                    ["Category", selected.category],
                    ["Activity", `${fmt(selected.activity_value)} ${selected.activity_unit}`],
                    ["Emissions", fmtCO2(selected.kgco2e)],
                    ["Period", `${selected.period_start} → ${selected.period_end}`],
                  ].map(([k,v]) => (
                    <div key={k} style={{ display:"flex", justifyContent:"space-between", padding:"7px 0", borderBottom:`1px solid ${T.border}`, fontSize:13 }}>
                      <span style={{ color:T.muted }}>{k}</span>
                      <span style={{ fontWeight:500 }}>{v}</span>
                    </div>
                  ))}

                  {selected.is_suspicious && (
                    <div style={{ background:"#FCEBEB", border:`1px solid #F7C1C1`, borderRadius:8, padding:"10px 12px", marginTop:14, fontSize:12 }}>
                      <div style={{ fontWeight:700, color:T.flagged, marginBottom:4 }}>⚠ Suspicious</div>
                      <div style={{ color:"#791F1F" }}>No receipt · High amount detected</div>
                    </div>
                  )}

                  {/* Actions */}
                  {selected.status !== "LOCKED" && (
                    <div style={{ marginTop:16 }}>
                      <div style={{ display:"flex", gap:8, marginBottom:10 }}>
                        {selected.status === "PENDING" && (
                          <ActionBtn label="Approve" color={T.approved} onClick={() => approve(selected.id)}/>
                        )}
                        {selected.status === "APPROVED" && (
                          <ActionBtn label="Lock for audit" color={T.locked} onClick={() => lock(selected.id)}/>
                        )}
                      </div>
                      <div style={{ fontSize:12, color:T.muted, marginBottom:6, fontWeight:600 }}>Flag with note</div>
                      <textarea
                        value={flagNote} onChange={e => setFlagNote(e.target.value)}
                        placeholder="Describe the issue…"
                        style={{ width:"100%", height:64, border:`1px solid ${T.border}`, borderRadius:8, padding:"8px 10px", fontSize:12, resize:"vertical", outline:"none", fontFamily:"inherit", boxSizing:"border-box" }}
                      />
                      <ActionBtn label="Flag record" color={T.flagged} onClick={() => flag(selected.id)}/>
                    </div>
                  )}
                  {selected.status === "LOCKED" && (
                    <div style={{ marginTop:14, background:"#EEEDFE", borderRadius:8, padding:"10px 12px", fontSize:12, color:"#3C3489" }}>
                      🔒 This record is locked for audit. No further edits allowed.
                    </div>
                  )}
                </Card>
              </div>
            )}
          </div>
        )}

        {/* ── BATCHES TAB ── */}
        {tab === "batches" && (
          <div>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:20 }}>
              <h2 style={{ fontSize:18, fontWeight:700, margin:0 }}>Ingestion batches</h2>
              <button style={{
                background:T.accent, color:"#fff", border:"none", borderRadius:8,
                padding:"8px 16px", fontSize:13, fontWeight:600, cursor:"pointer",
              }}>+ Upload file</button>
            </div>
            <Card style={{ padding:0 }}>
              <table style={{ width:"100%", borderCollapse:"collapse", fontSize:13 }}>
                <thead>
                  <tr style={{ background:"#F4F3EF", borderBottom:`1px solid ${T.border}` }}>
                    {["Source","Type","File","Uploaded by","Date","Rows","Errors","Status"].map(h => (
                      <th key={h} style={{ padding:"10px 16px", textAlign:"left", fontSize:11, fontWeight:700, color:T.muted, textTransform:"uppercase", letterSpacing:"0.04em" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {MOCK_BATCHES.map((b,i) => (
                    <tr key={b.id} style={{ background: i%2===0?T.card:"#FAFAF8", borderBottom:`1px solid ${T.border}` }}>
                      <td style={{ padding:"12px 16px", fontWeight:500 }}>{b.source_name}</td>
                      <td style={{ padding:"12px 16px" }}>
                        <span style={{ background: b.source_type==="SAP"?"#FAECE7":b.source_type==="UTILITY"?"#E6F1FB":"#E1F5EE", color: b.source_type==="SAP"?T.scope1:b.source_type==="UTILITY"?T.scope2:T.scope3, fontSize:11, fontWeight:700, padding:"2px 8px", borderRadius:20 }}>{b.source_type}</span>
                      </td>
                      <td style={{ padding:"12px 16px", color:T.muted, fontFamily:"monospace", fontSize:12 }}>{b.filename}</td>
                      <td style={{ padding:"12px 16px" }}>{b.uploaded_by_name}</td>
                      <td style={{ padding:"12px 16px", color:T.muted, fontSize:12 }}>{new Date(b.uploaded_at).toLocaleDateString("en-IN")}</td>
                      <td style={{ padding:"12px 16px", fontVariantNumeric:"tabular-nums" }}>{b.row_count}</td>
                      <td style={{ padding:"12px 16px", color: b.error_count>0?T.flagged:T.approved, fontWeight:600 }}>{b.error_count}</td>
                      <td style={{ padding:"12px 16px" }}>
                        <StatusPill status={b.status==="DONE"?"APPROVED":b.status==="FAILED"?"FLAGGED":"PENDING"}/>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>
        )}

        {/* ── SUMMARY TAB ── */}
        {tab === "summary" && (
          <div>
            <h2 style={{ fontSize:18, fontWeight:700, marginBottom:20 }}>Emissions summary — FY2024 Q1</h2>

            {/* Metric cards */}
            <div style={{ display:"flex", gap:16, marginBottom:24, flexWrap:"wrap" }}>
              <MetricCard label="Total CO₂e" value={fmtCO2(totalCO2)} sub="All scopes, approved + locked" color={T.text}/>
              <MetricCard label="Pending review" value={MOCK_SUMMARY.pending} sub="Records awaiting analyst action" color={T.pending}/>
              <MetricCard label="Suspicious" value={MOCK_SUMMARY.suspicious} sub="Anomalies detected on ingest" color={T.flagged}/>
              <MetricCard label="Locked for audit" value={MOCK_SUMMARY.status_counts.find(s=>s.status==="LOCKED")?.count||0} sub="Immutable, sent to auditors" color={T.locked}/>
            </div>

            <div style={{ display:"flex", gap:20, flexWrap:"wrap" }}>
              {/* Scope breakdown chart */}
              <Card style={{ flex:2, minWidth:300 }}>
                <div style={{ fontWeight:700, fontSize:14, marginBottom:16 }}>Emissions by scope (tCO₂e)</div>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={MOCK_SUMMARY.scope_totals} barSize={48}>
                    <XAxis dataKey="scope" tickFormatter={s => `Scope ${s}`} tick={{ fontSize:12, fill:T.muted }}/>
                    <YAxis tickFormatter={v => `${(v/1000).toFixed(0)}t`} tick={{ fontSize:11, fill:T.muted }} width={40}/>
                    <Tooltip formatter={(v) => [`${(v/1000).toFixed(1)} tCO₂e`]} labelFormatter={l => `Scope ${l}`}/>
                    <Bar dataKey="total_kgco2e" radius={[6,6,0,0]}>
                      {MOCK_SUMMARY.scope_totals.map(e => <Cell key={e.scope} fill={SCOPE_COLOR[e.scope]}/>)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </Card>

              {/* Status breakdown */}
              <Card style={{ flex:1, minWidth:200 }}>
                <div style={{ fontWeight:700, fontSize:14, marginBottom:16 }}>Records by status</div>
                {MOCK_SUMMARY.status_counts.map(s => (
                  <div key={s.status} style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:12 }}>
                    <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                      <div style={{ width:10, height:10, borderRadius:3, background:STATUS_COLOR[s.status] }}/>
                      <span style={{ fontSize:13 }}>{s.status}</span>
                    </div>
                    <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                      <div style={{ width:80, height:6, background:"#F0EFE9", borderRadius:3, overflow:"hidden" }}>
                        <div style={{ width:`${(s.count/142)*100}%`, height:"100%", background:STATUS_COLOR[s.status], borderRadius:3 }}/>
                      </div>
                      <span style={{ fontSize:13, fontWeight:700, minWidth:24, textAlign:"right" }}>{s.count}</span>
                    </div>
                  </div>
                ))}

                <div style={{ marginTop:20, paddingTop:16, borderTop:`1px solid ${T.border}` }}>
                  <div style={{ fontWeight:700, fontSize:14, marginBottom:12 }}>Scope totals</div>
                  {MOCK_SUMMARY.scope_totals.map(s => (
                    <div key={s.scope} style={{ display:"flex", justifyContent:"space-between", fontSize:13, marginBottom:8 }}>
                      <div style={{ display:"flex", gap:6, alignItems:"center" }}>
                        <ScopeBadge scope={s.scope}/>
                      </div>
                      <span style={{ fontWeight:600 }}>{fmtCO2(s.total_kgco2e)}</span>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          </div>
        )}
      </div>

      <style>{`
        @keyframes fadeIn { from { opacity:0; transform:translateY(-8px); } to { opacity:1; transform:translateY(0); } }
        * { box-sizing: border-box; }
        select, input { background: white; }
      `}</style>
    </div>
  );
}
