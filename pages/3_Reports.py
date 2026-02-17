import streamlit as st
from firebase_config import db
import pandas as pd
from datetime import datetime, timedelta
import io
from utils import inject_custom_css, render_sidebar

inject_custom_css()
render_sidebar()
st.title("📊 Sales Reports & Analytics")

# Create tabs for different report types
tab1, tab2, tab3 = st.tabs(["📅 Date Range Reports", "🏆 Top Sellers", "👥 Customer Reports"])

# ==================== TAB 1: DATE RANGE REPORTS ====================
with tab1:
    st.subheader("📅 Sales by Date Range")
    
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", value=datetime.now() - timedelta(days=7))
    with col2:
        end_date = st.date_input("End Date", value=datetime.now())
    
    # Search/Filter options
    st.write("**Filters:**")
    col_filter1, col_filter2 = st.columns(2)
    with col_filter1:
        customer_search = st.text_input("🔍 Search by Customer Name", placeholder="Type customer name...")
    with col_filter2:
        min_amount = st.number_input("Minimum Amount (₹)", min_value=0.0, value=0.0, step=100.0)
    
    if st.button("📊 Generate Report", type="primary"):
        try:
            # Fetch sales in date range
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
                    customer_name = data.get("customer_name", "N/A")
                    total = data.get("total", 0)
                    
                    # Apply filters
                    if customer_search and customer_search.lower() not in customer_name.lower():
                        continue
                    if total < min_amount:
                        continue
                    
                    # Get items details
                    items = data.get("items", [])
                    items_str = ", ".join([f"{item.get('name', 'Unknown')} x{item.get('qty', 0)}" for item in items])
                    
                    sales_data.append({
                        "Date": sale_date_str,
                        "Customer": customer_name,
                        "Phone": data.get("customer_phone", "N/A"),
                        "Items": items_str,
                        "Quantity": sum(item.get("qty", 0) for item in items),
                        "Total": total,
                        "Time": data.get("timestamp", datetime.now()).strftime("%I:%M %p") if isinstance(data.get("timestamp"), datetime) else "N/A"
                    })
            
            if sales_data:
                df = pd.DataFrame(sales_data)
                
                # Display summary metrics
                st.markdown("### 📈 Summary")
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total Sales", len(df))
                with col2:
                    st.metric("Total Revenue", f"₹{df['Total'].sum():,.0f}")
                with col3:
                    st.metric("Avg Order Value", f"₹{df['Total'].mean():,.0f}")
                with col4:
                    st.metric("Total Items Sold", int(df['Quantity'].sum()))
                
                st.markdown("---")
                
                # Display data table
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                # Export to Excel
                st.markdown("### 📥 Export Data")
                
                # Create Excel file in memory
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Sales Report')
                output.seek(0)
                
                st.download_button(
                    label="📥 Download Excel Report",
                    data=output,
                    file_name=f"sales_report_{start_date}_to_{end_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
                
                # Daily revenue chart
                st.markdown("### 📊 Daily Revenue Trend")
                daily_revenue = df.groupby("Date")["Total"].sum().reset_index()
                st.line_chart(daily_revenue.set_index("Date"))
                
            else:
                st.warning(f"No sales found between {start_date} and {end_date} with the selected filters")
        
        except Exception as e:
            st.error(f"Error generating report: {e}")
            import traceback
            st.code(traceback.format_exc())

# ==================== TAB 2: TOP SELLERS ====================
with tab2:
    st.subheader("🏆 Best Selling Products")
    
    # Date range for top sellers
    col1, col2 = st.columns(2)
    with col1:
        top_start_date = st.date_input("From Date", value=datetime.now() - timedelta(days=30), key="top_start")
    with col2:
        top_end_date = st.date_input("To Date", value=datetime.now(), key="top_end")
    
    if st.button("🔍 Analyze Top Sellers", type="primary"):
        try:
            all_sales = db.collection("sales").stream()
            item_stats = {}
            
            for sale in all_sales:
                data = sale.to_dict()
                sale_date_str = data.get("date", "")
                
                try:
                    sale_date = datetime.strptime(sale_date_str, "%Y-%m-%d").date()
                except:
                    continue
                
                if top_start_date <= sale_date <= top_end_date:
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
    
    # Date range for customers
    col1, col2 = st.columns(2)
    with col1:
        cust_start_date = st.date_input("From Date", value=datetime.now() - timedelta(days=30), key="cust_start")
    with col2:
        cust_end_date = st.date_input("To Date", value=datetime.now(), key="cust_end")
    
    if st.button("👥 Analyze Customers", type="primary"):
        try:
            all_sales = db.collection("sales").stream()
            customer_stats = {}
            
            for sale in all_sales:
                data = sale.to_dict()
                sale_date_str = data.get("date", "")
                
                try:
                    sale_date = datetime.strptime(sale_date_str, "%Y-%m-%d").date()
                except:
                    continue
                
                if cust_start_date <= sale_date <= cust_end_date:
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
