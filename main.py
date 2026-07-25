import os
import json
import gspread
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime

# Load local .env if present
load_dotenv()

# 1. Configure Gemini AI
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

# 2. Configure Google Sheets from JSON String Variable
sheet = None
try:
    google_creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if google_creds_json:
        creds_dict = json.loads(google_creds_json)
        gc = gspread.service_account_from_dict(creds_dict)
        sheet = gc.open("MyLoginDatabase").sheet1
    else:
        print("Warning: GOOGLE_CREDENTIALS environment variable missing.")
except Exception as e:
    print(f"Failed to connect to Google Sheets: {e}")

# 3. Initialize FastAPI App
app = FastAPI()

# 4. Enable CORS (Allows Vercel Frontend to communicate with Railway Backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your Vercel URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LoginRequest(BaseModel):
    username: str
    password: str

@app.get("/")
def health_check():
    return File{"index.html"}

@app.post("/login")
def process_login(request: LoginRequest):
    # Ask Gemini for a greeting
    prompt = f"Write a 1-sentence funny welcome back message for a user named {request.username}."
    try:
        ai_response = model.generate_content(prompt).text
    except Exception:
        ai_response = f"Welcome back, {request.username}!"

    # Append entry to Google Sheets database
    if sheet:
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet.append_row([timestamp, request.username, "***HIDDEN***", ai_response])
        except Exception as e:
            print(f"Google Sheets log failed: {e}")

    return {"message": ai_response}
