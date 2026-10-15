"use client";

import Link from "next/link";
import { ReactNode, useEffect, useMemo, useState } from "react";
import { onAuthStateChanged, signOut, User } from "firebase/auth";

import {
  deleteSavedGmailInvoice,
  disconnectGmail,
  fetchGmailAttachment,
  fetchSavedGmailInvoiceFile,
  getGmailStatus,
  GmailAttachment,
  GmailMessage,
  GmailStatus,
  listSavedGmailInvoices,
  SavedGmailInvoice,
  searchGmailInvoices,
  startGmailConnect,
} from "@/lib/api";
import { auth } from "@/lib/firebase";

function Icon({ children, size = 20 }: { children: ReactNode; size?: number }) {
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {children}
    </svg>
  );
}

function MailIcon({ size = 20 }: { size?: number }) {
  return <Icon size={size}><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></Icon>;
}

function sizeLabel(size: number | null) {
  if (size === null) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function isAlreadyStored(message: GmailMessage) {
  return message.attachments.length > 0 && message.attachments.every((attachment) => attachment.saved_status === "existing");
}

function receivedLabel(value: string | null) {
  if (!value) return "Unknown";
  return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function GmailConnectPage() {
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [status, setStatus] = useState<GmailStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [busy, setBusy] = useState<"" | "connect" | "disconnect" | "fetch">("");
  const [notice, setNotice] = useState<{ level: "success" | "error"; text: string } | null>(null);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [messages, setMessages] = useState<GmailMessage[] | null>(null);
  const [filter, setFilter] = useState("");
  const [hideStored, setHideStored] = useState(false);
  const [downloading, setDownloading] = useState("");
  const [saved, setSaved] = useState<SavedGmailInvoice[]>([]);
  const [savedLoading, setSavedLoading] = useState(false);
  const [deletingId, setDeletingId] = useState("");

  useEffect(() => onAuthStateChanged(auth, (nextUser) => {
    setUser(nextUser);
    setAuthReady(true);
  }), []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const outcome = params.get("gmail");
    if (!outcome) return;
    if (outcome === "connected") {
      const email = params.get("email");
      setNotice({ level: "success", text: email ? `Gmail connected as ${email}.` : "Gmail connected." });
    } else {
      setNotice({ level: "error", text: params.get("message") || "Could not connect Gmail." });
    }
    window.history.replaceState(null, "", window.location.pathname);
  }, []);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    setStatusLoading(true);
    getGmailStatus().then((next) => {
      if (!cancelled) setStatus(next);
    }).catch((error) => {
      if (!cancelled) setNotice({ level: "error", text: error instanceof Error ? error.message : "Could not load Gmail status." });
    }).finally(() => {
      if (!cancelled) setStatusLoading(false);
    });
    return () => { cancelled = true; };
  }, [user]);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    setSavedLoading(true);
    listSavedGmailInvoices().then((records) => {
      if (!cancelled) setSaved(records);
    }).catch((error) => {
      if (!cancelled) setNotice({ level: "error", text: error instanceof Error ? error.message : "Could not load saved invoices." });
    }).finally(() => {
      if (!cancelled) setSavedLoading(false);
    });
    return () => { cancelled = true; };
  }, [user]);

  const visibleMessages = useMemo(() => {
    if (!messages) return [];
    const needle = filter.trim().toLowerCase();
    return messages.filter((message) =>
      (!hideStored || !isAlreadyStored(message))
      && (!needle || `${message.sender} ${message.subject}`.toLowerCase().includes(needle)));
  }, [messages, filter, hideStored]);

  async function connect() {
    setBusy("connect");
    setNotice(null);
    try {
      const { url } = await startGmailConnect();
      window.location.assign(url);
    } catch (error) {
      setNotice({ level: "error", text: error instanceof Error ? error.message : "Could not start Google sign-in." });
      setBusy("");
    }
  }

  async function disconnect() {
    if (!window.confirm("Disconnect Gmail? Access will be revoked and the stored token deleted.")) return;
    setBusy("disconnect");
    setNotice(null);
    try {
      await disconnectGmail();
      setStatus((current) => current && { ...current, connected: false, email: null });
      setMessages(null);
      setNotice({ level: "success", text: "Gmail disconnected." });
    } catch (error) {
      setNotice({ level: "error", text: error instanceof Error ? error.message : "Could not disconnect Gmail." });
    } finally {
      setBusy("");
    }
  }

  async function fetchInvoices() {
    setBusy("fetch");
    setNotice(null);
    try {
      const result = await searchGmailInvoices(dateFrom, dateTo);
      setMessages(result.messages);
      const count = result.messages.length;
      let text = count === 0
        ? "No potential invoices found. Try a wider date range."
        : `Found ${count} potential invoice email${count === 1 ? "" : "s"}. Saved ${result.saved_new} new file${result.saved_new === 1 ? "" : "s"}.`;
      if (result.already_saved) text += ` ${result.already_saved} already saved.`;
      if (result.failed) text += ` ${result.failed} could not be saved.`;
      setNotice({ level: "success", text });
      if (result.saved_new) setSaved(await listSavedGmailInvoices());
    } catch (error) {
      const text = error instanceof Error ? error.message : "Could not fetch invoices.";
      setNotice({ level: "error", text });
      if (text.includes("Connect Gmail again") || text.includes("not connected")) {
        setStatus((current) => current && { ...current, connected: false, email: null });
      }
    } finally {
      setBusy("");
    }
  }

  async function showFile(key: string, fileName: string, mode: "open" | "download", load: () => Promise<Blob>) {
    setDownloading(key);
    setNotice(null);
    try {
      const url = URL.createObjectURL(await load());
      if (mode === "open") {
        window.open(url, "_blank", "noopener");
      } else {
        const link = document.createElement("a");
        link.href = url;
        link.download = fileName;
        link.click();
      }
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      setNotice({ level: "error", text: error instanceof Error ? error.message : "The file could not be opened." });
    } finally {
      setDownloading("");
    }
  }

  function openAttachment(message: GmailMessage, attachment: GmailAttachment, mode: "open" | "download") {
    const savedId = attachment.saved_id;
    return showFile(
      `${message.id}:${attachment.part_id}`,
      attachment.filename,
      mode,
      savedId ? () => fetchSavedGmailInvoiceFile(savedId) : () => fetchGmailAttachment(message.id, attachment.part_id),
    );
  }

  async function removeSaved(record: SavedGmailInvoice) {
    if (!window.confirm(`Delete ${record.fileName} from the invoice folder? The email in Gmail is not affected.`)) return;
    setDeletingId(record.id);
    setNotice(null);
    try {
      await deleteSavedGmailInvoice(record.id);
      setSaved((current) => current.filter((item) => item.id !== record.id));
      setMessages((current) => current && current.map((message) => ({
        ...message,
        attachments: message.attachments.map((attachment) => attachment.saved_id === record.id ? { ...attachment, saved_id: null, saved_status: null } : attachment),
      })));
    } catch (error) {
      setNotice({ level: "error", text: error instanceof Error ? error.message : "The saved invoice could not be deleted." });
    } finally {
      setDeletingId("");
    }
  }

  if (!authReady) return <main className="review-state"><span className="spinner dark-spinner" /><p>Loading…</p></main>;
  if (!user) return (
    <main className="review-state">
      <span className="review-state-icon"><MailIcon size={25} /></span>
      <h1>Sign in required</h1>
      <p>Sign in from the invoice workspace to connect Gmail.</p>
      <Link className="primary-button review-back-button" href="/">Go to sign in</Link>
    </main>
  );

  const connected = Boolean(status?.connected);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><MailIcon size={23} /></span><span>Invoice<span className="brand-dot">.</span></span></div>
        <nav aria-label="Main navigation">
          <p className="nav-label">Workspace</p>
          <Link className="nav-item" href="/dashboard"><Icon size={19}><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" /></Icon><span>Dashboard</span></Link>
          <Link className="nav-item" href="/"><Icon size={19}><path d="M6 3h9l3 3v15H6z" /><path d="M14 3v4h4M9 11h6M9 15h6" /></Icon><span>Two way match</span></Link>
          <Link className="nav-item" href="/invoice-analyzer"><Icon size={19}><path d="M4 19V5a2 2 0 0 1 2-2h8l4 4v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z" /><path d="M14 3v5h5M8 13h8M8 17h5" /></Icon><span>Invoice analyzer</span></Link>
          <Link className="nav-item" href="/purchase-orders"><Icon size={19}><path d="M6 3h12v18H6z" /><path d="M9 8h6M9 12h6M9 16h4" /></Icon><span>Purchase orders</span></Link>
          <Link className="nav-item active" href="/gmail-connect" aria-current="page"><MailIcon size={19} /><span>Gmail Connect</span></Link>
        </nav>
        <div className="sidebar-footer">
          {user.photoURL ? <img className="mini-avatar" src={user.photoURL} alt="" referrerPolicy="no-referrer" /> : <div className="mini-avatar">{(user.displayName || "U")[0]}</div>}
          <div className="account-copy"><strong>{user.displayName || "Google account"}</strong><span>{user.email}</span></div>
          <button type="button" className="signout-button" onClick={() => signOut(auth)} aria-label="Sign out"><Icon size={17}><path d="M10 17l5-5-5-5M15 12H3" /><path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5" /></Icon></button>
        </div>
      </aside>

      <main className="main-content">
        <header className="page-header">
          <div><p className="eyebrow">Integrations</p><h1>Gmail Connect</h1><p>Find invoice emails in your Gmail and download their PDF or image attachments.</p></div>
          {connected
            ? <button className="secondary-button header-button" type="button" onClick={disconnect} disabled={busy !== ""}>{busy === "disconnect" ? "Disconnecting…" : "Disconnect"}</button>
            : <button className="primary-button header-button" type="button" onClick={connect} disabled={busy !== "" || statusLoading || status?.configured === false}>{busy === "connect" ? <span className="spinner" /> : <MailIcon size={18} />}Connect Gmail</button>}
        </header>

        <section className="intro-banner">
          <div className="banner-icon"><MailIcon size={23} /></div>
          <div className="banner-copy">
            <h2>{connected ? `Connected${status?.email ? ` as ${status.email}` : ""}` : "Connect your inbox"}</h2>
            <p>
              {status?.configured === false
                ? "Gmail is not configured on the server. Add the Google OAuth keys to backend/.env.local."
                : "Read-only access. The app cannot send, delete, or change mail. Fetched invoice attachments are saved to your private invoice folder."}
            </p>
          </div>
          <span className="banner-pill">{statusLoading ? "Checking…" : connected ? "Connected" : "Not connected"}</span>
        </section>

        {notice && <div role={notice.level === "error" ? "alert" : "status"} className={notice.level === "error" ? "error-message gmail-notice" : "gmail-notice gmail-success"}>{notice.text}</div>}

        <section className="invoice-table-card">
          <div className="invoice-table-heading">
            <div><p className="eyebrow">Gmail search</p><h2>Potential invoice emails</h2><p>Matches emails with attachments that mention invoice, receipt, or billing. Spam and trash are skipped.</p></div>
            {messages && <span className="invoice-count">{visibleMessages.length} emails</span>}
          </div>
          <div className="gmail-filters">
            <label>From<input type="date" value={dateFrom} max={dateTo || undefined} onChange={(event) => setDateFrom(event.target.value)} disabled={!connected} /></label>
            <label>To<input type="date" value={dateTo} min={dateFrom || undefined} onChange={(event) => setDateTo(event.target.value)} disabled={!connected} /></label>
            <button type="button" className="primary-button" onClick={fetchInvoices} disabled={!connected || busy !== ""}>{busy === "fetch" ? <span className="spinner" /> : <Icon size={18}><path d="M12 4v12M7 11l5 5 5-5" /><path d="M5 20h14" /></Icon>}{busy === "fetch" ? "Fetching…" : "Fetch invoices"}</button>
            {messages && messages.some(isAlreadyStored) && <label className="gmail-toggle"><input type="checkbox" checked={hideStored} onChange={(event) => setHideStored(event.target.checked)} />Hide already stored</label>}
            {messages && messages.length > 0 && <input className="gmail-search" type="search" placeholder="Filter by sender or subject" value={filter} onChange={(event) => setFilter(event.target.value)} />}
          </div>

          {!connected ? (
            <div className="table-empty"><div className="empty-icon"><MailIcon size={26} /></div><h3>Gmail is not connected</h3><p>Connect Gmail to search for invoice emails.</p></div>
          ) : busy === "fetch" ? (
            <div className="table-state"><span className="spinner dark-spinner" />Searching Gmail…</div>
          ) : messages === null ? (
            <div className="table-empty"><div className="empty-icon"><MailIcon size={26} /></div><h3>No search yet</h3><p>Pick an optional date range and click Fetch invoices.</p></div>
          ) : visibleMessages.length === 0 ? (
            <div className="table-empty"><div className="empty-icon"><MailIcon size={26} /></div><h3>No matching emails</h3><p>Try a wider date range or clear the filter.</p></div>
          ) : (
            <div className="invoice-table-scroll"><table className="invoice-list-table"><thead><tr><th>Received</th><th>From</th><th>Subject</th><th>Attachments</th></tr></thead><tbody>
              {visibleMessages.map((message) => <tr key={message.id}>
                <td className="gmail-received">{receivedLabel(message.received)}</td>
                <td className="vendor-cell" title={message.sender}>{message.sender}</td>
                <td className="gmail-subject">
                  <strong title={message.subject}>{message.subject}</strong>
                  {isAlreadyStored(message) && <span className="review-flag needs-review gmail-row-flag"><span className="status-dot" />Already stored</span>}
                  {message.note && <small>{message.note}</small>}
                </td>
                <td>
                  {message.attachments.length === 0 ? <span className="gmail-muted">None supported</span> : <div className="gmail-attachments">
                    {message.attachments.map((attachment) => {
                      const key = `${message.id}:${attachment.part_id}`;
                      return <div key={key} className="gmail-attachment">
                        <span className="table-file-icon"><Icon size={16}><path d="M6 3h9l3 3v15H6z" /><path d="M14 3v4h4" /></Icon></span>
                        <span className="gmail-attachment-name"><strong title={attachment.filename}>{attachment.filename}</strong><small>{sizeLabel(attachment.size)}</small></span>
                        {attachment.saved_status === "existing" && <span className="review-flag needs-review" title="This attachment was stored on an earlier fetch"><span className="status-dot" />Already saved</span>}
                        {attachment.saved_status === "new" && <span className="review-flag verified"><span className="status-dot" />New</span>}
                        <div className="table-row-actions">
                          <button type="button" className="view-button" disabled={downloading === key} onClick={() => openAttachment(message, attachment, "open")}>View</button>
                          <button type="button" className="view-button" disabled={downloading === key} onClick={() => openAttachment(message, attachment, "download")}>{downloading === key ? "…" : "Download"}</button>
                        </div>
                      </div>;
                    })}
                  </div>}
                </td>
              </tr>)}
            </tbody></table></div>
          )}
        </section>

        <section className="invoice-table-card">
          <div className="invoice-table-heading">
            <div><p className="eyebrow">Invoice folder</p><h2>Saved invoices</h2><p>Attachments saved from Gmail. Files are kept in the invoice folder and their details in Firestore.</p></div>
            <span className="invoice-count">{saved.length} files</span>
          </div>
          {savedLoading ? (
            <div className="table-state"><span className="spinner dark-spinner" />Loading saved invoices…</div>
          ) : saved.length === 0 ? (
            <div className="table-empty"><div className="empty-icon"><Icon size={26}><path d="M6 3h9l3 3v15H6z" /><path d="M14 3v4h4" /></Icon></div><h3>No saved invoices yet</h3><p>Fetch invoices from Gmail to save their attachments here.</p></div>
          ) : (
            <div className="invoice-table-scroll"><table className="invoice-list-table"><thead><tr><th>File</th><th>From</th><th>Subject</th><th>Received</th><th>Saved</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>
              {saved.map((record) => <tr key={record.id}>
                <td><div className="invoice-identity"><span className="table-file-icon"><Icon size={18}><path d="M6 3h9l3 3v15H6z" /><path d="M14 3v4h4" /></Icon></span><span><strong title={record.fileName}>{record.fileName}</strong><small>{sizeLabel(record.sizeBytes)}</small></span></div></td>
                <td className="vendor-cell" title={record.sender}>{record.sender}</td>
                <td className="gmail-subject"><strong title={record.subject}>{record.subject}</strong></td>
                <td className="gmail-received">{receivedLabel(record.receivedAt)}</td>
                <td className="gmail-received">{record.createdAt ? record.createdAt.toLocaleDateString() : "Just now"}</td>
                <td><div className="table-row-actions">
                  <button type="button" className="view-button" disabled={downloading === record.id} onClick={() => showFile(record.id, record.fileName, "open", () => fetchSavedGmailInvoiceFile(record.id))}>View</button>
                  <button type="button" className="view-button" disabled={downloading === record.id} onClick={() => showFile(record.id, record.fileName, "download", () => fetchSavedGmailInvoiceFile(record.id))}>Download</button>
                  <button type="button" className="view-button delete-button" disabled={deletingId === record.id} onClick={() => removeSaved(record)}>{deletingId === record.id ? "Deleting…" : "Delete"}</button>
                </div></td>
              </tr>)}
            </tbody></table></div>
          )}
        </section>
        <footer>Search results are potential invoices only. A keyword match does not confirm an email is a real invoice.</footer>
      </main>
    </div>
  );
}
