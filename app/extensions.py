"""Flask extension singletons.

Kept in their own module so models, services and the app factory can import
them without importing the factory (and creating a cycle).
"""

from __future__ import annotations

from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base for every model in the app."""


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
jwt = JWTManager()
cors = CORS()
