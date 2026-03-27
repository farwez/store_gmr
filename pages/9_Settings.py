import streamlit as st
from firebase_config import db
from utils import inject_custom_css, render_sidebar, get_settings, check_admin, create_user, set_user_password, change_user_password

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide", initial_sidebar_state="expanded")
inject_custom_css()
render_sidebar()
check_admin()

st.title("⚙️ Store Settings")
st.markdown("---")

# Load current settings
settings = get_settings()

with st.container():
    st.subheader("🏢 Store Branding")
    st.info("These details will appear on all your generated bills and quotations.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        store_name = st.text_input("Store Name", value=settings.get("store_name", "MY STORE"))
        phone = st.text_input("Contact Phone", value=settings.get("phone", ""))
        email = st.text_input("Contact Email", value=settings.get("email", ""))
        
    with col2:
        address = st.text_area("Store Address", value=settings.get("address", ""), height=100)
        gstin = st.text_input("GSTIN (Optional)", value=settings.get("gstin", ""))
        currency = st.selectbox("Currency Symbol", ["₹", "$", "£", "€"], index=0)

    allow_self_signup = st.checkbox(
        "Allow self account creation on login page",
        value=bool(settings.get("allow_self_signup", True)),
        help="If enabled, users can create their own staff accounts from the login screen."
    )

    st.markdown("---")
    
    if st.button("💾 Save Settings", type="primary", use_container_width=True):
        try:
            db.collection("settings").document("store_info").set({
                "store_name": store_name.strip(),
                "phone": phone.strip(),
                "email": email.strip(),
                "address": address.strip(),
                "gstin": gstin.strip(),
                "currency": currency,
                "allow_self_signup": allow_self_signup
            })
            st.cache_data.clear()
            st.toast("✅ Store settings saved!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error saving settings: {e}")

st.markdown("---")
st.caption("v1.2.0 • Data is stored securely in Firebase")


st.markdown("---")
st.subheader("👥 User & Role Management")
st.caption("Manage staff accounts and permissions")

# Load users
@st.cache_data(ttl=30)
def _load_users_for_admin():
    rows = []
    for d in db.collection("users").stream():
        dd = d.to_dict() or {}
        rows.append({
            "doc_id": d.id,
            "username": dd.get("username", d.id),
            "name": dd.get("name", ""),
            "role": dd.get("role", "user"),
            "created_at": dd.get("created_at"),
        })
    rows.sort(key=lambda x: x.get("username", "").lower())
    return rows

users = _load_users_for_admin()
admin_count = sum(1 for u in users if u.get("role") == "admin")

# Create tabs for better organization
um_tab1, um_tab2, um_tab3 = st.tabs(["➕ Create User", "👤 Manage Users", "🔐 Passwords"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: CREATE USER
# ═══════════════════════════════════════════════════════════════════════════════
with um_tab1:
    st.markdown("#### Add New Staff Member")
    
    with st.form("create_user_form", clear_on_submit=True, enter_to_submit=False):
        col1, col2 = st.columns(2)
        
        with col1:
            new_username = st.text_input("👤 Username", placeholder="e.g. staff01", help="Unique login identifier")
            new_name = st.text_input("📝 Display Name", placeholder="e.g. Ravi Kumar", help="Name shown in sales records")
        
        with col2:
            new_password = st.text_input("🔑 Temporary Password", type="password", placeholder="Min 6 characters")
            new_role = st.selectbox("👑 Role", ["👨 Staff (user)", "👨‍💼 Manager (admin)"], 
                                   help="Staff: Can enter sales/returns. Manager: Full access to settings")

        st.markdown("---")
        
        if st.form_submit_button("✅ Create User", type="primary", use_container_width=True):
            if not new_username.strip() or not new_password.strip():
                st.error("❌ Username and password are required.")
            elif len(new_password.strip()) < 6:
                st.error("❌ Password must be at least 6 characters.")
            else:
                role_value = "admin" if "Manager" in new_role else "user"
                ok, msg = create_user(
                    new_username.strip(),
                    new_password.strip(),
                    name=(new_name.strip() or new_username.strip()),
                    role=role_value
                )
                if ok:
                    st.toast(f"✅ {msg}")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: MANAGE USERS
# ═══════════════════════════════════════════════════════════════════════════════
with um_tab2:
    st.markdown("#### Staff Directory")
    
    if not users:
        st.info("ℹ️ No staff members yet. Create one in the 'Create User' tab.")
    else:
        st.caption(f"Total: {len(users)} staff • Managers: {admin_count}")
        st.markdown("---")
        
        for u in users:
            with st.container(border=True):
                col_info, col_role, col_action = st.columns([2.5, 1.5, 1])
                
                # User info
                with col_info:
                    username_display = u.get("username", "")
                    name_display = u.get("name", "")
                    role_badge = "👑 Manager" if u.get("role") == "admin" else "👤 Staff"
                    
                    st.markdown(f"**{username_display}**")
                    st.caption(f"{name_display} • {role_badge}")
                
                # Role selector
                with col_role:
                    current_role = u.get("role", "user")
                    role_options = ["👤 Staff", "👑 Manager"]
                    role_index = 1 if current_role == "admin" else 0
                    selected_role_display = st.selectbox(
                        "Change Role",
                        role_options,
                        index=role_index,
                        key=f"role_select_{u['doc_id']}",
                        label_visibility="collapsed"
                    )
                    selected_role = "admin" if "Manager" in selected_role_display else "user"
                
                # Action button
                with col_action:
                    if st.button("💾 Update", key=f"update_role_{u['doc_id']}", use_container_width=True):
                        if selected_role == current_role:
                            st.info(f"No changes for {username_display}")
                        else:
                            # Validation
                            if current_role == "admin" and selected_role == "user" and admin_count <= 1:
                                st.error("❌ Cannot demote the last manager.")
                            elif u.get("username") == st.session_state.get("username") and current_role == "admin" and selected_role == "user":
                                st.error("❌ You cannot demote your own account.")
                            else:
                                try:
                                    db.collection("users").document(u["doc_id"]).update({"role": selected_role})
                                    st.toast(f"✅ {username_display} is now a {selected_role_display}")
                                    _load_users_for_admin.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Failed: {str(e)[:60]}")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: PASSWORD MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════
with um_tab3:
    pwd_col1, pwd_col2 = st.columns(2)
    
    # Admin password reset
    with pwd_col1:
        st.markdown("#### 🔐 Reset Staff Password")
        st.caption("Only managers can reset other staff passwords")
        
        with st.form("pwd_reset_form", clear_on_submit=True, enter_to_submit=False):
            reset_user = st.selectbox(
                "Select Staff Member",
                options=[u.get("username", "") for u in users] if users else [],
                label_visibility="collapsed"
            )
            reset_new_password = st.text_input("New Password", type="password", placeholder="Min 6 characters")

            if st.form_submit_button("🔑 Reset Password", type="primary", use_container_width=True):
                if not users:
                    st.error("❌ No staff members available.")
                elif not reset_user or not reset_new_password.strip():
                    st.error("❌ Select a staff member and enter password.")
                elif len(reset_new_password.strip()) < 6:
                    st.error("❌ Password must be at least 6 characters.")
                else:
                    ok, msg = set_user_password(reset_user, reset_new_password.strip())
                    if ok:
                        st.toast(f"✅ Password reset for {reset_user}")
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")
    
    # Change own password
    with pwd_col2:
        st.markdown("#### 🔁 Change My Password")
        st.caption("Update your own login password")
        
        with st.form("change_pwd_form", clear_on_submit=True, enter_to_submit=False):
            current_password = st.text_input("Current Password", type="password", placeholder="Enter current password")
            new_password_me = st.text_input("New Password", type="password", placeholder="Min 6 characters")

            if st.form_submit_button("✅ Update Password", type="primary", use_container_width=True):
                if not current_password.strip() or not new_password_me.strip():
                    st.error("❌ Both passwords required.")
                elif len(new_password_me.strip()) < 6:
                    st.error("❌ New password must be at least 6 characters.")
                else:
                    ok, msg = change_user_password(
                        st.session_state.get("username", ""),
                        current_password.strip(),
                        new_password_me.strip(),
                    )
                    if ok:
                        st.toast("✅ Your password updated successfully!")
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")

