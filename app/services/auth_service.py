"""Authentication: login, token issue, revocation, password change."""

from __future__ import annotations

from datetime import datetime, timezone

from flask import current_app
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from ..errors import InvalidCredentialsError, ValidationError
from ..extensions import db
from ..models import AdminUser, TokenBlocklist, utcnow
from ..security import client_ip
from . import rate_limit

LOGIN_BUCKET = "auth_login"

# A hash of a value nobody can supply, used to spend the same amount of time
# on an unknown email as on a wrong password.
_DUMMY_HASH = generate_password_hash("timing-equalisation-placeholder", method="scrypt")


def find_by_email(email: str) -> AdminUser | None:
    stmt = select(AdminUser).where(AdminUser.email == email.strip().lower())
    return db.session.execute(stmt).scalar_one_or_none()


def authenticate(email: str, password: str) -> AdminUser:
    """Verify credentials. Unknown email and wrong password are identical."""
    rate_limit.enforce(LOGIN_BUCKET, client_ip())

    user = find_by_email(email)
    if user is None:
        # Spend the same work so response timing does not reveal which emails
        # have accounts.
        check_password_hash(_DUMMY_HASH, password)
        raise InvalidCredentialsError()
    if not user.check_password(password):
        raise InvalidCredentialsError()
    if not user.is_active:
        raise InvalidCredentialsError()

    user.last_login_at = utcnow()
    db.session.commit()
    rate_limit.reset(LOGIN_BUCKET, client_ip())
    return user


def issue_tokens(user: AdminUser) -> dict:
    identity = str(user.id)
    claims = {"name": user.name, "email": user.email}
    return {
        "access_token": create_access_token(identity=identity, additional_claims=claims),
        "refresh_token": create_refresh_token(identity=identity, additional_claims=claims),
        "user": user.to_dict(),
    }


def issue_access_token(user: AdminUser) -> dict:
    identity = str(user.id)
    claims = {"name": user.name, "email": user.email}
    return {
        "access_token": create_access_token(identity=identity, additional_claims=claims),
        "user": user.to_dict(),
    }


def revoke_current_token(user_id: int | None) -> None:
    """Write the presented token's jti to the blocklist. Logout means logout."""
    claims = get_jwt()
    jti = claims.get("jti")
    if not jti:
        return
    exists = db.session.execute(
        select(TokenBlocklist.id).where(TokenBlocklist.jti == jti).limit(1)
    ).first()
    if exists is not None:
        return
    expires_at = None
    if claims.get("exp"):
        expires_at = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    db.session.add(
        TokenBlocklist(
            jti=jti,
            token_type=claims.get("type", "access"),
            user_id=user_id,
            expires_at=expires_at,
        )
    )
    db.session.commit()


def validate_password(password: str, field: str = "new_password") -> None:
    minimum = current_app.config["PASSWORD_MIN_LENGTH"]
    if len(password) < minimum:
        raise ValidationError(
            "Some fields need attention.",
            fields={field: f"Must be at least {minimum} characters."},
        )


def change_password(user: AdminUser, current_password: str, new_password: str) -> None:
    if not user.check_password(current_password):
        raise ValidationError(
            "Some fields need attention.",
            fields={"current_password": "That is not your current password."},
        )
    validate_password(new_password)
    if current_password == new_password:
        raise ValidationError(
            "Some fields need attention.",
            fields={"new_password": "Choose a password you have not used here before."},
        )
    user.set_password(new_password)
    db.session.commit()


def create_admin(email: str, name: str, password: str) -> AdminUser:
    validate_password(password, field="password")
    normalised = email.strip().lower()
    if find_by_email(normalised) is not None:
        raise ValidationError(
            "Some fields need attention.",
            fields={"email": "An account with that email already exists."},
        )
    user = AdminUser(email=normalised, name=name.strip())
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user
