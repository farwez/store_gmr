import streamlit as st
from firebase_config import db
from utils import inject_custom_css, render_sidebar, get_settings, check_admin

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")
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

    st.markdown("---")
    
    if st.button("💾 Save Settings", type="primary", use_container_width=True):
        try:
            db.collection("settings").document("store_info").set({
                "store_name": store_name.strip(),
                "phone": phone.strip(),
                "email": email.strip(),
                "address": address.strip(),
                "gstin": gstin.strip(),
                "currency": currency
            })
            st.cache_data.clear() # Clear cache to refresh settings everywhere
            st.success("✅ Settings saved successfully! Refresh the page to see changes.")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error saving settings: {e}")

st.markdown("---")
st.caption("v1.2.0 • Data is stored securely in Firebase")
