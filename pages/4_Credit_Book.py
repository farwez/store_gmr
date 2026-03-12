import streamlit as st
from firebase_config import db
from datetime import datetime
import pandas as pd
from utils import inject_custom_css, render_sidebar, get_ist_time, check_admin
import urllib.parse

st.set_page_config(page_title="Credit Book", page_icon="📙", layout="wide")
inject_custom_css()
render_sidebar()
check_admin()

st.title("📙 Customer Credit Book")
st.markdown("Track unpaid balances (Udhaar) and receive payments.")
st.markdown("---")

# 1. Fetch Sales that were "Credit/Due"
@st.cache_data(ttl=60)
def fetch_credit_data():
    all_sales = db.collection("sales").where("payment_method", "==", "Credit/Due").stream()
    all_payments = db.collection("credit_payments").stream()
    
    customers = {}
    
    # Process Credit Sales
    for sale in all_sales:
        data = sale.to_dict()
        name = data.get("customer_name", "Unknown").strip()
        phone = data.get("customer_phone", "").strip()
        total = data.get("total", 0)
        
        # Unique customer key (name + phone)
        cust_key = f"{name}_{phone}"
        
        if cust_key not in customers:
            customers[cust_key] = {
                "name": name,
                "phone": phone,
                "total_credit": 0,
                "total_paid": 0,
                "balance": 0,
                "last_purchase_date": data.get("date", "")
            }
        
        customers[cust_key]["total_credit"] += total
        # keep the most recent purchase date
        sale_date = data.get("date", "")
        if sale_date > customers[cust_key]["last_purchase_date"]:
            customers[cust_key]["last_purchase_date"] = sale_date
            
    # Process Repayments
    for pmt in all_payments:
        data = pmt.to_dict()
        name = data.get("customer_name", "").strip()
        phone = data.get("customer_phone", "").strip()
        amount = data.get("amount", 0)
        
        cust_key = f"{name}_{phone}"
        if cust_key in customers:
             customers[cust_key]["total_paid"] += amount
             
    # Calculate Balance
    active_credits = []
    for k, v in customers.items():
        balance = v["total_credit"] - v["total_paid"]
        v["balance"] = balance
        if balance > 0:
            active_credits.append(v)
            
    return active_credits

try:
    with st.spinner("Loading credit records..."):
         credit_records = fetch_credit_data()
         
    if not credit_records:
        st.success("🎉 No outstanding credit! All customers have paid.")
        st.stop()
        
    # Calculate overall metrics
    total_outstanding = sum(c["balance"] for c in credit_records)
    total_customers_due = len(credit_records)
    
    col_met1, col_met2, col_met3 = st.columns(3)
    with col_met1:
        st.metric("₹ Total Outstanding", f"₹{total_outstanding:,.2f}")
    with col_met2:
        st.metric("👥 Customers with Dues", total_customers_due)
    with col_met3:
        st.metric("📅 Last Updated", get_ist_time().strftime("%I:%M %p"))
        
    st.markdown("---")
    
    # Search and Filter
    col_search, col_space = st.columns([1, 2])
    with col_search:
        search_query = st.text_input("🔍 Search Customer", placeholder="Name or Phone...")
    
    if search_query:
        query_lower = search_query.lower()
        filtered_records = [
            c for c in credit_records 
            if query_lower in c['name'].lower() or query_lower in c['phone']
        ]
    else:
        filtered_records = credit_records
        
    filtered_records.sort(key=lambda x: x['balance'], reverse=True) # Sort by largest due first

    st.subheader("📋 Active Credit Accounts")
    
    for record in filtered_records:
        st.markdown(f"""
            <div style='background: white; padding: 20px; border-radius: 12px; border: 1px solid #e2e8f0; margin-bottom: 15px;'>
                <div style='display: flex; justify-content: space-between; align-items: center;'>
                    <div>
                        <h4 style='margin: 0; color: #1e293b;'>{record['name']}</h4>
                        <div style='color: #64748b; font-size: 14px; margin-top: 5px;'>📞 {record['phone'] if record['phone'] else 'No Phone'}</div>
                        <div style='color: #64748b; font-size: 13px; margin-top: 2px;'>📅 Last Purchase: {record['last_purchase_date']}</div>
                    </div>
                    <div style='text-align: right;'>
                        <div style='font-size: 12px; color: #64748b;'>Outstanding Balance</div>
                        <div style='color: #ef4444; font-size: 24px; font-weight: bold;'>₹{record['balance']:,.2f}</div>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        col_act1, col_act2, col_act3 = st.columns([1, 1, 2])
        with col_act1:
            if st.button(f"💰 Receive Payment", key=f"pay_{record['name']}_{record['phone']}", use_container_width=True):
                st.session_state[f"show_payment_modal_{record['name']}"] = True
                
        with col_act2:
            if record['phone']:
                from utils import get_settings
                store_name = get_settings().get("store_name", "GMR STORE").upper()
                msg = f"*Important Update off {store_name}*\n\n"
                msg += f"Dear {record['name']},\n"
                msg += f"Your pending balance is *₹{record['balance']:,.2f}*.\n"
                msg += f"Kindly arrange for the payment at your earliest convenience.\n"
                msg += "Thank you!"
                
                # Format Indian number if needed
                ph = record['phone']
                if not ph.startswith("+91") and len(ph) == 10:
                    ph = "+91" + ph
                    
                wa_link = f"https://wa.me/{ph.replace('+', '')}?text={urllib.parse.quote(msg)}"
                st.link_button("📲 Send Reminder", wa_link, use_container_width=True)
        
        # Payment Form pop-in logic
        if st.session_state.get(f"show_payment_modal_{record['name']}", False):
            with st.container():
                st.markdown("<div style='background: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #cbd5e1; margin-top: 5px;'>", unsafe_allow_html=True)
                st.markdown(f"**Receive Payment from {record['name']}**")
                
                form_col1, form_col2 = st.columns(2)
                with form_col1:
                    pay_amount = st.number_input("Amount Received (₹)", min_value=1.0, max_value=float(record['balance']), value=float(record['balance']), key=f"amt_{record['name']}")
                with form_col2:
                    pay_method = st.selectbox("Payment Method", ["Cash", "UPI", "Card", "Bank Transfer"], key=f"meth_{record['name']}")
                
                submit_col1, submit_col2 = st.columns(2)
                with submit_col1:
                    if st.button("✅ Confirm Payment", type="primary", key=f"conf_{record['name']}", use_container_width=True):
                        # Save payment
                        pmt_data = {
                            "customer_name": record['name'],
                            "customer_phone": record['phone'],
                            "amount": pay_amount,
                            "payment_method": pay_method,
                            "date": get_ist_time().strftime("%Y-%m-%d"),
                            "timestamp": get_ist_time()
                        }
                        db.collection("credit_payments").add(pmt_data)
                        st.cache_data.clear()
                        st.session_state[f"show_payment_modal_{record['name']}"] = False
                        st.toast("✅ Payment Recorded Successfully!")
                        st.rerun()
                with submit_col2:
                    if st.button("❌ Cancel", key=f"canc_{record['name']}", use_container_width=True):
                        st.session_state[f"show_payment_modal_{record['name']}"] = False
                        st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
                
        st.markdown("<br>", unsafe_allow_html=True)

except Exception as e:
    st.error(f"Error loading credit book: {e}")
    import traceback
    st.code(traceback.format_exc())
