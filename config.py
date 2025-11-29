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
    SUPABASE_URL = "https://ovgifprrgpohicfgiuov.supabase.co"  # Add to config.py
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im92Z2lmcHJyZ3BvaGljZmdpdW92Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjQzMzA2NTAsImV4cCI6MjA3OTkwNjY1MH0.cE_CHq84Cl1izY8bAaYOPPapWj0MPBTJxDdk9yb56B4"  # Add to config.py
    
