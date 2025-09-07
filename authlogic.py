import re
# from app import db
import jwt
from services import create_response


def handle_phone_verification(session_id, user_message, session_budgets):
    """Handle phone number verification and determine next steps"""
    # from app import User
    from models import User
    
    
    print("Processing phone number verification")
    clean_message = user_message.replace(" ", "").replace("-", "")
    print(f"Formatted phone number: {clean_message}")
    
    # Check if it looks like a phone number
    if not re.match(r'^\+\d{9,15}$', clean_message):   
        print("Invalid phone number format")
        if not clean_message.startswith("+"):
            return create_response("❌ Phone Number should be in format: +233", "PENDING_PHONE_NUMBER")
        return create_response("❌ Invalid phone number, please try again", "PENDING_PHONE_NUMBER")
    
    print("Looking up user by phone number")
    # Import here to avoid circular imports
    user = User.query.filter_by(phone_number=clean_message).first()
    
    if user is None:
        print("User not found - starting new user registration")
        # Store the phone number and move to name collection
        session_budgets[session_id]['phone_number'] = clean_message
        session_budgets[session_id]['status'] = "PENDING_NAME"
        return create_response("Great! I need to create an account for you. What's your full name?", "PENDING_NAME")
    
    # Existing user - log them in
    session_budgets[session_id]['user'] = user
    session_budgets[session_id]['status'] = "LOGGED_IN"
    return create_response(f"Welcome back, {user.username}!", "LOGGED_IN")

def handle_name_input(session_id, user_message, session_budgets):
    """Process user's name input during registration"""
    print("Processing name input")
    if len(user_message.strip()) < 2:
        return create_response("Please enter a valid name (at least 2 characters).", "PENDING_NAME")
    
    # Store the name and move to PIN creation
    session_budgets[session_id]['name'] = user_message.strip()
    session_budgets[session_id]['status'] = "PENDING_PIN_CREATION"
    return create_response(f"Thanks {user_message}! Please create a 4-digit PIN to secure your account.", "PENDING_PIN_CREATION")

def handle_pin_creation(session_id, user_message, session_budgets, JWT_SECRET, JWT_ALGORITHM):
    """Process PIN creation for new users"""
    print("Processing PIN creation")
    import bcrypt
    from datetime import datetime, timedelta
    import jwt
    
    # Validate PIN format (4 digits)
    if not re.match(r'^\d{4}$', user_message.strip()):
        return create_response("Your PIN must be exactly 4 digits. Please try again.", "PENDING_PIN_CREATION")
    
    # Create the new user
    try:
        phone_number = session_budgets[session_id]['phone_number']
        name = session_budgets[session_id]['name']
        pin = user_message.strip()
        
        # Hash the PIN before storing
        hashed_pin = bcrypt.hashpw(pin.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        from app import User  # Import here to avoid circular imports
        new_user = User(
            phone_number=phone_number,
            username=name,
            pin=hashed_pin,
            created_at=datetime.now()
        )
        
        db.session.add(new_user)
        db.session.commit()
        print(f"Created new user: {name} with phone {phone_number}")
        
        # Send welcome email (if email is available)
        # send_welcome_email(name, "user@example.com")
        
        # Generate JWT token
        token = jwt.encode({
            'username': name,
            'phone_number': phone_number,
            'exp': datetime.now() + timedelta(days=30)
        }, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        # Update session
        session_budgets[session_id]['user'] = new_user
        session_budgets[session_id]['status'] = "LOGGED_IN"
        session_budgets[session_id]['pending'] = False
        
        return create_response(f"✅ Account created successfully! Welcome to PrestoQ, {name}!", "LOGGED_IN", token)
    
    except Exception as e:
        print(f"Error creating user: {str(e)}")
        return create_response("Error creating your account. Please try again later.", "ERROR")

def handle_pin_verification(session_id, user_message, session_budgets, JWT_SECRET, JWT_ALGORITHM):
    """Verify PIN for existing users"""
    print("Verifying PIN")
    import bcrypt
    from datetime import datetime, timedelta
    import jwt
    
    user = session_budgets[session_id]['user']
    
    # Verify PIN
    if bcrypt.checkpw(user_message.strip().encode('utf-8'), user.pin.encode('utf-8')):
        print("PIN verified successfully")
        
        # Generate JWT token
        token = jwt.encode({
            'username': user.username,
            'phone_number': user.phone_number,
            'exp': datetime.now() + timedelta(days=30)
        }, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        # Update session
        session_budgets[session_id]['status'] = "LOGGED_IN"
        session_budgets[session_id]['pending'] = False
        
        return create_response(f"Welcome back, {user.username}!", "LOGGED_IN", token)
    else:
        print("Invalid PIN")
        return create_response("❌ Invalid PIN. Please try again.", "PENDING_PIN")

def handle_payment_confirmation(session_id, user_message, session_budgets):
    """Process payment confirmation"""
    print("Processing payment confirmation")
    if "yes" in user_message.lower() and "pending_transfer" in session_budgets.get(session_id, {}):
        print("User confirmed payment")
        tx = session_budgets[session_id]["pending_transfer"]
        
        payoutId = session_budgets[session_id]['pending_payout']['id']
        print(f"Confirming payout ID: {payoutId}")
        import services
        response = services.confirm_payout(payoutId)
        
        if response:
            print("Payment confirmed successfully")
            session_budgets[session_id].pop("pending_transfer", None)
            return create_response(f"✅ Sent GHC {tx['amount']:.2f} to {tx['phone_number']} for \"{tx['reference']}\".")
        else:
            print("Payment confirmation failed")
            return create_response("❌ Something went wrong while trying to send the money. Please try again later.")


def check_token(session_budgets, session_id, JWT_SECRET, JWT_ALGORITHM, token):
    print("Processing token")
    try:
        # Verify the token
        print("Decoding JWT token")
        decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = decoded.get('username')
        phone_number = decoded.get('phone_number')
        print(f"Decoded token: username={username}, phone_number={phone_number}")
        
        # Find the user in the database
        user = None
        if phone_number:
            print(f"Looking up user by phone number: {phone_number}")
            user = User.query.filter_by(phone_number=phone_number).first()
        elif username:
            print(f"Looking up user by username: {username}")
            user = User.query.filter_by(username=username).first()
            
        if user:
            print(f"Found user: {user.username}")
            # User is authenticated via JWT
            if session_budgets.get(session_id, None) is None:
                print("Creating new session budget")
                session_budgets[session_id] = {
                    "status": "LOGGED_IN",
                    "pending": False,
                    "user": user
                }
            elif session_budgets[session_id].get('status') not in ["LOGGED_IN", "PENDING_PAYMENT_CONFIRMATION"]:
                print("Updating existing session budget")
                # Only override status if it's not already in a special state
                session_budgets[session_id]['status'] = "LOGGED_IN"
                session_budgets[session_id]['pending'] = False
                session_budgets[session_id]['user'] = user
        
    except Exception as e:
        print(f"Token verification error: {str(e)}")
        # Token is invalid, continue with normal flow
        pass
