"use client";

import Link from "next/link";
import { ChangeEvent, ReactNode, useEffect, useRef, useState } from "react";
import { onAuthStateChanged, signOut, User } from "firebase/auth";

import {
  deleteSavedPurchaseOrder,
  extractPurchaseOrder,
  listPurchaseOrders,
  savePurchaseOrder,
  SavedPurchaseOrder,
} from "@/lib/api";
import { auth } from "@/lib/firebase";

const MAX_FILE_BYTES = 20 * 1024 * 1024;

function Icon({ children, size = 20 }: { children: ReactNode; size?: number }) {
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {children}
    </svg>
  );
}

function PurchaseOrderIcon({ size = 20 }: { size?: number }) {
  return <Icon size={size}><path d="M6 3h12v18H6z" /><path d="M9 8h6M9 12h6M9 16h4" /></Icon>;
}

function normalizePoNumber(value: string | null) {
  return (value || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
}

function money(value: number | null, currency: string | null) {
  if (value === null) return "—";
  try {
    return currency
      ? new Intl.NumberFormat(undefined, { style: "currency", currency }).format(value)
      : value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  } catch {
    return value.toFixed(2);
  }
}

export default function PurchaseOrdersPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [orders, setOrders] = useState<SavedPurchaseOrder[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState("");
  const [deleteError, setDeleteError] = useState("");

  useEffect(() => onAuthStateChanged(auth, (nextUser) => {
    setUser(nextUser);
    setAuthReady(true);
  }), []);

  useEffect(() => {
    if (!user) return;
    setHistoryLoading(true);
    let cancelled = false;
    listPurchaseOrders().then((records) => {
      if (!cancelled) setOrders(records);
    }).catch((loadError) => {
      if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Purchase orders could not be loaded.");
    }).finally(() => {
      if (!cancelled) setHistoryLoading(false);
    });
    return () => { cancelled = true; };
  }, [user]);

  function openModal() {
    setFile(null);
    setError("");
    if (inputRef.current) inputRef.current.value = "";
    setModalOpen(true);
  }

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] || null;
    setError("");
    if (!selected) return setFile(null);
    if (!selected.name.toLowerCase().endsWith(".pdf")) {
      event.target.value = "";
      setFile(null);
      return setError("Choose a PDF purchase order.");
    }
    if (selected.size > MAX_FILE_BYTES) {
      event.target.value = "";
      setFile(null);
      return setError("The selected file is larger than 20 MB.");
    }
    setFile(selected);
  }

  async function upload() {
    if (!file || !user || loading) return;
    setLoading(true);
    setError("");
    try {
      const extraction = await extractPurchaseOrder(file);
      const normalizedPoNumber = normalizePoNumber(extraction.purchase_order.po_number);
      if (!normalizedPoNumber) throw new Error("No PO number was extracted. Review the PDF and try again.");

      const saved = await savePurchaseOrder({
        fileName: file.name,
        fileSizeBytes: file.size,
        normalizedPoNumber,
        status: "open",
        purchaseOrder: extraction.purchase_order,
        extraction,
      });
      setOrders((current) => [saved, ...current]);
      setModalOpen(false);
      setFile(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The purchase order could not be saved.");
    } finally {
      setLoading(false);
    }
  }

  async function deletePurchaseOrder(saved: SavedPurchaseOrder) {
    if (!user || deletingId) return;
    const poLabel = saved.purchaseOrder.po_number || saved.fileName;
    if (!window.confirm(`Delete ${poLabel}? Existing invoice results will not be changed. This cannot be undone.`)) return;
    setDeletingId(saved.id);
    setDeleteError("");
    try {
      await deleteSavedPurchaseOrder(saved.id);
      setOrders((current) => current.filter((item) => item.id !== saved.id));
    } catch (deleteFailure) {
      setDeleteError(deleteFailure instanceof Error ? deleteFailure.message : "The purchase order could not be deleted.");
    } finally {
      setDeletingId("");
    }
  }

  if (!authReady) return <main className="review-state"><span className="spinner dark-spinner" /><p>Loading purchase orders…</p></main>;
  if (!user) return (
    <main className="review-state">
      <span className="review-state-icon"><PurchaseOrderIcon size={25} /></span>
      <h1>Sign in required</h1>
      <p>Sign in from the invoice workspace to manage purchase orders.</p>
      <Link className="primary-button review-back-button" href="/">Go to sign in</Link>
    </main>
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><PurchaseOrderIcon size={23} /></span><span>Invoice<span className="brand-dot">.</span></span></div>
        <nav aria-label="Main navigation">
          <p className="nav-label">Workspace</p>
          <Link className="nav-item" href="/dashboard"><Icon size={19}><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" /></Icon><span>Dashboard</span></Link>
          <Link className="nav-item" href="/"><Icon size={19}><path d="M6 3h9l3 3v15H6z" /><path d="M14 3v4h4M9 11h6M9 15h6" /></Icon><span>Two way match</span></Link>
          <Link className="nav-item" href="/invoice-analyzer"><Icon size={19}><path d="M4 19V5a2 2 0 0 1 2-2h8l4 4v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z" /><path d="M14 3v5h5M8 13h8M8 17h5" /></Icon><span>Invoice analyzer</span></Link>
          <Link className="nav-item active" href="/purchase-orders" aria-current="page"><PurchaseOrderIcon size={19} /><span>Purchase orders</span></Link>
        </nav>
        <div className="sidebar-footer">
          {user.photoURL ? <img className="mini-avatar" src={user.photoURL} alt="" referrerPolicy="no-referrer" /> : <div className="mini-avatar">{(user.displayName || "U")[0]}</div>}
          <div className="account-copy"><strong>{user.displayName || "Google account"}</strong><span>{user.email}</span></div>
          <button type="button" className="signout-button" onClick={() => signOut(auth)} aria-label="Sign out"><Icon size={17}><path d="M10 17l5-5-5-5M15 12H3" /><path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5" /></Icon></button>
        </div>
      </aside>

      <main className="main-content">
        <header className="page-header">
          <div><p className="eyebrow">Procurement</p><h1>Purchase orders</h1><p>Upload approved POs once, then automatically match incoming invoices.</p></div>
          <button className="primary-button header-button" type="button" onClick={openModal}><Icon size={18}><path d="M12 5v14M5 12h14" /></Icon>Upload PO</button>
        </header>

        <section className="intro-banner po-banner">
          <div className="banner-icon"><PurchaseOrderIcon size={23} /></div>
          <div className="banner-copy"><h2>Your PO register</h2><p>Invoices use their extracted PO number to find an open order in this list.</p></div>
          <span className="banner-pill">{orders.filter((order) => order.status === "open").length} open</span>
        </section>

        <section className="invoice-table-card">
          <div className="invoice-table-heading"><div><p className="eyebrow">Workspace API</p><h2>Saved purchase orders</h2><p>PO data is private to your signed-in account.</p></div><span className="invoice-count">{orders.length} POs</span></div>
          {deleteError && <div role="alert" className="error-message table-error">{deleteError}</div>}
          {historyLoading ? <div className="table-state"><span className="spinner dark-spinner" />Loading purchase orders…</div> : orders.length === 0 ? (
            <div className="table-empty"><div className="empty-icon"><PurchaseOrderIcon size={26} /></div><h3>No purchase orders yet</h3><p>Upload a PO before processing its invoices.</p><button type="button" className="secondary-button" onClick={openModal}>Upload PO</button></div>
          ) : (
            <div className="invoice-table-scroll"><table className="invoice-list-table"><thead><tr><th>PO number</th><th>Vendor</th><th>Order date</th><th>Lines</th><th>Total</th><th>Status</th><th>Uploaded</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>
              {orders.map((saved) => <tr key={saved.id}>
                <td><div className="invoice-identity"><span className="table-file-icon"><PurchaseOrderIcon size={18} /></span><span><strong>{saved.purchaseOrder.po_number || "No PO number"}</strong><small>{saved.fileName}</small></span></div></td>
                <td className="vendor-cell">{saved.purchaseOrder.vendor_name || "Unknown vendor"}</td>
                <td>{saved.purchaseOrder.order_date || "—"}</td>
                <td>{saved.purchaseOrder.line_items.length}</td>
                <td className="total-cell">{money(saved.purchaseOrder.total, saved.purchaseOrder.currency)}</td>
                <td><span className={`review-flag ${saved.status === "open" ? "verified" : "needs-review"}`}><span className="status-dot" />{saved.status}</span></td>
                <td>{saved.createdAt ? saved.createdAt.toDate().toLocaleDateString() : "Just now"}</td>
                <td><div className="table-row-actions"><Link className="view-button" href={`/purchase-orders/${saved.id}`}>View</Link><button type="button" className="view-button delete-button" disabled={deletingId === saved.id} onClick={() => deletePurchaseOrder(saved)}>{deletingId === saved.id ? "Deleting…" : "Delete"}</button></div></td>
              </tr>)}
            </tbody></table></div>
          )}
        </section>
        <footer>Two-way matching compares invoice data with the saved purchase order; it does not confirm receipt of goods.</footer>
      </main>

      {modalOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !loading) setModalOpen(false); }}>
        <section className="modal-card upload-modal" role="dialog" aria-modal="true" aria-labelledby="po-upload-title">
          <div className="modal-header"><div><p className="eyebrow">PO register</p><h2 id="po-upload-title">Upload purchase order</h2><p>Choose one text-based purchase-order PDF.</p></div><button type="button" className="modal-close" onClick={() => setModalOpen(false)} disabled={loading} aria-label="Close"><Icon size={20}><path d="m6 6 12 12M18 6 6 18" /></Icon></button></div>
          <div className="modal-body">
            <div className="secure-strip"><Icon size={16}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /></Icon>Private PO register · PDF · Maximum 20 MB</div>
            <button type="button" className={`upload-zone modal-upload-zone ${file ? "has-file" : ""}`} onClick={() => inputRef.current?.click()} disabled={loading}>
              <span className="upload-icon"><Icon size={27}><path d="M12 16V4M7 9l5-5 5 5" /><path d="M5 14v5h14v-5" /></Icon></span>
              <span className="upload-copy"><strong>{file ? file.name : "Choose a purchase-order PDF"}</strong><small>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : "The PO number and line items will be extracted"}</small></span><span className="browse-button">Browse files</span>
            </button>
            <input ref={inputRef} type="file" accept="application/pdf,.pdf" onChange={chooseFile} className="sr-only" />
            {error && <div role="alert" className="error-message"><Icon size={18}><path d="M12 9v4M12 17h.01" /><circle cx="12" cy="12" r="9" /></Icon>{error}</div>}
          </div>
          <div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setModalOpen(false)} disabled={loading}>Cancel</button><button type="button" className="primary-button check-button" onClick={upload} disabled={!file || loading}>{loading ? <span className="spinner" /> : <PurchaseOrderIcon size={18} />}{loading ? "Extracting…" : "Extract and save PO"}</button></div>
        </section>
      </div>}
    </div>
  );
}
