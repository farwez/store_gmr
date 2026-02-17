import streamlit as st
from firebase_config import db
from datetime import datetime, timedelta
import pandas as pd
from utils import inject_custom_css, render_sidebar, get_ist_time

st.set_page_config(page_title="Store Management", layout="wide", page_icon="🏪")
inject_custom_css()
render_sidebar()

st.title("🏪 Store Management Dashboard")
st.markdown("---")

# Helper function for today's date
def today_string():
    return get_ist_time().strftime("%Y-%m-%d")

# ==================== QUICK STATS ====================
st.subheader("📊 Today's Overview")

col1, col2, col3, col4 = st.columns(4)

try:
    # Get today's sales
    today_sales = db.collection("sales").where("date", "==", today_string()).stream()
    sales_list = [sale.to_dict() for sale in today_sales]
    
    # Calculate stats
    today_revenue = sum(sale.get("total", 0) for sale in sales_list)
    today_orders = len(sales_list)
    today_items_sold = sum(
        sum(item.get("qty", 0) for item in sale.get("items", []))
        for sale in sales_list
    )
    
    # Get total items in catalog
    items_count = len(list(db.collection("items_master").stream()))
    
    with col1:
        st.metric(
            label="💰 Today's Revenue",
            value=f"₹{today_revenue:,.0f}",
            delta=f"{today_orders} orders"
        )
    
    with col2:
        st.metric(
            label="🛒 Orders Today",
            value=today_orders,
            delta=f"{today_items_sold} items sold"
        )
    
    with col3:
        st.metric(
            label="📦 Total Products",
            value=items_count,
            delta="In catalog"
        )
    
    with col4:
        # Calculate average order value
        avg_order = today_revenue / today_orders if today_orders > 0 else 0
        st.metric(
            label="📈 Avg Order Value",
            value=f"₹{avg_order:,.0f}",
            delta="Per order"
        )

except Exception as e:
    st.error(f"Error loading stats: {e}")

st.markdown("---")

# ==================== QUICK ACTIONS ====================
st.subheader("⚡ Quick Actions")

col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("🛒 New Sale", use_container_width=True, type="primary"):
        st.switch_page("pages/2_Sales.py")

with col2:
    if st.button("📦 Add Item", use_container_width=True):
        st.switch_page("pages/1_Items_Master.py")

with col3:
    if st.button("📊 View Reports", use_container_width=True):
        st.switch_page("pages/3_Reports.py")

with col4:
    if st.button("🧠 AI Insights", use_container_width=True):
        st.switch_page("pages/4_AI_Insights.py")

st.markdown("---")

# ==================== RECENT SALES ====================
st.subheader("🕐 Recent Sales")

try:
    # Get last 10 sales
    recent_sales = db.collection("sales").order_by("timestamp", direction="DESCENDING").limit(10).stream()
    sales_data = []
    
    for sale in recent_sales:
        data = sale.to_dict()
        sales_data.append({
            "Date": data.get("date", "N/A"),
            "Customer": data.get("customer_name", "N/A"),
            "Items": len(data.get("items", [])),
            "Total": f"₹{data.get('total', 0):,.0f}",
            "Time": data.get("timestamp", get_ist_time()).strftime("%I:%M %p") if isinstance(data.get("timestamp"), datetime) else "N/A"
        })
    
    if sales_data:
        df = pd.DataFrame(sales_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("📭 No sales yet. Create your first sale!")

except Exception as e:
    st.error(f"Error loading recent sales: {e}")


# ==================== FOOTER ====================
st.caption("💡 Use the sidebar to navigate between different modules")
st.caption(f"🕐 Last updated: {get_ist_time().strftime('%I:%M:%S %p')}")
