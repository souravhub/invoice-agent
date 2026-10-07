"use client";

import { ChangeEvent, useRef, useState } from "react";

import { checkInvoice, InvoiceResult } from "@/lib/api";

const MAX_FILE_BYTES = 20 * 1024 * 1024;

function display(value: string | number | null) {
  return value === null || value === "" ? "—" : String(value);
}

function money(value: number | null, currency: string | null) {
  if (value === null) return "—";
  if (currency) {
    try {
      return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(value);
    } catch {
      // Fall through for an invalid or uncommon currency code.
    }
  }
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function Home() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<InvoiceResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const nextFile = event.target.files?.[0] || null;
    setResult(null);
    setError("");

    if (!nextFile) {
      setFile(null);
      return;
    }
    if (nextFile.type !== "application/pdf" && !nextFile.name.toLowerCase().endsWith(".pdf")) {
      setFile(null);
      setError("Choose a PDF file to continue.");
      event.target.value = "";
      return;
    }
    if (nextFile.size > MAX_FILE_BYTES) {
      setFile(null);
      setError("The PDF is larger than the 20 MB upload limit.");
      event.target.value = "";
      return;
    }
    setFile(nextFile);
  }

  async function submit() {
    if (!file || loading) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      setResult(await checkInvoice(file));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The invoice could not be checked.");
    } finally {
      setLoading(false);
    }
  }

  function downloadJson() {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${file?.name.replace(/\.pdf$/i, "") || "invoice"}-result.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const invoice = result?.invoice;

  return (
    <main className="mx-auto min-h-screen w-full max-w-6xl px-4 py-8 sm:px-6 sm:py-12">
      <header className="mb-8 max-w-3xl sm:mb-10">
        <p className="mb-3 text-xs font-bold uppercase tracking-[0.22em] text-emerald-700">
          Invoice agent
        </p>
        <h1 className="text-4xl font-semibold tracking-[-0.04em] text-slate-900 sm:text-5xl">
          Check an invoice before it moves forward.
        </h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600 sm:text-lg">
          Upload one text-based PDF to extract its details and run the configured completeness and
          arithmetic checks.
        </p>
      </header>

      <section className="rounded-3xl border border-slate-200 bg-white/90 p-5 shadow-[0_20px_70px_rgba(35,55,45,0.08)] sm:p-8">
        <div className="grid gap-5 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <label htmlFor="invoice" className="mb-2 block text-sm font-semibold text-slate-800">
              Invoice PDF
            </label>
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="flex min-h-28 w-full cursor-pointer items-center justify-between gap-4 rounded-2xl border border-dashed border-emerald-300 bg-emerald-50/60 px-5 text-left transition hover:border-emerald-500 hover:bg-emerald-50"
            >
              <span>
                <span className="block font-semibold text-slate-900">
                  {file ? file.name : "Choose a PDF"}
                </span>
                <span className="mt-1 block text-sm text-slate-600">
                  {file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : "One file, up to 20 MB"}
                </span>
              </span>
              <span aria-hidden="true" className="rounded-full bg-white px-4 py-2 text-sm font-bold text-emerald-700 shadow-sm">
                Browse
              </span>
            </button>
            <input
              ref={inputRef}
              id="invoice"
              type="file"
              accept="application/pdf,.pdf"
              onChange={onFileChange}
              className="sr-only"
            />
          </div>
          <button
            type="button"
            disabled={!file || loading}
            onClick={submit}
            className="inline-flex h-12 min-w-44 items-center justify-center gap-2 rounded-xl bg-emerald-700 px-6 font-bold text-white transition hover:bg-emerald-800 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {loading && <span className="size-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />}
            {loading ? "Checking…" : "Check invoice"}
          </button>
        </div>

        {error && (
          <div role="alert" className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        )}
      </section>

      {result && invoice && (
        <div className="mt-7 space-y-6">
          <section className={`rounded-3xl border p-5 sm:p-7 ${result.status === "auto_approved" ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
              <div>
                <p className="text-xl font-bold text-slate-900">
                  {result.status === "auto_approved" ? "Passed configured checks" : "Needs review"}
                </p>
                <p className="mt-1 text-sm text-slate-600">
                  Extraction completed in {result.attempts} {result.attempts === 1 ? "attempt" : "attempts"}.
                </p>
              </div>
              <button type="button" onClick={downloadJson} className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-800 shadow-sm hover:bg-slate-50">
                Download JSON
              </button>
            </div>
            {result.reasons.length > 0 && (
              <ul className="mt-4 list-disc space-y-2 pl-5 text-sm leading-6 text-slate-800">
                {result.reasons.map((reason) => <li key={reason}>{reason}</li>)}
              </ul>
            )}
          </section>

          <section className="rounded-3xl border border-slate-200 bg-white p-5 sm:p-7">
            <h2 className="text-lg font-bold text-slate-900">Invoice details</h2>
            <dl className="mt-5 grid gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
              {[
                ["Vendor", invoice.vendor_name],
                ["Invoice number", invoice.invoice_number],
                ["Invoice date", invoice.invoice_date],
                ["PO number", invoice.po_number],
                ["Currency", invoice.currency],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-xs font-bold uppercase tracking-wider text-slate-500">{label}</dt>
                  <dd className="mt-1 text-base font-medium text-slate-900">{display(value)}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white">
            <div className="p-5 sm:p-7"><h2 className="text-lg font-bold text-slate-900">Line items</h2></div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[680px] border-collapse text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500">
                  <tr><th className="px-6 py-3">Description</th><th className="px-6 py-3 text-right">Quantity</th><th className="px-6 py-3 text-right">Unit price</th><th className="px-6 py-3 text-right">Amount</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {invoice.line_items.map((item, index) => (
                    <tr key={`${item.description}-${index}`}>
                      <td className="px-6 py-4 font-medium text-slate-900">{item.description}</td>
                      <td className="px-6 py-4 text-right text-slate-600">{display(item.quantity)}</td>
                      <td className="px-6 py-4 text-right text-slate-600">{money(item.unit_price, invoice.currency)}</td>
                      <td className="px-6 py-4 text-right font-semibold text-slate-900">{money(item.amount, invoice.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-3xl border border-slate-200 bg-white p-5 sm:p-7">
            <h2 className="text-lg font-bold text-slate-900">Amounts</h2>
            <dl className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              {[
                ["Subtotal", invoice.subtotal],
                ["Discount", invoice.discount],
                ["Shipping", invoice.shipping],
                ["Tax", invoice.tax],
                ["Total", invoice.total],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-xl bg-slate-50 p-4">
                  <dt className="text-xs font-bold uppercase tracking-wider text-slate-500">{label}</dt>
                  <dd className="mt-2 font-semibold text-slate-900">{money(value as number | null, invoice.currency)}</dd>
                </div>
              ))}
            </dl>
          </section>
        </div>
      )}

      <footer className="mx-auto mt-8 max-w-3xl text-center text-xs leading-5 text-slate-500">
        Passing the configured checks is not payment authorization and does not prove that an
        invoice or vendor is authentic. Review invoices according to your organization’s process.
      </footer>
    </main>
  );
}
