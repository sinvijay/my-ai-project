import os
import json
import hashlib
import gspread
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime
from fastapi.responses import FileResponse



# Load environment variables
load_dotenv()

# 1. Configure Gemini AI
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

# 2. Configure Google Sheets (Drive Database)
users_sheet = None
chat_sheet = None

try:
    google_creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if google_creds_json:
        creds_dict = json.loads(google_creds_json)
        gc = gspread.service_account_from_dict(creds_dict)
        doc = gc.open("MyLoginDatabase")

        # Get or create 'Users' Worksheet
        try:
            users_sheet = doc.worksheet("Users")
        except Exception:
            users_sheet = doc.sheet1
            users_sheet.update_title("Users")
        
        if not users_sheet.get_all_values():
            users_sheet.append_row(["Timestamp", "Username", "PasswordHash"])

        # Get or create 'ChatLogs' Worksheet
        try:
            chat_sheet = doc.worksheet("ChatLogs")
        except Exception:
            chat_sheet = doc.add_worksheet(title="ChatLogs", rows="1000", cols="4")
            chat_sheet.append_row(["Timestamp", "Username", "UserMessage", "BotResponse"])

        print("Successfully connected to Google Sheets database!")
    else:
        print("Warning: GOOGLE_CREDENTIALS environment variable missing.")
except Exception as e:
    print(f"Failed to connect to Google Sheets: {e}")

# 3. Initialize FastAPI App
app = FastAPI()

# Enable CORS for Vercel Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://my-ai-project-henna.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AuthRequest(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    username: str
    message: str

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

@app.get("/")
def serve_home():
    return FileResponse("index.html")

# Create a separate route for API health checks
@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "Backend API is online!"}

# --- SIGNUP ---
@app.post("/signup")
def process_signup(request: AuthRequest):
    if not users_sheet:
        raise HTTPException(status_code=500, detail="Database connection offline.")

    username = request.username.strip().lower()
    if not username or not request.password:
        raise HTTPException(status_code=400, detail="Username and password are required.")

    all_rows = users_sheet.get_all_values()
    for row in all_rows[1:]:
        if len(row) > 1 and row[1].strip().lower() == username:
            raise HTTPException(status_code=400, detail="Username already exists! Switch to Sign In.")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hashed_pwd = hash_password(request.password)
    users_sheet.append_row([timestamp, username, hashed_pwd])

    return {"message": "Account created successfully! Please Sign In."}

# --- LOGIN ---
@app.post("/login")
def process_login(request: AuthRequest):
    if not users_sheet:
        raise HTTPException(status_code=500, detail="Database connection offline.")

    username = request.username.strip().lower()
    all_rows = users_sheet.get_all_values()

    user_row = None
    for row in all_rows[1:]:
        if len(row) > 1 and row[1].strip().lower() == username:
            user_row = row
            break

    if not user_row:
        raise HTTPException(status_code=404, detail="User not found! Please Sign Up first.")

    input_pwd_hash = hash_password(request.password)
    stored_pwd_hash = user_row[2] if len(user_row) > 2 else ""

    if input_pwd_hash != stored_pwd_hash:
        raise HTTPException(status_code=401, detail="Incorrect password. Try again.")

    return {"message": "Login successful!", "username": username}

# --- CHATBOT & DRIVE SAVING ---
@app.post("/chat")
def process_chat(request: ChatRequest):
    username = request.username.strip().lower()
    user_msg = request.message.strip()

    if not user_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # 1. Get response from Gemini AI
    try:
        ai_response = model.generate_content(user_msg).text
    except Exception as e:
        ai_response = f"Sorry, Gemini AI encountered an error: {str(e)}"

    # 2. Save conversation log to Google Drive (ChatLogs sheet)
    if chat_sheet:
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            chat_sheet.append_row([timestamp, username, user_msg, ai_response])
        except Exception as e:
            print(f"Failed to save chat log to Google Drive: {e}")

    return {"response": ai_response}
