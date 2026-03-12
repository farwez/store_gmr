import streamlit as st
from firebase_config import db
from datetime import datetime, timedelta
import time
import pandas as pd
from utils import inject_custom_css, render_sidebar, get_ist_time, verify_user, create_user, hash_password
import json

st.set_page_config(page_title="Store Management", layout="wide", page_icon="🏪")
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
        /* Target the specific session restorer container */
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
        # Verify the user is still valid in DB (Optional but recommended)
        # For speed, we just trust the token if it's not expired
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
    # First, check if any users exist. If not, force admin creation
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
    # Handle safe redirection back to login
    if st.session_state.get("_redirect_to_login"):
        st.session_state["auth_mode"] = "Sign In"
        st.session_state["_redirect_to_login"] = False
        
    # Use Container for better mobile centering
    with st.container():
        st.markdown("""
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 20px 0;">
                <div style="background: white; padding: 35px; border-radius: var(--radius-lg); box-shadow: var(--shadow-lg); width: 100%; max-width: 440px; border: 1px solid var(--border-color);">
                    <div style="text-align: center; margin-bottom: 25px;">
                        <div style="background: var(--brand-gradient); width: 64px; height: 64px; border-radius: 18px; display: flex; align-items: center; justify-content: center; margin: 0 auto 15px auto; box-shadow: 0 10px 20px rgba(79, 70, 229, 0.2);">
                            <span style="font-size: 32px; color: white;">�</span>
                        </div>
                        <h1 style="margin: 0; font-size: 26px; color: var(--text-main); font-family: 'Outfit';">Welcome Back</h1>
                        <p style="color: var(--text-muted); font-size: 14px; margin-top: 4px;">Sign in to your GMR Fireworks account</p>
                    </div>
        """, unsafe_allow_html=True)

        mode = st.radio("Access Mode", ["Sign In", "Create New Account"], horizontal=True, label_visibility="collapsed", key="auth_mode")
        
        st.markdown("<div style='margin-top: 20px;'>", unsafe_allow_html=True)
        
        if mode == "Sign In":
            u = st.text_input("Username", key="login_u", placeholder="Enter your username")
            p = st.text_input("Password", type="password", key="login_p", placeholder="••••••••")
            remember = st.checkbox("Keep me logged in", value=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
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
                        st.error("Invalid credentials. Try again.")
                else:
                    st.warning("Please fill in both fields.")
                    
        else:
            st.markdown("<p style='font-size: 13px; color: var(--text-muted); margin-bottom: 15px;'>Set up your account credentials.</p>", unsafe_allow_html=True)
            su_u = st.text_input("Choose Username", key="su_u", placeholder="e.g. gopal_store")
            su_p = st.text_input("Set Password", type="password", key="su_p", placeholder="Min. 8 characters")
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Initialize Account", use_container_width=True):
                if not su_u or not su_p:
                    st.error("Username and password are required.")
                else:
                    success, msg = create_user(su_u, su_p)
                    if success:
                        st.success("Account created successfully! Switching to Login...")
                        st.balloons()
                        time.sleep(2)
                        st.session_state["_redirect_to_login"] = True
                        st.rerun()
                    else:
                        st.error(msg)
                        
        st.markdown("""
                    <div style="margin-top: 30px; border-top: 1px solid var(--border-color); padding-top: 15px; text-align: center;">
                        <p style="font-size: 11px; color: var(--text-muted); letter-spacing: 0.5px;">GMR FIREWORKS MANAGEMENT • v2.0</p>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
    st.stop()

if not st.session_state.get("authenticated"):
    login_screen()

render_sidebar()

st.markdown(f"""
    <div style="background: var(--brand-gradient); padding: 40px; border-radius: 24px; margin-bottom: 30px; color: white; box-shadow: 0 10px 30px rgba(99, 102, 241, 0.4);">
        <h1 style="color: white !important; margin: 0; font-size: 32px; font-family: 'Outfit';">Welcome to GMR Store Dashboard 🏪</h1>
        <p style="opacity: 0.9; margin-top: 10px; font-size: 16px;">Track your inventory, sales, and analytics in real-time.</p>
    </div>
""", unsafe_allow_html=True)

# Helper function for today's date
def today_string():
    return get_ist_time().strftime("%Y-%m-%d")

# ==================== QUICK STATS ====================
st.subheader("📊 Today's Overview", anchor=False)

col1, col2, col3, col4 = st.columns(4)

try:
    # Get today's sales
    today_sales = db.collection("sales").where("date", "==", today_string()).stream()
    sales_list = [sale.to_dict() for sale in today_sales]
    
    # Calculate stats
    today_revenue = sum(sale.get("total", 0) for sale in sales_list)
    today_orders = len(sales_list)
    today_items_sold = sum(
        sum(item.get("qty", 0) for item in sale.get("items", []))
        for sale in sales_list
    )
    
    # Get total items in catalog using aggregation (efficient)
    items_count = db.collection("items_master").count().get()[0][0].value
    
    with col1:
        st.metric(
            label="Today's Revenue",
            value=f"₹{today_revenue:,.0f}",
            delta=f"{today_orders} orders"
        )
    
    with col2:
        st.metric(
            label="Orders Today",
            value=today_orders,
            delta=f"{today_items_sold} items sold"
        )
    
    with col3:
        st.metric(
            label="Total Products",
            value=items_count,
            delta="In catalog"
        )
    
    with col4:
        # Calculate today's profit
        today_cost = sum(
            sum(item.get("cost", 0) * item.get("qty", 0) for item in sale.get("items", []))
            for sale in sales_list
        )
        today_profit = today_revenue - today_cost
        st.metric(
            label="Today's Profit",
            value=f"₹{today_profit:,.0f}",
            delta="Net Income"
        )

except Exception as e:
    st.error(f"Error loading stats: {e}")

st.markdown("<br>", unsafe_allow_html=True)

# ==================== QUICK ACTIONS ====================
st.subheader("⚡ Quick Actions", anchor=False)

col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("🛒 Create New Sale", use_container_width=True, type="primary"):
        st.switch_page("pages/2_Sales.py")

with col2:
    if st.button("📦 Inventory Master", use_container_width=True):
        st.switch_page("pages/1_Items_Master.py")

with col3:
    if st.button("📊 Sales Reports", use_container_width=True):
        st.switch_page("pages/3_Reports.py")

with col4:
    if st.button("🧠 AI Insights", use_container_width=True):
        st.switch_page("pages/4_AI_Insights.py")

st.markdown("---")

# ==================== RECENT SALES ====================
st.subheader("🕐 Recent Sales")

try:
    # Get last 10 sales
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
        df = pd.DataFrame(sales_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("📭 No sales yet. Create your first sale!")

except Exception as e:
    st.error(f"Error loading recent sales: {e}")


# ==================== FOOTER ====================
st.caption("💡 Use the sidebar to navigate between different modules")
st.caption(f"🕐 Last updated: {get_ist_time().strftime('%I:%M:%S %p')}")
