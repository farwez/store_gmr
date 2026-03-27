import streamlit as st
import base64
import hashlib
import json
import os
import pandas as pd
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import A4, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.pdfgen import canvas
from io import BytesIO
import urllib.parse
from firebase_config import bucket, db, storage_available

# Helper for IST Time
def get_ist_time():
    """Returns current time in IST (UTC + 5:30)"""
    return datetime.utcnow() + timedelta(hours=5, minutes=30)

def today_string():
    return get_ist_time().strftime("%Y-%m-%d")

def hash_password(password, salt=None):
    """Secure PBKDF2 hashing for passwords."""
    if salt is None:
        salt = os.urandom(16).hex()
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
    return f"{hashed}${salt}"

def verify_user(username, password):
    """Verify credentials against Firestore."""
    try:
        user_doc = db.collection("users").document(username.lower()).get()
        if user_doc.exists:
            data = user_doc.to_dict()
            stored_hash = data.get("password", "")
            
            # Legacy SHA-256 fallback and automatic upgrade
            if stored_hash == hashlib.sha256(password.encode()).hexdigest():
                db.collection("users").document(username.lower()).update({"password": hash_password(password)})
                return {"username": username, "name": data.get("name", username), "role": data.get("role", "user")}
                
            # Secure PBKDF2 hash verification
            elif "$" in stored_hash:
                _, salt = stored_hash.split("$", 1)
                if hash_password(password, salt) == stored_hash:
                    return {"username": username, "name": data.get("name", username), "role": data.get("role", "user")}
        return None
    except Exception as e:
        print(f"Auth error: {e}")
        return None

def create_user(username, password, name="", role="user"):
    """Create a new user in Firestore."""
    try:
        user_ref = db.collection("users").document(username.lower())
        if user_ref.get().exists:
            return False, "Username already exists"

        role = (role or "user").strip().lower()
        if role not in {"admin", "user"}:
            role = "user"

        # First account is always admin bootstrap
        users_count = db.collection("users").count().get()[0][0].value
        if users_count == 0:
            role = "admin"

        user_ref.set({
            "username": username.lower(),
            "password": hash_password(password),
            "name": name or username,
            "role": role,
            "created_at": get_ist_time()
        })
        return True, f"User created successfully as {role}"
    except Exception as e:
        return False, str(e)


def set_user_password(username, new_password):
    """Set password for an existing user using secure hashing."""
    try:
        uname = (username or "").strip().lower()
        pwd = (new_password or "").strip()
        if not uname or not pwd:
            return False, "Username and new password are required"
        user_ref = db.collection("users").document(uname)
        if not user_ref.get().exists:
            return False, "User not found"
        user_ref.update({"password": hash_password(pwd)})
        return True, "Password updated successfully"
    except Exception as e:
        return False, str(e)


def change_user_password(username, current_password, new_password):
    """Change password after validating current password."""
    try:
        uname = (username or "").strip()
        curr = (current_password or "").strip()
        newp = (new_password or "").strip()
        if not uname or not curr or not newp:
            return False, "Current password and new password are required"
        user = verify_user(uname, curr)
        if not user:
            return False, "Current password is incorrect"
        return set_user_password(uname, newp)
    except Exception as e:
        return False, str(e)

import hmac

@st.cache_resource
def get_server_secret():
    """Retrieve or create a server secret for HMAC signing.
    Cached as a resource so it only hits Firestore ONCE per server lifecycle.
    """
    try:
        secret_doc = db.collection("settings").document("server_secret").get()
        if secret_doc.exists:
            return secret_doc.to_dict().get("key", "fallback_secret")
        else:
            new_key = os.urandom(32).hex()
            db.collection("settings").document("server_secret").set({"key": new_key})
            return new_key
    except:
        return "fallback_secret"

SERVER_SECRET = get_server_secret()

def sign_session_data(data_dict):
    """Sign a dictionary payload securely with HMAC-SHA256."""
    data_str = json.dumps(data_dict, sort_keys=True)
    signature = hmac.new(SERVER_SECRET.encode(), data_str.encode(), hashlib.sha256).hexdigest()
    return f"{data_str}|{signature}"

def verify_session_data(signed_str):
    """Verify an HMAC-SHA256 signed payload and return the dictionary."""
    if not signed_str or "|" not in signed_str:
        return None
    data_str, signature = signed_str.rsplit("|", 1)
    expected_signature = hmac.new(SERVER_SECRET.encode(), data_str.encode(), hashlib.sha256).hexdigest()
    if hmac.compare_digest(expected_signature, signature):
        try:
            return json.loads(data_str)
        except json.JSONDecodeError:
            return None
    return None

def enforce_login_and_restore():
    if not st.session_state.get("authenticated", False):
        st.markdown("""
        <script>
            setTimeout(() => {
                const session = localStorage.getItem('gmr_auth_session');
                if (session) {
                    let shouldRestore = false;
                    try {
                        let payload = session;
                        if (session.includes('|')) {
                            payload = session.slice(0, session.lastIndexOf('|'));
                        }
                        const data = JSON.parse(payload);
                        shouldRestore = !!data.expiry && new Date().getTime() < data.expiry;
                    } catch (e) {
                        shouldRestore = session.includes('|');
                    }

                    if (shouldRestore) {
                        const inputs = window.parent.document.querySelectorAll('input[aria-label="session_restorer"]');
                        if (inputs.length > 0) {
                            const input = inputs[inputs.length - 1];
                            if (input.value !== session) {
                                input.value = session;
                                input.dispatchEvent(new Event('input', { bubbles: true }));
                                input.dispatchEvent(new KeyboardEvent('keydown', { 'key': 'Enter', 'bubbles': true }));
                            }
                        }
                    } else {
                        localStorage.removeItem('gmr_auth_session');
                    }
                }
            }, 300);
        </script>
        """, unsafe_allow_html=True)

        st.markdown("""
            <style>
                div[data-testid="stTextInput"]:has(input[aria-label="session_restorer"]) {
                    position: fixed !important;
                    top: -100px !important;
                    left: -100px !important;
                    width: 0 !important;
                    height: 0 !important;
                    overflow: hidden !important;
                    visibility: hidden !important;
                    margin: 0 !important;
                    padding: 0 !important;
                }
            </style>
        """, unsafe_allow_html=True)
        
        # We use a unique key per run, or a static key. We'll use static key that gets cleared if needed.
        restored_session = st.text_input("session_restorer", label_visibility="collapsed", key="restore_token")
        
        if restored_session and not st.session_state.get("authenticated"):
            # If the session string starts with {, it's legacy insecure JSON. We reject it to force re-login.
            if restored_session.startswith("{"):
                st.markdown("<script>localStorage.removeItem('gmr_auth_session');</script>", unsafe_allow_html=True)
                return False
                
            data = verify_session_data(restored_session)
            if data:
                try:
                    now = datetime.now().timestamp() * 1000
                    if data.get("expiry", 0) > now:
                        st.session_state["authenticated"] = True
                        st.session_state["username"] = data["username"]
                        st.session_state["user_name"] = data.get("name", data.get("username", ""))
                        st.session_state["user_role"] = data.get("role", "user")
                        st.rerun()
                except Exception:
                    pass
            else:
                st.markdown("<script>localStorage.removeItem('gmr_auth_session');</script>", unsafe_allow_html=True)
        return False
    return True

def check_auth(quiet=False):
    """Check if user is authenticated and handle role-based redirection."""
    auth_restored = enforce_login_and_restore()
    if not st.session_state.get("authenticated", False):
        if not quiet:
            st.warning("⚠️ Access Denied. Please login.")
            col1, col2 = st.columns([1, 4])
            with col1:
                if st.button("Go to Login", type="primary"):
                    st.switch_page("app.py")
            st.stop()
        return False
    return True

def check_admin():
    """Restrict access to admin users only."""
    if not check_auth():
        st.stop()
    if st.session_state.get("user_role", "user") != "admin":
        st.warning("⛔ Admin access required. Please login as an admin.")
        st.stop()

# --- SETTINGS MANAGEMENT ---
@st.cache_data(ttl=600)
def get_settings():
    """Fetch store settings from Firestore with caching."""
    try:
        settings_ref = db.collection("settings").document("store_info").get()
        if settings_ref.exists:
            return settings_ref.to_dict()
        else:
            # Default fallback settings
            return {
                "store_name": "MY STORE",
                "address": "Set Address in Settings",
                "phone": "0000000000",
                "email": "store@example.com",
                "gstin": "",
                "currency": "₹",
                "allow_self_signup": True
            }
    except Exception as e:
        print(f"Error fetching settings: {e}")
        return {}


# Custom CSS Injection
def inject_custom_css():
    st.markdown("""
    <style>
        /* 1. GLOBAL LIGHT THEME ENFORCEMENT */
        :root {
            --brand-primary: #4f46e5;
            --brand-secondary: #4338ca;
            --brand-gradient: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            --bg-main: #f8fafc;
            --card-bg: #ffffff;
            --sidebar-bg: #ffffff;
            --text-main: #0f172a;
            --text-muted: #475569;
            --border-color: #e2e8f0;
            --radius-lg: 20px;
            --radius-md: 12px;
            --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
            --shadow-md: 0 10px 15px -3px rgba(0,0,0,0.05), 0 4px 6px -2px rgba(0,0,0,0.05);
            --shadow-lg: 0 20px 25px -5px rgba(0,0,0,0.08), 0 10px 10px -5px rgba(0,0,0,0.04);
        }
        
        @keyframes slideFadeIn {
            0% { opacity: 0; transform: translateY(10px); }
            100% { opacity: 1; transform: translateY(0); }
        }

        [data-testid="stMainBlockContainer"] {
            animation: slideFadeIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }

        .stApp {
            background-color: var(--bg-main) !important;
            font-family: 'Inter', sans-serif !important;
        }
        
        /* Add top spacing for the new FAB button */
        [data-testid="stAppViewContainer"] {
            padding-top: 50px !important;
        }

        /* ------------------------------------- */
        /* PREMIUM CARDS & CONTAINERS            */
        /* ------------------------------------- */
        [data-testid="stVerticalBlock"] > [style*="border"] {
            background-color: white !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 16px !important;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03) !important;
            padding: 24px !important;
            margin-bottom: 1.5rem !important;
        }
        
        /* Metric Styling */
        [data-testid="stMetricValue"] {
            font-size: 1.8rem !important;
            font-weight: 700 !important;
            color: #1e293b !important;
        }

        /* ------------------------------------- */
        /* ENHANCED TEXT VISIBILITY (DESKTOP)    */
        /* ------------------------------------- */
        p, .stMarkdown p, .stText, [data-testid="stMarkdownContainer"] p, label, .stRadio div[role="radiogroup"] label, .stCheckbox label {
            color: var(--text-main) !important;
            font-size: 15px !important;
        }
        
        /* Ensures dropdown text and inputs are clearly visible */
        .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] span {
            color: #0f172a !important; 
            font-size: 15px !important;
            font-weight: 500 !important;
        }

        /* ------------------------------------- */
        /* MOBILE RESPONSIVE ADJUSTMENTS         */
        /* ------------------------------------- */
        @media (max-width: 768px) {
            .stMain { padding: 0.5rem !important; padding-top: 40px !important; }
            [data-testid="stMetric"] { padding: 15px !important; }
            h1 { font-size: 24px !important; }
            h2 { font-size: 20px !important; }
            h3 { font-size: 18px !important; }
            
            /* FORCE LARGER, DARKER TEXT ON MOBILE */
            p, .stMarkdown p, .stText, [data-testid="stMarkdownContainer"] p, label, .stRadio div[role="radiogroup"] label, .stCheckbox label {
                font-size: 16px !important; 
                line-height: 1.5 !important;
                color: #000000 !important;
                font-weight: 500 !important;
            }
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] span {
                font-size: 16px !important; 
                color: #000000 !important;
                padding: 10px 12px !important;
            }
        }

        h1, h2, h3, h4, h5, h6 {
            font-family: 'Outfit', sans-serif !important;
            color: var(--text-main) !important;
            font-weight: 700 !important;
        }

        /* ============================================ */
        /*   2. SIDEBAR — PREMIUM DARK DESIGN           */
        /* ============================================ */
        [data-testid="stSidebar"] {
            background-color: #111827 !important; /* Solid Slate Black */
            background-image: linear-gradient(180deg, #111827 0%, #1f2937 100%) !important;
            border-right: 1px solid rgba(255,255,255,0.05) !important;
        }

        /* Ensure the container inside sidebar is visible and clear */
        [data-testid="stSidebarContent"] {
            background-color: transparent !important;
        }

        /* All text and links inside sidebar MUST be light silver/white */
        [data-testid="stSidebar"] *, 
        [data-testid="stSidebar"] div, 
        [data-testid="stSidebar"] span, 
        [data-testid="stSidebar"] p, 
        [data-testid="stSidebar"] a {
            color: #d1d5db !important;
        }

        /* Active/Hover states for navigation links */
        [data-testid="stSidebar"] a:hover {
            background-color: rgba(255,255,255,0.05) !important;
            color: #ffffff !important;
        }

        /* Section headers in sidebar */
        [data-testid="stSidebar"] h6 {
            color: #6b7280 !important;
            font-size: 0.7rem !important;
            font-weight: 700 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.1em !important;
            margin-top: 1.5rem !important;
            padding-left: 1rem !important;
        }

        /* ================================================ */
        /* SIDEBAR TOGGLE BUTTONS — HIGHEST CLARITY         */
        /* ================================================ */

        /* Internal Collapse Button (when sidebar is open) */
        [data-testid="stSidebarCollapseButton"] {
            background: rgba(255,255,255,0.08) !important;
            border: 1px solid rgba(255,255,255,0.1) !important;
            border-radius: 50% !important;
            right: 10px !important;
            top: 10px !important;
        }

        /* External Expand Button (floating on the page) */
        [data-testid="collapsedControl"], 
        [data-testid="stSidebarCollapsedControl"], 
        [data-testid="stExpandSidebarButton"] {
            background-color: rgba(255, 255, 255, 0.95) !important;
            backdrop-filter: blur(8px) !important;
            border-radius: 12px !important;
            border: 1px solid #e2e8f0 !important;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03) !important;
            width: 44px !important;
            height: 44px !important;
            position: fixed !important;
            top: 20px !important;
            left: 20px !important;
            z-index: 10000000 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            transition: all 0.2s ease !important;
        }

        [data-testid="collapsedControl"]:hover, 
        [data-testid="stSidebarCollapsedControl"]:hover, 
        [data-testid="stExpandSidebarButton"]:hover {
            background-color: #ffffff !important;
            box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1) !important;
            transform: translateY(-1px) !important;
        }

        [data-testid="collapsedControl"]:active, 
        [data-testid="stSidebarCollapsedControl"]:active, 
        [data-testid="stExpandSidebarButton"]:active {
            background-color: #f8fafc !important;
            transform: scale(0.95) !important;
        }

        /* SVG Arrow Icons */
        [data-testid="stSidebarCollapseButton"] svg {
            fill: #ffffff !important;
            color: #ffffff !important;
            width: 20px !important;
            height: 20px !important;
        }

        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="stExpandSidebarButton"] {
            color: #0f172a !important;
        }

        [data-testid="collapsedControl"] svg,
        [data-testid="stSidebarCollapsedControl"] svg,
        [data-testid="stExpandSidebarButton"] svg {
            fill: #0f172a !important;
            color: #0f172a !important;
            stroke: #0f172a !important;
            width: 24px !important;
            height: 24px !important;
        }
        
        [data-testid="collapsedControl"] svg path,
        [data-testid="stSidebarCollapsedControl"] svg path,
        [data-testid="stExpandSidebarButton"] svg path {
            fill: #0f172a !important;
            stroke: #0f172a !important;
        }

        /* Mobile specific — ensure it's not cut off by status bar */
        @media (max-width: 768px) {
            [data-testid="stAppViewContainer"] {
                padding-top: 60px !important;
            }
            .main { padding-top: 20px !important; }
            
            [data-testid="collapsedControl"], 
            [data-testid="stSidebarCollapsedControl"], 
            [data-testid="stExpandSidebarButton"] {
                width: 44px !important;
                height: 44px !important;
                top: 16px !important;
                left: 16px !important;
            }
        }

        /* Hide native navigation list */
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
            display: none !important;
        }

        /* Nav links — normal state */
        div[data-testid="stPageLink-NavLink"] {
            padding: 11px 16px !important;
            border-radius: 10px !important;
            margin: 2px 10px !important;
            transition: all 0.2s ease !important;
            border: 1px solid transparent !important;
        }
        div[data-testid="stPageLink-NavLink"] p {
            color: #cbd5e1 !important;
            font-size: 14px !important;
            font-weight: 500 !important;
        }

        /* Nav links — hover */
        div[data-testid="stPageLink-NavLink"]:hover {
            background: rgba(255,255,255,0.07) !important;
            border-color: rgba(255,255,255,0.1) !important;
        }
        div[data-testid="stPageLink-NavLink"]:hover p {
            color: #ffffff !important;
        }

        /* Nav links — ACTIVE page */
        div[data-testid="stPageLink-NavLink"][aria-current="page"] {
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%) !important;
            box-shadow: 0 4px 15px rgba(99,102,241,0.4) !important;
            border-color: transparent !important;
        }
        div[data-testid="stPageLink-NavLink"][aria-current="page"] p {
            color: #ffffff !important;
            font-weight: 700 !important;
        }
        
        /* Dividers inside sidebar */
        [data-testid="stSidebar"] hr {
            border-color: #334155 !important;
        }
        
        /* Sidebar buttons (Refresh / Logout) */
        [data-testid="stSidebar"] button[kind="secondary"] {
            background: rgba(30, 41, 59, 0.8) !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            color: #cbd5e1 !important;
            border-radius: 10px !important;
        }
        [data-testid="stSidebar"] button[kind="secondary"]:hover {
            background: rgba(71, 85, 105, 0.8) !important;
            border-color: rgba(255, 255, 255, 0.2) !important;
            color: #ffffff !important;
        }

        /* 5. INPUTS - CLEAN WHITE & INTERACTIVE */
        .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {
            background: white !important;
            border-radius: 12px !important;
            border: 1px solid var(--border-color) !important;
            padding: 8px 12px !important;
            color: black !important;
            transition: all 0.2s ease-in-out !important;
            box-shadow: var(--shadow-sm) !important;
        }
        
        .stTextInput input:focus, .stNumberInput input:focus, .stSelectbox div[data-baseweb="select"]:focus-within {
            border-color: var(--brand-primary) !important;
            box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.2) !important;
            outline: none !important;
        }

        .stTextInput input:hover, .stNumberInput input:hover, .stSelectbox div[data-baseweb="select"]:hover {
            border-color: #cbd5e1 !important;
        }
        
        div[data-baseweb="select"] span {
            color: #0f172a !important;
        }

        /* 3. CARDS & METRICS (Modern Elegant) */
        [data-testid="stMetric"] {
            background: var(--card-bg) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: var(--radius-lg) !important;
            padding: 24px !important;
            box-shadow: var(--shadow-md) !important;
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) !important;
            position: relative;
            overflow: hidden;
        }

        [data-testid="stMetric"]::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 3px;
            background: var(--brand-gradient);
            opacity: 0.1;
            transition: opacity 0.3s ease;
        }

        [data-testid="stMetric"]:hover {
            transform: translateY(-8px) scale(1.02);
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04) !important;
            border-color: var(--brand-primary) !important;
        }

        [data-testid="stMetric"]:hover::before {
            opacity: 1;
        }

        [data-testid="stMetricLabel"] {
            font-size: 14px !important;
            color: var(--text-muted) !important;
            font-weight: 600 !important;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        [data-testid="stMetricValue"] {
            color: var(--text-main) !important;
            font-weight: 800 !important;
            font-size: 2.2rem !important;
            letter-spacing: -0.02em;
        }

        /* Glassmorphism for containers */
        div.stContainer {
            transition: all 0.3s ease-in-out !important;
        }
        
        div.stContainer:hover {
            border-color: #6366f1 !important;
        }

        /* Button micro-interactions */
        .stButton > button {
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
            border-radius: 10px !important;
            font-weight: 600 !important;
        }
        
        .stButton > button:active {
            transform: scale(0.96) !important;
        }
        
        [data-testid="stMetricDelta"] {
            font-weight: 600 !important;
        }

        /* THE DROPDOWN LIST (OPENED) */
        /* This is usually in a portal at the body level */
        div[data-baseweb="popover"], 
        div[role="listbox"],
        div[data-baseweb="menu"],
        ul[role="listbox"] {
            background-color: #ffffff !important;
            color: #1e293b !important;
            border: 1px solid #e2e8f0 !important;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1) !important;
            border-radius: 8px !important;
            max-height: 480px !important;
        }

        /* Items in the list */
        li[role="option"], 
        [role="listbox"] li,
        [data-baseweb="popover"] li {
            background-color: #ffffff !important;
            color: #1e293b !important;
            padding: 10px 15px !important;
            margin: 2px 5px !important;
            border-radius: 6px !important;
        }

        /* Hover & Active States in List */
        li[role="option"]:hover,
        [role="listbox"] li:hover,
        [data-baseweb="popover"] li:hover {
            background-color: #f1f5f9 !important;
            color: #4F46E5 !important;
        }

        /* 6. ALERTS & TOASTS */
        div.stAlert {
            border-radius: var(--radius-md) !important;
            border: 1px solid var(--border-color) !important;
            border-left: 4px solid var(--brand-primary) !important;
            box-shadow: var(--shadow-md) !important;
            background-color: white !important;
            transition: all 0.3s ease !important;
        }
        
        div.stAlert:hover {
            box-shadow: var(--shadow-lg) !important;
            transform: translateY(-2px);
        }

        [data-testid="stToast"] {
            background-color: white !important;
            border-radius: 12px !important;
            border: 1px solid var(--border-color) !important;
            border-left: 4px solid var(--brand-secondary) !important;
            box-shadow: var(--shadow-lg) !important;
            padding: 10px !important;
        }

        /* 7. TABLES - PREMIUM LOOK */
        [data-testid="stDataFrame"] {
            background: white !important;
            border-radius: var(--radius-md) !important;
            padding: 10px !important;
            border: 1px solid var(--border-color) !important;
            box-shadow: var(--shadow-sm) !important;
            overflow: hidden !important;
        }

        /* 8. TABS STYLING - SMOOTH UNDELINE */
        div[data-testid="stTabs"] button {
            font-family: 'Outfit', sans-serif !important;
            font-weight: 600 !important;
            color: var(--text-muted) !important;
            transition: all 0.3s ease !important;
        }
        
        div[data-testid="stTabs"] button:hover {
            color: var(--text-main) !important;
        }

        div[data-testid="stTabs"] button[aria-selected="true"] {
            color: var(--brand-primary) !important;
        }
        
        /* 9. SCROLLBARS */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #f1f5f9; }
        ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

        /* MainMenu, Footer, and Header visibility */
        #MainMenu {visibility: visible;}
        footer {visibility: hidden;}
        
        /* Forcely hide native sidebar to prevent delay/interference */
        [data-testid="stSidebarNav"] {
            display: none !important;
        }
        
        [data-testid="stHeader"] {
            background: rgba(255, 255, 255, 0.8) !important;
            backdrop-filter: blur(8px) !important;
            border-bottom: 1px solid var(--border-color) !important;
        }
        
        /* 4. BUTTONS - PREMIUM FEEL */
        button[kind="primary"] {
            background: var(--brand-gradient) !important;
            border: none !important;
            padding: 0.6rem 1.5rem !important;
            border-radius: 12px !important;
            font-weight: 600 !important;
            color: white !important;
            box-shadow: 0 4px 14px 0 rgba(99, 102, 241, 0.39) !important;
            transition: all 0.2s ease !important;
        }

        button[kind="primary"]:hover {
            box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5) !important;
            transform: scale(1.02) !important;
        }

        button[kind="secondary"] {
            background: white !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 12px !important;
            color: var(--text-main) !important;
            font-weight: 600 !important;
            box-shadow: var(--shadow-sm) !important;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
        }

        button[kind="secondary"]:hover {
            background: var(--bg-main) !important;
            border-color: #94a3b8 !important;
            box-shadow: var(--shadow-md) !important;
            transform: translateY(-2px) !important;
        }
        
    </style>
    
    <!-- JS Injection for 'Enter' key tab navigation (essential for barcode scanners and fast typing) -->
    <img src="x" onerror="
        if(!window.parent.enterBound){
            window.parent.document.addEventListener('keydown', function(event) {
                if (event.key === 'Enter' && event.target.tagName === 'INPUT' && event.target.type !== 'submit') {
                    event.preventDefault();
                    // Custom logic to focus the next input or button
                    const focusableElements = Array.from(window.parent.document.querySelectorAll('input:not([disabled]), button:not([disabled])'));
                    const index = focusableElements.indexOf(event.target);
                    if (index > -1 && index + 1 < focusableElements.length) { 
                        focusableElements[index + 1].focus(); 
                    }
                }
            });
            window.parent.enterBound = true;
        }
    " style="display:none;">
    
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@400;600;800&display=swap" rel="stylesheet" media="print" onload="this.media='all'">
    <noscript><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@400;600;800&display=swap" rel="stylesheet"></noscript>

    
    <script>
        (function() {
            function applyAll() {
                // Try both document and window.parent.document (for iframe/non-iframe environments)
                const docs = [document];
                try { if (window.parent && window.parent.document !== document) docs.unshift(window.parent.document); } catch(e) {}

                docs.forEach(function(P) {
                    try {
                        // Hide native auto-generated nav links only
                        const nav = P.querySelector('[data-testid="stSidebarNav"]');
                        if (nav) nav.style.display = 'none';

                        // Style sidebar dark
                        const sidebarInner = P.querySelector('[data-testid="stSidebar"] > div:first-child')
                                          || P.querySelector('[data-testid="stSidebar"]');
                        if (sidebarInner) sidebarInner.style.background = 'linear-gradient(160deg, #0f172a 0%, #1e293b 100%)';

                        // Ensure collapsedControl and its children are NOT hidden
                        const expandBtn = P.querySelector('[data-testid="collapsedControl"]') || 
                                          P.querySelector('[data-testid="stSidebarCollapsedControl"]') ||
                                          P.querySelector('[data-testid="stExpandSidebarButton"]');
                        if (expandBtn) {
                            expandBtn.style.visibility = 'visible';
                            expandBtn.style.opacity = '1';
                            expandBtn.style.display = 'flex';
                        }
                    } catch(e) {}
                });
            }

            applyAll();
            new MutationObserver(applyAll).observe(document.body, {childList:true, subtree:true});
        })();
    </script>
    """, unsafe_allow_html=True)

    import streamlit.components.v1 as components
    components.html(
        """
        <script>
        (function() {
            try {
                const P = window.parent;
                const D = P.document;
                
                // version 5.0 - Robust Streamlit Navigation
                if (!D || D.__poStoreEnterBoundV5) return;

                function isVisible(el) {
                    if (!el) return false;
                    if (el.disabled || el.readOnly) return false;
                    const style = P.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden') return false;
                    const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : null;
                    return !!(rect && rect.width > 0 && rect.height > 0);
                }

                function isField(el) {
                    if (!el) return false;
                    // Ignore the session restorer hidden field
                    if (el.getAttribute && el.getAttribute('aria-label') === 'session_restorer') return false;
                    
                    const tag = (el.tagName || '').toUpperCase();
                    const role = (el.getAttribute && el.getAttribute('role')) || '';
                    const type = (el.type || '').toLowerCase();

                    // Standard inputs
                    if (tag === 'INPUT' && !['hidden', 'checkbox', 'radio', 'button', 'submit', 'file', 'range'].includes(type)) return true;
                    if (tag === 'SELECT') return true;
                    if (role === 'combobox' || el.closest('[data-baseweb="select"]')) return true;
                    
                    return false;
                }

                function getFields(scope) {
                    // Find all possible interactable elements
                    const selectors = 'input:not([type="hidden"]):not([disabled]), select:not([disabled]), [role="combobox"], [data-baseweb="select"] input';
                    const nodes = Array.from(scope.querySelectorAll(selectors));
                    
                    // Filter and deduplicate (Streamlit selectboxes often have multiple elements)
                    const seen = new Set();
                    return nodes.filter(n => {
                        const isF = isField(n);
                        if (!isF || !isVisible(n)) return false;
                        
                        // For selectboxes, we only want one focusable element per widget
                        const container = n.closest('[data-testid="stSelectbox"]') || n.closest('[data-testid="stTextInput"]') || n.closest('[data-testid="stNumberInput"]');
                        if (container) {
                            if (seen.has(container)) return false;
                            seen.add(container);
                        }
                        return true;
                    });
                }

                function nearestSubmit(scope, current) {
                    const selectors = [
                        '[data-testid="stFormSubmitButton"] button',
                        'button[kind="primary"]',
                        'button[type="submit"]',
                        '[data-testid="baseButton-primary"]'
                    ].join(',');

                    const candidates = Array.from(D.querySelectorAll(selectors)).filter(isVisible);
                    
                    // Priority 1: Following the current element in the same scope
                    const following = candidates.filter(b => {
                        return !!(current.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
                    });
                    
                    if (following.length > 0) return following[0];
                    
                    // Priority 2: Any primary button in the current form/container
                    const local = scope ? Array.from(scope.querySelectorAll(selectors)).filter(isVisible) : [];
                    if (local.length > 0) return local[local.length - 1];

                    // Priority 3: Any primary button on page
                    return candidates.length > 0 ? candidates[candidates.length - 1] : null;
                }

                function focusEl(el) {
                    if (!el) return;
                    try {
                        // Special handling for Streamlit Selectbox (BaseWeb)
                        const selectbox = el.closest('[data-baseweb="select"]');
                        if (selectbox) {
                            const input = selectbox.querySelector('input');
                            if (input) { input.focus(); return; }
                        }
                        
                        el.focus();
                        if (el.tagName === 'INPUT' && typeof el.select === 'function') {
                            el.select();
                        }
                    } catch(e) {}
                }

                function onKeyDown(e) {
                    // Only handle Enter without modifiers
                    if (e.key !== 'Enter' || e.shiftKey || e.ctrlKey || e.altKey || e.metaKey) return;
                    
                    // Ignore if we are in a textarea
                    if (e.target.tagName === 'TEXTAREA') return;

                    let current = e.target;
                    if (!isField(current)) {
                        current = current.closest('input, select, [role="combobox"]');
                    }
                    if (!isField(current)) return;

                    const appScope = D.querySelector('[data-testid="stAppViewContainer"]') || D.body;
                    const scope = current.closest('form') || current.closest('[data-testid="stForm"]') || appScope;
                    
                    const fields = getFields(scope);
                    const idx = fields.indexOf(current);
                    
                    e.preventDefault();
                    e.stopPropagation();

                    if (idx >= 0 && idx + 1 < fields.length) {
                        // Move to next field
                        const nxt = fields[idx + 1];
                        setTimeout(() => focusEl(nxt), 10);
                    } else {
                        // Last field - trigger submit
                        const btn = nearestSubmit(scope, current);
                        if (btn) {
                            btn.click();
                            // Visual feedback
                            btn.style.transform = "scale(0.95)";
                            setTimeout(() => { btn.style.transform = ""; }, 100);
                        }
                    }
                }

                D.addEventListener('keydown', onKeyDown, true);
                D.__poStoreEnterBoundV5 = true;
                console.log("🚀 poStore Pro-Navigation Active");
            } catch (err) {
                console.error("Navigation error:", err);
            }
        })();
        </script>
        """,
        height=0,
        width=0,
    )

# --- CACHED DATA OPERATIONS ---

@st.cache_data(ttl=300)
def get_all_items():
    """Fetch all items from Firestore with caching to reduce reads and improve speed."""
    try:
        # Fetch only necessary fields to reduce API footprint
        items_ref = db.collection("items_master").select(["name", "price", "cost_price", "stock", "barcode"]).stream()
        # Convert to dictionary for easy lookup: {id: data}
        items_dict = {item.id: item.to_dict() for item in items_ref}
        return items_dict
    except Exception as e:
        print(f"Error fetching items: {e}")
        return {}

def clear_items_cache():
    """Clear only the items-related caches (surgical — does NOT wipe all caches)."""
    get_all_items.clear()

def clear_dashboard_cache():
    """Clear dashboard KPI caches only."""
    get_dashboard_kpis.clear()
    get_dashboard_alerts.clear()

def clear_expenses_cache():
    """Clear only the expenses cache."""
    # Imported pages use their own local @st.cache_data, so we signal via session state
    st.session_state["_expenses_cache_bust"] = st.session_state.get("_expenses_cache_bust", 0) + 1

def clear_credit_cache():
    """Clear only the credit book cache."""
    st.session_state["_credit_cache_bust"] = st.session_state.get("_credit_cache_bust", 0) + 1

# ── Cached Dashboard Data Fetchers ──────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def get_dashboard_kpis(today_str: str):
    """Fetch all KPI data for the dashboard in as few queries as possible."""
    try:
        sales_docs   = db.collection("sales").where("date", "==", today_str).stream()
        sales_list   = [s.to_dict() for s in sales_docs if not s.to_dict().get("voided", False)]
        gross_revenue    = sum(s.get("total", 0) for s in sales_list)
        today_orders     = len(sales_list)
        today_items_sold = sum(sum(it.get("qty", 0) for it in s.get("items", [])) for s in sales_list)
        today_cogs       = sum(sum(it.get("cost", 0) * it.get("qty", 0) for it in s.get("items", [])) for s in sales_list)

        rets_docs    = db.collection("returns").where("date", "==", today_str).stream()
        returns_list = [r.to_dict() for r in rets_docs]
        total_refunded   = sum(r.get("return_amount", 0) for r in returns_list)
        prior_ret_rev    = sum(r.get("return_amount", 0) for r in returns_list if r.get("original_sale_date", today_str) != today_str)
        prior_ret_cogs   = sum(sum(i.get("cost", 0) * i.get("qty", 0) for i in r.get("return_items", [])) for r in returns_list if r.get("original_sale_date", today_str) != today_str)

        exp_docs     = db.collection("expenses").where("date", "==", today_str).stream()
        today_expenses   = sum(e.to_dict().get("amount", 0) for e in exp_docs)

        items_count  = len(get_all_items())

        net_revenue  = gross_revenue - prior_ret_rev
        gross_profit = gross_revenue - today_cogs
        net_profit   = gross_profit - (prior_ret_rev - prior_ret_cogs) - today_expenses

        return {
            "gross_revenue":    gross_revenue,
            "today_orders":     today_orders,
            "today_items_sold": today_items_sold,
            "net_revenue":      net_revenue,
            "returns_count":    len(returns_list),
            "total_refunded":   total_refunded,
            "today_expenses":   today_expenses,
            "net_profit":       net_profit,
            "items_count":      items_count,
        }
    except Exception as e:
        return {"error": str(e)}

@st.cache_data(ttl=180)
def get_dashboard_alerts():
    """Fetch low-stock and credit alert data for the dashboard."""
    try:
        low_items = db.collection("items_master").where("stock", "<=", 5).stream()
        low_list  = [(i.to_dict().get("name", "?"), i.to_dict().get("stock", 0)) for i in low_items]
    except Exception:
        low_list  = []

    try:
        credit_sales = db.collection("sales").where("payment_method", "in", ["Credit / Due", "Credit/Due"]).stream()
        credit_total = sum(s.to_dict().get("total", 0) for s in credit_sales if not s.to_dict().get("voided", False))
        credit_pmts  = db.collection("credit_payments").stream()
        paid_total   = sum(p.to_dict().get("amount", 0) for p in credit_pmts)
        outstanding  = max(0, credit_total - paid_total)
    except Exception:
        outstanding  = 0

    return {"low_list": low_list, "outstanding": outstanding}

@st.cache_data(ttl=60)
def get_recent_transactions(limit: int = 10):
    """Fetch recent transactions for the dashboard."""
    from datetime import datetime as _dt
    rows = []
    try:
        recent_docs = db.collection("sales").order_by("timestamp", direction="DESCENDING").limit(max(limit * 3, limit)).stream()
        for doc in recent_docs:
            d  = doc.to_dict()
            if d.get("voided", False):
                continue
            ts = d.get("timestamp")
            rows.append({
                "Time":     ts.strftime("%I:%M %p") if isinstance(ts, _dt) else "N/A",
                "Date":     d.get("date", "N/A"),
                "Customer": d.get("customer_name", "N/A"),
                "Items":    len(d.get("items", [])),
                "Total":    f"₹{d.get('total', 0):,.0f}",
                "Mode":     d.get("payment_method", "Cash"),
            })
            if len(rows) >= limit:
                break
    except Exception:
        pass
    return rows

# --- CUSTOM SIDEBAR ---

def render_sidebar():
    """Render a custom sidebar with navigation links, refresh and logout."""
    if not st.session_state.get("authenticated", False):
        return
    try:
        is_admin = st.session_state.get("user_role", "user") == "admin"
        with st.sidebar:
            st.subheader("GMR Store Manager")
            st.caption(f"Signed in as: {st.session_state.get('user_name', '')} ({'Admin' if is_admin else 'User'})")
            st.markdown("---")

            # Dashboard
            st.page_link("app.py", label="Dashboard", icon="🏠")

            # Core Operations
            st.markdown("###### Operations", help="Manage daily tasks")
            st.page_link("pages/2_Sales.py", label="New Sale", icon="🛒")
            st.page_link("pages/1_Items_Master.py", label="Inventory / Items", icon="📦")
            if is_admin:
                st.page_link("pages/4_Credit_Book.py", label="Credit Book (Udhaar)", icon="📙")
                st.page_link("pages/6_Expense_Tracker.py", label="Daily Expense Tracker", icon="💸")
            st.page_link("pages/5_Returns.py", label="Returns / Exchange", icon="↩️")
            if is_admin:
                st.page_link("pages/8_Stock_Adjustments.py", label="Stock Adjustments", icon="📦")

            # History & Reports
            st.markdown("###### History & Reports", help="View past data")
            st.page_link("pages/7_Sales_History.py", label="Sales History", icon="📜")
            if is_admin:
                st.page_link("pages/3_Reports.py", label="Reports", icon="📊")

            st.markdown("###### System", help="App Settings")
            if is_admin:
                st.page_link("pages/9_Settings.py", label="Settings", icon="⚙️")

            st.markdown("---")
            if st.button("🔄 Refresh Data", type="secondary", use_container_width=True):
                get_all_items.clear()
                get_dashboard_kpis.clear()
                get_dashboard_alerts.clear()
                get_recent_transactions.clear()
                st.rerun()

            st.caption(f"v1.2.0 • {get_ist_time().strftime('%d-%b')}")

            if st.button("🚪 Logout", use_container_width=True):
                st.markdown("""
                    <script>
                        localStorage.removeItem('gmr_auth_session');
                        window.location.reload();
                    </script>
                """, unsafe_allow_html=True)
                st.session_state["authenticated"] = False
                st.session_state["username"] = None
                st.session_state["user_role"] = None
                st.rerun()

    except Exception as e:
        st.error(f"Sidebar Error: {e}")


def generate_bill_pdf(filename, items, subtotal, discount_amount, discount_type, total, customer_name="", customer_phone="", payment_method="", invoice_title="TAX INVOICE"):
    try:
        if not items:
            raise ValueError("Cannot generate bill with empty items list")
        
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import Paragraph, Spacer, HRFlowable
        from reportlab.lib.units import inch
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
        
        doc = SimpleDocTemplate(filename, pagesize=A4,
                               topMargin=0.5*inch, bottomMargin=0.5*inch,
                               leftMargin=0.75*inch, rightMargin=0.75*inch)
        elements = []
        styles = getSampleStyleSheet()
        
        # Get store settings
        sett = get_settings()
        store_name = sett.get("store_name", "MY STORE").upper()
        store_address = sett.get("address", "Set Address in Settings")
        store_phone = sett.get("phone", "0000000000")
        store_email = sett.get("email", "")
        store_gst = sett.get("gstin", "")

        # Store header
        header_style = ParagraphStyle(
            'StoreHeader',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#4F46E5'),
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        # Remove emoji from PDF header to avoid character rendering issues
        elements.append(Paragraph(f"{store_name}", header_style))
        
        # Store details
        store_details_style = ParagraphStyle(
            'StoreDetails',
            parent=styles['Normal'],
            fontSize=9,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#64748b')
        )
        
        details_text = store_address
        if store_phone: details_text += f" | Phone: {store_phone}"
        if store_email: details_text += f" | Email: {store_email}"
        elements.append(Paragraph(details_text, store_details_style))
        
        if store_gst:
            elements.append(Paragraph(f"GSTIN: {store_gst}", store_details_style))
        elements.append(Spacer(1, 0.2*inch))
        
        # Horizontal line
        elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#1f77b4')))
        elements.append(Spacer(1, 0.15*inch))
        
        # Invoice title
        invoice_style = ParagraphStyle(
            'InvoiceTitle',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#333333'),
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        elements.append(Paragraph(invoice_title, invoice_style))
        elements.append(Spacer(1, 0.15*inch))
        
        # Customer information and bill details side by side
        info_style = styles['Normal']
        info_style.fontSize = 10
        
        from reportlab.platypus import TableStyle as TS
        
        # Payment info included
        payment_info = f"<br/>Payment Mode: {payment_method}" if payment_method else ""
        
        info_data = [
            [
                Paragraph(f"<b>Bill To:</b><br/>{customer_name}<br/>Phone: {customer_phone if customer_phone else 'N/A'}", info_style),
                Paragraph(f"<b>Ref No:</b> {get_ist_time().strftime('%Y%m%d%H%M%S')}<br/><b>Date:</b> {get_ist_time().strftime('%d-%m-%Y')}<br/><b>Time:</b> {get_ist_time().strftime('%I:%M %p')}{payment_info}", info_style)
            ]
        ]
        info_table = Table(info_data, colWidths=[3.5*inch, 3*inch])
        info_table.setStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ])
        elements.append(info_table)
        elements.append(Spacer(1, 0.25*inch))
        
        # Items table
        data = [["#", "Item Description", "Qty", "Price", "Amount"]]
        
        for idx, item in enumerate(items, 1):
            item_total = item.get('qty', 0) * item.get('price', 0)
            data.append([
                str(idx),
                str(item.get("name", "Unknown")), 
                str(item.get("qty", 0)), 
                f"Rs. {item.get('price', 0):,.2f}",
                f"Rs. {item_total:,.2f}"
            ])
        
        # Create table with styling
        table = Table(data, colWidths=[0.5*inch, 3.5*inch, 0.75*inch, 1.25*inch, 1.25*inch])
        table.setStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),  # Item names left-aligned
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#4F46E5')),
        ])
        
        elements.append(table)
        elements.append(Spacer(1, 0.15*inch))
        
        # Totals section
        totals_data = [
            ["", "", "", "Subtotal:", f"Rs. {subtotal:,.2f}"]
        ]
        
        if discount_amount > 0:
            # Replace ₹ with Rs. in PDF to prevent font rendering errors
            pdf_discount_type = discount_type.replace('Discount', '').replace('₹', 'Rs.').strip()
            discount_label = f"Discount ({pdf_discount_type}):"
            totals_data.append(["", "", "", discount_label, f"- Rs. {discount_amount:,.2f}"])
        
        totals_data.append(["", "", "", "Grand Total:", f"Rs. {total:,.2f}"])
        
        totals_table = Table(totals_data, colWidths=[0.5*inch, 3.5*inch, 0.75*inch, 1.25*inch, 1.25*inch])
        totals_table.setStyle([
            ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (3, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (3, -1), (-1, -1), 12),
            ('TEXTCOLOR', (3, -1), (-1, -1), colors.HexColor('#4F46E5')),
            ('LINEABOVE', (3, -1), (-1, -1), 2, colors.HexColor('#4F46E5')),
            ('TOPPADDING', (3, -1), (-1, -1), 8),
        ])
        
        elements.append(totals_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Footer
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
        elements.append(Spacer(1, 0.1*inch))
        
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=9,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#666666')
        )
        # Remove emoji from footer
        elements.append(Paragraph("Thank you for your business!", footer_style))
        # REMOVED: computer-generated message
        
        doc.build(elements)
        return True
    except Exception as e:
        print(f"Error generating PDF: {e}")
        raise

def upload_bill_to_firebase(local_file, bill_name):
    try:
        if bucket is None:
            print("⚠️ Storage bucket not available, skipping cloud upload")
            return None
            
        blob = bucket.blob(f"bills/{bill_name}")
        blob.upload_from_filename(local_file)
        blob.make_public()
        return blob.public_url
    except Exception as e:
        print(f"⚠️ Error uploading to Firebase (continuing without cloud upload): {e}")
        return None

def build_whatsapp_message(items, subtotal, discount_amount, discount_type, total, customer_name="", invoice_title="Tax Invoice"):
    """Build a professional WhatsApp message for the bill"""
    
    # Header with store branding
    # Professional & Simple Header
    message = "*🏪 GMR FIREWORKS*\n"
    message += f"{invoice_title}\n"
    message += "──────────────────────\n"
    
    # Customer & Date (Compact)
    if customer_name:
        message += f"👤 *{customer_name}*\n"
        
    from datetime import datetime
    message += f"📅 {get_ist_time().strftime('%d-%b-%Y')} | ⏰ {get_ist_time().strftime('%I:%M %p')}\n"
    message += "──────────────────────\n"
    
    # Items List (Clean)
    for item in items:
        line_total = item['qty'] * item['price']
        message += f"• *{item['name']}*\n"
        message += f"   {item['qty']} × ₹{item['price']:,} = *₹{line_total:,.2f}*\n"
    
    message += "──────────────────────\n"
    
    # Payment Details
    if discount_amount > 0:
        message += f"Subtotal: ₹{subtotal:,.2f}\n"
        discount_label = discount_type.replace("Discount", "").strip()
        message += f"Discount: -₹{discount_amount:,.2f}\n"
    
    message += f"*GRAND TOTAL: ₹{total:,.2f}*\n"
    message += "──────────────────────\n\n"
    
    message += "🙏 *Thank you for your business!*"
    
    return urllib.parse.quote(message)

def generate_bill_html(items, subtotal, discount_amount, discount_type, total, customer_name, customer_phone, payment_method="", invoice_title="TAX INVOICE"):
    """Generate an HTML representation of the bill for preview"""
    sett = get_settings()
    store_name = sett.get("store_name", "MY STORE").upper()
    store_address = sett.get("address", "Set Address in Settings")
    store_phone = sett.get("phone", "")
    store_email = sett.get("email", "")
    
    html = f"""
    <div style="background-color: white; padding: 30px; border: 1px solid #e2e8f0; border-radius: 12px; max-width: 800px; margin: 0 auto; font-family: 'Inter', sans-serif; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);">
        <!-- Header -->
        <div style="text-align: center; margin-bottom: 20px;">
            <h1 style="color: #4F46E5; margin: 0; font-size: 24px; font-weight: 800;">🏪 {store_name}</h1>
            <p style="color: #64748b; font-size: 13px; margin: 5px 0;">{store_address}</p>
            <p style="color: #64748b; font-size: 13px; margin: 5px 0;">{"Phone: " + store_phone if store_phone else ""} {"| Email: " + store_email if store_email else ""}</p>
        </div>
        
        <hr style="border: 0; border-top: 2px solid #4F46E5; margin: 20px 0; opacity: 0.2;">
        
        <h2 style="text-align: center; color: #333; margin-bottom: 20px;">{invoice_title}</h2>
        
        <!-- Info -->
        <div style="display: flex; justify-content: space-between; margin-bottom: 30px;">
            <div style="width: 48%;">
                <p style="margin: 0; font-weight: bold;">Bill To:</p>
                <p style="margin: 5px 0; color: #333;">{customer_name}</p>
                <p style="margin: 0; color: #666; font-size: 14px;">Phone: {customer_phone if customer_phone else 'N/A'}</p>
            </div>
            <div style="width: 48%; text-align: right;">
                <p style="margin: 2px 0; font-size: 14px;"><b>Date:</b> {get_ist_time().strftime('%d-%m-%Y')}</p>
                <p style="margin: 2px 0; font-size: 14px;"><b>Time:</b> {get_ist_time().strftime('%I:%M %p')}</p>
                <p style="margin: 2px 0; font-size: 14px;"><b>Payment:</b> {payment_method if payment_method else 'Not Specified'}</p>
            </div>
        </div>
        
        <!-- Table -->
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
            <thead style="background-color: #1f77b4; color: white;">
                <tr>
                    <th style="padding: 10px; text-align: center; border: 1px solid #1f77b4;">#</th>
                    <th style="padding: 10px; text-align: left; border: 1px solid #1f77b4;">Item Description</th>
                    <th style="padding: 10px; text-align: center; border: 1px solid #1f77b4;">Qty</th>
                    <th style="padding: 10px; text-align: right; border: 1px solid #1f77b4;">Price</th>
                    <th style="padding: 10px; text-align: right; border: 1px solid #1f77b4;">Amount</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for idx, item in enumerate(items, 1):
        line_total = item['qty'] * item['price']
        html += f"""
                <tr>
                    <td style="padding: 8px; text-align: center; border: 1px solid #e5e7eb;">{idx}</td>
                    <td style="padding: 8px; text-align: left; border: 1px solid #e5e7eb;">{item['name']}</td>
                    <td style="padding: 8px; text-align: center; border: 1px solid #e5e7eb;">{item['qty']}</td>
                    <td style="padding: 8px; text-align: right; border: 1px solid #e5e7eb;">₹{item['price']:,.2f}</td>
                    <td style="padding: 8px; text-align: right; border: 1px solid #e5e7eb;">₹{line_total:,.2f}</td>
                </tr>
        """
        
    html += f"""
            </tbody>
        </table>
        
        <!-- Totals -->
        <div style="display: flex; justify-content: flex-end;">
            <div style="width: 50%;">
                <div style="display: flex; justify-content: space-between; padding: 5px 0;">
                    <span>Subtotal:</span>
                    <span>₹{subtotal:,.2f}</span>
                </div>
    """
    
    if discount_amount > 0:
        discount_label = discount_type.replace("Discount", "").strip()
        html += f"""
                <div style="display: flex; justify-content: space-between; padding: 5px 0; color: #ef4444;">
                    <span>Discount ({discount_label}):</span>
                    <span>- ₹{discount_amount:,.2f}</span>
                </div>
        """
        
    html += f"""
                <div style="display: flex; justify-content: space-between; padding: 10px 0; border-top: 2px solid #1f77b4; font-weight: bold; color: #1f77b4; font-size: 18px; margin-top: 5px;">
                    <span>Grand Total:</span>
                    <span>₹{total:,.2f}</span>
                </div>
            </div>
        </div>
        
        <!-- Footer -->
        <div style="margin-top: 30px; text-align: center; color: #666; font-size: 12px; border-top: 1px solid #e5e7eb; padding-top: 20px;">
            <p style="margin: 5px 0;">Thank you for your business! 🙏</p>
        </div>
    </div>
    """
    return html


def generate_thermal_bill_html(items, subtotal, discount_amount, discount_type, total, customer_name, customer_phone, payment_method="", invoice_title="TAX INVOICE"):
    """Generate a high-contrast, compact HTML for 58mm/80mm thermal printers."""
    sett = get_settings()
    store_name = sett.get("store_name", "MY STORE").upper()
    store_address = sett.get("address", "Set Address in Settings")
    store_phone = sett.get("phone", "")
    
    html = f"""
    <html>
    <head>
        <style>
            @media print {{
                body {{ margin: 0; padding: 0; width: 80mm; }}
                @page {{ size: 80mm auto; margin: 0; }}
            }}
            body {{
                font-family: 'Courier New', Courier, monospace;
                width: 72mm;
                margin: 0 auto;
                padding: 5px;
                font-size: 12px;
                line-height: 1.2;
                color: black;
            }}
            .text-center {{ text-align: center; }}
            .text-right {{ text-align: right; }}
            .bold {{ font-weight: bold; }}
            .dashed-line {{ border-top: 1px dashed black; margin: 5px 0; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th {{ border-bottom: 1px dashed black; padding: 2px 0; }}
            td {{ padding: 2px 0; }}
            .total-row {{ font-size: 14px; font-weight: bold; margin-top: 5px; }}
        </style>
    </head>
    <body onload="window.print();">
        <div class="text-center">
            <div class="bold" style="font-size: 16px;">{store_name}</div>
            <div style="font-size: 10px;">{store_address}</div>
            {"<div style='font-size: 10px;'>Phone: " + store_phone + "</div>" if store_phone else ""}
        </div>
        
        <div class="dashed-line"></div>
        <div class="text-center bold">{invoice_title}</div>
        <div class="dashed-line"></div>
        
        <div>Date: {get_ist_time().strftime('%d-%m-%Y')}</div>
        <div>Time: {get_ist_time().strftime('%I:%M %p')}</div>
        {f"<div>Cust: {customer_name}</div>" if customer_name else ""}
        {f"<div>Ph: {customer_phone}</div>" if customer_phone else ""}
        {f"<div>Pay: {payment_method}</div>" if payment_method else ""}
        
        <div class="dashed-line"></div>
        
        <table>
            <thead>
                <tr>
                    <th align="left">ITEM</th>
                    <th align="center">QTY</th>
                    <th align="right">AMT</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for item in items:
        line_total = item['qty'] * item['price']
        html += f"""
                <tr>
                    <td align="left">{item['name'][:18]}</td>
                    <td align="center">{item['qty']}</td>
                    <td align="right">{line_total:,.0f}</td>
                </tr>
        """
        
    html += f"""
            </tbody>
        </table>
        
        <div class="dashed-line"></div>
        
        <div class="text-right">Subtotal: {subtotal:,.2f}</div>
        {f"<div class='text-right'>Disc: -{discount_amount:,.2f}</div>" if discount_amount > 0 else ""}
        <div class="text-right total-row">TOTAL: ₹{total:,.2f}</div>
        
        <div class="dashed-line"></div>
        <div class="text-center" style="margin-top: 10px;">
            THANK YOU! VISIT AGAIN<br>
            *** GMR FIREWORKS ***
        </div>
    </body>
    </html>
    """
    return html


def trigger_thermal_print(html_content):
    """Utility to inject a hidden print trigger component."""
    import streamlit.components.v1 as components
    # We use a hidden iframe to trigger print without affecting the main UI
    print_js = f"""
    <iframe id="receiptFrame" style="display:none;"></iframe>
    <script>
        const doc = document.getElementById('receiptFrame').contentWindow.document;
        doc.open();
        doc.write({json.dumps(html_content)});
        doc.close();
        // The onload in HTML will trigger window.print()
    </script>
    """
    components.html(print_js, height=0, width=0)


