import streamlit as st
from firebase_config import db
from datetime import datetime
import pandas as pd
from utils import inject_custom_css, render_sidebar, get_ist_time, check_admin, get_all_items, clear_items_cache

st.set_page_config(page_title="Stock Adjustments", page_icon="📦", layout="wide")
inject_custom_css()
render_sidebar()
check_admin()

st.title("📦 Stock Adjustments (Damaged & Lost)")
st.markdown("Manually adjust inventory for damaged, expired, stolen, or promotional items.")
st.markdown("---")

# Fetch all items from the master list
items_dict = get_all_items()
if not items_dict:
    st.warning("No items found in the master list. Please add items first.")
    st.stop()
    
# Convert dictionary to list for selectbox
item_list = [{"id": k, **v} for k, v in items_dict.items()]
# Sort items alphabetically by name
item_list.sort(key=lambda x: x.get('name', ''))

# ==================== UI TABS ====================
tab1, tab2 = st.tabs(["📉 New Stock Adjustment", "📋 Adjustment History"])

# --- TAB 1: ADD NEW ADJUSTMENT ---
with tab1:
    st.subheader("Adjust Item Stock")
    
    with st.form("stock_adj_form", clear_on_submit=True):
        col_f1, col_f2 = st.columns(2)
        
        with col_f1:
            selected_item_name = st.selectbox(
                "Select Item", 
                options=[item['name'] for item in item_list],
                help="Type to search for the item..."
            )
            
            # Find the full item dict based on selection
            selected_item = next((item for item in item_list if item['name'] == selected_item_name), None)
            
            qty_to_adjust = st.number_input(
                "Quantity to Remove", 
                min_value=1, 
                value=1, 
                help="Amount of stock to deduct from the system."
            )
            
        with col_f2:
            reason = st.selectbox("Reason for Adjustment", [
                "Damaged / Broken",
                "Expired",
                "Lost / Stolen",
                "Internal Use / Store Sample",
                "Promotional Giveaway",
                "Data Entry Correction"
            ])
            
            notes = st.text_input("Additional Notes", placeholder="E.g., Dropped from shelf")
            
        # Display current stock as info
        if selected_item:
            st.info(f"📊 Current Stock for **{selected_item['name']}**: {selected_item.get('stock', 0)} units")    
            
        submitted = st.form_submit_button("📉 Process Adjustment", type="primary", use_container_width=True)
        
        if submitted and selected_item:
            current_stock = selected_item.get('stock', 0)
            
            if qty_to_adjust > current_stock:
                st.error(f"Cannot deduct {qty_to_adjust} units. Only {current_stock} available.")
            else:
                try:
                    # 1. Deduct Stock in Master
                    new_stock = current_stock - qty_to_adjust
                    db.collection("items_master").document(selected_item['id']).update({"stock": new_stock})
                    
                    # 2. Record the Adjustment History
                    cost_value = selected_item.get("cost_price", 0) * qty_to_adjust
                    
                    adj_record = {
                        "date": get_ist_time().strftime("%Y-%m-%d"),
                        "timestamp": get_ist_time(),
                        "item_id": selected_item['id'],
                        "item_name": selected_item['name'],
                        "qty_removed": qty_to_adjust,
                        "cost_value_lost": cost_value,
                        "reason": reason,
                        "notes": notes if notes else "No notes provided"
                    }
                    
                    db.collection("stock_adjustments").add(adj_record)
                    
                    # 3. Clear Cache
                    clear_items_cache()
                    
                    st.success(f"✅ Adjusted {qty_to_adjust} units of {selected_item['name']}. New stock is {new_stock}.")
                    st.toast("Stock Updated!")
                    
                except Exception as e:
                    st.error(f"Transaction Failed: {e}")

# --- TAB 2: HISTORY ---
with tab2:
    st.subheader("Adjustment History")
    
    @st.cache_data(ttl=60)
    def fetch_adjustments():
        all_adj = db.collection("stock_adjustments").order_by("timestamp", direction="DESCENDING").stream()
        return [adj.to_dict() for adj in all_adj]
        
    adj_data = fetch_adjustments()
    
    if adj_data:
        df = pd.DataFrame(adj_data)
        
        # Calculate high level metrics
        total_items_lost = df["qty_removed"].sum()
        total_value_lost = df["cost_value_lost"].sum()
        
        col_m1, col_m2 = st.columns(2)
        with col_m1:
             st.metric("Total Items Adjusted", int(total_items_lost))
        with col_m2:
             st.metric("Total Value Lost (Cost)", f"₹{total_value_lost:,.2f}")
             
        st.markdown("---")
        
        # Breakdown by Reason
        st.write("#### 📉 Reasons for Loss")
        reason_groups = df.groupby("reason")["qty_removed"].sum().reset_index()
        import plotly.express as px
        fig = px.pie(reason_groups, values="qty_removed", names="reason", hole=0.4, 
                     color_discrete_sequence=px.colors.sequential.Reds_r)
        st.plotly_chart(fig, use_container_width=True)
        
        # Details Table
        st.write("#### 📜 Detailed Log")
        display_df = df[["date", "item_name", "qty_removed", "reason", "cost_value_lost", "notes"]].copy()
        display_df.columns = ["Date", "Item Name", "Qty", "Reason", "Cost Val (₹)", "Notes"]
        display_df["Cost Val (₹)"] = display_df["Cost Val (₹)"].apply(lambda x: f"₹{x:,.2f}")
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
    else:
        st.info("No stock adjustments recorded yet.")
