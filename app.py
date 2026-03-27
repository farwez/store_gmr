import streamlit as st
from firebase_config import db
from datetime import datetime, timedelta
import time
import pandas as pd
from utils import inject_custom_css, render_sidebar, get_ist_time, verify_user, create_user, enforce_login_and_restore, sign_session_data, get_dashboard_kpis, get_dashboard_alerts, get_recent_transactions, clear_dashboard_cache, get_settings

# must be first
st.set_page_config(page_title="Store Management Dashboard", layout="wide", page_icon="🏪", initial_sidebar_state="expanded")
inject_custom_css()

# ==================== SESSION PERSISTENCE ====================
enforce_login_and_restore()

def save_persistent_session(username, name="", role="user"):
    expiry = (datetime.now() + timedelta(days=30)).timestamp() * 1000
    session_data = {"username": username, "name": name, "role": role, "expiry": expiry}
    signed_session = sign_session_data(session_data)
    st.markdown(f"""
        <script>
            localStorage.setItem('gmr_auth_session', '{signed_session}');
        </script>
    """, unsafe_allow_html=True)

# ==================== FIRST-TIME SETUP ====================
if not st.session_state.get("authenticated"):
    has_any_user = any(db.collection("users").limit(1).stream())
    if not has_any_user:
        st.info("👋 Welcome! First time setup — please create an Admin account.")
        new_u = st.text_input("Username", key="init_u")
        new_p = st.text_input("Password", type="password", key="init_p")
        if st.button("Create Account", type="primary"):
            if new_u and new_p:
                success, msg = create_user(new_u, new_p, name="Administrator")
                if success:
                    st.success("Account created! Please login.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(msg)
        st.stop()

# ==================== LOGIN UI ====================
def login_screen():
    if st.session_state.pop("_force_signin_mode", False):
        st.session_state["auth_mode"] = "Sign In"

    settings = get_settings()
    allow_self_signup = bool(settings.get("allow_self_signup", True))
    
    st.markdown("""
        <style>
        /* Center the radio buttons for login/signup */
        div[role="radiogroup"] {
            justify-content: center !important;
            margin-bottom: 20px;
        }
        /* Make form elements full width and styled properly */
        [data-testid="stForm"] {
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
            padding: 0 !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    with st.container():
        # Layout hack for clean centering
        c1, c2, c3 = st.columns([1, 1.2, 1])
        with c2:
            st.markdown("""
                <div style="text-align:center; padding-top: 5vh; margin-bottom: 30px;">
                    <div style="background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); width: 75px; height: 75px; border-radius: 22px; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px auto; box-shadow: 0 10px 25px rgba(79, 70, 229, 0.4);">
                        <span style="font-size: 38px;">🏪</span>
                    </div>
                    <h1 style="margin:0;font-size:32px;color:#1e293b;font-weight:800;letter-spacing:-0.5px;">Welcome Back</h1>
                    <p style="color:#64748b;font-size:16px;margin-top:8px;">Sign in to manage your store securely.</p>
                </div>
            """, unsafe_allow_html=True)

            mode_options = ["Sign In"] + (["Create Account"] if allow_self_signup else [])
            mode = st.radio("Mode", mode_options, horizontal=True, label_visibility="collapsed", key="auth_mode")

            if mode == "Sign In":
                with st.container(border=True):
                    with st.form("login_form", clear_on_submit=False):
                        st.markdown("<h4 style='margin-bottom:15px;color:#334155;'>Account Login</h4>", unsafe_allow_html=True)
                        u = st.text_input("Username", key="login_u", placeholder="Enter your username")
                        p = st.text_input("Password", type="password", key="login_p", placeholder="Enter your password")
                        remember = st.checkbox("Keep me logged in for 30 days", value=True)
                        
                        st.markdown("<br>", unsafe_allow_html=True)
                        submitted = st.form_submit_button("Secure Login ➔", use_container_width=True, type="primary")
                        
                        if submitted:
                            if u.strip() and p.strip():
                                user = verify_user(u.strip(), p.strip())
                                if user:
                                    st.session_state["authenticated"] = True
                                    st.session_state["username"] = user["username"]
                                    st.session_state["user_name"] = user["name"]
                                    st.session_state["user_role"] = user.get("role", "user")
                                    if remember:
                                        save_persistent_session(user["username"], user["name"], user.get("role", "user"))
                                    st.success("Access Granted! Redirecting...")
                                    time.sleep(0.5)
                                    st.rerun()
                                else:
                                    st.error("❌ Invalid username or password. Please try again.")
                            else:
                                st.warning("⚠️ Please enter both username and password.")
            
            else:
                with st.container(border=True):
                    with st.form("signup_form", clear_on_submit=False):
                        st.markdown("<h4 style='margin-bottom:15px;color:#334155;'>Register Staff</h4>", unsafe_allow_html=True)
                        su_n = st.text_input("Display Name", key="su_n", placeholder="E.g. John Doe", help="How your name will appear on the dashboard")
                        su_u = st.text_input("Choose Username", key="su_u", placeholder="E.g. johndoe123")
                        su_p = st.text_input("Set Password", type="password", key="su_p", placeholder="Minimum 6 characters")
                        
                        st.markdown("<br>", unsafe_allow_html=True)
                        submitted = st.form_submit_button("Create Account ✨", use_container_width=True, type="primary")
                        
                        if submitted:
                            if not su_u.strip() or not su_p.strip():
                                st.warning("⚠️ Username and password are required.")
                            elif len(su_p.strip()) < 6:
                                st.error("🔒 Password must be at least 6 characters for security.")
                            else:
                                with st.spinner("Creating account..."):
                                    success, msg = create_user(su_u.strip(), su_p.strip(), name=(su_n.strip() or su_u.strip()), role="user")
                                    if success:
                                        st.success("🎉 Account created successfully! Switch to Sign In.")
                                        time.sleep(1)
                                        st.session_state["_force_signin_mode"] = True
                                        st.rerun()
                                    else:
                                        st.error(f"❌ Registration Failed: {msg}")

            if not allow_self_signup:
                st.info("ℹ️ Account creation is restricted. Contact your administrator for access.")
                
            st.markdown("""
                <div style="text-align:center;margin-top:25px;">
                    <p style="color:#94a3b8;font-size:13px;">© 2026 Store Management System. All rights reserved.</p>
                </div>
            """, unsafe_allow_html=True)

    st.stop()

if not st.session_state.get("authenticated"):
    login_screen()

# ==================== MAIN DASHBOARD ====================
render_sidebar()

today_str = get_ist_time().strftime("%Y-%m-%d")
current_month = get_ist_time().strftime("%Y-%m")

st.markdown(f"""
    <div style="background: white; padding: 28px 32px; border-radius: 16px; border: 1px solid #e2e8f0; margin-bottom: 32px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.02);">
        <h1 style="color: #0f172a!important; margin: 0; font-size: 28px; font-weight: 800; letter-spacing: -0.5px;">Store Overview</h1>
        <p style="color: #64748b; margin-top: 6px; font-size: 15px; margin-bottom: 0;">Welcome back, <b style="color:#0f172a">{st.session_state.get('user_name', 'Admin')}</b> &nbsp;•&nbsp; {get_ist_time().strftime('%A, %d %B %Y')}</p>
    </div>
""", unsafe_allow_html=True)

# ==================== TODAY'S KPI METRICS ====================
dashboard_load_error = None
try:
    with st.spinner("Loading dashboard data..."):
        kpi = get_dashboard_kpis(today_str)
        alerts = get_dashboard_alerts()
        rows = get_recent_transactions(limit=10)
except Exception as e:
    dashboard_load_error = str(e)
    kpi = {"error": dashboard_load_error}
    alerts = {"low_list": [], "outstanding": 0}
    rows = []

try:
    if "error" in kpi:
        st.error(f"Error loading KPIs: {kpi['error']}")
    else:
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.metric("💰 Today's Sales", f"₹{kpi['gross_revenue']:,.0f}", f"{kpi['today_orders']} orders")
        with k2:
            st.metric("📦 Net Revenue", f"₹{kpi['net_revenue']:,.0f}", f"{kpi['returns_count']} returns", delta_color="inverse")
        with k3:
            st.metric("🧾 Expenses", f"₹{kpi['today_expenses']:,.0f}", "Store costs", delta_color="inverse")
        with k4:
            st.metric("📈 Net Profit", f"₹{kpi['net_profit']:,.0f}", "Est. Today")
except Exception as e:
    st.error(f"Error rendering Dashboard: {e}")

st.markdown("<br>", unsafe_allow_html=True)

# ==================== QUICK ACTIONS & ALERTS ====================
col_left, col_right = st.columns([1.5, 1])

with col_left:
    st.markdown("<h4 style='color:#1e293b; margin-bottom:16px;'>⚡ Quick Actions</h4>", unsafe_allow_html=True)
    q1, q2 = st.columns(2)
    with q1:
        if st.button("🛒 New Sale", use_container_width=True, type="primary"): st.switch_page("pages/2_Sales.py")
        if st.button("📙 Credit Book", use_container_width=True): st.switch_page("pages/4_Credit_Book.py")
    with q2:
        if st.button("📦 Item Master", use_container_width=True): st.switch_page("pages/1_Items_Master.py")
        if st.button("💸 Expenses", use_container_width=True): st.switch_page("pages/6_Expense_Tracker.py")

with col_right:
    st.markdown("<h4 style='color:#1e293b; margin-bottom:16px;'>🔔 Alerts</h4>", unsafe_allow_html=True)
    
    # Outstanding Credit Alert
    outstanding = alerts["outstanding"]
    if outstanding > 0:
        st.warning(f"**₹{outstanding:,.0f}** outstanding debt.")
    else:
        st.success("No outstanding credit! 🎉")
        
    # Low Stock Alert
    low_list = alerts["low_list"]
    if low_list:
        with st.expander(f"⚠️ {len(low_list)} items low on stock", expanded=True):
            for name, stk in low_list[:5]:  # Show top 5 to keep it clean
                color = "#ef4444" if stk == 0 else "#f97316"
                st.markdown(f"<div style='display:flex;justify-content:space-between;font-size:14px;padding:4px 0;border-bottom:1px solid #f1f5f9;'><span style='color:#334155'>{name}</span><b style='color:{color}'>{stk} left</b></div>", unsafe_allow_html=True)
            if len(low_list) > 5:
                st.caption(f"+ {len(low_list)-5} more items...")
    else:
        st.success("Stock levels are healthy.")

st.markdown("<br>", unsafe_allow_html=True)

# ==================== RECENT TRANSACTIONS ====================
st.markdown("<h4 style='color:#1e293b; margin-bottom:16px;'>📜 Recent Transactions</h4>", unsafe_allow_html=True)
try:
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("📭 No sales yet today.")
except Exception as e:
    st.error(f"Error loading transactions: {e}")

st.caption(f"🕐 Last refreshed: {get_ist_time().strftime('%I:%M:%S %p')} IST")
