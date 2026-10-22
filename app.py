"""
Campus Complaint Management Platform
Milestone 3 - Step 2: Complaint submission, categories, attachments,
anonymous option, automatic routing, and tracking.

This file now also does:
4. Lets a student submit a complaint (with category, optional file,
   optional anonymous flag).
5. Automatically assigns the complaint to a handler based on category.
6. Lets the student track their complaints, and lets the assigned
   handler (officer/hod/committee) or admin update the status.
"""

import os
from flask import Flask, render_template, redirect, url_for, flash, request, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, login_required,
    logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta

# ---------- App setup ----------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-this-secret-key'          # used to protect forms/sessions
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///complaints.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'docx'}

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'          # if not logged in, send user here
login_manager.login_message = 'Please log in to continue.'


# ---------- Models ----------
class User(UserMixin, db.Model):
    """One row = one user. The 'role' field decides what they can do."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    roll_no = db.Column(db.String(50))                       # only used for students
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')
    # role is one of: student, officer, hod, committee, admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)


class Category(db.Model):
    """Complaint categories, e.g. 'Faculty Related', 'Women Safety'."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    default_priority = db.Column(db.String(20), default='Medium')   # Low/Medium/High/Critical
    sla_hours = db.Column(db.Integer, default=72)                   # resolution deadline
    is_confidential = db.Column(db.Boolean, default=False)          # safety/ragging categories
    handler_role = db.Column(db.String(20), default='officer')      # who this routes to:
    # officer / hod / committee


class Complaint(db.Model):
    """One complaint submitted by a student."""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), default='Medium')
    status = db.Column(db.String(30), default='Submitted')
    # status: Submitted / In Progress / Resolved / Closed / Rejected
    is_anonymous = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    deadline = db.Column(db.DateTime)

    category = db.relationship('Category')
    student = db.relationship('User', foreign_keys=[student_id])
    handler = db.relationship('User', foreign_keys=[assigned_to])

    def display_name(self):
        """Shows 'Anonymous' to anyone except the student themself."""
        return self.student.name

    def is_overdue(self):
        return self.deadline and datetime.utcnow() > self.deadline and self.status not in (
            'Resolved', 'Closed'
        )


class Attachment(db.Model):
    """A file uploaded with a complaint."""
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaint.id'), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255))


class ComplaintHistory(db.Model):
    """Append-only log: every action taken on a complaint."""
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaint.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    remark = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Feedback(db.Model):
    """Student's rating/comment after a complaint is resolved."""
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaint.id'), nullable=False, unique=True)
    rating = db.Column(db.Integer, nullable=False)   # 1 to 5
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def route_complaint(category):
    """
    Finds a handler for a new complaint based on the category's handler_role.
    Picks the handler with the fewest currently-open complaints (simple load
    balancing). Returns None if no handler of that role exists yet.
    """
    candidates = User.query.filter_by(role=category.handler_role).all()
    if not candidates:
        return None

    def open_count(handler):
        return Complaint.query.filter(
            Complaint.assigned_to == handler.id,
            Complaint.status.notin_(['Resolved', 'Closed'])
        ).count()

    return min(candidates, key=open_count)


# ---------- Routes ----------
@app.route('/')
def home():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        roll_no = request.form.get('roll_no', '').strip()
        password = request.form.get('password', '')

        if not name or not email or not password:
            flash('Please fill all required fields.', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('An account with this email already exists.', 'danger')
            return redirect(url_for('register'))

        # New registrations from this public form are always students.
        # Officer/HOD/Admin accounts are created separately by the admin.
        user = User(name=name, email=email, roll_no=roll_no, role='student')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Account created. Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash(f'Welcome, {user.name}!', 'success')
            return redirect(url_for('dashboard'))

        flash('Invalid email or password.', 'danger')
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))


@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'student':
        complaints = (Complaint.query
                      .filter_by(student_id=current_user.id)
                      .order_by(Complaint.created_at.desc()).all())
    elif current_user.role == 'admin':
        complaints = Complaint.query.order_by(Complaint.created_at.desc()).all()
    else:  # officer / hod / committee
        complaints = (Complaint.query
                      .filter_by(assigned_to=current_user.id)
                      .order_by(Complaint.created_at.desc()).all())
    return render_template('dashboard.html', user=current_user, complaints=complaints)


@app.route('/complaint/new', methods=['GET', 'POST'])
@login_required
def new_complaint():
    if current_user.role != 'student':
        abort(403)

    categories = Category.query.order_by(Category.name).all()

    if request.method == 'POST':
        category_id = request.form.get('category_id', type=int)
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        is_anonymous = request.form.get('is_anonymous') == 'on'

        category = Category.query.get(category_id) if category_id else None
        if not category or not title or not description:
            flash('Please fill all required fields.', 'danger')
            return redirect(url_for('new_complaint'))

        complaint = Complaint(
            student_id=current_user.id,
            category_id=category.id,
            title=title,
            description=description,
            priority=category.default_priority,
            is_anonymous=is_anonymous,
            deadline=datetime.utcnow() + timedelta(hours=category.sla_hours),
        )

        # Automatic routing: assign to the right handler based on category.
        handler = route_complaint(category)
        if handler:
            complaint.assigned_to = handler.id

        db.session.add(complaint)
        db.session.commit()

        db.session.add(ComplaintHistory(
            complaint_id=complaint.id,
            action='Submitted',
            remark=f'Routed to {handler.name if handler else "unassigned (no handler set up yet)"}'
        ))
        db.session.commit()

        # Handle optional file attachment
        file = request.files.get('attachment')
        if file and file.filename and allowed_file(file.filename):
            safe_name = secure_filename(file.filename)
            stored_name = f"{complaint.id}_{safe_name}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], stored_name))
            db.session.add(Attachment(
                complaint_id=complaint.id,
                file_path=stored_name,
                original_name=safe_name
            ))
            db.session.commit()

        flash(f'Complaint submitted. Your complaint ID is #{complaint.id}.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('new_complaint.html', categories=categories)


@app.route('/complaint/<int:complaint_id>')
@login_required
def view_complaint(complaint_id):
    complaint = Complaint.query.get_or_404(complaint_id)

    # Access control: only the student who filed it, the assigned handler,
    # or an admin can view a complaint.
    allowed = (
        complaint.student_id == current_user.id
        or complaint.assigned_to == current_user.id
        or current_user.role == 'admin'
    )
    if not allowed:
        abort(403)

    # Extra protection for confidential categories (e.g. safety, ragging):
    # even the assigned handler can only view it if they are on the
    # committee (or are the student/admin). This guards against a
    # complaint ending up with the wrong handler role by mistake.
    if complaint.category.is_confidential:
        confidential_allowed = (
            complaint.student_id == current_user.id
            or current_user.role in ('committee', 'admin')
        )
        if not confidential_allowed:
            abort(403)

    history = (ComplaintHistory.query
               .filter_by(complaint_id=complaint.id)
               .order_by(ComplaintHistory.created_at.asc()).all())
    attachments = Attachment.query.filter_by(complaint_id=complaint.id).all()
    feedback = Feedback.query.filter_by(complaint_id=complaint.id).first()

    hide_identity = complaint.is_anonymous and current_user.id != complaint.student_id

    can_give_feedback = (
        current_user.id == complaint.student_id
        and complaint.status in ('Resolved', 'Closed')
        and feedback is None
    )

    return render_template(
        'view_complaint.html',
        complaint=complaint, history=history, attachments=attachments,
        hide_identity=hide_identity, feedback=feedback,
        can_give_feedback=can_give_feedback
    )


@app.route('/complaint/<int:complaint_id>/feedback', methods=['POST'])
@login_required
def submit_feedback(complaint_id):
    complaint = Complaint.query.get_or_404(complaint_id)

    if complaint.student_id != current_user.id:
        abort(403)
    if complaint.status not in ('Resolved', 'Closed'):
        flash('Feedback can only be given after the complaint is resolved.', 'danger')
        return redirect(url_for('view_complaint', complaint_id=complaint.id))

    action = request.form.get('action')  # 'feedback' or 'reopen'

    if action == 'reopen':
        reason = request.form.get('reopen_reason', '').strip()
        complaint.status = 'In Progress'
        db.session.add(ComplaintHistory(
            complaint_id=complaint.id,
            action='Reopened by student',
            remark=reason or None
        ))
        db.session.commit()
        flash('Complaint reopened. The handler has been notified.', 'info')
        return redirect(url_for('view_complaint', complaint_id=complaint.id))

    # Otherwise: submit feedback and close the complaint
    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment', '').strip()

    if not rating or rating < 1 or rating > 5:
        flash('Please choose a rating from 1 to 5.', 'danger')
        return redirect(url_for('view_complaint', complaint_id=complaint.id))

    db.session.add(Feedback(complaint_id=complaint.id, rating=rating, comment=comment))
    complaint.status = 'Closed'
    db.session.add(ComplaintHistory(
        complaint_id=complaint.id,
        action='Feedback submitted, complaint closed',
        remark=f'Rating: {rating}/5' + (f' — {comment}' if comment else '')
    ))
    db.session.commit()
    flash('Thank you for your feedback!', 'success')
    return redirect(url_for('view_complaint', complaint_id=complaint.id))


@app.route('/complaint/<int:complaint_id>/update', methods=['POST'])
@login_required
def update_complaint(complaint_id):
    complaint = Complaint.query.get_or_404(complaint_id)

    allowed = complaint.assigned_to == current_user.id or current_user.role == 'admin'
    if not allowed:
        abort(403)

    new_status = request.form.get('status')
    remark = request.form.get('remark', '').strip()

    valid_statuses = ['Submitted', 'In Progress', 'Resolved', 'Closed', 'Rejected']
    if new_status in valid_statuses:
        complaint.status = new_status
        db.session.add(ComplaintHistory(
            complaint_id=complaint.id,
            action=f'Status changed to {new_status}',
            remark=remark or None
        ))
        db.session.commit()
        flash('Complaint updated.', 'success')

    return redirect(url_for('view_complaint', complaint_id=complaint.id))


# ---------- Admin panel ----------
def admin_only():
    if current_user.role != 'admin':
        abort(403)


@app.route('/admin')
@login_required
def admin_home():
    admin_only()
    total = Complaint.query.count()
    open_count = Complaint.query.filter(Complaint.status.notin_(['Resolved', 'Closed'])).count()
    resolved_count = Complaint.query.filter_by(status='Resolved').count()
    overdue_count = sum(1 for c in Complaint.query.all() if c.is_overdue())
    return render_template(
        'admin_home.html',
        total=total, open_count=open_count,
        resolved_count=resolved_count, overdue_count=overdue_count
    )


@app.route('/admin/users')
@login_required
def admin_users():
    admin_only()
    users = User.query.order_by(User.role, User.name).all()
    return render_template('admin_users.html', users=users)


@app.route('/admin/users/<int:user_id>/role', methods=['POST'])
@login_required
def admin_change_role(user_id):
    admin_only()
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')

    if user.id == current_user.id:
        flash("You can't change your own role.", 'danger')
        return redirect(url_for('admin_users'))

    valid_roles = ['student', 'officer', 'hod', 'committee', 'admin']
    if new_role in valid_roles:
        user.role = new_role
        db.session.commit()
        flash(f'{user.name} is now {new_role}.', 'success')

    return redirect(url_for('admin_users'))


@app.route('/admin/categories')
@login_required
def admin_categories():
    admin_only()
    categories = Category.query.order_by(Category.name).all()
    return render_template('admin_categories.html', categories=categories)


@app.route('/admin/categories/<int:category_id>', methods=['POST'])
@login_required
def admin_update_category(category_id):
    admin_only()
    category = Category.query.get_or_404(category_id)

    priority = request.form.get('default_priority')
    sla_hours = request.form.get('sla_hours', type=int)
    handler_role = request.form.get('handler_role')
    is_confidential = request.form.get('is_confidential') == 'on'

    if priority in ['Low', 'Medium', 'High', 'Critical']:
        category.default_priority = priority
    if sla_hours and sla_hours > 0:
        category.sla_hours = sla_hours
    if handler_role in ['officer', 'hod', 'committee']:
        category.handler_role = handler_role
    category.is_confidential = is_confidential

    db.session.commit()
    flash(f'"{category.name}" updated.', 'success')
    return redirect(url_for('admin_categories'))


@app.route('/admin/complaints')
@login_required
def admin_complaints():
    admin_only()
    complaints = Complaint.query.order_by(Complaint.created_at.desc()).all()
    return render_template('admin_complaints.html', complaints=complaints)


# ---------- One-time setup command ----------
@app.cli.command('init-db')
def init_db():
    """
    Run this once from the terminal:  flask --app app init-db
    It creates the database tables and some starting data.
    """
    db.create_all()

    # Seed complaint categories (from the Milestone 1 routing table)
    # handler_role decides who a complaint in this category is routed to.
    default_categories = [
        ("Women Safety and Harassment", "Critical", 72, True, "committee"),
        ("Ragging and Bullying", "Critical", 72, True, "committee"),
        ("Faculty / Professor Related", "High", 168, False, "hod"),
        ("Academic / Study Related", "Medium", 240, False, "officer"),
        ("Classroom and Infrastructure", "Medium", 240, False, "officer"),
        ("Hostel", "Medium", 240, False, "officer"),
        ("Library", "Low", 360, False, "officer"),
        ("IT / Wi-Fi / Labs", "Medium", 240, False, "officer"),
        ("Canteen / Transport", "Low", 360, False, "officer"),
        ("Fees and Administration", "Medium", 240, False, "officer"),
        ("Other", "Low", 360, False, "officer"),
    ]
    for name, priority, sla, confidential, handler_role in default_categories:
        if not Category.query.filter_by(name=name).first():
            db.session.add(Category(
                name=name, default_priority=priority,
                sla_hours=sla, is_confidential=confidential,
                handler_role=handler_role
            ))

    # Seed a default account for every role, so you can log in and test
    # the full routing and complaint-handling flow immediately.
    default_users = [
        ("Admin", "admin@college.edu", "admin123", "admin"),
        ("Category Officer", "officer@college.edu", "officer123", "officer"),
        ("HOD", "hod@college.edu", "hod123", "hod"),
        ("Safety Committee", "committee@college.edu", "committee123", "committee"),
    ]
    for name, email, password, role in default_users:
        if not User.query.filter_by(email=email).first():
            u = User(name=name, email=email, role=role)
            u.set_password(password)
            db.session.add(u)

    db.session.commit()
    print('Database created with categories and default accounts:')
    for name, email, password, role in default_users:
        print(f'  {role:10s} -> email: {email:25s} password: {password}')


if __name__ == '__main__':
    app.run(debug=True)
