import streamlit as st
import os
import pandas as pd
from firebase_config import db, firestore_module
from utils import (
    generate_bill_pdf, upload_bill_to_firebase, build_whatsapp_message,
    today_string, inject_custom_css, render_sidebar, get_all_items,
    generate_bill_html, get_ist_time, generate_thermal_bill_html,
    trigger_thermal_print, check_auth, clear_items_cache, clear_dashboard_cache
)

st.set_page_config(page_title="New Sale", layout="wide", page_icon="🛒", initial_sidebar_state="expanded")
inject_custom_css()
check_auth()
render_sidebar()

# ── Init session state ─────────────────────────────────────────────────────
if "cart" not in st.session_state:
    st.session_state["cart"] = []

# ── Reset form after completed sale ───────────────────────────────────────
if st.session_state.pop("_do_reset", False):
    for key in ["customer_name", "customer_phone", "product_selector", "qty_input"]:
        st.session_state.pop(key, None)

# ── Last-Bill Success Banner ───────────────────────────────────────────────
if "last_bill" in st.session_state:
    bill = st.session_state["last_bill"]
    with st.container(border=True):
        st.success(f"✅ Sale completed! Bill issued to **{bill['name']}** — ₹{bill['total']:,.2f}")
        bc1, bc2, bc3, bc4 = st.columns(4)
        with bc1:
            if st.button("🖨️ Print Receipt", use_container_width=True, type="primary"):
                th = generate_thermal_bill_html(
                    bill["items"], bill["subtotal"], bill["discount_amount"],
                    bill["discount_type"], bill["total"], bill["name"],
                    bill.get("phone", ""), bill.get("pay_method", ""), bill.get("heading", "TAX INVOICE")
                )
                trigger_thermal_print(th)
                st.toast("Sent to printer…")
        with bc2:
            try:
                if os.path.exists(bill.get("pdf", "")):
                    with open(bill["pdf"], "rb") as f:
                        st.download_button("📄 Download PDF", f, file_name=bill["file_name"], mime="application/pdf", use_container_width=True)
                elif bill.get("public_url"):
                    st.link_button("☁️ Open Cloud PDF", bill["public_url"], use_container_width=True)
            except:
                pass
        with bc3:
            if bill.get("wa_link"):
                st.link_button("📲 WhatsApp Bill", bill["wa_link"], use_container_width=True)
        with bc4:
            if st.button("✖ Dismiss", use_container_width=True):
                del st.session_state["last_bill"]
                st.rerun()
    st.divider()

st.title("🛒 New Sale Entry")

# ═══════════════════════════════════════════════════════════════
# SECTION 1 — Customer Info
# ═══════════════════════════════════════════════════════════════
with st.container(border=True):
    st.markdown("**👤 Customer Details**")
    ci1, ci2 = st.columns(2)
    with ci1:
        customer_name = st.text_input("Customer Name *", placeholder="e.g. Ravi Kumar", key="customer_name")
    with ci2:
        customer_phone = st.text_input("Phone (Optional)", placeholder="10-digit mobile number", key="customer_phone")

st.divider()

# ═══════════════════════════════════════════════════════════════
# SECTION 2 — Product Search & Cart
# ═══════════════════════════════════════════════════════════════
st.markdown("### 🧺 Cart")

try:
    items_master = get_all_items()  # {id: {name, price, cost_price, stock}}
    if not items_master:
        st.warning("⚠️ No products in catalog. Add items from the **Items Master** page first.")
        st.stop()
except Exception as e:
    st.error(f"Failed to load product catalog: {e}")
    st.stop()

# ── Item Selector Row ──────────────────────────────────────────
with st.container(border=True):
    p1, p2, p3 = st.columns([4, 1, 1])
    with p1:
        product_opts = ["— Select a product —"] + list(items_master.keys())

        def fmt(x):
            if x == "— Select a product —": return x
            it = items_master[x]
            stock = it.get("stock", 0)
            flag = "🔴" if stock == 0 else "🟡" if stock <= 5 else "🟢"
            return f"{flag}  {it['name']}   |   Stock: {stock}   |   ₹{it['price']:,.0f}"

        chosen_id = st.selectbox("Product", product_opts, format_func=fmt, label_visibility="collapsed", key="product_selector")

    with p2:
        # Key is tied to the chosen product so qty resets to 1 whenever a different product is selected
        qty_key = f"qty_for_{chosen_id}"
        qty_input = st.number_input("Qty", min_value=1, value=1, step=1, label_visibility="collapsed", key=qty_key)

    with p3:
        add_clicked = st.button("➕ Add", type="primary", use_container_width=True)

    if add_clicked:
        if chosen_id == "— Select a product —":
            st.error("Please select a product first.")
        else:
            prod = items_master[chosen_id]
            available = prod.get("stock", 0)
            already   = sum(c["qty"] for c in st.session_state["cart"] if c["id"] == chosen_id)

            if available == 0:
                st.error(f"❌ **{prod['name']}** is out of stock.")
            elif already + qty_input > available:
                st.error(f"❌ Only **{available - already}** more unit(s) available (stock: {available}, in cart: {already}).")
            else:
                for c in st.session_state["cart"]:
                    if c["id"] == chosen_id:
                        c["qty"] += qty_input
                        break
                else:
                    st.session_state["cart"].append({
                        "id": chosen_id,
                        "name": prod["name"],
                        "qty": qty_input,
                        "price": prod["price"],
                        "cost": prod.get("cost_price", 0)
                    })
                st.toast(f"✅ {prod['name']} × {qty_input} added")
                st.rerun()

# ── Cart Table ─────────────────────────────────────────────────
cart = st.session_state["cart"]

if not cart:
    st.info("🛒 Your cart is empty — select a product above and click **Add**.")
    st.stop()

with st.container(border=True):
    hdr = st.columns([4, 1.5, 2, 2, 1])
    hdr[0].markdown("**Product**")
    hdr[1].markdown("**Qty**")
    hdr[2].markdown("**Unit Price**")
    hdr[3].markdown("**Line Total**")
    st.markdown("<hr style='margin:4px 0'>", unsafe_allow_html=True)

    subtotal = 0.0
    for idx, item in enumerate(cart):
        available_stock = int(items_master.get(item["id"], {}).get("stock", item["qty"]))
        max_qty = max(int(item["qty"]), available_stock)
        
        line = item["qty"] * item["price"]
        subtotal += line
        row = st.columns([4, 1.5, 2, 2, 1])
        row[0].write(item["name"])
        new_qty = row[1].number_input(
            f"Quantity for {item['name']}",
            min_value=1,
            max_value=max_qty,
            value=int(item["qty"]),
            step=1,
            key=f"qty_edit_{item['id']}",
            label_visibility="collapsed"
        )
        if int(new_qty) != int(item["qty"]):
            item["qty"] = int(new_qty)
            st.session_state["cart"] = cart
            st.rerun()
        row[2].write(f"₹{item['price']:,.2f}")
        row[3].write(f"**₹{line:,.2f}**")
        if row[4].button("🗑", key=f"rm_{idx}"):
            cart.pop(idx)
            st.session_state["cart"] = cart
            st.rerun()

    st.markdown(f"<div style='text-align:right;font-size:18px;padding-top:10px;'>Subtotal: <b>₹{subtotal:,.2f}</b></div>", unsafe_allow_html=True)

st.divider()

# ═══════════════════════════════════════════════════════════════
# SECTION 3 — Billing & Payment
# ═══════════════════════════════════════════════════════════════
with st.container(border=True):
    st.markdown("**💳 Billing & Payment**")
    b1, b2, b3, b4, b5 = st.columns(5)
    with b1:
        disc_type = st.selectbox("Discount Type", ["No Discount", "Flat (₹)", "Percentage (%)"])
    with b2:
        if disc_type == "Flat (₹)":
            disc_val = st.number_input("Discount (₹)", min_value=0.0, max_value=float(subtotal), step=10.0)
            disc_amt = disc_val
        elif disc_type == "Percentage (%)":
            disc_val = st.number_input("Discount (%)", min_value=0.0, max_value=100.0, step=1.0)
            disc_amt = round(subtotal * disc_val / 100, 2)
        else:
            disc_amt = 0.0
    with b3:
        pay_mode = st.selectbox("Payment Mode", ["Cash", "UPI / GPay", "Card / POS", "Credit / Due", "Cheque"])
    with b4:
        doc_type = st.selectbox("Document Type", ["TAX INVOICE", "RETAIL INVOICE", "CASH MEMO", "BILL OF SUPPLY"])
    with b5:
        fast_billing = st.checkbox("Fast Billing", value=True, help="Skips cloud upload for faster bill generation")

    final_total = max(0.0, subtotal - disc_amt)
    st.markdown(f"""
        <div style='background:#f8fafc;padding:14px;border-radius:12px;margin-top:10px;'>
            <span>Subtotal: ₹{subtotal:,.2f}</span>
            {"&nbsp;&nbsp;|&nbsp;&nbsp;<span style='color:#ef4444'>Discount: -₹" + f"{disc_amt:,.2f}</span>" if disc_amt > 0 else ""}
            &nbsp;&nbsp;|&nbsp;&nbsp;<b style='font-size:18px;color:#16a34a'>Total: ₹{final_total:,.2f}</b>
            &nbsp;&nbsp;|&nbsp;&nbsp;Mode: {pay_mode}
        </div>
    """, unsafe_allow_html=True)

st.divider()

# ═══════════════════════════════════════════════════════════════
# SECTION 4 — Actions
# ═══════════════════════════════════════════════════════════════
col_a1, col_a2, col_a3 = st.columns([1, 1, 2])

with col_a1:
    if st.button("🗑️ Clear Cart", use_container_width=True):
        st.session_state["cart"] = []
        st.rerun()

with col_a2:
    show_preview = st.button("👁 Preview Bill", use_container_width=True)

with col_a3:
    confirm_sale = st.button("✅ Confirm & Generate Bill", type="primary", use_container_width=True, disabled=st.session_state.get("processing_sale", False) or len(cart) == 0)

if show_preview:
    if not customer_name.strip():
        st.warning("Enter customer name to preview.")
    else:
        html_prev = generate_bill_html(cart, subtotal, disc_amt, disc_type, final_total,
                                       customer_name, customer_phone, pay_mode, doc_type + " (PREVIEW)")
        with st.expander("📋 Bill Preview", expanded=True):
            import streamlit.components.v1 as components
            components.html(html_prev, height=650, scrolling=True)

if confirm_sale:
    phone_text = customer_phone.strip()
    digits_only = "".join(filter(str.isdigit, phone_text))
    
    if not customer_name.strip():
        st.error("❌ Please enter the customer name.")
    elif phone_text and len(digits_only) < 10:
        st.error("❌ Invalid Phone Number. Please enter at least 10 numeric digits if providing a phone.")
    else:
        st.session_state["processing_sale"] = True
        try:
            os.makedirs("bills", exist_ok=True)
            stamp    = get_ist_time().strftime("%Y%m%d_%H%M%S")
            pdf_path = f"bills/bill_{stamp}.pdf"

            sale_doc = {
                "customer_name":  customer_name.strip(),
                "customer_phone": customer_phone.strip(),
                "items":          list(cart),        # snapshot of cart at time of sale
                "subtotal":       subtotal,
                "discount_type":  disc_type,
                "discount_amount":disc_amt,
                "total":          final_total,
                "payment_method": pay_mode,
                "date":           today_string(),
                "timestamp":      get_ist_time(),
                "entered_by":     st.session_state.get("user_name") or st.session_state.get("username", ""),
                "entered_by_username": st.session_state.get("username", ""),
                "voided":         False,
            }

            # ----- Atomic Firestore Transaction -----
            @firestore_module.transactional
            def do_sale_tx(tx, sale_ref, doc, cart_items):
                # PHASE 1 — read all item documents and validate
                item_refs = []
                for itm in cart_items:
                    iref = db.collection("items_master").document(itm["id"])
                    snap = iref.get(transaction=tx)
                    if not snap.exists:
                        raise ValueError(f"Item '{itm['name']}' no longer exists in catalog.")
                    curr_stock = snap.to_dict().get("stock", 0)
                    if curr_stock < itm["qty"]:
                        raise ValueError(
                            f"Insufficient stock for '{itm['name']}'. "
                            f"Available: {curr_stock}, Needed: {itm['qty']}."
                        )
                    item_refs.append((iref, curr_stock - itm["qty"]))

                # PHASE 2 — write all updates
                for iref, new_stock in item_refs:
                    tx.update(iref, {"stock": new_stock})
                tx.create(sale_ref, doc)

            new_sale_ref = db.collection("sales").document()
            do_sale_tx(db.transaction(), new_sale_ref, sale_doc, cart)
            clear_items_cache()
            clear_dashboard_cache()

            # ----- Generate Bill -----
            generate_bill_pdf(pdf_path, cart, subtotal, disc_amt, disc_type, final_total,
                               customer_name, customer_phone, pay_mode, doc_type)
                               
            # ----- Strict Phone Number Sanitization -----
            clean_phone = "".join(filter(str.isdigit, str(customer_phone)))
            clean_phone = clean_phone[-10:] if len(clean_phone) >= 10 else clean_phone
            
            pub_url  = None if fast_billing else upload_bill_to_firebase(pdf_path, f"bill_{stamp}.pdf")
            wa_msg   = build_whatsapp_message(cart, subtotal, disc_amt, disc_type, final_total, customer_name, doc_type)
            wa_link  = (f"https://wa.me/91{clean_phone}?text={wa_msg}"
                        if len(clean_phone) == 10
                        else f"https://wa.me/?text={wa_msg}")

            st.session_state["last_bill"] = {
                "name": customer_name, "phone": customer_phone,
                "items": cart, "subtotal": subtotal,
                "discount_type": disc_type, "discount_amount": disc_amt,
                "total": final_total, "pay_method": pay_mode, "heading": doc_type,
                "pdf": pdf_path, "file_name": f"bill_{stamp}.pdf",
                "public_url": pub_url, "wa_link": wa_link,
            }
            st.session_state["cart"] = []
            st.session_state["processing_sale"] = False
            st.session_state["_do_reset"] = True
            st.rerun()

        except ValueError as ve:
            st.session_state["processing_sale"] = False
            st.error(f"⚠️ {ve}")
        except Exception as e:
            st.session_state["processing_sale"] = False
            st.error(f"Sale failed: {e}")
