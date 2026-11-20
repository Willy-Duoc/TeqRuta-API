"""Extensiones Flask compartidas por todos los módulos."""

from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
cors = CORS()
