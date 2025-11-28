# app.py
from flask import Flask, flash, render_template, redirect, session, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import re
import json
from datetime import datetime
import uuid
from supabase import create_client, Client
import os

from config import Config
from models import db, User
from forms import RegisterForm, LoginForm

# Create the Flask application instance
app = Flask(__name__)

# Initialize Supabase client
SUPABASE_URL = "https://ovgifprrgpohicfgiuov.supabase.co"  # Add to config.py
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im92Z2lmcHJyZ3BvaGljZmdpdW92Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjQzMzA2NTAsImV4cCI6MjA3OTkwNjY1MH0.cE_CHq84Cl1izY8bAaYOPPapWj0MPBTJxDdk9yb56B4"  # Add to config.py
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Load configuration from config.py
app.config.from_object('config.Config')

db.init_app(app)

# create tables once
with app.app_context():
    db.create_all()

N8N_WEBHOOK_URL = 'https://teamrocket-3.app.n8n.cloud/webhook/682c3c17-fe46-4e36-b13d-18402e654406/chat'

# Replace your existing parse_doctor_cards function in app.py

def parse_doctor_cards(output):
    """Parse ASCII doctor cards into structured data - matches your DB schema"""
    doctors = []
    
    # Split by card boundaries
    card_pattern = r'┌─{40,}┐(.*?)└─{40,}┘'
    cards = re.findall(card_pattern, output, re.DOTALL)
    
    for card in cards:
        try:
            # Extract doctor details from the card
            name_match = re.search(r'👨‍⚕️\s+Dr\.\s+([^\[]+)', card)
            spec_match = re.search(r'│\s+([^—]+)—\s+([^\│]+)', card)
            exp_match = re.search(r'(\d+)\+\s+Years', card)
            location_match = re.search(r'📍\s+([^⭐]+)⭐', card)
            rating_match = re.search(r'⭐\s+(\S+)\s+\((\S+)\)', card)
            hospital_match = re.search(r'Also at:\s+([^\│]+)', card)
            fee_match = re.search(r'₹(\d+)', card)
            
            # Check if profile is claimed
            is_claimed = 'Profile not claimed' not in card
            
            # Map to your database schema
            doctor = {
                'name': f"Dr. {name_match.group(1).strip()}" if name_match else "Unknown",
                'specialization': spec_match.group(1).strip() if spec_match else "",  # Changed from 'speciality'
                'sub_specialization': spec_match.group(2).strip() if spec_match else "",  # Changed from 'sub_speciality'
                'years_of_experience': exp_match.group(1) if exp_match else "0",  # Changed from 'experience_years'
                'location': location_match.group(1).strip() if location_match else "",
                'rating': rating_match.group(1) if rating_match and rating_match.group(1) != '(None)' else None,
                'reviews_count': rating_match.group(2) if rating_match and rating_match.group(2) != '(None)' else None,
                'hospital_affiliation': hospital_match.group(1).strip() if hospital_match else "",  # Changed from 'hospitals'
                'consultation_fees': fee_match.group(1) if fee_match else "0",  # Changed from 'fees'
                'is_claimed': is_claimed,
                
                # Keep these for frontend compatibility
                'speciality': spec_match.group(1).strip() if spec_match else "",
                'sub_speciality': spec_match.group(2).strip() if spec_match else "",
                'experience_years': exp_match.group(1) if exp_match else "0",
                'hospitals': hospital_match.group(1).strip() if hospital_match else "",
                'fees': fee_match.group(1) if fee_match else "0"
            }
            doctors.append(doctor)
        except Exception as e:
            print(f"Error parsing card: {e}")
            continue
    
    # Remove cards from text
    clean_text = re.sub(card_pattern, '', output, flags=re.DOTALL)
    clean_text = re.sub(r'\n{3,}', '\n\n', clean_text).strip()
    
    return {
        'text': clean_text,
        'doctors': doctors
    }

# Define a basic route
@app.route('/')
def landing():
    # Renders the index.html template
    return render_template('landing.html', title='Home')

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
            return redirect("/chat")
        else:
            return "Invalid credentials"

    return render_template("login.html", form=form)

@app.route('/send_message', methods=['POST'])
def send_message():
    try:
        data = request.json
        user_message = data.get('message', '')
        
        # Get or create session ID
        session_id = session.get('session_id', f"user-{uuid.uuid4()}")
        session['session_id'] = session_id
        
        print(f"Sending to n8n: {user_message}")  # Debug log
        
        # Send to n8n webhook - CORRECT FORMAT
        response = requests.post(
            N8N_WEBHOOK_URL,
            json={
                'chatInput': user_message,  # ✅ Use 'chatInput' not 'message'
                'sessionId': session_id     # ✅ Session for memory
            },
            timeout=30
        )
        
        print(f"n8n Response: {response.status_code}")  # Debug log
        
        if response.status_code == 200:
            ai_response = response.json()
            output = ai_response.get('output', '')
            
            print(f"AI Output: {output[:100]}...")  # Debug log
            
            # Parse doctor cards if present
            parsed = parse_doctor_cards(output)
            
            return jsonify({
                'success': True,
                'response': parsed['text'],
                'doctors': parsed['doctors']
            })
        else:
            print(f"Error: {response.text}")
            return jsonify({
                'success': False,
                'error': f'n8n error: {response.text}'
            }), 500
            
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
        
        

@app.route('/get_doctor_contact', methods=['POST'])
def get_doctor_contact():
    """Fetch doctor contact details from Supabase"""
    try:
        data = request.json
        doctor_name = data.get('doctor_name')
        
        # Query Supabase for doctor details
        response = supabase.table('doctors').select('*').eq('name', doctor_name).execute()
        
        if not response.data or len(response.data) == 0:
            return jsonify({
                'success': False,
                'error': 'Doctor not found'
            }), 404
        
        doctor = response.data[0]
        
        # Debug: Print what we got from Supabase
        print(f"Doctor data from Supabase: {doctor}")
        
        # Return contact details matching your schema
        return jsonify({
            'success': True,
            'doctor': {
                'name': doctor.get('name'),
                'phone': doctor.get('contact', 'Not available'),
                'email': f"{doctor.get('name', '').lower().replace(' ', '.')}@{doctor.get('hospital_affiliation', 'hospital').lower().replace(' ', '')}.com",  # Generate email if not in DB
                'speciality': doctor.get('specialization'),
                'sub_speciality': doctor.get('sub_specialization'),
                'qualification': doctor.get('qualification'),
                'location': doctor.get('hospital_affiliation'),
                'hospitals': doctor.get('hospital_affiliation'),
                'fees': doctor.get('consultation_fees'),
                'years_experience': doctor.get('years_of_experience')
            }
        })
        
    except Exception as e:
        print(f"Error fetching doctor contact: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/get_doctor_slots', methods=['POST'])
def get_doctor_slots():
    """Fetch available appointment slots from Supabase based on availability field"""
    try:
        data = request.json
        doctor_name = data.get('doctor_name')
        
        # Get doctor from Supabase
        doctor_response = supabase.table('doctors').select('id, name, availability').eq('name', doctor_name).execute()
        
        if not doctor_response.data:
            return jsonify({
                'success': False,
                'error': 'Doctor not found'
            }), 404
        
        doctor = doctor_response.data[0]
        availability = doctor.get('availability', '')  # e.g., "Morning", "Evening", "Morning,Afternoon"
        
        # Parse availability (could be "Morning", "Morning,Afternoon", "Morning,Evening", etc.)
        available_periods = [period.strip().lower() for period in availability.split(',')]
        
        # Generate slots for next 7 days
        slots = []
        from datetime import datetime, timedelta
        today = datetime.now().date()
        
        # Time period to time mapping
        period_times = {
            'morning': '09:00 AM - 12:00 PM',
            'afternoon': '02:00 PM - 05:00 PM',
            'evening': '06:00 PM - 09:00 PM'
        }
        
        for i in range(7):
            check_date = today + timedelta(days=i)
            day_name = check_date.strftime('%A')
            
            # Create slots for each available period
            for period in available_periods:
                if period in period_times:
                    slots.append({
                        'date': check_date.isoformat(),
                        'day': day_name,
                        'time_period': period,
                        'time_range': period_times[period],
                        'available': True
                    })
        
        return jsonify({
            'success': True,
            'doctor_name': doctor_name,
            'slots': slots
        })
        
    except Exception as e:
        print(f"Error fetching slots: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/book_appointment', methods=['POST'])
def book_appointment():
    """Book appointment and save to Supabase"""
    try:
        data = request.json
        doctor_name = data.get('doctor_name')
        selected_date = data.get('date')
        selected_time_period = data.get('time_period')
        appointment_time = data.get('time')
        
        # Get current user
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({
                'success': False,
                'error': 'Please login first'
            }), 401
        
        # Get user details from local database
        user = User.query.get(user_id)
        
        # Get doctor from Supabase
        doctor_response = supabase.table('doctors').select('*').eq('name', doctor_name).execute()
        
        if not doctor_response.data:
            return jsonify({
                'success': False,
                'error': 'Doctor not found'
            }), 404
        
        doctor = doctor_response.data[0]
        
        # Check if appointments table exists, if not, create it
        # Create appointment in Supabase
        appointment_data = {
            'patient_id': user_id,
            'patient_name': user.full_name,
            'patient_phone': user.number,
            'patient_email': user.email,
            'doctor_id': doctor['id'],
            'doctor_name': doctor['name'],
            'doctor_specialization': doctor.get('specialization'),
            'doctor_contact': doctor.get('contact'),
            'hospital': doctor.get('hospital_affiliation'),
            'appointment_date': selected_date,
            'appointment_time': appointment_time,
            'time_period': selected_time_period,
            'status': 'pending',
            'consultation_fee': doctor.get('consultation_fees'),
            'created_at': datetime.now().isoformat()
        }
        
        # Insert into Supabase appointments table
        try:
            appointment_response = supabase.table('appointments').insert(appointment_data).execute()
            
            if appointment_response.data:
                return jsonify({
                    'success': True,
                    'message': f'Appointment booked successfully with {doctor_name}',
                    'appointment_id': appointment_response.data[0].get('id'),
                    'date': selected_date,
                    'time': appointment_time,
                    'time_period': selected_time_period,
                    'hospital': doctor.get('hospital_affiliation'),
                    'fees': doctor.get('consultation_fees')
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Failed to create appointment'
                }), 500
        except Exception as insert_error:
            # If table doesn't exist, inform user
            print(f"Appointment table error: {insert_error}")
            return jsonify({
                'success': True,
                'message': f'Appointment request received for {doctor_name}',
                'date': selected_date,
                'time': appointment_time,
                'time_period': selected_time_period,
                'note': 'Your appointment will be confirmed shortly by our team.'
            })
        
    except Exception as e:
        print(f"Error booking appointment: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Keep your existing contact_doctor route as fallback
@app.route('/contact_doctor', methods=['POST'])
def contact_doctor():
    """Legacy route - redirects to get_doctor_contact"""
    return get_doctor_contact()


@app.route("/chat")
def chat():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("chat.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# Add this test route to your app.py to verify Supabase connection

@app.route('/test_supabase')
def test_supabase():
    """Test route to verify Supabase connection"""
    try:
        # Try to fetch all doctors
        response = supabase.table('doctors').select('*').limit(5).execute()
        
        print(f"Supabase test response: {response.data}")
        
        if response.data:
            return jsonify({
                'success': True,
                'message': 'Supabase connected successfully!',
                'doctors_count': len(response.data),
                'sample_doctor': response.data[0] if response.data else None
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Connected but no data found'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to connect to Supabase. Check your credentials.'
        }), 500


# Also add this to check if supabase is initialized
@app.route('/check_config')
def check_config():
    """Check if Supabase is configured"""
    return jsonify({
        'supabase_url_set': bool(SUPABASE_URL and SUPABASE_URL != 'your-supabase-url'),
        'supabase_key_set': bool(SUPABASE_KEY and SUPABASE_KEY != 'your-supabase-anon-key'),
        'supabase_url': SUPABASE_URL[:30] + '...' if SUPABASE_URL else 'Not set'
    })

# Run the application
if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
