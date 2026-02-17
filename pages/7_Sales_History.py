import streamlit as st
from firebase_config import db
from datetime import datetime, timedelta
import pandas as pd
from utils import inject_custom_css, render_sidebar

st.set_page_config(page_title="Sales History", layout="wide", page_icon="📜")
inject_custom_css()
render_sidebar()

st.title("📜 Sales History")

# Date selection options
st.subheader("📅 Select Date Range")

col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    view_mode = st.selectbox(
        "View Mode",
        ["Today", "Yesterday", "Last 7 Days", "Last 30 Days", "Custom Range"],
        index=0  # Default to "Today"
    )

# Set dates based on view mode
if view_mode == "Today":
    start_date = datetime.now().date()
    end_date = datetime.now().date()
    st.info(f"📅 Showing sales for: **{start_date.strftime('%d-%m-%Y')}** (Today)")
elif view_mode == "Yesterday":
    start_date = (datetime.now() - timedelta(days=1)).date()
    end_date = (datetime.now() - timedelta(days=1)).date()
    st.info(f"📅 Showing sales for: **{start_date.strftime('%d-%m-%Y')}** (Yesterday)")
elif view_mode == "Last 7 Days":
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=7)
    st.info(f"📅 Showing sales from: **{start_date.strftime('%d-%m-%Y')}** to **{end_date.strftime('%d-%m-%Y')}**")
elif view_mode == "Last 30 Days":
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)
    st.info(f"📅 Showing sales from: **{start_date.strftime('%d-%m-%Y')}** to **{end_date.strftime('%d-%m-%Y')}**")
else:  # Custom Range
    col_date1, col_date2 = st.columns(2)
    with col_date1:
        start_date = st.date_input("Start Date", value=datetime.now().date())
    with col_date2:
        end_date = st.date_input("End Date", value=datetime.now().date())

st.markdown("---")

# Fetch and display sales
try:
    with st.spinner("Loading sales..."):
        # Fetch all sales
        all_sales = db.collection("sales").stream()
        sales_data = []
        
        for sale in all_sales:
            data = sale.to_dict()
            sale_date_str = data.get("date", "")
            
            # Parse date
            try:
                sale_date = datetime.strptime(sale_date_str, "%Y-%m-%d").date()
            except:
                continue
            
            # Filter by date range
            if start_date <= sale_date <= end_date:
                # Get items details
                items = data.get("items", [])
                items_str = ", ".join([f"{item.get('name', 'Unknown')} x{item.get('qty', 0)}" for item in items])
                
                # Get discount info
                discount_amount = data.get("discount_amount", 0)
                subtotal = data.get("subtotal", data.get("total", 0))
                
                sales_data.append({
                    "id": sale.id,
                    "Date": sale_date_str,
                    "Time": data.get("timestamp", datetime.now()).strftime("%I:%M %p") if isinstance(data.get("timestamp"), datetime) else "N/A",
                    "Customer": data.get("customer_name", "N/A"),
                    "Phone": data.get("customer_phone", "N/A"),
                    "Items": items_str,
                    "Item Count": len(items),
                    "Subtotal": subtotal,
                    "Discount": discount_amount,
                    "Total": data.get("total", 0),
                    "raw_items": items,
                    "raw_timestamp": data.get("timestamp", datetime.now())
                })
        
        if sales_data:
            # Sort by date and time (newest first)
            sales_data.sort(key=lambda x: x["raw_timestamp"], reverse=True)
            
            # Display summary metrics
            st.subheader("📊 Summary")
            col1, col2, col3, col4 = st.columns(4)
            
            total_sales = len(sales_data)
            total_revenue = sum(s["Total"] for s in sales_data)
            total_discount = sum(s["Discount"] for s in sales_data)
            avg_order = total_revenue / total_sales if total_sales > 0 else 0
            
            with col1:
                st.metric("Total Sales", total_sales)
            with col2:
                st.metric("Total Revenue", f"₹{total_revenue:,.2f}")
            with col3:
                st.metric("Total Discount", f"₹{total_discount:,.2f}")
            with col4:
                st.metric("Avg Order Value", f"₹{avg_order:,.2f}")
            
            st.markdown("---")
            
            # Display sales in expandable cards
            st.subheader(f"📋 Sales List ({total_sales} sales)")
            
            # Search filter
            search_customer = st.text_input("🔍 Search by Customer Name", placeholder="Type to filter...")
            
            # Filter by search
            filtered_sales = sales_data
            if search_customer:
                filtered_sales = [s for s in sales_data if search_customer.lower() in s["Customer"].lower()]
            
            if not filtered_sales:
                st.warning(f"No sales found matching '{search_customer}'")
            else:
                st.write(f"**Showing {len(filtered_sales)} of {total_sales} sales**")
                
                # Display each sale in an expandable card
                for idx, sale in enumerate(filtered_sales):
                    # Card header
                    with st.expander(
                        f"🧾 Sale #{total_sales - idx} - {sale['Customer']} - ₹{sale['Total']:,.2f} - {sale['Date']} {sale['Time']}",
                        expanded=(idx == 0 and len(filtered_sales) <= 5)  # Expand first if 5 or fewer
                    ):
                        # Sale details in columns
                        col_info1, col_info2 = st.columns(2)
                        
                        with col_info1:
                            st.write("**Customer Information:**")
                            st.write(f"👤 Name: {sale['Customer']}")
                            st.write(f"📞 Phone: {sale['Phone']}")
                            st.write(f"📅 Date: {sale['Date']}")
                            st.write(f"🕐 Time: {sale['Time']}")
                        
                        with col_info2:
                            st.write("**Payment Details:**")
                            st.write(f"Subtotal: ₹{sale['Subtotal']:,.2f}")
                            if sale['Discount'] > 0:
                                st.write(f"Discount: -₹{sale['Discount']:,.2f}")
                            st.write(f"**Total: ₹{sale['Total']:,.2f}**")
                        
                        st.markdown("---")
                        
                        # Items table
                        st.write("**📦 Items Purchased:**")
                        items_table_data = []
                        for item in sale['raw_items']:
                            items_table_data.append({
                                "Item": item.get('name', 'Unknown'),
                                "Quantity": item.get('qty', 0),
                                "Price": f"₹{item.get('price', 0):,.2f}",
                                "Amount": f"₹{item.get('qty', 0) * item.get('price', 0):,.2f}"
                            })
                        
                        if items_table_data:
                            df_items = pd.DataFrame(items_table_data)
                            st.dataframe(df_items, use_container_width=True, hide_index=True)
                        
                        # Action buttons
                        st.markdown("---")
                        col_btn1, col_btn2, col_btn3 = st.columns(3)
                        
                        with col_btn1:
                            if st.button(f"🔄 Process Return", key=f"return_{sale['id']}"):
                                st.session_state["selected_sale_for_return"] = sale
                                st.switch_page("pages/5_Returns.py")
                        
                        with col_btn2:
                            # WhatsApp share
                            from utils import build_whatsapp_message
                            wa_msg = build_whatsapp_message(
                                sale['raw_items'],
                                sale['Subtotal'],
                                sale['Discount'],
                                "Discount" if sale['Discount'] > 0 else "No Discount",
                                sale['Total'],
                                sale['Customer']
                            )
                            if sale['Phone'] and sale['Phone'] != "N/A" and len(sale['Phone'].strip()) == 10:
                                wa_link = f"https://wa.me/91{sale['Phone'].strip()}?text={wa_msg}"
                            else:
                                wa_link = f"https://wa.me/?text={wa_msg}"
                            
                            st.markdown(f"[📲 Send WhatsApp]({wa_link})")
                        
                        with col_btn3:
                            st.caption(f"Sale ID: {sale['id'][:8]}...")
            
            st.markdown("---")
            
            # Export option
            st.subheader("📥 Export Data")
            
            # Prepare export data
            export_data = []
            for sale in filtered_sales:
                export_data.append({
                    "Date": sale["Date"],
                    "Time": sale["Time"],
                    "Customer": sale["Customer"],
                    "Phone": sale["Phone"],
                    "Items": sale["Items"],
                    "Item Count": sale["Item Count"],
                    "Subtotal": sale["Subtotal"],
                    "Discount": sale["Discount"],
                    "Total": sale["Total"]
                })
            
            df_export = pd.DataFrame(export_data)
            
            # Excel export
            import io
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False, sheet_name='Sales History')
            output.seek(0)
            
            st.download_button(
                label="📥 Download Excel Report",
                data=output,
                file_name=f"sales_history_{start_date}_to_{end_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        
        else:
            st.info(f"📭 No sales found for the selected period ({start_date} to {end_date})")
            st.write("**Tips:**")
            st.write("- Try selecting a different date range")
            st.write("- Check if any sales were made during this period")
            st.write("- Go to Sales page to create your first sale")

except Exception as e:
    st.error(f"❌ Error loading sales history: {e}")
    import traceback
    st.code(traceback.format_exc())

# Quick stats by date (if multiple days)
if sales_data and (end_date - start_date).days > 0:
    st.markdown("---")
    st.subheader("📈 Daily Breakdown")
    
    # Group by date
    daily_stats = {}
    for sale in sales_data:
        date = sale["Date"]
        if date not in daily_stats:
            daily_stats[date] = {"count": 0, "revenue": 0}
        daily_stats[date]["count"] += 1
        daily_stats[date]["revenue"] += sale["Total"]
    
    # Create chart data
    chart_data = []
    for date, stats in sorted(daily_stats.items()):
        chart_data.append({
            "Date": date,
            "Sales": stats["count"],
            "Revenue": stats["revenue"]
        })
    
    df_chart = pd.DataFrame(chart_data)
    
    # Display chart
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.write("**Sales Count by Date**")
        st.bar_chart(df_chart.set_index("Date")["Sales"])
    
    with col_chart2:
        st.write("**Revenue by Date**")
        st.bar_chart(df_chart.set_index("Date")["Revenue"])
