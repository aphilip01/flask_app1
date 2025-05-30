from flask import Flask, render_template, request, redirect, url_for, jsonify,flash,session
from datetime import datetime
import json
import os
import logging

app = Flask(__name__)
app.jinja_env.auto_reload = True

app.secret_key = 'abcd'  # Set a secret key for session
app.config['TEMPLATES_AUTO_RELOAD'] = True

print("Template folder is:", app.template_folder)


# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Output to console
        logging.FileHandler('app.log')  # Optional: Save to file for persistence
    ]
)
logger = logging.getLogger(__name__)  # Define logger
# File paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, 'users.json')
QUESTIONS_FILE = os.path.join(BASE_DIR, 'questions.json')

# Load user data

# Load user data
def load_users():
    try:
        with open(USERS_FILE, 'r') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.error(f"{USERS_FILE} is not a dictionary: {data}")
            return {}
        # Validate and process user entries
        valid_users = {}
        for username, user in data.items():
            if not isinstance(user, dict):
                logger.warning(f"Invalid user entry for {username}: {user}")
                continue
            # Add username to user dict and convert IsManager
            user['username'] = username
            user['is_manager'] = user.get('IsManager', 'no').lower() == 'yes'
            valid_users[username] = user
        logger.debug(f"Loaded {len(valid_users)} valid users from {USERS_FILE}")
        return valid_users
    except FileNotFoundError:
        logger.error(f"Users file not found: {USERS_FILE}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {USERS_FILE}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error loading {USERS_FILE}: {e}")
        return {}

# In-memory storage
#questions = []
# Write questions to a JSON file
def write_questions_to_file(questions, file_path=QUESTIONS_FILE):
    try:
        with open(file_path, 'w') as f:
            json.dump(questions, f, indent=4)
        logger.debug(f"Wrote {len(questions)} questions to {file_path}")
    except PermissionError as e:
        logger.error(f"Permission denied writing to {file_path}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error writing to {file_path}: {e}")
        raise

def read_questions_from_file(file_path=QUESTIONS_FILE):
    try:
        with open(file_path, 'r') as f:
            questions = json.load(f)
        if not isinstance(questions, list):
            logger.error(f"{file_path} does not contain a JSON array")
            return []
        today = datetime.now().date()
        for q in questions:
            if not isinstance(q, dict):
                logger.warning(f"Invalid question format: {q}")
                continue
            if 'tags' not in q:
                q['tags'] = []

            if 'mngr_approval_received' not in q:
                q['mngr_approval_received'] = 'no'
            if 'status' not in q:
                q['status'] = 'Posted to dashboard' if q['mngr_approval_received'] == 'yes' else 'Waiting for manager approval'
            if 'Credits' not in q:
                q['Credits'] = 0
            if q.get('duedate'):
                try:
                    due_date = datetime.strptime(q['duedate'], '%Y-%m-%d').date()
                    q['expired'] = 'Yes' if due_date < today else 'No'
                except ValueError as e:
                    logger.warning(f"Invalid duedate format for question {q.get('id', 'unknown')}: {e}")
                    q['expired'] = 'No'
            else:
                q['expired'] = 'No'
        logger.debug(f"Read {len(questions)} questions from {file_path}")
        return questions
    except FileNotFoundError:
        logger.error(f"Questions file not found: {file_path}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {file_path}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return []
def update_user_credits():
    try:
        with open(USERS_FILE, 'r') as f:
            users = json.load(f)
        with open(QUESTIONS_FILE, 'r') as f:
            questions = json.load(f)

        for user in users.values():
            user['credits_available'] = 0

        for question in questions:
            if question.get('status') == 'Credits released':
                accepted_user = question.get('accepted_comment_user')
                if accepted_user and accepted_user in users:
                    users[accepted_user]['credits_available'] += question.get('Credits', 0)

        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=4)

        logger.info("User credits updated successfully at startup.")
    except Exception as e:
        logger.error(f"Failed to update user credits: {e}")

# Add this function near the other helper functions
def get_user_credits(username):
    try:
        questions = read_questions_from_file()
        return sum(q.get("Credits", 0) for q in questions
                   if q.get("accepted_comment_user") == username and q.get("status") == 'Credits released')
    except Exception as e:
        logger.error(f"Failed to calculate credits for {username}: {e}")
        return 0

@app.route('/accept_answer/<int:question_id>/<int:comment_id>', methods=['POST'])
def accept_answer(question_id, comment_id):
    questions = read_questions_from_file()
    users = load_users()

    for question in questions:
        if question['id'] == question_id:
            # Reset all comments
            for comment in question['comments']:
                comment['accepted'] = False

            # Set the new accepted comment
            for comment in question['comments']:
                if comment['id'] == comment_id:
                    comment['accepted'] = True
                    question['accepted_comment_user'] = comment['user']
                    break

            credits = question.get('Credits', 0)
            asker = question.get('asked_by')
            accepted_user = question.get('accepted_comment_user')

            if question.get('mngr_approval_required') == 'no':
                question['status'] = 'Credits released'
                question['comment_mngr_approval_received'] = 'yes'

                # ✅ Deduct from asker
                if asker in users:
                    users[asker]['credits_available'] = users[asker].get('credits_available', 0) - credits
                    if users[asker]['credits_available'] < 0:
                        users[asker]['credits_available'] = 0

                # ✅ Add to commenter
                if accepted_user and accepted_user in users:
                    users[accepted_user]['credits_available'] = users[accepted_user].get('credits_available', 0) + credits

                # Save updated users
                with open(USERS_FILE, 'w') as f:
                    json.dump(users, f, indent=4)
            else:
                question['status'] = 'Awaiting manager approval to start'
                question['comment_mngr_approval_received'] = 'no'
            break

    write_questions_to_file(questions)
    return jsonify({"success": True})



@app.route('/')
def home():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])

def login():
    #update_user_credits()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        users = load_users()
        user = users.get(username)
        if user and user.get('password') == password:
            session['username'] = username
            session['is_manager'] = user.get('is_manager', False)
            logger.debug(f"User {username} logged in, is_manager: {session['is_manager']}")
            return redirect(url_for('task_details'))
        else:
            flash('Invalid username or password')
            logger.warning(f"Failed login attempt for {username}")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/task_details')
def task_details():
    if 'username' not in session:
        logger.warning("Unauthorized access to task_details")
        return redirect(url_for('login'))

    questions = read_questions_from_file()
    users = load_users()
    username = session['username']
    is_manager = session.get('is_manager', False)
    for q in questions:
        for comment in q.get("comments", []):
            comment["user_credits"] = users.get(comment["user"], {}).get("credits_available", 0)

    # Get managed users
    managed_users = [u['username'] for u in users.values() if u.get('manager') == username] if is_manager else []

    # Enhanced pending questions logic
    if is_manager:
           pending_questions = [
        q for q in questions
        if (
            # Manager of the asker handles initial approval and sees outcome
            (q['asked_by'] in managed_users and q['status'] in [
                'Waiting for manager approval',
                'Posted to dashboard',
                'Manager rejected',
                'Ready to start work',
                'Work In Progress',
                'Work Completed. Sent for review',
                'Credits released'
            ]) or
            # Manager of the accepted_comment_user handles comment approval and sees outcome
            (q.get('accepted_comment_user') in managed_users and q['status'] in [
                'Awaiting manager approval to start',
                'Ready to start work',
                'Rejected permission to take this work',
                'Work In Progress',
                'Work Completed. Sent for review',
                'Credits released'
            ])
        )
    ]
    else:
        pending_questions = []

    # All questions = all non-rejected questions
    all_questions = [q for q in questions if q['status'] not in [
        'Waiting for manager approval',
        'Manager rejected'
    ]]

    # My questions = all questions asked by the logged-in user or accepted by them
    my_questions = [q for q in questions if q['asked_by'] == username or q.get('accepted_comment_user') == username]

    # Earned credits
    earned_credits = users.get(username, {}).get('credits_available', 0)


    logger.debug(f"Loaded {len(all_questions)} All Questions, {len(my_questions)} My Questions, {len(pending_questions)} Actions Pending for {username}")

    return render_template(
        'task_details.html',
        all_questions=all_questions,
        my_questions=my_questions,
        pending_questions=pending_questions,
        username=username,
        is_manager=is_manager,
        earned_credits=earned_credits
    )


@app.route('/add_comment/<int:question_id>', methods=['POST'])
def add_comment(question_id):
   # user = request.form['user']
    user = session.get('username')
    comment_text = request.form['comment']
    questions = read_questions_from_file()
    for question in questions:
        if question['id'] == question_id:
            # Ensure comments have unique IDs
            new_comment_id = max([c['id'] for c in question['comments']], default=0) + 1
            question['comments'].append({
                'id': new_comment_id,
                'user': user,
                'text': comment_text,
                'accepted': False
            })
            break

    write_questions_to_file(questions)  # Write questions to a JSON file
    return redirect(url_for('task_details'))

@app.route('/get_all_questions', methods=['GET'])
def get_all_questions():
    questions = read_questions_from_file()
    all_questions = [q for q in questions if q['status'] not in [
            'Waiting for manager approval',
            'Manager rejected'
        ]]
    logger.debug(f"Fetched {len(all_questions)} all questions")
    return jsonify({"success": True, "questions": all_questions})
@app.route('/add_question', methods=['GET', 'POST'])
def add_question():



    questions = read_questions_from_file()
    asked_by = session.get('username')
    users=load_users()
    earned_credits = users.get(asked_by, {}).get('credits_available', 0)
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        asked_by = session.get('username')
        date = request.form['duedate']
        team = request.form['team']
        date_posted = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mngr_approval_required ='yes' if request.form.get('mngr_approval_required') == 'on' else 'no'
        tags_raw = request.form.get('tags', '')
        tags = [tag.strip().lower() for tag in tags_raw.replace(',', ' ').split() if tag.strip()]


        questions = read_questions_from_file()

        new_question_id = max([q['id'] for q in questions], default=0) + 1
        credits = int(request.form.get('credits', 0)) if mngr_approval_required == 'no' else 0



        new_question = {
            'id': new_question_id,
            'title': title,
            'description': description,
            'asked_by': asked_by,
            'duedate': date,
            'team': team,
            'comments': [],
            'date_posted': date_posted,
            'mngr_approval_required': mngr_approval_required,
            'mngr_approval_received': 'no',
            'status': 'Waiting for manager approval' if mngr_approval_required == 'yes' else 'Posted to dashboard',
            'Credits': credits,
            "accepted_comment_user": None,
            "comment_mngr_approval_received": 'no',
            "tags": tags

        }

        questions.append(new_question)
        try:
            write_questions_to_file(questions)
            logger.info(f"New question {new_question_id} added by {asked_by}")
            return redirect(url_for('task_details'))
        except Exception as e:
            logger.error(f"Failed to save new question {new_question_id}: {e}")
            flash('Error saving question. Please try again.')
            return render_template('add_question.html')
        
        

    return render_template('add_question.html',earned_credits=earned_credits)
@app.route('/approve_question/<int:question_id>', methods=['POST'])
def approve_question(question_id):
    if 'username' not in session or not session.get('is_manager'):
        logger.warning(f"Unauthorized access attempt to approve question {question_id}")
        return jsonify({"success": False, "error": "Unauthorized: Must be a manager"}), 403

    try:
        data = request.get_json()
        credits = data.get('credits')
        if credits is None or not isinstance(credits, int) or credits < 0:
            logger.warning(f"Invalid credits value for question_id {question_id}: {credits}")
            return jsonify({"success": False, "error": "Invalid credits value: Must be a non-negative integer"}), 400
    except Exception as e:
        logger.error(f"Failed to parse request body for question_id {question_id}: {e}")
        return jsonify({"success": False, "error": "Invalid request format"}), 400

    questions = read_questions_from_file()
    for question in questions:
        if question['id'] == question_id:
            question['mngr_approval_received'] = 'yes'
            question['status'] = 'Posted to dashboard'
            question['Credits'] = credits
            logger.info(f"Question {question_id} approved by {session['username']} with {credits} credits")
            break
    else:
        logger.warning(f"Question ID {question_id} not found")
        return jsonify({"success": False, "error": "Question not found"}), 404

    try:
        write_questions_to_file(questions)
    except Exception as e:
        logger.error(f"Failed to write questions file after approving question {question_id}: {e}")
        return jsonify({"success": False, "error": "Failed to save changes"}), 500

    return jsonify({"success": True, "message": "Question approved successfully"})
@app.route('/reject_question/<int:question_id>', methods=['POST'])
def reject_question(question_id):
    if 'username' not in session or not session.get('is_manager'):
        logger.warning(f"Unauthorized access attempt to reject question {question_id}")
        return jsonify({"success": False, "error": "Unauthorized: Must be a manager"}), 403

    try:
        questions = read_questions_from_file()
    except Exception as e:
        logger.error(f"Failed to read questions for question_id {question_id}: {e}")
        return jsonify({"success": False, "error": f"Server error: Unable to load questions: {str(e)}"}), 500

    for question in questions:
        if question.get('id') == question_id:
            question['mngr_approval_received'] = 'no'
            question['status'] = 'Manager rejected'
            question['Credits'] = 0
            try:
                write_questions_to_file(questions)
                logger.info(f"Question {question_id} rejected by {session.get('username')}")
                return jsonify({"success": True})
            except Exception as e:
                logger.error(f"Failed to write questions for question_id {question_id}: {e}")
                return jsonify({"success": False, "error": f"Server error: Unable to save changes: {str(e)}"}), 500

    logger.warning(f"Question {question_id} not found")
    return jsonify({"success": False, "error": "Question not found"}), 404
@app.route('/get_pending_questions', methods=['GET'])
def get_pending_questions():
    if 'username' not in session or not session.get('is_manager', False):
        return jsonify({"success": False, "error": "Unauthorized: Must be a manager"}), 403

    questions = read_questions_from_file()
    users = load_users()
    username = session['username']
    managed_users = [u['username'] for u in users.values() if u.get('manager') == username]

    pending_questions = [
        q for q in questions
        if (
            # Manager of the asker handles initial approval and sees outcome
            (q['asked_by'] in managed_users and q['status'] in [
                'Waiting for manager approval',
                'Posted to dashboard',
                'Manager rejected',
                'Ready to start work',
                'Work In Progress',
                'Work Completed. Sent for review',
                'Credits released'
            ]) or
            # Manager of the accepted_comment_user handles comment approval and sees outcome
            (q.get('accepted_comment_user') in managed_users and q['status'] in [
                'Awaiting manager approval to start',
                'Ready to start work',
                'Rejected permission to take this work',
                'Work In Progress',
                'Work Completed. Sent for review',
                'Credits released'
            ])
        )
    ]

    logger.debug(f"Fetched {len(pending_questions)} pending+historical questions for {username}")
    return jsonify({"success": True, "questions": pending_questions})
@app.route('/questions', methods=['GET'])
def get_questions():
    questions = read_questions_from_file()
    return jsonify(questions)
@app.route('/approve_comment/<int:question_id>', methods=['POST'])
def approve_comment(question_id):
    if 'username' not in session or not session.get('is_manager'):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    questions = read_questions_from_file()
    for question in questions:
        if question['id'] == question_id:
            # Only allow if status is appropriate
            if question.get('status') == 'Awaiting manager approval to start':
                question['status'] = 'Ready to start work'
                question['comment_mngr_approval_received'] = 'yes'
                write_questions_to_file(questions)
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "error": "Invalid status"}), 400

    return jsonify({"success": False, "error": "Question not found"}), 404
@app.route('/reject_comment/<int:question_id>', methods=['POST'])
def reject_comment(question_id):
    if 'username' not in session or not session.get('is_manager'):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    questions = read_questions_from_file()
    for question in questions:
        if question['id'] == question_id:
            if question.get('status') == 'Awaiting manager approval to start':
                question['status'] = 'Rejected permission to take this work'
                question['comment_mngr_approval_received'] = 'no'
                write_questions_to_file(questions)
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "error": "Invalid status"}), 400

    return jsonify({"success": False, "error": "Question not found"}), 404
@app.route('/start_work/<int:question_id>', methods=['POST'])
def start_work(question_id):
    if 'username' not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    questions = read_questions_from_file()
    for question in questions:
        if question['id'] == question_id:
            if question['status'].lower().strip() == 'ready to start work':
                question['status'] = 'Work In Progress'
                write_questions_to_file(questions)
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "error": "Invalid status"}), 400

    return jsonify({"success": False, "error": "Question not found"}), 404

@app.route('/mark_completion/<int:question_id>', methods=['POST'])
def mark_completion(question_id):
    if 'username' not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    username = session['username']
    questions = read_questions_from_file()
    for question in questions:
        if question['id'] == question_id:
            if question.get('accepted_comment_user') == username and question['status'] == 'Work In Progress':
                question['status'] = 'Work Completed. Sent for review'
                write_questions_to_file(questions)
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "error": "Not authorized or invalid status"}), 400

    return jsonify({"success": False, "error": "Question not found"}), 404

@app.route('/accept_work/<int:question_id>', methods=['POST'])
def accept_work(question_id):
    if 'username' not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    username = session['username']
    questions = read_questions_from_file()
    users = load_users()

    for question in questions:
        if question['id'] == question_id:
            if question['asked_by'] == username and question['status'] == 'Work Completed. Sent for review':
                question['status'] = 'Credits released'

                accepted_user = question.get('accepted_comment_user')
                credits = question.get('Credits', 0)

                # ✅ Add credits to commenter
                if accepted_user and accepted_user in users:
                    users[accepted_user]['credits_available'] = users[accepted_user].get('credits_available', 0) + credits

                # ✅ Deduct credits from asker
                if username in users and question['mngr_approval_required']=='no':
                    users[username]['credits_available'] = users[username].get('credits_available', 0) - credits
                    if users[username]['credits_available'] < 0:
                        users[username]['credits_available'] = 0  # Prevent negative balance

                # Save updated users
                with open(USERS_FILE, 'w') as f:
                    json.dump(users, f, indent=4)

                write_questions_to_file(questions)
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "error": "Not authorized or invalid status"}), 400

    return jsonify({"success": False, "error": "Question not found"}), 404

@app.route('/get_credits', methods=['GET'])
def get_credits():
    if 'username' not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 403
    username = session['username']
    users = load_users()
    credits = users.get(username, {}).get('credits_available', 0)
    return jsonify({"success": True, "credits": credits})
@app.route('/get_user_credits_map', methods=['GET'])
def get_user_credits_map():
    users = load_users()
    credits_map = {u: data.get('credits_available', 0) for u, data in users.items()}
    return jsonify({"success": True, "credits": credits_map})

@app.route('/get_question/<int:question_id>', methods=['GET'])
def get_question(question_id):
    questions = read_questions_from_file()
    question = next((q for q in questions if q['id'] == question_id), None)
    if question:
        return jsonify({"success": True, "question": question})
    else:
        return jsonify({"success": False, "error": "Question not found"}), 404


if __name__ == '__main__':
    app.run()