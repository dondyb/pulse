from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import ContactIn
from app.db import get_db
from app.models import Contact
from app.services import contacts as service
from app.services.queries import like_pattern, page_meta

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


def serialize(contact: Contact) -> dict:
    return {
        "id": contact.id,
        "name": contact.name,
        "email": contact.email,
        "company": contact.company,
        "segment": contact.segment,
        "subscribed": contact.subscribed,
        "unsubscribed_at": contact.unsubscribed_at,
        "created_at": contact.created_at,
        "updated_at": contact.updated_at,
    }


def _to_input(body: ContactIn) -> service.ContactInput:
    return service.ContactInput(**body.model_dump())


@router.get("")
def list_contacts(
    search: str = "",
    segment: str | None = Query(None, pattern="^(active_customer|trial_user|vip_customer|prospect)$"),
    subscription: str | None = Query(None, pattern="^(subscribed|unsubscribed)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_db),
):
    query = select(Contact)
    if search.strip():
        query = query.where(
            func.lower(Contact.name + " " + Contact.email + " " + Contact.company).like(like_pattern(search), escape="\\")
        )
    if segment:
        query = query.where(Contact.segment == segment)
    if subscription:
        query = query.where(Contact.subscribed.is_(subscription == "subscribed"))
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(Contact.created_at.desc(), Contact.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return {"items": [serialize(c) for c in rows], **page_meta(total, page, page_size)}


@router.post("", status_code=201)
def create_contact(body: ContactIn, session: Session = Depends(get_db)):
    contact = service.create_contact(session, _to_input(body))
    session.commit()
    return serialize(contact)


@router.get("/{contact_id}")
def get_contact(contact_id: int, session: Session = Depends(get_db)):
    return serialize(service.get_contact(session, contact_id))


@router.put("/{contact_id}")
def update_contact(contact_id: int, body: ContactIn, session: Session = Depends(get_db)):
    contact = service.update_contact(session, contact_id, _to_input(body))
    session.commit()
    return serialize(contact)


@router.post("/{contact_id}/subscribe")
def subscribe(contact_id: int, session: Session = Depends(get_db)):
    contact = service.set_subscription(session, contact_id, True)
    session.commit()
    return serialize(contact)


@router.post("/{contact_id}/unsubscribe")
def unsubscribe(contact_id: int, session: Session = Depends(get_db)):
    contact = service.set_subscription(session, contact_id, False)
    session.commit()
    return serialize(contact)

