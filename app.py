# app.py
from flask import Flask, flash, render_template, redirect, session, request
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config
from models import db, User
from forms import RegisterForm, LoginForm

# Create the Flask application instance
app = Flask(__name__)

# Load configuration from config.py
app.config.from_object('config.Config')

db.init_app(app)

# create tables once
with app.app_context():
    db.create_all()

# Define a basic route
@app.route('/')
def index():
    # Renders the index.html template
    return render_template('index.html', title='Home')

# app.py excerpt

@app.route('/about')
def about(): # <-- THIS is the function name (endpoint)
    return render_template('about.html', title='About Us')

@app.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()

    if form.validate_on_submit():

        # Check if email already exists
        existing = User.query.filter_by(email=form.email.data).first()
        if existing:
            flash("Email already registered. Please log in instead.", "danger")
            return redirect("/register")

        # Hash password and save user
        hashed_pw = generate_password_hash(form.password.data)

        user = User(
            full_name=form.full_name.data,
            email=form.email.data,
            number=form.number.data,
            gender=form.gender.data,
            password=hashed_pw
        )
        db.session.add(user)
        db.session.commit()

        flash("Account created successfully! Please log in.", "success")
        return redirect("/login")

    return render_template("register.html", form=form)

@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():

        user = User.query.filter_by(email=form.email.data).first()

        if user and check_password_hash(user.password, form.password.data):
            session["user_id"] = user.id
            return redirect("/dashboard")
        else:
            return "Invalid credentials"

    return render_template("login.html", form=form)


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("dashboard.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# Run the application
if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
