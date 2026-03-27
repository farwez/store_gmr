import streamlit as st
import pandas as pd
import io
from firebase_config import db, firestore_module
from datetime import datetime, timedelta
from utils import (
    inject_custom_css, render_sidebar, get_ist_time, check_auth,
    generate_thermal_bill_html, trigger_thermal_print,
    build_whatsapp_message, clear_items_cache, clear_dashboard_cache
)

st.set_page_config(page_title="Sales History", layout="wide", initial_sidebar_state="expanded", page_icon="📜")
inject_custom_css()
check_auth()
render_sidebar()

st.title("📜 Sales History")
st.caption("View, reprint, and void past sales. Export records to Excel for accounting.")

# ─── Date range picker ─────────────────────────────────────────────────────
with st.container(border=True):
    dc1, dc2, dc3 = st.columns([2, 2, 2])
    with dc1:
        mode = st.selectbox("Quick Range", ["Today", "Yesterday", "Last 7 Days", "Last 30 Days", "Custom"])
    with dc2:
        if mode == "Custom":
            start_d = st.date_input("From", value=get_ist_time().date())
        else:
            now = get_ist_time().date()
            if mode == "Today": start_d = now
            elif mode == "Yesterday": start_d = now - timedelta(days=1)
            elif mode == "Last 7 Days": start_d = now - timedelta(days=7)
            elif mode == "Last 30 Days": start_d = now - timedelta(days=30)
    with dc3:
        if mode == "Custom":
            end_d = st.date_input("To", value=get_ist_time().date())
        else:
            now = get_ist_time().date()
            if mode == "Today": end_d = now
            elif mode == "Yesterday": end_d = now - timedelta(days=1)
            else: end_d = now

start_str = start_d.strftime("%Y-%m-%d")
end_str   = end_d.strftime("%Y-%m-%d")

# ─── Fetch with Caching ────────────────────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def fetch_sales_history(s_str, e_str):
    try:
        docs = db.collection("sales") \
                  .where("date", ">=", s_str) \
                  .where("date", "<=", e_str) \
                  .order_by("date", direction="DESCENDING") \
                  .stream()

        results = []
        for d in docs:
            dd = d.to_dict()
            ts = dd.get("timestamp")
            results.append({
                "_id":       d.id,
                "Date":      dd.get("date", ""),
                "Time":      ts.strftime("%I:%M %p") if isinstance(ts, datetime) else "N/A",
                "Customer":  dd.get("customer_name", "N/A"),
                "EnteredBy": dd.get("entered_by") or dd.get("entered_by_username", "N/A"),
                "Phone":     dd.get("customer_phone", ""),
                "Items":     dd.get("items", []),
                "Items_str": ", ".join(f"{i['name']} ×{i['qty']}" for i in dd.get("items", [])),
                "Subtotal":  dd.get("subtotal", dd.get("total", 0)),
                "Discount":  dd.get("discount_amount", 0),
                "Total":     dd.get("total", 0),
                "Payment":   dd.get("payment_method", "Cash"),
                "Dis_type":  dd.get("discount_type", "No Discount"),
                "has_returns": dd.get("has_returns", False),
                "voided":    dd.get("voided", False),
                "_ts_val":   ts.timestamp() if isinstance(ts, datetime) else 0,
            })
        results.sort(key=lambda x: x["_ts_val"], reverse=True)
        return results
    except Exception as e:
        return []

with st.spinner("Retrieving records..."):
    all_rows = fetch_sales_history(start_str, end_str)

# ─── Filtering (Client-side for speed) ────────────────────────────────────
rows = all_rows

if rows:
    active_rows = [r for r in rows if not r["voided"]]
    total_rev  = sum(r["Total"] for r in active_rows)
    total_disc = sum(r["Discount"] for r in active_rows)
    avg_order  = total_rev / len(active_rows) if active_rows else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Sales", len(active_rows))
    m2.metric("Total Revenue", f"₹{total_rev:,.2f}")
    m3.metric("Total Discounts", f"₹{total_disc:,.2f}")
    m4.metric("Avg. Order Value", f"₹{avg_order:,.2f}")

    st.markdown("---")

    # ─── Client-side Filter Bar ─────────────────────────────────────────────
    sf1, sf2 = st.columns(2)
    with sf1:
        search_name = st.text_input("🔍 Search Customer", placeholder="Type name...")
    with sf2:
        payment_filter = st.selectbox("Payment Mode", ["All", "Cash", "UPI / GPay", "Card / POS", "Credit / Due"])

    if search_name:
        rows = [r for r in rows if search_name.lower() in r["Customer"].lower()]
    if payment_filter != "All":
        rows = [r for r in rows if r["Payment"] == payment_filter]

    st.caption(f"Showing {len(rows)} matching transactions")

    # ─── Render List ───────────────────────────────────────────────────────
    for idx, sale in enumerate(rows):
        status_tag = "❌ VOIDED" if sale["voided"] else "🔄 RETURNS" if sale["has_returns"] else "✅"
        bgcolor = "#fff1f2" if sale["voided"] else "white"
        
        with st.container(border=True):
            r_hdr, r_act = st.columns([4, 1])
            with r_hdr:
                st.markdown(f"**{sale['Customer']}** &nbsp; | &nbsp; ₹{sale['Total']:,.2f} &nbsp; | &nbsp; {status_tag}")
                st.caption(f"{sale['Date']} {sale['Time']} • {sale['Payment']} • {sale['EnteredBy']}")
            
            with r_act:
                if st.button("Details", key=f"det_btn_{sale['_id']}", use_container_width=True):
                    st.session_state[f"show_det_{sale['_id']}"] = not st.session_state.get(f"show_det_{sale['_id']}", False)
            
            if st.session_state.get(f"show_det_{sale['_id']}", False):
                st.markdown("---")
                d_c1, d_c2 = st.columns(2)
                with d_c1:
                    st.write(f"**📞 Phone:** {sale['Phone'] or 'N/A'}")
                    st.write(f"**🧾 Subtotal:** ₹{sale['Subtotal']:,.2f}")
                    if sale["Discount"] > 0:
                        st.write(f"**🏷️ Discount:** -₹{sale['Discount']:,.2f} ({sale['Dis_type']})")
                with d_c2:
                    if sale["Items"]:
                        i_df = pd.DataFrame([{"Product": i["name"], "Qty": i["qty"], "Total": f"₹{i.get('qty',0)*i.get('price',0):,.0f}"} for i in sale["Items"]])
                        st.dataframe(i_df, use_container_width=True, hide_index=True)
                
                # Actions inside details
                if not sale["voided"]:
                    act1, act2, act3, act4 = st.columns(4)
                    with act1:
                        if st.button("🔄 Return", key=f"ret_s_{sale['_id']}", use_container_width=True):
                            st.session_state["selected_sale_for_return"] = sale
                            st.switch_page("pages/5_Returns.py")
                    with act2:
                        wa_msg  = build_whatsapp_message(sale["Items"], sale["Subtotal"], sale["Discount"], sale["Dis_type"], sale["Total"], sale["Customer"])
                        wa_link = (f"https://wa.me/91{sale['Phone'].strip()}?text={wa_msg}" if sale["Phone"] and len(sale["Phone"].strip()) == 10 else f"https://wa.me/?text={wa_msg}")
                        st.link_button("📲 WhatsApp", wa_link, use_container_width=True)
                    with act3:
                        if st.button("🖨️ Reprint", key=f"pr_s_{sale['_id']}", use_container_width=True):
                            th = generate_thermal_bill_html(sale["Items"], sale["Subtotal"], sale["Discount"], sale["Dis_type"], sale["Total"], sale["Customer"], sale["Phone"], sale["Payment"])
                            trigger_thermal_print(th)
                    with act4:
                        if st.button("🗑️ Void", key=f"vd_s_{sale['_id']}", use_container_width=True, type="secondary"):
                            st.session_state[f"void_q_{sale['_id']}"] = True

                    if st.session_state.get(f"void_q_{sale['_id']}", False):
                        st.error("Restore stock and cancel this sale?")
                        vy, vn = st.columns(2)
                        if vy.button("Yes, Void", key=f"v_y_{sale['_id']}", type="primary", use_container_width=True):
                            try:
                                @firestore_module.transactional
                                def do_void(tx, sale_id, items):
                                    s_ref = db.collection("sales").document(sale_id)
                                    s_snap = s_ref.get(transaction=tx)
                                    if s_snap.exists and not s_snap.to_dict().get("voided"):
                                        for itm in items:
                                            if itm.get("id"):
                                                i_ref = db.collection("items_master").document(itm["id"])
                                                i_snap = i_ref.get(transaction=tx)
                                                if i_snap.exists:
                                                    tx.update(i_ref, {"stock": i_snap.to_dict().get("stock", 0) + itm["qty"]})
                                        tx.update(s_ref, {"voided": True})
                                do_void(db.transaction(), sale["_id"], sale["Items"])
                                fetch_sales_history.clear()
                                clear_items_cache()
                                clear_dashboard_cache()
                                st.rerun()
                            except Exception as e: st.error(str(e))
                        if vn.button("Cancel", key=f"v_n_{sale['_id']}", use_container_width=True):
                            del st.session_state[f"void_q_{sale['_id']}"]
                            st.rerun()

    # ─── Export ────────────────────────────────────────────────────────────
    st.markdown("---")
    export_df = pd.DataFrame([{
        "Date": r["Date"], "Time": r["Time"], "Customer": r["Customer"], "Staff": r["EnteredBy"],
        "Items": r["Items_str"], "Total": r["Total"], "Payment": r["Payment"], "Status": "Voided" if r["voided"] else "Active"
    } for r in rows])
    buf = io.BytesIO()
    export_df.to_excel(buf, index=False, sheet_name="Sales")
    st.download_button("📥 Export Current List to Excel", buf.getvalue(), file_name=f"sales_{start_str}.xlsx", use_container_width=True)

else:
    st.info(f"No transactions found for **{start_str}** to **{end_str}**.")
