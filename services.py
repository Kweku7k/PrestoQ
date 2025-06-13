import pprint
from flask import jsonify
import requests

def send_otp(phone_number):
    token = "ftpxjx7wb23mumli"
    instance_id = "instance116864"
    url = f"https://api.ultramsg.com/{instance_id}/messages/chat"

    payload = {
        "token": token,
        "to": f"whatsapp:{phone_number}",
        "body": "Your OTP is 1234",
    }

    response = requests.post(url, data=payload)
    print(response.json())
    
    return response.json()

def send_email():
    pass

# Python is unable to parse the code provided. Please turn off Smart Send if you wish to always run line by line or explicitly select code to force run. See logs for more details

def momolookup(accountNumber):
    url = "https://prestoghana.com/authorizedCustomerLookup"
    
    payload = {
        "accountNumber": accountNumber,
        "bankCode": "300591"
    }
    
    response = requests.post(url, json=payload)
    print(response.json())
    return response.json()['data']['AccountName']

def trigger_payment():
    url = "https://prestoghana.com/korba"
    payload = {
        "appId":"PrestoSolutions", 
        "ref":"transactionId",
        "description":"description",
        "reference":"reimburse withdrawal",
        "paymentId":"manualTransaction", 
        "phone":"0545977791",
        "amount":1,
        "total":1,
        "recipient":"payment",
        "percentage":"3",
        "callbackUrl":"prestoghana.com",
        "firstName":"Kweku",
        "network":"MTN"
    }
    
    response = requests.post(url, json=payload)
    print(response.json())
    return response.json()

def create_payout(pending_transfer, user):
    print("""""user""""")
    print(user)
    body = {
        "username": user.username,
        "amount": pending_transfer['amount'],
        "name": "John Doe",
        "account": pending_transfer['phone_number'],
        "accountName":pending_transfer['name'],
        "accountNumber": pending_transfer['phone_number'],
        "accountType": 'MOMO',
        "network": "MTN",
        "bankCode": "MTN",
        "reference": pending_transfer['reference'],
        "api_key":"fb5d5ed44582a40e1befa33f848852c95eece4a87f81040da6abbe7adc06b071"
    }
    pprint.pprint(body)
    url = "https://prestoghana.com/api/payout"
    headers = {"x-api-key": "fb5d5ed44582a40e1befa33f848852c95eece4a87f81040da6abbe7adc06b071"}
    response = requests.post(url, json=body, headers=headers)
    return response.json()

def confirm_payout(payout, pin, user):
    print("payoutId")
    print(payout)
    
    payoutId = payout['id']
    # do authentication before this call ... I guess
    print("Confirming payout...")
    url = "https://prestoghana.com/api/firepayout/"+str(payoutId)
    print(f"Making request to URL: {url}")
    headers = {"x-api-key": "fb5d5ed44582a40e1befa33f848852c95eece4a87f81040da6abbe7adc06b071"}
    response = requests.post(url, headers=headers)
    print(f"Response received: {response.json()}")
    return response.json()

# Add this helper function at the top of your file
def create_response(message, status=None, token=None):
    """Create a standardized response with status and optional token"""
    response = {"response": message}
    
    # Always include the status if available
    if status:
        response["status"] = status
    
    # Include token if provided
    if token:
        response["token"] = token
        
    return jsonify(response)

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
