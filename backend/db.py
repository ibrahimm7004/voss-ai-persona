from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["izzah"]

users_col = db["users"]
chats_col = db["chats"]
memory_col = db["memories"] 
