"use client";

import { ChangeEvent, ReactNode, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithPopup,
  signOut,
  User,
} from "firebase/auth";

import {
  checkInvoice,
  ApiTimestamp,
  CheckResult,
  ConfiguredCheck,
  Invoice,
  InvoiceResult,
  isBatchResult,
  deleteSavedInvoice,
  listInvoices,
  matchSavedPurchaseOrder,
  saveInvoice,
  SavedInvoice,
  syncUserProfile,
  updateSavedInvoice,
} from "@/lib/api";
import { auth } from "@/lib/firebase";

const MAX_FILE_BYTES = 20 * 1024 * 1024;

type InvoiceTableRow = {
  id: string;
  recordId: string;
  batchIndex: number | null;
  fileName: string;
  createdAt: ApiTimestamp | null;
  result: InvoiceResult;
};

function authMessage(error: unknown) {
  if (typeof error === "object" && error !== null && "code" in error) {
    const code = String(error.code);
    if (code === "auth/popup-closed-by-user") return "Google sign-in was cancelled.";
    if (code === "auth/popup-blocked") return "Your browser blocked the sign-in window. Allow popups and try again.";
    if (code === "auth/unauthorized-domain") return "This domain is not authorized in Firebase Authentication.";
  }
  return "Could not sign in with Google. Please try again.";
}

function apiSaveMessage(error: unknown) {
  return error instanceof Error
    ? error.message
    : "The extraction completed, but it could not be saved.";
}

function deleteMessage(error: unknown) {
  return error instanceof Error ? error.message : "The invoice could not be deleted.";
}

function Icon({ children, size = 20 }: { children: ReactNode; size?: number }) {
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {children}
    </svg>
  );
}

const InvoiceIcon = ({ size }: { size?: number }) => (
  <Icon size={size}>
    <path d="M6 3h9l3 3v15H6z" />
    <path d="M14 3v4h4M9 11h6M9 15h6M9 19h3" />
  </Icon>
);

const GoogleIcon = () => (
  <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24">
    <path fill="#4285F4" d="M21.6 12.2c0-.7-.1-1.5-.2-2.2H12v4.3h5.4a4.7 4.7 0 0 1-2 3v2.8h3.3c1.9-1.8 2.9-4.4 2.9-7.9Z" />
    <path fill="#34A853" d="M12 22c2.7 0 5-.9 6.7-2.4l-3.3-2.8c-.9.6-2.1 1-3.4 1a5.9 5.9 0 0 1-5.5-4.1H3.1v2.9A10 10 0 0 0 12 22Z" />
    <path fill="#FBBC05" d="M6.5 13.7a6 6 0 0 1 0-3.8V7H3.1A10 10 0 0 0 3.1 16.6l3.4-2.9Z" />
    <path fill="#EA4335" d="M12 5.8c1.5 0 2.8.5 3.8 1.5l2.9-2.8A9.7 9.7 0 0 0 12 2a10 10 0 0 0-8.9 5.5l3.4 2.9A5.9 5.9 0 0 1 12 5.8Z" />
  </svg>
);

function display(value: string | number | null) {
  return value === null || value === "" ? "—" : String(value);
}

function money(value: number | null, currency: string | null) {
  if (value === null) return "—";
  if (currency) {
    try {
      return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(value);
    } catch {
      // Fall through for uncommon currency codes.
    }
  }
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const checkStyle: Record<ConfiguredCheck["status"], { badge: string; card: string; text: string }> = {
  passed: { badge: "badge badge-success", card: "check-card check-card-success", text: "Passed" },
  failed: { badge: "badge badge-danger", card: "check-card check-card-danger", text: "Needs review" },
  not_checked: { badge: "badge badge-neutral", card: "check-card", text: "Not checked" },
};

function ChecksPanel({ checks }: { checks: ConfiguredCheck[] }) {
  if (checks.length === 0) return null;
  const passedCount = checks.filter((check) => check.status === "passed").length;

  return (
    <section className="result-card">
      <div className="section-heading-row">
        <div>
          <h3>Validation checks</h3>
          <p>Extracted fields and amounts compared with the configured rules.</p>
        </div>
        <span className="section-count">{passedCount}/{checks.length} passed</span>
      </div>
      <div className="checks-grid">
        {checks.map((check) => {
          const style = checkStyle[check.status];
          return (
            <article key={check.id} className={style.card}>
              <div className="check-title">
                <h4>{check.label}</h4>
                <span className={style.badge}>{style.text}</span>
              </div>
              <p>{check.detail}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function StatusBlock({ result }: { result: InvoiceResult }) {
  const passed = result.status === "auto_approved";
  return (
    <>
      <section className={`status-card ${passed ? "status-success" : "status-review"}`}>
        <div className="status-icon">
          {passed ? (
            <Icon><path d="m5 12 4 4L19 6" /></Icon>
          ) : (
            <Icon><path d="M12 9v4M12 17h.01" /><path d="M10.3 3.7 2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.7a2 2 0 0 0-3.4 0Z" /></Icon>
          )}
        </div>
        <div>
          <h3>{passed ? "Passed configured checks" : "Invoice needs review"}</h3>
          <p>Extraction completed in {result.attempts} {result.attempts === 1 ? "attempt" : "attempts"}.</p>
          {result.reasons.length > 0 && (
            <ul>{result.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
          )}
        </div>
      </section>
      <ChecksPanel checks={result.checks} />
    </>
  );
}

function InvoiceData({ invoice }: { invoice: Invoice }) {
  const fields: Array<[string, string | number | null]> = [
    ["Vendor", invoice.vendor_name],
    ["Invoice number", invoice.invoice_number],
    ["Invoice date", invoice.invoice_date],
    ["PO number", invoice.po_number],
    ["Currency", invoice.currency],
  ];
  const amounts: Array<[string, number | null]> = [
    ["Subtotal", invoice.subtotal],
    ["Discount", invoice.discount],
    ["Shipping", invoice.shipping],
    ["Tax", invoice.tax],
    ["Total", invoice.total],
  ];

  return (
    <div className="invoice-results">
      <section className="result-card">
        <h3>Invoice details</h3>
        <dl className="details-grid">
          {fields.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{display(value)}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="result-card table-card">
        <div className="table-heading"><h3>Line items</h3></div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Description</th><th>Quantity</th><th>Unit price</th><th>Amount</th></tr></thead>
            <tbody>
              {invoice.line_items.length === 0 && (
                <tr><td colSpan={4} className="empty-cell">No line items extracted.</td></tr>
              )}
              {invoice.line_items.map((item, index) => (
                <tr key={`${item.description}-${index}`}>
                  <td className="primary-cell">{item.description}</td>
                  <td>{display(item.quantity)}</td>
                  <td>{money(item.unit_price, invoice.currency)}</td>
                  <td className="primary-cell">{money(item.amount, invoice.currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="result-card">
        <h3>Amounts</h3>
        <dl className="amount-grid">
          {amounts.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{money(value, invoice.currency)}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}

export default function Home() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<CheckResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [saveError, setSaveError] = useState("");
  const [savedInvoices, setSavedInvoices] = useState<SavedInvoice[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [deletingInvoiceId, setDeletingInvoiceId] = useState("");
  const [deleteError, setDeleteError] = useState("");

  useEffect(() => onAuthStateChanged(auth, (nextUser) => {
    setUser(nextUser);
    setAuthReady(true);
  }), []);

  useEffect(() => {
    if (!user) {
      setSavedInvoices([]);
      setHistoryLoading(false);
      return;
    }

    setHistoryLoading(true);
    setHistoryError("");
    let cancelled = false;
    listInvoices(20).then((records) => {
      if (!cancelled) setSavedInvoices(records);
    }).catch((loadError) => {
      if (!cancelled) setHistoryError(loadError instanceof Error ? loadError.message : "Invoices could not be loaded.");
    }).finally(() => {
      if (!cancelled) setHistoryLoading(false);
    });
    return () => { cancelled = true; };
  }, [user]);

  useEffect(() => {
    if (!uploadModalOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (!loading) setUploadModalOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    document.body.classList.add("modal-open");
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.classList.remove("modal-open");
    };
  }, [uploadModalOpen, loading]);

  function openUploadModal() {
    setFile(null);
    setResult(null);
    setError("");
    setSaveState("idle");
    setSaveError("");
    if (inputRef.current) inputRef.current.value = "";
    setUploadModalOpen(true);
  }

  function closeUploadModal() {
    if (loading) return;
    setUploadModalOpen(false);
  }

  async function loginWithGoogle() {
    if (authLoading) return;
    setAuthLoading(true);
    setAuthError("");
    try {
      const provider = new GoogleAuthProvider();
      provider.setCustomParameters({ prompt: "select_account" });
      const credential = await signInWithPopup(auth, provider);
      await syncUserProfile(credential.user);
    } catch (caught) {
      setAuthError(authMessage(caught));
    } finally {
      setAuthLoading(false);
    }
  }

  async function logout() {
    await signOut(auth);
    setFile(null);
    setResult(null);
    setSaveState("idle");
    setSaveError("");
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const nextFile = event.target.files?.[0] || null;
    setResult(null);
    setError("");
    setSaveState("idle");
    setSaveError("");
    if (!nextFile) { setFile(null); return; }

    const lowerName = nextFile.name.toLowerCase();
    if (!lowerName.endsWith(".pdf") && !lowerName.endsWith(".zip")) {
      setFile(null);
      setError("Choose a PDF or ZIP file to continue.");
      event.target.value = "";
      return;
    }
    if (nextFile.size > MAX_FILE_BYTES) {
      setFile(null);
      setError("The selected file is larger than the 20 MB upload limit.");
      event.target.value = "";
      return;
    }
    setFile(nextFile);
  }

  async function submit() {
    if (!file || !user || loading) return;
    setLoading(true);
    setError("");
    setResult(null);
    setSaveState("idle");
    setSaveError("");
    try {
      const extractedResult = await checkInvoice(file);
      const matchOne = async (invoiceResult: InvoiceResult): Promise<InvoiceResult> => {
        const twoWayMatch = await matchSavedPurchaseOrder(invoiceResult.invoice);
        if (twoWayMatch.status === "matched") return { ...invoiceResult, two_way_match: twoWayMatch };
        return {
          ...invoiceResult,
          status: "needs_review",
          reasons: [...invoiceResult.reasons, ...twoWayMatch.reasons],
          two_way_match: twoWayMatch,
        };
      };

      let checkedResult: CheckResult;
      if (isBatchResult(extractedResult)) {
        const files = [];
        for (const batchFile of extractedResult.files) {
          files.push(batchFile.result
            ? { ...batchFile, result: await matchOne(batchFile.result) }
            : batchFile);
        }
        checkedResult = { ...extractedResult, files };
      } else {
        checkedResult = await matchOne(extractedResult);
      }
      setResult(checkedResult);
      setSaveState("saving");
      try {
        const saved = await saveInvoice({
          fileName: file.name,
          fileType: selectedIsZip ? "zip" : "pdf",
          fileSizeBytes: file.size,
          status: isBatchResult(checkedResult) ? "batch_complete" : checkedResult.status,
          result: checkedResult,
        });
        setSavedInvoices((current) => [saved, ...current].slice(0, 20));
        setSaveState("saved");
        setUploadModalOpen(false);
        setFile(null);
        setResult(null);
      } catch (saveFailure) {
        setSaveState("error");
        setSaveError(apiSaveMessage(saveFailure));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The invoice file could not be checked.");
    } finally {
      setLoading(false);
    }
  }

  function downloadJson(downloadResult: CheckResult, downloadFileName: string) {
    const blob = new Blob([JSON.stringify(downloadResult, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${downloadFileName.replace(/\.(pdf|zip)$/i, "") || "invoice"}-result.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function deleteInvoice(row: InvoiceTableRow) {
    if (!user || deletingInvoiceId) return;
    const invoiceLabel = row.result.invoice.invoice_number || row.fileName;
    const saved = savedInvoices.find((item) => item.id === row.recordId);
    if (!saved) return;
    const batchCopy = row.batchIndex === null
      ? ""
      : " Only this invoice will be removed from its ZIP batch.";
    if (!window.confirm(`Delete ${invoiceLabel}?${batchCopy} This cannot be undone.`)) return;

    setDeletingInvoiceId(row.id);
    setDeleteError("");
    try {
      if (row.batchIndex === null || !isBatchResult(saved.result)) {
        await deleteSavedInvoice(row.recordId);
        setSavedInvoices((current) => current.filter((item) => item.id !== row.recordId));
      } else {
        const remainingFiles = saved.result.files.filter((_, index) => index !== row.batchIndex);
        if (remainingFiles.length === 0) {
          await deleteSavedInvoice(row.recordId);
          setSavedInvoices((current) => current.filter((item) => item.id !== row.recordId));
        } else {
          const succeeded = remainingFiles.filter((item) => item.result !== null).length;
          const updated = await updateSavedInvoice(row.recordId, {
            result: {
              ...saved.result,
              summary: {
                total: remainingFiles.length,
                succeeded,
                failed: remainingFiles.length - succeeded,
              },
              files: remainingFiles,
            },
            status: "batch_complete",
          });
          setSavedInvoices((current) => current.map((item) => item.id === updated.id ? updated : item));
        }
      }
    } catch (deleteFailure) {
      setDeleteError(deleteMessage(deleteFailure));
    } finally {
      setDeletingInvoiceId("");
    }
  }

  const selectedIsZip = file?.name.toLowerCase().endsWith(".zip") ?? false;
  const invoiceRows = savedInvoices.flatMap<InvoiceTableRow>((saved) => {
    if (!isBatchResult(saved.result)) {
      return [{ id: saved.id, recordId: saved.id, batchIndex: null, fileName: saved.fileName, createdAt: saved.createdAt, result: saved.result }];
    }
    return saved.result.files.flatMap((item, index) => item.result ? [{
      id: `${saved.id}-${index}`,
      recordId: saved.id,
      batchIndex: index,
      fileName: item.filename,
      createdAt: saved.createdAt,
      result: item.result,
    }] : []);
  });

  if (!authReady) {
    return (
      <main className="auth-screen">
        <div className="auth-loader"><span className="spinner" /> Loading Invoice Agent…</div>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="auth-screen">
        <section className="login-card">
          <div className="login-brand">
            <span className="brand-mark"><InvoiceIcon size={25} /></span>
            <span>Invoice<span className="brand-dot">.</span></span>
          </div>
          <div className="login-art" aria-hidden="true">
            <span className="login-document"><InvoiceIcon size={38} /></span>
            <span className="login-check"><Icon size={21}><path d="m5 12 4 4L19 6" /></Icon></span>
          </div>
          <p className="eyebrow">Welcome</p>
          <h1>Sign in to your invoice workspace</h1>
          <p className="login-description">Securely check invoices and keep every extraction saved to your private workspace.</p>
          <button type="button" className="google-button" onClick={loginWithGoogle} disabled={authLoading}>
            {authLoading ? <span className="spinner dark-spinner" /> : <GoogleIcon />}
            {authLoading ? "Connecting…" : "Continue with Google"}
          </button>
          {authError && <div role="alert" className="error-message auth-error">{authError}</div>}
          <p className="login-note"><Icon size={14}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /></Icon> Your saved invoices are only available to your account.</p>
        </section>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark"><InvoiceIcon size={23} /></span>
          <span>Invoice<span className="brand-dot">.</span></span>
        </div>

        <nav aria-label="Main navigation">
          <p className="nav-label">Workspace</p>
          <a className="nav-item" href="/dashboard">
            <Icon size={19}><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" /></Icon>
            <span>Dashboard</span>
          </a>
          <a className="nav-item active" href="#invoice-workspace" aria-current="page">
            <InvoiceIcon size={19} />
            <span>Two way match</span>
          </a>
          <a className="nav-item" href="/invoice-analyzer">
            <Icon size={19}><path d="M4 19V5a2 2 0 0 1 2-2h8l4 4v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z" /><path d="M14 3v5h5M8 13h8M8 17h5" /></Icon>
            <span>Invoice analyzer</span>
          </a>
          <a className="nav-item" href="/purchase-orders">
            <Icon size={19}><path d="M6 3h12v18H6z" /><path d="M9 8h6M9 12h6M9 16h4" /></Icon>
            <span>Purchase orders</span>
          </a>
        </nav>

        <div className="sidebar-footer">
          {user.photoURL ? (
            <img className="mini-avatar" src={user.photoURL} alt="" referrerPolicy="no-referrer" />
          ) : (
            <div className="mini-avatar">{(user.displayName || user.email || "U").slice(0, 1).toUpperCase()}</div>
          )}
          <div className="account-copy">
            <strong>{user.displayName || "Google account"}</strong>
            <span>{user.email}</span>
          </div>
          <button type="button" className="signout-button" onClick={logout} aria-label="Sign out" title="Sign out">
            <Icon size={17}><path d="M10 17l5-5-5-5M15 12H3" /><path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5" /></Icon>
          </button>
        </div>
      </aside>

      <main className="main-content" id="invoice-workspace">
        <header className="page-header">
          <div>
            <p className="eyebrow">Overview</p>
            <h1>Two way match</h1>
            <p>Upload invoices, review extracted data and catch issues before payment.</p>
          </div>
          <button className="primary-button header-button" type="button" onClick={openUploadModal}>
            <Icon size={18}><path d="M12 5v14M5 12h14" /></Icon>
            Upload invoice
          </button>
        </header>

        <section className="intro-banner">
          <div className="banner-icon"><Icon size={23}><path d="M12 3v18M3 12h18M5.6 5.6l12.8 12.8M18.4 5.6 5.6 18.4" /></Icon></div>
          <div className="banner-copy">
            <h2>Fast, reliable invoice checks</h2>
            <p>Upload a PDF or a ZIP batch and let the agent extract and validate every invoice.</p>
          </div>
          <span className="banner-pill">Up to 10 invoices</span>
        </section>

        <section className="invoice-table-card">
          <div className="invoice-table-heading">
            <div>
              <p className="eyebrow">Workspace API</p>
              <h2>All extracted invoices</h2>
              <p>Review invoice details and resolve anything flagged for human review.</p>
            </div>
            <span className="invoice-count">{invoiceRows.length} {invoiceRows.length === 1 ? "invoice" : "invoices"}</span>
          </div>

          {historyLoading && <div className="table-state"><span className="spinner dark-spinner" />Loading saved invoices…</div>}
          {historyError && <div role="alert" className="error-message table-error">{historyError}</div>}
          {deleteError && <div role="alert" className="error-message table-error">{deleteError}</div>}

          {!historyLoading && !historyError && invoiceRows.length === 0 && (
            <div className="table-empty">
              <div className="empty-icon"><InvoiceIcon size={26} /></div>
              <h3>No extracted invoices yet</h3>
              <p>Upload a PDF or ZIP file to create your first invoice record.</p>
              <button type="button" className="secondary-button" onClick={openUploadModal}>Upload invoice</button>
            </div>
          )}

          {!historyLoading && invoiceRows.length > 0 && (
            <div className="invoice-table-scroll">
              <table className="invoice-list-table">
                <thead>
                  <tr>
                    <th>Invoice</th>
                    <th>Vendor</th>
                    <th>Invoice date</th>
                    <th>Total</th>
                    <th>Status</th>
                    <th>PO match</th>
                    <th>Uploaded</th>
                    <th><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {invoiceRows.map((row) => {
                    const invoice = row.result.invoice;
                    return (
                      <tr key={row.id}>
                        <td>
                          <div className="invoice-identity">
                            <span className="table-file-icon"><InvoiceIcon size={18} /></span>
                            <span><strong>{invoice.invoice_number || "No invoice number"}</strong><small>{row.fileName}</small></span>
                          </div>
                        </td>
                        <td className="vendor-cell">{invoice.vendor_name || "Unknown vendor"}</td>
                        <td>{invoice.invoice_date || "—"}</td>
                        <td className="total-cell">{money(invoice.total, invoice.currency)}</td>
                        <td>
                          <span className={`review-flag ${row.result.status === "auto_approved" ? "verified" : "needs-review"}`}>
                            <span className="status-dot" />
                            {row.result.status === "auto_approved" ? "Verified" : "Human review needed"}
                          </span>
                        </td>
                        <td>
                          {row.result.two_way_match?.purchase_order_id ? (
                            <button
                              type="button"
                              className={`review-flag po-match-link ${row.result.two_way_match.status === "matched" ? "verified" : "needs-review"}`}
                              onClick={() => router.push(`/purchase-orders/${row.result.two_way_match?.purchase_order_id}`)}
                              title="Open matched purchase order"
                            >
                              <span className="status-dot" />
                              {row.result.two_way_match.status === "matched" ? "Matched · View PO" : "Review · View PO"}
                            </button>
                          ) : (
                            <span className="review-flag needs-review">
                              <span className="status-dot" />
                              {!row.result.two_way_match ? "Not checked" :
                                row.result.two_way_match.status === "po_not_found" ? "PO not found" :
                                row.result.two_way_match.status === "ambiguous_po" ? "Ambiguous PO" :
                                row.result.two_way_match.status === "po_unavailable" ? "PO unavailable" : "Mismatch"}
                            </span>
                          )}
                        </td>
                        <td>{row.createdAt ? new Date(row.createdAt).toLocaleDateString() : "Just now"}</td>
                        <td>
                          <div className="table-row-actions">
                            <button
                              type="button"
                              className="view-button"
                              onClick={() => router.push(`/invoices/${row.recordId}${row.batchIndex === null ? "" : `?item=${row.batchIndex}`}`)}
                            >
                              View
                            </button>
                            <button type="button" className="view-button delete-button" disabled={deletingInvoiceId === row.id} onClick={() => deleteInvoice(row)}>{deletingInvoiceId === row.id ? "Deleting…" : "Delete"}</button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <footer>Validation results support review and do not constitute payment authorization.</footer>
      </main>

      {uploadModalOpen && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) closeUploadModal();
        }}>
          <section className="modal-card upload-modal" role="dialog" aria-modal="true" aria-labelledby="upload-title">
            <div className="modal-header">
              <div>
                <p className="eyebrow">New extraction</p>
                <h2 id="upload-title">Upload invoice</h2>
                <p>Choose one PDF or a ZIP containing up to 10 invoices.</p>
              </div>
              <button type="button" className="modal-close" onClick={closeUploadModal} disabled={loading} aria-label="Close upload dialog">
                <Icon size={20}><path d="m6 6 12 12M18 6 6 18" /></Icon>
              </button>
            </div>

            <div className="modal-body">
              <div className="secure-strip"><Icon size={16}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /><path d="m9 12 2 2 4-4" /></Icon>Secure upload · PDF or ZIP · Maximum 20 MB</div>
              <button type="button" className={`upload-zone modal-upload-zone ${file ? "has-file" : ""}`} onClick={() => inputRef.current?.click()} disabled={loading}>
                <span className="upload-icon"><Icon size={27}><path d="M12 16V4M7 9l5-5 5 5" /><path d="M5 14v5h14v-5" /></Icon></span>
                <span className="upload-copy">
                  <strong>{file ? file.name : "Drop your invoice here, or browse"}</strong>
                  <small>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB · ${selectedIsZip ? "ZIP batch" : "PDF invoice"}` : "Text-based PDF and ZIP files are supported"}</small>
                </span>
                <span className="browse-button">Browse files</span>
              </button>
              <input ref={inputRef} id="invoice" type="file" accept="application/pdf,application/zip,application/x-zip-compressed,.pdf,.zip" onChange={onFileChange} className="sr-only" />

              {error && <div role="alert" className="error-message"><Icon size={18}><path d="M12 9v4M12 17h.01" /><circle cx="12" cy="12" r="9" /></Icon>{error}</div>}
              {saveState === "saving" && <div className="save-notice"><span className="spinner dark-spinner" />Saving extraction…</div>}
              {saveState === "error" && <div role="alert" className="error-message"><Icon size={18}><path d="M12 9v4M12 17h.01" /><circle cx="12" cy="12" r="9" /></Icon>{saveError}</div>}
            </div>

            <div className="modal-actions">
              <button type="button" className="secondary-button" onClick={closeUploadModal} disabled={loading}>Cancel</button>
              <button type="button" disabled={!file || loading} onClick={submit} className="primary-button check-button">
                {loading ? <span className="spinner" /> : <Icon size={18}><path d="m5 12 4 4L19 6" /></Icon>}
                {loading ? (saveState === "saving" ? "Saving…" : "Extracting…") : selectedIsZip ? "Extract & match batch" : "Extract & match invoice"}
              </button>
            </div>
          </section>
        </div>
      )}

    </div>
  );
}
