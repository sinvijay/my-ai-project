import os
import json
import hashlib
import gspread
from fastapi import FastAPI, HTTPException, status
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

# 2. Configure Google Sheets
# 2. Configure Google Sheets
sheet = None
try:
    google_creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if google_creds_json:
        creds_dict = json.loads(google_creds_json)
        gc = gspread.service_account_from_dict(creds_dict)
        sheet = gc.open("MyLoginDatabase").sheet1
        print("Successfully connected to Google Sheets!")
    else:
        print("Warning: GOOGLE_CREDENTIALS environment variable missing.")
except Exception as e:
    print(f"Failed to connect to Google Sheets: {e}")
    # Print the full error details if Google returns an HTTP response object
    if hasattr(e, 'response') and hasattr(e.response, 'text'):
        print(f"Google API Error Details: {e.response.text}")
    sheet = None

# 3. Initialize FastAPI
app = FastAPI()

# Enable CORS for Vercel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AuthRequest(BaseModel):
    username: str
    password: str

# Helper function to hash passwords securely
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

@app.get("/")
def serve_home():
    return FileResponse("index.html")

# Create a separate route for API health checks
@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "Backend API is online!"}
# --- SIGNUP ENDPOINT ---
@app.post("/signup")
def process_signup(request: AuthRequest):
    if not sheet:
        raise HTTPException(status_code=500, detail="Database connection offline.")

    username = request.username.strip().lower()
    if not username or not request.password:
        raise HTTPException(status_code=400, detail="Username and password are required.")

    # Fetch all existing rows from Google Sheet
    all_rows = sheet.get_all_values()
    
    # If sheet is brand new, add headers
    if not all_rows:
        sheet.append_row(["Timestamp", "Username", "PasswordHash"])
        all_rows = [["Timestamp", "Username", "PasswordHash"]]

    # Check if username already exists (Column Index 1 is Username)
    for row in all_rows[1:]:  # Skip header row
        if len(row) > 1 and row[1].strip().lower() == username:
            raise HTTPException(
                status_code=400, 
                detail="Username already registered! Please switch to Login."
            )

    # Save new user credentials to Google Drive/Sheet
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hashed_pwd = hash_password(request.password)
    
    try:
        sheet.append_row([timestamp, username, hashed_pwd])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save data to Drive: {e}")

    return {"message": "Account created successfully! You can now Log In."}

# --- LOGIN ENDPOINT ---
@app.post("/login")
def process_login(request: AuthRequest):
    if not sheet:
        raise HTTPException(status_code=500, detail="Database connection offline.")

    username = request.username.strip().lower()
    all_rows = sheet.get_all_values()

    # Find user in Google Sheet
    user_row = None
    for row in all_rows[1:]:
        if len(row) > 1 and row[1].strip().lower() == username:
            user_row = row
            break

    if not user_row:
        raise HTTPException(
            status_code=404, 
            detail="User not found! Please Sign Up first."
        )

    # Validate Password
    input_pwd_hash = hash_password(request.password)
    stored_pwd_hash = user_row[2] if len(user_row) > 2 else ""

    if input_pwd_hash != stored_pwd_hash:
        raise HTTPException(status_code=401, detail="Incorrect password. Try again.")

    # Generate custom greeting with Gemini AI
    prompt = f"Write a 1-sentence funny welcome back message for a user named {request.username}."
    try:
        ai_response = model.generate_content(prompt).text
    except Exception:
        ai_response = f"Welcome back, {request.username}!"

    return {"message": ai_response}
