import streamlit as st
from firebase_config import db
from datetime import datetime, timedelta
import pandas as pd
from utils import inject_custom_css, render_sidebar, get_ist_time, check_admin

st.set_page_config(page_title="Expense Tracker", page_icon="💸", layout="wide")
inject_custom_css()
render_sidebar()
check_admin()

st.title("💸 Daily Expense Tracker")
st.markdown("Record daily shop expenses like rent, salaries, tea, and electricity to calculate true net profit.")
st.markdown("---")

# ==================== DATA FETCHING ====================
@st.cache_data(ttl=60)
def fetch_expenses():
    all_exp = db.collection("expenses").order_by("date", direction="DESCENDING").stream()
    data = []
    for exp in all_exp:
        e_dict = exp.to_dict()
        e_dict["id"] = exp.id
        data.append(e_dict)
    return data

try:
    expenses_data = fetch_expenses()
    
    # Calculate MTDs
    current_month = get_ist_time().strftime("%Y-%m")
    current_day = get_ist_time().strftime("%Y-%m-%d")
    
    today_expense = sum(e["amount"] for e in expenses_data if e.get("date", "").startswith(current_day))
    month_expense = sum(e["amount"] for e in expenses_data if e.get("date", "").startswith(current_month))
    
    # Top metrics
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric("Today's Expenses", f"₹{today_expense:,.2f}")
    with col_m2:
        st.metric("This Month's Expenses", f"₹{month_expense:,.2f}")
    with col_m3:
        st.metric("Total Records", len(expenses_data))
        
    st.markdown("---")
    
    # ==================== UI WORKSPACE ====================
    tab1, tab2 = st.tabs(["➕ Add New Expense", "📋 Expense History"])
    
    with tab1:
        st.subheader("Record a New Expense")
        
        with st.form("add_expense_form", clear_on_submit=True):
            col_f1, col_f2 = st.columns(2)
            
            with col_f1:
                exp_date = st.date_input("Date", value=get_ist_time().date())
                exp_category = st.selectbox("Category", [
                    "Rent & Leases",
                    "Staff Salaries/Wages",
                    "Electricity / Utilities",
                    "Tea / Snacks / Water",
                    "Transport / Travel",
                    "Repairs & Maintenance",
                    "Packaging Materials",
                    "Marketing / Ads",
                    "Other / Misc"
                ])
                
            with col_f2:
                exp_amount = st.number_input("Amount (₹)", min_value=1.0, value=100.0, step=50.0)
                exp_desc = st.text_input("Description / Notes", placeholder="E.g., Bought tea for staff")
                
            # Submit button
            submitted = st.form_submit_button("💾 Save Expense", type="primary", use_container_width=True)
            
            if submitted:
                new_exp = {
                    "date": exp_date.strftime("%Y-%m-%d"),
                    "category": exp_category,
                    "amount": exp_amount,
                    "description": exp_desc if exp_desc else "No description",
                    "timestamp": get_ist_time()
                }
                
                db.collection("expenses").add(new_exp)
                st.cache_data.clear()
                st.success("✅ Expense added successfully!")
                st.rerun()

    with tab2:
        st.subheader("Expense History")
        
        if expenses_data:
            # Filters
            col_filt1, col_filt2 = st.columns(2)
            with col_filt1:
                filt_month = st.selectbox("Filter by Month", ["All Time", current_month], index=1)
            with col_filt2:
                categories = ["All Categories"] + list(set([e['category'] for e in expenses_data]))
                filt_cat = st.selectbox("Filter by Category", categories)
                
            filtered_data = expenses_data
            
            if filt_month != "All Time":
                filtered_data = [e for e in filtered_data if e.get("date", "").startswith(filt_month)]
                
            if filt_cat != "All Categories":
                filtered_data = [e for e in filtered_data if e.get("category") == filt_cat]
                
            if filtered_data:
                # Convert for display
                df = pd.DataFrame(filtered_data)[["date", "category", "amount", "description"]]
                df.columns = ["Date", "Category", "Amount (₹)", "Description"]
                
                # Format currency
                df["Amount (₹)"] = df["Amount (₹)"].apply(lambda x: f"₹{x:,.2f}")
                
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                # Breakdown Chart
                st.markdown("#### Spend by Category")
                cat_breakdown = pd.DataFrame(filtered_data).groupby("category")["amount"].sum().reset_index()
                
                import plotly.express as px
                fig = px.pie(cat_breakdown, values="amount", names="category", hole=0.4)
                fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig, use_container_width=True)
                
            else:
                st.info("No expenses found matching the selected filters.")
        else:
            st.info("No expenses recorded yet. Switch to the 'Add New Expense' tab to get started.")

except Exception as e:
    st.error(f"Error loading Expense Tracker: {e}")
    import traceback
    st.code(traceback.format_exc())
