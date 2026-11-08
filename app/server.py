"""Deployment entry point; refuses an unprotected shared workspace."""
import os
from .main import create_app

if not os.environ.get('ANALYST_PASSWORD') or not os.environ.get('ANALYST_ALLOWED_HOSTS'):
    raise RuntimeError('Set ANALYST_PASSWORD and ANALYST_ALLOWED_HOSTS before deployment.')
app=create_app(os.environ.get('ANALYST_DATA_DIR','/data'))
