"use client";

import Link from "next/link";
import { ChangeEvent, ReactNode, useEffect, useRef, useState } from "react";
import { onAuthStateChanged, signOut, User } from "firebase/auth";

import {
  checkInvoice,
  deleteSavedAnalysis,
  isBatchResult,
  listInvoiceAnalyses,
  saveInvoiceAnalyses,
  saveInvoiceAnalysis,
  SavedAnalysis,
} from "@/lib/api";
import { downloadInvoiceCsv, downloadInvoiceResultsCsv } from "@/lib/csv";
import { auth } from "@/lib/firebase";

const MAX_FILE_BYTES = 20 * 1024 * 1024;

function apiMessage(error: unknown, action: "save" | "load" | "delete") {
  if (error instanceof Error) return error.message;
  if (action === "save") return "The invoice was analyzed, but its record could not be saved.";
  if (action === "delete") return "The invoice could not be deleted.";
  return "Saved analyzer invoices could not be loaded.";
}

function Icon({ children, size = 20 }: { children: ReactNode; size?: number }) {
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{children}</svg>;
}

function InvoiceIcon({ size = 20 }: { size?: number }) {
  return <Icon size={size}><path d="M6 3h9l3 3v15H6z" /><path d="M14 3v4h4M9 11h6M9 15h6M9 19h3" /></Icon>;
}

function AnalyzerIcon({ size = 20 }: { size?: number }) {
  return <Icon size={size}><path d="M4 19V5a2 2 0 0 1 2-2h8l4 4v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z" /><path d="M14 3v5h5M8 13h8M8 17h5" /></Icon>;
}

function money(value: number | null, currency: string | null) {
  if (value === null) return "—";
  try {
    return currency ? new Intl.NumberFormat(undefined, { style: "currency", currency }).format(value) : value.toFixed(2);
  } catch {
    return value.toFixed(2);
  }
}

function display(value: string | number | null) {
  return value === null || value === "" ? "—" : String(value);
}

function AnalysisDetails({ analysis }: { analysis: SavedAnalysis }) {
  const result = analysis.result;
  const invoice = result.invoice;
  const passedChecks = result.checks.filter((check) => check.status === "passed").length;
  return <>
    <section className={`status-card ${result.status === "auto_approved" ? "status-success" : "status-review"}`}>
      <div className="status-icon">{result.status === "auto_approved" ? <Icon><path d="m5 12 4 4L19 6" /></Icon> : <Icon><path d="M12 9v4M12 17h.01" /><circle cx="12" cy="12" r="9" /></Icon>}</div>
      <div><h3>{result.status === "auto_approved" ? "Invoice validation passed" : "Invoice needs review"}</h3><p>{passedChecks}/{result.checks.length} checks passed · {result.attempts} extraction {result.attempts === 1 ? "attempt" : "attempts"}</p>{result.reasons.length > 0 && <ul>{result.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}</div>
    </section>
    <section className="result-card"><h3>Extracted invoice</h3><dl className="details-grid"><div><dt>Vendor</dt><dd>{display(invoice.vendor_name)}</dd></div><div><dt>Invoice number</dt><dd>{display(invoice.invoice_number)}</dd></div><div><dt>Invoice date</dt><dd>{display(invoice.invoice_date)}</dd></div><div><dt>PO number</dt><dd>{display(invoice.po_number)}</dd></div><div><dt>Currency</dt><dd>{display(invoice.currency)}</dd></div></dl></section>
    <section className="result-card table-card"><div className="table-heading"><h3>Line items</h3></div><div className="table-scroll"><table><thead><tr><th>Description</th><th>Quantity</th><th>Unit price</th><th>Amount</th></tr></thead><tbody>{invoice.line_items.length === 0 ? <tr><td colSpan={4} className="empty-cell">No line items extracted.</td></tr> : invoice.line_items.map((item, index) => <tr key={`${item.description}-${index}`}><td className="primary-cell">{item.description}</td><td>{display(item.quantity)}</td><td>{money(item.unit_price, invoice.currency)}</td><td className="primary-cell">{money(item.amount, invoice.currency)}</td></tr>)}</tbody></table></div></section>
    <section className="result-card"><h3>Amounts</h3><dl className="amount-grid"><div><dt>Subtotal</dt><dd>{money(invoice.subtotal, invoice.currency)}</dd></div><div><dt>Discount</dt><dd>{money(invoice.discount, invoice.currency)}</dd></div><div><dt>Shipping</dt><dd>{money(invoice.shipping, invoice.currency)}</dd></div><div><dt>Tax</dt><dd>{money(invoice.tax, invoice.currency)}</dd></div><div><dt>Total</dt><dd>{money(invoice.total, invoice.currency)}</dd></div></dl></section>
    <section className="result-card"><div className="section-heading-row"><div><h3>Validation checks</h3><p>Code-based checks on the extracted invoice values.</p></div><span className="section-count">{passedChecks}/{result.checks.length} passed</span></div><div className="checks-grid">{result.checks.map((check) => <article className={`check-card ${check.status === "passed" ? "check-card-success" : check.status === "failed" ? "check-card-danger" : ""}`} key={check.id}><div className="check-title"><h4>{check.label}</h4><span className={`badge ${check.status === "passed" ? "badge-success" : check.status === "failed" ? "badge-danger" : "badge-neutral"}`}>{check.status === "passed" ? "Passed" : check.status === "failed" ? "Review" : "Not checked"}</span></div><p>{check.detail}</p></article>)}</div></section>
  </>;
}

export default function InvoiceAnalyzerPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [saveState, setSaveState] = useState<"idle" | "saving" | "error">("idle");
  const [saveError, setSaveError] = useState("");
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [analyses, setAnalyses] = useState<SavedAnalysis[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [notice, setNotice] = useState("");
  const [selectedAnalysis, setSelectedAnalysis] = useState<SavedAnalysis | null>(null);
  const [deletingId, setDeletingId] = useState("");
  const [actionError, setActionError] = useState("");

  useEffect(() => onAuthStateChanged(auth, (nextUser) => {
    setUser(nextUser);
    setAuthReady(true);
  }), []);

  useEffect(() => {
    if (!user) {
      setAnalyses([]);
      setHistoryLoading(false);
      return;
    }
    setHistoryLoading(true);
    setHistoryError("");
    let cancelled = false;
    listInvoiceAnalyses().then((records) => {
      if (!cancelled) setAnalyses(records);
    }).catch((loadError) => {
      if (!cancelled) setHistoryError(apiMessage(loadError, "load"));
    }).finally(() => {
      if (!cancelled) setHistoryLoading(false);
    });
    return () => { cancelled = true; };
  }, [user]);

  useEffect(() => {
    if (!uploadModalOpen && !selectedAnalysis) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || loading || deletingId) return;
      setUploadModalOpen(false);
      setSelectedAnalysis(null);
    };
    document.addEventListener("keydown", onKeyDown);
    document.body.classList.add("modal-open");
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.classList.remove("modal-open");
    };
  }, [uploadModalOpen, selectedAnalysis, loading, deletingId]);

  function resetUpload() {
    setFile(null);
    setError("");
    setSaveState("idle");
    setSaveError("");
    if (inputRef.current) inputRef.current.value = "";
  }

  function openUploadModal() {
    resetUpload();
    setNotice("");
    setUploadModalOpen(true);
  }

  function closeUploadModal() {
    if (!loading) setUploadModalOpen(false);
  }

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] || null;
    setError("");
    setSaveState("idle");
    setSaveError("");
    if (!selected) return setFile(null);
    const lowerName = selected.name.toLowerCase();
    if (!lowerName.endsWith(".pdf") && !lowerName.endsWith(".zip")) {
      event.target.value = "";
      setFile(null);
      return setError("Choose a PDF invoice or a ZIP containing invoices.");
    }
    if (selected.size > MAX_FILE_BYTES) {
      event.target.value = "";
      setFile(null);
      return setError("The selected file is larger than 20 MB.");
    }
    setFile(selected);
  }

  async function analyze() {
    if (!file || !user || loading) return;
    setLoading(true);
    setError("");
    setSaveState("idle");
    setSaveError("");
    try {
      const analyzed = await checkInvoice(file);
      setSaveState("saving");
      try {
        if (isBatchResult(analyzed)) {
          const successfulFiles = analyzed.files.filter((item) => item.result !== null);
          if (successfulFiles.length === 0) {
            throw new Error("No invoice in this ZIP could be analyzed.");
          }
          const saved = await saveInvoiceAnalyses(successfulFiles.map((item) => ({
              fileName: item.filename,
              fileType: "pdf",
              archiveName: file.name,
              status: item.result!.status,
              result: item.result!,
            })));
          setAnalyses((current) => [...saved, ...current]);
          const failedCopy = analyzed.summary.failed
            ? ` ${analyzed.summary.failed} ${analyzed.summary.failed === 1 ? "file" : "files"} could not be analyzed.`
            : "";
          setNotice(`${successfulFiles.length} ${successfulFiles.length === 1 ? "invoice was" : "invoices were"} analyzed and saved.${failedCopy}`);
        } else {
          const saved = await saveInvoiceAnalysis({
            fileName: file.name,
            fileType: "pdf",
            fileSizeBytes: file.size,
            status: analyzed.status,
            result: analyzed,
          });
          setAnalyses((current) => [saved, ...current]);
          setNotice(`${analyzed.invoice.invoice_number || file.name} was analyzed and saved.`);
        }
        resetUpload();
        setUploadModalOpen(false);
      } catch (saveFailure) {
        setSaveState("error");
        setSaveError(saveFailure instanceof Error && saveFailure.message.startsWith("No invoice in this ZIP")
          ? saveFailure.message
          : apiMessage(saveFailure, "save"));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The invoice could not be analyzed.");
    } finally {
      setLoading(false);
    }
  }

  async function deleteAnalysis(analysis: SavedAnalysis) {
    if (!user || deletingId) return;
    const invoiceLabel = analysis.result.invoice.invoice_number || analysis.fileName;
    if (!window.confirm(`Delete ${invoiceLabel}? This cannot be undone.`)) return;
    setDeletingId(analysis.id);
    setActionError("");
    setNotice("");
    try {
      await deleteSavedAnalysis(analysis.id);
      setAnalyses((current) => current.filter((item) => item.id !== analysis.id));
      setSelectedAnalysis(null);
      setNotice(`${invoiceLabel} was deleted.`);
    } catch (deleteFailure) {
      setActionError(apiMessage(deleteFailure, "delete"));
    } finally {
      setDeletingId("");
    }
  }

  if (!authReady) return <main className="review-state"><span className="spinner dark-spinner" /><p>Loading invoice analyzer…</p></main>;
  if (!user) return <main className="review-state"><span className="review-state-icon"><AnalyzerIcon size={25} /></span><h1>Sign in required</h1><p>Sign in to use the invoice analyzer.</p><Link className="primary-button review-back-button" href="/">Go to sign in</Link></main>;

  const selectedIsZip = file?.name.toLowerCase().endsWith(".zip") ?? false;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><InvoiceIcon size={23} /></span><span>Invoice<span className="brand-dot">.</span></span></div>
        <nav aria-label="Main navigation">
          <p className="nav-label">Workspace</p>
          <Link className="nav-item" href="/dashboard"><Icon size={19}><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" /></Icon><span>Dashboard</span></Link>
          <Link className="nav-item" href="/"><InvoiceIcon size={19} /><span>Two way match</span></Link>
          <Link className="nav-item active" href="/invoice-analyzer" aria-current="page"><AnalyzerIcon size={19} /><span>Invoice analyzer</span></Link>
          <Link className="nav-item" href="/purchase-orders"><Icon size={19}><path d="M6 3h12v18H6z" /><path d="M9 8h6M9 12h6M9 16h4" /></Icon><span>Purchase orders</span></Link>
        </nav>
        <div className="sidebar-footer">
          {user.photoURL ? <img className="mini-avatar" src={user.photoURL} alt="" referrerPolicy="no-referrer" /> : <div className="mini-avatar">{(user.displayName || user.email || "U")[0].toUpperCase()}</div>}
          <div className="account-copy"><strong>{user.displayName || "Google account"}</strong><span>{user.email}</span></div>
          <button type="button" className="signout-button" onClick={() => signOut(auth)} aria-label="Sign out"><Icon size={17}><path d="M10 17l5-5-5-5M15 12H3" /><path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5" /></Icon></button>
        </div>
      </aside>

      <main className="main-content analyzer-content">
        <header className="page-header analyzer-header">
          <div><p className="eyebrow">Standalone tool</p><h1>Invoice analyzer</h1><p>Analyze invoices and keep them separate from two-way matching.</p></div>
          <button className="primary-button header-button" type="button" onClick={openUploadModal}><Icon size={18}><path d="M12 5v14M5 12h14" /></Icon>Upload invoice</button>
        </header>

        <section className="analyzer-privacy"><Icon size={18}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /><path d="m9 12 2 2 4-4" /></Icon><div><strong>Separate analyzer storage</strong><span>Analyzer records are stored in their own private collection and do not appear in two-way-match history or dashboard totals. Uploaded PDFs are not retained.</span></div></section>

        {notice && <div className="analyzer-save-notice" role="status"><Icon size={17}><path d="m5 12 4 4L19 6" /></Icon><span>{notice}</span></div>}
        {actionError && <div className="error-message analyzer-action-error" role="alert"><Icon size={18}><path d="M12 9v4M12 17h.01" /><circle cx="12" cy="12" r="9" /></Icon>{actionError}</div>}

        <section className="invoice-table-card analyzer-history">
          <div className="invoice-table-heading">
            <div><p className="eyebrow">Analyzer database</p><h2>Stored invoices</h2><p>Review standalone analysis records or export their extracted data to CSV.</p></div>
            <div className="analyzer-table-actions">
              <span className="invoice-count">{analyses.length} {analyses.length === 1 ? "invoice" : "invoices"}</span>
              <button type="button" className="secondary-button" disabled={analyses.length === 0} onClick={() => downloadInvoiceResultsCsv(analyses)}><Icon size={16}><path d="M12 3v12M7 10l5 5 5-5" /><path d="M5 21h14" /></Icon>Export all CSV</button>
            </div>
          </div>

          {historyLoading && <div className="table-state"><span className="spinner dark-spinner" />Loading stored invoices…</div>}
          {historyError && <div role="alert" className="error-message table-error">{historyError}</div>}
          {!historyLoading && !historyError && analyses.length === 0 && <div className="table-empty"><div className="empty-icon"><AnalyzerIcon size={26} /></div><h3>No analyzer invoices yet</h3><p>Upload a PDF to create your first stored analysis.</p><button type="button" className="secondary-button" onClick={openUploadModal}>Upload invoice</button></div>}

          {!historyLoading && !historyError && analyses.length > 0 && <div className="invoice-table-scroll"><table className="invoice-list-table analyzer-list-table"><thead><tr><th>Invoice</th><th>Vendor</th><th>Invoice date</th><th>Total</th><th>Status</th><th>Saved</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{analyses.map((analysis) => {
            const invoice = analysis.result.invoice;
            return <tr key={analysis.id}><td><div className="invoice-identity"><span className="table-file-icon"><InvoiceIcon size={18} /></span><span><strong>{invoice.invoice_number || "No invoice number"}</strong><small>{analysis.fileName}</small></span></div></td><td className="vendor-cell">{invoice.vendor_name || "Unknown vendor"}</td><td>{invoice.invoice_date || "—"}</td><td className="total-cell">{money(invoice.total, invoice.currency)}</td><td><span className={`review-flag ${analysis.result.status === "auto_approved" ? "verified" : "needs-review"}`}><span className="status-dot" />{analysis.result.status === "auto_approved" ? "Validated" : "Review"}</span></td><td>{analysis.createdAt ? analysis.createdAt.toDate().toLocaleDateString() : "Just now"}</td><td><div className="analyzer-row-actions"><button type="button" className="view-button" onClick={() => setSelectedAnalysis(analysis)}>View details</button><button type="button" className="view-button" onClick={() => downloadInvoiceCsv(analysis.result, analysis.fileName)}>Export CSV</button><button type="button" className="view-button delete-button" disabled={deletingId === analysis.id} onClick={() => deleteAnalysis(analysis)}>{deletingId === analysis.id ? "Deleting…" : "Delete"}</button></div></td></tr>;
          })}</tbody></table></div>}
        </section>

        <footer>Invoice Analyzer and Two Way Match use separate private workspace records.</footer>
      </main>

      {uploadModalOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeUploadModal(); }}>
        <section className="modal-card upload-modal" role="dialog" aria-modal="true" aria-labelledby="analyzer-upload-title">
          <div className="modal-header"><div><p className="eyebrow">New analysis</p><h2 id="analyzer-upload-title">Upload invoice</h2><p>Choose one PDF or a ZIP containing up to 10 invoices.</p></div><button type="button" className="modal-close" onClick={closeUploadModal} disabled={loading} aria-label="Close upload dialog"><Icon size={20}><path d="m6 6 12 12M18 6 6 18" /></Icon></button></div>
          <div className="modal-body">
            <div className="secure-strip"><Icon size={16}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /><path d="m9 12 2 2 4-4" /></Icon>Saved only to the Invoice Analyzer collection</div>
            <button type="button" className={`upload-zone modal-upload-zone ${file ? "has-file" : ""}`} onClick={() => inputRef.current?.click()} disabled={loading}><span className="upload-icon"><Icon size={27}><path d="M12 16V4M7 9l5-5 5 5" /><path d="M5 14v5h14v-5" /></Icon></span><span className="upload-copy"><strong>{file ? file.name : "Choose a PDF or ZIP"}</strong><small>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB · ${selectedIsZip ? "ZIP batch" : "PDF invoice"}` : "PDF or ZIP · Maximum 20 MB · Up to 10 invoices"}</small></span><span className="browse-button">Browse files</span></button>
            <input ref={inputRef} type="file" accept="application/pdf,application/zip,application/x-zip-compressed,.pdf,.zip" onChange={selectFile} className="sr-only" />
            {error && <div className="error-message" role="alert"><Icon size={18}><path d="M12 9v4M12 17h.01" /><circle cx="12" cy="12" r="9" /></Icon>{error}</div>}
            {saveState === "error" && <div className="error-message" role="alert"><Icon size={18}><path d="M12 9v4M12 17h.01" /><circle cx="12" cy="12" r="9" /></Icon>{saveError}</div>}
          </div>
          <div className="modal-actions"><button type="button" className="secondary-button" onClick={closeUploadModal} disabled={loading}>Cancel</button><button type="button" className="primary-button check-button" onClick={analyze} disabled={!file || loading}>{loading ? <span className="spinner" /> : <AnalyzerIcon size={18} />}{loading ? (saveState === "saving" ? "Saving…" : "Analyzing…") : "Analyze & save"}</button></div>
        </section>
      </div>}

      {selectedAnalysis && <div className="modal-backdrop details-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !deletingId) setSelectedAnalysis(null); }}>
        <section className="modal-card details-modal" role="dialog" aria-modal="true" aria-labelledby="analysis-detail-title">
          <div className="modal-header details-modal-header">
            <div><p className="eyebrow">Invoice analysis</p><h2 id="analysis-detail-title">{selectedAnalysis.result.invoice.invoice_number || "Extracted invoice"}</h2><p>{selectedAnalysis.fileName} · {selectedAnalysis.result.invoice.vendor_name || "Unknown vendor"}</p></div>
            <div className="modal-header-actions">
              <button type="button" className="secondary-button" onClick={() => downloadInvoiceCsv(selectedAnalysis.result, selectedAnalysis.fileName)}><Icon size={16}><path d="M12 3v12M7 10l5 5 5-5" /><path d="M5 21h14" /></Icon>Export CSV</button>
              <button type="button" className="secondary-button delete-button" disabled={Boolean(deletingId)} onClick={() => deleteAnalysis(selectedAnalysis)}><Icon size={16}><path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6" /></Icon>{deletingId ? "Deleting…" : "Delete"}</button>
              <button type="button" className="modal-close" onClick={() => setSelectedAnalysis(null)} disabled={Boolean(deletingId)} aria-label="Close invoice details"><Icon size={20}><path d="m6 6 12 12M18 6 6 18" /></Icon></button>
            </div>
          </div>
          <div className="details-modal-body"><AnalysisDetails analysis={selectedAnalysis} /></div>
        </section>
      </div>}
    </div>
  );
}
