from db_utils import create_connection, execute_query, execute_update, fetch_configuration
import hashlib
import pandas as pd
from decimal import Decimal
from typing import Optional
from math import ceil
from typing import List, Tuple, Dict, Any
from decimal import Decimal, getcontext
import numpy as np
import logging
import re
import math
from datetime import datetime


# Configure logging
logging.basicConfig(level=logging.DEBUG,  # Set the logging level
                    format='%(asctime)s %(levelname)s %(message)s',
                    handlers=[
                        logging.StreamHandler()  # Output logs to the console
                    ])

# Create logger for the current module
logger = logging.getLogger(__name__)


def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()


def authenticate(email, password):
    hashed_password = hash_password(password)
    query = "SELECT * FROM users WHERE e_mail=%s AND pass_word=%s"
    result = execute_query(query, (email, hashed_password))
    return result if result else []


def fetch_user_name(user_type_ID, user_ID):
    if user_type_ID == 2:  
        query = "SELECT student_name FROM student WHERE user_ID=%s"
        result = execute_query(query, (user_ID,))
        return result[0]['student_name'] if result else 'Unknown Student'
    elif user_type_ID == 1:  
        query = "SELECT advisor_name FROM advisor WHERE user_ID=%s"
        result = execute_query(query, (user_ID,))
        return result[0]['advisor_name'] if result else 'Unknown Staff'
    return 'Unknown User'


def fetch_student_info(user_ID):
    query = """
        SELECT s.student_name, s.student_ID, gt.cumulative_gpa, a.advisor_name, s.advisor_ID
        FROM student s
        LEFT JOIN advisor a ON s.advisor_ID = a.advisor_ID
        LEFT JOIN semester_gpa gt ON s.student_ID = gt.student_ID
        WHERE s.user_ID = %s
        ORDER BY gt.semester_ID DESC
        LIMIT 1
    """
    result = execute_query(query, (user_ID,))
    
    if result:
        return {
            'student_name': result[0]['student_name'],
            'student_ID': result[0]['student_ID'],
            'gpa': result[0]['cumulative_gpa'],  
            'advisor_name': result[0]['advisor_name'],
            'advisor_ID': result[0]['advisor_ID']
        }
    else:
        return {
            'student_name': 'Unknown Student',
            'student_ID': 'Unknown',
            'gpa': 'Unknown',
            'advisor_name': 'Unknown Advisor',
            'advisor_ID': 'Unknown'
        }


def fetch_user_info(user_type_ID, user_ID):
    if user_type_ID == 2:  # Student
        return fetch_student_info(user_ID)
    elif user_type_ID == 1:  # Advisor
        query = """
        SELECT a.advisor_name, a.advisor_ID
        FROM advisor AS a
        WHERE a.user_ID = %s
        """
        result = execute_query(query, (user_ID,))
        if result:
            return {
                'user_name': result[0]['advisor_name'],
                'advisor_ID': result[0]['advisor_ID']
            }
        return {'user_name': 'Unknown Staff', 'advisor_ID': None}
    
    return {'user_name': 'Unknown User'}


def fetch_student_transcript(user_id):
    GRADE_TO_POINTS = {
    'A+': 4.0, 'A': 4.0, 'A-': 3.7,
    'B+': 3.3, 'B': 3.0, 'B-': 2.7,
    'C+': 2.3, 'C': 2.0, 'C-': 1.7,
    'D+': 1.3, 'D': 1.0, 'F': 0.0, 'W': 0.0, 'FA': 0.0
    }
    logger.debug(f"Fetching transcript for user_id: {user_id}")
    
    # Step 1: Fetch the student_ID corresponding to the user_id
    student_id_query = "SELECT student_ID FROM student WHERE user_ID = %s"
    try:
        student_id_result = execute_query(student_id_query, (user_id,))
        if not student_id_result:
            logger.warning(f"No student found for user_id {user_id}")
            return pd.DataFrame()

        student_id = student_id_result[0]['student_ID']
        logger.debug(f"Found student_ID {student_id} for user_id {user_id}")
    except Exception as e:
        logger.error(f"Error fetching student_ID for user_id {user_id}: {e}")
        return pd.DataFrame()

    # Step 2: Fetch the transcript using the student_ID
    query = """
        SELECT 
            ec.grade, 
            c.course_name, 
            c.course_code, 
            c.credit_hours,
            c.course_type, 
            ec.semester_ID,
            s.semester AS semester_name,
            s.semester_year,
            COALESCE(repetition_counts.repetition_count, 0) AS repetition_count
        FROM sis_enrolled_courses ec
        JOIN course c ON ec.course_id = c.course_id
        JOIN sis_semester s ON ec.semester_ID = s.semester_ID
        LEFT JOIN (
            SELECT 
                student_id, 
                course_id,
                COUNT(*) - 1 AS repetition_count
            FROM sis_enrolled_courses
            WHERE student_id = %s
            GROUP BY student_id, course_id
            HAVING COUNT(*) > 1
        ) AS repetition_counts ON ec.student_id = repetition_counts.student_id AND ec.course_id = repetition_counts.course_id
        WHERE ec.student_id = %s
        AND NOT EXISTS (
            SELECT 1 
            FROM sis_enrolled_courses ec2
            WHERE ec2.student_id = ec.student_id 
            AND ec2.course_id = ec.course_id 
            AND ec2.semester_ID = ec.semester_ID
            AND ec2.grade > ec.grade
        )
        ORDER BY ec.semester_ID, c.course_code
    """
    try:
        result = execute_query(query, (student_id, student_id))
        logger.debug(f"Transcript query result for student_id {student_id}: {result}")

        if result:
            # Group courses by semester
            grouped_transcript = {}
            for row in result:
                semester_key = f"{row['semester_name']} {row['semester_year']}"
                if semester_key not in grouped_transcript:
                    grouped_transcript[semester_key] = []
                grouped_transcript[semester_key].append({
                    'course_code': row['course_code'],
                    'course_name': row['course_name'],
                    'course_type': row['course_type'],
                    'credit_hours': row['credit_hours'],
                    'grade': row['grade'],
                    'points': GRADE_TO_POINTS.get(row['grade'], 0.0),
                    'repetition_count': row['repetition_count']
                })

            logger.debug(f"Grouped transcript: {grouped_transcript}")
            return grouped_transcript
        else:
            logger.warning(f"No transcript data found for student_id {student_id}")
            return {}
    except Exception as e:
        logger.error(f"Error executing transcript query: {e}")
        return {}


def student_transcript(user_id):
    """
    Fetch the transcript for a student based on user_id.
    Returns a list of course dictionaries, each with semester details.
    """
    GRADE_TO_POINTS = {
        'A+': 4.0, 'A': 4.0, 'A-': 3.7,
        'B+': 3.3, 'B': 3.0, 'B-': 2.7,
        'C+': 2.3, 'C': 2.0, 'C-': 1.7,
        'D+': 1.3, 'D': 1.0, 'F': 0.0, 'W': 0.0, 'FA': 0.0
    }
    logger.debug(f"Fetching transcript for user_id: {user_id}")
    
    # Step 1: Fetch the student_ID corresponding to the user_id
    student_id_query = "SELECT student_ID FROM student WHERE user_ID = %s"
    try:
        student_id_result = execute_query(student_id_query, (user_id,))
        if not student_id_result:
            logger.warning(f"No student found for user_id {user_id}")
            return []

        student_id = student_id_result[0]['student_ID']
        logger.debug(f"Found student_ID {student_id} for user_id {user_id}")
    except Exception as e:
        logger.error(f"Error fetching student_ID for user_id {user_id}: {e}")
        return []

    # Step 2: Fetch the transcript using the student_ID
    query = """
        SELECT 
            ec.grade, 
            c.course_name, 
            c.course_code, 
            c.credit_hours,
            c.course_type, 
            ec.semester_ID,
            s.semester AS semester_name,
            s.semester_year,
            COALESCE(repetition_counts.repetition_count, 0) AS repetition_count
        FROM sis_enrolled_courses ec
        JOIN course c ON ec.course_id = c.course_id
        JOIN sis_semester s ON ec.semester_ID = s.semester_ID
        LEFT JOIN (
            SELECT 
                student_id, 
                course_id,
                COUNT(*) - 1 AS repetition_count
            FROM sis_enrolled_courses
            WHERE student_id = %s
            GROUP BY student_id, course_id
            HAVING COUNT(*) > 1
        ) AS repetition_counts ON ec.student_id = repetition_counts.student_id AND ec.course_id = repetition_counts.course_id
        WHERE ec.student_id = %s
        AND NOT EXISTS (
            SELECT 1 
            FROM sis_enrolled_courses ec2
            WHERE ec2.student_id = ec.student_id 
            AND ec2.course_id = ec.course_id 
            AND ec2.semester_ID = ec.semester_ID
            AND ec2.grade > ec.grade
        )
        ORDER BY ec.semester_ID, c.course_code
    """
    try:
        result = execute_query(query, (student_id, student_id))
        logger.debug(f"Transcript query result for student_id {student_id}: {result}")

        if result:
            # Flatten the grouped transcript into a list
            transcript = []
            for row in result:
                transcript.append({
                    'course_code': row['course_code'],
                    'course_name': row['course_name'],
                    'course_type': row['course_type'],
                    'credit_hours': row['credit_hours'],
                    'grade': row['grade'],
                    'points': GRADE_TO_POINTS.get(row['grade'], 0.0),
                    'repetition_count': row['repetition_count'],
                    'semester': f"{row['semester_name']} {row['semester_year']}"
                })

            logger.debug(f"Flattened transcript: {transcript}")
            return transcript
        else:
            logger.warning(f"No transcript data found for student_id {student_id}")
            return []
    except Exception as e:
        logger.error(f"Error executing transcript query: {e}")
        return []



def fetch_student_info_by_id(user_id):
    logger.debug(f"Fetching student info for user_id: {user_id}")
    # First, fetch the student_ID corresponding to the user_id
    student_id_query = "SELECT student_ID FROM student WHERE user_ID = %s"
    try:
        student_id_result = execute_query(student_id_query, (user_id,))
        if not student_id_result:
            logger.warning(f"No student found for user_id {user_id}")
            return None

        student_id = student_id_result[0]['student_ID']
        logger.debug(f"Found student_ID {student_id} for user_id {user_id}")
    except Exception as e:
        logger.error(f"Error fetching student_ID for user_id {user_id}: {e}")
        return None

    # Fetch the student's detailed information using the student_ID
    query = """
        WITH EnrolledDistinct AS (
            SELECT 
                ec.student_ID,
                c.course_ID,
                c.credit_hours,
                ROW_NUMBER() OVER (PARTITION BY ec.student_ID, c.course_ID ORDER BY ec.course_ID) AS course_instance
            FROM sis_enrolled_courses ec
            LEFT JOIN course c ON ec.course_ID = c.course_ID
            WHERE ec.grade NOT IN ('W', 'FA', 'I', 'F')
        )
        SELECT 
            s.student_name, 
            s.student_ID, 
            a.advisor_name, 
            s.program_ID,
            s.advisor_ID,
            p.total_hours AS program_total_hours,
            COALESCE(SUM(CASE WHEN ed.course_instance = 1 THEN ed.credit_hours ELSE 0 END), 0) AS total_credit_hours,
            (SELECT sg.cumulative_gpa
             FROM semester_gpa sg
             WHERE sg.student_ID = s.student_ID
             ORDER BY sg.semester_ID DESC
             LIMIT 1) AS cumulative_gpa
        FROM student s
        LEFT JOIN advisor a ON s.advisor_ID = a.advisor_ID
        LEFT JOIN EnrolledDistinct ed ON s.student_ID = ed.student_ID
        LEFT JOIN program p ON s.program_ID = p.program_ID
        WHERE s.student_ID = %s
        GROUP BY s.student_name, s.student_ID, a.advisor_name, s.program_ID, p.total_hours
    """
    try:
        result = execute_query(query, (student_id,))
        logger.debug(f"Query result for student_id {student_id}: {result}")
        if result:
            student_info = result[0]
            # Calculate additional fields
            student_info['remaining_credit_hours'] = (
                student_info['program_total_hours'] - student_info['total_credit_hours']
            )
            student_info['completion_percentage'] = round(
                (student_info['total_credit_hours'] / student_info['program_total_hours']) * 100, 0
            )
            logger.debug(f"Processed student info: {student_info}")
            return student_info
        else:
            logger.warning(f"No detailed student info found for student_id {student_id}")
    except Exception as e:
        logger.error(f"Error fetching detailed student info: {e}")
    return None


def get_student_info(student_id):
    
    # Fetch the student's detailed information using the student_ID
    query = """
        WITH EnrolledDistinct AS (
            SELECT 
                ec.student_ID,
                c.course_ID,
                c.credit_hours,
                ROW_NUMBER() OVER (PARTITION BY ec.student_ID, c.course_ID ORDER BY ec.course_ID) AS course_instance
            FROM sis_enrolled_courses ec
            LEFT JOIN course c ON ec.course_ID = c.course_ID
            WHERE ec.grade NOT IN ('W', 'FA', 'I', 'F')
        )
        SELECT 
            s.student_name, 
            s.student_ID, 
            a.advisor_name, 
            s.program_ID,
            s.advisor_ID,
            p.total_hours AS program_total_hours,
            COALESCE(SUM(CASE WHEN ed.course_instance = 1 THEN ed.credit_hours ELSE 0 END), 0) AS total_credit_hours,
            (SELECT sg.cumulative_gpa
             FROM semester_gpa sg
             WHERE sg.student_ID = s.student_ID
             ORDER BY sg.semester_ID DESC
             LIMIT 1) AS cumulative_gpa
        FROM student s
        LEFT JOIN advisor a ON s.advisor_ID = a.advisor_ID
        LEFT JOIN EnrolledDistinct ed ON s.student_ID = ed.student_ID
        LEFT JOIN program p ON s.program_ID = p.program_ID
        WHERE s.student_ID = %s
        GROUP BY s.student_name, s.student_ID, a.advisor_name, s.program_ID, p.total_hours
    """
    try:
        result = execute_query(query, (student_id,))
        logger.debug(f"Query result for student_id {student_id}: {result}")
        if result:
            student_info = result[0]
            # Calculate additional fields
            student_info['remaining_credit_hours'] = (
                student_info['program_total_hours'] - student_info['total_credit_hours']
            )
            student_info['completion_percentage'] = round(
                (student_info['total_credit_hours'] / student_info['program_total_hours']) * 100, 0
            )
            logger.debug(f"Processed student info: {student_info}")
            return student_info
        else:
            logger.warning(f"No detailed student info found for student_id {student_id}")
    except Exception as e:
        logger.error(f"Error fetching detailed student info: {e}")
    return None


def prob(student_id, consecutive_semesters=None):
    # Fetch the probation threshold or default to 2
    if consecutive_semesters is None:
        consecutive_semesters = int(fetch_configuration('consecutive_semesters') or 2)

    query = """
        SELECT semester_ID, cumulative_gpa
        FROM semester_gpa  
        WHERE student_id = %s
        ORDER BY semester_ID ASC
    """
    result = execute_query(query, (student_id,))
    
    # Prepare the list of (semester_ID, cumulative_gpa) tuples
    semesters = [(row['semester_ID'], row['cumulative_gpa']) for row in result]

    count = 0
    for semester_id, cumulative_gpa in semesters:
        if cumulative_gpa < 2.0:
            count += 1
            if count >= consecutive_semesters:
                return True  # Probation threshold met
        else:
            count = 0  # Reset count if GPA is above threshold

    return False  # No probation


def check_probation_status(user_id: int, con_sem: int) -> bool:
    """
    Check if a student is on probation based on their user ID and consecutive semesters.

    Args:
        user_id (int): The user ID of the student.
        con_sem (int): The count of consecutive semesters below the threshold GPA.

    Returns:
        bool: True if the student is on probation, False otherwise.
    """
    try:
        # Fetch the student_ID from the user_ID
        student_id = fetch_student_id_by_user_id(user_id)
        if not student_id:
            logger.warning(f"No student ID found for user_id {user_id}. Cannot check probation status.")
            return False

        logger.debug(f"Checking probation status for student_id {student_id}")

        # Query to fetch semester GPA data
        query = """
            SELECT semester_ID, cumulative_gpa
            FROM semester_gpa  
            WHERE student_id = %s
            ORDER BY semester_ID ASC
        """
        result = execute_query(query, (student_id,))
        if not result:
            logger.warning(f"No GPA data found for student_id {student_id}")
            return False

        logger.debug(f"Fetched semester GPA data for student_id {student_id}: {result}")

        # Compare `con_sem` with the configured threshold or default to 3
        probation_threshold = int(fetch_configuration('consecutive_semesters') or 3)
        if con_sem >= probation_threshold:
            logger.info(f"Student {student_id} is on probation (con_sem={con_sem}, threshold={probation_threshold})")
            return True

        logger.info(f"Student {student_id} is not on probation (con_sem={con_sem}, threshold={probation_threshold})")
        return False
    except Exception as e:
        logger.error(f"Error checking probation status for user_id {user_id}: {e}", exc_info=True)
        return False

def get_advisor_student_summary(advisor_id: int) -> dict:
    try:
        # Step 1: Fetch total students assigned to the advisor
        total_students_query = "SELECT student_ID FROM student WHERE advisor_ID = %s;"
        students = execute_query(total_students_query, (advisor_id,))
        total_students = len(students)

        if total_students == 0:
            return {
                "total_students": 0,
                "students_on_probation": 0,
                "students_advised": 0
            }

        student_ids = [student['student_ID'] for student in students]

        # Step 2: Count students on probation
        probation_count = 0
        for student_id in student_ids:
            # Query to fetch GPA data for the student, ordered by semester
            probation_query = """
                SELECT semester_ID, cumulative_gpa
                FROM semester_gpa
                WHERE student_ID = %s
                ORDER BY semester_ID ASC;
            """
            gpa_results = execute_query(probation_query, (student_id,))

            if not gpa_results:
                continue

            # Convert results to DataFrame
            df = pd.DataFrame(gpa_results, columns=["semester_ID", "cumulative_gpa"])

            # Separate semesters ending with '3' for special handling
            regular_semesters = df[~df["semester_ID"].astype(str).str.endswith("3")].copy()

            # Initialize counters for consecutive probation semesters
            consecutive_count = 0
            max_consecutive_count = 0

            # Process regular semesters
            for _, row in regular_semesters.iterrows():
                cumulative_gpa = float(row["cumulative_gpa"])

                if cumulative_gpa < 2.0:
                    consecutive_count += 1
                    max_consecutive_count = max(max_consecutive_count, consecutive_count)
                else:
                    consecutive_count = 0  # Reset streak

            # Check if max consecutive probation semesters meet threshold
            probation_threshold = int(fetch_configuration('consecutive_semesters') or 3)
            if max_consecutive_count >= probation_threshold:
                probation_count += 1

        # Step 3: Count students with completed advising for active semesters
        # Dynamically generate the placeholders for the IN clause
        placeholders = ', '.join(['%s'] * len(student_ids))
        advising_query = f"""
            SELECT DISTINCT ar.student_ID
            FROM advising_reports ar
            JOIN sis_semester ss ON ar.semester_ID = ss.semester_ID
            WHERE ar.student_ID IN ({placeholders}) AND ss.active = 1;
        """
        advising_result = execute_query(advising_query, tuple(student_ids))
        advised_students = len(advising_result)

        # Return summary
        return {
            "total_students": total_students,
            "students_on_probation": probation_count,
            "students_advised": advised_students
        }

    except Exception as e:
        logger.error(f"Error fetching student summary for advisor {advisor_id}: {e}", exc_info=True)
        return {
            "total_students": 0,
            "students_on_probation": 0,
            "students_advised": 0
        }




def recommend_courses(user_id):
    """
    Recommend courses for a student based on their GPA, completed courses, and study plan.
    If the student is on probation, recommend only retake courses.
    Returns a list of recommended courses for the student.
    """
    try:
        # Fetch student ID from user ID
        student_id_query = "SELECT student_ID FROM student WHERE user_ID = %s"
        student_id_result = execute_query(student_id_query, (user_id,))
        if not student_id_result:
            raise ValueError(f"No student found for user ID {user_id}.")
        student_id = student_id_result[0]['student_ID']
        logger.debug(f"Found student_ID {student_id} for user_id {user_id}")

        # Check probation status
        con_sem = probation_semesters_count(user_id)
        probation_status = check_probation_status(user_id, con_sem)
        if probation_status:
            logger.info(f"Student {student_id} is on probation. Fetching retake courses.")
            # Integrated logic for fetching retake courses with prerequisite as course_name
            query = """
                SELECT DISTINCT 
                    c.course_name, 
                    c.course_code, 
                    c.credit_hours, 
                    c.course_type, 
                    c.course_ID, 
                    ec.grade,
                    COALESCE(prerequisite_courses.course_name, NULL) AS prerequisite_course_name,
                    COALESCE(repetition_counts.repetition_count, 0) AS repetition_count
                FROM (
                    SELECT 
                        ec.student_id, 
                        ec.course_id, 
                        MAX(ec.semester_ID) AS latest_semester_ID
                    FROM sis_enrolled_courses ec
                    WHERE ec.student_id = %s
                    GROUP BY ec.student_id, ec.course_id
                ) AS latest_courses
                JOIN sis_enrolled_courses ec 
                    ON latest_courses.student_id = ec.student_id 
                    AND latest_courses.course_id = ec.course_id 
                    AND latest_courses.latest_semester_ID = ec.semester_ID
                JOIN course c 
                    ON ec.course_id = c.course_id
                LEFT JOIN course prerequisite_courses 
                    ON c.prerequisite = prerequisite_courses.course_ID
                LEFT JOIN (
                    SELECT 
                        student_id, 
                        course_id,
                        COUNT(*) - 1 AS repetition_count
                    FROM sis_enrolled_courses
                    WHERE student_id = %s
                    GROUP BY student_id, course_id
                    HAVING COUNT(*) > 1
                ) AS repetition_counts 
                    ON ec.student_id = repetition_counts.student_id 
                    AND ec.course_id = repetition_counts.course_id
                WHERE ec.grade IN ('D', 'F')
                ORDER BY FIELD(ec.grade, 'F', 'D'), c.course_code
            """
            result = execute_query(query, (student_id, student_id))
            
            # Apply credit hour cap logic
            retake_courses = []
            total_credit_hours = 0
            max_credit_hours = 14  # Default probation credit hour limit

            for course in result:
                if total_credit_hours + course['credit_hours'] <= max_credit_hours:
                    retake_courses.append(course)
                    total_credit_hours += course['credit_hours']
                if total_credit_hours >= max_credit_hours:
                    break

            return retake_courses

        # Fetch program ID and total program hours
        program_query = """
            SELECT program_ID, total_hours 
            FROM student 
            JOIN program USING(program_ID) 
            WHERE student_ID = %s
        """
        program_info = execute_query(program_query, (student_id,))
        if not program_info:
            raise ValueError(f"No program found for student ID {student_id}.")
        program_id = program_info[0]['program_ID']
        total_program_hours = program_info[0]['total_hours']
        logger.debug(f"Program ID: {program_id}, Total Hours: {total_program_hours}")

        # Fetch student's most recent GPA
        gpa_query = """
            SELECT cumulative_gpa 
            FROM semester_gpa 
            WHERE student_ID = %s 
            ORDER BY semester_ID DESC 
            LIMIT 1
        """
        gpa_result = execute_query(gpa_query, (student_id,))
        if not gpa_result:
            raise ValueError(f"Unable to fetch GPA for student ID {student_id}.")
        gpa = gpa_result[0]['cumulative_gpa']
        logger.debug(f"Student GPA: {gpa}")

        completed_courses_query = """
            SELECT c.course_code, c.credit_hours, sec.grade
            FROM sis_enrolled_courses sec
            JOIN course c ON sec.course_ID = c.course_ID
            WHERE sec.student_ID = %s
        """
        enrolled_courses = execute_query(completed_courses_query, (student_id,))
        
        # Filter completed courses based on grades
        valid_grades = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'P', 'T']
        completed_course_codes = set()
        for course in enrolled_courses:
            if course['grade'] in valid_grades:
                completed_course_codes.add(course['course_code'])
        logger.debug(f"Completed Courses: {list(completed_course_codes)}")

        # Determine credit hour limits based on GPA
        credit_hours_limit = {
            'low_gpa': int(fetch_configuration('low_gpa_credit_hours') or 14),
            'medium_gpa': int(fetch_configuration('medium_gpa_credit_hours') or 18),
            'high_gpa': int(fetch_configuration('high_gpa_credit_hours') or 21),
        }
        max_credit_hours = (
            credit_hours_limit['low_gpa'] if gpa < 2 else
            credit_hours_limit['medium_gpa'] if gpa < 3 else
            credit_hours_limit['high_gpa']
        )
        logger.debug(f"Max Credit Hours Allowed: {max_credit_hours}")

        # Fetch study plan courses
        study_plan_query = """
            SELECT DISTINCT 
                c.course_ID, 
                c.course_code, 
                c.course_name, 
                c.credit_hours, 
                c.course_type, 
                spd.semester, 
                COALESCE(prerequisite_courses.course_name, NULL) AS prerequisite_course_name
            FROM study_plan_details spd
            JOIN study_plan sp ON spd.SP_ID = sp.SP_ID
            JOIN course c ON spd.course_ID = c.course_ID
            LEFT JOIN course prerequisite_courses 
                ON c.prerequisite = prerequisite_courses.course_ID
            WHERE sp.program_ID = %s
        """
        study_plan_courses = execute_query(study_plan_query, (program_id,))
        logger.debug(f"Study Plan Courses: {len(study_plan_courses)} courses retrieved")

        # Filter out completed courses and electives
        available_courses = [
            course for course in study_plan_courses
            if course['course_code'] not in completed_course_codes and "Elective" not in course['course_type']
        ]
        logger.debug(f"Available Courses after filtering: {len(available_courses)}")

        # Ensure prerequisites are satisfied
        def prerequisites_satisfied(prerequisite, completed):
            return prerequisite is None or prerequisite == 0 or prerequisite in completed

        available_courses = [
            course for course in available_courses
            if prerequisites_satisfied(course['prerequisite_course_name'], completed_course_codes)
        ]
        logger.debug(f"Courses after checking prerequisites: {len(available_courses)}")

        # Sort courses by semester and limit by credit hours
        recommended_courses = []
        total_credit_hours = 0
        seen_course_codes = set()

        for course in sorted(available_courses, key=lambda x: x['semester']):
            if course['course_code'] in seen_course_codes:
                continue  # Skip duplicate courses
            if total_credit_hours + course['credit_hours'] > max_credit_hours:
                break
            recommended_courses.append(course)
            seen_course_codes.add(course['course_code'])
            total_credit_hours += course['credit_hours']

        logger.debug(f"Recommended Courses: {recommended_courses}")
        return recommended_courses

    except Exception as e:
        logger.error(f"Error in recommend_courses for user_id={user_id}: {str(e)}")
        raise



def get_student_id_from_user(user_id):
    """
    Fetch the student_ID for a given user_ID.
    """
    query = "SELECT student_ID FROM student WHERE user_ID = %s"
    result = execute_query(query, (user_id,))
    if not result:
        raise ValueError(f"No student found for user ID {user_id}.")
    return result[0]['student_ID']


def populate_recommended_courses(user_id, recommended_courses):
    """
    Populate the recommended_courses table with initial data for a user (mapped to their student ID).
    """
    student_id = get_student_id_from_user(user_id)  # Get student_ID from user_ID
    for course in recommended_courses:
        course_id = course['course_ID']  # Use the course_ID directly
        logger.debug(f"Processing course: {course} for student_id: {student_id}")

        # Check if the course already exists for the student
        query_check = """
            SELECT id FROM recommended_courses
            WHERE course_ID = %s AND student_ID = %s
        """
        exists = execute_query(query_check, (course_id, student_id))
        logger.debug(f"Exists check for course_ID {course_id}: {exists}")

        if not exists:
            # Insert course into the recommended_courses table
            query_insert = """
                INSERT INTO recommended_courses (course_ID, student_ID)
                VALUES (%s, %s)
            """
            execute_update(query_insert, (course_id, student_id))
            logger.debug(f"Successfully inserted course_ID {course_id} for student_id {student_id}")



def fetch_updated_recommended_courses(user_id):
    student_id = get_student_id_from_user(user_id)

    fetching_query = """
    SELECT DISTINCT 
        u.id, 
        c.course_code, 
        c.course_name, 
        u.course_ID, 
        c.credit_hours, 
        c.prerequisite, 
        COALESCE(prerequisite_courses.course_name, NULL) AS prerequisite_course_name,
        spd.course_type, 
        spd.semester,
        COALESCE(repetition_counts.repetition_count, 0) AS repetition_count,
        COALESCE(latest_grades.grade, NULL) AS latest_grade
    FROM recommended_courses u
    JOIN course c ON u.course_ID = c.course_ID
    JOIN study_plan_details spd ON u.course_ID = spd.course_ID
    JOIN study_plan sp ON spd.SP_ID = sp.SP_ID
    JOIN student s ON u.student_ID = s.student_ID
    LEFT JOIN course prerequisite_courses 
        ON c.prerequisite = prerequisite_courses.course_ID
    LEFT JOIN (
        SELECT 
            student_ID, 
            course_ID, 
            COUNT(*) - 1 AS repetition_count
        FROM sis_enrolled_courses
        WHERE student_ID = %s
        GROUP BY student_ID, course_ID
        HAVING COUNT(*) > 1
    ) AS repetition_counts 
        ON u.student_ID = repetition_counts.student_ID 
        AND u.course_ID = repetition_counts.course_ID
    LEFT JOIN (
        SELECT 
            sec.student_ID, 
            sec.course_ID, 
            sec.grade
        FROM sis_enrolled_courses sec
        JOIN (
            SELECT 
                student_ID, 
                course_ID, 
                MAX(semester_ID) AS latest_semester_ID
            FROM sis_enrolled_courses
            WHERE student_ID = %s
            GROUP BY student_ID, course_ID
        ) latest_semesters 
        ON sec.student_ID = latest_semesters.student_ID 
        AND sec.course_ID = latest_semesters.course_ID 
        AND sec.semester_ID = latest_semesters.latest_semester_ID
    ) AS latest_grades
        ON u.student_ID = latest_grades.student_ID 
        AND u.course_ID = latest_grades.course_ID
    WHERE u.student_ID = %s
    AND sp.program_ID = s.program_ID
    """

    try:
        result = execute_query(fetching_query, (student_id, student_id, student_id))
        if result:
            # Use a dictionary to filter out duplicates by course_code
            courses_dict = {}
            for row in result:
                if row['course_code'] not in courses_dict:
                    courses_dict[row['course_code']] = {
                        'id': row['id'],
                        'course_name': row['course_name'],
                        'course_code': row['course_code'],
                        'credit_hours': row['credit_hours'],
                        'course_type': row['course_type'],
                        'prerequisite': row['prerequisite_course_name'],  # Use resolved prerequisite course name
                        'semester': row['semester'],
                        'repetition_count': row['repetition_count'],  # Include repetition count
                        'latest_grade': row['latest_grade'],  # Include latest grade
                    }
            
            # Extract the values from the dictionary
            updated_recommended_courses = list(courses_dict.values())
            logger.debug(f"Updated Recommended courses: {updated_recommended_courses}")
            return updated_recommended_courses
        else:
            logger.warning(f"No recommended courses found for student_id {student_id}")
            return []
    except Exception as e:
        logger.error(f"Error fetching recommended courses for student_id {student_id}: {e}")
        return []


def add_recommended_course(course_id: int, user_id: int) -> None:
    """
    Add a course to the recommended_courses table for a student.
    
    Args:
        course_id (int): The ID of the course to be recommended.
        user_id (int): The ID of the user (advisor-selected student).
    """
    student_id = get_student_id_from_user(user_id)  # Ensure this fetches the correct student ID
    if not student_id:
        logger.error(f"Invalid user_id {user_id}. Student ID not found.")
        raise ValueError("Invalid user_id. Student ID not found.")

    logger.debug(f"Attempting to add recommended course: course_id={course_id}, student_id={student_id}")
    query = """
        INSERT INTO recommended_courses (course_ID, student_ID)
        VALUES (%s, %s)
    """
    try:
        execute_update(query, (course_id, student_id))
        logger.debug("Course successfully added to recommended_courses table.")
    except Exception as e:
        logger.error(f"Error adding recommended course: {e}")
        raise



def add_course_to_recommendations(user_id: int, course_id: int) -> dict:
    """
    Fetch study plan courses, validate the course ID, include the latest grade, and add the course to recommendations.

    Args:
        user_id (int): The ID of the user (advisor-selected student).
        course_id (int): The ID of the course to recommend.

    Returns:
        dict: A dictionary containing success status and a message.
    """
    try:
        # Fetch student ID from user ID
        student_id_query = "SELECT student_ID FROM student WHERE user_ID = %s"
        student_id_result = execute_query(student_id_query, (user_id,))
        if not student_id_result:
            logger.error(f"No student found for user ID {user_id}.")
            raise ValueError(f"No student found for user ID {user_id}.")
        student_id = student_id_result[0]['student_ID']

        # Fetch study plan courses
        study_plan_query = """
            SELECT DISTINCT c.course_ID, c.course_code, c.course_name, c.credit_hours, c.course_type
            FROM study_plan_details spd
            JOIN study_plan sp ON spd.SP_ID = sp.SP_ID
            JOIN course c ON spd.course_ID = c.course_ID
            WHERE sp.program_ID = (SELECT program_ID FROM student WHERE student_ID = %s)
        """
        study_plan_courses = execute_query(study_plan_query, (student_id,))
        logger.debug(f"Fetched study plan courses for student {student_id}: {study_plan_courses}")

        # Fetch the student's transcript and order by semester_ID ASC
        transcript_query = """
            SELECT c.course_ID, sec.grade, sec.semester_ID
            FROM sis_enrolled_courses sec
            JOIN course c ON sec.course_ID = c.course_ID
            WHERE sec.student_ID = %s
            ORDER BY sec.semester_ID ASC
        """
        transcript = execute_query(transcript_query, (student_id,))
        logger.debug(f"Fetched transcript for student {student_id}: {transcript}")

        # Keep the latest grade for each course
        latest_grades = {}
        for entry in transcript:
            latest_grades[entry['course_ID']] = entry['grade']  # Replace with the latest grade

        # Merge study plan courses with the latest grades
        for course in study_plan_courses:
            course['latest_grade'] = latest_grades.get(course['course_ID'], 'New Course')

        # Check if the course ID is in the study plan
        valid_course = any(course['course_ID'] == course_id for course in study_plan_courses)
        if not valid_course:
            logger.warning(f"Course {course_id} is not in the study plan for student {student_id}.")
            return {"success": False, "message": "Selected course is not in the study plan."}

        # Add the course to recommended courses
        insert_query = """
            INSERT INTO recommended_courses (course_ID, student_ID)
            VALUES (%s, %s)
        """
        execute_update(insert_query, (course_id, student_id))
        logger.debug(f"Added course {course_id} to recommendations for student {student_id}.")

        # Return the latest grade with the success message
        latest_grade = latest_grades.get(course_id, 'New Course')
        return {
            "success": True,
            "message": f"Course added successfully to recommendations. Latest grade: {latest_grade}",
            "latest_grade": latest_grade,
        }

    except Exception as e:
        logger.error(f"Error adding course {course_id} for user {user_id}: {str(e)}", exc_info=True)
        return {"success": False, "message": "An error occurred while adding the course. Please try again."}



def delete_recommended_course(id: int) -> None:
    query = "DELETE FROM recommended_courses WHERE id = %s"
    execute_update(query, (id,))


def get_manual_course_selection(student_id):
    """
    Retrieves a list of courses for manual selection by the advisor, excluding courses already completed by the student.

    Args:
        student_id (int): The ID of the student.

    Returns:
        pd.DataFrame: DataFrame containing the list of courses available for manual selection.
    """
    transcript = fetch_student_transcript(student_id)

    completed_courses = transcript[transcript['status'] == 'Success']['course_code'].tolist()

    manual_courses_query = """
        SELECT DISTINCT c.course_code, c.course_name, c.credit_hours, c.course_type
        FROM course c
        JOIN study_plan_details spd ON c.course_ID = spd.course_ID
        JOIN study_plan sp ON spd.SP_ID = sp.SP_ID
        JOIN student s ON sp.program_ID = s.program_ID
        WHERE s.student_ID = %s AND c.course_type NOT IN ('Core', 'University Requirement')
    """
    manual_courses_result = execute_query(manual_courses_query, (student_id,))
    if not manual_courses_result:
        return pd.DataFrame()

    manual_courses_df = pd.DataFrame(manual_courses_result, columns=[
        'course_code', 'course_name', 'credit_hours', 'course_type'
    ])
    available_manual_courses = manual_courses_df[~manual_courses_df['course_code'].isin(completed_courses)]
    available_manual_courses = available_manual_courses.drop_duplicates(subset=['course_code']).sort_values(by='course_name')

    return available_manual_courses


def fetch_unfinished_courses(user_id):
    """
    Fetch courses from the study plan that the student has not completed yet.
    Returns a list of dictionaries representing unfinished courses.
    """
    # Fetch student ID from user ID
    student_id_query = "SELECT student_ID FROM student WHERE user_ID = %s"
    student_id_result = execute_query(student_id_query, (user_id,))
    if not student_id_result:
        raise ValueError(f"No student found for user ID {user_id}.")
    student_id = student_id_result[0]['student_ID']

    # Fetch study plan courses for the student's program
    study_plan_query = """
        SELECT DISTINCT c.course_code, c.course_name, c.credit_hours, c.course_type
        FROM study_plan_details spd
        JOIN study_plan sp ON spd.SP_ID = sp.SP_ID
        JOIN course c ON spd.course_ID = c.course_ID
        JOIN student s ON sp.program_ID = s.program_ID
        WHERE s.student_ID = %s
    """
    study_plan_courses = execute_query(study_plan_query, (student_id,))

    # Fetch the student's transcript
    transcript_query = """
        SELECT c.course_code, sec.grade, sec.points
        FROM sis_enrolled_courses sec
        JOIN course c ON sec.course_ID = c.course_ID
        WHERE sec.student_ID = %s
    """
    student_transcript = execute_query(transcript_query, (student_id,))

    # Handle missing transcript data
    if not student_transcript:
        return []

    # Remove duplicates, keeping the highest points for retaken courses
    student_transcript.sort(key=lambda x: float(x['points']) if x['points'] else 0, reverse=True)
    unique_transcript = {course['course_code']: course for course in student_transcript}.values()

    # Identify completed courses
    valid_grades = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'P', 'T']
    completed_courses = [course['course_code'] for course in unique_transcript if course['grade'] in valid_grades]

    # Find unfinished courses
    unfinished_courses = [
        course for course in study_plan_courses if course['course_code'] not in completed_courses
    ]

    # Add grades to unfinished courses for better context
    course_grades = {course['course_code']: course['grade'] for course in unique_transcript}
    for course in unfinished_courses:
        course['grade'] = course_grades.get(course['course_code'], "New Course")

    # Rename keys for consistency
    for course in unfinished_courses:
        course['Course Name'] = course.pop('course_name')
        course['Course Code'] = course.pop('course_code')
        course['Credit Hours'] = course.pop('credit_hours')
        course['Course Type'] = course.pop('course_type')
        course['Grade'] = course.pop('grade')

    return unfinished_courses



def fetch_elective_courses(user_id, elective_type):
    """
    Fetch elective courses of a specific type that the student has not completed yet.
    Returns a list of dictionaries representing elective courses.
    """
    # Fetch student ID from user ID
    student_id_query = "SELECT student_ID FROM student WHERE user_ID = %s"
    student_id_result = execute_query(student_id_query, (user_id,))
    if not student_id_result:
        raise ValueError(f"No student found for user ID {user_id}.")
    student_id = student_id_result[0]['student_ID']

    # Fetch the program ID for the student
    program_query = "SELECT program_ID FROM student WHERE student_ID = %s"
    program_result = execute_query(program_query, (student_id,))
    if not program_result:
        raise ValueError(f"No program found for student ID {student_id}.")
    program_id = program_result[0]['program_ID']

    # Fetch completed courses
    transcript_query = """
        SELECT c.course_code, sec.grade
        FROM sis_enrolled_courses sec
        JOIN course c ON sec.course_ID = c.course_ID
        WHERE sec.student_ID = %s
    """
    student_transcript = execute_query(transcript_query, (student_id,))

    # Identify completed courses
    valid_grades = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'P', 'T']
    completed_courses = [course['course_code'] for course in student_transcript if course['grade'] in valid_grades]

    # Fetch elective courses of the specified type
    elective_query = """
        SELECT DISTINCT c.course_code, c.course_name, c.credit_hours, c.course_type
        FROM study_plan_details spd
        JOIN study_plan sp ON spd.SP_ID = sp.SP_ID
        JOIN course c ON spd.course_ID = c.course_ID
        WHERE sp.program_ID = %s AND c.course_type = %s
    """
    elective_courses = execute_query(elective_query, (program_id, elective_type))

    # Filter out completed courses
    elective_courses = [
        course for course in elective_courses if course['course_code'] not in completed_courses
    ]

    # Rename keys for consistency
    for course in elective_courses:
        course['Course Name'] = course.pop('course_name')
        course['Course Code'] = course.pop('course_code')
        course['Credit Hours'] = course.pop('credit_hours')
        course['Course Type'] = course.pop('course_type')

    return elective_courses



def fetch_courses_to_retake(student_id, max_credit_hours):
    query = """
        SELECT 
            c.course_name, 
            c.course_code, 
            c.credit_hours, 
            c.course_type, 
            c.course_ID, 
            ec.grade,
            COALESCE(prerequisite_courses.course_code, NULL) AS prerequisite_course,
            COALESCE(repetition_counts.repetition_count, 0) AS repetition_count
        FROM (
            SELECT 
                ec.student_id, 
                ec.course_id, 
                MAX(ec.semester_ID) AS latest_semester_ID
            FROM sis_enrolled_courses ec
            WHERE ec.student_id = %s
            GROUP BY ec.student_id, ec.course_id
        ) AS latest_courses
        JOIN sis_enrolled_courses ec 
            ON latest_courses.student_id = ec.student_id 
            AND latest_courses.course_id = ec.course_id 
            AND latest_courses.latest_semester_ID = ec.semester_ID
        JOIN course c 
            ON ec.course_id = c.course_id
        LEFT JOIN course prerequisite_courses 
            ON c.prerequisite = prerequisite_courses.course_ID
        LEFT JOIN (
            SELECT 
                student_id, 
                course_id,
                COUNT(*) - 1 AS repetition_count
            FROM sis_enrolled_courses
            WHERE student_id = %s
            GROUP BY student_id, course_id
            HAVING COUNT(*) > 1
        ) AS repetition_counts 
            ON ec.student_id = repetition_counts.student_id 
            AND ec.course_id = repetition_counts.course_id
        WHERE ec.grade IN ('D', 'F')
        ORDER BY FIELD(ec.grade, 'F', 'D'), c.course_code
    """
    result = execute_query(query, (student_id, student_id))
    
    retake_courses = []
    total_credit_hours = 0

    for course in result:
        if total_credit_hours + course['credit_hours'] <= max_credit_hours:
            retake_courses.append(course)
            total_credit_hours += course['credit_hours']
        if total_credit_hours >= max_credit_hours:
            break

    return retake_courses



def fetch_recommended_courses(user_id):
    logger.debug(f"Fetching recommended courses for user_id: {user_id}")
    
    # Step 1: Fetch the student_ID corresponding to the user_id
    student_id_query = "SELECT student_ID FROM student WHERE user_ID = %s"
    try:
        student_id_result = execute_query(student_id_query, (user_id,))
        if not student_id_result:
            logger.warning(f"No student found for user_id {user_id}")
            return []

        student_id = student_id_result[0]['student_ID']
        logger.debug(f"Found student_ID {student_id} for user_id {user_id}")
    except Exception as e:
        logger.error(f"Error fetching student_ID for user_id {user_id}: {e}")
        return []

    # Step 2: Fetch the recommended courses for the current active semester
    query = """
        SELECT c.course_name, c.course_code, c.credit_hours
        FROM advising_reports ar
        JOIN course c ON ar.course_ID = c.course_ID
        JOIN sis_semester s ON ar.semester_ID = s.semester_ID
        WHERE ar.student_ID = %s
        AND s.active = 1
    """
    try:
        result = execute_query(query, (student_id,))
        if result:
            # Format the result into a list of dictionaries
            recommended_courses = [
                {
                    'course_name': row['course_name'],
                    'course_code': row['course_code'],
                    'credit_hours': row['credit_hours']
                }
                for row in result
            ]
            logger.debug(f"Recommended courses: {recommended_courses}")
            return recommended_courses
        else:
            logger.warning(f"No recommended courses found for student_id {student_id}")
            return []
    except Exception as e:
        logger.error(f"Error fetching recommended courses for student_id {student_id}: {e}")
        return []


def fetch_study_plan_courses(student_id):
    program_query = """
        SELECT program_ID
        FROM student
        WHERE student_ID = %s
    """
    program_id_result = execute_query(program_query, (student_id,))
    if not program_id_result:
        raise ValueError("Student's program ID not found.")
    
    program_id = program_id_result[0]['program_ID']

    query = """
        SELECT DISTINCT c.course_name, c.course_code, c.credit_hours, c.course_type, c.course_ID
        FROM study_plan_details spd
        JOIN course c ON spd.course_id = c.course_id
        JOIN study_plan sp ON spd.SP_ID = sp.SP_ID
        JOIN program p ON sp.program_ID = p.program_ID
        WHERE p.program_ID = %s
    """
    result = execute_query(query, (program_id,))
    return pd.DataFrame(result, columns=['course_name', 'course_code', 'credit_hours', 'course_type', 'course_ID'])


def add_study_plan_courses(user_id):
    """
    Add study plan courses and merge with the student's transcript.
    Returns a list of dictionaries representing the merged data, including the latest grade and repetition count.
    """
    # Fetch student ID from user ID
    student_id_query = "SELECT student_ID FROM student WHERE user_ID = %s"
    student_id_result = execute_query(student_id_query, (user_id,))
    if not student_id_result:
        raise ValueError(f"No student found for user ID {user_id}.")
    student_id = student_id_result[0]['student_ID']

    # Fetch study plan courses
    study_plan_query = """
        SELECT DISTINCT c.course_ID, c.course_code, c.course_name, c.credit_hours, c.course_type
        FROM study_plan_details spd
        JOIN study_plan sp ON spd.SP_ID = sp.SP_ID
        JOIN course c ON spd.course_ID = c.course_ID
        WHERE sp.program_ID = (SELECT program_ID FROM student WHERE student_ID = %s)
    """
    study_plan_courses = execute_query(study_plan_query, (student_id,))

    # Fetch the student's transcript with the latest grade and repetition count
    transcript_query = """
        SELECT 
            c.course_code, 
            MAX(sec.grade) AS latest_grade, 
            COUNT(*) AS repetition_count, 
            MAX(sec.points) AS points
        FROM sis_enrolled_courses sec
        JOIN course c ON sec.course_ID = c.course_ID
        WHERE sec.student_ID = %s
        GROUP BY c.course_code
    """
    transcript = execute_query(transcript_query, (student_id,))

    # Ensure 'points' exists and is numeric
    for course in transcript:
        course['points'] = float(course['points']) if 'points' in course and course['points'] else 0

    # Convert transcript to a dictionary for quick lookups
    transcript_dict = {course['course_code']: course for course in transcript}

    # Merge study plan courses with the transcript
    merged_courses = []
    for course in study_plan_courses:
        merged_course = course.copy()
        transcript_data = transcript_dict.get(course['course_code'], {})
        merged_course['latest_grade'] = transcript_data.get('latest_grade', 'New Course')
        merged_course['repetition_count'] = transcript_data.get('repetition_count', 0)
        merged_course['points'] = transcript_data.get('points', 0)
        merged_courses.append(merged_course)

    # Rename keys for consistency
    for course in merged_courses:
        course['Course Name'] = course.pop('course_name')
        course['Course Code'] = course.pop('course_code')
        course['Credit Hours'] = course.pop('credit_hours')
        course['Course Type'] = course.pop('course_type')
        course['Latest Grade'] = course.pop('latest_grade')
        course['Repetition Count'] = course.pop('repetition_count')
        course['Points'] = course.pop('points')

    return merged_courses





def calculate_gpa_deficit(user_id: int, min_gpa: float = 2.0) -> Optional[int]:
    """
    Calculate the GPA deficit for a student based on their user ID.

    Args:
        user_id (int): The user ID of the student.
        min_gpa (float): The minimum required GPA to calculate the deficit (default is 2.0).

    Returns:
        Optional[int]: The GPA deficit rounded up to the nearest whole number, or None if not applicable.
    """
    try:
        # Fetch the student_ID from the user_ID
        student_id = fetch_student_id_by_user_id(user_id)
        if not student_id:
            logger.warning(f"No student ID found for user_id {user_id}. Cannot calculate GPA deficit.")
            return None

        logger.debug(f"Calculating GPA deficit for student_id {student_id} with min_gpa {min_gpa}")

        min_gpa = Decimal(min_gpa)

        query = """
            SELECT gt.cumulative_gpa, SUM(c.credit_hours) AS total_credit_hours
            FROM semester_gpa gt
            JOIN (
                SELECT sec.student_id, sec.course_id, MAX(sec.grade) AS max_grade
                FROM sis_enrolled_courses sec
                WHERE sec.student_id = %s
                AND sec.included = 'Y'
                GROUP BY sec.course_id, sec.student_id
            ) max_grades ON gt.student_ID = max_grades.student_id
            JOIN course c ON max_grades.course_id = c.course_id
            WHERE gt.student_ID = %s
            GROUP BY gt.cumulative_gpa
            ORDER BY gt.semester_ID DESC
            LIMIT 1
        """
        result = execute_query(query, (student_id, student_id))
        
        if not result:
            logger.warning(f"No GPA data found for student_id {student_id}")
            return None

        cumulative_gpa = Decimal(result[0]['cumulative_gpa'])
        total_credit_hours = Decimal(result[0]['total_credit_hours'])

        if total_credit_hours == 0:
            logger.warning(f"Total credit hours is 0 for student_id {student_id}.")
            return None

        required_grade_points = total_credit_hours * min_gpa
        current_grade_points = cumulative_gpa * total_credit_hours
        deficit = required_grade_points - current_grade_points

        logger.debug(f"Student {student_id}: cumulative_gpa={cumulative_gpa}, "
                     f"total_credit_hours={total_credit_hours}, deficit={deficit}")

        # Round up the deficit to the nearest whole number
        rounded_deficit = math.ceil(max(Decimal('0'), deficit))

        return int(rounded_deficit)
    except Exception as e:
        logger.error(f"Error calculating GPA deficit for user_id {user_id}: {e}", exc_info=True)
        return None
    


def fetch_calculator_data(user_id: int) -> Dict[str, List[Dict]]:
    """
    Fetch study plan courses and transcript for a student.

    Args:
        user_id (int): The user's ID.

    Returns:
        dict: A dictionary containing the study plan courses and the latest transcript data.
    """
    try:
        # Validate and retrieve student_id
        student_id = get_student_id_from_user(user_id)
        if not student_id:
            raise ValueError(f"No student ID found for user ID {user_id}.")

        # Fetch study plan courses
        study_plan_query = """
            SELECT DISTINCT c.course_ID, c.course_code, c.course_name, c.credit_hours, c.course_type
            FROM study_plan_details spd
            JOIN study_plan sp ON spd.SP_ID = sp.SP_ID
            JOIN course c ON spd.course_ID = c.course_ID
            JOIN student s ON s.program_ID = sp.program_ID
            WHERE s.student_ID = %s
        """
        study_plan_courses = execute_query(study_plan_query, (student_id,))

        # Fetch transcript data
        transcript_query = """
            SELECT c.course_code, sec.grade, sec.points, c.credit_hours, sec.semester_ID
            FROM sis_enrolled_courses sec
            JOIN course c ON sec.course_ID = c.course_ID
            WHERE sec.student_ID = %s
            ORDER BY sec.semester_ID ASC
        """
        raw_transcript = execute_query(transcript_query, (student_id,))

        # Process the latest transcript entries
        latest_transcript = {}
        for entry in raw_transcript:
            latest_transcript[entry["course_code"]] = entry

        return {
            "study_plan_courses": study_plan_courses,
            "transcript": list(latest_transcript.values())  # Convert dict to list
        }

    except Exception as e:
        logger.error(f"Error fetching student data for user_id {user_id}: {e}", exc_info=True)
        return {"study_plan_courses": [], "transcript": []}




from decimal import Decimal
from typing import List, Dict, Any, Optional

def calculate_updated_gpa(
    user_id: int,
    courses: List[Dict[str, Any]],
    min_gpa: float = 2.0
) -> Dict[str, Optional[Decimal]]:
    """
    Calculate the updated GPA and GPA deficit based on the advisor's input.

    Args:
        user_id (int): The user's ID.
        courses (List[Dict[str, Any]]): List of courses with their grades and credit hours.
            Each course dict should contain:
            - course_code: str
            - new_grade: str
            - course_type: str ('transcript' or 'study_plan')
            - credit_hours: str or float
            - current_grade: str (only for transcript courses)
        min_gpa (float): The minimum required GPA for deficit calculation (default is 2.0).

    Returns:
        dict: A dictionary containing updated GPA and GPA deficit.
    """
    try:
        # Fetch student_id from user_id
        student_id = get_student_id_from_user(user_id)
        if not student_id:
            raise ValueError(f"No student ID found for user ID {user_id}.")

        # Fetch cumulative GPA and credit hours
        query = """
            SELECT gt.cumulative_gpa, SUM(c.credit_hours) AS total_credit_hours
            FROM semester_gpa gt
            JOIN (
                SELECT sec.student_id, sec.course_id, MAX(sec.grade) AS max_grade
                FROM sis_enrolled_courses sec
                WHERE sec.student_id = %s
                AND sec.included = 'Y'
                GROUP BY sec.course_id, sec.student_id
            ) max_grades ON gt.student_ID = max_grades.student_id
            JOIN course c ON max_grades.course_id = c.course_id
            WHERE gt.student_ID = %s
            GROUP BY gt.cumulative_gpa
            ORDER BY gt.semester_ID DESC
            LIMIT 1
        """
        result = execute_query(query, (student_id, student_id))
        if not result:
            logger.warning(f"No GPA data found for student_id {student_id}.")
            return {"updated_gpa": None, "gpa_deficit": None}

        # Extract current cumulative GPA and total credit hours
        cumulative_gpa = Decimal(result[0]['cumulative_gpa'])
        total_credit_hours = Decimal(result[0]['total_credit_hours'])

        # Grade points mapping
        grade_points_map = {
            "A+": Decimal('4.0'), "A": Decimal('4.0'), "A-": Decimal('3.7'),
            "B+": Decimal('3.3'), "B": Decimal('3.0'), "B-": Decimal('2.7'),
            "C+": Decimal('2.3'), "C": Decimal('2.0'), "C-": Decimal('1.7'),
            "D+": Decimal('1.3'), "D": Decimal('1.0'), "F": Decimal('0.0')
        }

        # Calculate current grade points
        current_grade_points = cumulative_gpa * total_credit_hours
        new_total_credit_hours = total_credit_hours

        # Process each course
        for course in courses:
            course_code = course['course_code']
            new_grade = course['new_grade']
            course_type = course['course_type']
            credit_hours = Decimal(str(course['credit_hours']))

            # Validate grade
            if new_grade not in grade_points_map:
                raise ValueError(f"Invalid grade {new_grade} provided for course {course_code}.")

            # Process transcript or study plan courses
            if course_type == 'study_plan':
                # Add new course credit hours to total
                new_total_credit_hours += credit_hours
            elif course_type == 'transcript':
                # Fetch the current grade and update grade points
                current_grade = course.get('current_grade')
                if current_grade and current_grade in grade_points_map:
                    current_grade_points -= grade_points_map[current_grade] * credit_hours
            else:
                raise ValueError(f"Invalid course type {course_type} for course {course_code}.")

            # Add new grade points for the updated grade
            current_grade_points += grade_points_map[new_grade] * credit_hours

        # Calculate updated GPA
        updated_gpa = current_grade_points / new_total_credit_hours

        # Calculate GPA deficit
        required_grade_points = new_total_credit_hours * Decimal(str(min_gpa))
        gpa_deficit = required_grade_points - current_grade_points
        gpa_deficit = max(Decimal('0'), gpa_deficit)

        return {
            "updated_gpa": updated_gpa.quantize(Decimal("0.01")),
            "gpa_deficit": gpa_deficit.quantize(Decimal("0.01"))
        }

    except Exception as e:
        logger.error(f"Error calculating updated GPA for user_id {user_id}: {e}", exc_info=True)
        return {"updated_gpa": None, "gpa_deficit": None}






def predict_semesters_to_clear_probation(student_id, max_credit_hours=14, target_gpa=2.0, assumed_grade='B'):
    GRADE_TO_POINTS = {
        'A+': 4.0, 'A': 4.0, 'A-': 3.7,
        'B+': 3.3, 'B': 3.0, 'B-': 2.7,
        'C+': 2.3, 'C': 2.0, 'C-': 1.7,
        'D+': 1.3, 'D': 1.0, 'F': 0.0, 'W': 0.0, 'FA': 0.0
    }
    assumed_points = GRADE_TO_POINTS[assumed_grade]

    current_gpa_query = """
        SELECT sg.cumulative_gpa AS current_gpa, SUM(c.credit_hours) AS total_credit_hours
        FROM semester_gpa sg
        JOIN sis_enrolled_courses sec ON sg.student_ID = sec.student_ID AND sg.semester_ID = sec.semester_ID
        JOIN course c ON sec.course_id = c.course_id
        WHERE sg.student_ID = %s
        GROUP BY sg.cumulative_gpa
    """
    student_gpa_data = execute_query(current_gpa_query, (student_id,))
    if not student_gpa_data:
        raise ValueError("Student GPA data not found.")

    current_gpa = float(student_gpa_data[0]['current_gpa'])
    total_credit_hours = float(student_gpa_data[0]['total_credit_hours'])

    predicted_semesters = 0

    while current_gpa < target_gpa:
        predicted_semesters += 1
        courses_to_retake = fetch_courses_to_retake(student_id, max_credit_hours)

        if not courses_to_retake:
            return float('inf')  # Progress is impossible

        semester_credit_hours = 0
        semester_points_added = 0

        for course in courses_to_retake:
            credit_hours = float(course['credit_hours'])
            points = GRADE_TO_POINTS['B+'] if course['grade'] == 'F' else assumed_points

            semester_credit_hours += credit_hours
            semester_points_added += credit_hours * points

        total_points = (current_gpa * total_credit_hours) + semester_points_added
        total_credit_hours += semester_credit_hours
        current_gpa = total_points / total_credit_hours

        if current_gpa >= target_gpa:
            break

    return predicted_semesters


def fetch_repeated_courses(student_id: str) -> list:
    """
    Fetch courses where the student received a low grade (D or F).

    Args:
        student_id (str): The student ID.

    Returns:
        list: A list of dictionaries containing course information.
    """
    query = """
        SELECT 
            c.course_code,
            c.credit_hours, 
            ec.grade AS current_grade
        FROM sis_enrolled_courses ec
        JOIN course c ON ec.course_id = c.course_id
        WHERE ec.student_id = %s
          AND ec.grade IN ('D', 'F')
    """
    result = execute_query(query, (student_id,))

    if not result:
        return []

    repeated_courses = [
        {
            'course_code': row['course_code'],
            'credit_hours': Decimal(row['credit_hours']),
            'current_grade': row['current_grade']
        }
        for row in result
    ]

    return repeated_courses


def create_personalized_plan(student_id, selected_courses, new_grades, grade_options=None):
    """
    Create a personalized improvement plan for a student.

    Args:
        student_id (str): The student ID.
        selected_courses (list): List of course codes selected for improvement.
        new_grades (dict): A mapping of course codes to expected grades.
        grade_options (list): Available grade options.
    
    Returns:
        dict: A summary of the improvement plan, including new GPA and deficit.
    """
    if grade_options is None:
        grade_options = fetch_configuration('grade_options').split(',') if fetch_configuration('grade_options') else ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'F']

    student_data = fetch_repeated_courses(student_id)

    if not student_data:
        raise ValueError("No courses available for improvement.")

    # Filter selected courses
    filtered_data = [course for course in student_data if course['course_code'] in selected_courses]

    # Simulate grade improvements
    new_gpa, new_deficit = simulate_grade_improvements(student_id, filtered_data, new_grades)

    return {
        'new_gpa': new_gpa,
        'new_deficit': new_deficit,
        'message': "GPA improvement plan calculated successfully."
    }


def simulate_grade_improvements(student_id, courses, new_grades, grade_points=None, min_gpa=None):
    """
    Simulate the impact of grade improvements on GPA.

    Args:
        student_id (str): The student ID.
        courses (list): List of courses to simulate improvements for.
        new_grades (dict): A mapping of course codes to expected grades.
        grade_points (dict): Mapping of grades to points.
        min_gpa (float): Minimum GPA target.

    Returns:
        tuple: New GPA and GPA deficit.
    """
    if grade_points is None:
        grade_points = {
            'A+': 4.0, 'A': 4.0, 'A-': 3.7,
            'B+': 3.3, 'B': 3.0, 'B-': 2.7,
            'C+': 2.3, 'C': 2.0, 'C-': 1.7,
            'D+': 1.3, 'D': 1.0, 'F': 0.0
        }
    if min_gpa is None:
        min_gpa = float(fetch_configuration('min_gpa') or 2.0)

    query = """
        SELECT cumulative_gpa
        FROM semester_gpa
        WHERE student_ID = %s
        ORDER BY semester_ID DESC
        LIMIT 1
    """
    result = execute_query(query, (student_id,))
    if not result:
        return None, None

    current_gpa = float(result[0]['cumulative_gpa'])

    credit_hour_query = """
        SELECT SUM(c.credit_hours) AS total_credit_hours
        FROM (
            SELECT DISTINCT sec.course_id
            FROM sis_enrolled_courses sec
            WHERE sec.student_id = %s
        ) unique_courses
        JOIN course c ON unique_courses.course_id = c.course_id
    """
    credit_hour_result = execute_query(credit_hour_query, (student_id,))
    if not credit_hour_result:
        return None, None

    total_credit_hours = float(credit_hour_result[0]['total_credit_hours'])

    current_grade_points = current_gpa * total_credit_hours
    new_grade_points = current_grade_points
    adjusted_credit_hours = total_credit_hours

    adjusted_courses = set()

    for course_code, new_grade in new_grades.items():
        course = next((c for c in courses if c['course_code'] == course_code), None)
        if not course:
            continue

        credit_hours = course['credit_hours']
        old_grade = course['current_grade']

        if course_code not in adjusted_courses:
            if old_grade in ['D', 'F']:
                new_grade_points -= credit_hours * grade_points[old_grade]
                adjusted_credit_hours -= credit_hours

            new_grade_points += credit_hours * grade_points[new_grade]
            adjusted_credit_hours += credit_hours
            adjusted_courses.add(course_code)

    new_gpa = new_grade_points / adjusted_credit_hours if adjusted_credit_hours > 0 else 0.0
    required_grade_points = adjusted_credit_hours * min_gpa
    new_deficit = max(0, required_grade_points - new_grade_points)

    return new_gpa, new_deficit


def fetch_detailed_student_data(student_id):
    """
    Fetch detailed student data for courses where grades are eligible for improvement.

    Args:
        student_id (str): The student ID.

    Returns:
        pd.DataFrame: A DataFrame containing detailed student data.
    """
    query = """
        SELECT 
            ec.grade AS current_grade, 
            c.course_name, 
            c.course_code, 
            c.credit_hours,
            c.course_type
        FROM sis_enrolled_courses ec
        JOIN course c ON ec.course_id = c.course_id
        WHERE ec.student_id = %s AND ec.grade IN ('D', 'F', 'D+')
    """
    result = execute_query(query, (student_id,))
    return pd.DataFrame(result)


def fetch_probation_semesters(student_id):
    """
    Fetch semesters where a student was on probation.

    Args:
        student_id (str): The student ID.

    Returns:
        list: A list of tuples containing semester_ID and cumulative_gpa.
    """
    query = """
        SELECT semester_ID, cumulative_gpa
        FROM semester_gpa
        WHERE student_id = %s
        ORDER BY semester_ID ASC
    """
    result = execute_query(query, (student_id,))
    return [(row['semester_ID'], row['cumulative_gpa']) for row in result]


def is_consecutive_semester(prev_sem, curr_sem):
    """
    Determine if two semester IDs are consecutive.

    Args:
        prev_sem (int): Previous semester ID (e.g., 2201).
        curr_sem (int): Current semester ID (e.g., 2202).

    Returns:
        bool: True if the semesters are consecutive, False otherwise.
    """
    prev_year, prev_term = divmod(prev_sem, 10)
    curr_year, curr_term = divmod(curr_sem, 10)

    # Check if semesters are consecutive within the same year
    if prev_year == curr_year and curr_term == prev_term + 1:
        return True

    # Check if semesters are consecutive across years
    if curr_year == prev_year + 1 and prev_term == 3 and curr_term == 1:
        return True

    return False


def count_consecutive_semesters(semester_ids):
    """
    Count the longest sequence of consecutive semesters.

    Args:
        semester_ids (list of tuples): List of tuples where the first element is the semester ID.

    Returns:
        int: The count of the longest sequence of consecutive semesters.
    """
    if not semester_ids:
        return 0

    consecutive_count = 1  # Current streak
    max_consecutive = 1    # Longest streak

    for i in range(1, len(semester_ids)):
        prev_sem = semester_ids[i - 1][0]
        curr_sem = semester_ids[i][0]

        if is_consecutive_semester(prev_sem, curr_sem):
            consecutive_count += 1
        else:
            max_consecutive = max(max_consecutive, consecutive_count)
            consecutive_count = 1

    return max(max_consecutive, consecutive_count)


def probation_semesters_count(user_id: str) -> int:
    """
    Count the number of consecutive semesters a student has been on probation.

    Args:
        user_id (str): The user ID.

    Returns:
        int: The count of consecutive semesters on probation.
    """
    try:
        # Step 1: Fetch the student_ID corresponding to the user_ID
        student_id_query = "SELECT student_ID FROM student WHERE user_ID = %s"
        student_id_result = execute_query(student_id_query, (user_id,))
        if not student_id_result:
            logger.warning(f"No student found for user_id {user_id}")
            return 0

        student_id = student_id_result[0]['student_ID']
        logger.debug(f"Found student_ID {student_id} for user_id {user_id}")

        # Step 2: Fetch GPA records for the student
        gpa_query = """
            SELECT semester_ID, cumulative_gpa
            FROM semester_gpa
            WHERE student_ID = %s
            ORDER BY semester_ID ASC
        """
        gpa_result = execute_query(gpa_query, (student_id,))
        if not gpa_result:
            logger.warning(f"No GPA records found for student_id {student_id}")
            return 0

        sem_df = pd.DataFrame(gpa_result, columns=["semester_ID", "cumulative_gpa"])
        logger.debug(f"Semester GPA data for student_id {student_id}: {sem_df}")

        # Step 3: Calculate consecutive probation semesters
        probation_count = 0
        max_consecutive_probation = 0

        for _, row in sem_df.iterrows():
            semester_id = str(row["semester_ID"])
            is_summer = semester_id.endswith("3")
            gpa = float(row["cumulative_gpa"])

            if gpa < 2.0 and not is_summer:
                probation_count += 1
                max_consecutive_probation = max(max_consecutive_probation, probation_count)
            else:
                probation_count = 0  # Reset probation count if GPA >= 2.0 or summer semester

        logger.debug(f"Max consecutive probation semesters for student_id {student_id}: {max_consecutive_probation}")
        return max_consecutive_probation

    except Exception as e:
        logger.error(f"Error calculating probation semesters for user_id {user_id}: {e}")
        return 0



def semesters_chart(student_id):
    """
    Generate a chart of semesters with cumulative GPA.

    Args:
        student_id (str): The student ID.

    Returns:
        pd.DataFrame: A DataFrame containing semester_ID, cumulative_gpa, and semester_name.
    """
    query = """
        SELECT sg.semester_ID, sg.cumulative_gpa, CONCAT(ss.semester, ' ', ss.semester_year) AS semester_name
        FROM semester_gpa sg
        JOIN sis_semester ss ON sg.semester_ID = ss.semester_ID
        WHERE sg.student_ID = %s
    """
    result = execute_query(query, (student_id,))
    return pd.DataFrame(result)


def count_consecutive_probation_semesters(user_id: int) -> int:
    try:
        # Fetch the student_ID from the user_ID
        student_id = fetch_student_id_by_user_id(user_id)
        if not student_id:
            logger.warning(f"No student ID found for user_id {user_id}. Cannot count probation semesters.")
            return 0

        logger.debug(f"Counting consecutive probation semesters for student_id {student_id}")

        # Query to fetch GPA data for all semesters
        query = """
            SELECT semester_ID, cumulative_gpa
            FROM semester_gpa
            WHERE student_ID = %s
            ORDER BY semester_ID ASC
        """
        result = execute_query(query, (student_id,))
        if not result:
            logger.warning(f"No GPA data found for student_id {student_id}")
            return 0

        # Convert result to DataFrame
        df = pd.DataFrame(result, columns=["semester_ID", "cumulative_gpa"])
        logger.debug(f"Semester GPA data for student_id {student_id}: {df}")

        # Separate semesters ending with '3' for special handling
        regular_semesters = df[~df["semester_ID"].astype(str).str.endswith("3")].copy()
        special_semesters = df[df["semester_ID"].astype(str).str.endswith("3")].copy()

        logger.debug(f"Regular Semesters: {regular_semesters}")
        logger.debug(f"Special Semesters (Ending with '3'): {special_semesters}")

        # Initialize counters
        consecutive_count = 0
        max_consecutive_count = 0

        # Process regular semesters first
        for _, row in regular_semesters.iterrows():
            semester_id = str(row["semester_ID"])
            cumulative_gpa = float(row["cumulative_gpa"])

            if cumulative_gpa < 2.0:
                consecutive_count += 1
                max_consecutive_count = max(max_consecutive_count, consecutive_count)
                logger.debug(f"Incremented probation streak. Current streak: {consecutive_count}")
            else:
                consecutive_count = 0
                logger.debug(f"Semester {semester_id}: GPA >= 2.0. Resets streak.")

        # Handle special semesters ending with '3'
        for _, row in special_semesters.iterrows():
            semester_id = str(row["semester_ID"])
            cumulative_gpa = float(row["cumulative_gpa"])

            if cumulative_gpa >= 2.0:
                consecutive_count = 0  # Reset the streak
                logger.debug(f"Semester {semester_id}: GPA >= 2.0. Resets streak.")
            else:
                logger.debug(f"Semester {semester_id}: GPA < 2.0. Ignored.")

        logger.info(f"Max consecutive probation semesters for student_id {student_id}: {max_consecutive_count}")
        return max_consecutive_count

    except Exception as e:
        logger.error(f"Error counting probation semesters for user_id {user_id}: {e}", exc_info=True)
        return 0



getcontext().prec = 6

def calculate_semester_data(student_id: int) -> List[Dict]:
    """
    Calculate semester data including semester GPA and cumulative GPA for a given student.

    Args:
        user_id (int): The ID of the user.

    Returns:
        List[Dict]: A list of dictionaries containing semester data and GPAs.
    """
    try:
        # Query to fetch transcript data
        query = """
            SELECT 
                ec.grade, 
                c.course_name, 
                c.course_code, 
                c.credit_hours, 
                c.course_type, 
                ec.semester_ID, 
                s.semester AS semester_name, 
                s.semester_year, 
                COALESCE(repetition_counts.repetition_count, 0) AS repetition_count,
                CASE 
                    WHEN ec.grade IN ('A+', 'A') THEN 4.0 
                    WHEN ec.grade = 'A-' THEN 3.7
                    WHEN ec.grade = 'B+' THEN 3.3
                    WHEN ec.grade = 'B' THEN 3.0
                    WHEN ec.grade = 'B-' THEN 2.7
                    WHEN ec.grade = 'C+' THEN 2.3
                    WHEN ec.grade = 'C' THEN 2.0
                    WHEN ec.grade = 'C-' THEN 1.7
                    WHEN ec.grade = 'D+' THEN 1.3
                    WHEN ec.grade = 'D' THEN 1.0
                    WHEN ec.grade IN ('F', 'W', 'FA') THEN 0.0
                    ELSE NULL 
                END AS points
            FROM sis_enrolled_courses ec
            JOIN course c ON ec.course_id = c.course_id
            JOIN sis_semester s ON ec.semester_ID = s.semester_ID
            LEFT JOIN (
                SELECT 
                    student_id, 
                    course_id,
                    COUNT(*) - 1 AS repetition_count
                FROM sis_enrolled_courses
                WHERE student_id = %s
                GROUP BY student_id, course_id
                HAVING COUNT(*) > 1
            ) AS repetition_counts 
            ON ec.student_id = repetition_counts.student_id AND ec.course_id = repetition_counts.course_id
            WHERE ec.student_id = %s
            AND NOT EXISTS (
                SELECT 1 
                FROM sis_enrolled_courses ec2
                WHERE ec2.student_id = ec.student_id 
                AND ec2.course_id = ec.course_id 
                AND ec2.semester_ID = ec.semester_ID
                AND ec2.grade > ec.grade
            )
            ORDER BY ec.semester_ID, c.course_code
        """

        # Fetch transcript data using execute_query
        transcript = execute_query(query, (student_id, student_id))
        if not transcript:
            print(f"No transcript data found for student_id {student_id}")
            return []

        # Initialize cumulative totals
        cumulative_points = Decimal(0)
        cumulative_hours = Decimal(0)
        semester_data = []
        grouped_transcript = {}

        # Group transcript data by semester
        for row in transcript:
            semester_key = f"{row['semester_name']} {row['semester_year']}"
            grouped_transcript.setdefault(semester_key, []).append(row)

        # Function to extract year for sorting
        def extract_year(semester_name: str) -> int:
            match = re.search(r'\b\d{4}\b', semester_name)
            return int(match.group(0)) if match else float('inf')

        # Calculate semester and cumulative GPAs
        for semester_key, courses in grouped_transcript.items():
            semester_total_hours = Decimal(sum(course['credit_hours'] for course in courses))
            semester_total_points = Decimal(
                sum(Decimal(course['credit_hours']) * Decimal(course['points']) for course in courses if course['points'] is not None)
            )
            semester_gpa = (semester_total_points / semester_total_hours) if semester_total_hours > 0 else Decimal(0)

            # Update cumulative totals
            cumulative_points += semester_total_points
            cumulative_hours += semester_total_hours
            cumulative_gpa = (cumulative_points / cumulative_hours) if cumulative_hours > 0 else Decimal(0)

            # Append semester data
            semester_data.append({
                'semester_name': semester_key,
                'semester_gpa': round(float(semester_gpa), 2),
                'cumulative_gpa': round(float(cumulative_gpa), 2),
                'total_credit_hours': float(semester_total_hours),
                'total_points': float(semester_total_points),
            })

        # Sort semester data by extracted year
        semester_data = sorted(semester_data, key=lambda x: extract_year(x['semester_name']))

        return semester_data

    except Exception as e:
        print(f"Error calculating semester data: {e}")
        return []



def safe_convert(value):
    """
    Safely convert a value to float if it is a Decimal.

    Args:
        value: The value to convert.

    Returns:
        float or original value.
    """
    if isinstance(value, Decimal):
        return float(value)
    return value


def fetch_current_semester_data(student_id):
    """
    Fetch data for the current semester's courses.

    Args:
        student_id (str): The student ID.

    Returns:
        pd.DataFrame: A DataFrame containing current semester course data.
    """
    query = """
        SELECT 
            c.course_code, 
            c.course_name, 
            c.credit_hours, 
            ec.grade AS current_grade
        FROM sis_enrolled_courses ec
        JOIN course c ON ec.course_id = c.course_id
        WHERE ec.student_id = %s AND ec.semester_ID = (
            SELECT MAX(semester_ID) FROM sis_enrolled_courses WHERE student_id = %s
        )
    """
    result = execute_query(query, (student_id, student_id))
    return pd.DataFrame(result)


def calculate_current_semester_gpa(df, new_grades, grade_points=None):
    """
    Calculate GPA for the current semester.

    Args:
        df (pd.DataFrame): Current semester courses with credit hours.
        new_grades (dict): Mapping of course codes to new grades.
        grade_points (dict): Grade to GPA mapping.

    Returns:
        tuple: (GPA, Total Grade Points, Total Credit Hours)
    """
    if grade_points is None:
        grade_points = {
            'A+': 4.0, 'A': 4.0, 'A-': 3.7,
            'B+': 3.3, 'B': 3.0, 'B-': 2.7,
            'C+': 2.3, 'C': 2.0, 'C-': 1.7,
            'D+': 1.3, 'D': 1.0, 'F': 0.0
        }

    total_credit_hours = 0
    total_grade_points = 0

    for _, row in df.iterrows():
        credit_hours = row['credit_hours']
        grade = new_grades[row['course_code']]
        grade_point = grade_points[grade]
        total_credit_hours += credit_hours
        total_grade_points += credit_hours * grade_point

    gpa = total_grade_points / total_credit_hours if total_credit_hours > 0 else 0.0
    return gpa, total_grade_points, total_credit_hours


def fetch_cumulative_gpa(student_id):
    """
    Fetch the cumulative GPA and total credit hours.

    Args:
        student_id (str): The student ID.

    Returns:
        tuple: (Cumulative GPA, Total Credit Hours)
    """
    query = """
        SELECT 
            s.gpa AS cumulative_gpa,
            SUM(c.credit_hours) AS total_credit_hours
        FROM student s
        JOIN sis_enrolled_courses sec ON s.student_ID = sec.student_id
        JOIN course c ON sec.course_id = c.course_id
        WHERE s.student_ID = %s
    """
    result = execute_query(query, (student_id,))
    if not result:
        return 0.0, 0  # Default values if no data is found
    return float(result[0]['cumulative_gpa']), int(result[0]['total_credit_hours'])


def calculate_cumulative_gpa(
    current_cumulative_gpa, total_credit_hours, current_grade_points, current_credit_hours
):
    """
    Calculate updated cumulative GPA after the current semester.

    Args:
        current_cumulative_gpa (float): Current cumulative GPA.
        total_credit_hours (int): Total credit hours completed so far.
        current_grade_points (float): Grade points earned this semester.
        current_credit_hours (int): Credit hours taken this semester.

    Returns:
        float: Updated cumulative GPA.
    """
    cumulative_grade_points = current_cumulative_gpa * total_credit_hours

    new_total_credit_hours = total_credit_hours + current_credit_hours
    new_total_grade_points = cumulative_grade_points + current_grade_points

    new_cumulative_gpa = new_total_grade_points / new_total_credit_hours
    return new_cumulative_gpa


def create_chat_message(sender_id: int, receiver_id: int, message: str, slot_id: int) -> None:
    """
    Save a chat message to the database.
    """
    query = """
        INSERT INTO chat (sender_id, receiver_id, message, slot_id, timestamp)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
    """
    execute_update(query, (sender_id, receiver_id, message, slot_id))


def send_message(slot_id: int, sender_id: int, receiver_id: int, message: str):
    """
    Send a chat message.
    """
    query = """
        INSERT INTO chat_messages (slot_id, sender_id, receiver_id, message, timestamp)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP);
    """
    execute_update(query, (slot_id, sender_id, receiver_id, message))


def fetch_chat_history(slot_id: int) -> list:
    """
    Fetch chat history for a given slot.
    """
    query = """
        SELECT sender_id, receiver_id, message, timestamp
        FROM chat_messages
        WHERE slot_id = %s
        ORDER BY timestamp ASC;
    """
    return execute_query(query, (slot_id,))


def fetch_reserved_slots(advisor_id: int) -> list:
    """
    Fetch and format reserved slots for a specific advisor.
    Returns a list of dictionaries suitable for passing to templates.
    """
    try:
        logger.debug(f"Fetching reserved slots for advisor_ID: {advisor_id}")

        # SQL query to fetch reserved slots
        query = """
            SELECT 
                s.id AS Slot_ID, 
                s.slot_date AS Date, 
                s.start_time AS Start_Time, 
                s.end_time AS End_Time, 
                s.reserved_by AS Reserved_By
            FROM advisor_slots AS s
            WHERE s.advisor_ID = %s AND s.is_reserved = 1
            ORDER BY s.slot_date, s.start_time;
        """
        result = execute_query(query, (advisor_id,))

        if result:
            # Convert the result to a Pandas DataFrame
            df = pd.DataFrame(result, columns=[
                'Slot_ID', 'Date', 'Start_Time', 'End_Time', 'Reserved_By'
            ])

            logger.debug("Formatting reserved slots data...")

            # Format the Date column to 'YYYY-MM-DD'
            df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')

            # Remove '0 days' from Start_Time and End_Time and convert to string
            df['Start_Time'] = df['Start_Time'].astype(str).str.replace('0 days ', '', regex=False)
            df['End_Time'] = df['End_Time'].astype(str).str.replace('0 days ', '', regex=False)

            # Replace NaN or None values in Reserved_By with "Unknown"
            df['Reserved_By'] = df['Reserved_By'].fillna('Unknown').astype(str)

            # Convert DataFrame to a list of dictionaries
            reserved_slots = df.to_dict(orient='records')
            logger.debug(f"Formatted reserved slots: {reserved_slots}")

            return reserved_slots
        else:
            # Return an empty list if no reserved slots are found
            logger.debug(f"No reserved slots found for advisor_ID {advisor_id}")
            return []
    except Exception as e:
        logger.error(f"Error fetching reserved slots for advisor_ID {advisor_id}: {e}")
        return []


def add_availability_slot(advisor_id: int, slot_date: str, start_time: str, end_time: str) -> None:
    """
    Add a new availability slot for the advisor.
    """
    logger.debug(f"Attempting to add slot: advisor_id={advisor_id}, slot_date={slot_date}, start_time={start_time}, end_time={end_time}")
    query = """
        INSERT INTO advisor_slots (advisor_id, slot_date, start_time, end_time, is_reserved)
        VALUES (%s, %s, %s, %s, FALSE)
    """
    try:
        execute_update(query, (advisor_id, slot_date, start_time, end_time))
        logger.debug("Slot successfully added to database.")
    except Exception as e:
        logger.error(f"Error adding availability slot: {e}")
        raise



    
def delete_availability_slot(slot_id: int) -> None:
    """
    Delete an availability slot by ID.
    """
    query = "DELETE FROM advisor_slots WHERE id = %s"
    execute_update(query, (slot_id,))


def fetch_availability_slots(advisor_id: int) -> list:
    """
    Fetch and format all availability slots for a given advisor using their advisor_ID.
    Returns a list of dictionaries suitable for passing to templates.
    """
    try:
        logger.debug(f"Fetching availability slots for advisor_ID: {advisor_id}")

        # SQL Query to fetch availability slots for the advisor
        query = """
            SELECT 
                a.id AS Slot_ID,
                a.slot_date AS Date,
                a.start_time AS Start_Time,
                a.end_time AS End_Time,
                CASE 
                    WHEN a.is_reserved = 0 THEN 'No'
                    ELSE 'Yes'
                END AS Reserved,
                a.reserved_by AS Student_ID
            FROM advisor_slots AS a
            WHERE a.advisor_ID = %s
            ORDER BY a.slot_date, a.start_time;
        """
        result = execute_query(query, (advisor_id,))

        if result:
            # Convert the result to a Pandas DataFrame for easy manipulation
            df = pd.DataFrame(result, columns=[
                'Slot_ID', 'Date', 'Start_Time', 'End_Time', 'Reserved', 'Student_ID'
            ])

            logger.debug("Formatting availability slots data...")

            # Convert 'Date' to a readable format (YYYY-MM-DD)
            df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')

            # Remove '0 days' from Start_Time and End_Time and convert to string
            df['Start_Time'] = df['Start_Time'].astype(str).str.replace('0 days ', '', regex=False)
            df['End_Time'] = df['End_Time'].astype(str).str.replace('0 days ', '', regex=False)

            # Replace NaN in 'Student_ID' with empty string
            df['Student_ID'] = df['Student_ID'].fillna('').astype(str)

            # Convert DataFrame to a list of dictionaries
            slots_dict = df.to_dict(orient='records')
            logger.debug(f"Formatted availability slots as dictionary: {slots_dict}")

            return slots_dict
        else:
            # Return an empty list if no slots are available
            logger.debug(f"No availability slots found for advisor_ID {advisor_id}")
            return []
    except Exception as e:
        logger.error(f"Error fetching availability slots for advisor_ID {advisor_id}: {e}")
        return []


def get_student_id_from_slot(slot_id: int) -> int:
    """
    Fetch the student ID associated with a reserved slot.
    """
    query = "SELECT reserved_by FROM advisor_slots WHERE id = %s AND is_reserved = 1;"
    result = execute_query(query, (slot_id,))
    return result[0]['reserved_by'] if result else None


def fetch_chatroom_status(slot_id: int) -> bool:
    """
    Check if a chatroom is active for a specific slot.
    """
    query = "SELECT is_active FROM advisor_slots WHERE id = %s;"
    result = execute_query(query, (slot_id,))
    return result[0]['is_active'] if result else False


def open_chatroom(slot_id: int) -> None:
    """
    Open a chatroom for a specific slot.
    """
    query = "UPDATE advisor_slots SET is_active = 1 WHERE id = %s;"
    execute_update(query, (slot_id,))
    logger.debug(f"Chatroom opened for slot_id {slot_id}")


def close_chatroom(slot_id: int) -> None:
    """
    Close a chatroom for a specific slot.
    """
    query = "UPDATE advisor_slots SET is_active = 0 WHERE id = %s;"
    execute_update(query, (slot_id,))
    logger.debug(f"Chatroom closed for slot_id {slot_id}")


def end_chatroom(slot_id: int):
    """
    End a chatroom session.
    """
    query = """
        UPDATE advisor_slots
        SET is_active = FALSE
        WHERE id = %s;
    """
    execute_update(query, (slot_id,))


def get_user_id_from_student_id(student_id: int) -> int:
    """
    Get user ID for a student.
    """
    query = "SELECT user_ID FROM student WHERE student_ID = %s;"
    result = execute_query(query, (student_id,))
    return result[0]['user_ID'] if result else None


def get_user_id_from_advisor_id(advisor_id: int) -> int:
    """
    Get user ID for an advisor.
    """
    query = "SELECT user_ID FROM advisor WHERE advisor_ID = %s;"
    result = execute_query(query, (advisor_id,))
    return result[0]['user_ID'] if result else None


def validate_advisor_id(advisor_id: int) -> bool:
    """
    Validate if an advisor ID exists.
    """
    query = "SELECT COUNT(*) AS count FROM advisor WHERE advisor_ID = %s"
    result = execute_query(query, (advisor_id,))
    return result[0]['count'] > 0


def fetch_advisor_slots(user_id: int) -> pd.DataFrame:
    try:
        # Step 1: Fetch the student_ID corresponding to the user_ID
        student_id_query = "SELECT student_ID, advisor_ID FROM student WHERE user_ID = %s"
        student_result = execute_query(student_id_query, (user_id,))
        if not student_result:
            logger.warning(f"No student found for user_id {user_id}")
            return pd.DataFrame()

        student_id = student_result[0]['student_ID']
        advisor_id = student_result[0]['advisor_ID']
        logger.debug(f"Found student_ID {student_id} and advisor_ID {advisor_id} for user_id {user_id}")

        # Step 2: Fetch the advisor's available slots
        query = """
            SELECT 
                id AS Slot_ID, 
                slot_date AS Date, 
                start_time AS Start_Time, 
                end_time AS End_Time
            FROM advisor_slots
            WHERE advisor_ID = %s AND is_reserved = 0
            ORDER BY slot_date, start_time;
        """
        result = execute_query(query, (advisor_id,))
        if result:
            logger.debug(f"Advisor slots fetched for advisor_id {advisor_id}: {result}")
            return [
                {
                    'Slot_ID': row['Slot_ID'],
                    'Date': row['Date'],
                    'Start_Time': row['Start_Time'],
                    'End_Time': row['End_Time']
                }
                for row in result
            ]
        else:
            logger.warning(f"No available slots found for advisor_id {advisor_id}")
            return []
    except Exception as e:
        logger.error(f"Error fetching advisor slots for user_id {user_id}: {e}")
        return []



def reserve_advisor_slot(user_id: int, slot_id: int) -> bool:
    try:
        # Step 1: Fetch the student_ID corresponding to the user_ID
        student_id_query = "SELECT student_ID FROM student WHERE user_ID = %s"
        student_result = execute_query(student_id_query, (user_id,))
        if not student_result:
            logger.warning(f"No student found for user_id {user_id}")
            return False

        student_id = student_result[0]['student_ID']
        logger.debug(f"Found student_ID {student_id} for user_id {user_id}")

        # Step 2: Attempt to reserve the slot
        query = """
            UPDATE advisor_slots
            SET is_reserved = 1, reserved_by = %s
            WHERE id = %s AND is_reserved = 0;
        """
        rows_affected = execute_update(query, (student_id, slot_id))
        if rows_affected > 0:
            logger.info(f"Slot {slot_id} successfully reserved for student_id {student_id}")
            return True
        else:
            logger.warning(f"Slot {slot_id} is already reserved or does not exist for student_id {student_id}")
            return False
    except Exception as e:
        logger.error(f"Error reserving slot {slot_id} for user_id {user_id}: {e}")
        return False


def fetch_student_id_by_user_id(user_id: int) -> int:
    if not user_id:
        logger.warning("User ID is None, cannot fetch student ID.")
        return None

    query = "SELECT student_ID FROM student WHERE user_ID = %s"
    try:
        result = execute_query(query, (user_id,))
        if not result:
            logger.warning(f"No student found for user_id {user_id}")
            return None

        student_id = result[0]['student_ID']
        logger.debug(f"Found student_ID {student_id} for user_id {user_id}")
        return student_id
    except Exception as e:
        logger.error(f"Error fetching student ID for user_id {user_id}: {e}", exc_info=True)
        return None


def get_advisor_id(user_id):
    query = "SELECT advisor_ID FROM advisor WHERE user_id = %s"
    result = execute_query(query, (user_id,))
    if result:
        return result[0]['advisor_ID']
    return None


def fetch_advisor_info(advisor_id):
    """
    Fetch detailed information about the advisor based on their advisor_id.
    """
    query = """
        SELECT 
            advisor_ID, 
            advisor_name
        FROM 
            advisor
        WHERE 
            advisor_ID = %s
    """
    result = execute_query(query, (advisor_id,))
    if result:
        return result[0]  # Return the first result (dictionary format)
    return None


def get_user_id_from_student_id(student_id):
    query = "SELECT user_ID FROM student WHERE student_ID = %s"
    result = execute_query(query, (student_id,))
    return result[0]['user_ID'] if result else None


# Head of Advising Functions

def get_head_id(user_id):
    # Assuming `db_utils` is used to interact with the database
    query = "SELECT id FROM head_of_advising WHERE user_id = %s"
    result = execute_query(query, (user_id,))
    if result:
        return result[0]['id']
    return None


def fetch_head_info(head_id):
    query = """
        SELECT id, name
        FROM head_of_advising
        WHERE id = %s
    """
    result = execute_query(query, (head_id,))
    if result:
        return result[0]  
    return None


def add_head_slot(head_id: int, slot_date: str, start_time: str, end_time: str) -> None:
    logger.debug(f"Attempting to add slot: head_id={head_id}, slot_date={slot_date}, start_time={start_time}, end_time={end_time}")
    query = """
        INSERT INTO advisor_slots (head_id, slot_date, start_time, end_time, is_reserved)
        VALUES (%s, %s, %s, %s, FALSE)
    """
    try:
        execute_update(query, (head_id, slot_date, start_time, end_time))
        logger.debug("Slot successfully added to database.")
    except Exception as e:
        logger.error(f"Error adding availability slot: {e}")
        raise


def delete_head_slot(slot_id: int) -> None:
    query = "DELETE FROM advisor_slots WHERE id = %s"
    execute_update(query, (slot_id,))


def fetch_head_slots(head_id: int) -> list:
    try:
        logger.debug(f"Fetching availability slots for head_ID: {head_id}")

        # SQL Query to fetch availability slots for the advisor
        query = """
            SELECT 
                a.id AS Slot_ID,
                a.slot_date AS Date,
                a.start_time AS Start_Time,
                a.end_time AS End_Time,
                CASE 
                    WHEN a.is_reserved = 0 THEN 'No'
                    ELSE 'Yes'
                END AS Reserved,
                a.reserved_by AS Student_ID
            FROM advisor_slots AS a
            WHERE a.head_id = %s
            ORDER BY a.slot_date, a.start_time;
        """
        result = execute_query(query, (head_id,))

        if result:
            # Convert the result to a Pandas DataFrame for easy manipulation
            df = pd.DataFrame(result, columns=[
                'Slot_ID', 'Date', 'Start_Time', 'End_Time', 'Reserved', 'Student_ID'
            ])

            logger.debug("Formatting availability slots data...")

            # Convert 'Date' to a readable format (YYYY-MM-DD)
            df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')

            # Remove '0 days' from Start_Time and End_Time and convert to string
            df['Start_Time'] = df['Start_Time'].astype(str).str.replace('0 days ', '', regex=False)
            df['End_Time'] = df['End_Time'].astype(str).str.replace('0 days ', '', regex=False)

            # Replace NaN in 'Student_ID' with empty string
            df['Student_ID'] = df['Student_ID'].fillna('').astype(str)

            # Convert DataFrame to a list of dictionaries
            slots_dict = df.to_dict(orient='records')
            logger.debug(f"Formatted availability slots as dictionary: {slots_dict}")

            return slots_dict
        else:
            # Return an empty list if no slots are available
            logger.debug(f"No availability slots found for head_ID {head_id}")
            return []
    except Exception as e:
        logger.error(f"Error fetching availability slots for head_ID {head_id}: {e}")
        return []


def get_headofadvising_summary(user_id: int) -> dict:
    try:
        # Step 1: Fetch total students
        total_students_query = "SELECT student_ID FROM student"
        students = execute_query(total_students_query)
        total_students = len(students)

        if total_students == 0:
            return {
                "total_students": 0,
                "students_on_probation": 0,
                "students_advised": 0
            }

        student_ids = [student['student_ID'] for student in students]

        # Step 2: Count students on probation
        probation_count = 0
        for student_id in student_ids:
            # Query to fetch GPA data for the student, ordered by semester
            probation_query = """
                SELECT semester_ID, cumulative_gpa
                FROM semester_gpa
                WHERE student_ID = %s
                ORDER BY semester_ID ASC;
            """
            gpa_results = execute_query(probation_query, (student_id,))

            if not gpa_results:
                continue

            # Convert results to DataFrame
            df = pd.DataFrame(gpa_results, columns=["semester_ID", "cumulative_gpa"])

            # Separate semesters ending with '3' for special handling
            regular_semesters = df[~df["semester_ID"].astype(str).str.endswith("3")].copy()

            # Initialize counters for consecutive probation semesters
            consecutive_count = 0
            max_consecutive_count = 0

            # Process regular semesters
            for _, row in regular_semesters.iterrows():
                cumulative_gpa = float(row["cumulative_gpa"])

                if cumulative_gpa < 2.0:
                    consecutive_count += 1
                    max_consecutive_count = max(max_consecutive_count, consecutive_count)
                else:
                    consecutive_count = 0  # Reset streak

            # Check if max consecutive probation semesters meet threshold
            probation_threshold = int(fetch_configuration('consecutive_semesters') or 3)
            if max_consecutive_count >= probation_threshold:
                probation_count += 1

        # Step 3: Count students with completed advising for active semesters
        # Dynamically generate the placeholders for the IN clause
        placeholders = ', '.join(['%s'] * len(student_ids))
        advising_query = f"""
            SELECT DISTINCT ar.student_ID
            FROM advising_reports ar
            JOIN sis_semester ss ON ar.semester_ID = ss.semester_ID
            WHERE ar.student_ID IN ({placeholders}) AND ss.active = 1;
        """
        advising_result = execute_query(advising_query, tuple(student_ids))
        advised_students = len(advising_result)

        # Return summary
        return {
            "total_students": total_students,
            "students_on_probation": probation_count,
            "students_advised": advised_students
        }

    except Exception as e:
        logger.error(f"Error fetching students summary {user_id}: {e}", exc_info=True)
        return {
            "total_students": 0,
            "students_on_probation": 0,
            "students_advised": 0
        }



def get_program_student_summary():
    try:
        # Step 1: Fetch program and student counts
        program_query = """
            SELECT 
                p.program_description,
                p.program_ID,
                COUNT(s.student_ID) AS total_students
            FROM program p
            LEFT JOIN student s ON p.program_ID = s.program_ID
            GROUP BY p.program_ID, p.program_description
        """
        programs = execute_query(program_query)

        # Step 2: Fetch probation counts for each program
        probation_query = """
            SELECT 
                s.program_ID, s.student_ID, sg.semester_ID, sg.cumulative_gpa
            FROM student s
            JOIN semester_gpa sg ON s.student_ID = sg.student_ID
            WHERE sg.cumulative_gpa < %s
            ORDER BY sg.semester_ID ASC
        """
        probation_threshold = 2.0  # Example probation GPA threshold
        probation_data = execute_query(probation_query, (probation_threshold,))

        # Step 3: Process probation data to filter out summer semesters and calculate counts
        probation_counts = {}
        for row in probation_data:
            program_id = row['program_ID']
            semester_id = str(row['semester_ID'])
            cumulative_gpa = float(row['cumulative_gpa'])

            # Skip summer semesters (semester_ID ends with '3')
            if semester_id.endswith("3"):
                continue

            # Track students on probation per program
            if cumulative_gpa < probation_threshold:
                if program_id not in probation_counts:
                    probation_counts[program_id] = set()  # Use a set to avoid duplicate students
                probation_counts[program_id].add(row['student_ID'])

        # Convert sets to counts for each program
        probation_counts = {program_id: len(student_ids) for program_id, student_ids in probation_counts.items()}

        # Step 4: Build summary result
        program_summary = []
        for program in programs:
            program_id = program['program_ID']
            program_summary.append({
                "program_name": program['program_description'],
                "total_students": program['total_students'],
                "students_on_probation": probation_counts.get(program_id, 0)
            })

        return program_summary

    except Exception as e:
        logger.error(f"Error fetching program student summary: {e}", exc_info=True)
        return []
    


def fetch_advising_report(student_id, semester_id=None):
    """
    Fetch advising reports for a specific student, optionally filtered by semester
    """
    try:
        # Base query
        query = """
            SELECT ar.*, c.course_name, c.course_code, c.credit_hours, CONCAT(s.semester, ' - ', s.semester_year) AS semester_name 
            FROM advising_reports ar
            JOIN course c ON ar.course_ID = c.id
            JOIN sis_semester s ON ar.semester_ID = s.id
            WHERE ar.student_ID = %s
        """
        params = [student_id]
        
        # Add semester filter if provided
        if semester_id:
            query += " AND ar.semester_ID = %s"
            params.append(semester_id)
            
        # Order by semester and course
        query += " ORDER BY ar.semester_ID DESC, c.course_name"
        
        # Execute query and return results
        reports = execute_query(query, params)
        
        return {
            'success': True,
            'reports': reports
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
    


# Program Director Functions

def check_program_director(advisor_id):
    query = """
            SELECT program_director
            FROM advisor
            WHERE advisor_ID = %s
            """
    
    # Execute the query and fetch the result
    result = execute_query(query, (advisor_id,))
    
    if result:
        # Assuming execute_query returns a list of rows
        return result[0]['program_director'] == 1
    else:
        return False  # Advisor not found


def get_program_director_summary(advisor_id: int) -> dict:
   
    try:
        # Step 1: Fetch the program_ID of the advisor
        program_query = "SELECT program_ID FROM advisor WHERE advisor_ID = %s;"
        advisor_program = execute_query(program_query, (advisor_id,))
        
        if not advisor_program or not advisor_program[0]["program_ID"]:
            return {
                "total_students": 0,
                "students_on_probation": 0,
                "students_advised": 0
            }

        program_id = advisor_program[0]["program_ID"]

        # Step 2: Fetch all students with the same program_ID
        students_query = "SELECT student_ID FROM student WHERE program_ID = %s;"
        students = execute_query(students_query, (program_id,))
        total_students = len(students)

        if total_students == 0:
            return {
                "total_students": 0,
                "students_on_probation": 0,
                "students_advised": 0
            }

        student_ids = [student['student_ID'] for student in students]

        # Step 3: Count students on probation
        probation_count = 0
        for student_id in student_ids:
            probation_query = """
                SELECT semester_ID, cumulative_gpa
                FROM semester_gpa
                WHERE student_ID = %s
                ORDER BY semester_ID ASC;
            """
            gpa_results = execute_query(probation_query, (student_id,))

            if not gpa_results:
                continue

            # Convert results to DataFrame
            df = pd.DataFrame(gpa_results, columns=["semester_ID", "cumulative_gpa"])

            # Separate regular semesters
            regular_semesters = df[~df["semester_ID"].astype(str).str.endswith("3")].copy()

            # Initialize counters for consecutive probation semesters
            consecutive_count = 0
            max_consecutive_count = 0

            for _, row in regular_semesters.iterrows():
                cumulative_gpa = float(row["cumulative_gpa"])

                if cumulative_gpa < 2.0:
                    consecutive_count += 1
                    max_consecutive_count = max(max_consecutive_count, consecutive_count)
                else:
                    consecutive_count = 0  # Reset streak

            # Check if max consecutive probation semesters meet threshold
            probation_threshold = int(fetch_configuration('consecutive_semesters') or 3)
            if max_consecutive_count >= probation_threshold:
                probation_count += 1

        # Step 4: Count students with completed advising for active semesters
        placeholders = ', '.join(['%s'] * len(student_ids))
        advising_query = f"""
            SELECT DISTINCT ar.student_ID
            FROM advising_reports ar
            JOIN sis_semester ss ON ar.semester_ID = ss.semester_ID
            WHERE ar.student_ID IN ({placeholders}) AND ss.active = 1;
        """
        advising_result = execute_query(advising_query, tuple(student_ids))
        advised_students = len(advising_result)

        # Return summary
        return {
            "total_students": total_students,
            "students_on_probation": probation_count,
            "students_advised": advised_students
        }

    except Exception as e:
        logger.error(f"Error fetching student summary for advisor {advisor_id}: {e}", exc_info=True)
        return {
            "total_students": 0,
            "students_on_probation": 0,
            "students_advised": 0
        }


def get_advisor_program_id(advisor_id):
    query = "SELECT program_ID FROM advisor WHERE advisor_ID = %s"
    try:
        result = execute_query(query, (advisor_id,))
        logger.debug(f"Query result for advisor_id {advisor_id}: {result}")
        
        if not result:
            logger.warning(f"No program found for advisor_id {advisor_id}")
            return None
            
        # Handle result as dictionary
        if isinstance(result[0], dict):
            return result[0]['program_ID']
        # Handle result as tuple
        elif isinstance(result[0], tuple):
            return result[0][0]
        else:
            logger.error(f"Unexpected result format: {type(result[0])}")
            return None
            
    except Exception as e:
        logger.error(f"Error in get_advisor_program_id for advisor_id {advisor_id}: {str(e)}")
        return None


def get_unassigned_students(program_id):
    query = """
    SELECT 
        s.student_ID, 
        s.student_name, 
        sg.cumulative_gpa
    FROM 
        student s
    LEFT JOIN (
        SELECT student_ID, cumulative_gpa
        FROM semester_gpa
        WHERE (student_ID, semester_ID) IN (
            SELECT student_ID, MAX(semester_ID)
            FROM semester_gpa
            GROUP BY student_ID
        )
    ) sg
    ON s.student_ID = sg.student_ID
    WHERE s.program_ID = %s AND s.advisor_ID IS NULL
    """
    return execute_query(query, (program_id,))



def get_program_advisors(program_id):
    query = """
    SELECT advisor_ID, advisor_name 
    FROM advisor 
    WHERE program_ID = %s
    """
    return execute_query(query, (program_id,))


def get_assigned_students(program_id):
    query = """
    SELECT 
        s.student_ID, 
        s.student_name, 
        a.advisor_ID, 
        a.advisor_name, 
        sg.cumulative_gpa
    FROM 
        student s
    JOIN advisor a 
        ON s.advisor_ID = a.advisor_ID
    LEFT JOIN (
        SELECT student_ID, cumulative_gpa
        FROM semester_gpa
        WHERE (student_ID, semester_ID) IN (
            SELECT student_ID, MAX(semester_ID)
            FROM semester_gpa
            GROUP BY student_ID
        )
    ) sg
        ON s.student_ID = sg.student_ID
    WHERE 
        s.program_ID = %s
    """
    return execute_query(query, (program_id,))


def assign_student_to_advisor(student_id, new_advisor_id, program_id):
    # First check if the student and advisor are in the same program
    check_query = """
    SELECT 1 FROM student s, advisor a 
    WHERE s.student_ID = %s AND a.advisor_ID = %s 
    AND s.program_ID = a.program_ID AND s.program_ID = %s
    """
    try:
        result = execute_query(check_query, (student_id, new_advisor_id, program_id))
        if not result:
            logger.error(f"Program mismatch or invalid IDs for student {student_id} and advisor {new_advisor_id}")
            return False

        # Update the student's advisor
        update_query = """
        UPDATE student 
        SET advisor_ID = %s 
        WHERE student_ID = %s AND program_ID = %s
        """
        params = (new_advisor_id, student_id, program_id)
        
        # Execute the update query using execute_update function
        if execute_update(update_query, params):
            logger.debug(f"Successfully assigned student {student_id} to advisor {new_advisor_id}")
            return True
        else:
            logger.error(f"Failed to update database for student {student_id} and advisor {new_advisor_id}")
            return False

    except Exception as e:
        logger.error(f"Error in assign_student_to_advisor: {str(e)}")
        return False
    

def get_program_student_summary_for_director(advisor_id):
    try:
        # Step 1: Fetch the program_ID for the given advisor
        advisor_query = """
            SELECT program_ID
            FROM advisor
            WHERE advisor_ID = %s
        """
        advisor_data = execute_query(advisor_query, (advisor_id,))
        if not advisor_data:
            logger.error(f"No program found for advisor_id: {advisor_id}")
            return []
        
        advisor_program_id = advisor_data[0]['program_ID']

        # Step 2: Fetch program and student counts for the advisor's program
        program_query = """
            SELECT 
                p.program_description,
                p.program_ID,
                COUNT(s.student_ID) AS total_students
            FROM program p
            LEFT JOIN student s ON p.program_ID = s.program_ID
            WHERE p.program_ID = %s
            GROUP BY p.program_ID, p.program_description
        """
        programs = execute_query(program_query, (advisor_program_id,))

        # Step 3: Fetch probation counts for the advisor's program
        probation_query = """
            SELECT 
                s.program_ID, s.student_ID, sg.semester_ID, sg.cumulative_gpa
            FROM student s
            JOIN semester_gpa sg ON s.student_ID = sg.student_ID
            WHERE s.program_ID = %s AND sg.cumulative_gpa < %s
            ORDER BY sg.semester_ID ASC
        """
        probation_threshold = 2.0  # Example probation GPA threshold
        probation_data = execute_query(probation_query, (advisor_program_id, probation_threshold))

        # Step 4: Process probation data to filter out summer semesters and calculate counts
        probation_counts = {}
        for row in probation_data:
            program_id = row['program_ID']
            semester_id = str(row['semester_ID'])
            cumulative_gpa = float(row['cumulative_gpa'])

            # Skip summer semesters (semester_ID ends with '3')
            if semester_id.endswith("3"):
                continue

            # Track students on probation for the program
            if cumulative_gpa < probation_threshold:
                if program_id not in probation_counts:
                    probation_counts[program_id] = set()  # Use a set to avoid duplicate students
                probation_counts[program_id].add(row['student_ID'])

        # Convert sets to counts for the program
        probation_counts = {program_id: len(student_ids) for program_id, student_ids in probation_counts.items()}

        # Step 5: Build summary result
        program_summary = []
        for program in programs:
            program_id = program['program_ID']
            program_summary.append({
                "program_name": program['program_description'],
                "total_students": program['total_students'],
                "students_on_probation": probation_counts.get(program_id, 0)
            })

        return program_summary

    except Exception as e:
        logger.error(f"Error fetching program student summary for advisor: {e}", exc_info=True)
        return []



# Send Advising Report

def send_courses_to_advising_reports(student_id, semester_id, attachment=None, comment=None):
    """
    Transfers recommended courses for a student from the `recommended_courses` table to the
    `advising_reports` table, allowing the advisor to specify a semester, upload an attachment,
    and add comments. Deletes the courses from `recommended_courses` only after a successful transfer.

    Args:
        student_id (int): The ID of the student whose courses are being processed.
        semester_id (int): The semester ID chosen by the advisor.
        attachment (str, optional): The filename or path of the attachment. Defaults to None.
        comment (str, optional): Comments provided by the advisor. Defaults to None.

    Returns:
        dict: Success or error message with details.
    """
    try:
        # Step 1: Retrieve recommended courses for the student
        fetch_query = """
        SELECT course_ID FROM recommended_courses WHERE student_ID = %s
        """
        recommended_courses = execute_query(fetch_query, (student_id,))
        
        if not recommended_courses:
            return {"success": False, "message": "No recommended courses found for the student."}

        # Step 2: Validate that the semester exists in the sis_semester table
        validate_semester_query = """
        SELECT semester_ID FROM sis_semester WHERE semester_ID = %s
        """
        valid_semester = execute_query(validate_semester_query, (semester_id,))
        if not valid_semester:
            return {"success": False, "message": "Invalid semester ID provided."}

        # Step 3: Insert the courses into advising_reports
        insert_query = """
        INSERT INTO advising_reports (student_ID, course_ID, semester_ID, warning_attachment, comments)
        VALUES (%s, %s, %s, %s, %s)
        """
        for course in recommended_courses:
            execute_update(insert_query, (student_id, course['course_ID'], semester_id, attachment, comment))

        # Step 4: Delete the courses from recommended_courses
        delete_query = """
        DELETE FROM recommended_courses WHERE student_ID = %s
        """
        execute_update(delete_query, (student_id,))

        return {"success": True, "message": "Courses successfully transferred to advising reports and deleted from recommended_courses."}
    
    except Exception as e:
        return {"success": False, "message": str(e)}


def fetch_semesters():
    query = """SELECT semester_ID, CONCAT(semester, ' - ', semester_year) AS semester_name 
                 FROM sis_semester ORDER BY semester_ID DESC"""
    return execute_query(query)



# Chat functions

def get_current_timestamp():
    return datetime.utcnow()

def save_message(room, sender_id, receiver_id, message):
    try:
        query = """
            INSERT INTO chat_messages (slot_id, sender_id, receiver_id, message, timestamp)
            VALUES (%s, %s, %s, %s, %s)
        """
        
        params = (room, sender_id, receiver_id, message, datetime.now())
        execute_update(query, params)
        return True
        
    except Exception as e:
        logger.error(f"Error saving message: {str(e)}")
        return False


def get_receiver_id_from_slot(slot_id, sender_id):
    """
    Fetch the receiver user_ID based on the slot ID and sender user_ID.
    """
    try:
        query = """
            SELECT a.user_ID as advisor_user_id, s.user_ID as student_user_id 
            FROM advisor_slots AS slot
            JOIN advisor AS a ON slot.advisor_ID = a.advisor_ID
            JOIN student AS s ON slot.reserved_by = s.student_ID
            WHERE slot.id = %s
        """
        result = execute_query(query, (slot_id,))

        logger.debug(f"Query result for slot {slot_id}: {result}")

        if result and len(result) > 0:
            row = result[0]
            advisor_user_id = row['advisor_user_id']
            student_user_id = row['student_user_id']

            logger.debug(f"Sender ID: {sender_id}, Advisor User ID: {advisor_user_id}, Student User ID: {student_user_id}")

            if int(sender_id) == int(advisor_user_id):
                return student_user_id
            elif int(sender_id) == int(student_user_id):
                return advisor_user_id
            else:
                logger.error(f"Sender {sender_id} is neither the advisor nor the student for slot {slot_id}.")
                return None
        else:
            logger.error(f"Slot {slot_id} not found or not associated with both advisor and student.")
            return None

    except Exception as e:
        logger.exception(f"Unexpected error retrieving receiver ID for slot {slot_id}: {str(e)}")
        return None


def get_active_chat_slot(advisor_id):
    query = """
        SELECT Slot_ID FROM advisor_slots 
        WHERE advisor_ID = %s AND is_active = 1 
        LIMIT 1
    """
    result = execute_query(query, (advisor_id,))
    return result[0] if result else None