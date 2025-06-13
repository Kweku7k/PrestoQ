from collections import defaultdict
from datetime import datetime, timedelta
import pprint
import re
import json
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import jwt
from openai import OpenAI
import os
# import jwt
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
        'exp': datetime.now() + timedelta(hours=24)
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
    token = data.get("token", "")  # Get token from request JSON
    user_reflections[session_id] = []
    
    print(f"session_id: {session_id}")
    
    if not session_id or not user_message:
        return jsonify({"error": "Both 'session_id' and 'message' are required."}), 400
    
    # Check for JWT token in the request data or headers
    if not token:
        token = request.headers.get('Authorization')
        # if token == "":
        #     session_budgets[session_id] = {
        #     "status":"PENDING_PHONE_NUMBER",
        #     "pending":True,
        #     "otp":1234
        # }
        
        # # send otp
        # return jsonify({
        #     "response": f"Hi, please give me your phone number so I log you in"
        # })
        
    if token:
        try:
            # Verify the token
            decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            username = decoded.get('username')
            phone_number = decoded.get('phone_number')
            
            # Find the user in the database
            user = None
            if phone_number:
                user = User.query.filter_by(phone_number=phone_number).first()
            elif username:
                user = User.query.filter_by(username=username).first()
                
            if user:
                # User is authenticated via JWT
                if session_budgets.get(session_id, None) is None:
                    session_budgets[session_id] = {
                        "status": "LOGGED_IN",
                        "pending": False,
                        "user": user
                    }
                elif session_budgets[session_id].get('status') not in ["LOGGED_IN", "PENDING_PAYMENT_CONFIRMATION"]:
                    # Only override status if it's not already in a special state
                    session_budgets[session_id]['status'] = "LOGGED_IN"
                    session_budgets[session_id]['pending'] = False
                    session_budgets[session_id]['user'] = user

        except Exception as e:
            print(f"Token verification error: {str(e)}")
            # Token is invalid, continue with normal flow
            pass
    
    # else:
        
    
    # check to see if a user is logged in, if not request phone number and send an otp for confirmation of user
    if session_budgets.get(session_id, None) is None:
        
        session_budgets[session_id] = {
            "status":"PENDING_PHONE_NUMBER",
            "pending":True,
            "otp":1234
        }
        
        # send otp
        return jsonify({
            "response": f"Hi, please give me your phone number so I log you in"
        })
        
    user_status = session_budgets.get(session_id, {}).get('status', None) 
    print("user_status")
    print("USER STATUS: " +user_status)
    print("SESSION BUDGETS: ")
    pprint.pprint(session_budgets)
        
    if session_budgets[session_id]['status'] == "PENDING_PHONE_NUMBER":
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
            
            session_budgets[session_id]['status'] = "PENDING_NAME"
            session_budgets[session_id]['phone_number'] = user_message
            return jsonify({
                "response": f"Hi! I am Mama Lizy, what is your name?"
            })
        session_budgets[session_id]['user'] = user
        
        session_budgets[session_id]['status'] = "PENDING_OTP"
        send_otp(user.phone_number)
        return jsonify({
                "response": f"Hi {user.username}, I just shot you an otp, please verify!"
            })
        
    if session_budgets[session_id]['status'] == "PENDING_NAME":
        # check if the phone number is correct
        user = User.query.filter_by(phone_number=session_budgets[session_id]['phone_number']).first()

        if user is not None:
            user.username = user_message
            db.session.commit()
            
        # Generate JWT token for persistence
        token = jwt.encode({
            'username': user_message,
            'phone_number': session_budgets[session_id]['phone_number'],
            'exp': datetime.utcnow() + datetime.timedelta(days=30)
        }, JWT_SECRET, algorithm=JWT_ALGORITHM)

        session_budgets[session_id]['status'] = "LOGGED_IN"
        session_budgets[session_id]['pending'] = False
        session_budgets[session_id]['user'] = user
        
        return jsonify({
            "response": f"✅ You're logged in",
            "token": token
        })
        
    if session_budgets[session_id]['status'] == "PENDING_OTP":
        # check if the otp is correct
        # check to see if the input is not null
        
        if int(user_message) == session_budgets[session_id]['otp']:
            user = session_budgets[session_id]['user']
            
            # Generate JWT token for persistence
            token = jwt.encode({
                'username': user.username,
                'phone_number': user.phone_number,
                'exp': datetime.now() + timedelta(days=30)
            }, JWT_SECRET, algorithm=JWT_ALGORITHM)
            
            session_budgets[session_id]['status'] = "LOGGED_IN"
            session_budgets[session_id]['pending'] = False
            
            return jsonify({
                "response": f"Heyyyy {user.username}, welcome back!",
                "token": token
            })
        else:
            return jsonify({
                "response": f"❌ Invalid OTP, please try again"
            })

      # Set budget if provided and not already set
      
    if session_budgets[session_id]['status'] == "PENDING_PAYMENT_CONFIRMATION":
        if "yes" in user_message.lower() and "pending_transfer" in session_budgets.get(session_id, {}):
            print("USER ENTERED YES")
            tx = session_budgets[session_id]["pending_transfer"]


            payoutId = session_budgets[session_id]['pending_payout']['id']
            response = services.confirm_payout(payoutId) #TODO: MAKE THIS PAYOUT CONFIRMATION
            # response = services.trigger_payment() #TODO: MAKE THIS PAYOUT CONFIRMATION

            if response:
                session_budgets[session_id].pop("pending_transfer", None)
                return jsonify({"response": f"✅ Sent GHC {tx['amount']:.2f} to {tx['phone_number']} for \"{tx['reference']}\"."})
            else:
                return jsonify({"response": "❌ Something went wrong while trying to send the money. Please try again later."})
    
   
    #SEND MONEY PATTERN!
    # send_money_pattern = re.search(r'send\s+(?:ghc)?\s?(\d+(?:\.\d{1,2})?)\s+to\s+(\d{10})\s*(?:for\s+(.*))?', user_message.lower())
    # if send_money_pattern: 
    #     amount = float(send_money_pattern.group(1))
    #     phone_number = send_money_pattern.group(2)
    #     reference = send_money_pattern.group(3) or "No reference"


    #     pending_transfer = {
    #             "phone_number": phone_number,
    #             "amount": amount,
    #             "reference": reference
    #         }
        
    #     # Store the pending transfer without overwriting the entire session
    #     session_budgets[session_id]["pending_transfer"] = pending_transfer
        
    #     # identify user by phone number
    #     name = services.momolookup(phone_number)
        
    #     # Get the current user from the session
    #     user = session_budgets[session_id].get('user')
    #     if not user:
    #         return jsonify({"response": "You need to be logged in to make a transfer."})
            
    #     payout = services.create_payout(pending_transfer, user)
        
    #     # add payout to session_budgets
    #     session_budgets[session_id]['pending_payout'] = payout['data']
    #     pprint.pprint(payout)
        
    #     # Update status to pending payment confirmation
    #     session_budgets[session_id]['status'] = "PENDING_PAYMENT_CONFIRMATION"
        
    #     return jsonify({
    #         "response": f"You're about to send GHC {amount:.2f} to {name} for \"{reference}\". Enter your pin so I proceed?"
    #     })
        
        
    # confirm transactionft
        
     
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

    # Define functions for GPT-4 to call
    tools = [
        {
            "type": "function",
            "function": {
                "name": "send_money",
                "description": "Send money to a recipient using their phone number",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "amount": {
                            "type": "number",
                            "description": "The amount of money to send in GHC"
                        },
                        "phone_number": {
                            "type": "string",
                            "description": "The recipient's phone number (10 digits)"
                        },
                        "reference": {
                            "type": "string",
                            "description": "The reason for sending money"
                        }
                    },
                    "required": ["amount", "phone_number"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "confirm_payout",
                "description": "Confirm a pending money transfer after PIN verification",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pin": {
                            "type": "string",
                            "description": "The user's PIN for confirming the transaction"
                        }
                    },
                    "required": ["pin"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "add_shopping_item",
                "description": "Add an item to the shopping list",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item": {
                            "type": "string",
                            "description": "The item to add to the shopping list"
                        },
                        "estimated_cost": {
                            "type": "number",
                            "description": "The estimated cost of the item in GHC"
                        }
                    },
                    "required": ["item"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "show_shopping_list",
                "description": "Show the current shopping list",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        }
    ]

    # Add user message to session history
    chat_sessions[session_id].append({"role": "user", "content": user_message})
    
    
    # # Check if there's a pending payment confirmation and the message might contain a PIN
    # if session_budgets[session_id].get('status') == "PENDING_PAYMENT_CONFIRMATION" and user_message.strip().isdigit():
    #     # Automatically invoke the confirm_payout function with the PIN
    #     pending_info = {
    #     "role": "system",
    #     "content": "There is a pending payment that needs confirmation. If the user has entered what appears to be a PIN (a numeric code), use the confirm_payout function with that PIN."
    #     }
    #     chat_sessions[session_id].append(pending_info)     
    if session_budgets[session_id].get('status') == "PENDING_PAYMENT_CONFIRMATION":
        pending_info = {
            "role": "system",
            "content": "There is a pending payment that needs confirmation. If the user has entered what appears to be a PIN (a numeric code), use the confirm_payout function with that PIN."
        }
        chat_sessions[session_id].append(pending_info)

    # Call the OpenAI API
    completion = client.chat.completions.create(
        model = "gpt-4",
        messages=chat_sessions[session_id],
        temperature=0.7,
        tools=tools,
        tool_choice="auto"
    )
    response_message = completion.choices[0].message

    # Remove the temporary context message if we added it
    if session_budgets[session_id].get('status') == "PENDING_PAYMENT_CONFIRMATION":
        # Remove the last system message if it was our pending info
        if len(chat_sessions[session_id]) > 0 and chat_sessions[session_id][-1]["role"] == "system":
            chat_sessions[session_id].pop()
        
    else:
        # Normal flow - call the OpenAI API
        
        pprint.pprint(chat_sessions[session_id])

        completion = client.chat.completions.create(
            model = "gpt-4",
            messages=chat_sessions[session_id],
            temperature=0.7,
            tools=tools,
            tool_choice="auto"
        )
        response_message = completion.choices[0].message
        
    def extract_tool_calls(msg):
        if not msg:
            return None
        try:
            if isinstance(msg, dict):
                return msg.get("tool_calls")
            return getattr(msg, "tool_calls", None)
        except Exception as e:
            print(f"Error extracting tool_calls: {e}")
            return None

    # tool_calls = extract_tool_calls(response_message)

    # print(tool_calls)

    try:
        print("Processing response message...")
        pprint.pprint(response_message)
        print(type(response_message))
        # response_message is now defined either from completion or directly for PIN handling
        
        
        # Check if the model wants to call a function
        # if hasattr(response_message, 'tool_calls') and response_message.tool_calls:
        # if tool_calls:
        if (hasattr(response_message, 'tool_calls') and response_message.tool_calls):
            print(f"Found tool calls: {len(response_message.tool_calls)}")
            # Process each function call
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                print(f"Processing function call: {function_name}")
                print(f"Function arguments: {function_args}")
                
                # Add the assistant's message to the conversation
                chat_sessions[session_id].append(response_message)
                
                # Handle different function calls
                if function_name == "send_money":
                    print("Handling send_money function")
                    amount = function_args.get("amount")
                    phone_number = function_args.get("phone_number")
                    reference = function_args.get("reference", "No reference")
                    
                    # Create pending transfer
                    pending_transfer = {
                        "phone_number": phone_number,
                        "amount": amount,
                        "reference": reference
                    }
                    print(f"Created pending transfer: {pending_transfer}")
                    
                    # Store the pending transfer
                    session_budgets[session_id]["pending_transfer"] = pending_transfer
                    
                    # Get recipient name
                    name = services.momolookup(phone_number)
                    print(f"Retrieved recipient name: {name}")
                    
                    pending_transfer['name'] = name
                                    
                    # Get the current user from the session
                    user = session_budgets[session_id].get('user')
                    if not user:
                        print("No user found in session")
                        return jsonify({"response": "You need to be logged in to make a transfer."})
                        
                    # Create payout
                    payout = services.create_payout(pending_transfer, user)
                    print(f"Created payout: {payout}")
                    
                    # Add payout to session_budgets
                    session_budgets[session_id]['pending_payout'] = payout['data']
                    
                    # Update status to pending payment confirmation
                    session_budgets[session_id]['status'] = "PENDING_PAYMENT_CONFIRMATION"
                    
                    # Add the function response to the conversation
                    function_response = f"You're about to send GHC {amount:.2f} to {name} for \"{reference}\". Enter your pin so I proceed?"
                    chat_sessions[session_id].append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": function_response
                    })
                    
                    return jsonify({"response": function_response, "status": session_budgets[session_id]['status']})
                    
                elif function_name == "add_shopping_item":
                    print("Handling add_shopping_item function")
                    item = function_args.get("item")
                    estimated_cost = function_args.get("estimated_cost")
                    
                    # Add to shopping list
                    add_to_shopping_list(session_id, item, estimated_cost)
                    print(f"Added item to shopping list: {item}, cost: {estimated_cost}")
                    
                    # Add the function response to the conversation
                    function_response = f"I've added {item} to your shopping list. Would you like to set an estimated cost for this item?"
                    chat_sessions[session_id].append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": function_response
                    })
                    
                    return jsonify({"response": function_response, "status": session_budgets[session_id].get('status', 'IDLE')})
                    
                elif function_name == "show_shopping_list":
                    print("Handling show_shopping_list function")
                    shopping_list = get_shopping_list(session_id)
                    if not shopping_list:
                        print("Shopping list is empty")
                        function_response = "Your shopping list is empty."
                        chat_sessions[session_id].append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": function_name,
                            "content": function_response
                        })
                        return jsonify({"response": function_response, "status": session_budgets[session_id].get('status', 'IDLE')})
                    
                    items_text = "\n".join([f"- {item['item']}: Ghc{item['estimated_cost']:.2f}" 
                                          for item in shopping_list])
                    total = calculate_list_total(session_id)
                    print(f"Shopping list items:\n{items_text}")
                    print(f"Total cost: {total}")
                    
                    function_response = f"Here's your shopping list:\n{items_text}\n\nTotal estimated cost: Ghc{total:.2f}"
                    
                    chat_sessions[session_id].append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": function_response
                    })
                    
                    return jsonify({"response": function_response, "status": session_budgets[session_id].get('status', 'IDLE')})
                    
                elif function_name == "confirm_payout":
                    print("Handling confirm_payout function")
                    pin = function_args.get("pin")
                    
                    # Check if there's a pending payout
                    if session_budgets[session_id].get('status') != "PENDING_PAYMENT_CONFIRMATION" or not session_budgets[session_id].get('pending_payout'):
                        print("No pending payout found")
                        function_response = "There is no pending transaction to confirm."
                        chat_sessions[session_id].append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": function_name,
                            "content": function_response
                        })
                        return jsonify({"response": function_response, "status": session_budgets[session_id].get('status', 'IDLE')})
                    
                    # Get the pending payout and user
                    pending_payout = session_budgets[session_id].get('pending_payout')
                    user = session_budgets[session_id].get('user')
                    print(f"Processing payout for user: {user}")
                    
                    # Process the payout with the PIN
                    result = services.confirm_payout(pending_payout, pin, user)
                    print(f"Payout confirmation result: {result}")
                    
                    if result.get('success') == True:
                        print("Transaction successful")
                        # Clear the pending state but keep user logged in
                        session_budgets[session_id]['status'] = "LOGGED_IN"
                        session_budgets[session_id]['pending_payout'] = None
                        session_budgets[session_id]['pending_transfer'] = None

                        
                        # Format the response
                        amount = pending_payout.get('amount')
                        recipient = pending_payout.get('recipient_name', 'the recipient')
                        reference = pending_payout.get('reference', 'No reference')
                        
                        function_response = f"Transaction successful! GHC {amount:.2f} has been sent to {recipient} for \"{reference}\"."
                    else:
                        print("Transaction failed")
                        function_response = f"Transaction failed: {result.get('message', 'Invalid PIN or transaction error.')}"
                    
                    chat_sessions[session_id].append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": function_response
                    })
                    
                    # return jsonify({"response": function_response})
                    return jsonify({"response": function_response, "status": session_budgets[session_id]['status']})

            
            # If we get here, no function was handled
            print("No matching function handler found")
            return jsonify({"response": "I'm not sure how to handle that request.", "status": session_budgets[session_id].get('status', 'IDLE')}), 200
        else:
            print("No tool calls found, returning direct response")
            # No function call, just return the response
            return jsonify({"response": response_message.content, "status": session_budgets[session_id].get('status', 'IDLE')}), 200
            
    except Exception as e:
        print(f"Error generating response: {str(e)}")
        return jsonify({"response": "I'm sorry, I'm having trouble responding right now. Please try again later.", "status": "ERROR"}), 500

import uuid

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')