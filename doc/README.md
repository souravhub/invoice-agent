# Invoice Agent API

This document lists the API endpoints implemented by the FastAPI backend. The API prefix is `/api`.

## Authentication

Workspace endpoints (user profile, invoices, purchase orders, and invoice analyses) require a valid Firebase-authenticated user. The processing endpoints do not use the workspace authentication dependency.

## Processing endpoints

| Method and path | Purpose | Input |
|---|---|---|
| `GET /api/health` | Check that the API is responding. | None |
| `POST /api/invoices/check` | Extract invoice data from a PDF and run validation checks. | Multipart form field `file` (PDF) |
| `POST /api/purchase-orders/extract` | Extract purchase order data from a PDF. | Multipart form field `file` (PDF) |
| `POST /api/invoices/two-way-match` | Compare supplied invoice data against a supplied purchase order. | JSON `TwoWayMatchRequest` |
| `POST /api/invoices/recheck` | Re-run deterministic validation on an existing extraction without an AI request. | JSON `InvoiceRecheckRequest` |
| `POST /api/invoices/check-batch` | Check invoice PDFs in a ZIP archive and return per-file results. | Multipart form field `file` (ZIP) |

PDF endpoints enforce the configured upload limit (currently 20 MB) and validate file type/content. Batch ZIP processing also applies archive safety and uncompressed-size limits.

## User profile and invoice endpoints

These endpoints operate on the authenticated user’s records.

| Method and path | Purpose | Input / result |
|---|---|---|
| `PUT /api/users/me` | Sync the signed-in user’s profile. Verified identity claims take precedence over browser-provided identity values. | JSON `UserProfileRequest`; returns `204 No Content` |
| `GET /api/invoices` | List saved invoices, newest first. | Optional `limit` query parameter (default 20, range 1–100) |
| `POST /api/invoices` | Save an invoice record. | JSON `InvoiceRecordCreate`; returns created record |
| `GET /api/invoices/{invoice_id}` | Get one saved invoice. | Path parameter `invoice_id` |
| `PUT /api/invoices/{invoice_id}` | Update a saved invoice and update its timestamps. | Path parameter `invoice_id`, JSON `InvoiceRecordUpdate` |
| `DELETE /api/invoices/{invoice_id}` | Delete a saved invoice. | Path parameter `invoice_id`; returns `204 No Content` |

## Purchase order endpoints

| Method and path | Purpose | Input / result |
|---|---|---|
| `GET /api/purchase-orders` | List saved purchase orders, newest first. | Optional `limit` query parameter (default 100, range 1–100) |
| `POST /api/purchase-orders` | Save a purchase order; rejects a duplicate normalized PO number with `409 Conflict`. | JSON `PurchaseOrderRecordCreate`; returns created record |
| `GET /api/purchase-orders/{purchase_order_id}` | Get one saved purchase order. | Path parameter `purchase_order_id` |
| `PATCH /api/purchase-orders/{purchase_order_id}` | Update a saved purchase order’s status. | Path parameter `purchase_order_id`, JSON `PurchaseOrderStatusUpdate` |
| `DELETE /api/purchase-orders/{purchase_order_id}` | Delete a saved purchase order. | Path parameter `purchase_order_id`; returns `204 No Content` |
| `POST /api/purchase-orders/match` | Find a saved PO using the invoice PO number and compare the invoice against it. Reports missing or ambiguous matches. | JSON `MatchSavedPurchaseOrderRequest` |

## Invoice analysis endpoints

| Method and path | Purpose | Input / result |
|---|---|---|
| `GET /api/invoice-analyses` | List saved invoice analyses, newest first. | Optional `limit` query parameter (default 100, range 1–100) |
| `POST /api/invoice-analyses` | Save one invoice analysis. | JSON `AnalysisRecordCreate`; returns created record |
| `POST /api/invoice-analyses/batch` | Save multiple invoice analyses in one batch operation. | JSON `AnalysisBatchCreate`; returns created records |
| `DELETE /api/invoice-analyses/{analysis_id}` | Delete a saved invoice analysis. | Path parameter `analysis_id`; returns `204 No Content` |

## Interactive API reference

When the backend is running, FastAPI serves its generated OpenAPI documentation at `/docs` and the schema at `/openapi.json` (typically `http://localhost:8000/docs` and `http://localhost:8000/openapi.json`).

## Endpoint count

There are **20 route definitions**: 6 processing endpoints, 6 user profile and invoice endpoints, 6 purchase order endpoints, and 4 invoice analysis endpoints.
