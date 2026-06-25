from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os
import pandas as pd
import webbrowser 
from threading import Timer
from captcha.image import ImageCaptcha
import random
import string
import io
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
Talisman(app, content_security_policy=None, force_https=False)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or os.urandom(24)

app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True 
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

raw_db_url = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://username:password@hostname/database_name' if raw_db_url else 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))

class Student_user(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reg_id = db.Column(db.String(100), unique=True) 
    dob = db.Column(db.String(100))
    name = db.Column(db.String(100))
    semester = db.Column(db.String(100))
    year = db.Column(db.String(100))
    institute = db.Column(db.String(100)) 
    results = db.relationship('Exam_result', backref='student', lazy=True)

class Subject(db.Model):
    reg_id = db.Column(db.Integer.)
    id = db.Column(db.Integer,autoincrement = True, primary_key = True)
    subject_code = db.Column(db.String(10), nullable = False)
    subject_name = db.Column(db.String(100), nullable=False)
    grade = db.Column(db.String(3),nullable = False)

class Exam_result(db.Model):
    result_id = db.Column(db.Integer, primary_key=True)
    grade = db.Column(db.String(100),db.ForeignKey('subject.grade'), nullable=False)
    result_status = db.Column(db.String(100))
    subject_code = db.Column(db.Stirng(10),db.ForeignKey('subject.subject_code'))
    reg_id = db.Column(db.String(100), db.ForeignKey('student_user.reg_id'))
    dob = db.Column(db.String(100),db.ForeignKey('student_user.dob'))
    name = db.Column(db.String(100),db.ForeignKey('student_user.name'))
    semester = db.Column(db.String(100),db.ForeignKey('student_user.semester'))
    year = db.Column(db.String(100),db.ForeignKey('student_user.year'))
    institute = db.Column(db.String(100),db.ForeignKey('student_user.institute')) 
    exam_period = db.Column(db.String(20), nullable=False)
    


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

with app.app_context():
    db.create_all() 
    
    # 1. Fetch admin credentials and force lowercase
    admin1_user = os.getenv('ADMIN1_USER', 'fallback_admin').lower()
    admin1_pass = os.getenv('ADMIN1_PASS', 'fallback_pass_123').lower()
    
    admin2_user = os.getenv('ADMIN2_USER', 'fallback_test').lower()
    admin2_pass = os.getenv('ADMIN2_PASS', 'fallback_test_123').lower()

    # Create the initial master admin securely if they don't exist
    if not User.query.filter_by(username=admin1_user).first():
        db.session.add(User(username=admin1_user, password=admin1_pass))
        db.session.commit()
        
    # Second admin
    if not User.query.filter_by(username=admin2_user).first():
        db.session.add(User(username=admin2_user, password=admin2_pass))
        db.session.commit()


@app.route('/')
def home():
    return render_template('index.html')

@app.route('/gpa')
def gpa():
    return render_template('gpacalculator.html')

@app.route('/resultlogin')
def resultlogin():
    return render_template('resultlogin.html')

@app.route('/timetable')
def time_table():
    return render_template('timetable.html')

@app.route('/upcomingevents')
def upcomingevents():
    return render_template('events.html')

@app.route('/internals')
def internals():
    return render_template('Internals.html')

@app.route('/result')
def result():
    return render_template('result.html')

# --- CAPTCHA Generation ---
image_captcha = ImageCaptcha(width=200, height=90)

def generate_random_string(length=6):
    """Generates a random alphanumeric string."""
    letters = string.ascii_letters + string.digits
    return ''.join(random.choice(letters) for i in range(length))

@app.route('/captcha-image', methods=['GET'])
def get_captcha():
    captcha_text = generate_random_string(6)
    session['captcha'] = captcha_text.upper() 
    data = image_captcha.generate(captcha_text)
    
    return send_file(
        io.BytesIO(data.read()),
        mimetype='image/png',
        download_name='captcha.png'
    )

# --- Verification of student captcha and login ---
@app.route('/resultverify/input', methods=['GET','POST'])
def verify_login():
    """Handles the standard user/student login from the frontend with CAPTCHA."""
    
    raw_reg_id = request.form.get('reg_id', '').strip().lower()
    raw_dob = request.form.get('dob', '').strip().lower()
    user_captcha_input = request.form.get('input', '').strip()

    # 1. CAPTCHA Verification
    stored_captcha = session.get('captcha')
    session.pop('captcha', None) 

    if not stored_captcha:
        flash("CAPTCHA expired. Please refresh the page.")
        return redirect(url_for('resultlogin'))
    
    if user_captcha_input.upper() != stored_captcha:
        flash("Invalid CAPTCHA. Try again.")
        return redirect(url_for('resultlogin'))

    # 2. Database Verification (Fixed: Now queries student_user table!)
    student = student_user.query.filter_by(reg_id=raw_reg_id).first()
    
    # Check if student exists and DOB matches
    if student and student.dob.lower() == raw_dob:
        # Success! You can set session variables here
        session['student_logged_in'] = True
        session['student_reg_id'] = student.reg_id
        return redirect(url_for('result'))
    else:
        flash("Invalid Register Number or Date of Birth.")
        return redirect(url_for('resultlogin'))

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri = "memory://"
)

@app.route('/admin', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if request.method == 'POST':
        raw_username = request.form.get('username', '').strip().lower()
        raw_password = request.form.get('password', '').strip().lower()
        
        print("\n=== LOGIN DEBUG ===")
        print(f"1. HTML Form sent username: '{raw_username}'")
        print(f"2. HTML Form sent password: '{raw_password}'")
        
        user = User.query.filter_by(username=raw_username).first()
        
        if user:
            print("3. Database Result: USER FOUND")
            if user.password.lower() == raw_password:
                print("4. Password Result: MATCH! Logging in.")
                print("===================\n")
                login_user(user)
                return redirect(url_for('admin_dashboard'))
            else:
                print("4. Password Result: NO MATCH")
        else:
            print("3. Database Result: USER NOT FOUND")
        print("===================\n")
        
        flash('Invalid Credentials')
    return render_template('adminlogin.html')

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    return render_template('admin.html')

# Add a logout route for your admins!
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been safely logged out.')
    return redirect(url_for('login'))

@app.route('/admin/import_students', methods=['GET', 'POST'])
@login_required
def import_users():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
            
        file = request.files['file']
        
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)

        if file:
            try:
                if file.filename.endswith('.csv'):
                    df = pd.read_csv(file)
                elif file.filename.endswith(('.xls', '.xlsx')):
                    df = pd.read_excel(file)
                else:
                    flash('Invalid file format. Please upload a CSV or Excel file.')
                    return redirect(request.url)

                df.columns = df.columns.str.strip()
                
                for index, row in df.iterrows():
                    raw_reg_id = str(row['reg_id']).strip()
                    # Process directly in plain text
                    raw_dob = str(row['dob']).strip()
                    student_name = str(row['name']).strip()
                    student_sem = str(row['semester']).strip()
                    s_year = str(row['year']).strip()
                    s_institute = str(row['institute']).strip()

                    # Check if the user already exists
                    existing_user = student_user.query.filter_by(reg_id=raw_reg_id).first()
                    if not existing_user:
                        new_user = student_user(
                            reg_id=raw_reg_id, 
                            dob=raw_dob, 
                            name=student_name, 
                            semester=student_sem, 
                            year=s_year, 
                            institute=s_institute
                        )
                        db.session.add(new_user)

                db.session.commit()
                flash('File imported and users added successfully!')
                return redirect(url_for('admin_dashboard'))

            except Exception as e:
                db.session.rollback()
                flash(f'An error occurred during import: {str(e)}')
                return redirect(request.url)

    return render_template('import.html')


@app.route('/admin/import_results', methods=['GET', 'POST'])
@login_required  
def import_results():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
            
        file = request.files['file']
        
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)

        if file:
            try:
                if file.filename.endswith('.csv'):
                    df = pd.read_csv(file)
                elif file.filename.endswith(('.xls', '.xlsx')):
                    df = pd.read_excel(file)
                else:
                    flash('Invalid file format. Please upload a CSV or Excel file.')
                    return redirect(request.url)

                df.columns = df.columns.str.strip().str.lower()
                print("\n=== DEBUG: PANDAS SEES THESE COLUMNS ===")
                print(df.columns.tolist())
                print("========================================\n")

                required_cols = ['id', 'result', 'grade']
                missing_cols = [col for col in required_cols if col not in df.columns]
                
                if missing_cols:
                    flash(f"Missing required columns in file: {', '.join(missing_cols)}. Please check your headers.")
                    return redirect(request.url)
                
                for index, row in df.iterrows():
                    raw_reg_id = str(row['id']).strip()
                    # Plain text values
                    s_result = str(row['result']).strip()
                    s_grade = str(row['grade']).strip()

                    # Find student in database via plain text ID
                    student = student_user.query.filter_by(reg_id=raw_reg_id).first()
                    
                    if student:
                        new_result = Exam_result(
                            student_reg_id=raw_reg_id,
                            grade=s_grade, 
                            result_status=s_result
                            
                        )
                        db.session.add(new_result)
                    else:
                        print(f"Skipped: Student {raw_reg_id} not found in database.")

                db.session.commit()
                flash('File imported and results added successfully!')
                return redirect(url_for('admin_dashboard'))

            except Exception as e:
                db.session.rollback()  
                flash(f'An error occurred during import: {str(e)}')
                return redirect(request.url)

    return render_template('import.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)