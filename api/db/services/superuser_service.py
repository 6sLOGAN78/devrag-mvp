"""First-superuser seed (D-03, D-24, AUTH-02).

Creates the user (``is_superuser`` true), the tenant with the same id and the owner ``user_tenant``
row in ONE transaction, the same shape the Go registration writes. It is idempotent and safe when two
processes boot together: a MySQL named lock serialises the seed and a unique-email violation is
re-checked instead of surfacing. An existing account is never changed: an existing superuser is left
alone, an existing normal account makes boot fail (no silent promotion, no password overwrite).

The password is never logged and never part of an exception message; errors name the setting only.
No DDL runs here: Peewee migrations own the schema.
"""
from __future__ import annotations

import logging
import re
import uuid

import peewee

from api.db.database import DB, DatabaseLock, transaction
from api.db.models import Tenant, User, UserTenant
from common.security.emails import canonical_email, new_account_email_chars
from common.security.passwords import hash_password

logger = logging.getLogger(__name__)

MIN_PASSWORD_LENGTH = 8  # D-02
MAX_PASSWORD_LENGTH = 128  # D-29
MAX_EMAIL_LENGTH = 255
LOCK_TIMEOUT_SECONDS = 30
# RAGFlow default document-parser list of a new tenant; identical to internal/service/account.go.
DEFAULT_PARSER_IDS = (
    "naive:General,qa:Q&A,resume:Resume,manual:Manual,table:Table,paper:Paper,book:Book,laws:Laws,"
    "presentation:Presentation,picture:Picture,one:One,audio:Audio,email:Email,tag:Tag"
)
_EMAIL_RE = re.compile(r"[^@\s<>(),;:\\\"\[\]]+@[^@\s<>(),;:\\\"\[\]]+\.[^@\s<>(),;:\\\"\[\]]+")
_OWNER = "owner"
_ACTIVE = "1"


class SuperuserConfigError(Exception):
    """A superuser setting is invalid; the message names the setting and never its value."""


class SuperuserSeedError(Exception):
    """The seed cannot proceed (for example the email belongs to a normal account)."""


def normalise_email(email: str) -> str:
    """The shared canonical form, exactly like registration (internal/common/email.go, R-129)."""
    return canonical_email(email)


def validate_credentials(email: str, password: str) -> tuple[str, str]:
    """Return ``(normalised email, password)`` or raise ``SuperuserConfigError`` naming the setting."""
    normalised = normalise_email(email)
    if not normalised or len(normalised) > MAX_EMAIL_LENGTH or not new_account_email_chars(normalised) or not _EMAIL_RE.fullmatch(normalised):
        raise SuperuserConfigError("SUPERUSER_EMAIL is not a valid email address")
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise SuperuserConfigError(f"SUPERUSER_PASSWORD must be {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters")
    return normalised, password


def _existing(email: str) -> User | None:
    return User.get_or_none(User.email == email)


def _check_existing(user: User) -> bool:
    """False (nothing to do) for an existing superuser; fail for a normal account."""
    if user.is_superuser:
        logger.info("superuser already exists; left unchanged")
        return False
    logger.warning("superuser seed skipped: the configured email belongs to a non-superuser account")
    raise SuperuserSeedError("SUPERUSER_EMAIL belongs to an existing non-superuser account; it is not promoted automatically")


def _create(email: str, password: str) -> None:
    user_id = uuid.uuid4().hex
    nickname = email.split("@", 1)[0][:64] or "admin"
    with transaction():
        User.create(
            id=user_id,
            email=email,
            nickname=nickname,
            password=hash_password(password),
            language="English",
            color_schema="Bright",
            timezone="UTC+8\tAsia/Shanghai",
            is_authenticated="1",
            is_active="1",
            is_anonymous="0",
            login_channel="password",
            status=_ACTIVE,
            is_superuser=True,
        )
        Tenant.create(
            id=user_id,
            name=f"{nickname}'s Kingdom",
            llm_id="",
            embd_id="",
            asr_id="",
            img2txt_id="",
            rerank_id="",
            parser_ids=DEFAULT_PARSER_IDS,
            credit=512,
            status=_ACTIVE,
        )
        UserTenant.create(id=uuid.uuid4().hex, user_id=user_id, tenant_id=user_id, role=_OWNER, invited_by=user_id, status=_ACTIVE)


def ensure_superuser(email: str, password: str) -> bool:
    """Create the first superuser when absent. Returns True when it was created, False when it existed.

    Needs an initialised ``DB``; the connection is opened and returned to the pool here.
    """
    email, password = validate_credentials(email, password)
    with DB.connection_context():
        return _seed(email, password)


def _seed(email: str, password: str) -> bool:
    lock_name = f"ensure_superuser:{DB.database}"[:64]
    with DatabaseLock(lock_name, LOCK_TIMEOUT_SECONDS):
        user = _existing(email)
        if user is not None:
            return _check_existing(user)
        try:
            _create(email, password)
        except peewee.IntegrityError:
            # Lost a race despite the lock (for example a registration): re-check, never surface it raw.
            user = _existing(email)
            if user is None:
                raise
            return _check_existing(user)
    logger.info("superuser created")
    return True
