import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.deps import get_current_user
from src.db.models import AgentLog, Lead, User
from src.db.session import get_db
from src.schemas.lead import AgentLogOut, LeadCreate, LeadOut
from src.services.lead_service import create_and_run_lead, lead_to_out

router = APIRouter(prefix="/leads", tags=["leads"])


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: LeadCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LeadOut:
    """
    Synchronous on purpose: the request blocks until the full 4-agent
    pipeline finishes (up to ~30s per architecture.md's latency target).
    A background task queue (Celery/RQ/arq) is the obvious next step once
    this needs to serve concurrent users — deliberately deferred rather
    than added prematurely for a single-user portfolio demo. Documented in
    Future Improvements.
    """
    lead = create_and_run_lead(db, payload.company_name, payload.domain)
    return lead_to_out(lead)


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LeadOut:
    """
    `lead_id: uuid.UUID`, not `str` — FastAPI parses and validates the path
    param itself, returning a clean 422 for a malformed UUID before this
    function ever runs. The earlier `str` version let a malformed ID reach
    the ORM query and crash with an opaque SQLAlchemy error 500 instead of
    a proper 404/422 — caught by test_get_lead_not_found, not by inspection.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead_to_out(lead)


@router.get("", response_model=list[LeadOut])
def list_leads(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[LeadOut]:
    leads = (
        db.query(Lead).order_by(Lead.created_at.desc()).offset(skip).limit(limit).all()
    )
    return [lead_to_out(lead) for lead in leads]


@router.get("/{lead_id}/logs", response_model=list[AgentLogOut])
def get_lead_logs(
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AgentLogOut]:
    """
    The full agent invocation audit trail for one lead, oldest first — every
    attempt (including retries and failures), not just the final accepted
    result per stage. Powers the dashboard's agent trace viewer.

    404s on an unknown lead rather than silently returning an empty list,
    same reasoning as GET /leads/{lead_id}: a client shouldn't have to guess
    whether "no rows" means "lead doesn't exist" or "pipeline hasn't logged
    anything yet for a lead that does".
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    logs = (
        db.query(AgentLog)
        .filter(AgentLog.lead_id == lead_id)
        .order_by(AgentLog.created_at.asc())
        .all()
    )
    return [AgentLogOut.model_validate(log) for log in logs]
