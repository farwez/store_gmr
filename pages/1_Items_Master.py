import streamlit as st
from firebase_config import db
import pandas as pd
from utils import inject_custom_css, render_sidebar, clear_items_cache

st.set_page_config(page_title="Items Master", layout="wide", page_icon="📦")
inject_custom_css()
render_sidebar()
st.title("📦 Items Master")

# Create tabs for better organization
tab1, tab2 = st.tabs(["➕ Add Item", "📋 Manage Items"])

# ==================== TAB 1: ADD ITEM ====================
with tab1:
    st.subheader("Add New Item")
    
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Item Name", key="add_name")
    with col2:
        price = st.number_input("Selling Price (₹)", min_value=0.0, step=10.0, key="add_price")
    
    if st.button("➕ Add Item", type="primary", use_container_width=True):
        if not name or name.strip() == "":
            st.error("⚠️ Please enter an item name")
        elif price <= 0:
            st.error("⚠️ Price must be greater than 0")
        else:
            try:
                db.collection("items_master").add({
                    "name": name.strip(),
                    "price": price
                })
                st.success(f"✅ Item '{name}' added successfully!")
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
                "price": data.get("price", 0)
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
                        col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
                        
                        with col1:
                            st.write(f"**{item['name']}**")
                        
                        with col2:
                            st.write(f"₹{item['price']}")
                        
                        with col3:
                            # Edit button
                            if st.button("✏️ Edit", key=f"edit_{item['id']}"):
                                st.session_state[f"editing_{item['id']}"] = True
                                st.rerun()
                        
                        with col4:
                            # Delete button
                            if st.button("🗑️", key=f"delete_{item['id']}"):
                                st.session_state[f"confirm_delete_{item['id']}"] = True
                                st.rerun()
                        
                        # Edit form (shown when edit button clicked)
                        if st.session_state.get(f"editing_{item['id']}", False):
                            with st.form(key=f"edit_form_{item['id']}"):
                                st.write("**Edit Item**")
                                new_name = st.text_input("Name", value=item['name'], key=f"name_{item['id']}")
                                new_price = st.number_input("Price (₹)", value=float(item['price']), min_value=0.0, step=10.0, key=f"price_{item['id']}")
                                
                                col_save, col_cancel = st.columns(2)
                                with col_save:
                                    if st.form_submit_button("💾 Save", use_container_width=True):
                                        if new_name.strip() and new_price > 0:
                                            try:
                                                db.collection("items_master").document(item['id']).update({
                                                    "name": new_name.strip(),
                                                    "price": new_price
                                                })
                                                st.success(f"✅ Updated '{new_name}'")
                                                del st.session_state[f"editing_{item['id']}"]
                                                clear_items_cache()
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"❌ Error: {e}")
                                        else:
                                            st.error("Invalid name or price")
                                
                                with col_cancel:
                                    if st.form_submit_button("❌ Cancel", use_container_width=True):
                                        del st.session_state[f"editing_{item['id']}"]
                                        st.rerun()
                        
                        # Delete confirmation (shown when delete button clicked)
                        if st.session_state.get(f"confirm_delete_{item['id']}", False):
                            st.warning(f"⚠️ Are you sure you want to delete **{item['name']}**?")
                            col_yes, col_no = st.columns(2)
                            
                            with col_yes:
                                if st.button("✅ Yes, Delete", key=f"confirm_yes_{item['id']}", type="primary"):
                                    try:
                                        db.collection("items_master").document(item['id']).delete()
                                        st.success(f"🗑️ Deleted '{item['name']}'")
                                        clear_items_cache()
                                        del st.session_state[f"confirm_delete_{item['id']}"]
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ Error: {e}")
                            
                            with col_no:
                                if st.button("❌ Cancel", key=f"confirm_no_{item['id']}"):
                                    del st.session_state[f"confirm_delete_{item['id']}"]
                                    st.rerun()
                        
                        st.divider()
    
    except Exception as e:
        st.error(f"❌ Error loading items: {e}")
