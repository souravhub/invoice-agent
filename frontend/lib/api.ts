export type LineItem = {
  description: string;
  quantity: number | null;
  unit_price: number | null;
  amount: number | null;
};

export type Invoice = {
  vendor_name: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  po_number: string | null;
  currency: string | null;
  line_items: LineItem[];
  subtotal: number | null;
  discount: number | null;
  shipping: number | null;
  tax: number | null;
  total: number | null;
};

export type InvoiceResult = {
  invoice: Invoice;
  status: "auto_approved" | "needs_review";
  reasons: string[];
  attempts: number;
};

type ErrorPayload = { error?: { message?: string } };

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(
  /\/$/,
  "",
);

export async function checkInvoice(file: File): Promise<InvoiceResult> {
  const formData = new FormData();
  formData.append("file", file);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/invoices/check`, {
      method: "POST",
      body: formData,
    });
  } catch {
    throw new Error("Could not reach the invoice service. Check that the backend is running.");
  }

  const payload = (await response.json().catch(() => ({}))) as InvoiceResult & ErrorPayload;
  if (!response.ok) {
    throw new Error(payload.error?.message || "The invoice could not be checked.");
  }
  return payload;
}
