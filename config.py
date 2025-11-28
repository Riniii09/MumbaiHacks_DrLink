# config.py - SAFE to PUSH
import os

class Config:
    # Key is required by Flask, but the *value* comes from the environment.
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY') or 'A_SIMPLE_DEFAULT_FOR_DEV_ONLY'
    
    # Structure of the DB URI is provided, but connection details are hidden.
    #SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') 
    
    SQLALCHEMY_DATABASE_URI = "sqlite:///local.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    #SECRET_KEY = "secret-key-here"
