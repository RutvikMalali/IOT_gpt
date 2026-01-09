import os
from supabase import create_client, Client
from datetime import date, datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ----------------------------
# USER OPERATIONS
# ----------------------------
def create_user(username, password):
    """Create a new user. Returns user_id on success, None on duplicate username."""
    try:
        result = supabase.table("users").insert({
            "username": username,
            "password": password,
            "xp": 0,
            "streak": 0
        }).execute()
        return result.data[0]["id"] if result.data else None
    except Exception as e:
        # Username already exists
        return None

def authenticate_user(username, password):
    """Authenticate user. Returns user_id on success, None on failure."""
    try:
        result = supabase.table("users").select("id").eq("username", username).eq("password", password).execute()
        return result.data[0]["id"] if result.data else None
    except:
        return None

def get_user_stats(user_id):
    """Get user's XP and streak."""
    try:
        result = supabase.table("users").select("xp, streak").eq("id", user_id).execute()
        if result.data:
            return result.data[0]["xp"], result.data[0]["streak"]
        return 0, 0
    except:
        return 0, 0

# ----------------------------
# CHAT OPERATIONS
# ----------------------------
def save_chat(user_id, project):
    """Save a chat/project to history."""
    try:
        supabase.table("chats").insert({
            "user_id": user_id,
            "project": project
        }).execute()
        return True
    except:
        return False

def get_user_chats(user_id):
    """Get all chats for a user."""
    try:
        result = supabase.table("chats").select("id, project").eq("user_id", user_id).order("created_at", desc=True).execute()
        return [(row["id"], row["project"]) for row in result.data] if result.data else []
    except:
        return []

# ----------------------------
# DOMAIN TRACKING OPERATIONS
# ----------------------------
def check_domain_usage(user_id, domain):
    """Check if user has used this domain before. Returns True if used, False if new."""
    try:
        result = supabase.table("domains_used").select("id").eq("user_id", user_id).eq("domain", domain).execute()
        return len(result.data) > 0
    except:
        return False

def mark_domain_used(user_id, domain):
    """Mark a domain as used by the user."""
    try:
        supabase.table("domains_used").insert({
            "user_id": user_id,
            "domain": domain
        }).execute()
        return True
    except:
        return False

# ----------------------------
# XP AND STREAK OPERATIONS
# ----------------------------
def update_user_xp_streak(user_id, xp_gained, new_streak):
    """Update user's XP and streak."""
    try:
        # Get current XP
        result = supabase.table("users").select("xp").eq("id", user_id).execute()
        current_xp = result.data[0]["xp"] if result.data else 0
        
        # Update XP, streak, and last_visit
        today = date.today().isoformat()
        supabase.table("users").update({
            "xp": current_xp + xp_gained,
            "streak": new_streak,
            "last_visit": today
        }).eq("id", user_id).execute()
        
        return current_xp + xp_gained, new_streak
    except Exception as e:
        print(f"Error updating XP/streak: {e}")
        return 0, 0

def get_user_last_visit(user_id):
    """Get user's last visit date."""
    try:
        result = supabase.table("users").select("last_visit").eq("id", user_id).execute()
        if result.data and result.data[0]["last_visit"]:
            return result.data[0]["last_visit"]
        return None
    except:
        return None
