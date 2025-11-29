from flask import Flask, flash, render_template, redirect, session, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import re
import json
from datetime import datetime, timedelta
import uuid
from supabase import create_client, Client
import os
from functools import wraps
from config import Config
from models import db, User
from forms import RegisterForm, LoginForm
from google import genai

# Create the Flask application instance
app = Flask(__name__)

# Load configuration FIRST
app.config.from_object('config.Config')

# Initialize Supabase from config
SUPABASE_URL = "https://ovgifprrgpohicfgiuov.supabase.co"  # Add to config.py
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im92Z2lmcHJyZ3BvaGljZmdpdW92Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjQzMzA2NTAsImV4cCI6MjA3OTkwNjY1MH0.cE_CHq84Cl1izY8bAaYOPPapWj0MPBTJxDdk9yb56B4"  # Add to config.py
    

# Fallback to hardcoded values if not in config (for development only)
if not SUPABASE_URL or not SUPABASE_KEY:
    SUPABASE_URL = "https://ovgifprrgpohicfgiuov.supabase.co"
    SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im92Z2lmcHJyZ3BvaGljZmdpdW92Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjQzMzA2NTAsImV4cCI6MjA3OTkwNjY1MH0.cE_CHq84Cl1izY8bAaYOPPapWj0MPBTJxDdk9yb56B4"

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print(f"✅ Supabase connected: {SUPABASE_URL[:30]}...")
except Exception as e:
    print(f"❌ Supabase connection failed: {e}")
    raise

# Initialize database
db.init_app(app)

# Create tables once
with app.app_context():
    db.create_all()

N8N_WEBHOOK_URL = os.getenv('N8N_WEBHOOK_URL', 'https://teamrocket-3.app.n8n.cloud/webhook/682c3c17-fe46-4e36-b13d-18402e654406/chat')

client = genai.Client()

# ==================== DECORATORS ====================

def doctor_login_required(f):
    """Protects doctor routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'doctor_id' not in session:
            return redirect('/doclogin')
        return f(*args, **kwargs)
    return decorated_function

def user_login_required(f):
    """Protects user routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

# ==================== HELPER FUNCTIONS ====================

def parse_doctor_cards(output):
    """Parse ASCII doctor cards into structured data"""
    doctors = []
    
    # Split by card boundaries
    card_pattern = r'┌[^\n]+┐(.*?)└[^\n]+┘'
    cards = re.findall(card_pattern, output, re.DOTALL)
    
    print(f"🔍 Found {len(cards)} card(s) in output")
    
    for idx, card in enumerate(cards):
        try:
            # Extract doctor name - handle broken emoji and flexible spacing
            # Pattern matches: │ [emoji] Dr. Name [spaces/brackets] │
            name_match = re.search(r'│\s*(?:👨‍⚕️?|👨‍⚕)\s*Dr\.\s*([A-Za-z\s.-]+?)\s+(?:\[|—|│)', card)
            
            # Fallback: try without "Dr." prefix
            if not name_match:
                name_match = re.search(r'│\s*(?:👨‍⚕️?|👨‍⚕)\s*([A-Za-z\s.-]+?)\s+(?:\[|—|│)', card)
            
            # Extract specialization (the part after the em-dash)
            spec_match = re.search(r'—\s*([^\n│]+)', card)
            
            # Extract experience - handles formats like "+ 18 Years experience" or "18+ Years"
            exp_match = re.search(r'(?:\+\s*)?(\d+)\s*\+?\s*Years?\s+experience', card, re.IGNORECASE)
            
            # Debug experience extraction
            if exp_match:
                print(f"   ✅ Experience: {exp_match.group(1)} years")
            else:
                print(f"   ⚠️ No experience found in card")
                # Try to find any number followed by "Years"
                exp_debug = re.search(r'(\d+).*?[Yy]ears?', card)
                if exp_debug:
                    print(f"      Debug found: {exp_debug.group(0)}")
            
            # Extract location (after pin emoji, before star or │)
            location_match = re.search(r'📍\s*([^⭐│\n]+)', card)
            
            # Extract rating (format: ⭐ 4.5 (123))
            rating_match = re.search(r'⭐\s*(\d+\.?\d*)\s*\((\d+)\)', card)
            
            # Extract hospital affiliation (after "Also at:")
            hospital_match = re.search(r'Also at:\s*([^\n│]+?)(?:\s*│|\s*$)', card)
            
            # Extract consultation fee
            fee_match = re.search(r'₹\s*(\d+)', card)
            
            # Check if profile is claimed
            is_claimed = 'Profile not claimed' not in card
            
            # Extract and clean the name
            if name_match:
                doctor_name = name_match.group(1).strip()
                print(f"✅ Card {idx + 1}: Extracted name = {doctor_name}")
            else:
                doctor_name = "Unknown"
                print(f"❌ Card {idx + 1}: Could not extract name")
                print(f"   First 200 chars: {card[:200]}")
            
            # Get specialization - use the part after em-dash
            specialization = ""
            sub_specialization = ""
            
            if spec_match:
                spec_text = spec_match.group(1).strip()
                # Some cards have "Specialty — Sub-specialty" format
                if '—' in spec_text:
                    parts = spec_text.split('—')
                    specialization = parts[0].strip()
                    sub_specialization = parts[1].strip() if len(parts) > 1 else ""
                else:
                    specialization = spec_text
            
            # Map to your database schema
            doctor = {
                'name': f"Dr. {doctor_name}",
                'specialization': specialization,
                'sub_specialization': sub_specialization,
                'years_of_experience': exp_match.group(1) if exp_match else "0",
                'location': location_match.group(1).strip() if location_match else "",
                'rating': rating_match.group(1) if rating_match else None,
                'reviews_count': rating_match.group(2) if rating_match else None,
                'hospital_affiliation': hospital_match.group(1).strip() if hospital_match else "",
                'consultation_fees': fee_match.group(1) if fee_match else "0",
                'is_claimed': is_claimed,
                
                # Keep these for frontend compatibility
                'speciality': specialization,
                'sub_speciality': sub_specialization,
                'experience_years': exp_match.group(1) if exp_match else "0",
                'hospitals': hospital_match.group(1).strip() if hospital_match else "",
                'fees': fee_match.group(1) if fee_match else "0"
            }
            
            doctors.append(doctor)
            
        except Exception as e:
            print(f"❌ Error parsing card {idx + 1}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Clean the text response
    clean_text = re.sub(card_pattern, '', output, flags=re.DOTALL)
    clean_text = re.sub(r'\n{3,}', '\n\n', clean_text).strip()
    
    print(f"📊 Total doctors successfully parsed: {len(doctors)}")
    for i, doc in enumerate(doctors):
        print(f"   {i+1}. {doc['name']} - {doc['specialization']}")
    
    return {'text': clean_text, 'doctors': doctors}
# ==================== PUBLIC ROUTES ====================

@app.route('/')
def landing():
    return render_template('landing.html', title='Home')

@app.route('/explore')
def about():
    return render_template('explore.html', title='About Us')


@app.route("/agent")
def agent():
    return render_template("agent.html")

# ==================== USER AUTH ROUTES ====================

@app.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()
    
    if form.validate_on_submit():
        try:
            # Check if email already exists
            existing = User.query.filter_by(email=form.email.data).first()
            if existing:
                flash("Email already registered. Please log in instead.", "danger")
                return redirect("/register")
            
            # Hash password and save user
            hashed_pw = generate_password_hash(form.password.data, method='pbkdf2:sha256')
            
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
        except Exception as e:
            db.session.rollback()
            flash(f"Registration error: {str(e)}", "danger")
            print(f"Registration error: {e}")
    
    return render_template("register.html", form=form)

@app.route("/ask-ai")
def ask_ai():
    # If user is logged in → go to chat
    if 'user_id' in session:
        return redirect("/chat")
    
    # If not logged in → go to login page
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    if 'user_id' in session:
        return redirect("/chat")
    
    
    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = User.query.filter_by(email=form.email.data).first()
            
            if user and check_password_hash(user.password, form.password.data):
                session["user_id"] = user.id
                session["user_name"] = user.full_name
                flash("Login successful!", "success")
                return redirect("/chat")
            else:
                flash("Invalid email or password", "danger")
        except Exception as e:
            flash(f"Login error: {str(e)}", "danger")
            print(f"Login error: {e}")
    
    return render_template("login.html", form=form)

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect("/login")

@app.route("/chat")
@user_login_required
def chat():
    return render_template("chat.html")

# ==================== DOCTOR CLAIM/AUTH ROUTES ====================

@app.route('/claim-profile', methods=['GET'])
def doctor_claim_profile_page():
    if 'doctor_id' in session:
        return redirect('/doctor/dashboard')
    return render_template('doctor_claim_profile.html')

@app.route('/api/doctor-search', methods=['GET'])
def doctor_search():
    """Search for unclaimed doctors by name"""
    search_term = request.args.get('q', '').strip()
    
    if not search_term or len(search_term) < 2:
        return jsonify({'success': True, 'doctors': []})
    
    try:
        # Search for doctors - remove the is_claimed filter temporarily to debug
        response = supabase.table('doctors')\
            .select('id, name, specialization, hospital_affiliation, is_claimed')\
            .ilike('name', f'%{search_term}%')\
            .limit(10)\
            .execute()
        
        print(f"Search term: {search_term}")
        print(f"Raw response: {response.data}")
        
        results = []
        for doc in response.data:
            # Only include unclaimed profiles
            if not doc.get('is_claimed', False):
                results.append({
                    'id': doc['id'],
                    'name': doc['name'],
                    'description': f"{doc.get('specialization', 'N/A')} at {doc.get('hospital_affiliation', 'Unknown Facility')}"
                })
        
        print(f"Filtered results: {results}")
        
        return jsonify({
            'success': True,
            'doctors': results
        })
        
    except Exception as e:
        print(f"Doctor search error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/doctor/profile/<int:doctor_id>', methods=['GET', 'POST'])
def doctor_profile_update_page(doctor_id):
    """View/claim/update doctor profile"""
    
    # Already logged in as this doctor - show update page
    if 'doctor_id' in session and session['doctor_id'] == doctor_id:
        if request.method == 'GET':
            return render_template('doctor_profile_update.html', doctor_id=doctor_id)
        else:
            return update_doctor_profile_claimed(doctor_id)
    
    if request.method == 'GET':
        try:
            response = supabase.table('doctors').select('*').eq('id', doctor_id).execute()
            
            if not response.data:
                flash("Doctor profile not found.", "danger")
                return redirect('/claim-profile')
            
            doctor = response.data[0]
            
            if doctor.get('is_claimed'):
                flash(f"Dr. {doctor.get('name')} profile has already been claimed. Please log in.", "warning")
                return redirect('/doclogin')
            
            return render_template('doctor_profile_update.html', doctor=doctor, claiming=True)
            
        except Exception as e:
            flash("An error occurred while fetching the profile.", "danger")
            print(f"Error fetching profile: {e}")
            return redirect('/claim-profile')
    
    elif request.method == 'POST':
        return handle_profile_claim(doctor_id)

def handle_profile_claim(doctor_id):
    """Handle profile claiming"""
    try:
        data = request.json
        new_contact = data.get('contact', '').strip()
        new_email = data.get('email', '').strip()
        new_password = data.get('password', '')
        
        if not new_contact or not new_email or not new_password:
            return jsonify({
                'success': False,
                'error': 'Contact, Email, and Password are required to claim profile.'
            }), 400
        
        # FIXED: Use proper password hashing
        hashed_password = generate_password_hash(new_password, method='pbkdf2:sha256')
        
        # Only update fields that exist in your schema
        update_data = {
            'contact': new_contact,
            'email': new_email,
            'is_claimed': True
        }
        
        # Note: Your schema doesn't have a password field!
        # You'll need to add it to Supabase or store it elsewhere
        # For now, I'm commenting this out
        # update_data['password'] = hashed_password
        
        # Check if already claimed (race condition protection)
        check_response = supabase.table('doctors').select('is_claimed').eq('id', doctor_id).execute()
        if check_response.data and check_response.data[0].get('is_claimed'):
            return jsonify({
                'success': False,
                'error': 'Profile has already been claimed by another user.'
            }), 409
        
        update_response = supabase.table('doctors').update(update_data).eq('id', doctor_id).execute()
        
        if update_response.data:
            doctor = update_response.data[0]
            session['doctor_id'] = doctor['id']
            session['doctor_name'] = doctor['name']
            
            return jsonify({
                'success': True,
                'message': 'Profile claimed successfully! Redirecting to dashboard.',
                'warning': 'Password storage not implemented - please add password column to doctors table'
            })
        else:
            return jsonify({'success': False, 'error': 'Profile claim failed.'}), 500
        
    except Exception as e:
        print(f"Profile claim error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/doclogin', methods=['GET', 'POST'])
def doctor_login_page():
    """Doctor login - TEMPORARY: No password validation until password column is added"""
    if 'doctor_id' in session:
        return redirect('/doctor/dashboard')
    
    if request.method == 'POST':
        try:
            data = request.json
            contact = data.get('contact', '').strip()
            password = data.get('password', '')  # Not used yet
            
            if not contact:
                return jsonify({
                    'success': False,
                    'error': 'Contact/Email is required.'
                }), 400
            
            # Search for claimed doctor by contact or email
            doctor_response = supabase.table('doctors').select('*')\
                .or_(f'contact.eq.{contact},email.eq.{contact}')\
                .eq('is_claimed', True)\
                .execute()
            
            if not doctor_response.data:
                return jsonify({
                    'success': False,
                    'error': 'Doctor not found or profile not claimed. Please claim your profile first.'
                }), 404
            
            doctor = doctor_response.data[0]
            
            # TEMPORARY: Skip password verification until password column is added
            # TODO: Add password column to doctors table and uncomment this
            # stored_password = doctor.get('password', '')
            # if not check_password_hash(stored_password, password):
            #     return jsonify({'success': False, 'error': 'Incorrect password.'}), 401
            
            # Create session
            session['doctor_id'] = doctor['id']
            session['doctor_name'] = doctor['name']
            
            return jsonify({
                'success': True, 
                'message': 'Login successful',
                'warning': 'Password authentication disabled - add password column to enable'
            })
            
        except Exception as e:
            print(f"Doctor login error: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': 'Login failed. Please try again.'}), 500
    
    return render_template('doctor_login.html')

@app.route('/doctor/logout')
def doctor_logout():
    """Logout doctor"""
    session.pop('doctor_id', None)
    session.pop('doctor_name', None)
    flash("You have been logged out.", "info")
    return redirect('/doclogin')

@app.route("/api/ask_gemini", methods=["POST"])
def ask_gemini():
    data = request.get_json()
    question = data.get("question", "")
    context = data.get("context", "")

    if not question:
        return jsonify({"answer": "No question provided"}), 400

    # System prompt to constrain AI
    system_prompt = (
        "You are a helpful AI assistant that ONLY answers questions related to "
        "the consultation transcripts provided. Do NOT answer unrelated questions."
        "If asked who you are, respond with 'I am an AI assistant for Dr. Link.'"
    )

    # Combine system prompt + context + user question
    prompt = f"{system_prompt}\n\nConsultation Transcripts:\n{context}\n\nQuestion: {question}\nAnswer:"

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return jsonify({"answer": response.text})
    except Exception as e:
        return jsonify({"answer": f"Error: {str(e)}"}), 500

# ==================== DOCTOR DASHBOARD ROUTES ====================

@app.route('/doctor/dashboard')
@doctor_login_required
def doctor_dashboard():
    appointments = supabase.table('apt').select('*').execute()
    print(appointments.data)  # <-- check what comes here
    return render_template('doctor_dashboard.html', appointments=appointments.data)
    
    
@app.route('/doctor/appointment/<apt_id>')
@doctor_login_required
def appointment_detail(apt_id):
    # Fetch appointment details
    appointment = supabase.table('apt').select('*').eq('id', apt_id).single().execute()
    
    # Fetch all transcripts for this appointment    
    return render_template('appointment_detail.html', 
                         appointment=appointment.data)

@app.route('/doctor/profile', methods=['GET'])
@doctor_login_required
def get_doctor_profile():
    """Get current doctor's profile"""
    try:
        doctor_id = session.get('doctor_id')
        response = supabase.table('doctors').select('*').eq('id', doctor_id).execute()
        
        if response.data:
            return jsonify({'success': True, 'doctor': response.data[0]})
        else:
            return jsonify({'success': False, 'error': 'Profile not found'}), 404
            
    except Exception as e:
        print(f"Error fetching profile: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/doctor/update_profile/<int:doctor_id>', methods=['POST'])
@doctor_login_required
def update_doctor_profile_claimed(doctor_id):
    """Update doctor profile (post-claim)"""
    try:
        if session.get('doctor_id') != doctor_id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        data = request.json
        
        # Prepare update data - only fields that exist in your schema
        update_data = {}
        
        # Update allowed fields
        if 'contact' in data:
            update_data['contact'] = data['contact']
        if 'email' in data:
            update_data['email'] = data['email']
        if 'specialization' in data:
            update_data['specialization'] = data['specialization']
        if 'sub_specialization' in data:
            update_data['sub_specialization'] = data['sub_specialization']
        if 'qualification' in data:
            update_data['qualification'] = data['qualification']
        if 'years_of_experience' in data:
            update_data['years_of_experience'] = int(data['years_of_experience']) if data['years_of_experience'] else 0
        if 'hospital_affiliation' in data:
            update_data['hospital_affiliation'] = data['hospital_affiliation']
        if 'availability' in data:
            update_data['availability'] = data['availability']
        if 'consultation_fees' in data:
            update_data['consultation_fees'] = float(data['consultation_fees']) if data['consultation_fees'] else 0.0
        if 'icd_10_codes' in data:
            update_data['icd_10_codes'] = data['icd_10_codes']
        
        # Perform update
        update_response = supabase.table('doctors').update(update_data).eq('id', doctor_id).execute()
        
        if update_response.data:
            return jsonify({'success': True, 'message': 'Profile updated successfully'})
        else:
            return jsonify({'success': False, 'error': 'Update failed'}), 500
            
    except Exception as e:
        print(f"Error updating profile: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/doctor/appointments', methods=['GET'])
@doctor_login_required
def get_doctor_appointments():
    """Get all appointments for current doctor"""
    try:
        doctor_id = session.get('doctor_id')
        status = request.args.get('status', 'all')
        
        query = supabase.table('appointments').select('*').eq('doctor_id', doctor_id)
        
        if status != 'all':
            query = query.eq('status', status)
        
        response = query.order('appointment_date', desc=False).execute()
        
        return jsonify({
            'success': True,
            'appointments': response.data if response.data else []
        })
        
    except Exception as e:
        print(f"Error fetching appointments: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/doctor/appointment/<appointment_id>/update', methods=['POST'])
@doctor_login_required
def update_appointment_status():
    """Update appointment status"""
    try:
        doctor_id = session.get('doctor_id')
        data = request.json
        appointment_id = data.get('appointment_id')
        new_status = data.get('status')
        
        if not appointment_id or not new_status:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Verify appointment belongs to this doctor
        appointment_response = supabase.table('appointments')\
            .select('*')\
            .eq('id', appointment_id)\
            .eq('doctor_id', doctor_id)\
            .execute()
        
        if not appointment_response.data:
            return jsonify({'success': False, 'error': 'Appointment not found or unauthorized'}), 404
        
        # Update status
        update_response = supabase.table('appointments').update({
            'status': new_status,
            'updated_at': datetime.now().isoformat()
        }).eq('id', appointment_id).execute()
        
        return jsonify({
            'success': True,
            'message': f'Appointment {new_status}',
            'appointment': update_response.data[0] if update_response.data else None
        })
        
    except Exception as e:
        print(f"Error updating appointment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== CHAT & APPOINTMENTS ====================

@app.route('/send_message', methods=['POST'])
@user_login_required
def send_message():
    try:
        data = request.json
        user_message = data.get('message', '')
        
        if not user_message:
            return jsonify({'success': False, 'error': 'Message is required'}), 400
        
        # Get or create session ID
        session_id = session.get('session_id', f"user-{uuid.uuid4()}")
        session['session_id'] = session_id
        
        print(f"Sending to n8n: {user_message}")
        
        # Send to n8n webhook
        response = requests.post(
            N8N_WEBHOOK_URL,
            json={
                'chatInput': user_message,
                'sessionId': session_id
            },
            timeout=30
        )
        
        print(f"n8n Response: {response.status_code}")
        
        if response.status_code == 200:
            ai_response = response.json()
            output = ai_response.get('output', '')
            
            print(f"AI Output: {output[:100]}...")
            
            # Parse doctor cards if present
            parsed = parse_doctor_cards(output)
            
            return jsonify({
                'success': True,
                'response': parsed['text'],
                'doctors': parsed['doctors']
            })
        else:
            print(f"n8n Error: {response.text}")
            return jsonify({
                'success': False,
                'error': f'AI service error: {response.status_code}'
            }), 500
            
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Request timed out. Please try again.'}), 504
    except Exception as e:
        print(f"Send message exception: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/get_doctor_contact', methods=['POST'])
@user_login_required
def get_doctor_contact():
    """Fetch doctor contact details"""
    try:
        data = request.json
        doctor_name = data.get('doctor_name')
        
        if not doctor_name:
            return jsonify({'success': False, 'error': 'Doctor name is required'}), 400
        
        response = supabase.table('doctors').select('*').eq('name', doctor_name).execute()
        
        if not response.data:
            return jsonify({'success': False, 'error': 'Doctor not found'}), 404
        
        doctor = response.data[0]
        
        return jsonify({
            'success': True,
            'doctor': {
                'name': doctor.get('name'),
                'phone': doctor.get('contact', 'Not available'),
                'email': doctor.get('email', 'Not available'),
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
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/get_doctor_slots', methods=['POST'])
@user_login_required
def get_doctor_slots():
    """Fetch available appointment slots"""
    try:
        data = request.json
        doctor_name = data.get('doctor_name')
        
        if not doctor_name:
            return jsonify({'success': False, 'error': 'Doctor name is required'}), 400
        
        doctor_response = supabase.table('doctors')\
            .select('id, name, availability')\
            .eq('name', doctor_name)\
            .execute()
        
        if not doctor_response.data:
            return jsonify({'success': False, 'error': 'Doctor not found'}), 404
        
        doctor = doctor_response.data[0]
        availability = doctor.get('availability', 'Morning,Afternoon,Evening')
        
        available_periods = [period.strip().lower() for period in availability.split(',')]
        
        # Generate slots for next 7 days
        slots = []
        today = datetime.now().date()
        
        period_times = {
            'morning': '09:00 AM - 12:00 PM',
            'afternoon': '02:00 PM - 05:00 PM',
            'evening': '06:00 PM - 09:00 PM'
        }
        
        for i in range(7):
            check_date = today + timedelta(days=i)
            day_name = check_date.strftime('%A')
            
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
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/book_appointment', methods=['POST'])
@user_login_required
def book_appointment():
    """Book appointment"""
    try:
        data = request.json
        doctor_name = data.get('doctor_name')
        selected_date = data.get('date')
        selected_time_period = data.get('time_period')
        appointment_time = data.get('time')
        
        if not all([doctor_name, selected_date, selected_time_period, appointment_time]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        user_id = session.get('user_id')
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        doctor_response = supabase.table('doctors').select('*').eq('name', doctor_name).execute()
        
        if not doctor_response.data:
            return jsonify({'success': False, 'error': 'Doctor not found'}), 404
        
        doctor = doctor_response.data[0]
        
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
            return jsonify({'success': False, 'error': 'Failed to create appointment'}), 500
        
    except Exception as e:
        print(f"Error booking appointment: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== TEST ROUTES ====================

@app.route('/test_supabase')
def test_supabase():
    """Test Supabase connection"""
    try:
        # Fetch all doctors to see what's in the database
        response = supabase.table('doctors').select('id, name, specialization, is_claimed').limit(10).execute()
        
        print(f"Supabase test - found {len(response.data)} doctors")
        for doc in response.data:
            print(f"  - {doc.get('name')} (ID: {doc.get('id')}, Claimed: {doc.get('is_claimed')})")
        
        if response.data:
            return jsonify({
                'success': True,
                'message': 'Supabase connected successfully!',
                'doctors_count': len(response.data),
                'doctors': response.data
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Connected but no data found',
                'message': 'Your doctors table might be empty. Please add some doctor records.'
            })
            
    except Exception as e:
        print(f"Supabase error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to connect to Supabase. Check your credentials.'
        }), 500

@app.route('/check_config')
def check_config():
    """Check configuration"""
    return jsonify({
        'supabase_url_set': bool(SUPABASE_URL and 'supabase.co' in SUPABASE_URL),
        'supabase_key_set': bool(SUPABASE_KEY and len(SUPABASE_KEY) > 20),
        'n8n_webhook_set': bool(N8N_WEBHOOK_URL)
    })

@app.route('/add_test_doctor')
def add_test_doctor():
    """Add a test doctor to the database"""
    try:
        test_doctor = {
            'name': 'Dr. Ethan Stone',
            'specialization': 'Cardiologist',
            'sub_specialization': 'Interventional Cardiology',
            'qualification': 'MBBS, MD (Cardiology)',
            'years_of_experience': 15,  # Changed to int
            'hospital_affiliation': 'City General Hospital',
            'availability': 'Morning,Afternoon',
            'consultation_fees': 1500.00,  # Changed to decimal
            'icd_10_codes': 'I25.10, I20.9',  # Added this field
            'contact': '555-0199',
            'email': 'dr.ethan.stone@citygeneralhospital.com',
            'is_claimed': False
        }
        
        response = supabase.table('doctors').insert(test_doctor).execute()
        
        if response.data:
            return jsonify({
                'success': True,
                'message': 'Test doctor added successfully!',
                'doctor': response.data[0]
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to insert test doctor'
            }), 500
            
    except Exception as e:
        print(f"Error adding test doctor: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(e):
    return jsonify({'success': False, 'error': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

# Run the application
if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)