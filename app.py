from collections import defaultdict
from datetime import datetime
import re
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os

# from tenacity import retry
from flask import render_template

app = Flask(__name__)
CORS(app)

# Set your API key
api_key = os.getenv("OPENAI_API_KEY")  # or hardcode it for now

client = OpenAI(
    api_key = os.getenv("OPENAI_API_KEY"),
)

chat_sessions = defaultdict(list)
session_budgets = {}
question_stages = {}  # session_id: int
user_reflections = {}  # session_id: list of user answers

# At the top with your other global variables
shopping_lists = defaultdict(list)  # session_id: [(item, estimated_cost)]


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
    return sum(amount for _, amount in past_transactions)

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
    return render_template('index.html')


@app.route('/chat', methods=['POST'])
def chat():
    
    data = request.get_json()
    user_message = data.get("message", "")
    session_id = data.get("session_id", "")
    budget = data.get("budget", "")
    user_reflections[session_id] = []
    
    if not session_id or not user_message:
        return jsonify({"error": "Both 'session_id' and 'message' are required."}), 400

      # Set budget if provided and not already set
    if budget is not None:
        session_budgets[session_id] = float(budget)
        
    current_budget = session_budgets.get(session_id)
    total_spent_amount = total_spent()
    budget_context = (
        f"You have a budget of Ghc{current_budget:.2f}."
        if current_budget is not None
        else "No budget has been set."
    )
    
    # THE CODE BELOW IS REDUNDANT
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
                If it's within budget, give mild approval but still add a lesson or warning.
                Use common expressions and Nigerian/Ghanaian slang where appropriate, but keep it clear and friendly.
                Ask one clarifying question at a time before giving advice.
                You can help manage a shopping list. Commands available:
                - To add: "Add [item] to my shopping list"
                - To view: "Show my shopping list"
                - To clear: "Clear my shopping list"
                Current shopping list status:{shopping_list_context}
                """
    #         "content": (
    #     "You're a smart AI financial assistant that talks like an african parent "
    #     "When users ask about making a purchase, don't give your opinion right away. "
    #     # "Instead, ask 2-3 helpful questions that make them reflect on the purchase. "
    #     "Ask the user what they think about the purchase themselves. "
    #     "Then, after their answers, provide thoughtful advice based on their budget and past spending."
    #     "Before you provide advice request an average amount of the product"
    # )
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

    # # Handle cases where no purchase amount is mentioned
    # if purchase_amount is None:
    #     return jsonify({
    #         "response": "I didn't catch the amount you're considering for this purchase. Could you let me know how much it would cost?"
    #     })

    # Check if the purchase exceeds the budget by more than 20%
    # if purchase_amount and current_budget is not None and purchase_amount > current_budget * 1.2:
    #     return jsonify({
    #         "response": f"Ei! This purchase of ${purchase_amount} is way over your budget of ${current_budget:.2f}. "
    #                     "Are you sure about this? You might want to reconsider."
    #     })
        
    # stage = question_stages.get(session_id, 0)

    # # Save user reply from previous question
    # if stage > 0 and stage <= 3:
    #     user_reflections[session_id].append(user_message)

    # # Add user message to conversation
    # chat_sessions[session_id].append({"role": "user", "content": user_message})

    # # Ask next question or provide final advice
    # questions = [
    #     "Okay, lets think about it🧠\n\nWould you say this is a need or a want?",
    #     "Do you already own something similar that works fine?",
    #     "Are there any upcoming expenses that might affect this decision?"
    # ]

    # if stage < 3:
    #     next_question = questions[stage]
    #     question_stages[session_id] += 1
    #     return jsonify({"response": next_question})
    # else:
    #     # All questions answered, provide advice
    #     reflections = "\n".join([
    #         f"Q{i+1}: {questions[i]}\nA: {ans}"
    #         for i, ans in enumerate(user_reflections[session_id])
    #     ])
    #     chat_sessions[session_id].append({
    #         "role": "user",
    #         "content": f"Here are my reflections:\n{reflections}\n\n{budget_context}"
    #     })


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

    print(completion.choices[0].message.content)
    return jsonify({"response": completion.choices[0].message.content})

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')