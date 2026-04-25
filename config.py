# -*- encoding: utf-8 -*-
import datetime
import logging
import os

# -----------------------------------------------------
# Application configurations
# ------------------------------------------------------
SECRET_KEY = os.environ.get('SECRET_KEY', '')
PORT = 5000
HOST = os.environ.get('SERVER_NAME', 'localhost')
LOG_LEVEL = logging.WARNING

# -----------------------------------------------------
# MongoDB Configs
# -----------------------------------------------------
MONGO_URI = 'mongodb://db:27017/peld'

# -----------------------------------------------------
# ESI Configs
# -----------------------------------------------------
# Set ESI_SECRET_KEY and ESI_CLIENT_ID in your .env file (never commit real credentials)
ESI_SECRET_KEY = os.environ.get('ESI_SECRET_KEY', '')
ESI_CLIENT_ID = os.environ.get('ESI_CLIENT_ID', '')
ESI_CALLBACK = 'https://%s/sso/callback' % HOST
ESI_USER_AGENT = 'peld-server by Demogorgon Asmodeous'
ESI_BASE_URL = 'https://esi.evetech.net'
EVE_TOKEN_URL = 'https://login.eveonline.com/v2/oauth/token'
EVE_AUTH_URL = 'https://login.eveonline.com/v2/oauth/authorize'
EVE_REVOKE_URL = 'https://login.eveonline.com/v2/oauth/revoke'

# ------------------------------------------------------
# Session settings for flask login
# ------------------------------------------------------
PERMANENT_SESSION_LIFETIME = datetime.timedelta(days=30)
REMEMBER_COOKIE_REFRESH_EACH_REQUEST = True

# -----------------------------------------------------
# Redis Configs
# -----------------------------------------------------
REDIS_URL = 'redis'
