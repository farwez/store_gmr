import streamlit as st
from firebase_config import db
import pandas as pd
from utils import inject_custom_css, render_sidebar, clear_items_cache, check_auth

st.set_page_config(page_title="Items Master", layout="wide", initial_sidebar_state="expanded", page_icon="📦")
inject_custom_css()
check_auth()
render_sidebar()
st.title("📦 Items Master")

# Create tabs for better organization
tab1, tab2 = st.tabs(["➕ Add Item", "📋 Manage Items"])

# ==================== TAB 1: ADD ITEM ====================
with tab1:
    st.subheader("Add New Item")
    
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Item Name", key="add_name", placeholder="e.g. 2.5 Inch Shell")
        cost_price = st.number_input("Purchase Price (Cost) (₹)", min_value=0.0, step=10.0, key="add_cost")
    with col2:
        price = st.number_input("Selling Price (₹)", min_value=0.0, step=10.0, key="add_price")
        stock = st.number_input("Initial Stock Qty", min_value=0, step=1, value=0, key="add_stock")
    
    if st.button("➕ Add Item", type="primary", use_container_width=True):
        if not name or name.strip() == "":
            st.error("⚠️ Please enter an item name")
        elif price <= 0:
            st.error("⚠️ Selling price must be greater than 0")
        else:
            try:
                db.collection("items_master").add({
                    "name": name.strip(),
                    "price": price,
                    "cost_price": cost_price,
                    "stock": stock
                })
                st.toast(f"✅ Item '{name}' added!")
                clear_items_cache()
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error adding item: {e}")

# ==================== TAB 2: MANAGE ITEMS ====================
with tab2:
    st.subheader("📋 Item List")
    
    # Search box
    search_query = st.text_input("🔍 Search items", placeholder="Type to search...")
    
    try:
        # Fetch all items
        items_ref = db.collection("items_master").stream()
        items_list = []
        
        for item in items_ref:
            data = item.to_dict()
            items_list.append({
                "id": item.id,
                "name": data.get("name", "Unknown"),
                "price": data.get("price", 0),
                "cost_price": data.get("cost_price", 0),
                "stock": data.get("stock", 0)
            })
        
        if not items_list:
            st.info("📦 No items in the catalog yet. Add your first item in the 'Add Item' tab!")
        else:
            # Filter by search query
            if search_query:
                items_list = [
                    item for item in items_list 
                    if search_query.lower() in item["name"].lower()
                ]
            
            if not items_list:
                st.warning(f"No items found matching '{search_query}'")
            else:
                st.write(f"**Total Items:** {len(items_list)}")
                
                # Display items in a nice format
                for idx, item in enumerate(items_list):
                    with st.container():
                        st.markdown(f"""
                        <div style="background: white; padding: 20px; border-radius: 16px; border: 1px solid #f1f5f9; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
                            <div style="display: flex; justify-content: space-between; align-items: start;">
                                <div>
                                    <h3 style="margin: 0; color: #0f172a; font-size: 18px;">{item['name']}</h3>
                                    <div style="margin-top: 8px; font-size: 14px; color: #64748b;">
                                        <span style="background: #f1f5f9; padding: 4px 8px; border-radius: 6px; margin-right: 10px;">💰 Sell: ₹{item['price']}</span>
                                        <span style="background: #f1f5f9; padding: 4px 8px; border-radius: 6px; margin-right: 10px;">📑 Cost: ₹{item['cost_price']}</span>
                                        <span style="background: {'#fee2e2' if item['stock'] <= 5 else '#f0fdf4'}; color: {'#991b1b' if item['stock'] <= 5 else '#166534'}; padding: 4px 8px; border-radius: 6px; font-weight: 600;">
                                            📦 Stock: {item['stock']}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        col_btns1, col_btns2, _ = st.columns([1, 1, 4])
                        with col_btns1:
                            if st.button("✏️ Edit", key=f"edit_{item['id']}", use_container_width=True):
                                st.session_state[f"editing_{item['id']}"] = True
                                st.rerun()
                        with col_btns2:
                            if st.button("🗑️", key=f"delete_{item['id']}", use_container_width=True):
                                st.session_state[f"confirm_delete_{item['id']}"] = True
                                st.rerun()
                        
                        # Edit form (shown when edit button clicked)
                        if st.session_state.get(f"editing_{item['id']}", False):
                            st.markdown("<div style='background: #f8fafc; padding: 20px; border-radius: 12px; border: 1px dashed #cbd5e1; margin-bottom: 20px;'>", unsafe_allow_html=True)
                            with st.form(key=f"edit_form_{item['id']}"):
                                st.write("**Edit Item Details**")
                                new_name = st.text_input("Name", value=item['name'], key=f"name_{item['id']}")
                                ce1, ce2, ce3 = st.columns(3)
                                with ce1:
                                    new_cost = st.number_input("Cost (₹)", value=float(item.get('cost_price', 0)), min_value=0.0, step=10.0, key=f"cost_{item['id']}")
                                with ce2:
                                    new_price = st.number_input("Selling Price (₹)", value=float(item['price']), min_value=0.0, step=10.0, key=f"price_{item['id']}")
                                with ce3:
                                    new_stock = st.number_input("Stock Qty", value=int(item.get('stock', 0)), min_value=0, step=1, key=f"stock_{item['id']}")
                                
                                cs, cc = st.columns(2)
                                with cs:
                                    if st.form_submit_button("✅ Update Item", use_container_width=True):
                                        if new_name.strip() and new_price > 0:
                                            try:
                                                db.collection("items_master").document(item['id']).update({
                                                    "name": new_name.strip(),
                                                    "price": new_price,
                                                    "cost_price": new_cost,
                                                    "stock": new_stock
                                                })
                                                st.success(f"Updated '{new_name}'")
                                                del st.session_state[f"editing_{item['id']}"]
                                                clear_items_cache()
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"Error: {e}")
                                with cc:
                                    if st.form_submit_button("Cancel", use_container_width=True):
                                        del st.session_state[f"editing_{item['id']}"]
                                        st.rerun()
                            st.markdown("</div>", unsafe_allow_html=True)
                        
                        # Delete confirmation
                        if st.session_state.get(f"confirm_delete_{item['id']}", False):
                            st.error(f"Are you sure you want to delete **{item['name']}**?")
                            cy, cn = st.columns(2)
                            with cy:
                                if st.button("Yes, Delete", key=f"confirm_yes_{item['id']}", type="primary", use_container_width=True):
                                    db.collection("items_master").document(item['id']).delete()
                                    clear_items_cache()
                                    del st.session_state[f"confirm_delete_{item['id']}"]
                                    st.rerun()
                            with cn:
                                if st.button("No, Keep it", key=f"confirm_no_{item['id']}", use_container_width=True):
                                    del st.session_state[f"confirm_delete_{item['id']}"]
                                    st.rerun()
                        
                        st.markdown("<div style='margin-bottom: 30px;'></div>", unsafe_allow_html=True)
    
    except Exception as e:
        st.error(f"❌ Error loading items: {e}")

