
import streamlit as st
import sqlite3
import hashlib
import hmac
import os
import json
from datetime import date
from google import genai
from google.genai import types
from pypdf import PdfReader


# --------------------------------------------------
# 1. PAGE SETTINGS
# --------------------------------------------------

st.set_page_config(
    page_title="StudySphere",
    page_icon="🎓",
    layout="wide"
)


# --------------------------------------------------
# 2. STUDYSPHERE THEME
# --------------------------------------------------

st.markdown("""
<style>

.stApp {
    background-color: #F4F7FB;
    color: #142B4A;
}

[data-testid="stSidebar"] {
    background-color: #142B4A;
}

[data-testid="stSidebar"] * {
    color: #FFFFFF !important;
}

h1, h2, h3 {
    color: #142B4A !important;
    font-weight: 700 !important;
}

.stApp p {
    color: #243B53;
}

.brand-title {
    color: #142B4A;
    font-size: 44px;
    font-weight: 800;
    text-align: center;
}

.brand-tagline {
    color: #40536B;
    font-size: 17px;
    font-weight: 600;
    text-align: center;
    margin-bottom: 25px;
}

.stTabs [data-baseweb="tab"] {
    color: #142B4A !important;
    font-weight: 800 !important;
    font-size: 17px !important;
}

.stTabs [data-baseweb="tab"] p {
    color: #142B4A !important;
    font-weight: 800 !important;
}

.stTabs [aria-selected="true"] {
    color: #1D5FA7 !important;
    border-bottom-color: #1D5FA7 !important;
}

.stTextInput label,
.stTextArea label,
.stSelectbox label,
.stDateInput label,
.stRadio label,
.stCheckbox label {
    color: #142B4A !important;
    font-weight: 700 !important;
    font-size: 16px !important;
}

.stTextInput input,
.stTextArea textarea,
.stDateInput input {
    color: #142B4A !important;
    background-color: #FFFFFF !important;
    border: 1.5px solid #9BAFC5 !important;
    border-radius: 8px !important;
    font-size: 16px !important;
}

.stTextInput input::placeholder,
.stTextArea textarea::placeholder {
    color: #687D94 !important;
    opacity: 1 !important;
}

.stTextInput input:focus,
.stTextArea textarea:focus {
    border: 2px solid #244B75 !important;
    box-shadow: 0 0 0 1px #244B75 !important;
}

div[data-testid="stForm"] {
    background-color: #FFFFFF !important;
    padding: 25px !important;
    border-radius: 12px !important;
    border: 1px solid #DCE5EF !important;
}

.stButton > button,
.stFormSubmitButton > button {
    background-color: #142B4A !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    padding: 10px 18px !important;
}

.stButton > button p,
.stFormSubmitButton > button p {
    color: #FFFFFF !important;
}

.stButton > button:hover,
.stFormSubmitButton > button:hover {
    background-color: #3D75B9 !important;
    color: #FFFFFF !important;
}

.welcome-card {
    background-color: #142B4A;
    padding: 30px;
    border-radius: 15px;
    margin-bottom: 20px;
}

.welcome-card h2 {
    color: #FFFFFF !important;
}

.welcome-card p {
    color: #DCE8F5 !important;
}

[data-testid="stMetric"] {
    background-color: #FFFFFF;
    padding: 18px;
    border-radius: 10px;
    border: 1px solid #DCE5EF;
}

[data-testid="stMetricLabel"],
[data-testid="stMetricValue"] {
    color: #142B4A !important;
}

.stAlert {
    border-radius: 10px;
}

.stDownloadButton > button {
    background-color: #244B75 !important;
    color: #FFFFFF !important;
}

hr {
    border-color: #DCE5EF;
}

</style>
""", unsafe_allow_html=True)


# --------------------------------------------------
# 3. GEMINI AI CONNECTION
# --------------------------------------------------

try:
    client = genai.Client(
        api_key=st.secrets["GEMINI_API_KEY"],
        http_options=types.HttpOptions(timeout=120000)
    )

except Exception:
    st.error(
        "Gemini API connection failed. "
        "Please check your .streamlit/secrets.toml file."
    )
    st.stop()

MODEL_NAME = "gemini-3.5-flash-lite"


# --------------------------------------------------
# 4. DATABASE SETUP
# --------------------------------------------------

DB_NAME = "study_planner.db"


def get_connection():
    return sqlite3.connect(DB_NAME)


def setup_database():

    conn = get_connection()
    cursor = conn.cursor()

    # Create students table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT
        )
    """)

    # Check student table columns
    cursor.execute("PRAGMA table_info(students)")

    student_columns = [
        column[1] for column in cursor.fetchall()
    ]

    # Add password_hash if missing
    if "password_hash" not in student_columns:

        cursor.execute("""
            ALTER TABLE students
            ADD COLUMN password_hash TEXT
        """)

    # Migrate old passwords if an old password column exists
    if "password" in student_columns:

        cursor.execute("""
            SELECT id, password
            FROM students
            WHERE password_hash IS NULL
              AND password IS NOT NULL
        """)

        old_passwords = cursor.fetchall()

        for student_id, old_password in old_passwords:

            old_password = str(old_password)

            is_existing_hash = False

            try:
                salt_hex, hash_hex = old_password.split(":")
                salt = bytes.fromhex(salt_hex)
                stored_hash = bytes.fromhex(hash_hex)

                if len(salt) == 16 and len(stored_hash) == 32:
                    is_existing_hash = True

            except (ValueError, TypeError):
                is_existing_hash = False

            if is_existing_hash:
                migrated_password = old_password

            else:

                salt = os.urandom(16)

                password_hash = hashlib.pbkdf2_hmac(
                    "sha256",
                    old_password.encode("utf-8"),
                    salt,
                    600000
                )

                migrated_password = (
                    salt.hex() + ":" + password_hash.hex()
                )

            cursor.execute("""
                UPDATE students
                SET password_hash = ?
                WHERE id = ?
            """, (migrated_password, student_id))

    # Create tasks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            task TEXT,
            study_date TEXT,
            completed INTEGER DEFAULT 0
        )
    """)

    # Check task table columns
    cursor.execute("PRAGMA table_info(tasks)")

    task_columns = [
        column[1] for column in cursor.fetchall()
    ]

    # Add student_id if missing
    if "student_id" not in task_columns:

        cursor.execute("""
            ALTER TABLE tasks
            ADD COLUMN student_id INTEGER
        """)

    conn.commit()
    conn.close()


setup_database()


# --------------------------------------------------
# 5. PASSWORD SECURITY
# --------------------------------------------------

def hash_password(password):

    salt = os.urandom(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        600000
    )

    return salt.hex() + ":" + password_hash.hex()


def verify_password(password, stored_password):

    try:

        if not stored_password:
            return False

        salt_hex, original_hash = stored_password.split(":")

        salt = bytes.fromhex(salt_hex)

        new_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            600000
        )

        return hmac.compare_digest(
            new_hash.hex(),
            original_hash
        )

    except Exception:
        return False


# --------------------------------------------------
# 6. SESSION STATE
# --------------------------------------------------

if "student_id" not in st.session_state:
    st.session_state.student_id = None

if "student_name" not in st.session_state:
    st.session_state.student_name = None

if "quiz_data" not in st.session_state:
    st.session_state.quiz_data = None

if "quiz_submitted" not in st.session_state:
    st.session_state.quiz_submitted = False


# --------------------------------------------------
# 7. SIGN UP AND LOGIN PAGE
# --------------------------------------------------

def authentication_page():

    st.markdown(
        '<div class="brand-title">🎓 StudySphere</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="brand-tagline">'
        'Your World. Your Learning. Your Future.'
        '</div>',
        unsafe_allow_html=True
    )

    st.divider()

    login_tab, signup_tab = st.tabs(
        ["Login", "Create Account"]
    )

    # LOGIN
    with login_tab:

        st.subheader("Welcome Back!")

        st.write(
            "Login to continue your learning journey."
        )

        with st.form("login_form"):

            email = st.text_input(
                "Email Address",
                placeholder="Enter your email address"
            )

            password = st.text_input(
                "Password",
                type="password",
                placeholder="Enter your password"
            )

            login_button = st.form_submit_button(
                "Login",
                use_container_width=True
            )

            if login_button:

                if not email.strip() or not password:

                    st.warning(
                        "Please enter your email and password."
                    )

                else:

                    conn = get_connection()
                    cursor = conn.cursor()

                    cursor.execute("""
                        SELECT id, name, password_hash
                        FROM students
                        WHERE email = ?
                    """, (email.strip().lower(),))

                    student = cursor.fetchone()

                    conn.close()

                    if student and verify_password(
                        password,
                        student[2]
                    ):

                        st.session_state.student_id = student[0]
                        st.session_state.student_name = student[1]

                        st.success("Login successful!")

                        st.rerun()

                    else:

                        st.error("Invalid email or password.")

    # SIGNUP
    with signup_tab:

        st.subheader("Create Your Account")

        st.write(
            "Join StudySphere and start learning smarter."
        )

        with st.form("signup_form"):

            name = st.text_input(
                "Full Name",
                placeholder="Enter your full name"
            )

            email = st.text_input(
                "Email Address",
                placeholder="Enter your email address"
            )

            password = st.text_input(
                "Create Password",
                type="password",
                placeholder="At least 8 characters"
            )

            confirm_password = st.text_input(
                "Confirm Password",
                type="password",
                placeholder="Enter your password again"
            )

            signup_button = st.form_submit_button(
                "Create Account",
                use_container_width=True
            )

            if signup_button:

                if not name.strip() or not email.strip() or not password:

                    st.warning("Please fill in all fields.")

                elif password != confirm_password:

                    st.error("Passwords do not match.")

                elif len(password) < 8:

                    st.error(
                        "Password must contain at least 8 characters."
                    )

                else:

                    conn = get_connection()
                    cursor = conn.cursor()

                    try:

                        cursor.execute("""
                            INSERT INTO students (
                                name,
                                email,
                                password_hash
                            )
                            VALUES (?, ?, ?)
                        """, (
                            name.strip(),
                            email.strip().lower(),
                            hash_password(password)
                        ))

                        conn.commit()

                        st.success(
                            "Account created successfully! "
                            "Please go to the Login tab."
                        )

                    except sqlite3.IntegrityError:

                        st.error(
                            "This email is already registered."
                        )

                    finally:
                        conn.close()


# --------------------------------------------------
# 8. CHECK LOGIN
# --------------------------------------------------

if st.session_state.student_id is None:

    authentication_page()
    st.stop()


# --------------------------------------------------
# 9. SIDEBAR NAVIGATION
# --------------------------------------------------

with st.sidebar:

    st.markdown("# 🎓 StudySphere")

    st.caption(
        "Your World. Your Learning. Your Future."
    )

    st.divider()

    st.write(
        f"Welcome, **{st.session_state.student_name}**"
    )

    st.divider()

    page = st.radio(
        "Navigation",
        [
            "Home",
            "AI Tutor",
            "Smart Notes",
            "Quiz Generator",
            "Study Planner"
        ]
    )

    st.divider()

    if st.button(
        "Logout",
        use_container_width=True
    ):

        st.session_state.student_id = None
        st.session_state.student_name = None
        st.session_state.quiz_data = None
        st.session_state.quiz_submitted = False

        st.rerun()


# --------------------------------------------------
# 10. HOME DASHBOARD
# --------------------------------------------------

if page == "Home":

    st.markdown("""
    <div class="welcome-card">
        <h2>Welcome to StudySphere! 🎓</h2>
        <p>Your personal AI-powered learning space.</p>
        <p>Learn smarter, practice better and achieve your goals.</p>
    </div>
    """, unsafe_allow_html=True)

    st.subheader("Your Learning Dashboard")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE student_id = ?
    """, (st.session_state.student_id,))

    total_tasks = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM tasks
        WHERE student_id = ? AND completed = 1
    """, (st.session_state.student_id,))

    completed_tasks = cursor.fetchone()[0]

    pending_tasks = total_tasks - completed_tasks

    conn.close()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Total Tasks", total_tasks)

    with col2:
        st.metric("Completed Tasks", completed_tasks)

    with col3:
        st.metric("Pending Tasks", pending_tasks)

    st.divider()

    st.subheader("Explore Your Learning Tools")

    col1, col2 = st.columns(2)

    with col1:

        st.info(
            "### 🤖 AI Tutor\n"
            "Ask questions and understand difficult topics."
        )

        st.info(
            "### 📚 Smart Notes\n"
            "Upload PDFs and generate easy notes."
        )

    with col2:

        st.info(
            "### 📝 Quiz Generator\n"
            "Generate practice MCQs and test yourself."
        )

        st.info(
            "### 📅 Study Planner\n"
            "Organize your daily study tasks."
        )


# --------------------------------------------------
# 11. AI TUTOR
# --------------------------------------------------

elif page == "AI Tutor":

    st.title("🤖 AI Tutor")

    st.write(
        "Ask any academic question and get a simple explanation."
    )

    question = st.text_area(
        "Enter your question",
        placeholder="Example: Explain neural networks in simple words..."
    )

    if st.button("Ask AI Tutor"):

        if question.strip():

            with st.spinner(
                "StudySphere AI is thinking..."
            ):

                try:

                    response = client.models.generate_content(
                        model=MODEL_NAME,
                        contents=(
                            "You are a friendly academic tutor. "
                            "Explain concepts in very simple language "
                            "with examples and step-by-step explanations. "
                            "Help students understand the topic.\n\n"
                            + question
                        )
                    )

                    st.subheader("AI Tutor Answer")
                    st.markdown(response.text or "No answer received.")

                except Exception as e:

                    st.error(f"AI Tutor error: {e}")

        else:

            st.warning("Please enter a question.")


# --------------------------------------------------
# 12. SMART NOTES
# --------------------------------------------------

elif page == "Smart Notes":

    st.title("📚 Smart Notes")

    st.write(
        "Upload a PDF and let StudySphere generate easy-to-understand notes."
    )

    uploaded_file = st.file_uploader(
        "Upload your PDF file",
        type=["pdf"]
    )

    if uploaded_file is not None:

        if st.button("Generate Smart Notes"):

            with st.spinner(
                "Reading PDF and preparing notes..."
            ):

                try:

                    reader = PdfReader(uploaded_file)

                    pdf_text = ""

                    for pdf_page in reader.pages:

                        page_text = pdf_page.extract_text()

                        if page_text:
                            pdf_text += page_text + "\n"

                    if not pdf_text.strip():

                        st.warning(
                            "No readable text found. "
                            "This may be a scanned PDF."
                        )

                    else:

                        pdf_text = pdf_text[:30000]

                        response = client.models.generate_content(
                            model=MODEL_NAME,
                            contents=(
                                "Create simple and well-organized study notes "
                                "from the following PDF content.\n\n"
                                "Include:\n"
                                "1. Topic heading\n"
                                "2. Important definitions\n"
                                "3. Key points\n"
                                "4. Simple explanations\n"
                                "5. Important exam questions\n\n"
                                "Use simple student-friendly language.\n\n"
                                + pdf_text
                            )
                        )

                        notes = response.text or "No notes generated."

                        st.subheader("Your Smart Notes")
                        st.markdown(notes)

                        st.download_button(
                            "Download Notes",
                            data=notes,
                            file_name="StudySphere_Notes.txt",
                            mime="text/plain"
                        )

                except Exception as e:

                    st.error(f"PDF processing error: {e}")


# --------------------------------------------------
# 13. QUIZ GENERATOR
# --------------------------------------------------

elif page == "Quiz Generator":

    st.title("📝 Quiz Generator")

    st.write(
        "Generate 10 multiple-choice questions to test your knowledge."
    )

    topic = st.text_input(
        "Enter the topic",
        placeholder="Example: ARM Architecture"
    )

    difficulty = st.selectbox(
        "Select Difficulty",
        ["Easy", "Medium", "Hard"]
    )

    if st.button("Generate Quiz"):

        if not topic.strip():

            st.warning("Please enter a topic.")

        else:

            with st.spinner(
                "Generating your 10-question quiz..."
            ):

                try:

                    prompt = f"""
                    Create exactly 10 multiple-choice questions about {topic}.
                    Difficulty: {difficulty}.

                    Return ONLY valid JSON in this exact format:

                    {{
                      "questions": [
                        {{
                          "question": "Question text",
                          "options": [
                            "Option A",
                            "Option B",
                            "Option C",
                            "Option D"
                          ],
                          "answer": "Correct option text",
                          "explanation": "Simple explanation"
                        }}
                      ]
                    }}

                    Make sure:
                    - There are exactly 10 questions.
                    - Each question has exactly 4 options.
                    - The answer exactly matches one option.
                    - Each question has an explanation.
                    """

                    response = client.models.generate_content(
                        model=MODEL_NAME,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json"
                        )
                    )

                    quiz_data = json.loads(response.text)

                    if len(quiz_data.get("questions", [])) != 10:
                        raise ValueError(
                            "The AI did not generate exactly 10 questions. "
                            "Please try again."
                        )

                    for question in quiz_data["questions"]:

                        if (
                            len(question.get("options", [])) != 4
                            or question.get("answer") not in question.get("options", [])
                        ):
                            raise ValueError(
                                "The quiz contains an invalid question. "
                                "Please generate it again."
                            )

                    st.session_state.quiz_data = quiz_data
                    st.session_state.quiz_submitted = False

                    st.rerun()

                except Exception as e:

                    st.error(f"Quiz generation error: {e}")

    # DISPLAY QUIZ
    if st.session_state.quiz_data:

        questions = st.session_state.quiz_data["questions"]

        st.divider()

        st.subheader("Your 10 Questions")

        if not st.session_state.quiz_submitted:

            with st.form("quiz_form"):

                answers = []

                for i, question in enumerate(questions):

                    st.markdown(
                        f"**Question {i + 1}: {question['question']}**"
                    )

                    answer = st.radio(
                        "Choose your answer:",
                        question["options"],
                        index=None,
                        key=f"quiz_question_{i}"
                    )

                    answers.append(answer)

                    st.divider()

                submit_quiz = st.form_submit_button(
                    "Submit Quiz",
                    use_container_width=True
                )

                if submit_quiz:

                    if any(answer is None for answer in answers):

                        st.warning(
                            "Please answer all 10 questions."
                        )

                    else:

                        score = 0

                        for i, question in enumerate(questions):

                            if answers[i] == question["answer"]:
                                score += 1

                        st.session_state.quiz_score = score
                        st.session_state.quiz_answers = answers
                        st.session_state.quiz_submitted = True

                        st.rerun()

        else:

            score = st.session_state.quiz_score
            answers = st.session_state.quiz_answers

            st.success(
                f"Your Score: {score} / 10"
            )

            st.progress(score / 10)

            if score >= 8:

                st.balloons()
                st.success("Excellent work! 🎉")

            elif score >= 5:

                st.info(
                    "Good effort! Keep practising."
                )

            else:

                st.warning(
                    "Keep learning. You can improve!"
                )

            st.subheader("Answer Review")

            for i, question in enumerate(questions):

                st.markdown(
                    f"**Question {i + 1}: {question['question']}**"
                )

                st.write(
                    f"Your answer: {answers[i]}"
                )

                st.write(
                    f"Correct answer: {question['answer']}"
                )

                st.write(
                    f"Explanation: {question['explanation']}"
                )

                if answers[i] == question["answer"]:
                    st.success("Correct answer")

                else:
                    st.error("Incorrect answer")

                st.divider()

            if st.button("Generate Another Quiz"):

                st.session_state.quiz_data = None
                st.session_state.quiz_submitted = False

                st.rerun()


# --------------------------------------------------
# 14. STUDY PLANNER
# --------------------------------------------------

elif page == "Study Planner":

    st.title("📅 Study Planner")

    st.write(
        "Plan your study activities and track your progress."
    )

    st.subheader("Add a New Study Task")

    with st.form("task_form"):

        subject = st.text_input(
            "Subject",
            placeholder="Example: Network Theory"
        )

        task = st.text_input(
            "Study Task",
            placeholder="Example: Complete Unit 1"
        )

        study_date = st.date_input(
            "Study Date",
            value=date.today()
        )

        add_task = st.form_submit_button(
            "Add Study Task",
            use_container_width=True
        )

        if add_task:

            if subject.strip() and task.strip():

                conn = get_connection()
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO tasks (
                        subject,
                        task,
                        study_date,
                        completed,
                        student_id
                    )
                    VALUES (?, ?, ?, 0, ?)
                """, (
                    subject.strip(),
                    task.strip(),
                    str(study_date),
                    st.session_state.student_id
                ))

                conn.commit()
                conn.close()

                st.success(
                    "Study task added successfully!"
                )

                st.rerun()

            else:

                st.warning(
                    "Please enter both subject and task."
                )

    st.divider()

    st.subheader("Your Study Tasks")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, subject, task, study_date, completed
        FROM tasks
        WHERE student_id = ?
        ORDER BY study_date ASC, id DESC
    """, (st.session_state.student_id,))

    tasks = cursor.fetchall()

    conn.close()

    if not tasks:

        st.info(
            "No study tasks yet. Add your first task above!"
        )

    else:

        for task_row in tasks:

            task_id, subject, task_name, task_date, completed = task_row

            with st.container(border=True):

                col1, col2 = st.columns([4, 1])

                with col1:

                    st.markdown(f"### {subject}")

                    st.write(task_name)

                    st.caption(
                        f"Study Date: {task_date}"
                    )

                    if completed:
                        st.success("Completed")

                    else:
                        st.warning("Pending")

                with col2:

                    if not completed:

                        if st.button(
                            "Complete",
                            key=f"complete_{task_id}"
                        ):

                            conn = get_connection()
                            cursor = conn.cursor()

                            cursor.execute("""
                                UPDATE tasks
                                SET completed = 1
                                WHERE id = ? AND student_id = ?
                            """, (
                                task_id,
                                st.session_state.student_id
                            ))

                            conn.commit()
                            conn.close()

                            st.rerun()


# --------------------------------------------------
# 15. FOOTER
# --------------------------------------------------

st.divider()

st.markdown("""
<div style="
    text-align: center;
    color: #40536B;
    padding: 20px;
">
    <h3 style="color: #142B4A;">🎓 StudySphere</h3>
    <p>Your World. Your Learning. Your Future.</p>
    <p>Learn Smarter. Achieve More.</p>
</div>
""", unsafe_allow_html=True)
