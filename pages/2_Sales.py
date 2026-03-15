import streamlit as st
from firebase_config import db, firestore_module
from utils import (
    generate_bill_pdf,
    upload_bill_to_firebase,
    build_whatsapp_message,
    today_string,
    inject_custom_css,
    render_sidebar,
    get_all_items,
    generate_bill_html,
    get_ist_time,
    generate_thermal_bill_html,
    trigger_thermal_print,
    check_auth
)
import streamlit.components.v1 as components
from datetime import datetime

st.set_page_config(page_title="New Sale", layout="wide", page_icon="🛒", initial_sidebar_state="expanded")
inject_custom_css()
check_auth()
render_sidebar()

# Handle Reset Trigger (Must be before widgets are cleared)
if st.session_state.get("trigger_reset"):
    try:
        st.session_state["customer_name"] = ""
        st.session_state["customer_phone"] = ""
        st.session_state["pay_method"] = "Cash"
        st.session_state["trigger_reset"] = False
    except:
        pass

# Display Success Message from previous run
if st.session_state.get("last_bill"):
    bill = st.session_state["last_bill"]
    
    # Professional Success Banner
    with st.container():
        st.markdown(f"""
        <div style="background-color: #ecfdf5; padding: 15px; border-radius: 10px; border: 1px solid #10b981; margin-bottom: 15px; display: flex; flex-direction: row; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 15px;">
                <div style="font-size: 24px;">✅</div>
                <div>
                    <h3 style="color: #065f46; margin: 0; font-size: 18px; font-weight: 600;">Bill Generated Successfully</h3>
                    <p style="color: #047857; margin: 2px 0 0 0; font-size: 14px;">Customer: <b>{bill['name']}</b></p>
                </div>
            </div>
            <div style="font-size: 12px; color: #047857;">{get_ist_time().strftime('%I:%M %p')}</div>
        </div>
        """, unsafe_allow_html=True)
        
        col_s1, col_s2, col_s3 = st.columns([2, 2, 1])
        
        with col_s1:
            local_exists = False
            try:
                import os
                if os.path.exists(bill['pdf']):
                    local_exists = True
                    with open(bill['pdf'], "rb") as f:
                        st.download_button(
                            "📄 Download PDF", 
                            f, 
                            file_name=bill['file_name'],
                            mime="application/pdf",
                            use_container_width=True,
                            type="primary"
                        )
            except:
                pass
            
            if not local_exists and bill.get("public_url"):
                st.link_button("🌐 Open from Cloud", bill["public_url"], use_container_width=True, type="primary")
                
        with col_s2:
            if bill.get('wa_link'):
                st.link_button("📲 WhatsApp", bill['wa_link'], use_container_width=True)
                
        # New Column for Thermal Print
        col_s4, col_s5 = st.columns([1, 1])
        with col_s4:
            if st.button("🖨️ Thermal Print", use_container_width=True):
                # We need the bill data to generate the thermal version
                # If we saved it in session state correctly:
                thermal_html = generate_thermal_bill_html(
                    bill['items'], bill['subtotal'], bill['discount_amount'], 
                    bill['discount_type'], bill['total'], bill['name'], 
                    bill.get('phone', ''), bill.get('pay_method', ''), bill.get('heading', 'TAX INVOICE')
                )
                trigger_thermal_print(thermal_html)
                st.toast("Printing receipt...")
        
        with col_s5:
            if st.button("❌ Close", use_container_width=True):
                del st.session_state["last_bill"]
                st.rerun()
                
        st.divider()

st.title("Sales Entry")

# Customer Information Section
st.subheader("Customer Information")
col1, col2 = st.columns(2)
with col1:
    customer_name = st.text_input("Customer Name", placeholder="Enter customer name", key="customer_name")
with col2:
    customer_phone = st.text_input("Phone Number (Optional)", placeholder="10-digit number", key="customer_phone")

st.divider()

# Items Selection Section
st.subheader("Select Items")

try:
    items_list = get_all_items()
    
    if not items_list:
        st.warning("⚠️ No items in catalog. Please add items in the Items Master page first.")
        st.stop()
    
    selected_item_id = st.selectbox(
        "Select Item",
        options=list(items_list.keys()),
        format_func=lambda x: f"{items_list[x]['name']} (Stock: {items_list[x].get('stock', 0)}) - ₹{items_list[x]['price']}"
    )
    
    qty = st.number_input("Quantity", min_value=1, step=1)
except Exception as e:
    st.error(f"❌ Error loading items: {e}")
    st.stop()

cart = st.session_state.get("cart", [])

if st.button("Add to Cart"):
    item = items_list[selected_item_id]
    current_stock = item.get("stock", 0)
    
    # Check if already in cart
    already_in_cart = sum(c['qty'] for c in cart if c['id'] == selected_item_id)
    
    if (already_in_cart + qty) > current_stock:
        st.error(f"❌ Cannot add. Only {current_stock - already_in_cart} units left in stock.")
    else:
        cart.append({
            "id": selected_item_id,
            "name": item["name"],
            "qty": qty,
            "price": item["price"],
            "cost": item.get("cost_price", 0) # Store cost at time of sale
        })
    st.session_state.cart = cart
    st.toast(f"🛒 {item['name']} added!")


st.divider()

# Calculate subtotal
subtotal = 0
if cart:
    st.subheader("Cart Items", anchor=False)
    
    # Create header
    h_col1, h_col2, h_col3, h_col4 = st.columns([3, 1, 1, 1])
    h_col1.markdown("**Item Name**")
    h_col2.markdown("**Qty**")
    h_col3.markdown("**Price**")
    h_col4.markdown("**Total**")
    
    st.markdown("<hr style='margin: 0.5rem 0;'>", unsafe_allow_html=True)
    
    for i, c in enumerate(cart):
        line_total = c["qty"] * c["price"]
        subtotal += line_total
        
        row_col1, row_col2, row_col3, row_col4 = st.columns([3, 1, 1, 1])
        row_col1.write(c['name'])
        row_col2.write(str(c['qty']))
        row_col3.write(f"₹{c['price']}")
        row_col4.write(f"₹{line_total}")
    
    st.markdown("<hr style='margin: 0.5rem 0 1.5rem 0;'>", unsafe_allow_html=True)
    
    # Discount Section
    st.subheader("Discount (Optional)")
    col_disc1, col_disc2 = st.columns(2)
    
    with col_disc1:
        discount_type = st.selectbox("Discount Type", ["No Discount", "Percentage (%)", "Fixed Amount (₹)"])
    
    with col_disc2:
        if discount_type == "Percentage (%)":
            discount_value = st.number_input("Discount %", min_value=0.0, max_value=100.0, value=0.0, step=5.0)
        elif discount_type == "Fixed Amount (₹)":
            discount_value = st.number_input("Discount Amount (₹)", min_value=0.0, max_value=float(subtotal), value=0.0, step=10.0)
        else:
            discount_value = 0.0
    
    # Calculate discount and total
    if discount_type == "Percentage (%)":
        discount_amount = (subtotal * discount_value) / 100
    elif discount_type == "Fixed Amount (₹)":
        discount_amount = discount_value
    else:
        discount_amount = 0.0
    
    total = subtotal - discount_amount
    
    # Display pricing breakdown
    st.markdown("---")
    # Discount Breakdown
    # Discount Breakdown
    col_price1, col_price2 = st.columns([3, 1])
    with col_price1:
        st.write("**Subtotal:**")
        if discount_amount > 0:
            st.write(f"**Discount ({discount_type.replace('Discount', '').strip()}):**")
        st.write("**Final Total:**")
    with col_price2:
        st.write(f"₹{subtotal:,.2f}")
        if discount_amount > 0:
            st.write(f"- ₹{discount_amount:,.2f}")
        st.markdown(f"**₹{total:,.2f}**")
    
    st.divider()

    # Document Details Selection
    st.subheader("Document Details")
    col_doc1, col_doc2 = st.columns(2)
    with col_doc1:
        invoice_heading = st.selectbox("Document Heading", ["TAX INVOICE", "RETAIL INVOICE", "INVOICE", "BILL OF SUPPLY"], key="invoice_heading")
    with col_doc2:
        payment_method = st.selectbox("Select Payment Mode", ["Cash", "UPI", "Card", "Credit/Due", "Other"], key="pay_method")

    # Resulting Buttons
    col_clear, col_spacer = st.columns([1, 3])
    with col_clear:
         if st.button("Clear Cart"):
            st.session_state.cart = []
            st.rerun()

    # Bill Preview Section
    st.divider()
    with st.expander("Preview Document", expanded=True):
        if not customer_name:
            st.info("Enter Customer Name to generate a complete preview.")
        else:
            # Use the selected payment method and heading in preview
            preview_html = generate_bill_html(cart, subtotal, discount_amount, discount_type, total, 
                                            customer_name, customer_phone, payment_method, f"{invoice_heading} (PREVIEW)")
            components.html(preview_html, height=600, scrolling=True)
            
    st.divider()
    st.subheader("Actions")
    
    col_act1, col_act2 = st.columns(2)
    
    with col_act1:
        if st.button("Generate Quote / Proforma", use_container_width=True):
            if not customer_name or customer_name.strip() == "":
                st.error("Customer name required for quotation.")
            else:
                try:
                    import os
                    os.makedirs("quotations", exist_ok=True)
                    quote_id = get_ist_time().strftime("%Y%m%d_%H%M%S")
                    pdf_name = f"quotations/quote_{quote_id}.pdf"
                    
                    # Prepare quote data
                    quote_data = {
                        "type": "quotation",
                        "customer_name": customer_name.strip(),
                        "customer_phone": customer_phone.strip() if customer_phone else "",
                        "items": cart,
                        "subtotal": subtotal,
                        "discount_type": discount_type,
                        "discount_amount": discount_amount,
                        "total": total,
                        "date": today_string(),
                        "timestamp": get_ist_time()
                    }
                    
                    # Save to quotations collection
                    db.collection("quotations").add(quote_data)
                    
                    # Generate PDF
                    generate_bill_pdf(pdf_name, cart, subtotal, discount_amount, discount_type, total, 
                                     customer_name, customer_phone, "", "PROFORMA INVOICE / QUOTATION")
                    
                    st.success(f"Quotation Generated!")
                    
                    with open(pdf_name, "rb") as f:
                        st.download_button("Download Quote", f, file_name=f"quote_{quote_id}.pdf", mime="application/pdf")
                        
                except Exception as e:
                    st.error("An error occurred while generating the quotation.")

    with col_act2:
        if st.button(f"Generate {invoice_heading.title()}", type="primary", use_container_width=True):
            if not customer_name or customer_name.strip() == "":
                st.error("Please enter customer name before generating the document.")
            else:
                try:
                    import os
                    os.makedirs("bills", exist_ok=True)
                    bill_id = get_ist_time().strftime("%Y%m%d_%H%M%S")
                    pdf_name = f"bills/bill_{bill_id}.pdf"
                    
                    # Prepare bill data
                    bill_data = {
                        "type": "invoice",
                        "customer_name": customer_name.strip(),
                        "customer_phone": customer_phone.strip() if customer_phone else "",
                        "payment_method": payment_method,
                        "items": cart,
                        "subtotal": subtotal,
                        "discount_type": discount_type,
                        "discount_amount": discount_amount,
                        "total": total,
                        "date": today_string(),
                        "timestamp": get_ist_time()
                    }
                    
                    # Save to sales collection with Transaction for Stock Deduction
                    @firestore_module.transactional
                    def process_sale_transaction(transaction, sales_ref, bill_data, cart):
                        # 1. Update stock for each item
                        for item in cart:
                            item_ref = db.collection("items_master").document(item['id'])
                            snapshot = item_ref.get(transaction=transaction)
                            if not snapshot.exists:
                                raise Exception(f"Item {item['name']} not found!")
                            
                            current_stock = snapshot.get("stock")
                            if current_stock < item['qty']:
                                raise Exception(f"Insufficient stock for {item['name']}! Available: {current_stock}")
                            
                            transaction.update(item_ref, {"stock": current_stock - item['qty']})
                        
                        # 2. Add the sale record
                        transaction.create(sales_ref, bill_data)

                    # Execute transaction
                    sales_ref = db.collection("sales").document()
                    process_sale_transaction(db.transaction(), sales_ref, bill_data, cart)
                    
                    # Generate PDF
                    generate_bill_pdf(pdf_name, cart, subtotal, discount_amount, discount_type, total, 
                                     customer_name, customer_phone, payment_method, invoice_heading)
                    
                    # Upload to Firebase
                    public_url = upload_bill_to_firebase(pdf_name, f"bill_{bill_id}.pdf")
                    
                    # WhatsApp sharing link generation
                    wa_msg = build_whatsapp_message(cart, subtotal, discount_amount, discount_type, total, customer_name, invoice_heading)
                    if customer_phone and len(customer_phone.strip()) == 10:
                        wa_link = f"https://wa.me/91{customer_phone.strip()}?text={wa_msg}"
                    else:
                        wa_link = f"https://wa.me/?text={wa_msg}"
                    
                    # Store data for next run (Success message & Download)
                    st.session_state["last_bill"] = {
                        "name": customer_name,
                        "phone": customer_phone,
                        "pdf": pdf_name,
                        "file_name": f"bill_{bill_id}.pdf",
                        "wa_link": wa_link,
                        "public_url": public_url,
                        "items": cart,
                        "subtotal": subtotal,
                        "discount_amount": discount_amount,
                        "discount_type": discount_type,
                        "total": total,
                        "pay_method": payment_method,
                        "heading": invoice_heading
                    }
                    
                    # Trigger reset and rerun
                    st.session_state.cart = []
                    st.session_state["trigger_reset"] = True
                    st.rerun()
                        
                except Exception as e:
                    st.error("An error occurred while generating the document. Please verify all inputs and try again.")
                    # Log internally instead of exposing the stack trace to the user
                    print(f"Error generating document: {e}")

else:
    st.info("Cart is empty. Add items to get started!")
    subtotal = 0
    discount_amount = 0
    discount_type = "No Discount"
    total = 0

st.divider()
