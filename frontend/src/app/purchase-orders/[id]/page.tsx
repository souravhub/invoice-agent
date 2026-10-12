"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { onAuthStateChanged, User } from "firebase/auth";

import { ApiTimestamp, getPurchaseOrder, InvoiceResult, isBatchResult, listInvoices, SavedPurchaseOrder, updatePurchaseOrderStatus } from "@/lib/api";
import { auth } from "@/lib/firebase";

type RelatedInvoice = {
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

function display(value: string | number | null) {
  return value === null || value === "" ? "—" : String(value);
}

function money(value: number | null, currency: string | null) {
  if (value === null) return "—";
  try {
    return currency ? new Intl.NumberFormat(undefined, { style: "currency", currency }).format(value) : value.toFixed(2);
  } catch {
    return value.toFixed(2);
  }
}

export default function PurchaseOrderDetailsPage() {
  const params = useParams<{ id: string }>();
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [saved, setSaved] = useState<SavedPurchaseOrder | null>(null);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState("");
  const [relatedInvoices, setRelatedInvoices] = useState<RelatedInvoice[]>([]);
  const [invoicesLoading, setInvoicesLoading] = useState(false);

  useEffect(() => onAuthStateChanged(auth, (nextUser) => {
    setUser(nextUser);
    setAuthReady(true);
  }), []);

  useEffect(() => {
    if (!authReady) return;
    if (!user) {
      setError("Sign in to view this purchase order.");
      setLoading(false);
      return;
    }
    getPurchaseOrder(params.id).then((record) => {
      setSaved(record);
    }).catch((caught) => setError(caught instanceof Error ? caught.message : "The purchase order could not be loaded.")).finally(() => setLoading(false));
  }, [authReady, user, params.id]);

  useEffect(() => {
    if (!user) return;
    setInvoicesLoading(true);
    let cancelled = false;
    listInvoices(100).then((records) => {
      const rows = records.flatMap<RelatedInvoice>((savedInvoice) => {
        if (isBatchResult(savedInvoice.result)) {
          return savedInvoice.result.files.flatMap((file, index) =>
            file.result?.two_way_match?.purchase_order_id === params.id
              ? [{
                  id: `${savedInvoice.id}-${index}`,
                  recordId: savedInvoice.id,
                  batchIndex: index,
                  fileName: file.filename,
                  createdAt: savedInvoice.createdAt,
                  result: file.result,
                }]
              : [],
          );
        }
        return savedInvoice.result.two_way_match?.purchase_order_id === params.id
          ? [{
              id: savedInvoice.id,
              recordId: savedInvoice.id,
              batchIndex: null,
              fileName: savedInvoice.fileName,
              createdAt: savedInvoice.createdAt,
              result: savedInvoice.result,
            }]
          : [];
      });
      if (!cancelled) setRelatedInvoices(rows);
    }).catch((loadError) => {
      if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Related invoices could not be loaded.");
    }).finally(() => {
      if (!cancelled) setInvoicesLoading(false);
    });
    return () => { cancelled = true; };
  }, [user, params.id]);

  async function changeStatus(status: SavedPurchaseOrder["status"]) {
    if (!user || !saved || updating) return;
    setUpdating(true);
    setError("");
    try {
      const updated = await updatePurchaseOrderStatus(params.id, status);
      setSaved(updated);
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : "The PO status could not be updated.");
    } finally {
      setUpdating(false);
    }
  }

  if (loading || !authReady) return <main className="review-state"><span className="spinner dark-spinner" /><p>Loading purchase order…</p></main>;
  if (error && !saved) return <main className="review-state"><span className="review-state-icon"><Icon size={24}><path d="M12 9v4M12 17h.01" /><circle cx="12" cy="12" r="9" /></Icon></span><h1>Purchase order unavailable</h1><p>{error}</p><Link className="primary-button review-back-button" href="/purchase-orders">Back to purchase orders</Link></main>;
  if (!saved) return null;

  const po = saved.purchaseOrder;
  const checks = saved.extraction?.checks || [];
  return (
    <main className="review-page">
      <header className="review-header">
        <div className="review-heading"><Link href="/purchase-orders" className="review-back" aria-label="Back to purchase orders"><Icon size={19}><path d="m15 18-6-6 6-6" /></Icon></Link><div><p className="eyebrow">Purchase order</p><h1>{po.po_number || "Extracted PO"}</h1><p>{saved.fileName} · {po.vendor_name || "Unknown vendor"}</p></div></div>
        <div className="review-header-actions">
          <span className={`review-header-status ${saved.status === "open" ? "verified" : "needs-review"}`}><span className="status-dot" />{saved.status}</span>
          <select className="status-select" value={saved.status} onChange={(event) => changeStatus(event.target.value as SavedPurchaseOrder["status"])} disabled={updating} aria-label="Purchase order status"><option value="open">Open</option><option value="closed">Closed</option><option value="cancelled">Cancelled</option></select>
        </div>
      </header>
      <div className="po-details-layout">
        <section className="result-card">
          <div className="validation-section-heading"><div><span>Saved record</span><h3>Purchase order information</h3></div><span className="field-count">{po.line_items.length} lines</span></div>
          <dl className="details-grid po-details-grid"><div><dt>PO number</dt><dd>{display(po.po_number)}</dd></div><div><dt>Vendor</dt><dd>{display(po.vendor_name)}</dd></div><div><dt>Order date</dt><dd>{display(po.order_date)}</dd></div><div><dt>Currency</dt><dd>{display(po.currency)}</dd></div><div><dt>Total</dt><dd>{money(po.total, po.currency)}</dd></div></dl>
        </section>
        {error && <div className="error-message">{error}</div>}
        <section className="result-card table-card"><div className="table-heading"><h3>Ordered line items</h3></div><div className="table-scroll"><table><thead><tr><th>Description</th><th>Quantity</th><th>Unit price</th><th>Amount</th></tr></thead><tbody>{po.line_items.length === 0 ? <tr><td colSpan={4} className="empty-cell">No PO line items were extracted.</td></tr> : po.line_items.map((item, index) => <tr key={`${item.description}-${index}`}><td className="primary-cell">{item.description}</td><td>{display(item.quantity)}</td><td>{money(item.unit_price, po.currency)}</td><td className="primary-cell">{money(item.amount, po.currency)}</td></tr>)}</tbody></table></div></section>
        <section className="result-card table-card">
          <div className="table-heading related-invoices-heading">
            <div><h3>Related invoices</h3><p>Invoices that were compared with this purchase order.</p></div>
            <span className="invoice-count">{relatedInvoices.length} {relatedInvoices.length === 1 ? "invoice" : "invoices"}</span>
          </div>
          {invoicesLoading ? (
            <div className="table-state"><span className="spinner dark-spinner" />Loading related invoices…</div>
          ) : relatedInvoices.length === 0 ? (
            <div className="related-invoices-empty"><p>No invoices have been matched against this PO yet.</p><Link href="/" className="secondary-button">Go to invoices</Link></div>
          ) : (
            <div className="table-scroll"><table><thead><tr><th>Invoice</th><th>Invoice date</th><th>Total</th><th>PO match</th><th>Uploaded</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>
              {relatedInvoices.map((related) => {
                const invoice = related.result.invoice;
                const matchStatus = related.result.two_way_match?.status;
                return <tr key={related.id}>
                  <td><div className="invoice-identity"><span className="table-file-icon"><Icon size={18}><path d="M6 3h9l3 3v15H6z" /><path d="M14 3v4h4M9 11h6M9 15h6" /></Icon></span><span><strong>{invoice.invoice_number || "No invoice number"}</strong><small>{related.fileName}</small></span></div></td>
                  <td>{invoice.invoice_date || "—"}</td>
                  <td className="total-cell">{money(invoice.total, invoice.currency)}</td>
                  <td><span className={`review-flag ${matchStatus === "matched" ? "verified" : "needs-review"}`}><span className="status-dot" />{matchStatus === "matched" ? "Matched" : "Review needed"}</span></td>
                  <td>{related.createdAt ? related.createdAt.toDate().toLocaleDateString() : "Just now"}</td>
                  <td><Link className="view-button" href={`/invoices/${related.recordId}${related.batchIndex === null ? "" : `?item=${related.batchIndex}`}`}>View</Link></td>
                </tr>;
              })}
            </tbody></table></div>
          )}
        </section>
        <section className="result-card"><h3>Extraction checks</h3><div className="checks-grid">{checks.map((check) => <article key={check.id} className={`check-card ${check.status === "passed" ? "check-card-success" : "check-card-danger"}`}><div className="check-title"><h4>{check.label}</h4><span className={`badge ${check.status === "passed" ? "badge-success" : "badge-danger"}`}>{check.status === "passed" ? "Passed" : "Review"}</span></div><p>{check.detail}</p></article>)}</div></section>
      </div>
    </main>
  );
}
