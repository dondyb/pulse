from dataclasses import dataclass

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import SEGMENTS, Contact
from app.services.errors import NotFound, ValidationFailed
from app.timeutil import utcnow


@dataclass
class ContactInput:
    name: str
    email: str
    company: str
    segment: str
    subscribed: bool = True


def _normalize(session: Session, data: ContactInput, exclude_id: int | None = None) -> ContactInput:
    errors: dict[str, str] = {}
    name = data.name.strip()
    if not name:
        errors["name"] = "Name is required."
    elif len(name) > 120:
        errors["name"] = "Name must be 120 characters or fewer."
    email = data.email.strip()
    try:
        email = validate_email(email, check_deliverability=False, test_environment=True).normalized
    except EmailNotValidError:
        errors["email"] = "Enter a valid email address."
    if data.segment not in SEGMENTS:
        errors["segment"] = "Choose a segment."
    company = data.company.strip()
    if len(company) > 160:
        errors["company"] = "Company must be 160 characters or fewer."
    if "email" not in errors:
        query = select(Contact.id).where(func.lower(Contact.email) == email.lower())
        if exclude_id is not None:
            query = query.where(Contact.id != exclude_id)
        if session.scalar(query) is not None:
            errors["email"] = "A contact with this email already exists."
    if errors:
        raise ValidationFailed("Please fix the highlighted fields.", errors)
    return ContactInput(name=name, email=email, company=company, segment=data.segment, subscribed=data.subscribed)


def _flush_unique(session: Session) -> None:
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError as exc:
        raise ValidationFailed("Please fix the highlighted fields.", {"email": "A contact with this email already exists."}) from exc


def create_contact(session: Session, data: ContactInput) -> Contact:
    clean = _normalize(session, data)
    contact = Contact(
        name=clean.name,
        email=clean.email,
        company=clean.company,
        segment=clean.segment,
        subscribed=clean.subscribed,
        unsubscribed_at=None if clean.subscribed else utcnow(),
    )
    session.add(contact)
    _flush_unique(session)
    return contact


def get_contact(session: Session, contact_id: int) -> Contact:
    contact = session.get(Contact, contact_id)
    if contact is None:
        raise NotFound("Contact not found.")
    return contact


def update_contact(session: Session, contact_id: int, data: ContactInput) -> Contact:
    contact = get_contact(session, contact_id)
    clean = _normalize(session, data, exclude_id=contact_id)
    contact.name = clean.name
    contact.email = clean.email
    contact.company = clean.company
    contact.segment = clean.segment
    set_subscription(session, contact_id, clean.subscribed)
    _flush_unique(session)
    return contact


def set_subscription(session: Session, contact_id: int, subscribed: bool) -> Contact:
    contact = get_contact(session, contact_id)
    if contact.subscribed != subscribed:
        contact.subscribed = subscribed
        contact.unsubscribed_at = None if subscribed else utcnow()
    return contact

