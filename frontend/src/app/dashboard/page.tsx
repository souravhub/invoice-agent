"use client";

import Link from "next/link";
import { ReactNode, useEffect, useState } from "react";
import { onAuthStateChanged, signOut, User } from "firebase/auth";

import { ApiTimestamp, InvoiceResult, isBatchResult, listInvoices, listPurchaseOrders, SavedPurchaseOrder } from "@/lib/api";
import { auth } from "@/lib/firebase";

type InvoiceRow = {
  id: string;
  recordId: string;
  batchIndex: number | null;
  fileName: string;
  createdAt: ApiTimestamp | null;
  result: InvoiceResult;
};

function Icon({ children, size = 20 }: { children: ReactNode; size?: number }) {
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{children}</svg>;
}

function InvoiceIcon({ size = 20 }: { size?: number }) {
  return <Icon size={size}><path d="M6 3h9l3 3v15H6z" /><path d="M14 3v4h4M9 11h6M9 15h6M9 19h3" /></Icon>;
}

function DashboardIcon({ size = 20 }: { size?: number }) {
  return <Icon size={size}><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" /></Icon>;
}

function money(value: number | null, currency: string | null) {
  if (value === null) return "—";
  try {
    return currency ? new Intl.NumberFormat(undefined, { style: "currency", currency }).format(value) : value.toFixed(2);
  } catch {
    return value.toFixed(2);
  }
}

function matchLabel(result: InvoiceResult) {
  const status = result.two_way_match?.status;
  if (!status) return "Not checked";
  if (status === "matched") return "Matched";
  if (status === "po_not_found") return "PO not found";
  if (status === "ambiguous_po") return "Ambiguous PO";
  if (status === "po_unavailable") return "PO unavailable";
  return "Mismatch";
}

export default function DashboardPage() {
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [invoices, setInvoices] = useState<InvoiceRow[]>([]);
  const [orders, setOrders] = useState<SavedPurchaseOrder[]>([]);
  const [invoicesLoading, setInvoicesLoading] = useState(false);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => onAuthStateChanged(auth, (nextUser) => {
    setUser(nextUser);
    setAuthReady(true);
  }), []);

  useEffect(() => {
    if (!user) return;
    setInvoicesLoading(true);
    let cancelled = false;
    listInvoices(100).then((records) => {
      const rows = records.flatMap<InvoiceRow>((saved) => {
        if (isBatchResult(saved.result)) {
          return saved.result.files.flatMap((file, index) => file.result ? [{
            id: `${saved.id}-${index}`,
            recordId: saved.id,
            batchIndex: index,
            fileName: file.filename,
            createdAt: saved.createdAt,
            result: file.result,
          }] : []);
        }
        return [{ id: saved.id, recordId: saved.id, batchIndex: null, fileName: saved.fileName, createdAt: saved.createdAt, result: saved.result }];
      });
      if (!cancelled) setInvoices(rows);
    }).catch((loadError) => {
      if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Dashboard invoice data could not be loaded.");
    }).finally(() => {
      if (!cancelled) setInvoicesLoading(false);
    });
    return () => { cancelled = true; };
  }, [user]);

  useEffect(() => {
    if (!user) return;
    setOrdersLoading(true);
    let cancelled = false;
    listPurchaseOrders(100).then((records) => {
      if (!cancelled) setOrders(records);
    }).catch((loadError) => {
      if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Dashboard purchase-order data could not be loaded.");
    }).finally(() => {
      if (!cancelled) setOrdersLoading(false);
    });
    return () => { cancelled = true; };
  }, [user]);

  if (!authReady) return <main className="review-state"><span className="spinner dark-spinner" /><p>Loading dashboard…</p></main>;
  if (!user) return <main className="review-state"><span className="review-state-icon"><DashboardIcon size={25} /></span><h1>Sign in required</h1><p>Sign in to view your invoice dashboard.</p><Link className="primary-button review-back-button" href="/">Go to sign in</Link></main>;

  const loading = invoicesLoading || ordersLoading;
  const reviewInvoices = invoices.filter((row) => row.result.status === "needs_review");
  const matchedInvoices = invoices.filter((row) => row.result.two_way_match?.status === "matched");
  const poCheckedInvoices = invoices.filter((row) => Boolean(row.result.two_way_match));
  const poExceptions = invoices.filter((row) => row.result.two_way_match && row.result.two_way_match.status !== "matched");
  const poNotChecked = invoices.length - poCheckedInvoices.length;
  const verifiedInvoices = invoices.filter((row) => row.result.status === "auto_approved");
  const openOrders = orders.filter((order) => order.status === "open");
  const closedOrders = orders.filter((order) => order.status === "closed");
  const cancelledOrders = orders.filter((order) => order.status === "cancelled");
  const matchRate = poCheckedInvoices.length ? Math.round((matchedInvoices.length / poCheckedInvoices.length) * 100) : 0;
  const attentionRows = invoices.filter((row) => row.result.status === "needs_review" || (row.result.two_way_match && row.result.two_way_match.status !== "matched")).slice(0, 5);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><InvoiceIcon size={23} /></span><span>Invoice<span className="brand-dot">.</span></span></div>
        <nav aria-label="Main navigation">
          <p className="nav-label">Workspace</p>
          <Link className="nav-item active" href="/dashboard" aria-current="page"><DashboardIcon size={19} /><span>Dashboard</span></Link>
          <Link className="nav-item" href="/"><InvoiceIcon size={19} /><span>Two way match</span></Link>
          <Link className="nav-item" href="/invoice-analyzer"><Icon size={19}><path d="M4 19V5a2 2 0 0 1 2-2h8l4 4v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z" /><path d="M14 3v5h5M8 13h8M8 17h5" /></Icon><span>Invoice analyzer</span></Link>
          <Link className="nav-item" href="/purchase-orders"><Icon size={19}><path d="M6 3h12v18H6z" /><path d="M9 8h6M9 12h6M9 16h4" /></Icon><span>Purchase orders</span></Link>
        </nav>
        <div className="sidebar-footer">
          {user.photoURL ? <img className="mini-avatar" src={user.photoURL} alt="" referrerPolicy="no-referrer" /> : <div className="mini-avatar">{(user.displayName || user.email || "U")[0].toUpperCase()}</div>}
          <div className="account-copy"><strong>{user.displayName || "Google account"}</strong><span>{user.email}</span></div>
          <button type="button" className="signout-button" onClick={() => signOut(auth)} aria-label="Sign out"><Icon size={17}><path d="M10 17l5-5-5-5M15 12H3" /><path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5" /></Icon></button>
        </div>
      </aside>

      <main className="main-content dashboard-content">
        <header className="page-header dashboard-header">
          <div><p className="eyebrow">Workspace overview</p><h1>Dashboard</h1><p>See what is ready, what needs attention, and how invoices are matching to purchase orders.</p></div>
          <div className="dashboard-actions"><Link className="secondary-button" href="/purchase-orders">View POs</Link><Link className="primary-button" href="/">Upload invoice</Link></div>
        </header>

        {error && <div className="error-message dashboard-error" role="alert">{error}</div>}
        {loading ? <div className="dashboard-loading"><span className="spinner dark-spinner" />Loading workspace totals…</div> : <>
          <section className="dashboard-metrics" aria-label="Workspace totals">
            <article className="metric-card"><span className="metric-icon metric-purple"><InvoiceIcon size={21} /></span><div><span>Total invoices</span><strong>{invoices.length}</strong><small>{verifiedInvoices.length} validated</small></div></article>
            <article className="metric-card"><span className="metric-icon metric-amber"><Icon size={21}><path d="M12 9v4M12 17h.01" /><circle cx="12" cy="12" r="9" /></Icon></span><div><span>Needs review</span><strong>{reviewInvoices.length}</strong><small>{invoices.length ? Math.round(reviewInvoices.length / invoices.length * 100) : 0}% of invoices</small></div></article>
            <article className="metric-card"><span className="metric-icon metric-green"><Icon size={21}><path d="m5 12 4 4L19 6" /></Icon></span><div><span>PO matched</span><strong>{matchedInvoices.length}</strong><small>{matchRate}% match rate</small></div></article>
            <article className="metric-card"><span className="metric-icon metric-blue"><Icon size={21}><path d="M6 3h12v18H6z" /><path d="M9 8h6M9 12h6" /></Icon></span><div><span>Open POs</span><strong>{openOrders.length}</strong><small>{orders.length} total purchase orders</small></div></article>
          </section>

          <div className="dashboard-grid">
            <section className="dashboard-card dashboard-attention">
              <div className="dashboard-card-heading"><div><p className="eyebrow">Action required</p><h2>Needs attention</h2><span>Review validation failures and PO exceptions.</span></div><Link href="/">View all invoices</Link></div>
              {attentionRows.length === 0 ? <div className="dashboard-empty"><Icon size={24}><path d="m5 12 4 4L19 6" /></Icon><strong>Everything looks clear</strong><span>No invoices currently need attention.</span></div> : <div className="attention-list">{attentionRows.map((row) => <Link className="attention-row" key={row.id} href={`/invoices/${row.recordId}${row.batchIndex === null ? "" : `?item=${row.batchIndex}`}`}><span className="attention-document"><InvoiceIcon size={17} /></span><span className="attention-main"><strong>{row.result.invoice.invoice_number || "No invoice number"}</strong><small>{row.result.invoice.vendor_name || row.fileName}</small></span><span className="attention-reason">{row.result.status === "needs_review" ? "Validation review" : matchLabel(row.result)}</span><span className="attention-total">{money(row.result.invoice.total, row.result.invoice.currency)}</span><Icon size={16}><path d="m9 18 6-6-6-6" /></Icon></Link>)}</div>}
            </section>

            <section className="dashboard-card match-health">
              <div className="dashboard-card-heading"><div><p className="eyebrow">Two-way matching</p><h2>PO match health</h2><span>Coverage across saved invoices.</span></div></div>
              <div className="match-score"><strong>{matchRate}%</strong><span>matched</span></div>
              <div className="match-progress" aria-label={`${matchRate}% matched`}><span style={{ width: `${matchRate}%` }} /></div>
              <dl className="match-breakdown"><div><dt><span className="legend-dot green" />Matched</dt><dd>{matchedInvoices.length}</dd></div><div><dt><span className="legend-dot amber" />Exceptions</dt><dd>{poExceptions.length}</dd></div><div><dt><span className="legend-dot purple" />Not checked</dt><dd>{poNotChecked}</dd></div><div><dt><span className="legend-dot blue" />Total checked</dt><dd>{poCheckedInvoices.length}</dd></div></dl>
              <Link className="secondary-button dashboard-card-action" href="/">Review matching</Link>
            </section>
          </div>

          <div className="dashboard-grid dashboard-lower-grid">
            <section className="dashboard-card">
              <div className="dashboard-card-heading"><div><p className="eyebrow">Latest activity</p><h2>Recent invoices</h2><span>Your five most recently uploaded invoices.</span></div></div>
              {invoices.length === 0 ? <div className="dashboard-empty"><InvoiceIcon size={24} /><strong>No invoices yet</strong><span>Upload an invoice to begin.</span></div> : <div className="recent-list">{invoices.slice(0, 5).map((row) => <Link key={row.id} className="recent-row" href={`/invoices/${row.recordId}${row.batchIndex === null ? "" : `?item=${row.batchIndex}`}`}><span><strong>{row.result.invoice.invoice_number || "No invoice number"}</strong><small>{row.result.invoice.vendor_name || "Unknown vendor"} · {row.createdAt ? row.createdAt.toDate().toLocaleDateString() : "Just now"}</small></span><span className={`review-flag ${row.result.status === "auto_approved" ? "verified" : "needs-review"}`}><span className="status-dot" />{row.result.status === "auto_approved" ? "Validated" : "Review"}</span></Link>)}</div>}
            </section>

            <section className="dashboard-card">
              <div className="dashboard-card-heading"><div><p className="eyebrow">Procurement</p><h2>Purchase orders</h2><span>Current PO availability.</span></div><Link href="/purchase-orders">Open register</Link></div>
              <div className="po-status-grid"><div><strong>{openOrders.length}</strong><span>Open</span></div><div><strong>{closedOrders.length}</strong><span>Closed</span></div><div><strong>{cancelledOrders.length}</strong><span>Cancelled</span></div></div>
              {orders.length === 0 ? <div className="dashboard-empty compact"><span>No purchase orders saved.</span><Link href="/purchase-orders">Upload your first PO</Link></div> : <div className="recent-list po-recent-list">{orders.slice(0, 3).map((order) => <Link key={order.id} className="recent-row" href={`/purchase-orders/${order.id}`}><span><strong>{order.purchaseOrder.po_number || "No PO number"}</strong><small>{order.purchaseOrder.vendor_name || "Unknown vendor"}</small></span><span className={`review-flag ${order.status === "open" ? "verified" : "needs-review"}`}><span className="status-dot" />{order.status}</span></Link>)}</div>}
            </section>
          </div>
        </>}
        <footer>Dashboard figures reflect the latest 100 saved invoices and purchase orders.</footer>
      </main>
    </div>
  );
}
