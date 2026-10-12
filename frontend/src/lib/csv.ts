import { InvoiceResult } from "@/lib/api";

const CSV_HEADERS = [
  "vendor_name",
  "invoice_number",
  "invoice_date",
  "po_number",
  "currency",
  "line_description",
  "quantity",
  "unit_price",
  "line_amount",
  "subtotal",
  "discount",
  "shipping",
  "tax",
  "total",
  "validation_status",
  "review_reasons",
];

function escapeCsv(value: string | number | null | undefined) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

function invoiceRows(result: InvoiceResult) {
  const invoice = result.invoice;
  const lineItems = invoice.line_items.length
    ? invoice.line_items
    : [{ description: "", quantity: null, unit_price: null, amount: null }];
  return lineItems.map((item) => [
    invoice.vendor_name,
    invoice.invoice_number,
    invoice.invoice_date,
    invoice.po_number,
    invoice.currency,
    item.description,
    item.quantity,
    item.unit_price,
    item.amount,
    invoice.subtotal,
    invoice.discount,
    invoice.shipping,
    invoice.tax,
    invoice.total,
    result.status,
    result.reasons.join("; "),
  ]);
}

export function invoiceResultToCsv(result: InvoiceResult) {
  const rows = invoiceRows(result).map((row) => row.map(escapeCsv).join(","));

  return `\uFEFF${CSV_HEADERS.join(",")}\r\n${rows.join("\r\n")}`;
}

export function invoiceResultsToCsv(records: Array<{ fileName: string; result: InvoiceResult }>) {
  const rows = records.flatMap((record) => invoiceRows(record.result).map((row) => [record.fileName, ...row]));
  return `\uFEFFfile_name,${CSV_HEADERS.join(",")}\r\n${rows.map((row) => row.map(escapeCsv).join(",")).join("\r\n")}`;
}

function downloadCsv(csv: string, fileName: string) {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function downloadInvoiceCsv(result: InvoiceResult, fileName: string) {
  downloadCsv(invoiceResultToCsv(result), `${fileName.replace(/\.pdf$/i, "") || "invoice"}-analysis.csv`);
}

export function downloadInvoiceResultsCsv(
  records: Array<{ fileName: string; result: InvoiceResult }>,
  fileName = "invoice-analyses.csv",
) {
  downloadCsv(invoiceResultsToCsv(records), fileName);
}
