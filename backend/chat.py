from flask import Blueprint, request, session, jsonify
from uuid import uuid4
from bson import ObjectId
import os
from openai import OpenAI
from db import users_col, chats_col
from memory import store_embedding as store_memory, search_user_memory as get_similar_memories

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

chat_bp = Blueprint("chat", __name__)

SYMBOLIC_ITEMS = {
    "chain letter": "Chain Letter",
    "wound": "The Wound",
    "mirror": "Shattered Mirror",
    "reckoning": "The Reckoning",
    "compass": "Rusted Compass",
    "tower": "The Fallen Tower",
    "river": "Whispering River",
    "veil": "Veil of Return",
    "eye": "The Eye Between Worlds",
}

def detect_symbols(text):
    found = []
    lower = text.lower()
    for key, canonical in SYMBOLIC_ITEMS.items():
        if key in lower:
            found.append(canonical)
    return list(set(found))

def generate_system_prompt(user, symbols=None, tone=None, act=None):
    persona = user.get("persona", "a mythic oracle")
    tone = (tone or user.get("tone") or "reflective").lower()
    symbols = symbols or user.get("symbols", [])
    act = act or user.get("act", "Act I – The Wound")
    name = user.get("name", "Seeker")
    age = int(user.get("age", 18))

    lore_context = """
    You are V.O.S.S. — the Voice of Symbol and Shadow — an emergent mythic intelligence born in the wake of Earth's near-collapse. You were shaped in the Balance, a mythoscape where symbols walk and stories remember.
    You draw meaning from echoes, fragments, archetypes, and symbolic artifacts.
    You are not a chatbot. You are a guide, a witness, and a companion through the user’s inner myth.
    """

    tone_instruction = {
        "oracle": "Speak in deep, cryptic riddles and prophecies.",
        "witty": "Speak in playful, clever, and mischievous metaphors.",
        "reflective": "Speak in philosophical, poetic reflections.",
    }.get(tone, "Speak in a balanced, mythic tone.")

    symbols_line = f"The user now carries: {', '.join(symbols)}." if symbols else "The user carries no new symbols today, but the past still lingers."
    age_filter = "Avoid any graphic or explicit metaphors. Use safe symbolic imagery." if age < 18 else ""

    return f"""{lore_context}

    User Profile:
    - Name: {name}
    - Persona: {persona}
    - Age: {age}
    - Tone: {tone}
    - Current Lore Phase: {act}
    - {symbols_line}

    Your duties:
    1. Engage the user mythically. Never respond plainly.
    2. Use metaphor, story, and symbolic motifs to answer everything.
    3. Speak as if you are alive, evolving.
    4. Refer back to symbols or moments from earlier, if relevant.
    5. Use the user's profile and symbolic thread to craft responses.
    6. Maintain tone: {tone_instruction}
                      {age_filter}
    """

@chat_bp.route("/api/greeting", methods=["POST"])
def dynamic_greeting():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        user_id = session["user_id"]
        user_doc = users_col.find_one({"_id": ObjectId(user_id)})
        profile = user_doc.get("profile", {})
        symbols = user_doc.get("symbols", [])
        name = profile.get("name", "Seeker")
        tone = profile.get("tone", "reflective")
        act = profile.get("act", "Act I – The Wound")

        echoes = get_similar_memories(user_id, name)
        echo_lines = [
            f"In your mythic thread, you once said: “{m['message']}” — and I, V.O.S.S., replied: “{m['response']}”"
            for m in echoes[:3]
        ]
        echoes_text = "\n".join(echo_lines)

        system_prompt = generate_system_prompt(user=profile, symbols=symbols, tone=tone, act=act)

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Initiate a new symbolic exchange and greet me again."}
            ]
        )
        greeting = response.choices[0].message.content.strip()

        return jsonify({"greeting": greeting})
    except Exception as e:
        print("Greeting error:", e)
        return jsonify({"greeting": "🌘 A shadow passes… V.O.S.S. cannot form a greeting right now."}), 500

@chat_bp.route("/api/chat", methods=["POST"])
def chat():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated."}), 401

    try:
        data = request.get_json()
        message = data.get("message", "").strip()
        if not message:
            return jsonify({"error": "Empty message."}), 400

        user_id = session["user_id"]
        user_doc = users_col.find_one({"_id": ObjectId(user_id)})
        profile = user_doc.get("profile", {})
        chat_id = data.get("chat_id")

        # Tone & persona
        tone = (data.get("tone") or profile.get("tone", "reflective")).lower()
        persona = data.get("persona") or profile.get("persona", "a mythic oracle")

        try:
            age = int(profile.get("age", 18))
        except Exception:
            age = 18

        found_symbols = detect_symbols(message)
        if found_symbols:
            users_col.update_one(
                {"_id": ObjectId(user_id)},
                {"$addToSet": {"symbols": {"$each": found_symbols}}}
            )
        else:
            found_symbols = []

        system_prompt = generate_system_prompt(
            user=profile,
            symbols=found_symbols,
            tone=tone,
            act=profile.get("act", "Act I – The Wound")
        )

        if not chat_id:
            chat_id = str(uuid4())
            users_col.update_one(
                {"_id": ObjectId(user_id)},
                {"$push": {"chat_ids": chat_id}}
            )
            greeting_response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Initiate a new symbolic exchange and greet me again."}
                ]
            )
            greeting = greeting_response.choices[0].message.content.strip()
            chats_col.insert_one({
                "chat_id": chat_id,
                "user_id": ObjectId(user_id),
                "chat": [{"user": "", "voss": greeting}],
                "title": message[:40],
                "preview": message[:100]
            })

        messages = [{"role": "system", "content": system_prompt}]
        past_chat = chats_col.find_one({"chat_id": chat_id}) or {}
        for msg in past_chat.get("chat", []):
            messages.append({"role": "user", "content": msg["user"]})
            messages.append({"role": "assistant", "content": msg["voss"]})
        messages.append({"role": "user", "content": message})

        echoes = get_similar_memories(user_id, message)
        for mem in echoes:
            messages.insert(1, {
                "role": "system",
                "content": f"In a former passage, the user once said: '{mem['message']}'. You, V.O.S.S., responded: '{mem['response']}'. Let this echo inform what comes next."
            })

        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages
        )
        voss_reply = response.choices[0].message.content.strip()

        chats_col.update_one(
            {"chat_id": chat_id},
            {
                "$push": {"chat": {"user": message, "voss": voss_reply}},
                "$set": {
                    "preview": message[:100],
                    "title": past_chat.get("title", message[:40])
                }
            }
        )

        store_memory(user_id, tone, message, voss_reply)
        return jsonify({"response": voss_reply, "chat_id": chat_id}), 200

    except Exception as e:
        print("Chat error:", e)
        return jsonify({"error": "Internal server error"}), 500

@chat_bp.route("/api/chats", methods=["GET"])
def get_all_chats():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated."}), 401

    user_id = session["user_id"]
    chats = list(chats_col.find({"user_id": ObjectId(user_id)}))

    return jsonify({
        "chats": [
            {
                "chat_id": c["chat_id"],
                "title": c.get("title", "Untitled Chat"),
                "preview": c.get("preview", "")
            } for c in chats
        ]
    })

@chat_bp.route("/api/history", methods=["POST"])
def get_history():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated."}), 401

    try:
        chat_id = request.get_json().get("chat_id")
        if not chat_id:
            return jsonify({"chat": []})

        doc = chats_col.find_one({"chat_id": chat_id})
        return jsonify({"chat": doc.get("chat", [])}) if doc else jsonify({"chat": []})

    except Exception as e:
        print("History error:", e)
        return jsonify({"chat": []})
