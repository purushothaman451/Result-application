from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os
import pandas as pd
import io
import random
import string
from captcha.image import ImageCaptcha
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

# ==========================================
# DATABASE MODELS
# ==========================================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))

class Student_user(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reg_id = db.Column(db.String(100), unique=True, nullable=False) 
    dob = db.Column(db.String(100))
    name = db.Column(db.String(100))
    year = db.Column(db.String(100))
    institute = db.Column(db.String(100))
    dept = db.Column(db.String(100))
    results = db.relationship("Exam_result", back_populates='student')

class Staff(UserMixin,db.Model):
    staff_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    staff_name = db.Column(db.String(100), nullable=False)
    staff_institute = db.Column(db.String(100))
    reg_id = db.Column(db.String(100), db.ForeignKey('student_user.reg_id'), nullable=False)
    subject_name = db.Column(db.String(100), nullable=False)
    subject_code = db.Column(db.String(100), unique=True, nullable=False) # Must be unique to act as a target for FK
    grade_handled = db.Column(db.String(3)) 
    password = db.Column(db.String(100))
    semester = db.Column(db.String(100))
    student = db.relationship('Student_user', foreign_keys=[reg_id], backref='assigned_staff')


class Subject(db.Model):
    # This is your "Hidden" linking table. It connects Student to Staff/Subject.
    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    reg_id = db.Column(db.String(100), db.ForeignKey('student_user.reg_id'), nullable=False)
    subject_code = db.Column(db.String(100), db.ForeignKey('staff.subject_code'), nullable=False)
    
    # We can store these for easy querying, though technically they are available via the relationship
    subject_name = db.Column(db.String(100))
    staff_name = db.Column(db.String(100))
    
    
    # Relationships
    student = db.relationship('Student_user', foreign_keys=[reg_id], backref='subjects_enrolled')
    staff = db.relationship('Staff', foreign_keys=[subject_code], backref='students_enrolled')

class Exam_result(db.Model):
    result_id = db.Column(db.Integer, primary_key=True)
    reg_id = db.Column(db.String(100), db.ForeignKey('student_user.reg_id'), nullable=False)
    semester = db.Column(db.String(100), db.ForeignKey('staff.semester'), nullable=False)
    subject_code = db.Column(db.String(100), db.ForeignKey('staff.subject_code'), nullable=False)
    grade = db.Column(db.String(10),db.ForeignKey('staff.grade_handled'), nullable=False)
    result_status = db.Column(db.String(100))
    exam_period = db.Column(db.String(20))
    
    # Relationships
    student = db.relationship('Student_user', foreign_keys=[reg_id], back_populates='results')
    subject_details = db.relationship('Staff', foreign_keys=[subject_code], backref='exam_results')

# ==========================================
# APP SETUP & ROUTES
# ==========================================

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

with app.app_context():
    db.create_all() 
    
    admin1_user = os.getenv('ADMIN1_USER', 'fallback_admin').lower()
    admin1_pass = os.getenv('ADMIN1_PASS', 'fallback_pass_123').lower()
    admin2_user = os.getenv('ADMIN2_USER', 'fallback_test').lower()
    admin2_pass = os.getenv('ADMIN2_PASS', 'fallback_test_123').lower()

    if not User.query.filter_by(username=admin1_user).first():
        db.session.add(User(username=admin1_user, password=admin1_pass))
        db.session.commit()
        
    if not User.query.filter_by(username=admin2_user).first():
        db.session.add(User(username=admin2_user, password=admin2_pass))
        db.session.commit()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/resultlogin')
def resultlogin():
    return render_template('resultlogin.html')

@app.route('/gpa')
def gpa():
    return render_template('gpacalculator.html')

@app.route('/result')
def result():
    # 1. Ensure the user is actually logged in
    if not session.get('student_logged_in'):
        flash("Please log in to view your results.")
        return redirect(url_for('resultlogin'))
    
    # 2. Get the specific student's reg_id from the active session
    current_student_reg_id = session.get('student_reg_id')
    
    # 3. Fetch the Student profile
    student = Student_user.query.filter_by(reg_id=current_student_reg_id).first()
    result_new = Exam_result.query.all()



    # 4. Fetch all results linked to this student AND matching 2025
    results = db.session.query(
        Exam_result.subject_code,
        Staff.subject_name,
        Staff.semester,
        Exam_result.grade,
        Exam_result.result_status,
        Exam_result.exam_period
    ).join(
        Staff, Exam_result.subject_code == Staff.subject_code
    ).filter(
        Exam_result.reg_id == current_student_reg_id,
        Exam_result.exam_period.contains('2025') # NEW: Ensures the exam period contains 2025
    ).all()

    # 5. Send both the student profile and the results to the HTML template
    return render_template('result.html', student=student, results=results,result_new=result_new)

# --- CAPTCHA & STUDENT LOGIN ---
image_captcha = ImageCaptcha(width=200, height=90)

def generate_random_string(length=6):
    letters = string.ascii_letters + string.digits
    return ''.join(random.choice(letters) for i in range(length))

@app.route('/captcha-image', methods=['GET'])
def get_captcha():
    captcha_text = generate_random_string(6) 
    session['captcha'] = captcha_text.upper() 
    data = image_captcha.generate(captcha_text)
    return send_file(io.BytesIO(data.read()), mimetype='image/png', download_name='captcha.png')

@app.route('/resultverify/input', methods=['GET','POST'])
def verify_login():
    raw_reg_id = request.form.get('reg_id', '').strip().upper()
    raw_dob = request.form.get('dob', '').strip()
    user_captcha_input = request.form.get('input', '').strip()

    stored_captcha = session.get('captcha')
    session.pop('captcha', None) 

    if not stored_captcha or user_captcha_input.upper() != stored_captcha:
        flash("Invalid or expired CAPTCHA. Try again.")
        return redirect(url_for('resultlogin'))

    student = Student_user.query.filter(Student_user.reg_id.ilike(raw_reg_id)).first()
    
    # --- DEBUGGING PRINTS (Look at your terminal after clicking login) ---
    print(f"--- DEBUG LOGIN ---")
    print(f"Typed Reg ID: '{raw_reg_id}'")
    print(f"Typed DOB: '{raw_dob}'")
    if student:
        print(f"Found Student in DB! DB Reg ID: '{student.reg_id}'")
        print(f"Student DB DOB: '{student.dob}'")
    else:
        print(f"Could not find student with Reg ID '{raw_reg_id}' in DB.")
    print(f"-------------------")

    #debegger ends
    if student and raw_dob in student.dob:
        session['student_logged_in'] = True
        session['student_reg_id'] = student.reg_id
        return redirect(url_for('result'))
    else:
        flash("Invalid Register Number or Date of Birth.")
        return redirect(url_for('resultlogin'))

# --- ADMIN ROUTES ---
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per day", "50 per hour"], storage_uri="memory://")

@app.route('/admin', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if request.method == 'POST':
        raw_username = request.form.get('username', '').strip().lower()
        raw_password = request.form.get('password', '').strip().lower()
        
        user = User.query.filter_by(username=raw_username).first()
        if user and user.password.lower() == raw_password:
            login_user(user)
            return redirect(url_for('admin_dashboard'))
        flash('Invalid Credentials')
    return render_template('adminlogin.html')

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    return render_template('admin.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been safely logged out.')
    return render_template('index.html')

# ==========================================
# IMPORT LOGIC
# ==========================================

@app.route('/admin/import_students', methods=['GET', 'POST'])
@login_required
def import_users():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('No valid file selected')
            return redirect(request.url)

        try:
            if file.filename.endswith('.csv'):
                df = pd.read_csv(file, dtype=str)
            elif file.filename.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(file,dtype=str)
            else:
                flash('Invalid format. Use CSV or Excel.')
                return redirect(request.url)

            df.columns = df.columns.str.strip().str.lower()
            
            for index, row in df.iterrows():
                raw_reg_id = str(row['reg_id']).strip()
                if not Student_user.query.filter_by(reg_id=raw_reg_id).first():
                    new_user = Student_user(
                        reg_id=raw_reg_id, 
                        dob=str(row['dob']).strip(), 
                        name=str(row['name']).strip(),  
                        year=str(row.get('year', '')).strip(), 
                        institute=str(row.get('institute', '')).strip(),
                        dept = str(row.get('dept','')).strip()
                    )
                    db.session.add(new_user)
            db.session.commit()
            flash('Students imported successfully!')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error during import: {str(e)}')
            return redirect(request.url)

    return render_template('import.html')

@app.route('/admin/import_results', methods=['GET', 'POST'])
@login_required  
def import_results():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('No file selected')
            return redirect(request.url)

        try:
            if file.filename.endswith('.csv'):
                df = pd.read_csv(file, dtype=str)
            elif file.filename.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(file, dtype=str)
            else:
                flash('Invalid format.')
                return redirect(request.url)

            df.columns = df.columns.str.strip().str.lower()

            # Required columns for result upload. 
            # Note: We need 'reg_id' and 'subject_code' to auto-link the files.
            required_cols = ['reg_id', 'subject_code', 'result', 'grade']
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                flash(f"Missing required headers: {', '.join(missing_cols)}")
                return redirect(request.url)
                
            for index, row in df.iterrows():
                raw_reg_id = str(row['reg_id']).strip()
                semester=str(row.get('semester', '')).strip()
                raw_subj_code = str(row['subject_code']).strip()
                s_result = str(row['result']).strip()
                s_grade = str(row['grade']).strip()
                s_exam = str(row.get('exam_period', 'Unknown')).strip()

                student = Student_user.query.filter_by(reg_id=raw_reg_id).first()
                staff = Staff.query.filter_by(subject_code=raw_subj_code).first()
                
                # Automatically build the connections if both Student and Staff exist
                if student and staff:
                    # 2. Automatically pull the semester from the Staff database record
                    staff_semester = staff.semester
                    # 1. Check/Create the "Hidden" Subject Linking Table mapping
                    subject_link = Subject.query.filter_by(reg_id=student.reg_id, subject_code=staff.subject_code).first()
                    if not subject_link:
                        new_link = Subject(
                            reg_id=student.reg_id,
                            subject_code=staff.subject_code,
                            subject_name=staff.subject_name,
                            staff_name=staff.staff_name
                        )
                        db.session.add(new_link)

                    # 2. Add the actual Result 
                    new_result = Exam_result(
                        reg_id=student.reg_id,
                        subject_code=staff.subject_code,
                        grade=s_grade, 
                        result_status=s_result,
                        exam_period=s_exam,
                        semester=staff_semester
                    )
                    db.session.add(new_result)
                else:
                    print(f"Skipped Row: Missing Student ({raw_reg_id}) or Subject Code ({raw_subj_code}) in database.")

            db.session.commit()
            flash('Results imported and hidden connections mapped successfully!')
            return redirect(url_for('admin_dashboard'))

        except Exception as e:
            db.session.rollback()  
            flash(f'An error occurred: {str(e)}')
            return redirect(request.url)

    return render_template('import.html')

@app.route('/admin/import_staff', methods=['GET', 'POST'])
@login_required
def import_staff():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('No valid file selected')
            return redirect(request.url)

        try:
            if file.filename.endswith('.csv'):
                df = pd.read_csv(file, dtype=str)
            elif file.filename.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(file, dtype=str)
            else:
                flash('Invalid format. Use CSV or Excel.')
                return redirect(request.url)

            df.columns = df.columns.str.strip().str.lower()
            
            required_cols = ['staff_name', 'subject_name', 'subject_code', 'password','reg_id']
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                flash(f"Missing required headers: {', '.join(missing_cols)}")
                return redirect(request.url)
            
            for index, row in df.iterrows():
                raw_subj_code = str(row['subject_code']).strip()
                raw_reg_id = str(row['reg_id']).strip()
                
                # Pandas reads empty cells as 'nan', so we convert that to Python's None
                if raw_reg_id.lower() == 'nan' or raw_reg_id == '':
                    raw_reg_id = None
                
                # Check if staff/subject already exists to prevent duplicates
                if not Staff.query.filter_by(subject_code=raw_subj_code).first():
                    new_staff = Staff(
                        staff_name=str(row['staff_name']).strip(),
                        staff_institute=str(row.get('staff_institute', '')).strip(),
                        subject_name=str(row['subject_name']).strip(),
                        subject_code=raw_subj_code,
                        grade_handled=str(row.get('grade_handled', '')).strip(),
                        password=str(row['password']).strip(),
                        semester=str(row.get('semester', '')).strip(),
                        reg_id=raw_reg_id  # NEW: Pushing the reg_id to the database
                    )
                    db.session.add(new_staff)
            db.session.commit()
            flash('Staff imported successfully!')
            return redirect(url_for('admin_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error during staff import: {str(e)}')
            return redirect(request.url)

    return render_template('import.html') # Reusing your existing import template

if __name__ == '__main__':
    app.run(debug=True, port=5000)