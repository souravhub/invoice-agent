"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { onAuthStateChanged, User } from "firebase/auth";

import {
  CheckResult,
  ConfiguredCheck,
  getInvoice,
  Invoice,
  InvoiceResult,
  isBatchResult,
  matchSavedPurchaseOrder,
  recheckInvoice,
  updateSavedInvoice,
} from "@/lib/api";
import { auth } from "@/lib/firebase";

function Icon({ children, size = 20 }: { children: ReactNode; size?: number }) {
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {children}
    </svg>
  );
}

function display(value: string | number | null) {
  return value === null || value === "" ? "—" : String(value);
}

function money(value: number | null, currency: string | null) {
  if (value === null) return "—";
  if (currency) {
    try {
      return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(value);
    } catch {
      // Fall back to a plain number for uncommon currency codes.
    }
  }
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const checkMeta: Record<ConfiguredCheck["status"], { label: string; className: string }> = {
  passed: { label: "Passed", className: "review-check-passed" },
  failed: { label: "Needs review", className: "review-check-failed" },
  not_checked: { label: "Not checked", className: "review-check-neutral" },
};

function InvoiceDocument({ invoice }: { invoice: Invoice }) {
  return (
    <article className="invoice-paper" aria-label="Invoice preview">
      <div className="paper-topline" />
      <header className="paper-header">
        <div>
          <span className="paper-kicker">From</span>
          <h2>{invoice.vendor_name || "Unknown vendor"}</h2>
          <p>Vendor invoice</p>
        </div>
        <div className="paper-title">
          <strong>INVOICE</strong>
          <span>{invoice.invoice_number || "No invoice number"}</span>
        </div>
      </header>

      <dl className="paper-meta">
        <div><dt>Invoice date</dt><dd>{display(invoice.invoice_date)}</dd></div>
        <div><dt>PO number</dt><dd>{display(invoice.po_number)}</dd></div>
        <div><dt>Currency</dt><dd>{display(invoice.currency)}</dd></div>
      </dl>

      <div className="paper-table-wrap">
        <table className="paper-table">
          <thead>
            <tr><th>Description</th><th>Qty</th><th>Unit price</th><th>Amount</th></tr>
          </thead>
          <tbody>
            {invoice.line_items.length === 0 ? (
              <tr><td colSpan={4} className="paper-empty">No line items extracted</td></tr>
            ) : invoice.line_items.map((item, index) => (
              <tr key={`${item.description}-${index}`}>
                <td>{item.description || "Untitled item"}</td>
                <td>{display(item.quantity)}</td>
                <td>{money(item.unit_price, invoice.currency)}</td>
                <td>{money(item.amount, invoice.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="paper-summary">
        <dl>
          <div><dt>Subtotal</dt><dd>{money(invoice.subtotal, invoice.currency)}</dd></div>
          <div><dt>Discount</dt><dd>{money(invoice.discount, invoice.currency)}</dd></div>
          <div><dt>Shipping</dt><dd>{money(invoice.shipping, invoice.currency)}</dd></div>
          <div><dt>Tax</dt><dd>{money(invoice.tax, invoice.currency)}</dd></div>
          <div className="paper-total"><dt>Total</dt><dd>{money(invoice.total, invoice.currency)}</dd></div>
        </dl>
      </div>

      <footer className="paper-footer">Invoice preview generated from the extracted data.</footer>
    </article>
  );
}

function ValidationPanel({ result }: { result: InvoiceResult }) {
  const invoice = result.invoice;
  const approved = result.status === "auto_approved";
  const passedChecks = result.checks.filter((check) => check.status === "passed").length;
  const fields: Array<[string, string | number | null]> = [
    ["Vendor", invoice.vendor_name],
    ["Invoice number", invoice.invoice_number],
    ["Invoice date", invoice.invoice_date],
    ["PO number", invoice.po_number],
    ["Currency", invoice.currency],
    ["Total", money(invoice.total, invoice.currency)],
  ];

  return (
    <aside className="validation-panel" aria-label="Invoice validation">
      <div className={`validation-status ${approved ? "validation-approved" : "validation-warning"}`}>
        <span className="validation-status-icon">
          {approved
            ? <Icon size={22}><path d="m5 12 4 4L19 6" /></Icon>
            : <Icon size={22}><path d="M12 9v4M12 17h.01" /><path d="M10.3 3.7 2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.7a2 2 0 0 0-3.4 0Z" /></Icon>}
        </span>
        <div>
          <span className="validation-label">Validation result</span>
          <h2>{approved ? "Validation passed" : "Human review needed"}</h2>
          <p>{passedChecks} of {result.checks.length} checks passed · {result.attempts} extraction {result.attempts === 1 ? "attempt" : "attempts"}</p>
        </div>
      </div>

      <section className="validation-section">
        <div className="validation-section-heading">
          <div><span>Extracted fields</span><h3>Invoice information</h3></div>
          <span className="field-count">{fields.length} fields</span>
        </div>
        <dl className="validation-fields">
          {fields.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{display(value)}</dd>
            </div>
          ))}
        </dl>
      </section>

      {result.reasons.length > 0 && (
        <section className="validation-section review-reasons">
          <div className="validation-section-heading"><div><span>Attention</span><h3>Review notes</h3></div></div>
          <ul>{result.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
        </section>
      )}

      {result.two_way_match && (
        <section className="validation-section">
          <div className="validation-section-heading">
            <div><span>Two-way match</span><h3>Purchase order comparison</h3></div>
            <span className="field-count">{result.two_way_match.status.replaceAll("_", " ")}</span>
          </div>
          {result.two_way_match.purchase_order_id && (
            <p className="matched-po-link"><Link href={`/purchase-orders/${result.two_way_match.purchase_order_id}`}>View matched PO {result.two_way_match.po_number}</Link></p>
          )}
          <div className="review-check-list">
            {result.two_way_match.checks.map((check) => {
              const meta = checkMeta[check.status];
              return (
                <article className={`review-check ${meta.className}`} key={`po-${check.id}`}>
                  <span className="review-check-icon">
                    {check.status === "passed"
                      ? <Icon size={16}><path d="m5 12 4 4L19 6" /></Icon>
                      : <Icon size={16}><path d="M12 8v5M12 17h.01" /><circle cx="12" cy="12" r="9" /></Icon>}
                  </span>
                  <div><h4>{check.label}</h4><p>{check.detail}</p></div>
                  <span className="review-check-result">{meta.label}</span>
                </article>
              );
            })}
          </div>
        </section>
      )}

      <section className="validation-section">
        <div className="validation-section-heading">
          <div><span>Rules</span><h3>Validation checks</h3></div>
          <span className="field-count">{passedChecks}/{result.checks.length}</span>
        </div>
        {result.checks.length === 0 ? (
          <p className="no-checks">No configured validation checks were returned.</p>
        ) : (
          <div className="review-check-list">
            {result.checks.map((check) => {
              const meta = checkMeta[check.status];
              return (
                <article className={`review-check ${meta.className}`} key={check.id}>
                  <span className="review-check-icon">
                    {check.status === "passed"
                      ? <Icon size={16}><path d="m5 12 4 4L19 6" /></Icon>
                      : <Icon size={16}><path d="M12 8v5M12 17h.01" /><circle cx="12" cy="12" r="9" /></Icon>}
                  </span>
                  <div><h4>{check.label}</h4><p>{check.detail}</p></div>
                  <span className="review-check-result">{meta.label}</span>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </aside>
  );
}

export default function InvoiceReviewPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [result, setResult] = useState<InvoiceResult | null>(null);
  const [savedResult, setSavedResult] = useState<CheckResult | null>(null);
  const [batchIndex, setBatchIndex] = useState<number | null>(null);
  const [fileName, setFileName] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [rechecking, setRechecking] = useState(false);
  const [recheckError, setRecheckError] = useState("");

  useEffect(() => onAuthStateChanged(auth, (nextUser) => {
    setUser(nextUser);
    setAuthReady(true);
  }), []);

  useEffect(() => {
    if (!authReady) return;
    if (!user) {
      setLoading(false);
      setError("Sign in to view this invoice.");
      return;
    }

    let cancelled = false;
    async function loadInvoice() {
      setLoading(true);
      setError("");
      try {
        const saved = await getInvoice(params.id);
        let selectedResult: InvoiceResult;
        let selectedFileName = saved.fileName;

        if (isBatchResult(saved.result)) {
          const itemIndex = Number(searchParams.get("item"));
          const item = Number.isInteger(itemIndex) ? saved.result.files[itemIndex] : undefined;
          if (!item?.result) throw new Error("This batch invoice could not be found.");
          selectedResult = item.result;
          selectedFileName = item.filename;
        } else {
          selectedResult = saved.result;
        }

        if (!cancelled) {
          setResult(selectedResult);
          setSavedResult(saved.result);
          setBatchIndex(isBatchResult(saved.result) ? Number(searchParams.get("item")) : null);
          setFileName(selectedFileName);
        }
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "The invoice could not be loaded.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadInvoice();
    return () => { cancelled = true; };
  }, [authReady, user, params.id, searchParams]);

  function downloadJson() {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${fileName.replace(/\.pdf$/i, "") || "invoice"}-result.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function recheckValidation() {
    if (!user || !result || !savedResult || rechecking) return;
    setRechecking(true);
    setRecheckError("");
    try {
      const validationOnlyResult = await recheckInvoice({ ...result, two_way_match: null });
      const twoWayMatch = await matchSavedPurchaseOrder(validationOnlyResult.invoice);

      const rechecked: InvoiceResult = twoWayMatch.status === "matched"
        ? { ...validationOnlyResult, two_way_match: twoWayMatch }
        : {
            ...validationOnlyResult,
            status: "needs_review",
            reasons: [...validationOnlyResult.reasons, ...twoWayMatch.reasons],
            two_way_match: twoWayMatch,
          };
      let nextSavedResult: CheckResult;
      if (isBatchResult(savedResult)) {
        if (batchIndex === null || !savedResult.files[batchIndex]?.result) {
          throw new Error("This batch invoice could not be rechecked.");
        }
        nextSavedResult = {
          ...savedResult,
          files: savedResult.files.map((file, index) =>
            index === batchIndex ? { ...file, result: rechecked } : file,
          ),
        };
      } else {
        nextSavedResult = rechecked;
      }
      await updateSavedInvoice(params.id, {
        result: nextSavedResult,
        status: isBatchResult(nextSavedResult) ? "batch_complete" : rechecked.status,
      });
      setResult(rechecked);
      setSavedResult(nextSavedResult);
    } catch (caught) {
      setRecheckError(caught instanceof Error ? caught.message : "Validation could not be rechecked.");
    } finally {
      setRechecking(false);
    }
  }

  if (loading || !authReady) {
    return <main className="review-state"><span className="spinner dark-spinner" /><p>Loading invoice review…</p></main>;
  }

  if (error || !result) {
    return (
      <main className="review-state">
        <span className="review-state-icon"><Icon size={25}><path d="M12 9v4M12 17h.01" /><circle cx="12" cy="12" r="9" /></Icon></span>
        <h1>Invoice unavailable</h1>
        <p>{error || "The invoice could not be loaded."}</p>
        <Link className="primary-button review-back-button" href="/">Back to invoices</Link>
      </main>
    );
  }

  const invoice = result.invoice;
  return (
    <main className="review-page">
      <header className="review-header">
        <div className="review-heading">
          <Link href="/" className="review-back" aria-label="Back to invoices">
            <Icon size={19}><path d="m15 18-6-6 6-6" /></Icon>
          </Link>
          <div>
            <p className="eyebrow">Invoice review</p>
            <h1>{invoice.invoice_number || "Extracted invoice"}</h1>
            <p>{fileName} <span aria-hidden="true">·</span> {invoice.vendor_name || "Unknown vendor"}</p>
          </div>
        </div>
        <div className="review-header-actions">
          <span className={`review-header-status ${result.status === "auto_approved" ? "verified" : "needs-review"}`}>
            <span className="status-dot" />
            {result.status === "auto_approved" ? "Validated" : "Review needed"}
          </span>
          {result.two_way_match?.purchase_order_id && (
            <Link className="secondary-button" href={`/purchase-orders/${result.two_way_match.purchase_order_id}`}>
              <Icon size={17}><path d="M6 3h12v18H6z" /><path d="M9 8h6M9 12h6M9 16h4" /></Icon>
              View PO
            </Link>
          )}
          <button type="button" className="secondary-button" onClick={downloadJson}>
            <Icon size={17}><path d="M12 3v12M7 10l5 5 5-5" /><path d="M5 21h14" /></Icon>
            Download JSON
          </button>
          <button type="button" className="secondary-button" onClick={recheckValidation} disabled={rechecking}>
            {rechecking ? <span className="spinner dark-spinner" /> : <Icon size={17}><path d="M20 11a8 8 0 1 0 2 5" /><path d="M20 4v7h-7" /></Icon>}
            {rechecking ? "Rechecking…" : "Recheck validation & PO"}
          </button>
        </div>
      </header>

      {recheckError && <div className="review-recheck-error" role="alert">{recheckError}</div>}

      <div className="review-split">
        <section className="document-pane">
          <div className="pane-heading">
            <div><span>Document</span><h2>Invoice preview</h2></div>
            <span className="page-indicator">Page 1 of 1</span>
          </div>
          <div className="paper-stage"><InvoiceDocument invoice={invoice} /></div>
        </section>
        <ValidationPanel result={result} />
      </div>
    </main>
  );
}
