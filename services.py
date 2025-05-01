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
