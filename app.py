from collections import defaultdict
from datetime import datetime
import re
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from openai import OpenAI
import os
import jwt
import bcrypt
from functools import wraps
from flask_migrate import Migrate

import requests

from services import send_otp
import services

app = Flask(__name__)

# Initialize Flask-Migrate

# Initialize SQLAlchemy
CORS(app)

# Set your API key
api_key = os.getenv("OPENAI_API_KEY")  # or hardcode it for now
# db_uri = os.getenv("PG_DB_URL")  # or hardcode it for now
DATABASE_URI = os.getenv("Q_DATABASE_URI") 


client = OpenAI(
    api_key = os.getenv("OPENAI_API_KEY"),
)


chat_sessions = defaultdict(list)
session_budgets = {}
question_stages = {}  # session_id: int
user_reflections = {}  # session_id: list of user answers

# At the top with your other global variables
shopping_lists = defaultdict(list)  # session_id: [(item, estimated_cost)]


app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI
db = SQLAlchemy()
db.init_app(app)
migrate = Migrate(app, db)


class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80))
    pin = db.Column(db.String(120))
    phone_number = db.Column(db.String(15), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.now())
    transactions = db.relationship('Transaction', backref='user', lazy=True)
    shopping_lists = db.relationship('ShoppingList', backref='user', lazy=True)

class Transaction(db.Model):
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)  # 'send' or 'receive'
    recipient_phone = db.Column(db.String(15))
    reference = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.now())

class ShoppingList(db.Model):
    __tablename__ = 'shopping_lists'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now())
    items = db.relationship('ShoppingListItem', backref='shopping_list', lazy=True)

class ShoppingListItem(db.Model):
    __tablename__ = 'shopping_list_items'
    
    id = db.Column(db.Integer, primary_key=True)
    shopping_list_id = db.Column(db.Integer, db.ForeignKey('shopping_lists.id'), nullable=False)
    item = db.Column(db.String(100), nullable=False)
    estimated_cost = db.Column(db.Float)
    purchased = db.Column(db.Boolean, default=False)
    added_date = db.Column(db.DateTime, default=datetime.now())

past_transactions = [
    ("Bought coffee", 3.50),
    ("Uber ride", 12.00),
    ("Monthly subscription", 15.00),
    ("Groceries", 42.75),
    ("Pizza with friends", 20.00)
]

def transaction_summary():
    return "\n".join([f"{desc} - Ghc{amount:.2f}" for desc, amount in past_transactions])

def total_spent():
    return 0
    # return sum(amount for _, amount in past_transactions)

def add_to_shopping_list(session_id, item, estimated_cost=None):
    shopping_lists[session_id].append({
        'item': item,
        'estimated_cost': estimated_cost,
        'added_date': datetime.now(),
        'purchased': False
    })

def get_shopping_list(session_id):
    return shopping_lists[session_id]

def calculate_list_total(session_id):
    return sum(item['estimated_cost'] or 0 for item in shopping_lists[session_id])


@app.route('/', methods=['GET', 'POST'])
def index():
    return render_template('index.html', title="PrestoQ")

# @app.route('/auth', methods=['GET', 'POST'])
# def auth():


# Mock database for users
users_db = {}

# JWT config
JWT_SECRET = 'your-secret-key'
JWT_ALGORITHM = 'HS256'

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            current_user = users_db.get(data['username'])
        except:
            return jsonify({'message': 'Token is invalid'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

@app.route('/auth/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            return render_template('signup.html', error='Missing username or password')
            
        if username in users_db:
            return render_template('signup.html', error='Username already exists')
            
        # Hash password
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        # Store user
        users_db[username] = {
            'username': username,
            'password': hashed
        }
        
        return render_template('login.html', message='User created successfully')
        
    return render_template('signup.html')


@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'message': 'Missing username or password'}), 400
        
    user = users_db.get(username)
    if not user:
        return jsonify({'message': 'User not found'}), 404
        
    if not bcrypt.checkpw(password.encode('utf-8'), user['password']):
        return jsonify({'message': 'Invalid password'}), 401
        
    # Generate JWT token
    token = jwt.encode({
        'username': username,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    return jsonify({
        'message': 'Login successful',
        'token': token
    })    

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    return render_template('chat.html', title="PrestoQAI")

@app.route('/chat-backend', methods=['POST'])
def chat_backend():
    
    data = request.get_json()
    user_message = data.get("message", "")
    session_id = data.get("session_id", "")
    budget = data.get("budget", 0)
    user_reflections[session_id] = []
    
    if not session_id or not user_message:
        return jsonify({"error": "Both 'session_id' and 'message' are required."}), 400
    
    
    # check to see if a user is logged in, if not request phone number and send an otp for confirmation of user
    if session_budgets.get('user', None) is None:
        
        session_budgets['user'] = {
            "status":"PENDING_PHONE_NUMBER",
            "pending":True,
            "otp":1234
        }
        
        # send otp
        return jsonify({
            "response": f"Hi, please give me your phone number so I log you in"
        })
        
    user_status = session_budgets.get('user', {}).get('status', None) 
    print("user_status")
    print("USER STATUS: " +user_status)
        
    if session_budgets['user']['status'] == "PENDING_PHONE_NUMBER":
        # check if the phone number is correct
        # lets verify if this is an actual phone number
        user_message = user_message.replace(" ", "").replace("-", "")
        if not re.match(r'^\+\d{9,15}$', user_message):   
            
        #  check to see if there is a plus starting the phone number if not tell the user to start with a +
            if not user_message.startswith("+"):
                return jsonify({
                    "response": f"❌ Phone Number should be in format: +233"
                })

            return jsonify({
                "response": f"❌ Invalid phone number, please try again"
            })
        
        user = User.query.filter_by(phone_number=user_message).first()
        
        if user is None:
            
            # check if user already exists
            user = User.query.filter_by(username=user_message).first()
            
            new_user = User(phone_number=user_message, username="USER", pin="0000")
            db.session.add(new_user)
            db.session.commit()
            
            session_budgets['user']['status'] = "PENDING_NAME"
            session_budgets['user']['phone_number'] = user_message
            return jsonify({
                "response": f"Hi! I am Mama Lizy, what is your name?"
            })
        
        session_budgets['user']['status'] = "PENDING_OTP"
        send_otp(user.phone_number)
        return jsonify({
                "response": f"Hi {user.username}, I just shot you an otp, please verify!"
            })
        
    if session_budgets['user']['status'] == "PENDING_NAME":
        # check if the phone number is correct
        user = User.query.filter_by(phone_number=session_budgets['user']['phone_number']).first()

        if user is not None:
            user.username = user_message
            db.session.commit()

        session_budgets['user']['status'] = "LOGGED_IN"
        session_budgets['user']['pending'] = False
        return jsonify({
            "response": f"✅ You're logged in"
        })
        
    if session_budgets['user']['status'] == "PENDING_OTP":
        # check if the otp is correct
        if int(user_message) == session_budgets['user']['otp']:
            session_budgets['user']['status'] = "LOGGED_IN"
            session_budgets['user']['pending'] = False
            return jsonify({
                "response": f"Heyyyy" #LETS AUTOMATE THIS
            })
        else:
            return jsonify({
                "response": f"❌ Invalid OTP, please try again"
            })

      # Set budget if provided and not already set
      
    if session_budgets['user']['status'] == "PENDING_PAYMENT_CONFIRMATION":
        if "yes" in user_message.lower() and "pending_transfer" in session_budgets.get(session_id, {}):
            tx = session_budgets[session_id]["pending_transfer"]

            response = services.trigger_payment()

            if response:
                session_budgets[session_id].pop("pending_transfer", None)
                return jsonify({"response": f"✅ Sent GHC {tx['amount']:.2f} to {tx['phone_number']} for \"{tx['reference']}\"."})
            else:
                return jsonify({"response": "❌ Something went wrong while trying to send the money. Please try again later."})
    
   
    send_money_pattern = re.search(r'send\s+(?:ghc)?\s?(\d+(?:\.\d{1,2})?)\s+to\s+(\d{10})\s*(?:for\s+(.*))?', user_message.lower())
    if send_money_pattern:
        amount = float(send_money_pattern.group(1))
        phone_number = send_money_pattern.group(2)
        reference = send_money_pattern.group(3) or "No reference"

        # Save this data temporarily in session context
        session_budgets[session_id] = {
            "pending_transfer": {
                "phone_number": phone_number,
                "amount": amount,
                "reference": reference
            }
        }
        
        # identify user by phone number
        # name = "Nana Kweku Adumatta" #TODO: Update this guy!
        
        name = services.momolookup(phone_number)
        session_budgets['user']['status'] = "PENDING_PAYMENT_CONFIRMATION"
        
        
        return jsonify({
            "response": f"You're about to send GHC {amount:.2f} to {name} for \"{reference}\". Enter your pin so I proceed?"
        })
        
     
    # if budget is not None:
    #     session_budgets[session_id] = float(budget)
        
    # current_budget = session_budgets.get(session_id)['budget']
    total_spent_amount = total_spent()
    # budget_context = (
    #     f"You have a budget of Ghc{current_budget:.2f}."
    #     if current_budget is not None
    #     else "No budget has been set."
    # )
    
    # # THE CODE BELOW IS REDUNDANT
    # budget_context = (
    #     f"You have a budget of Ghc{current_budget:.2f} and have already spent Ghc{total_spent_amount:.2f}."
    #     if current_budget is not None
    #     else "No budget has been set."
    # )
    current_budget = None
    budget_context = (
    f"You have a budget of Ghc{current_budget:.2f} and have already spent Ghc{total_spent_amount:.2f}."
    if current_budget is not None
    else "No budget has been set."
    )

    # If new session, start with system + transaction context
    if len(chat_sessions[session_id]) == 0:
        question_stages[session_id] = 0

        chat_sessions[session_id].append({
            "role": "system",
            "content" : """
                You are an African parent who deeply cares about your child's financial well-being.
                Respond in a warm, firm, and very dramatic tone, often adding life lessons or subtle guilt to drive your point.
                Keep responses short, straight to the point, and expressive.
                If the user tries to spend above their budget, respond with a concerned or exasperated tone (e.g. “Ei!”, “Ah ah!”, "Herh") do not constrain to only these responses.
                Ask the average amount. If it's within budget, give approval by replying "Okay, who am I sending the money to?".
                Use common expressions and Nigerian/Ghanaian slang where appropriate, but keep it clear and friendly.
                """
            
        })
        
        chat_sessions[session_id].append({
            "role": "user",
            "content": f"My recent transactions are:\n{past_transactions}\n\n{budget_context}"
        })
        
    # Extract purchase amount from user message
    purchase_amount = None
    match = re.search(r'\$(\d+(?:\.\d{2})?)', user_message)
    if match:
        purchase_amount = float(match.group(1))


    # =========== REMINDERS ============
    
    # Add shopping list context to the conversation
    if len(chat_sessions[session_id]) == 0:
        shopping_list = get_shopping_list(session_id)
        shopping_list_context = ""
        if shopping_list:
            items_text = "\n".join([f"- {item['item']}: Ghc{item['estimated_cost']:.2f}" 
                                  for item in shopping_list])
            shopping_list_context = f"\nCurrent shopping list:\n{items_text}"
        
        chat_sessions[session_id].append({
            "role": "system",
            "content": f"""
                You are an African parent who deeply cares about your child's financial well-being.
                You can help manage a shopping list. Commands available:
                - To add: "Add [item] to my shopping list"
                - To view: "Show my shopping list"
                - To clear: "Clear my shopping list"
                Current shopping list status:{shopping_list_context}
                """
        })
    
    # Add logic to detect shopping list commands
    if "add" in user_message.lower() and "shopping list" in user_message.lower():
        # Extract item name using regex or simple string manipulation
        item_match = re.search(r"add (.*?) to my shopping list", user_message.lower())
        if item_match:
            item = item_match.group(1)
            add_to_shopping_list(session_id, item)
            return jsonify({"response": f"I've added {item} to your shopping list. Would you like to set an estimated cost for this item?"})
    
    elif "show" in user_message.lower() and "shopping list" in user_message.lower():
        shopping_list = get_shopping_list(session_id)
        if not shopping_list:
            return jsonify({"response": "Your shopping list is empty."})
        
        items_text = "\n".join([f"- {item['item']}: Ghc{item['estimated_cost']:.2f}" 
                              for item in shopping_list])
        total = calculate_list_total(session_id)
        return jsonify({"response": f"Here's your shopping list:\n{items_text}\n\nTotal estimated cost: Ghc{total:.2f}"})

    # ... (rest of your existing chat code)

    
    # ========= OPEN AI CALL =============

    # Add user message to session history
    chat_sessions[session_id].append({"role": "user", "content": user_message})

    completion = client.chat.completions.create(
    model = "gpt-3.5-turbo",
    messages=chat_sessions[session_id],
    temperature=0.7
    )

    try:
        print(completion.choices[0].message.content)
        return jsonify({"response": completion.choices[0].message.content}, theme="DARK")
    except Exception as e:
        print(f"Error generating response: {str(e)}")
        return jsonify({"response": "I'm sorry, I'm having trouble responding right now. Please try again later."}, theme="DARK"), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')