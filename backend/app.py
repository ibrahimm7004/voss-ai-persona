from flask import Flask, request, session, jsonify
from flask_cors import CORS
from bson import ObjectId
from datetime import timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import os

from db import users_col, chats_col
from chat import chat_bp
from memory import setup_vector_index

# Load .env
load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True)

# Session config
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")
app.permanent_session_lifetime = timedelta(days=7)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = False  # Set to True in production

# Register chat blueprint
app.register_blueprint(chat_bp)

# Initialize memory vector search (OpenAI embeddings + Mongo index)
setup_vector_index()

# Serialize user doc for client
def serialize_user(user_doc):
    return {
        "id": str(user_doc["_id"]),
        "username": user_doc["username"],
        "age": user_doc.get("profile", {}).get("age", ""),
        "gender": user_doc.get("profile", {}).get("gender", ""),
        "personality": user_doc.get("profile", {}).get("personality", ""),
        "tone": user_doc.get("profile", {}).get("tone", "reflective"),
        "custom": user_doc.get("profile", {}).get("custom", ""),
        "chat_ids": user_doc.get("chat_ids", []),
        "name": user_doc["username"]
    }

@app.route("/")
def home():
    return jsonify({"status": "VOSS API Active"}), 200

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("name", "").strip().lower()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Missing username or password"}), 400

    if users_col.find_one({"username": username}):
        return jsonify({"error": "Username already exists"}), 400

    hashed_pw = generate_password_hash(password)
    user_id = users_col.insert_one({
        "username": username,
        "password": hashed_pw,
        "profile": {
            "age": data.get("age"),
            "gender": data.get("gender"),
            "personality": data.get("personality"),
            "tone": data.get("tone", "reflective"),
            "custom": data.get("custom")
        },
        "chat_ids": []
    }).inserted_id

    session.permanent = True
    session["user_id"] = str(user_id)

    user = users_col.find_one({"_id": user_id})
    return jsonify({
        "user": serialize_user(user),
        "greeting": f"Welcome, {username}!"
    }), 200

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("name", "").strip().lower()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Missing username or password"}), 400

    user = users_col.find_one({"username": username})
    if not user or not check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid credentials"}), 401

    session.permanent = True
    session["user_id"] = str(user["_id"])

    return jsonify({
        "user": serialize_user(user),
        "message": "Login successful"
    }), 200

@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return jsonify({"message": "Logged out"}), 200

@app.route("/session", methods=["GET"])
def get_session():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"user": None}), 200

    user = users_col.find_one({"_id": ObjectId(user_id)})
    if not user:
        return jsonify({"user": None}), 200

    return jsonify({"user": serialize_user(user)}), 200

@app.route("/users", methods=["GET"])
def list_users():
    users = users_col.find()
    return jsonify([
        {
            "name": u["username"],
            "tone": u.get("profile", {}).get("tone", "reflective"),
            "custom": u.get("profile", {}).get("custom", "")
        } for u in users
    ])

# Handle 404/500 cleanly
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Route not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500

@app.route('/lore-act', methods=['POST'])
def update_lore_act():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated."}), 401

    user_id = session["user_id"]
    new_act = request.json.get("act")
    if new_act not in ["Act I – The Wound", "Act II – The Reckoning", "Act III – The Return"]:
        return jsonify({"error": "Invalid act"}), 400

    users_col.update_one({"_id": ObjectId(user_id)}, {"$set": {"act": new_act}})
    return jsonify({"msg": f"Lore act set to {new_act}."})


if __name__ == "__main__":
    print("🚀 Server running at http://localhost:5000")
    app.run(debug=True)
