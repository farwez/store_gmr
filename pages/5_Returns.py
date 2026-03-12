import streamlit as st
from firebase_config import db, firestore_module
from datetime import datetime, timedelta
import pandas as pd
from utils import inject_custom_css, render_sidebar

st.set_page_config(page_title="Returns & Exchanges", layout="wide", page_icon="↩️")
inject_custom_css()
render_sidebar()

st.title("🔄 Returns & Exchanges")

# Create tabs
tab1, tab2 = st.tabs(["🔙 Process Return", "📋 Return History"])

# ==================== TAB 1: PROCESS RETURN ====================
with tab1:
    st.subheader("Process Return/Exchange")
    
    # Search for sale
    st.write("**Step 1: Find the Original Sale**")
    
    col1, col2 = st.columns(2)
    with col1:
        search_date = st.date_input("Sale Date", value=datetime.now())
    with col2:
        search_customer = st.text_input("Customer Name", placeholder="Enter customer name...")
    
    if st.button("🔍 Search Sales", type="primary"):
        try:
            # Search for sales
            sales_ref = db.collection("sales").where("date", "==", str(search_date)).stream()
            found_sales = []
            
            for sale in sales_ref:
                data = sale.to_dict()
                customer_name = data.get("customer_name", "")
                
                if search_customer.lower() in customer_name.lower():
                    found_sales.append({
                        "id": sale.id,
                        "customer": customer_name,
                        "phone": data.get("customer_phone", "N/A"),
                        "total": data.get("total", 0),
                        "items": data.get("items", []),
                        "timestamp": data.get("timestamp", datetime.now())
                    })
            
            if found_sales:
                st.session_state["found_sales"] = found_sales
                st.success(f"✅ Found {len(found_sales)} sale(s)")
            else:
                st.warning("No sales found matching the criteria")
                st.session_state["found_sales"] = []
        
        except Exception as e:
            st.error(f"Error searching: {e}")
    
    # Display found sales
    if "found_sales" in st.session_state and st.session_state["found_sales"]:
        st.markdown("---")
        st.write("**Step 2: Select the Sale**")
        
        for idx, sale in enumerate(st.session_state["found_sales"]):
            with st.expander(f"Sale #{idx+1} - {sale['customer']} - ₹{sale['total']:,.2f}"):
                st.write(f"**Customer:** {sale['customer']}")
                st.write(f"**Phone:** {sale['phone']}")
                st.write(f"**Total:** ₹{sale['total']:,.2f}")
                st.write(f"**Time:** {sale['timestamp'].strftime('%I:%M %p') if isinstance(sale['timestamp'], datetime) else 'N/A'}")
                
                st.write("**Items:**")
                for item in sale['items']:
                    st.write(f"- {item.get('name', 'Unknown')} × {item.get('qty', 0)} = ₹{item.get('qty', 0) * item.get('price', 0)}")
                
                if st.button(f"🔄 Process Return for this Sale", key=f"return_{sale['id']}"):
                    st.session_state["selected_sale"] = sale
                    st.rerun()
    
    # Process return for selected sale
    if "selected_sale" in st.session_state:
        st.markdown("---")
        st.write("**Step 3: Select Items to Return**")
        
        sale = st.session_state["selected_sale"]
        st.info(f"Processing return for: {sale['customer']}")
        
        return_items = []
        
        for idx, item in enumerate(sale['items']):
            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col1:
                st.write(f"**{item.get('name', 'Unknown')}**")
                st.caption(f"Original Qty: {item.get('qty', 0)} × ₹{item.get('price', 0)}")
            
            with col2:
                return_qty = st.number_input(
                    "Return Qty",
                    min_value=0,
                    max_value=item.get('qty', 0),
                    value=0,
                    key=f"return_qty_{idx}"
                )
            
            with col3:
                if return_qty > 0:
                    return_items.append({
                        "id": item.get('id'),
                        "name": item.get('name', 'Unknown'),
                        "qty": return_qty,
                        "price": item.get('price', 0),
                        "original_qty": item.get('qty', 0)
                    })
                    st.write(f"₹{return_qty * item.get('price', 0):,.2f}")
        
        if return_items:
            st.markdown("---")
            st.write("**Step 4: Return Details**")
            
            return_reason = st.text_area("Reason for Return", placeholder="e.g., Damaged, Wrong item, Customer changed mind...")
            
            return_type = st.radio("Return Type", ["Refund", "Exchange"])
            
            # Calculate return amount
            return_amount = sum(item['qty'] * item['price'] for item in return_items)
            
            st.write(f"**Return Amount:** ₹{return_amount:,.2f}")
            
            if st.button("✅ Process Return", type="primary", use_container_width=True):
                if not return_reason.strip():
                    st.error("Please provide a reason for return")
                else:
                    try:
                        # Create return record
                        return_data = {
                            "original_sale_id": sale['id'],
                            "customer_name": sale['customer'],
                            "customer_phone": sale['phone'],
                            "return_items": return_items,
                            "return_amount": return_amount,
                            "return_type": return_type,
                            "reason": return_reason.strip(),
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "timestamp": datetime.now(),
                            "processed_by": "Admin"  # You can add user authentication later
                        }
                        
                        # Transactional update for Stock increment and Return record
                        @firestore_module.transactional
                        def process_return_transaction(transaction, return_ref, return_data, return_items):
                            # 1. Update stock for each returned item
                            for item in return_items:
                                # We need the original item ID. Existing sales might not have it.
                                # Let's try to find it by name if missing
                                item_id = item.get("id")
                                if not item_id:
                                    # Fallback: search by name in items_master
                                    items_ref = db.collection("items_master").where("name", "==", item['name']).limit(1).get()
                                    if items_ref:
                                        item_id = items_ref[0].id
                                
                                if item_id:
                                    item_ref = db.collection("items_master").document(item_id)
                                    snapshot = item_ref.get(transaction=transaction)
                                    if snapshot.exists:
                                        current_stock = snapshot.get("stock", 0)
                                        transaction.update(item_ref, {"stock": current_stock + item['qty']})
                            
                            # 2. Add the return record
                            transaction.create(return_ref, return_data)

                        # Execute transaction
                        return_ref = db.collection("returns").document()
                        process_return_transaction(db.transaction(), return_ref, return_data, return_items)
                        
                        st.success(f"✅ Return processed successfully!")
                        st.success(f"💰 Refund Amount: ₹{return_amount:,.2f}")
                        
                        # Clear session
                        if "selected_sale" in st.session_state:
                            del st.session_state["selected_sale"]
                        if "found_sales" in st.session_state:
                            del st.session_state["found_sales"]
                        
                        st.balloons()
                        
                        if st.button("🔄 Process Another Return"):
                            st.rerun()
                    
                    except Exception as e:
                        st.error(f"Error processing return: {e}")

# ==================== TAB 2: RETURN HISTORY ====================
with tab2:
    st.subheader("📋 Return History")
    
    # Date range filter
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("From Date", value=datetime.now() - timedelta(days=30), key="return_start")
    with col2:
        end_date = st.date_input("To Date", value=datetime.now(), key="return_end")
    
    if st.button("📊 View Returns", type="primary"):
        try:
            # Fetch all returns
            returns_ref = db.collection("returns").stream()
            returns_data = []
            
            for ret in returns_ref:
                data = ret.to_dict()
                return_date_str = data.get("date", "")
                
                try:
                    return_date = datetime.strptime(return_date_str, "%Y-%m-%d").date()
                except:
                    continue
                
                if start_date <= return_date <= end_date:
                    items_str = ", ".join([f"{item.get('name', 'Unknown')} x{item.get('qty', 0)}" for item in data.get("return_items", [])])
                    
                    returns_data.append({
                        "Date": return_date_str,
                        "Customer": data.get("customer_name", "N/A"),
                        "Items": items_str,
                        "Amount": data.get("return_amount", 0),
                        "Type": data.get("return_type", "N/A"),
                        "Reason": data.get("reason", "N/A")
                    })
            
            if returns_data:
                df = pd.DataFrame(returns_data)
                
                # Summary metrics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Returns", len(df))
                with col2:
                    st.metric("Total Amount", f"₹{df['Amount'].sum():,.2f}")
                with col3:
                    refunds = len(df[df['Type'] == 'Refund'])
                    st.metric("Refunds", refunds)
                
                st.markdown("---")
                
                # Display table
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                # Export option
                import io
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Returns')
                output.seek(0)
                
                st.download_button(
                    label="📥 Download Returns Report",
                    data=output,
                    file_name=f"returns_{start_date}_to_{end_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.info("No returns found for the selected period")
        
        except Exception as e:
            st.error(f"Error loading returns: {e}")
