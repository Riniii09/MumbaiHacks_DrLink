# app.py
from flask import Flask, render_template

# Create the Flask application instance
app = Flask(__name__)

# Load configuration from config.py
app.config.from_object('config.Config')

# Define a basic route
@app.route('/')
def index():
    # Renders the index.html template
    return render_template('index.html', title='Home')

# app.py excerpt

@app.route('/about')
def about(): # <-- THIS is the function name (endpoint)
    return render_template('about.html', title='About Us')

# Run the application
if __name__ == '__main__':
    app.run()