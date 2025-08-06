import os
from dotenv import load_dotenv
from pymongo import MongoClient, TEXT
from openai import OpenAI

# Load environment variables
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# MongoDB setup
client = MongoClient(MONGO_URI)
db = client["vossdb"]
memory_col = db["memory"]

# OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# 🔍 Ensure fallback text index
def setup_vector_index():
    print("🔍 Setting up text index for memory...")
    memory_col.create_index([("content", TEXT), ("tone", TEXT), ("username", TEXT)])

# 🧠 Get embedding for a given text
def get_embedding(text):
    try:
        response = openai_client.embeddings.create(
            input=[text],
            model="text-embedding-ada-002"
        )
        return response.data[0].embedding
    except Exception as e:
        print("❌ Error creating embedding:\n", e)
        return None

# 🗂️ Store message + embedding
def store_embedding(username, content, tone="neutral", chat_id=None):
    vector = get_embedding(content)
    if not vector:
        print("❌ Embedding generation failed.")
        return

    try:
        memory_col.insert_one({
            "username": username,
            "content": content,
            "embedding": vector,
            "tone": tone,
            "chat_id": chat_id
        })
        print(f"✅ Memory stored for {username}")
    except Exception as e:
        print("❌ Error storing embedding:", e)

# 🔎 Semantic memory search
def search_user_memory(username, query, top_k=3):
    query_vector = get_embedding(query)
    if not query_vector:
        print("❌ Failed to generate embedding for query")
        return []

    try:
        pipeline = [
            {
                "$vectorSearch": {
                    "queryVector": query_vector,
                    "path": "embedding",
                    "numCandidates": 100,
                    "limit": top_k,
                    "index": "default",  # ensure your MongoDB Atlas vector index is named "default"
                }
            },
            {"$match": {"username": username}}
        ]
        results = list(memory_col.aggregate(pipeline))
        return [r["content"] for r in results]
    except Exception as e:
        print("❌ Memory search error:\n", e)
        return []
