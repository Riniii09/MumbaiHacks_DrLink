from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    number = db.Column(db.String(20), nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    password = db.Column(db.String(255), nullable=False)  # hashed password
