"""
 This file contains many of the objects that need to be shared between flask and background workers
 Many of them are later initiated in main.py, but some like the ESI library is used as-is
"""

from flask_pymongo import PyMongo
from flask_login import LoginManager
from flask_socketio import SocketIO

# define mongo global for other modules
mongo = PyMongo()

# define login_manager global for other modules
login_manager = LoginManager()
login_manager.login_view = 'login'

# init socket.io
socketio = SocketIO()
