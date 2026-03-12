import streamlit as st
from firebase_config import db
from datetime import datetime, timedelta
import time
import pandas as pd
from utils import inject_custom_css, render_sidebar, get_ist_time, verify_user, create_user, hash_password
import json

# must be first
st.set_page_config(page_title="Store Management Dashboard", layout="wide", page_icon="🏪", initial_sidebar_state="expanded")
inject_custom_css()

# ==================== SESSION PERSISTENCE ====================
# JavaScript to handle localStorage for persistent login
st.markdown("""
<script>
    const session = localStorage.getItem('gmr_auth_session');
    if (session) {
        const data = JSON.parse(session);
        const now = new Date().getTime();
        if (now < data.expiry) {
            // Fill the hidden input that Streamlit can see
            const input = window.parent.document.querySelector('input[aria-label="session_restorer"]');
            if (input) {
                input.value = session;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                // Trigger Enter to submit the value
                input.dispatchEvent(new KeyboardEvent('keydown', { 'key': 'Enter', 'bubbles': true }));
            }
        }
    }
</script>
""", unsafe_allow_html=True)

# Hidden input for the JS to fill (Completely invisible)
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
        }
    </style>
""", unsafe_allow_html=True)
restored_session = st.text_input("session_restorer", label_visibility="collapsed", key="restore_token")

# Logic to handle the restored session
if restored_session and not st.session_state.get("authenticated"):
    try:
        data = json.loads(restored_session)
        st.session_state["authenticated"] = True
        st.session_state["username"] = data["username"]
        st.session_state["user_name"] = data.get("name", data["username"])
        st.rerun()
    except:
        pass

# Helper to save session to localStorage
def save_persistent_session(username, name=""):
    expiry = (datetime.now() + timedelta(days=7)).timestamp() * 1000
    session_data = json.dumps({"username": username, "expiry": expiry})
    st.markdown(f"""
        <script>
            localStorage.setItem('gmr_auth_session', '{session_data}');
        </script>
    """, unsafe_allow_html=True)

# Check if we need to auto-login (from previous session)
if not st.session_state.get("authenticated"):
    users_count = db.collection("users").count().get()[0][0].value
    if users_count == 0:
        st.info("👋 Welcome! This is your first time setup. Please create an Admin account.")
        with st.container():
            st.subheader("🛠️ Initial Account Setup")
            new_u = st.text_input("Username", key="init_u")
            new_p = st.text_input("Password", type="password", key="init_p")
            if st.button("Create Account", type="primary"):
                if new_u and new_p:
                    success, msg = create_user(new_u, new_p, name="Administrator")
                    if success:
                        st.success("Account created! Please login.")
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.error(msg)
        st.stop()

# ==================== LOGIN / SIGNUP UI ====================
def login_screen():
    if st.session_state.get("_redirect_to_login"):
        st.session_state["auth_mode"] = "Sign In"
        st.session_state["_redirect_to_login"] = False
        
    with st.container():
        st.markdown("""
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 20px 0;">
                <div style="background: white; padding: 35px; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.1); width: 100%; max-width: 440px; border: 1px solid #eef2f6;">
                    <div style="text-align: center; margin-bottom: 25px;">
                        <h1 style="margin: 0; font-size: 26px; color: #1e293b; font-family: 'Outfit';">Welcome Back</h1>
                        <p style="color: #64748b; font-size: 14px; margin-top: 4px;">Sign in to your GMR Store account</p>
                    </div>
        """, unsafe_allow_html=True)

        mode = st.radio("Access Mode", ["Sign In", "Create New Account"], horizontal=True, label_visibility="collapsed", key="auth_mode")
        
        st.markdown("<div style='margin-top: 20px;'>", unsafe_allow_html=True)
        
        if mode == "Sign In":
            u = st.text_input("Username", key="login_u")
            p = st.text_input("Password", type="password", key="login_p")
            remember = st.checkbox("Keep me logged in", value=True)
            if st.button("Unlock Dashboard", use_container_width=True, type="primary"):
                if u and p:
                    user = verify_user(u, p)
                    if user:
                        st.session_state["authenticated"] = True
                        st.session_state["username"] = user["username"]
                        st.session_state["user_name"] = user["name"]
                        if remember:
                            save_persistent_session(u, user["name"])
                        st.rerun()
                    else:
                        st.error("Invalid credentials.")
        else:
            su_u = st.text_input("Choose Username", key="su_u")
            su_p = st.text_input("Set Password", type="password", key="su_p")
            if st.button("Initialize Account", use_container_width=True):
                if su_u and su_p:
                    success, msg = create_user(su_u, su_p)
                    if success:
                        st.success("Account created!")
                        time.sleep(2)
                        st.session_state["_redirect_to_login"] = True
                        st.rerun()
                    else:
                        st.error(msg)
                        
        st.markdown("""
                </div>
            </div>
        """, unsafe_allow_html=True)
    st.stop()

if not st.session_state.get("authenticated"):
    login_screen()

# ==================== MAIN DASHBOARD ====================
render_sidebar()

st.markdown(f"""
    <div style="background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%); padding: 40px; border-radius: 24px; margin-bottom: 30px; color: white; box-shadow: 0 10px 30px rgba(99, 102, 241, 0.4);">
        <h1 style="color: white !important; margin: 0; font-size: 32px; font-family: 'Outfit';">Dashboard 🏪</h1>
        <p style="opacity: 0.9; margin-top: 10px; font-size: 16px;">Welcome back, {st.session_state.get('user_name', 'User')}</p>
    </div>
""", unsafe_allow_html=True)

def today_string():
    return get_ist_time().strftime("%Y-%m-%d")

# ==================== QUICK STATS ====================
st.subheader("📊 Today's Overview", anchor=False)
col1, col2, col3, col4 = st.columns(4)

try:
    today_sales = db.collection("sales").where("date", "==", today_string()).stream()
    sales_list = [sale.to_dict() for sale in today_sales]
    today_revenue = sum(sale.get("total", 0) for sale in sales_list)
    today_orders = len(sales_list)
    today_items_sold = sum(sum(item.get("qty", 0) for item in sale.get("items", [])) for sale in sales_list)
    items_count = db.collection("items_master").count().get()[0][0].value
    
    with col1:
        st.metric("Revenue", f"₹{today_revenue:,.0f}", f"{today_orders} orders")
    with col2:
        st.metric("Orders", today_orders, f"{today_items_sold} items")
    with col3:
        st.metric("Total Products", items_count, "In catalog")
    with col4:
        today_cost = sum(sum(item.get("cost", 0) * item.get("qty", 0) for item in sale.get("items", [])) for sale in sales_list)
        today_profit = today_revenue - today_cost
        st.metric("Profit", f"₹{today_profit:,.0f}", "Net")
except Exception as e:
    st.error(f"Error loading stats: {e}")

st.markdown("<br>", unsafe_allow_html=True)

# ==================== QUICK ACTIONS ====================
st.subheader("⚡ Quick Actions", anchor=False)

# ROW 1
r1c1, r1c2, r1c3 = st.columns(3)
with r1c1:
    if st.button("🛒 Create New Sale", use_container_width=True, type="primary"):
        st.switch_page("pages/2_Sales.py")
with r1c2:
    if st.button("📦 Inventory Master", use_container_width=True):
        st.switch_page("pages/1_Items_Master.py")
with r1c3:
    if st.button("📓 Credit Book (Udhaar)", use_container_width=True):
        st.switch_page("pages/4_Credit_Book.py")

# ROW 2
r2c1, r2c2, r2c3 = st.columns(3)
with r2c1:
    if st.button("💸 Expense Tracker", use_container_width=True):
        st.switch_page("pages/6_Expense_Tracker.py")
with r2c2:
    if st.button("📜 Sales History", use_container_width=True):
        st.switch_page("pages/7_Sales_History.py")
with r2c3:
    if st.button("📊 Reports & Analytics", use_container_width=True):
        st.switch_page("pages/3_Reports.py")

st.markdown("---")

# ==================== RECENT SALES ====================
st.subheader("🕐 Recent Sales")
try:
    recent_sales = db.collection("sales").order_by("timestamp", direction="DESCENDING").limit(10).stream()
    sales_data = []
    for sale in recent_sales:
        data = sale.to_dict()
        sales_data.append({
            "Date": data.get("date", "N/A"),
            "Customer": data.get("customer_name", "N/A"),
            "Items": len(data.get("items", [])),
            "Total": f"₹{data.get('total', 0):,.0f}",
            "Time": data.get("timestamp", get_ist_time()).strftime("%I:%M %p") if isinstance(data.get("timestamp"), datetime) else "N/A"
        })
    if sales_data:
        st.dataframe(pd.DataFrame(sales_data), use_container_width=True, hide_index=True)
    else:
        st.info("📭 No sales yet.")
except Exception as e:
    st.error(f"Error loading recent sales: {e}")

# FOOTER
st.caption(f"🕐 Last updated: {get_ist_time().strftime('%I:%M:%S %p')}")
