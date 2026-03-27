import streamlit as st
from firebase_config import db
from datetime import datetime, timedelta
import pandas as pd
import urllib.parse
from utils import inject_custom_css, render_sidebar, get_ist_time, check_admin, get_settings, clear_dashboard_cache

st.set_page_config(page_title="Credit Book", page_icon="📙", layout="wide", initial_sidebar_state="expanded")
inject_custom_css()
render_sidebar()
check_admin()

st.title("📙 Credit Book")
st.caption("Manage customer dues (Udhaar). Record repayments and send WhatsApp reminders.")

# ═══════════════════════════════════════════════════════════════
# DATA LAYER
# ═══════════════════════════════════════════════════════════════
@st.cache_data(ttl=180, show_spinner=False)
def get_credit_summary():
    """
    Returns a dict { customer_key: {name, phone, total_credit, total_paid, balance, last_date} }
    Optimized to avoid Firestore composite index requirement while maintaining speed.
    """
    customers = {}
    
    # Fetch credit sales. Sorting is done in Python to avoid needing a Firestore composite index.
    credit_sales = db.collection("sales") \
                     .where("payment_method", "in", ["Credit / Due", "Credit/Due"]) \
                     .stream()
                     
    for doc in credit_sales:
        d = doc.to_dict()
        if d.get("voided", False): continue
        
        name = d.get("customer_name", "Unknown").strip()
        phone = d.get("customer_phone", "").strip()
        key = f"{name.lower()}_{phone}"
        
        if key not in customers:
            customers[key] = {
                "name": name, 
                "phone": phone, 
                "total_credit": 0, 
                "total_paid": 0, 
                "last_date": d.get("date", "")
            }
        
        customers[key]["total_credit"] += d.get("total", 0)
        # Update last_date if this sale is newer
        if d.get("date", "") > customers[key]["last_date"]:
            customers[key]["last_date"] = d.get("date", "")

    # 2. Fetch all repayments
    repayments = db.collection("credit_payments").stream()
    for doc in repayments:
        d = doc.to_dict()
        name = d.get("customer_name", "").strip()
        phone = d.get("customer_phone", "").strip()
        key = f"{name.lower()}_{phone}"
        if key in customers:
            customers[key]["total_paid"] += d.get("amount", 0)

    # 3. Calculate final balances
    result = []
    for c in customers.values():
        c["balance"] = max(0, c["total_credit"] - c["total_paid"])
        if c["balance"] > 1:
            result.append(c)
            
    # Sort by balance descending (highest dues first)
    result.sort(key=lambda x: x["balance"], reverse=True)
    return result

# ═══════════════════════════════════════════════════════════════
# METRICS BAR
# ═══════════════════════════════════════════════════════════════
try:
    with st.spinner("Loading credit summary..."):
        records = get_credit_summary()

    if not records:
        st.success("🎉 Great news — no outstanding dues! All credit customers have paid.")
        st.stop()

    total_outstanding = sum(r["balance"] for r in records)
    m1, m2, m3 = st.columns(3)
    m1.metric("💰 Total Outstanding", f"₹{total_outstanding:,.2f}")
    m2.metric("👥 Credit Customers", len(records))
    m3.metric("📅 As of", get_ist_time().strftime("%d %b %Y, %I:%M %p"))

    st.markdown("---")

    # Search
    sq = st.text_input("🔍 Search by name or phone", placeholder="Type to filter…")
    if sq:
        records = [r for r in records if sq.lower() in r["name"].lower() or sq in r["phone"]]

    # ═══════════════════════════════════════════════════════════════
    # CUSTOMER CARDS
    # ═══════════════════════════════════════════════════════════════
    store_name = get_settings().get("store_name", "Our Store")

    for idx, rec in enumerate(records):
        bal   = rec["balance"]
        paid  = rec["total_paid"]
        total = rec["total_credit"]
        pct   = int((paid / total * 100)) if total > 0 else 0

        with st.container(border=True):
            hdr1, hdr2 = st.columns([4, 2])
            with hdr1:
                st.markdown(f"### {rec['name']}")
                st.caption(f"📞 {rec['phone'] or 'No phone'} &nbsp; | &nbsp; 🗓 Last purchase: {rec['last_date']}")
                st.progress(pct, text=f"Paid ₹{paid:,.0f} of ₹{total:,.0f} ({pct}%)")
            with hdr2:
                color = "#dc2626" if bal > 5000 else "#ea580c" if bal > 1000 else "#92400e"
                st.markdown(f"<div style='text-align:right;'><div style='font-size:13px;color:#64748b;'>Outstanding Balance</div><div style='font-size:28px;font-weight:700;color:{color};'>₹{bal:,.2f}</div></div>", unsafe_allow_html=True)

            st.divider()
            ac1, ac2, ac3 = st.columns(3)

            # RECEIVE PAYMENT BUTTON
            with ac1:
                if st.button("💰 Receive Payment", key=f"pay_{idx}", use_container_width=True, type="primary"):
                    st.session_state[f"payment_modal_{idx}"] = not st.session_state.get(f"payment_modal_{idx}", False)

            # WHATSAPP REMINDER
            with ac2:
                if rec["phone"] and len(rec["phone"]) >= 10:
                    ph  = rec["phone"].replace(" ", "").replace("-", "")
                    if not ph.startswith("91") and len(ph) == 10: ph = "91" + ph
                    msg = (f"*{store_name}* — Payment Reminder\n\n"
                           f"Dear *{rec['name']}*,\n"
                           f"Your outstanding balance is *₹{bal:,.2f}*.\n"
                           f"Total credit: ₹{total:,.2f} | Paid: ₹{paid:,.2f}\n\n"
                           f"Please arrange payment at your earliest convenience.\nThank you! 🙏")
                    wa = f"https://wa.me/{ph}?text={urllib.parse.quote(msg)}"
                    st.link_button("📲 WhatsApp Reminder", wa, use_container_width=True)
                else:
                    st.button("📲 No Phone", disabled=True, use_container_width=True)

            # VIEW HISTORY
            with ac3:
                if st.button("📜 View History", key=f"hist_{idx}", use_container_width=True):
                    st.session_state[f"show_hist_{idx}"] = not st.session_state.get(f"show_hist_{idx}", False)

            # PAYMENT FORM
            if st.session_state.get(f"payment_modal_{idx}", False):
                with st.container(border=True):
                    st.markdown(f"**Record Payment from {rec['name']}**")
                    pf1, pf2 = st.columns(2)
                    with pf1:
                        pay_amt  = st.number_input("Amount Received (₹)", min_value=0.01, max_value=float(bal), value=float(bal), key=f"pamt_{idx}", format="%.2f")
                    with pf2:
                        pay_meth = st.selectbox("Mode", ["Cash", "UPI / GPay", "Bank Transfer", "Cheque"], key=f"pmeth_{idx}")
                    pay_note = st.text_input("Notes (optional)", key=f"pnote_{idx}")

                    ps, pc = st.columns(2)
                    if ps.button("✅ Confirm Payment", key=f"pconf_{idx}", type="primary", use_container_width=True):
                        db.collection("credit_payments").add({
                            "customer_name":  rec["name"],
                            "customer_phone": rec["phone"],
                            "amount":         pay_amt,
                            "payment_method": pay_meth,
                            "notes":          pay_note,
                            "date":           get_ist_time().strftime("%Y-%m-%d"),
                            "timestamp":      get_ist_time(),
                        })
                        get_credit_summary.clear()
                        clear_dashboard_cache()
                        st.toast(f"✅ ₹{pay_amt:,.2f} recorded from {rec['name']}")
                        st.rerun()
                    if pc.button("Cancel", key=f"pcan_{idx}", use_container_width=True):
                        st.session_state[f"payment_modal_{idx}"] = False
                        st.rerun()

            # PAYMENT HISTORY
            if st.session_state.get(f"show_hist_{idx}", False):
                with st.container(border=True):
                    st.markdown(f"**Payment history for {rec['name']}**")
                    hist_docs = db.collection("credit_payments") \
                        .where("customer_name", "==", rec["name"]) \
                        .where("customer_phone", "==", rec["phone"]) \
                        .order_by("date", direction="DESCENDING").stream()
                    hist_rows = []
                    for h in hist_docs:
                        hd = h.to_dict()
                        hist_rows.append({"Date": hd.get("date"), "Amount": f"₹{hd.get('amount',0):,.2f}", "Mode": hd.get("payment_method"), "Notes": hd.get("notes","")})
                    if hist_rows:
                        st.dataframe(pd.DataFrame(hist_rows), use_container_width=True, hide_index=True)
                    else:
                        st.info("No payments recorded yet.")

except Exception as e:
    st.error(f"Error: {e}")
    import traceback; st.code(traceback.format_exc())
