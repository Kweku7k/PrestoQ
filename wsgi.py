from app import app as application

if __name__ == "__main__":
    application.run(port=5000,debug=True, host="0.0.0.0")