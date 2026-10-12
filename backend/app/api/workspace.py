"""API routes that keep all Firestore data access behind FastAPI."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status
from firebase_admin import firestore

from ..agent.schema import PurchaseOrder
from ..core.firebase import (
    authenticated_user,
    document_payload,
    firestore_client,
    get_owned_document,
    user_collection,
)
from ..services.matching import match_invoice_to_purchase_order
from ..models.schemas import (
    AnalysisBatchCreate,
    AnalysisRecord,
    AnalysisRecordCreate,
    ConfiguredCheck,
    InvoiceRecord,
    InvoiceRecordCreate,
    InvoiceRecordUpdate,
    MatchSavedPurchaseOrderRequest,
    PurchaseOrderRecord,
    PurchaseOrderRecordCreate,
    PurchaseOrderStatusUpdate,
    TwoWayMatchResponse,
    UserProfileRequest,
)


router = APIRouter(prefix="/api", tags=["workspace"])
CurrentUser = Annotated[dict[str, Any], Depends(authenticated_user)]


def _list_records(uid: str, collection_name: str, limit: int) -> list[dict[str, Any]]:
    query = (
        user_collection(uid, collection_name)
        .order_by("createdAt", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    return [document_payload(snapshot) for snapshot in query.stream()]


@router.put("/users/me", status_code=status.HTTP_204_NO_CONTENT)
def sync_user_profile(payload: UserProfileRequest, user: CurrentUser) -> Response:
    profile = payload.model_dump(exclude_none=True)
    # Prefer verified token claims to browser-provided identity values.
    profile.update({
        key: value
        for key, value in {
            "displayName": user.get("name"),
            "email": user.get("email"),
            "photoURL": user.get("picture"),
        }.items()
        if value is not None
    })
    profile["lastLoginAt"] = firestore.SERVER_TIMESTAMP
    user_collection(user["uid"], "_profile").parent.set(profile, merge=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/invoices", response_model=list[InvoiceRecord])
def list_invoices(user: CurrentUser, limit: int = Query(20, ge=1, le=100)):
    return _list_records(user["uid"], "invoices", limit)


@router.post("/invoices", response_model=InvoiceRecord, status_code=status.HTTP_201_CREATED)
def create_invoice(payload: InvoiceRecordCreate, user: CurrentUser):
    reference = user_collection(user["uid"], "invoices").document()
    reference.set({**payload.model_dump(mode="json"), "createdAt": firestore.SERVER_TIMESTAMP})
    return document_payload(reference.get())


@router.get("/invoices/{invoice_id}", response_model=InvoiceRecord)
def get_invoice(invoice_id: str, user: CurrentUser):
    _, snapshot = get_owned_document(user["uid"], "invoices", invoice_id)
    return document_payload(snapshot)


@router.put("/invoices/{invoice_id}", response_model=InvoiceRecord)
def update_invoice(invoice_id: str, payload: InvoiceRecordUpdate, user: CurrentUser):
    reference, _ = get_owned_document(user["uid"], "invoices", invoice_id)
    reference.update({
        **payload.model_dump(mode="json"),
        "updatedAt": firestore.SERVER_TIMESTAMP,
        "recheckedAt": firestore.SERVER_TIMESTAMP,
    })
    return document_payload(reference.get())


@router.delete("/invoices/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(invoice_id: str, user: CurrentUser) -> Response:
    reference, _ = get_owned_document(user["uid"], "invoices", invoice_id)
    reference.delete()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/purchase-orders", response_model=list[PurchaseOrderRecord])
def list_purchase_orders(user: CurrentUser, limit: int = Query(100, ge=1, le=100)):
    return _list_records(user["uid"], "purchaseOrders", limit)


@router.post(
    "/purchase-orders",
    response_model=PurchaseOrderRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_purchase_order(payload: PurchaseOrderRecordCreate, user: CurrentUser):
    collection = user_collection(user["uid"], "purchaseOrders")
    duplicates = list(
        collection.where("normalizedPoNumber", "==", payload.normalizedPoNumber).limit(1).stream()
    )
    if duplicates:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=409,
            detail=f"Purchase order {payload.purchaseOrder.po_number} is already saved.",
        )
    reference = collection.document()
    reference.set({**payload.model_dump(mode="json"), "createdAt": firestore.SERVER_TIMESTAMP})
    return document_payload(reference.get())


@router.get("/purchase-orders/{purchase_order_id}", response_model=PurchaseOrderRecord)
def get_purchase_order(purchase_order_id: str, user: CurrentUser):
    _, snapshot = get_owned_document(user["uid"], "purchaseOrders", purchase_order_id)
    return document_payload(snapshot)


@router.patch("/purchase-orders/{purchase_order_id}", response_model=PurchaseOrderRecord)
def update_purchase_order_status(
    purchase_order_id: str,
    payload: PurchaseOrderStatusUpdate,
    user: CurrentUser,
):
    reference, _ = get_owned_document(user["uid"], "purchaseOrders", purchase_order_id)
    reference.update({"status": payload.status, "updatedAt": firestore.SERVER_TIMESTAMP})
    return document_payload(reference.get())


@router.delete("/purchase-orders/{purchase_order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_order(purchase_order_id: str, user: CurrentUser) -> Response:
    reference, _ = get_owned_document(user["uid"], "purchaseOrders", purchase_order_id)
    reference.delete()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/purchase-orders/match", response_model=TwoWayMatchResponse)
def match_saved_purchase_order(payload: MatchSavedPurchaseOrderRequest, user: CurrentUser):
    po_number = payload.invoice.po_number
    normalized = "".join(character for character in (po_number or "").upper() if character.isalnum())
    if not normalized:
        detail = "The invoice does not contain a purchase order number."
        return TwoWayMatchResponse(
            status="po_not_found",
            po_number=po_number,
            checks=[ConfiguredCheck(
                id="po_availability",
                label="Purchase order is available",
                status="failed",
                detail=detail,
            )],
            reasons=[detail],
        )

    matches = list(
        user_collection(user["uid"], "purchaseOrders")
        .where("normalizedPoNumber", "==", normalized)
        .limit(2)
        .stream()
    )
    if not matches:
        detail = f"No saved purchase order matches {po_number}."
        return TwoWayMatchResponse(
            status="po_not_found",
            po_number=po_number,
            checks=[ConfiguredCheck(
                id="po_availability",
                label="Purchase order is available",
                status="failed",
                detail=detail,
            )],
            reasons=[detail],
        )
    if len(matches) > 1:
        detail = f"More than one saved purchase order matches {po_number}."
        return TwoWayMatchResponse(
            status="ambiguous_po",
            po_number=po_number,
            checks=[ConfiguredCheck(
                id="po_availability",
                label="Purchase order is available",
                status="failed",
                detail=detail,
            )],
            reasons=[detail],
        )

    snapshot = matches[0]
    saved = snapshot.to_dict() or {}
    return match_invoice_to_purchase_order(
        payload.invoice,
        PurchaseOrder.model_validate(saved["purchaseOrder"]),
        snapshot.id,
        saved.get("status", "open"),
    )


@router.get("/invoice-analyses", response_model=list[AnalysisRecord])
def list_invoice_analyses(user: CurrentUser, limit: int = Query(100, ge=1, le=100)):
    return _list_records(user["uid"], "invoiceAnalyses", limit)


@router.post(
    "/invoice-analyses",
    response_model=AnalysisRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_invoice_analysis(payload: AnalysisRecordCreate, user: CurrentUser):
    reference = user_collection(user["uid"], "invoiceAnalyses").document()
    reference.set({**payload.model_dump(mode="json"), "createdAt": firestore.SERVER_TIMESTAMP})
    return document_payload(reference.get())


@router.post(
    "/invoice-analyses/batch",
    response_model=list[AnalysisRecord],
    status_code=status.HTTP_201_CREATED,
)
def create_invoice_analyses(payload: AnalysisBatchCreate, user: CurrentUser):
    collection = user_collection(user["uid"], "invoiceAnalyses")
    batch = firestore_client().batch()
    references = []
    for analysis in payload.analyses:
        reference = collection.document()
        references.append(reference)
        batch.set(reference, {**analysis.model_dump(mode="json"), "createdAt": firestore.SERVER_TIMESTAMP})
    batch.commit()
    return [document_payload(reference.get()) for reference in references]


@router.delete("/invoice-analyses/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice_analysis(analysis_id: str, user: CurrentUser) -> Response:
    reference, _ = get_owned_document(user["uid"], "invoiceAnalyses", analysis_id)
    reference.delete()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
