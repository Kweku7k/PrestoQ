from datetime import datetime
from app import db

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
