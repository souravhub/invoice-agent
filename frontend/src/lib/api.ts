import type { User } from "firebase/auth";

import { auth } from "@/lib/firebase";

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

export type PurchaseOrder = {
  vendor_name: string | null;
  po_number: string | null;
  order_date: string | null;
  currency: string | null;
  line_items: LineItem[];
  subtotal: number | null;
  shipping: number | null;
  tax: number | null;
  total: number | null;
};

export type ConfiguredCheck = {
  id: string;
  label: string;
  status: "passed" | "failed" | "not_checked";
  detail: string;
};

export type InvoiceResult = {
  invoice: Invoice;
  status: "auto_approved" | "needs_review";
  reasons: string[];
  attempts: number;
  checks: ConfiguredCheck[];
  two_way_match?: TwoWayMatchResult | null;
};

export type PurchaseOrderExtractionResult = {
  purchase_order: PurchaseOrder;
  attempts: number;
  checks: ConfiguredCheck[];
};

export type TwoWayMatchResult = {
  status: "matched" | "needs_review" | "po_not_found" | "po_unavailable" | "ambiguous_po";
  purchase_order_id: string | null;
  po_number: string | null;
  checks: ConfiguredCheck[];
  reasons: string[];
};

export type BatchFileResult = {
  filename: string;
  result: InvoiceResult | null;
  error: { code: string; message: string } | null;
};

export type InvoiceBatchResult = {
  summary: {
    total: number;
    succeeded: number;
    failed: number;
  };
  files: BatchFileResult[];
};

export type CheckResult = InvoiceResult | InvoiceBatchResult;

export type ApiTimestamp = Date & { toDate: () => Date };

function apiTimestamp(value: string | null | undefined): ApiTimestamp | null {
  if (!value) return null;
  const parsed = new Date(value) as ApiTimestamp;
  parsed.toDate = () => parsed;
  return parsed;
}

export type SavedInvoice = {
  id: string;
  fileName: string;
  fileType: "pdf" | "zip";
  fileSizeBytes: number;
  status: "auto_approved" | "needs_review" | "batch_complete";
  createdAt: ApiTimestamp | null;
  result: CheckResult;
};

export type SavedPurchaseOrder = {
  id: string;
  fileName: string;
  fileSizeBytes: number;
  normalizedPoNumber: string;
  status: "open" | "closed" | "cancelled";
  createdAt: ApiTimestamp | null;
  purchaseOrder: PurchaseOrder;
  extraction: PurchaseOrderExtractionResult;
};

export type SavedAnalysis = {
  id: string;
  fileName: string;
  fileType: "pdf";
  fileSizeBytes?: number | null;
  archiveName?: string | null;
  createdAt: ApiTimestamp | null;
  status: "auto_approved" | "needs_review";
  result: InvoiceResult;
};

export type AnalysisCreate = Omit<SavedAnalysis, "id" | "createdAt">;

type ErrorPayload = { error?: { message?: string }; detail?: string };

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(
  /\/$/,
  "",
);

export function isBatchResult(result: CheckResult): result is InvoiceBatchResult {
  return "files" in result;
}

export async function checkInvoice(file: File): Promise<CheckResult> {
  const formData = new FormData();
  formData.append("file", file);
  const isZip = file.name.toLowerCase().endsWith(".zip");
  const endpoint = isZip ? "/api/invoices/check-batch" : "/api/invoices/check";

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: "POST",
      body: formData,
    });
  } catch {
    throw new Error("Could not reach the invoice service. Check that the backend is running.");
  }

  const payload = (await response.json().catch(() => ({}))) as CheckResult & ErrorPayload;
  if (!response.ok) {
    throw new Error(payload.error?.message || "The invoice could not be checked.");
  }
  return payload;
}

async function apiJson<T>(path: string, init: RequestInit = {}, authenticated = false): Promise<T> {
  const headers = new Headers(init.headers);
  if (authenticated) {
    const user = auth.currentUser;
    if (!user) throw new Error("Sign in is required for this request.");
    headers.set("Authorization", `Bearer ${await user.getIdToken()}`);
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  } catch {
    throw new Error("Could not reach the invoice service. Check that the backend is running.");
  }
  const payload = (response.status === 204
    ? undefined
    : await response.json().catch(() => ({}))) as (T & ErrorPayload) | undefined;
  if (!response.ok) {
    throw new Error(payload?.error?.message || payload?.detail || "The request could not be completed.");
  }
  return payload as T;
}

export async function syncUserProfile(user: User): Promise<void> {
  await apiJson<void>("/api/users/me", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      displayName: user.displayName,
      email: user.email,
      photoURL: user.photoURL,
    }),
  }, true);
}

export function listInvoices(limit = 20): Promise<SavedInvoice[]> {
  return apiJson<Array<Omit<SavedInvoice, "createdAt"> & { createdAt: string | null }>>(
    `/api/invoices?limit=${limit}`, {}, true,
  ).then((records) => records.map((record) => ({ ...record, createdAt: apiTimestamp(record.createdAt) })));
}

export function getInvoice(id: string): Promise<SavedInvoice> {
  return apiJson<Omit<SavedInvoice, "createdAt"> & { createdAt: string | null }>(
    `/api/invoices/${encodeURIComponent(id)}`, {}, true,
  ).then((record) => ({ ...record, createdAt: apiTimestamp(record.createdAt) }));
}

export function saveInvoice(payload: Omit<SavedInvoice, "id" | "createdAt">): Promise<SavedInvoice> {
  return apiJson<Omit<SavedInvoice, "createdAt"> & { createdAt: string | null }>("/api/invoices", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }, true).then((record) => ({ ...record, createdAt: apiTimestamp(record.createdAt) }));
}

export function updateSavedInvoice(
  id: string,
  payload: Pick<SavedInvoice, "status" | "result">,
): Promise<SavedInvoice> {
  return apiJson<Omit<SavedInvoice, "createdAt"> & { createdAt: string | null }>(`/api/invoices/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }, true).then((record) => ({ ...record, createdAt: apiTimestamp(record.createdAt) }));
}

export function deleteSavedInvoice(id: string): Promise<void> {
  return apiJson<void>(`/api/invoices/${encodeURIComponent(id)}`, { method: "DELETE" }, true);
}

export function listPurchaseOrders(limit = 100): Promise<SavedPurchaseOrder[]> {
  return apiJson<Array<Omit<SavedPurchaseOrder, "createdAt"> & { createdAt: string | null }>>(
    `/api/purchase-orders?limit=${limit}`, {}, true,
  ).then((records) => records.map((record) => ({ ...record, createdAt: apiTimestamp(record.createdAt) })));
}

export function getPurchaseOrder(id: string): Promise<SavedPurchaseOrder> {
  return apiJson<Omit<SavedPurchaseOrder, "createdAt"> & { createdAt: string | null }>(
    `/api/purchase-orders/${encodeURIComponent(id)}`, {}, true,
  ).then((record) => ({ ...record, createdAt: apiTimestamp(record.createdAt) }));
}

export function savePurchaseOrder(
  payload: Omit<SavedPurchaseOrder, "id" | "createdAt">,
): Promise<SavedPurchaseOrder> {
  return apiJson<Omit<SavedPurchaseOrder, "createdAt"> & { createdAt: string | null }>("/api/purchase-orders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }, true).then((record) => ({ ...record, createdAt: apiTimestamp(record.createdAt) }));
}

export function updatePurchaseOrderStatus(
  id: string,
  status: SavedPurchaseOrder["status"],
): Promise<SavedPurchaseOrder> {
  return apiJson<Omit<SavedPurchaseOrder, "createdAt"> & { createdAt: string | null }>(`/api/purchase-orders/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  }, true).then((record) => ({ ...record, createdAt: apiTimestamp(record.createdAt) }));
}

export function deleteSavedPurchaseOrder(id: string): Promise<void> {
  return apiJson<void>(`/api/purchase-orders/${encodeURIComponent(id)}`, { method: "DELETE" }, true);
}

export function matchSavedPurchaseOrder(invoice: Invoice): Promise<TwoWayMatchResult> {
  return apiJson<TwoWayMatchResult>("/api/purchase-orders/match", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ invoice }),
  }, true);
}

export function listInvoiceAnalyses(limit = 100): Promise<SavedAnalysis[]> {
  return apiJson<Array<Omit<SavedAnalysis, "createdAt"> & { createdAt: string | null }>>(
    `/api/invoice-analyses?limit=${limit}`, {}, true,
  ).then((records) => records.map((record) => ({ ...record, createdAt: apiTimestamp(record.createdAt) })));
}

export function saveInvoiceAnalysis(payload: AnalysisCreate): Promise<SavedAnalysis> {
  return apiJson<Omit<SavedAnalysis, "createdAt"> & { createdAt: string | null }>("/api/invoice-analyses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }, true).then((record) => ({ ...record, createdAt: apiTimestamp(record.createdAt) }));
}

export function saveInvoiceAnalyses(analyses: AnalysisCreate[]): Promise<SavedAnalysis[]> {
  return apiJson<Array<Omit<SavedAnalysis, "createdAt"> & { createdAt: string | null }>>("/api/invoice-analyses/batch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ analyses }),
  }, true).then((records) => records.map((record) => ({ ...record, createdAt: apiTimestamp(record.createdAt) })));
}

export function deleteSavedAnalysis(id: string): Promise<void> {
  return apiJson<void>(`/api/invoice-analyses/${encodeURIComponent(id)}`, { method: "DELETE" }, true);
}

export async function extractPurchaseOrder(file: File): Promise<PurchaseOrderExtractionResult> {
  const formData = new FormData();
  formData.append("file", file);
  return apiJson<PurchaseOrderExtractionResult>("/api/purchase-orders/extract", {
    method: "POST",
    body: formData,
  });
}

export async function recheckInvoice(result: InvoiceResult): Promise<InvoiceResult> {
  return apiJson<InvoiceResult>("/api/invoices/recheck", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      invoice: result.invoice,
      attempts: result.attempts,
      two_way_match: result.two_way_match || null,
    }),
  });
}
