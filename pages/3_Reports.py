import streamlit as st
from firebase_config import db
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.graph_objects as go
import smtplib
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from utils import inject_custom_css, render_sidebar, get_ist_time, check_admin, get_settings

st.set_page_config(page_title="Reports", layout="wide", page_icon="📊", initial_sidebar_state="expanded")
inject_custom_css()
render_sidebar()
check_admin()

st.title("📊 Sales Reports & Analytics")
st.markdown("---")

# Create tabs for different report types
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📅 Date Range Reports", 
    "🏆 Top Sellers", 
    "👥 Customer Reports", 
    "📲 WhatsApp Share",
    "🧠 AI Health",
    "📧 Dispatch Center"
])

# ==================== TAB 1: DATE RANGE REPORTS ====================
with tab1:
    st.subheader("📅 Sales by Date Range")
    st.markdown("Select a date range to view detailed sales reports")
    
    # Date inputs with better styling
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        start_date = st.date_input(
            "📅 Start Date", 
            value=(get_ist_time() - timedelta(days=7)).date(),
            help="Select the starting date for the report"
        )
    with col2:
        end_date = st.date_input(
            "📅 End Date", 
            value=get_ist_time().date(),
            help="Select the ending date for the report"
        )
    with col3:
        st.write("")  # Spacer
        st.write("")  # Spacer
    
    st.markdown("---")
    
    # Search/Filter options
    st.markdown("#### 🔍 Filters")
    col_filter1, col_filter2 = st.columns(2)
    with col_filter1:
        customer_search = st.text_input(
            "Customer Name", 
            placeholder="Type customer name...",
            help="Filter by customer name"
        )
    with col_filter2:
        min_amount = st.number_input(
            "Minimum Amount (₹)", 
            min_value=0.0, 
            value=0.0, 
            step=100.0,
            help="Show only sales above this amount"
        )


# ── Module-level cached functions for Tab 1 ──────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def get_sales_report_records(start_str, end_str):
    try:
        sales_ref = db.collection("sales") \
                      .where("date", ">=", start_str) \
                      .where("date", "<=", end_str) \
                      .select(["date", "total", "customer_name", "customer_phone", "items", "timestamp", "voided"]) \
                      .stream()
        records = []
        for sale in sales_ref:
            d = sale.to_dict()
            if d.get("voided", False): continue
            items = d.get("items", [])
            cost = sum(i.get("cost", 0) * i.get("qty", 0) for i in items)
            total = d.get("total", 0)
            records.append({
                "Date": d.get("date", ""),
                "Customer": d.get("customer_name", "N/A"),
                "Phone": d.get("customer_phone", "N/A"),
                "Items_Detail": ", ".join([f"{i.get('name', 'Unknown')} x{i.get('qty', 0)}" for i in items]),
                "Quantity": sum(i.get("qty", 0) for i in items),
                "Total": total,
                "Cost": cost,
                "Profit": total - cost,
                "Time": d.get("timestamp").strftime("%I:%M %p") if isinstance(d.get("timestamp"), datetime) else "N/A"
            })
        return records
    except Exception:
        return []

@st.cache_data(ttl=300, show_spinner=False)
def get_returns_summary(start_str, end_str):
    try:
        returns_ref = db.collection("returns").where("date", ">=", start_str).where("date", "<=", end_str).stream()
        r_total, r_cost_red = 0, 0
        for ret in returns_ref:
            rd = ret.to_dict()
            r_total += rd.get("return_amount", 0)
            r_cost_red += sum(i.get("cost", 0) * i.get("qty", 0) for i in rd.get("return_items", []))
        return r_total, r_cost_red
    except Exception:
        return 0, 0

# ── Tab 1 continued ─────────────────────────────────────────────────────────
with tab1:
    if st.button("📊 Generate Report", type="primary", use_container_width=True):
        with st.spinner("Processing..."):
            _s = start_date.strftime("%Y-%m-%d")
            _e = end_date.strftime("%Y-%m-%d")
            sales_data = get_sales_report_records(_s, _e)
            ret_total, ret_cost_red = get_returns_summary(_s, _e)

            if sales_data:
                df = pd.DataFrame(sales_data)
                if customer_search:
                    df = df[df['Customer'].str.contains(customer_search, case=False, na=False)]
                if min_amount > 0:
                    df = df[df['Total'] >= min_amount]

                if df.empty:
                    st.warning("No records match the selected filters.")
                else:
                    gross_rev   = df['Total'].sum()
                    gross_profit = df['Profit'].sum()
                    net_rev     = gross_rev - ret_total
                    net_profit  = gross_profit - (ret_total - ret_cost_red)
                    margin      = (net_profit / net_rev * 100) if net_rev > 0 else 0

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Orders", len(df), f"₹{gross_rev:,.0f} Gross")
                    c2.metric("Net Revenue", f"₹{net_rev:,.0f}", f"-₹{ret_total:,.0f} Returns", delta_color="inverse")
                    c3.metric("Net Profit", f"₹{net_profit:,.0f}", f"{margin:.1f}% Margin")
                    c4.metric("Units (Net)", int(df['Quantity'].sum()))

                    st.markdown("---")
                    st.dataframe(df.drop(columns=["Cost", "Profit"]), use_container_width=True, hide_index=True)

                    out = io.BytesIO()
                    df.to_excel(out, index=False)
                    st.download_button("📥 Download Excel Report", out.getvalue(), file_name=f"report_{_s}.xlsx", use_container_width=True)
                    st.line_chart(df.groupby("Date")["Total"].sum())
            else:
                st.info("No sales found for this date range.")

# ==================== TAB 2: TOP SELLERS ====================
with tab2:
    st.subheader("🏆 Best Selling Products")
    st.markdown("Analyze which products generate the most revenue")
    
    # Date range for top sellers
    col1, col2 = st.columns(2)
    with col1:
        top_start_date = st.date_input(
            "📅 From Date", 
            value=(get_ist_time() - timedelta(days=30)).date(), 
            key="top_start",
            help="Start date for analysis"
        )
    with col2:
        top_end_date = st.date_input(
            "📅 To Date", 
            value=get_ist_time().date(), 
            key="top_end",
            help="End date for analysis"
        )
    
    if st.button("🔍 Analyze Top Sellers", type="primary"):
        try:
            start_str = top_start_date.strftime("%Y-%m-%d")
            end_str = top_end_date.strftime("%Y-%m-%d")
            sales_ref = db.collection("sales").where("date", ">=", start_str).where("date", "<=", end_str).select(["items", "date", "voided"]).stream()
            item_stats = {}
            
            for sale in sales_ref:
                data = sale.to_dict()
                if data.get("voided", False):
                    continue
                for item in data.get("items", []):
                    item_name = item.get("name", "Unknown")
                    qty = item.get("qty", 0)
                    price = item.get("price", 0)
                    revenue = qty * price
                    
                    if item_name not in item_stats:
                        item_stats[item_name] = {"quantity": 0, "revenue": 0, "orders": 0}
                    
                    item_stats[item_name]["quantity"] += qty
                    item_stats[item_name]["revenue"] += revenue
                    item_stats[item_name]["orders"] += 1
            
            if item_stats:
                # Convert to DataFrame
                top_items = []
                for name, stats in item_stats.items():
                    top_items.append({
                        "Product": name,
                        "Quantity Sold": stats["quantity"],
                        "Revenue": stats["revenue"],
                        "Orders": stats["orders"],
                        "Avg Qty/Order": round(stats["quantity"] / stats["orders"], 2)
                    })
                
                df_top = pd.DataFrame(top_items)
                df_top = df_top.sort_values("Revenue", ascending=False)
                
                # Display top 10
                st.markdown("### 🥇 Top 10 Products by Revenue")
                st.dataframe(df_top.head(10), use_container_width=True, hide_index=True)
                
                # Chart
                st.markdown("### 📊 Revenue Breakdown")
                chart_data = df_top.head(10)[["Product", "Revenue"]].set_index("Product")
                st.bar_chart(chart_data)
                
                # Export
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_top.to_excel(writer, index=False, sheet_name='Top Sellers')
                output.seek(0)
                
                st.download_button(
                    label="📥 Download Top Sellers Report",
                    data=output,
                    file_name=f"top_sellers_{top_start_date}_to_{top_end_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.info("No sales data found for the selected period")
        
        except Exception as e:
            st.error(f"Error: {e}")

# ==================== TAB 3: CUSTOMER REPORTS ====================
with tab3:
    st.subheader("👥 Customer Analysis")
    st.markdown("Identify your most valuable customers")
    
    # Date range for customers
    col1, col2 = st.columns(2)
    with col1:
        cust_start_date = st.date_input(
            "📅 From Date", 
            value=(get_ist_time() - timedelta(days=30)).date(), 
            key="cust_start",
            help="Start date for customer analysis"
        )
    with col2:
        cust_end_date = st.date_input(
            "📅 To Date", 
            value=get_ist_time().date(), 
            key="cust_end",
            help="End date for customer analysis"
        )
    
    if st.button("👥 Analyze Customers", type="primary"):
        try:
            start_str = cust_start_date.strftime("%Y-%m-%d")
            end_str = cust_end_date.strftime("%Y-%m-%d")
            sales_ref = db.collection("sales").where("date", ">=", start_str).where("date", "<=", end_str).select(["customer_name", "customer_phone", "total", "items", "date", "voided"]).stream()
            customer_stats = {}
            
            for sale in sales_ref:
                data = sale.to_dict()
                if data.get("voided", False):
                    continue
                customer_name = data.get("customer_name", "Unknown")
                customer_phone = data.get("customer_phone", "N/A")
                total = data.get("total", 0)
                items_count = sum(item.get("qty", 0) for item in data.get("items", []))
                
                if customer_name not in customer_stats:
                    customer_stats[customer_name] = {
                        "phone": customer_phone,
                        "orders": 0,
                        "revenue": 0,
                        "items": 0
                    }
                
                customer_stats[customer_name]["orders"] += 1
                customer_stats[customer_name]["revenue"] += total
                customer_stats[customer_name]["items"] += items_count
            
            if customer_stats:
                # Convert to DataFrame
                customer_data = []
                for name, stats in customer_stats.items():
                    customer_data.append({
                        "Customer": name,
                        "Phone": stats["phone"],
                        "Orders": stats["orders"],
                        "Total Spent": stats["revenue"],
                        "Items Purchased": stats["items"],
                        "Avg Order Value": round(stats["revenue"] / stats["orders"], 2)
                    })
                
                df_customers = pd.DataFrame(customer_data)
                df_customers = df_customers.sort_values("Total Spent", ascending=False)
                
                # Display metrics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Customers", len(df_customers))
                with col2:
                    st.metric("Repeat Customers", len(df_customers[df_customers["Orders"] > 1]))
                with col3:
                    st.metric("Avg Customer Value", f"₹{df_customers['Total Spent'].mean():,.0f}")
                
                st.markdown("---")
                
                # Display table
                st.dataframe(df_customers, use_container_width=True, hide_index=True)
                
                # Export
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_customers.to_excel(writer, index=False, sheet_name='Customer Report')
                output.seek(0)
                
                st.download_button(
                    label="📥 Download Customer Report",
                    data=output,
                    file_name=f"customer_report_{cust_start_date}_to_{cust_end_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.info("No customer data found for the selected period")
        
        except Exception as e:
            st.error(f"Error: {e}")
# ==================== TAB 4: INSTANT SHARE (WHATSAPP) ====================
with tab4:
    st.subheader("📲 WhatsApp & Quick Reporting")
    st.markdown("Generate a professional summary message to share instantly with partners or owners.")
    
    col_share1, col_share2 = st.columns(2)
    with col_share1:
        share_start = st.date_input("Summary From", value=get_ist_time().date(), key="share_start")
    with col_share2:
        share_end = st.date_input("Summary To", value=get_ist_time().date(), key="share_end")
        
    st.markdown("---")
    
    if st.button("📝 Generate WhatsApp Summary", type="primary", use_container_width=True):
        try:
            start_str = share_start.strftime("%Y-%m-%d")
            end_str = share_end.strftime("%Y-%m-%d")
            sales_ref = db.collection("sales").where("date", ">=", start_str).where("date", "<=", end_str).select(["total", "items", "date", "voided"]).stream()
            count = 0
            revenue = 0
            profit = 0
            items_sold = 0
            
            for sale in sales_ref:
                data = sale.to_dict()
                if data.get("voided", False):
                    continue
                count += 1
                revenue += data.get("total", 0)
                items = data.get("items", [])
                sale_cost = sum(item.get("cost", 0) * item.get("qty", 0) for item in items)
                profit += (data.get("total", 0) - sale_cost)
                items_sold += sum(item.get("qty", 0) for item in items)

            if count > 0:
                sett = get_settings()
                store_name = sett.get("store_name", "GMR STORE").upper()
                
                msg = f"*📢 {store_name} - SALES REPORT*\n"
                msg += f"📅 Period: {share_start.strftime('%d-%b')} to {share_end.strftime('%d-%b')}\n"
                msg += "──────────────────────\n"
                msg += f"💰 *Total Revenue:* ₹{revenue:,.2f}\n"
                msg += f"📈 *Net Profit:* ₹{profit:,.2f}\n"
                msg += f"🛒 *Orders:* {count}\n"
                msg += f"📦 *Items Sold:* {items_sold}\n"
                msg += "──────────────────────\n"
                msg += f"⏰ Generated: {get_ist_time().strftime('%I:%M %p')}\n"
                msg += "🙏 _Automated by GMR Store Manager_"
                
                import urllib.parse
                wa_link = f"https://wa.me/?text={urllib.parse.quote(msg)}"
                
                st.markdown(f"""
                <div style='background: white; padding: 25px; border-radius: 15px; border: 1px solid #e2e8f0; margin-bottom: 20px;'>
                    <h5 style='margin-bottom:15px;'>📄 Message Preview</h5>
                    <pre style='background: #f8fafc; padding: 15px; border-radius: 10px; font-family: monospace; font-size: 14px; color: #1e293b; border: 1px solid #f1f5f9;'>{msg}</pre>
                </div>
                """, unsafe_allow_html=True)
                
                col_act1, col_act2 = st.columns(2)
                with col_act1:
                    st.link_button("📲 Share to WhatsApp", wa_link, use_container_width=True, type="primary")
                with col_act2:
                    st.button("📋 Copy to Clipboard", on_click=lambda: st.toast("Link ready! Open WhatsApp and paste."), use_container_width=True)
                    st.info("💡 Tip: You can also copy the preview text directly.")
            else:
                st.warning("No sales found for this period to generate a summary.")
                
        except Exception as e:
            st.error(f"Error: {e}")

# ==================== TAB 5: AI HEALTH ====================
with tab5:
    st.subheader("🧠 Business Health Score")
    st.markdown("AI-driven analysis of your overall store performance based on the last 30 days.")
    
    if st.button("Analyze Store Health", type="primary", use_container_width=True):
        with st.spinner("Analyzing performance metrics..."):
            try:
                end_health = get_ist_time().date()
                start_health = end_health - timedelta(days=30)
                
                start_str = start_health.strftime("%Y-%m-%d")
                end_str = end_health.strftime("%Y-%m-%d")
                sales_ref = db.collection("sales").where("date", ">=", start_str).where("date", "<=", end_str).select(["total", "discount_amount", "customer_name", "date", "voided"]).stream()
                
                total_revenue = 0
                total_orders = 0
                total_discount = 0
                customer_data = {}
                
                for sale in sales_ref:
                    data = sale.to_dict()
                    if data.get("voided", False):
                        continue
                    total_orders += 1
                    total_revenue += data.get("total", 0)
                    total_discount += data.get("discount_amount", 0)
                    
                    cust = data.get("customer_name", "Walk-in")
                    if cust not in customer_data: customer_data[cust] = 0
                    customer_data[cust] += 1
                
                if total_orders > 0:
                    avg_order_value = total_revenue / total_orders
                    repeat_customers = sum(1 for c in customer_data.values() if c > 1)
                    repeat_rate = (repeat_customers / len(customer_data) * 100) if customer_data else 0
                    avg_discount_pct = (total_discount / (total_revenue + total_discount) * 100) if (total_revenue + total_discount) > 0 else 0
                    
                    score = 0
                    
                    # Revenue points
                    if total_revenue > 10000: score += 25
                    elif total_revenue > 5000: score += 15
                    else: score += 5
                    
                    # Order volume points
                    if total_orders > 100: score += 25
                    elif total_orders > 50: score += 15
                    else: score += 5
                    
                    # Retention points
                    if repeat_rate > 30: score += 25
                    elif repeat_rate > 15: score += 15
                    else: score += 5
                    
                    # AOV points
                    if avg_order_value > 500: score += 25
                    elif avg_order_value > 300: score += 15
                    else: score += 5
                    
                    col_score1, col_score2, col_score3 = st.columns([1, 2, 1])
                    with col_score2:
                        fig_gauge = go.Figure(go.Indicator(
                            mode="gauge+number+delta",
                            value=score,
                            domain={'x': [0, 1], 'y': [0, 1]},
                            title={'text': "Store Health Score (out of 100)"},
                            gauge={
                                'axis': {'range': [None, 100]},
                                'bar': {'color': "darkblue"},
                                'steps': [
                                    {'range': [0, 40], 'color': "lightpink"},
                                    {'range': [40, 70], 'color': "lightyellow"},
                                    {'range': [70, 100], 'color': "lightgreen"}
                                ],
                                'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 90}
                            }
                        ))
                        st.plotly_chart(fig_gauge, use_container_width=True)
                        
                        if score >= 80:
                            st.success("🎉 Excellent! Your business is performing great!")
                        elif score >= 50:
                            st.info("👍 Good performance! Room for improvement in retention.")
                        else:
                            st.warning("⚠️ Average performance. Focus on increasing order values.")
                            
                    st.markdown("---")
                    st.markdown("### 💡 AI Recommendations")
                    if repeat_rate < 30:
                        st.write("🔹 **Customer Retention:** Your repeat rate is low. Consider a loyalty program.")
                    if avg_discount_pct > 10:
                        st.write("🔹 **Discounting:** High discount rate detected. Try bundling instead of flat discounts.")
                    if avg_order_value < 300:
                        st.write("🔹 **Order Value:** Try upselling small items at the checkout counter.")
                        
                else:
                    st.info("No sales data in the last 30 days to analyze.")
            except Exception as e:
                st.error(f"Error calculating health: {e}")

# ==================== TAB 6: DISPATCH CENTER (EMAIL & SETTINGS) ====================
with tab6:
    st.subheader("📧 Report Dispatch Center")
    st.markdown("Set once, then send by one click or auto-send daily.")

    def _get_report_period_dates(period_label: str):
        today = get_ist_time().date()
        if period_label == "Today":
            return today, today
        if period_label == "Yesterday":
            y = today - timedelta(days=1)
            return y, y
        return today - timedelta(days=7), today

    def _prepare_report_data(start_date, end_date):
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        sales_ref = db.collection("sales").where("date", ">=", start_str).where("date", "<=", end_str).select([
            "date", "customer_name", "payment_method", "items", "total", "discount_amount", "voided", "entered_by", "entered_by_username"
        ]).stream()

        sales_rows = []
        gross_revenue = 0.0
        gross_profit = 0.0
        total_orders = 0
        total_items = 0

        for sale in sales_ref:
            data = sale.to_dict()
            if data.get("voided", False):
                continue

            items = data.get("items", [])
            qty = sum(item.get("qty", 0) for item in items)
            cost = sum(item.get("cost", 0) * item.get("qty", 0) for item in items)
            total = float(data.get("total", 0) or 0)

            total_orders += 1
            total_items += qty
            gross_revenue += total
            gross_profit += total - cost

            sales_rows.append({
                "Date": data.get("date", ""),
                "Customer": data.get("customer_name", "Walk-in"),
                "Entered By": data.get("entered_by") or data.get("entered_by_username", "N/A"),
                "Payment": data.get("payment_method", "Cash"),
                "Items": qty,
                "Total": total,
                "Subtotal": float(data.get("subtotal", total) or total),
                "Discount": float(data.get("discount_amount", 0) or 0),
                "_items": items,  # kept for itemised sheet, removed before display
            })

        # ── Returns ──────────────────────────────────────────────────────────────
        returns_ref = db.collection("returns").where("date", ">=", start_str).where("date", "<=", end_str).stream()

        returns_rows = []
        returns_items_rows = []
        returns_total = 0.0
        returns_cost_reduction = 0.0

        for ret in returns_ref:
            ret_data = ret.to_dict()
            ret_amt = float(ret_data.get("return_amount", 0) or 0)
            returns_total += ret_amt
            ret_reason = ret_data.get("reason", "")
            ret_customer = ret_data.get("customer_name", ret_data.get("customer", "N/A"))
            ret_date = ret_data.get("date", "")
            ret_original_date = ret_data.get("original_sale_date", "")
            ret_by = ret_data.get("entered_by") or ret_data.get("entered_by_username", "")

            for ri in ret_data.get("return_items", []):
                cst = float(ri.get("cost", 0) or 0) * int(ri.get("qty", 0) or 0)
                returns_cost_reduction += cst
                returns_items_rows.append({
                    "Return Date": ret_date,
                    "Original Sale Date": ret_original_date,
                    "Customer": ret_customer,
                    "Item": ri.get("name", "?"),
                    "Qty": ri.get("qty", 0),
                    "Price (₹)": round(float(ri.get("price", 0) or 0), 2),
                    "Line Refund (₹)": round(ri.get("qty", 0) * float(ri.get("price", 0) or 0), 2),
                    "Reason": ret_reason,
                    "Staff": ret_by,
                })

            returns_rows.append({
                "Date": ret_date,
                "Original Sale Date": ret_original_date,
                "Customer": ret_customer,
                "Items Returned": sum(i.get("qty", 0) for i in ret_data.get("return_items", [])),
                "Refund Amount (₹)": round(ret_amt, 2),
                "Reason": ret_reason,
                "Staff": ret_by,
            })

        # ── Stock Entries ─────────────────────────────────────────────────────────
        stock_ref = db.collection("stock_entries").where("date", ">=", start_str).where("date", "<=", end_str).stream()
        stock_rows = []
        for se in stock_ref:
            sd = se.to_dict()
            stock_rows.append({
                "Date": sd.get("date", ""),
                "Item": sd.get("item_name", ""),
                "Boxes": int(sd.get("boxes", 0) or 0),
                "Qty per Box": int(sd.get("qty_per_box", 0) or 0),
                "Qty Added": int(sd.get("qty_added", 0) or 0),
                "Old Stock": int(sd.get("previous_stock", 0) or 0),
                "New Stock": int(sd.get("new_stock", 0) or 0),
                "Cost Price (₹)": round(float(sd.get("cost_price", 0) or 0), 2),
                "Selling Price (₹)": round(float(sd.get("selling_price", 0) or 0), 2),
                "Type": sd.get("entry_type", ""),
                "Notes": sd.get("notes", ""),
                "Staff": sd.get("created_by", ""),
            })

        # ── Sales item-wise detail ────────────────────────────────────────────────
        # Build sale_no for each sale_row entry
        for i, row in enumerate(sales_rows):
            row["Sale #"] = i + 1

        sales_items_rows = []
        for s in sales_rows:
            for it in s.get("_items", []):
                sales_items_rows.append({
                    "Sale #": s["Sale #"],
                    "Date": s["Date"],
                    "Customer": s["Customer"],
                    "Entered By": s["Entered By"],
                    "Payment": s["Payment"],
                    "Item": it.get("name", ""),
                    "Qty": it.get("qty", 0),
                    "Unit Price (₹)": round(float(it.get("price", 0) or 0), 2),
                    "Line Total (₹)": round(it.get("qty", 0) * float(it.get("price", 0) or 0), 2),
                    "Discount on Sale (₹)": round(float(s.get("Discount", 0) or 0), 2),
                    "Sale Total (₹)": round(float(s.get("Total", 0) or 0), 2),
                })

        # Clean sales_rows for display (remove internal _items)
        display_sales_rows = []
        for s in sales_rows:
            display_sales_rows.append({
                "Sale #": s["Sale #"],
                "Date": s["Date"],
                "Customer": s["Customer"],
                "Entered By": s["Entered By"],
                "Payment": s["Payment"],
                "Items (count)": s["Items"],
                "Subtotal (₹)": round(float(s.get("Subtotal", s.get("Total", 0))), 2),
                "Discount (₹)": round(float(s.get("Discount", 0) or 0), 2),
                "Total (₹)": round(float(s["Total"] or 0), 2),
            })

        net_revenue = gross_revenue - returns_total
        net_profit = gross_profit - (returns_total - returns_cost_reduction)

        summary_df = pd.DataFrame([
            {"Metric": "Report Period", "Value": f"{start_str} to {end_str}"},
            {"Metric": "Total Orders", "Value": total_orders},
            {"Metric": "Total Items Sold", "Value": total_items},
            {"Metric": "Gross Revenue (₹)", "Value": round(gross_revenue, 2)},
            {"Metric": "Total Discounts (₹)", "Value": round(sum(float(s.get("Discount", 0) or 0) for s in sales_rows), 2)},
            {"Metric": "Returns (₹)", "Value": round(returns_total, 2)},
            {"Metric": "Net Revenue (₹)", "Value": round(net_revenue, 2)},
            {"Metric": "Net Profit (₹)", "Value": round(net_profit, 2)},
            {"Metric": "Stock Entries Made", "Value": len(stock_rows)},
            {"Metric": "Total Boxes Received", "Value": sum(r["Boxes"] for r in stock_rows)},
            {"Metric": "Total Units Received", "Value": sum(r["Qty Added"] for r in stock_rows)},
        ])

        sales_df = pd.DataFrame(display_sales_rows) if display_sales_rows else pd.DataFrame(
            columns=["Sale #", "Date", "Customer", "Entered By", "Payment", "Items (count)", "Subtotal (₹)", "Discount (₹)", "Total (₹)"])

        sales_items_df = pd.DataFrame(sales_items_rows) if sales_items_rows else pd.DataFrame(
            columns=["Sale #", "Date", "Customer", "Entered By", "Payment", "Item", "Qty", "Unit Price (₹)", "Line Total (₹)", "Discount on Sale (₹)", "Sale Total (₹)"])

        returns_df = pd.DataFrame(returns_rows) if returns_rows else pd.DataFrame(
            columns=["Date", "Original Sale Date", "Customer", "Items Returned", "Refund Amount (₹)", "Reason", "Staff"])

        returns_items_df = pd.DataFrame(returns_items_rows) if returns_items_rows else pd.DataFrame(
            columns=["Return Date", "Original Sale Date", "Customer", "Item", "Qty", "Price (₹)", "Line Refund (₹)", "Reason", "Staff"])

        stock_df = pd.DataFrame(stock_rows) if stock_rows else pd.DataFrame(
            columns=["Date", "Item", "Boxes", "Qty per Box", "Qty Added", "Old Stock", "New Stock", "Cost Price (₹)", "Selling Price (₹)", "Type", "Notes", "Staff"])

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            summary_df.to_excel(writer, index=False, sheet_name='Summary')
            sales_df.to_excel(writer, index=False, sheet_name='Sales (Overview)')
            sales_items_df.to_excel(writer, index=False, sheet_name='Sales (Itemised)')
            returns_df.to_excel(writer, index=False, sheet_name='Returns (Overview)')
            returns_items_df.to_excel(writer, index=False, sheet_name='Returns (Itemised)')
            stock_df.to_excel(writer, index=False, sheet_name='Stock Entries')
        output.seek(0)

        return {
            "start_str": start_str,
            "end_str": end_str,
            "total_orders": total_orders,
            "total_items": total_items,
            "gross_revenue": gross_revenue,
            "returns_total": returns_total,
            "net_revenue": net_revenue,
            "net_profit": net_profit,
            "excel_bytes": output.getvalue(),
            "sales_rows": display_sales_rows,
            "sales_items_rows": sales_items_rows,
            "returns_rows": returns_rows,
            "returns_items_rows": returns_items_rows,
            "stock_rows": stock_rows,
        }

    def _send_report_email(cfg: dict, period_label: str):
        sender_email = (cfg.get("sender_email") or "").strip()
        sender_password = (cfg.get("sender_password") or "").strip()
        recipients = (cfg.get("recipient_emails") or "").strip()

        if not sender_email or not sender_password or not recipients:
            raise ValueError("Sender email, app password, and recipient email are required.")

        recipients_list = [addr.strip() for addr in recipients.split(",") if addr.strip()]
        if not recipients_list:
            raise ValueError("Please provide at least one valid recipient email.")

        start_date, end_date = _get_report_period_dates(period_label)
        report_data = _prepare_report_data(start_date, end_date)

        store_name = get_settings().get("store_name", "Store")
        msg = EmailMessage()
        msg["Subject"] = f"{store_name} Sales Report • {period_label}"
        msg["From"] = sender_email
        msg["To"] = ", ".join(recipients_list)

        msg.set_content(
            f"{store_name} Sales Report\n"
            f"Period: {report_data['start_str']} to {report_data['end_str']}\n"
            f"Orders: {report_data['total_orders']} | Items Sold: {report_data['total_items']}\n"
            f"Gross Revenue: Rs.{report_data['gross_revenue']:,.2f}\n"
            f"Returns: Rs.{report_data['returns_total']:,.2f}\n"
            f"Net Revenue: Rs.{report_data['net_revenue']:,.2f}\n"
            f"Net Profit: Rs.{report_data['net_profit']:,.2f}\n"
            f"See attached Excel for full details."
        )

        # ── Build HTML email ───────────────────────────────────────────────────────
        td = 'style="padding:7px 10px;border:1px solid #e5e7eb;"'
        tdh = 'style="padding:7px 10px;border:1px solid #e5e7eb;background:#f1f5f9;font-weight:600;"'
        tds = 'style="padding:7px 10px;border:1px solid #e5e7eb;text-align:right;"'

        def _tbl_header(cols):
            return "<tr>" + "".join(f"<th {tdh}>{c}</th>" for c in cols) + "</tr>"

        def _tbl_row(vals):
            return "<tr>" + "".join(f"<td {td}>{v}</td>" for v in vals) + "</tr>"

        # Summary block
        summary_html = f"""
        <table style="border-collapse:collapse;width:100%;max-width:560px;">
            {_tbl_header(['Metric','Value'])}
            {_tbl_row(['Orders', report_data['total_orders']])}
            {_tbl_row(['Items Sold', report_data['total_items']])}
            {_tbl_row(['Gross Revenue', f"&#8377;{report_data['gross_revenue']:,.2f}"])}
            {_tbl_row(['Returns', f"&#8377;{report_data['returns_total']:,.2f}"])}
            {_tbl_row(['Net Revenue', f"&#8377;{report_data['net_revenue']:,.2f}"])}
            {_tbl_row(['Net Profit', f"&#8377;{report_data['net_profit']:,.2f}"])}
            {_tbl_row(['Stock Entries', len(report_data['stock_rows'])])}
        </table>"""

        # Sales one-by-one block
        sales_html_rows = ""
        for s in report_data["sales_rows"]:
            sales_html_rows += _tbl_row([
                s.get('Sale #',''), s.get('Date',''), s.get('Customer',''),
                s.get('Entered By',''), s.get('Payment',''), s.get('Items (count)',0),
                f"&#8377;{float(s.get('Discount',0) or 0):,.2f}",
                f"&#8377;{float(s.get('Total',0) or 0):,.2f}",
            ])
        sales_html = f"""
        <table style="border-collapse:collapse;width:100%;">
            {_tbl_header(['#','Date','Customer','Staff','Payment','Items','Discount','Total'])}
            {sales_html_rows if sales_html_rows else _tbl_row(['—','No sales','','','','','',''])}
        </table>"""

        # Itemised sales block
        si_html_rows = ""
        rupee = "\u20b9"
        for row in report_data["sales_items_rows"]:
            up_key = f'Unit Price ({rupee})'
            lt_key = f'Line Total ({rupee})'
            si_html_rows += _tbl_row([
                row.get('Sale #',''), row.get('Date',''), row.get('Customer',''),
                row.get('Item',''), row.get('Qty',0),
                f"&#8377;{float(row.get(up_key, 0) or 0):,.2f}",
                f"&#8377;{float(row.get(lt_key, 0) or 0):,.2f}",
            ])
        si_html = f"""
        <table style="border-collapse:collapse;width:100%;">
            {_tbl_header(['Sale#','Date','Customer','Item','Qty','Unit Price','Line Total'])}
            {si_html_rows if si_html_rows else _tbl_row(['—','No items','','','','',''])}
        </table>"""

        # Returns block
        returns_html_rows = ""
        rupee = "\u20b9"
        for r in report_data["returns_items_rows"]:
            lr_key = f'Line Refund ({rupee})'
            returns_html_rows += _tbl_row([
                r.get('Return Date',''), r.get('Customer',''), r.get('Item',''),
                r.get('Qty',0), f"&#8377;{float(r.get(lr_key, 0) or 0):,.2f}",
                r.get('Reason',''), r.get('Staff',''),
            ])
        returns_html = f"""
        <table style="border-collapse:collapse;width:100%;">
            {_tbl_header(['Date','Customer','Item','Qty','Refund','Reason','Staff'])}
            {returns_html_rows if returns_html_rows else _tbl_row(['—','No returns for this period','','','','',''])}
        </table>"""

        # Stock entries block
        stock_html_rows = ""
        rupee = "\u20b9"
        for se in report_data["stock_rows"]:
            cp_key = f'Cost Price ({rupee})'
            sp_key = f'Selling Price ({rupee})'
            stock_html_rows += _tbl_row([
                se.get('Date',''), se.get('Item',''), se.get('Boxes',0),
                se.get('Qty per Box',0), se.get('Qty Added',0),
                se.get('Old Stock',0), se.get('New Stock',0),
                f"&#8377;{float(se.get(cp_key, 0) or 0):,.2f}",
                f"&#8377;{float(se.get(sp_key, 0) or 0):,.2f}",
                se.get('Staff',''), se.get('Notes',''),
            ])
        stock_html = f"""
        <table style="border-collapse:collapse;width:100%;">
            {_tbl_header(['Date','Item','Boxes','Qty/Box','Added','Old Stock','New Stock','CP','SP','Staff','Notes'])}
            {stock_html_rows if stock_html_rows else _tbl_row(['—','No stock entries','','','','','','','','',''])}
        </table>"""

        section_style = "font-family:Arial,sans-serif;font-size:16px;font-weight:700;color:#1e293b;margin:28px 0 8px 0;border-left:4px solid #4f46e5;padding-left:10px;"

        html = f"""
        <html>
        <body style="font-family:Arial,sans-serif;color:#1f2937;max-width:900px;margin:0 auto;padding:20px;">
            <h1 style="color:#4f46e5;margin-bottom:4px;">{store_name}</h1>
            <h2 style="margin-top:0;color:#374151;">Daily Sales Report</h2>
            <p style="color:#6b7280;">Period: <b>{report_data['start_str']}</b> to <b>{report_data['end_str']}</b> &nbsp;|&nbsp; Generated: {get_ist_time().strftime('%d-%b-%Y %I:%M %p')} IST</p>
            <hr style="border:1px solid #e5e7eb;margin:16px 0;">

            <p {section_style}>&#128202; Summary</p>
            {summary_html}

            <p {section_style}>&#128722; Sales (One per Row)</p>
            {sales_html}

            <p {section_style}>&#128220; Sales — Itemised Breakdown</p>
            {si_html}

            <p {section_style}>&#128260; Returns</p>
            {returns_html}

            <p {section_style}>&#128230; Stock Received</p>
            {stock_html}

            <hr style="border:1px solid #e5e7eb;margin:28px 0 10px 0;">
            <p style="font-size:12px;color:#94a3b8;">Full details are in the attached Excel file (6 sheets). Automated by poSTORE.</p>
        </body>
        </html>
        """
        msg.add_alternative(html, subtype="html")
        msg.add_attachment(
            report_data["excel_bytes"],
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=f"sales_report_{report_data['start_str']}_to_{report_data['end_str']}.xlsx"
        )

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(sender_email, sender_password)
            smtp.send_message(msg)

        return report_data

    dispatch_doc_ref = db.collection("settings").document("dispatch_center")
    dispatch_settings = dispatch_doc_ref.get().to_dict() or {}

    auto_enabled = bool(dispatch_settings.get("auto_enabled", False))
    auto_period = dispatch_settings.get("auto_period", "Yesterday")
    auto_hour = int(dispatch_settings.get("auto_hour", 21))
    last_auto_sent_on = dispatch_settings.get("last_auto_sent_on", "Never")
    last_status = dispatch_settings.get("last_status", "Not sent yet")

    # Auto-send once daily (when this page loads and app is running)
    auto_send_attempted_this_session = st.session_state.get("_dispatch_auto_attempted", False)
    if auto_enabled and not auto_send_attempted_this_session:
        st.session_state["_dispatch_auto_attempted"] = True
        now_ist = get_ist_time()
        today_str = now_ist.strftime("%Y-%m-%d")
        already_sent_today = dispatch_settings.get("last_auto_sent_on") == today_str
        attempted_today = dispatch_settings.get("last_auto_attempt_on") == today_str

        if (not already_sent_today) and (not attempted_today) and now_ist.hour >= auto_hour:
            with st.spinner("Checking auto-send..."):
                try:
                    _send_report_email(dispatch_settings, auto_period)
                    dispatch_doc_ref.set({
                        "last_auto_sent_on": today_str,
                        "last_auto_attempt_on": today_str,
                        "last_auto_sent_at": now_ist,
                        "last_status": f"Auto sent successfully at {now_ist.strftime('%I:%M %p')} IST",
                    }, merge=True)
                    st.toast("Daily report auto-sent successfully!")
                except Exception as auto_err:
                    error_msg = str(auto_err)[:100]
                    dispatch_doc_ref.set({
                        "last_auto_attempt_on": today_str,
                        "last_status": f"Auto send failed: {error_msg}",
                    }, merge=True)
                    st.toast(f"Auto-send failed: {error_msg}", icon="warning")

    c1, c2 = st.columns([2, 1])

    with c1:
        with st.form("dispatch_center_setup", enter_to_submit=False):
            st.markdown("#### One-time Setup")
            sender_email = st.text_input("Sender Email (Gmail)", value=dispatch_settings.get("sender_email", ""))
            sender_password_new = st.text_input("App Password", type="password", value="", help="Leave blank to keep existing saved password")
            recipient_emails = st.text_input("Recipient Email(s)", value=dispatch_settings.get("recipient_emails", ""), help="Comma separated if multiple")

            st.markdown("#### Daily Auto Dispatch")
            auto_enabled_input = st.checkbox("Enable Auto Daily Send", value=auto_enabled)
            auto_period_input = st.selectbox("Auto Report Period", ["Yesterday", "Today", "Last 7 Days"], index=["Yesterday", "Today", "Last 7 Days"].index(auto_period if auto_period in ["Yesterday", "Today", "Last 7 Days"] else "Yesterday"))
            auto_hour_input = st.number_input("Send After Hour (IST)", min_value=0, max_value=23, value=auto_hour, step=1)

            if st.form_submit_button("💾 Save Dispatch Settings", type="primary", use_container_width=True):
                if not sender_email.strip():
                    st.error("Sender email is required.")
                elif "@gmail.com" not in sender_email.lower() and "@googlemail.com" not in sender_email.lower():
                    st.error("Currently supports Gmail only. Use a @gmail.com or @googlemail.com address.")
                elif not recipient_emails.strip():
                    st.error("Recipient email(s) are required.")
                else:
                    # Validate recipient emails
                    recipients_list = [e.strip() for e in recipient_emails.split(",")]
                    valid_emails = all("@" in e for e in recipients_list)
                    if not valid_emails:
                        st.error("Invalid email format in recipients. Check for commas and @ symbols.")
                    else:
                        try:
                            payload = {
                                "sender_email": sender_email.strip(),
                                "recipient_emails": recipient_emails.strip(),
                                "auto_enabled": auto_enabled_input,
                                "auto_period": auto_period_input,
                                "auto_hour": int(auto_hour_input),
                                "updated_at": get_ist_time(),
                            }
                            if sender_password_new.strip():
                                payload["sender_password"] = sender_password_new.strip()

                            dispatch_doc_ref.set(payload, merge=True)
                            st.toast("Settings saved successfully!")
                            st.rerun()
                        except Exception as save_err:
                            st.error(f"Failed to save: {save_err}")

        st.markdown("---")
        st.markdown("#### Quick Actions")
        quick_period = st.selectbox("One-click Report Period", ["Today", "Yesterday", "Last 7 Days"], index=1)
        q1, q2 = st.columns(2)

        with q1:
            if st.button("📧 Send Now", type="primary", use_container_width=True):
                try:
                    latest_cfg = dispatch_doc_ref.get().to_dict() or {}
                    if not latest_cfg.get("sender_email"):
                        st.error("Email settings not configured. Save settings first.")
                    else:
                        with st.spinner("Sending report..."):
                            _send_report_email(latest_cfg, quick_period)
                        dispatch_doc_ref.set({
                            "last_status": f"Manual send success at {get_ist_time().strftime('%d-%b %I:%M %p')} IST",
                            "last_manual_sent_at": get_ist_time(),
                        }, merge=True)
                        st.toast("Report sent successfully!")
                except Exception as manual_err:
                    st.error(f"Send failed: {str(manual_err)[:80]}")

        with q2:
            if st.button("🧪 Test Sender", use_container_width=True):
                try:
                    latest_cfg = dispatch_doc_ref.get().to_dict() or {}
                    if not latest_cfg.get("sender_email"):
                        st.error("Email settings not configured first.")
                    elif not latest_cfg.get("sender_password"):
                        st.error("App password not saved. Save settings first.")
                    else:
                        with st.spinner("Testing email..."):
                            from email.message import EmailMessage
                            test_msg = EmailMessage()
                            test_msg["Subject"] = "poSTORE Email Test"
                            test_msg["From"] = latest_cfg.get("sender_email")
                            test_msg["To"] = latest_cfg.get("sender_email")
                            test_msg.set_content("This is a test email from poSTORE. If you see this, SMTP is working correctly.")
                            
                            with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as smtp:
                                smtp.starttls()
                                smtp.login(latest_cfg.get("sender_email"), latest_cfg.get("sender_password"))
                                smtp.send_message(test_msg)
                        st.toast("Test email sent to yourself!")
                except Exception as test_err:
                    st.error(f"Test failed: {str(test_err)[:80]}")

    with c2:
        st.markdown("#### 📊 Dispatch Status")
        
        # Auto-send indicator
        if auto_enabled:
            st.success(f"✅ Auto-send: Active at {auto_hour}:00 IST daily")
        else:
            st.warning("⏸️ Auto-send: Disabled")
        
        # Last send information
        latest_dispatch = dispatch_doc_ref.get().to_dict() or {}
        last_auto = latest_dispatch.get("last_auto_sent_at")
        last_manual = latest_dispatch.get("last_manual_sent_at")
        
        if last_auto:
            auto_time = last_auto.strftime('%d-%b %I:%M %p') if hasattr(last_auto, 'strftime') else str(last_auto)
            st.caption(f"Last auto-send: {auto_time} IST")
        
        if last_manual:
            manual_time = last_manual.strftime('%d-%b %I:%M %p') if hasattr(last_manual, 'strftime') else str(last_manual)
            st.caption(f"Last manual send: {manual_time} IST")
        
        st.divider()
        
        st.markdown("""
            <div style='background: #f8fafc; padding: 18px; border-radius: 12px; border: 1px solid #e2e8f0; margin-top:10px;'>
                <b>🆘 Gmail Setup Guide</b>
                <ol style='font-size: 13px; color: #475569; padding-left: 20px;'>
                    <li>Enable 2-Step Verification on Gmail account</li>
                    <li>Generate App Password (16 character) for Mail</li>
                    <li>Paste sender email + app password in settings</li>
                    <li>Enable 'Auto Daily Send' and save</li>
                </ol>
                <p style='font-size:12px;color:#64748b;'>🎯 Auto-send runs when this page opens after configured hour. App must be running.</p>
            </div>
        """, unsafe_allow_html=True)
