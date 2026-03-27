import streamlit as st
import pandas as pd
import io
import plotly.express as px
from firebase_config import db
from datetime import datetime, timedelta
from utils import inject_custom_css, render_sidebar, get_ist_time, check_admin, clear_dashboard_cache

st.set_page_config(page_title="Expense Tracker", page_icon="💸", layout="wide", initial_sidebar_state="expanded")
inject_custom_css()
render_sidebar()
check_admin()

st.title("💸 Expense Tracker")
st.caption("Record all daily shop expenses. These are deducted from your net profit in the dashboard.")

# ═══════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════
CATEGORIES = [
    "Rent & Lease",
    "Staff Salaries / Wages",
    "Electricity / Utilities",
    "Tea / Snacks / Water",
    "Transport / Delivery",
    "Repairs & Maintenance",
    "Packaging Materials",
    "Marketing & Advertising",
    "Purchase / Restock",
    "Bank Charges / Fees",
    "Other / Miscellaneous",
]

@st.cache_data(ttl=180, show_spinner=False)
def fetch_expenses():
    docs = db.collection("expenses").order_by("date", direction="DESCENDING").stream()
    rows = []
    for d in docs:
        dd = d.to_dict()
        dd["_id"] = d.id
        rows.append(dd)
    return rows

today_str   = get_ist_time().strftime("%Y-%m-%d")
month_str   = get_ist_time().strftime("%Y-%m")

try:
    with st.spinner("Loading expenses..."):
        all_expenses = fetch_expenses()
except Exception as e:
    st.error(f"Error loading expenses: {e}")
    all_expenses = []

today_total = sum(e["amount"] for e in all_expenses if e.get("date","").startswith(today_str))
month_total = sum(e["amount"] for e in all_expenses if e.get("date","").startswith(month_str))

# Top Metrics
m1, m2, m3, m4 = st.columns(4)
m1.metric("Today's Total",  f"₹{today_total:,.2f}")
m2.metric("This Month",     f"₹{month_total:,.2f}")
m3.metric("Total Records",  len(all_expenses))
m4.metric("Last Updated",   get_ist_time().strftime("%I:%M %p"))

st.markdown("---")

tab1, tab2 = st.tabs(["➕ Add Expense", "📋 History & Analytics"])

# ═══════════════════════════════════════════════════════════════
# TAB 1 — ADD EXPENSE
# ═══════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Record New Expense")
    with st.form("add_exp_form", clear_on_submit=True, enter_to_submit=False):
        r1, r2 = st.columns(2)
        with r1:
            exp_date  = st.date_input("Date", value=get_ist_time().date())
            exp_cat   = st.selectbox("Category", CATEGORIES)
        with r2:
            exp_amt   = st.number_input("Amount (₹) *", min_value=0.01, value=100.0, step=10.0, format="%.2f")
            exp_desc  = st.text_input("Description / Notes", placeholder="e.g. Paid electricity bill for March")
        exp_paid_to = st.text_input("Paid To (Vendor / Person)", placeholder="e.g. Ravi Kumar (Caterer)")

        if st.form_submit_button("💾 Save Expense", type="primary", use_container_width=True):
            try:
                db.collection("expenses").add({
                    "date":        exp_date.strftime("%Y-%m-%d"),
                    "category":    exp_cat,
                    "amount":      exp_amt,
                    "description": exp_desc.strip() or "No description",
                    "paid_to":     exp_paid_to.strip(),
                    "recorded_by": st.session_state.get("username", "Admin"),
                    "timestamp":   get_ist_time(),
                })
                fetch_expenses.clear()
                clear_dashboard_cache()
                st.toast(f"✅ ₹{exp_amt:,.2f} saved under '{exp_cat}'")
                st.rerun()
            except Exception as e:
                st.error(f"Error saving: {e}")

# ═══════════════════════════════════════════════════════════════
# TAB 2 — HISTORY & ANALYTICS
# ═══════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Expense History")

    if not all_expenses:
        st.info("No expenses recorded yet.")
    else:
        # Filters
        f1, f2, f3 = st.columns(3)
        with f1:
            period = st.selectbox("Period", ["Today", "This Month", "Last 30 Days", "All Time"])
        with f2:
            cat_opts = ["All Categories"] + CATEGORIES
            flt_cat  = st.selectbox("Category", cat_opts)
        with f3:
            min_amt = st.number_input("Min Amount (₹)", min_value=0.0, value=0.0, step=50.0)

        # Apply filters
        filtered = all_expenses
        if period == "Today":
            filtered = [e for e in filtered if e.get("date","").startswith(today_str)]
        elif period == "This Month":
            filtered = [e for e in filtered if e.get("date","").startswith(month_str)]
        elif period == "Last 30 Days":
            cutoff = (get_ist_time() - timedelta(days=30)).strftime("%Y-%m-%d")
            filtered = [e for e in filtered if e.get("date","") >= cutoff]
        if flt_cat != "All Categories":
            filtered = [e for e in filtered if e.get("category") == flt_cat]
        if min_amt > 0:
            filtered = [e for e in filtered if e.get("amount", 0) >= min_amt]

        if not filtered:
            st.warning("No expenses match the filters.")
        else:
            # Summary
            total_filtered = sum(e["amount"] for e in filtered)
            fs1, fs2, fs3 = st.columns(3)
            fs1.metric("Total (Filtered)", f"₹{total_filtered:,.2f}")
            fs2.metric("Records", len(filtered))
            fs3.metric("Avg per Entry", f"₹{total_filtered/len(filtered):,.2f}")

            st.divider()

            # Table
            df = pd.DataFrame(filtered)
            display_cols = {
                "date":        "Date",
                "category":    "Category",
                "amount":      "Amount (₹)",
                "description": "Description",
                "paid_to":     "Paid To",
            }
            available = {k: v for k, v in display_cols.items() if k in df.columns}
            df_disp = df[list(available.keys())].rename(columns=available)
            df_disp["Amount (₹)"] = df_disp["Amount (₹)"].apply(lambda x: f"₹{x:,.2f}")
            st.dataframe(df_disp, use_container_width=True, hide_index=True)

            # Category Breakdown Chart
            st.divider()
            st.markdown("#### Spend by Category")
            try:
                cat_df = pd.DataFrame(filtered).groupby("category")["amount"].sum().reset_index()
                fig    = px.pie(cat_df, values="amount", names="category", hole=0.45,
                                color_discrete_sequence=px.colors.qualitative.Bold)
                fig.update_layout(margin=dict(t=20, b=0, l=0, r=0), legend=dict(orientation="h"))
                st.plotly_chart(fig, use_container_width=True)
            except:
                pass

            # Export
            st.divider()
            buf = io.BytesIO()
            df_export = pd.DataFrame(filtered)
            # Strip timezone from any datetime columns (Firestore timestamps are tz-aware)
            for col in df_export.select_dtypes(include=["datetimetz"]).columns:
                df_export[col] = df_export[col].dt.tz_localize(None)
            df_export.to_excel(buf, index=False, sheet_name="Expenses")
            buf.seek(0)
            st.download_button("📥 Export to Excel", buf,
                               file_name=f"expenses_{today_str}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
