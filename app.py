from flask import Flask, render_template, redirect, url_for, flash, session, request, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit, join_room, leave_room
import json
from forms import LoginForm
from datetime import datetime
import functions
from db_utils import execute_query, execute_update, fetch_configuration, update_configuration
import logging
from werkzeug.utils import secure_filename
import os

# Initialize Flask app
app = Flask(
    __name__,
    static_folder='static',
    template_folder='templates'
)
app.config['SECRET_KEY'] = 'sadcbshvshcvhdv'  # Replace with a secure secret key

# Database configuration
app.config['DB_HOST'] = '41.34.206.254'
app.config['DB_USER'] = 'root'
app.config['DB_PASSWORD'] = ''
app.config['DB_NAME'] = 'adv'
app.config['DB_PORT'] = 3306

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt', 'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Logging configuration
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


socketio = SocketIO(app, cors_allowed_origins="*", logger=True)

# User class for Flask-Login
class User:
    def __init__(self, user_id, email, user_type_ID):
        self.id = user_id
        self.email = email
        self.user_type_ID = user_type_ID

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    logger.debug(f"Loading user with ID: {user_id}")
    user_info = functions.fetch_user_info(session.get('user_type_ID'), user_id)
    if user_info:
        logger.debug(f"User info found: {user_info}")
        return User(user_id, session.get('user_email'), session.get('user_type_ID'))
    logger.debug("No user info found.")
    return None

@app.route('/', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        logger.debug(f"Attempting login with email: {email}")
        user = functions.authenticate(email, password)
        if user:
            user = user[0]
            user_type_ID = user['user_type_ID']
            user_ID = user['user_ID']
            logger.debug(f"User authenticated: {user}")
            user_info = functions.fetch_user_info(user_type_ID, user_ID)
            logger.debug(f"Fetched user info: {user_info}")
            
            login_user(User(user_ID, email, user_type_ID))
            session['user_type_ID'] = user_type_ID
            session['user_email'] = email
            session['user_info'] = user_info
            
            flash('Logged in successfully.', 'success')
            return redirect(url_for('dashboard'))
        else:
            logger.debug("Invalid credentials.")
            flash('Invalid credentials. Please check your email and password.', 'error')
    return render_template('login.html', form=form)

@app.route('/dashboard')
@login_required
def dashboard():
    user_type_ID = current_user.user_type_ID
    logger.debug(f"Dashboard accessed by user type ID: {user_type_ID}")
    if user_type_ID == 1:
        return redirect(url_for('advisor'))
    elif user_type_ID == 2:
        return redirect(url_for('student'))
    elif user_type_ID == 3:
        return redirect(url_for('headofadvising'))
    else:
        logger.debug("Invalid user type.")
        flash('Invalid user type.', 'error')
        return redirect(url_for('login'))



@app.route('/student', methods=['GET', 'POST'])
@login_required
def student():
    if current_user.user_type_ID != 2:
        logger.debug(f"Access denied for user ID: {current_user.id} (type: {current_user.user_type_ID})")
        flash('Access denied. You are not a student.', 'error')
        return redirect(url_for('dashboard'))

    try:
        # Handle POST request for slot reservation
        if request.method == 'POST' and request.is_json:
            data = request.get_json()
            slot_id = data.get('slot_id')
            if slot_id:
                reservation_success = functions.reserve_advisor_slot(current_user.id, slot_id)
                if reservation_success:
                    # Fetch updated advisor slots
                    updated_advisor_slots = functions.fetch_advisor_slots(current_user.id)
                    return jsonify({
                        "success": True,
                        "message": "Slot reserved successfully.",
                        "updated_slots": updated_advisor_slots
                    }), 200
                else:
                    return jsonify({"success": False, "message": "Slot is already reserved or invalid."}), 400
            else:
                return jsonify({"success": False, "message": "Slot ID is missing."}), 400

        # Fetch student information
        student_info = functions.fetch_student_info_by_id(current_user.id)
        logger.debug(f"Student info: {student_info}")

        if not student_info:
            flash('Could not retrieve student information. Please contact support.', 'error')
            return redirect(url_for('dashboard'))

        transcript = functions.fetch_student_transcript(current_user.id)
        logger.debug(f"Transcript: {transcript}")

        recommended_courses = functions.fetch_recommended_courses(current_user.id)
        logger.debug(f"Recommended courses: {recommended_courses}")

        advisor_slots = functions.fetch_advisor_slots(current_user.id)
        logger.debug(f"Advisor Slots: {advisor_slots}")

        gpa_deficit = functions.calculate_gpa_deficit(current_user.id)
        logger.debug(f"GPA deficit: {gpa_deficit}")

        con_sem = functions.probation_semesters_count(current_user.id)
        logger.debug(f"Consecutive semesters on probation: {con_sem}")

        probation_status = functions.check_probation_status(current_user.id, con_sem)
        logger.debug(f"Probation status: {probation_status}")

        consecutive_semesters = functions.count_consecutive_probation_semesters(current_user.id)
        logger.debug(f"Consecutive semesters: {consecutive_semesters}")

        gpa_deficit = gpa_deficit if gpa_deficit is not None else 0

        return render_template(
            'student_dashboard.html',
            student_info=student_info,
            transcript=transcript,
            recommended_courses=recommended_courses,
            advisor_slots=advisor_slots,
            gpa_deficit=gpa_deficit,
            probation_status=probation_status,
            consecutive_semesters=consecutive_semesters
        )

    except Exception as e:
        logger.error(f"Error in student route: {str(e)}")
        flash('An error occurred while loading your dashboard. Please try again later.', 'error')
        return redirect(url_for('dashboard'))



@app.route('/advisor', methods=['GET', 'POST'])
@login_required
def advisor():
    if current_user.user_type_ID != 1:  # Ensure the user is an advisor
        logger.debug(f"Access denied for user ID: {current_user.id} (type: {current_user.user_type_ID})")
        flash('Access denied. You are not an advisor.', 'error')
        return redirect(url_for('dashboard'))

    try:
        advisor_id = functions.get_advisor_id(current_user.id)
        if not advisor_id:
            logger.error("Advisor ID not found.")
            flash('Error loading advisor information. Please try again.', 'error')
            return redirect(url_for('dashboard'))

        advisor_info = functions.fetch_advisor_info(advisor_id)
        logger.debug(f"Advisor info: {advisor_info}")

        # POST Request Handlers
        if request.method == 'POST':
            if 'set_availability' in request.form:
                slot_date = request.form.get('slot_date')
                start_time = request.form.get('start_time')
                end_time = request.form.get('end_time')
                logger.debug(f"Received form data: slot_date={slot_date}, start_time={start_time}, end_time={end_time}")
                if slot_date and start_time and end_time:
                    try:
                        functions.add_availability_slot(advisor_id, slot_date, start_time, end_time)
                        flash('Availability slot added successfully.', 'success')
                    except Exception as e:
                        logger.error(f"Error adding slot: {str(e)}")
                        flash('Error adding availability slot. Please try again.', 'error')
                else:
                    logger.warning("Incomplete form data received.")
                    flash('Please fill in all fields.', 'error')

            # Delete Availability Slot
            if 'delete_slot' in request.form:
                slot_id = request.form.get('slot_id')
                if slot_id:
                    try:
                        functions.delete_availability_slot(int(slot_id))
                        flash(f'Slot {slot_id} deleted successfully.', 'success')
                    except Exception as e:
                        logger.error(f"Error deleting slot: {str(e)}")
                        flash('Error deleting slot. Please try again.', 'error')
                else:
                    flash('Invalid slot ID.', 'error')

            # Search for a Student
            if 'search_student' in request.form:
                student_search_id = request.form.get('student_id')
                if student_search_id:
                    student_info = functions.fetch_student_info_by_id(student_search_id)
                    if not student_info:
                        flash('Student not found. Please check the ID.', 'error')

            # Chatroom Management
            if 'open_chatroom' in request.form:
                slot_id = request.form.get('slot_id')
                student_id = functions.get_student_id_from_slot(slot_id)
                if student_id:
                    chatroom_status = functions.open_chatroom(slot_id, advisor_id, student_id)
                    if chatroom_status:
                        return jsonify({'success': True, 'message': 'Chatroom opened successfully.'})
                    else:
                        return jsonify({'success': False, 'message': 'Failed to open chatroom.'})
                else:
                    return jsonify({'success': False, 'message': 'No student found for this slot.'})

            if 'close_chatroom' in request.form:
                slot_id = request.form.get('slot_id')
                if functions.close_chatroom(slot_id):
                    flash('Chatroom closed successfully.', 'success')
                else:
                    flash('Failed to close chatroom.', 'error')

            if 'send_message' in request.form:
                slot_id = request.form.get('slot_id')
                message = request.form.get('message')
                if functions.send_message(slot_id, advisor_id, message):
                    return jsonify({'success': True, 'message': 'Message sent successfully.'})
                else:
                    return jsonify({'success': False, 'message': 'Failed to send message.'})

            if 'get_chat_messages' in request.form:
                slot_id = request.form.get('slot_id')
                if slot_id:
                    messages = functions.fetch_chat_messages(slot_id)
                    return jsonify({'success': True, 'messages': messages})
                return jsonify({'success': False, 'message': 'Invalid slot ID.'})

        # Fetch Availability Slots
        availability_slots = functions.fetch_availability_slots(advisor_id)
        logger.debug(f"Availability slots passed to template: {availability_slots}")

        # Reserved Slots for Chat Management
        reserved_slots = functions.fetch_reserved_slots(advisor_id)

        # In your advisor route
        logger.debug(f"About to check program director status for advisor_id: {advisor_id}")
        program_director = functions.check_program_director(advisor_id)
        logger.debug(f"Program director check returned: {program_director}")


        # GPA Calculation
        added_courses = session.get('added_courses', [])
        if 'calculate_gpa' in request.form:
            # Process GPA calculations for added courses
            try:
                grade_points = {'A+': 4.0, 'A': 4.0, 'A-': 3.7, 'B+': 3.3, 'B': 3.0, 'B-': 2.7,
                                'C+': 2.3, 'C': 2.0, 'C-': 1.7, 'D+': 1.3, 'D': 1.0, 'F': 0.0}
                total_credits = sum(course['credit_hours'] for course in added_courses)
                total_points = sum(course['credit_hours'] * grade_points[course['grade']] for course in added_courses)
                current_semester_gpa = total_points / total_credits if total_credits > 0 else 0.0

                cumulative_gpa, cumulative_credits = functions.fetch_cumulative_gpa(current_user.id)
                new_cumulative_gpa = functions.calculate_cumulative_gpa(cumulative_gpa, cumulative_credits,
                                                                         total_points, total_credits)
                flash(f'Calculated GPA: {current_semester_gpa:.2f}, Updated Cumulative GPA: {new_cumulative_gpa:.2f}',
                      'success')
            except Exception as e:
                logger.error(f"Error calculating GPA: {str(e)}")
                flash('Error calculating GPA. Please try again.', 'error')

        # Fetch Advisor's Students
        student_search_id = request.args.get('student_id', None)
        student_info = None
        if student_search_id:
            student_info = functions.fetch_student_info_by_id(student_search_id)

        # Additional Data Fetches
        student_summary = functions.get_advisor_student_summary(advisor_id)
        logger.debug(f"Advisor's students summary: {student_summary}")
        program_director_summary = functions.get_program_director_summary(advisor_id)
        program_student_summary = functions.get_program_student_summary_for_director(advisor_id)
        advisor_slots = functions.fetch_availability_slots(advisor_id)
        transcript = functions.fetch_student_transcript(student_search_id) if student_search_id else None
        recommended_courses = functions.fetch_recommended_courses(student_search_id) if student_search_id else None
        gpa_deficit = functions.calculate_gpa_deficit(student_search_id) if student_search_id else None
        probation_status = functions.check_probation_status(student_search_id) if student_search_id else None

        # Chatroom Management
        chatroom_statuses = {}
        for slot in reserved_slots:
            chatroom_statuses[slot['Slot_ID']] = functions.fetch_chatroom_status(slot['Slot_ID'])

        # Render the Advisor Template
        return render_template(
            'advisor_dashboard.html',
            advisor_info=advisor_info,
            advisor_id = advisor_id,
            student_summary=student_summary,
            availability_slots=availability_slots,
            reserved_slots=reserved_slots,
            student_info=student_info,
            transcript=transcript,
            recommended_courses=recommended_courses,
            gpa_deficit=gpa_deficit,
            probation_status=probation_status,
            chatroom_statuses=chatroom_statuses,
            program_director = program_director,
            program_director_summary = program_director_summary,
            program_student_summary = program_student_summary
        )

    except Exception as e:
        logger.error(f"Error in advisor route: {str(e)}")
        flash('An error occurred while loading the advisor dashboard. Please try again later.', 'error')
        return redirect(url_for('dashboard'))



@app.route('/program_director', methods=['GET', 'POST'])
@login_required
def program_director():
    # Check if user is a program director
    advisor_id = functions.get_advisor_id(current_user.id)
    if not functions.check_program_director(advisor_id):
        logger.warning(f"Non-program director (advisor_id: {advisor_id}) attempted to access program_director route")
        flash('Access denied. You are not a program director.', 'error')
        return redirect(url_for('dashboard'))

    program_id = functions.get_advisor_program_id(advisor_id)
    if program_id is None:
        logger.error(f"No program found for advisor_id {advisor_id}")
        flash('Error: Unable to determine your program. Please contact support.', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        student_ids = request.form.getlist('student_ids[]')
        new_advisor_id = request.form.get('new_advisor_id')
        
        logger.debug(f"Attempting to assign students {student_ids} to advisor {new_advisor_id}")
        
        if not student_ids or not new_advisor_id:
            flash('Please select at least one student and an advisor.', 'error')
        else:
            success_count = 0
            for student_id in student_ids:
                if functions.assign_student_to_advisor(student_id, new_advisor_id, program_id):
                    success_count += 1
            
            if success_count == len(student_ids):
                flash(f'Successfully assigned {success_count} students to the new advisor.', 'success')
            elif success_count > 0:
                flash(f'Partially successful: Assigned {success_count} out of {len(student_ids)} students.', 'warning')
            else:
                flash('Failed to assign students. Please ensure all students and the advisor are in the same program.', 'error')

    # Fetch data for the template
    try:
        unassigned_students = functions.get_unassigned_students(program_id)
        assigned_students = functions.get_assigned_students(program_id)
        advisors = functions.get_program_advisors(program_id)

        return render_template('program_director.html',
                               unassigned_students=unassigned_students,
                               assigned_students=assigned_students,
                               advisors=advisors)
    except Exception as e:
        logger.error(f"Error fetching data for program director dashboard: {str(e)}")
        flash('An error occurred while loading the data. Please try again.', 'error')
        return redirect(url_for('dashboard'))




@app.route('/advising', methods=['GET', 'POST'])
@login_required
def advising():
    logger.debug(f"Advising route accessed by user {current_user.id}")

    # Authorization Check
    if current_user.user_type_ID != 1:
        flash('Access denied. You are not an advisor.', 'error')
        return redirect(url_for('dashboard'))

    try:
        # Fetch advisor details
        advisor_id = functions.get_advisor_id(current_user.id)
        logger.debug(f"Fetched advisor ID: {advisor_id}")
        if not advisor_id:
            flash('Advisor ID not found. Please try again.', 'error')
            return redirect(url_for('dashboard'))

        advisor_info = functions.fetch_advisor_info(advisor_id)
        logger.debug(f"Fetched advisor info: {advisor_info}")
        if not advisor_info:
            flash('Unable to load advisor information. Please contact support.', 'error')
            return redirect(url_for('dashboard'))

        # Initialize context variables
        student_info = None
        gpa_deficit = 0
        probation_status = False
        consecutive_semesters = 0
        transcript = None
        recommended_courses = []
        updated_recommended_courses = []
        unfinished_courses = None
        study_plan_courses = None
        core_electives = []
        university_electives = []
        core_courses = []
        university_requirements = []
        calculator_data = None
        semester_data = []

        # Handle student search and other POST requests
        if request.method == 'POST':
            logger.debug(f"POST request received: {request.form}")
            if request.is_json:
                data = request.get_json()
                if data.get('get_semester_data'):
                    student_id = data.get('user_id')
                    if student_id:
                        try:
                            semester_data = functions.calculate_semester_data(student_id)
                            logger.debug(f"Calculated semester data for student {student_id}: {semester_data}")

                            if not semester_data:
                                return jsonify({"error": f"No semester data found for student with ID {student_id}"}), 404

                            return jsonify(semester_data)
                        except Exception as e:
                            logger.error(f"Error fetching semester data: {str(e)}", exc_info=True)
                            return jsonify({"error": f"An error occurred while fetching semester data: {str(e)}"}), 500
                    else:
                        return jsonify({"error": "User ID is required"}), 400
                elif data.get('action') == 'calculate_gpa':
                    user_id = data.get('user_id')
                    courses = data.get('courses')
                    if not user_id:
                        logger.error("User ID is missing in calculate_gpa request")
                        return jsonify({'success': False, 'message': 'User ID is required.'})
                    if not courses:
                        logger.error("Courses list is missing in calculate_gpa request")
                        return jsonify({'success': False, 'message': 'No courses provided.'})
                    try:
                        result = functions.calculate_updated_gpa(int(user_id), courses)
                        if result['updated_gpa'] is None:
                            return jsonify({'success': False, 'message': 'Unable to calculate GPA.'})
                        return jsonify({
                            'success': True,
                            'updated_gpa': str(result['updated_gpa']),
                            'gpa_deficit': str(result['gpa_deficit'])
                        })
                    except Exception as e:
                        logger.error(f"Error calculating updated GPA: {e}", exc_info=True)
                        return jsonify({'success': False, 'message': 'Error calculating GPA.'})
            elif 'search_student' in request.form:
                student_id = request.form.get('student_id')
                logger.debug(f"Received student search request with student_ID: {student_id}")
                if student_id:
                    try:
                        user_id = functions.get_user_id_from_student_id(student_id)
                        if not user_id:
                            logger.warning(f"No user_ID found for student_ID: {student_id}")
                            flash(f"Student with ID {student_id} not found.", 'error')
                        else:
                            student_info = functions.fetch_student_info_by_id(user_id)
                            logger.debug(f"Fetched student info for user_ID {user_id}: {student_info}")
                            if student_info:
                                student_info['user_ID'] = user_id
                                gpa_deficit = functions.calculate_gpa_deficit(user_id)
                                logger.debug(f"GPA Deficit: {gpa_deficit}")
                                con_sem = functions.probation_semesters_count(user_id)
                                logger.debug(f"Consecutive semesters on probation: {con_sem}")
                                probation_status = functions.check_probation_status(user_id, con_sem)
                                logger.debug(f"Probation Status: {probation_status}")
                                consecutive_semesters = functions.count_consecutive_probation_semesters(user_id)
                                logger.debug(f"Consecutive Semesters on Probation: {consecutive_semesters}")
                                transcript = functions.fetch_student_transcript(user_id)
                                logger.debug(f"Fetched transcript: {transcript}")
                                recommended_courses = functions.recommend_courses(user_id) or []
                                logger.debug(f"Fetched recommended courses: {recommended_courses}")
                                unfinished_courses = functions.fetch_unfinished_courses(user_id)
                                logger.debug(f"Fetched unfinished courses: {unfinished_courses}")
                                study_plan_courses = functions.add_study_plan_courses(user_id)
                                logger.debug(f"Fetched study plan courses: {study_plan_courses}")
                                updated_recommended_courses = functions.fetch_updated_recommended_courses(user_id)
                                logger.debug(f"Fetched updated recommended courses: {updated_recommended_courses}")

                                # Categorize courses for dropdowns
                                core_electives = [course for course in study_plan_courses if course['Course Type'].startswith('Core Elective')]
                                university_electives = [course for course in study_plan_courses if course['Course Type'] == 'University Elective']
                                core_courses = [course for course in study_plan_courses if course['Course Type'] == 'Core']
                                university_requirements = [course for course in study_plan_courses if course['Course Type'] == 'University Requirement']

                                # Populate the recommended_courses table in the database
                                if recommended_courses:
                                    functions.populate_recommended_courses(user_id, recommended_courses)
                                    logger.debug("Populated recommended_courses table in the database.")

                                # Fetch calculator data
                                calculator_data = functions.fetch_calculator_data(user_id)
                                logger.debug(f"Fetched calculator data: {calculator_data}")

                                # Fetch semester data for GPA trend chart
                                semester_data = functions.calculate_semester_data(user_id)
                                logger.debug(f"Fetched semester data: {semester_data}")
                            else:
                                logger.warning(f"No data found for user_ID: {user_id}")
                                flash(f"Student with ID {student_id} not found.", 'error')
                    except Exception as e:
                        logger.error(f"Error during student search for student_ID {student_id}: {str(e)}", exc_info=True)
                        flash("An error occurred while searching for the student.", "error")
            elif 'send_advising_report' in request.form:
                logger.debug("Sending advising report")
                student_id = request.form.get('student_id')
                semester_id = request.form.get('semester_id')
                comment = request.form.get('comment')
                
                logger.debug(f"Student ID: {student_id}, Semester ID: {semester_id}")
                logger.debug(f"Comment: {comment}")

                attachment_path = None
                if 'attachment' in request.files:
                    file = request.files['attachment']
                    logger.debug(f"Attachment: {file.filename}")
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        attachment_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(attachment_path)
                        logger.debug(f"Attachment saved at: {attachment_path}")
                    else:
                        logger.warning("Invalid file type or no file provided")

                try:
                    result = functions.send_courses_to_advising_reports(
                        int(student_id),
                        int(semester_id),
                        attachment_path,
                        comment
                    )
                    logger.debug(f"Result from send_courses_to_advising_reports: {result}")
                    flash(result['message'], 'success' if result['success'] else 'error')
                    return jsonify(result)
                except Exception as e:
                    logger.error(f"Error sending advising report: {str(e)}", exc_info=True)
                    flash('An error occurred while sending the advising report.', 'error')
                    return jsonify({'success': False, 'message': 'An error occurred while sending the advising report.'})

            # Handle AJAX requests
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                if 'delete_course' in request.form:
                    id = request.form.get('id')
                    if id:
                        try:
                            functions.delete_recommended_course(int(id))
                            return jsonify({'success': True, 'message': f'Course {id} deleted successfully.'})
                        except Exception as e:
                            logger.error(f"Error deleting Course: {str(e)}")
                            return jsonify({'success': False, 'message': 'Error deleting course. Please try again.'})
                    else:
                        return jsonify({'success': False, 'message': 'Invalid ID.'})

                elif 'add_course' in request.form:
                    course_id = request.form.get('course_id')
                    user_id = request.form.get('user_id')
                    if course_id and user_id:
                        try:
                            study_plan_courses = functions.add_study_plan_courses(int(user_id))
                            course_in_plan = any(int(course['course_ID']) == int(course_id) for course in study_plan_courses)
                            if course_in_plan:
                                functions.add_recommended_course(int(course_id), int(user_id))
                                return jsonify({'success': True, 'message': 'Course added successfully to recommendations.'})
                            else:
                                return jsonify({'success': False, 'message': 'Selected course is not in the study plan.'})
                        except Exception as e:
                            logger.error(f"Error adding recommended course: {e}", exc_info=True)
                            return jsonify({'success': False, 'message': 'Error adding course.'})

        # Fetch availability slots for advisor
        advisor_slots = functions.fetch_availability_slots(advisor_id)
        logger.debug(f"Fetched advisor slots: {advisor_slots}")

        # Ensure recommended_courses is not None
        if recommended_courses is None:
            recommended_courses = []

        # Fetch semesters for the dropdown
        semesters = functions.fetch_semesters()
        logger.debug(f"Fetched semesters: {semesters}")

        if not semesters:
            flash("No semesters available. Please contact the administrator.", "error")

        # Render the page with all required context
        return render_template(
            'advising.html',
            advisor_info=advisor_info,
            advisor_slots=advisor_slots,
            student_info=student_info,
            gpa_deficit=gpa_deficit,
            probation_status=probation_status,
            consecutive_semesters=consecutive_semesters,
            transcript=transcript,
            recommended_courses=recommended_courses,
            unfinished_courses=unfinished_courses,
            study_plan_courses=study_plan_courses,
            updated_recommended_courses=updated_recommended_courses,
            core_electives=core_electives,
            university_electives=university_electives,
            core_courses=core_courses,
            university_requirements=university_requirements,
            calculator_data=calculator_data,
            semester_data=semester_data,
            semesters=semesters
        )

    except Exception as e:
        logger.error(f"Unexpected error in advising route: {str(e)}", exc_info=True)
        flash('An error occurred while loading the advising page. Please try again later.', 'error')
        return redirect(url_for('dashboard'))



@app.route('/headofadvising', methods=['GET', 'POST'])
@login_required
def headofadvising():
    if current_user.user_type_ID != 3:
        logger.debug(f"Access denied for user ID: {current_user.id} (type: {current_user.user_type_ID})")
        flash('Access denied. You are not the head of advising.', 'error')
        return redirect(url_for('dashboard'))
    try:
        head_id = functions.get_head_id(current_user.id)
        if not head_id:
            logger.error("Head ID not found.")
            flash('Error loading head of advising information. Please try again.', 'error')
            return redirect(url_for('dashboard'))

        head_info = functions.fetch_head_info(head_id)
        logger.debug(f"Advisor info: {head_info}")

        # POST Request Handlers
        if request.method == 'POST':
            if 'set_availability' in request.form:
                slot_date = request.form.get('slot_date')
                start_time = request.form.get('start_time')
                end_time = request.form.get('end_time')
                logger.debug(f"Received form data: slot_date={slot_date}, start_time={start_time}, end_time={end_time}")
                if slot_date and start_time and end_time:
                    try:
                        functions.add_head_slot(head_id, slot_date, start_time, end_time)
                        flash('Availability slot added successfully.', 'success')
                    except Exception as e:
                        logger.error(f"Error adding slot: {str(e)}")
                        flash('Error adding availability slot. Please try again.', 'error')
                else:
                    logger.warning("Incomplete form data received.")
                    flash('Please fill in all fields.', 'error')

            # Delete Availability Slot
            if 'delete_slot' in request.form:
                slot_id = request.form.get('slot_id')
                if slot_id:
                    try:
                        functions.delete_head_slot(int(slot_id))
                        flash(f'Slot {slot_id} deleted successfully.', 'success')
                    except Exception as e:
                        logger.error(f"Error deleting slot: {str(e)}")
                        flash('Error deleting slot. Please try again.', 'error')
                else:
                    flash('Invalid slot ID.', 'error')
        
        # Fetch Availability Slots
        availability_slots = functions.fetch_head_slots(head_id)
        logger.debug(f"Availability slots passed to template: {availability_slots}")


        # Reserved Slots for Chat Management
        reserved_slots = functions.fetch_head_slots(head_id)

        students_data = functions.get_headofadvising_summary(current_user.id)
        program_summary = functions.get_program_student_summary()
        
        return render_template(
            'headofadvising.html',
            students_data = students_data,
            program_summary = program_summary,
            availability_slots = availability_slots,
            reserved_slots = reserved_slots,
            head_info = head_info
        )
    except Exception as e:
        logger.error(f"Unexpected error in head of advising route: {str(e)}", exc_info=True)
        flash('An error occurred while loading the head of advising page. Please try again later.', 'error')
        return redirect(url_for('dashboard'))
    

@app.route('/headadvising', methods=['GET', 'POST'])
@login_required
def headadvising():
    logger.debug(f"Advising route accessed by user {current_user.id}")

    # Authorization Check
    if current_user.user_type_ID != 3:
        flash('Access denied. You are not the head of advising.', 'error')
        return redirect(url_for('dashboard'))

    try:

        # Initialize context variables
        student_info = None
        gpa_deficit = 0
        probation_status = False
        consecutive_semesters = 0
        transcript = None
        recommended_courses = []
        updated_recommended_courses = []
        unfinished_courses = None
        study_plan_courses = None
        core_electives = []
        university_electives = []
        core_courses = []
        university_requirements = []
        calculator_data = None
        semester_data = []

        # Handle student search
        if request.method == 'POST':
            if request.is_json:
                data = request.get_json()
                if data.get('get_semester_data'):
                    student_id = data.get('user_id')
                    if student_id:
                        try:

                            semester_data = functions.calculate_semester_data(student_id)
                            logger.debug(f"Calculated semester data for student {student_id}: {semester_data}")

                            if not semester_data:
                                return jsonify({"error": f"No semester data found for student with ID {student_id}"}), 404

                            return jsonify(semester_data)
                        except Exception as e:
                            logger.error(f"Error fetching semester data: {str(e)}", exc_info=True)
                            return jsonify({"error": f"An error occurred while fetching semester data: {str(e)}"}), 500
                    else:
                        return jsonify({"error": "User ID is required"}), 400
                elif data.get('action') == 'calculate_gpa':
                    user_id = data.get('user_id')
                    courses = data.get('courses')
                    if not user_id:
                        logger.error("User ID is missing in calculate_gpa request")
                        return jsonify({'success': False, 'message': 'User ID is required.'})
                    if not courses:
                        logger.error("Courses list is missing in calculate_gpa request")
                        return jsonify({'success': False, 'message': 'No courses provided.'})
                    try:
                        result = functions.calculate_updated_gpa(int(user_id), courses)
                        if result['updated_gpa'] is None:
                            return jsonify({'success': False, 'message': 'Unable to calculate GPA.'})
                        return jsonify({
                            'success': True,
                            'updated_gpa': str(result['updated_gpa']),
                            'gpa_deficit': str(result['gpa_deficit'])
                        })
                    except Exception as e:
                        logger.error(f"Error calculating updated GPA: {e}", exc_info=True)
                        return jsonify({'success': False, 'message': 'Error calculating GPA.'})
            elif 'search_student' in request.form:
                student_id = request.form.get('student_id')
                logger.debug(f"Received student search request with student_ID: {student_id}")
                if student_id:
                    try:
                        user_id = functions.get_user_id_from_student_id(student_id)
                        if not user_id:
                            logger.warning(f"No user_ID found for student_ID: {student_id}")
                            flash(f"Student with ID {student_id} not found.", 'error')
                        else:
                            student_info = functions.fetch_student_info_by_id(user_id)
                            logger.debug(f"Fetched student info for user_ID {user_id}: {student_info}")
                            if student_info:
                                student_info['user_ID'] = user_id
                                gpa_deficit = functions.calculate_gpa_deficit(user_id)
                                logger.debug(f"GPA Deficit: {gpa_deficit}")
                                con_sem = functions.probation_semesters_count(user_id)
                                logger.debug(f"Consecutive semesters on probation: {con_sem}")
                                probation_status = functions.check_probation_status(user_id, con_sem)
                                logger.debug(f"Probation Status: {probation_status}")
                                consecutive_semesters = functions.count_consecutive_probation_semesters(user_id)
                                logger.debug(f"Consecutive Semesters on Probation: {consecutive_semesters}")
                                transcript = functions.fetch_student_transcript(user_id)
                                logger.debug(f"Fetched transcript: {transcript}")
                                recommended_courses = functions.recommend_courses(user_id) or []
                                logger.debug(f"Fetched recommended courses: {recommended_courses}")
                                unfinished_courses = functions.fetch_unfinished_courses(user_id)
                                logger.debug(f"Fetched unfinished courses: {unfinished_courses}")
                                study_plan_courses = functions.add_study_plan_courses(user_id)
                                logger.debug(f"Fetched study plan courses: {study_plan_courses}")
                                updated_recommended_courses = functions.fetch_updated_recommended_courses(user_id)
                                logger.debug(f"Fetched updated recommended courses: {updated_recommended_courses}")

                                # Categorize courses for dropdowns
                                core_electives = [course for course in study_plan_courses if course['Course Type'].startswith('Core Elective')]
                                university_electives = [course for course in study_plan_courses if course['Course Type'] == 'University Elective']
                                core_courses = [course for course in study_plan_courses if course['Course Type'] == 'Core']
                                university_requirements = [course for course in study_plan_courses if course['Course Type'] == 'University Requirement']

                                # Populate the recommended_courses table in the database
                                if recommended_courses:
                                    functions.populate_recommended_courses(user_id, recommended_courses)
                                    logger.debug("Populated recommended_courses table in the database.")

                                # Fetch calculator data
                                calculator_data = functions.fetch_calculator_data(user_id)
                                logger.debug(f"Fetched calculator data: {calculator_data}")

                                # Fetch semester data for GPA trend chart
                                semester_data = functions.calculate_semester_data(user_id)
                                logger.debug(f"Fetched semester data: {semester_data}")
                            else:
                                logger.warning(f"No data found for user_ID: {user_id}")
                                flash(f"Student with ID {student_id} not found.", 'error')
                    except Exception as e:
                        logger.error(f"Error during student search for student_ID {student_id}: {str(e)}", exc_info=True)
                        flash("An error occurred while searching for the student.", "error")

            # Handle AJAX requests
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                if 'delete_course' in request.form:
                    id = request.form.get('id')
                    if id:
                        try:
                            functions.delete_recommended_course(int(id))
                            return jsonify({'success': True, 'message': f'Course {id} deleted successfully.'})
                        except Exception as e:
                            logger.error(f"Error deleting Course: {str(e)}")
                            return jsonify({'success': False, 'message': 'Error deleting course. Please try again.'})
                    else:
                        return jsonify({'success': False, 'message': 'Invalid ID.'})

                elif 'add_course' in request.form:
                    course_id = request.form.get('course_id')
                    user_id = request.form.get('user_id')
                    if course_id and user_id:
                        try:
                            study_plan_courses = functions.add_study_plan_courses(int(user_id))
                            course_in_plan = any(int(course['course_ID']) == int(course_id) for course in study_plan_courses)
                            if course_in_plan:
                                functions.add_recommended_course(int(course_id), int(user_id))
                                return jsonify({'success': True, 'message': 'Course added successfully to recommendations.'})
                            else:
                                return jsonify({'success': False, 'message': 'Selected course is not in the study plan.'})
                        except Exception as e:
                            logger.error(f"Error adding recommended course: {e}", exc_info=True)
                            return jsonify({'success': False, 'message': 'Error adding course.'})


        # Ensure recommended_courses is not None
        if recommended_courses is None:
            recommended_courses = []

        # Render the page with all required context
        return render_template(
            'advisinghead.html',
            student_info=student_info,
            gpa_deficit=gpa_deficit,
            probation_status=probation_status,
            consecutive_semesters=consecutive_semesters,
            transcript=transcript,
            recommended_courses=recommended_courses,
            unfinished_courses=unfinished_courses,
            study_plan_courses=study_plan_courses,
            updated_recommended_courses=updated_recommended_courses,
            core_electives=core_electives,
            university_electives=university_electives,
            core_courses=core_courses,
            university_requirements=university_requirements,
            calculator_data=calculator_data,
            semester_data=semester_data
        )

    except Exception as e:
        logger.error(f"Unexpected error in advising route: {str(e)}", exc_info=True)
        flash('An error occurred while loading the advising page. Please try again later.', 'error')
        return redirect(url_for('dashboard'))
    


@app.route('/update_config', methods=['GET', 'POST'])
def update_config():
    if current_user.user_type_ID != 3:
        flash('Access denied. You are not the head of advising.', 'error')
        return redirect(url_for('dashboard'))
    
    # Define configuration types and their default values
    config_definitions = {
        'low_gpa_credit_hours': {'type': int, 'default': 16},
        'medium_gpa_credit_hours': {'type': int, 'default': 18},
        'high_gpa_credit_hours': {'type': int, 'default': 21},
        'max_university_requirement': {'type': int, 'default': 7},
        'max_core_elective_1': {'type': int, 'default': 2},
        'max_core_elective_2': {'type': int, 'default': 2},
        'max_university_elective': {'type': int, 'default': 2},
        'consecutive_semesters': {'type': int, 'default': 3},
        'min_gpa': {'type': float, 'default': 2.0},
        'grade_options': {'type': str, 'default': 'A+,A,A-,B+,B,B-,C+,C,C-,D+,D,F'}
    }
    
    if request.method == 'POST':
        try:
            success_count = 0
            for config_name, config_def in config_definitions.items():
                value = request.form.get(config_name)
                if value is not None and value.strip():
                    try:
                        # Convert and validate the value
                        if config_def['type'] in (int, float):
                            typed_value = config_def['type'](value)
                            
                            # Validate ranges
                            if config_def['type'] == int:
                                if not (1 <= typed_value <= 30):
                                    raise ValueError(f"{config_name} must be between 1 and 30")
                            elif config_name == 'min_gpa':
                                if not (0.0 <= typed_value <= 4.0):
                                    raise ValueError(f"{config_name} must be between 0.0 and 4.0")
                            
                            # Store as string
                            update_configuration(config_name, str(typed_value))
                        else:
                            # Handle grade options
                            if config_name == 'grade_options':
                                grades = [g.strip() for g in value.split(',')]
                                if not all(g and len(g) <= 2 for g in grades):
                                    raise ValueError('Invalid grade format')
                            update_configuration(config_name, value.strip())
                        
                        success_count += 1
                        
                    except ValueError as e:
                        flash(f'Invalid value for {config_name}: {str(e)}', 'error')
                        return redirect(url_for('update_config'))
            
            if success_count > 0:
                flash(f'Successfully updated {success_count} configurations!', 'success')
            return redirect(url_for('update_config'))
            
        except Exception as e:
            flash(f'Error updating configurations: {str(e)}', 'error')
            return redirect(url_for('update_config'))
    
    # Fetch current configurations
    config = {}
    for config_name, config_def in config_definitions.items():
        try:
            value = fetch_configuration(config_name)
            config[config_name] = value if value is not None else str(config_def['default'])
        except Exception as e:
            print(f"Error fetching {config_name}: {str(e)}")
            config[config_name] = str(config_def['default'])
    
    return render_template('config.html', config=config)



@app.route('/advising_reports', methods=['GET', 'POST'])
@login_required
def advising_reports():
    if current_user.user_type_ID != 3:
        flash('Access denied. You are not the head of advising.', 'error')
        return redirect(url_for('dashboard'))
                        
    selected_student = None
    reports = []

    if request.method == 'POST':
        student_id = request.form.get('student_id')
        if student_id:
            selected_student = functions.get_student_info(student_id)
            if selected_student:
                reports = functions.fetch_advising_report(student_id)
            else:
                flash('Student not found. Please try again.', 'error')

    try:
        #students = functions.get_all_students()
        return render_template('advising_reports.html',
                               #students=students,
                               selected_student=selected_student,
                               reports=reports)
    except Exception as e:
        logger.error(f"Error fetching data for advising reports: {str(e)}")
        flash('An error occurred while loading the data. Please try again.', 'error')
        return redirect(url_for('dashboard'))


@app.route('/add_recommended_course', methods=['POST'])
@login_required
def add_recommended_course():
    if current_user.user_type_ID != 1:
        return jsonify({'success': False, 'message': 'Access denied.'})

    course_code = request.form.get('course_code')
    student_id = request.form.get('student_id')

    if not course_code or not student_id:
        return jsonify({'success': False, 'message': 'Missing course code or student ID.'})

    try:
        # Implement the logic to add the course to the recommended list
        functions.add_course_to_recommended(student_id, course_code)
        return jsonify({'success': True, 'message': 'Course added successfully.'})
    except Exception as e:
        logger.error(f"Error adding course to recommended list: {str(e)}")
        return jsonify({'success': False, 'message': 'Error adding course. Please try again.'})

def add_study_plan_courses(user_id):
    # ... (existing code to fetch study plan courses)
    merged_courses = functions.fetch_study_plan_courses(user_id) # Assuming this function exists

    # Categorize courses
    core_electives = [course for course in merged_courses if course['Course Type'].startswith('Core Elective')]
    university_electives = [course for course in merged_courses if course['Course Type'] == 'University Elective']
    core_courses = [course for course in merged_courses if course['Course Type'] == 'Core']
    university_requirements = [course for course in merged_courses if course['Course Type'] == 'University Requirement']

    return {
        'core_electives': core_electives,
        'university_electives': university_electives,
        'core_courses': core_courses,
        'university_requirements': university_requirements
    }



# Add these functions to your Flask app
@app.route('/update_chat_status', methods=['POST'])
def update_chat_status():
    try:
        slot_id = request.form.get('slot_id')
        is_active = request.form.get('is_active')
        
        query = """
            UPDATE advisor_slots 
            SET is_active = %s 
            WHERE id = %s
        """
        execute_update(query, (is_active, slot_id))
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error updating chat status: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    
@app.route('/get_active_chat_session', methods=['GET'])
@login_required
def get_active_chat_session():
    advisor_id = functions.get_advisor_id(current_user.id)
    active_slot = functions.get_active_chat_slot(advisor_id)
    if active_slot:
        return jsonify({'active_session': True, 'slot_id': active_slot['Slot_ID']})
    else:
        return jsonify({'active_session': False})


@app.route('/reserve-slot', methods=['POST'])
@login_required
def reserve_slot():
    try:
        # Parse JSON from the AJAX request
        data = request.get_json()
        logger.debug(f"Received request data: {data}")

        # Extract slot_id
        slot_id = data.get('slot_id')
        if not slot_id:
            logger.warning("No slot_id provided in request.")
            return jsonify({"success": False, "message": "Slot ID is missing."}), 400

        # Fetch the current student's ID
        user_id = current_user.id
        logger.debug(f"Current user ID: {user_id}")
        if not user_id:
            logger.warning("Current user ID is None.")
            return jsonify({"success": False, "message": "User is not authenticated."}), 401

        student_id = functions.fetch_student_id_by_user_id(user_id)
        if not student_id:
            logger.warning(f"No student ID found for user_id {user_id}.")
            return jsonify({"success": False, "message": "Could not find student information."}), 400

        logger.debug(f"Student ID: {student_id}")

        # Attempt to reserve the slot
        reservation_success = functions.reserve_advisor_slot(student_id, slot_id)
        if reservation_success:
            logger.info(f"Slot {slot_id} successfully reserved by student {student_id}.")
            return jsonify({"success": True, "message": "Slot reserved successfully."}), 200
        else:
            logger.warning(f"Failed to reserve slot {slot_id}. It might already be reserved.")
            return jsonify({"success": False, "message": "Slot is already reserved or invalid."}), 400

    except Exception as e:
        logger.error(f"Error in /reserve-slot: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "An error occurred during reservation."}), 500



@app.route('/logout')
@login_required
def logout():
    logger.debug(f"Logging out user ID: {current_user.id}")
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

# SocketIO event handlers
@socketio.on('connect')
def handle_connect():
    logger.debug('Client connected to WebSocket')

@socketio.on('disconnect')
def handle_disconnect():
    logger.debug('Client disconnected from WebSocket')

@socketio.on('join')
def on_join(data):
    try:
        room = str(data['room'])
        logger.debug(f'Client joining room: {room}')
        join_room(room)
        emit('status', {'message': 'User has joined the chat'}, room=room)
    except Exception as e:
        logger.error(f'Error in join handler: {str(e)}')

@socketio.on('leave')
def on_leave(data):
    try:
        room = str(data['room'])
        logger.debug(f'Client leaving room: {room}')
        leave_room(room)
        emit('status', {'message': 'User has left the chat'}, room=room)
    except Exception as e:
        logger.error(f'Error in leave handler: {str(e)}')

@socketio.on('message')
def handle_message(data):
    try:
        room = str(data['room'])
        message = data['message']
        sender_id = current_user.id
        
        logger.info(f'Message received - Room: {room}, Sender ID: {sender_id}, Message: {message}')

        # Get receiver ID
        receiver_id = functions.get_receiver_id_from_slot(room, sender_id)
        logger.debug(f"Determined receiver_id: {receiver_id} for sender_id: {sender_id} in room: {room}")
        
        if receiver_id is None:
            logger.error(f"Could not determine receiver for room {room}. Sender ID: {sender_id}")
            emit('error', {'message': 'Failed to process message'}, room=request.sid)
            return

        # Get sender's name based on their role
        query = """
            SELECT 
                COALESCE(a.advisor_name, s.student_name) as sender_name
            FROM users u
            LEFT JOIN advisor a ON u.user_ID = a.user_ID
            LEFT JOIN student s ON u.user_ID = s.user_ID
            WHERE u.user_ID = %s
        """
        result = execute_query(query, (sender_id,))
        sender_name = result[0]['sender_name'] if result else 'Unknown User'

        # Save the message to the database
        if functions.save_message(room, sender_id, receiver_id, message):
            # Broadcast the message to all clients in the room with the sender's name
            emit('message', {
                'sender': sender_name,  # Use name instead of ID
                'message': message,
                'timestamp': datetime.now().strftime('%H:%M:%S')
            }, room=room)
        else:
            logger.error(f'Failed to save message for room {room}, sender {sender_id}')
            emit('error', {'message': 'Failed to save message'}, room=request.sid)

    except Exception as e:
        logger.exception(f'Error in message handler: {str(e)}')
        emit('error', {'message': 'Failed to process message'}, room=request.sid)

if __name__ == '__main__':
    logger.debug("Starting the Flask app with SocketIO...")
    socketio.run(app, debug=True)
