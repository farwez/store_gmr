import streamlit as st
from firebase_config import db
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils import inject_custom_css, render_sidebar, get_all_items

st.set_page_config(page_title="AI Insights", page_icon="🧠", layout="wide")
inject_custom_css()
render_sidebar()

st.title("🧠 AI Insights & Analytics")

# Date range selector
st.sidebar.subheader("📅 Analysis Period")
analysis_period = st.sidebar.selectbox(
    "Select Period",
    ["Last 7 Days", "Last 30 Days", "Last 90 Days", "All Time"],
    index=1
)

# Calculate date range
if analysis_period == "Last 7 Days":
    start_date = (datetime.now() - timedelta(days=7)).date()
elif analysis_period == "Last 30 Days":
    start_date = (datetime.now() - timedelta(days=30)).date()
elif analysis_period == "Last 90 Days":
    start_date = (datetime.now() - timedelta(days=90)).date()
else:
    start_date = None

end_date = datetime.now().date()

# Cached data fetching function
@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_sales_data(start_date_str, end_date_str):
    """Fetch and process sales data with caching"""
    all_sales = db.collection("sales").stream()
    sales_data = []
    items_data = []
    customer_data = {}
    
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else None
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    
    for sale in all_sales:
        try:
            data = sale.to_dict()
            sale_date_str = data.get("date", "")
            
            # Parse date
            try:
                sale_date = datetime.strptime(sale_date_str, "%Y-%m-%d").date()
            except:
                continue
            
            # Filter by date range
            if start_date is None or sale_date >= start_date:
                sales_data.append({
                    "date": sale_date_str,
                    "total": data.get("total", 0),
                    "discount": data.get("discount_amount", 0),
                    "customer": data.get("customer_name", "Walk-in"),
                    "items_count": len(data.get("items", [])),
                    "timestamp": data.get("timestamp", datetime.now())
                })
                
                # Collect items
                for item in data.get("items", []):
                    items_data.append({
                        "name": item.get("name", "Unknown"),
                        "qty": item.get("qty", 0),
                        "price": item.get("price", 0),
                        "revenue": item.get("qty", 0) * item.get("price", 0),
                        "date": sale_date_str
                    })
                
                # Collect customer data
                customer = data.get("customer_name", "Walk-in")
                if customer not in customer_data:
                    customer_data[customer] = {"orders": 0, "revenue": 0}
                customer_data[customer]["orders"] += 1
                customer_data[customer]["revenue"] += data.get("total", 0)
        
        except Exception as e:
            continue
    
    return sales_data, items_data, customer_data

# Fetch sales data
try:
    with st.spinner("Analyzing your sales data..."):
        # Use cached function
        start_date_str = str(start_date) if start_date else None
        sales_data, items_data, customer_data = fetch_sales_data(start_date_str, str(end_date))
        
        if not sales_data:
            st.info("📭 No sales data available for the selected period")
            st.stop()
        
        # Convert to DataFrames
        df_sales = pd.DataFrame(sales_data)
        df_items = pd.DataFrame(items_data)
        
        # ==================== OVERVIEW METRICS ====================
        st.header("📊 Business Overview")
        
        col1, col2, col3, col4 = st.columns(4)
        
        total_revenue = df_sales["total"].sum()
        total_orders = len(df_sales)
        total_discount = df_sales["discount"].sum()
        avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
        
        with col1:
            st.metric("💰 Total Revenue", f"₹{total_revenue:,.0f}")
        with col2:
            st.metric("🛒 Total Orders", f"{total_orders:,}")
        with col3:
            st.metric("📦 Items Sold", f"{df_items['qty'].sum():,}")
        with col4:
            st.metric("💵 Avg Order Value", f"₹{avg_order_value:,.0f}")
        
        st.markdown("---")
        
        # ==================== TABS FOR DIFFERENT INSIGHTS ====================
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📈 Trends", 
            "🔥 Best Sellers", 
            "👥 Customers", 
            "💡 Recommendations",
            "🎯 Performance"
        ])
        
        # ==================== TAB 1: TRENDS ====================
        with tab1:
            st.subheader("📈 Sales Trends")
            
            # Daily revenue trend
            daily_revenue = df_sales.groupby("date")["total"].sum().reset_index()
            daily_revenue.columns = ["Date", "Revenue"]
            
            fig_revenue = px.line(
                daily_revenue, 
                x="Date", 
                y="Revenue",
                title="Daily Revenue Trend",
                markers=True
            )
            fig_revenue.update_layout(
                xaxis_title="Date",
                yaxis_title="Revenue (₹)",
                hovermode='x unified',
                height=400,
                margin=dict(l=20, r=20, t=40, b=20)
            )
            fig_revenue.update_traces(line_color='#1f77b4', line_width=2)
            st.plotly_chart(fig_revenue, use_container_width=True, config={'displayModeBar': False})
            
            # Daily orders trend
            daily_orders = df_sales.groupby("date").size().reset_index()
            daily_orders.columns = ["Date", "Orders"]
            
            fig_orders = px.bar(
                daily_orders,
                x="Date",
                y="Orders",
                title="Daily Orders Count",
                color="Orders",
                color_continuous_scale="Blues"
            )
            fig_orders.update_layout(
                xaxis_title="Date",
                yaxis_title="Number of Orders",
                height=400,
                margin=dict(l=20, r=20, t=40, b=20),
                showlegend=False
            )
            st.plotly_chart(fig_orders, use_container_width=True, config={'displayModeBar': False})
            
            # Average order value trend
            daily_aov = df_sales.groupby("date")["total"].mean().reset_index()
            daily_aov.columns = ["Date", "AOV"]
            
            fig_aov = px.area(
                daily_aov,
                x="Date",
                y="AOV",
                title="Average Order Value Trend",
                color_discrete_sequence=["#00CC96"]
            )
            fig_aov.update_layout(
                xaxis_title="Date",
                yaxis_title="Average Order Value (₹)",
                height=400,
                margin=dict(l=20, r=20, t=40, b=20)
            )
            st.plotly_chart(fig_aov, use_container_width=True, config={'displayModeBar': False})
        
        # ==================== TAB 2: BEST SELLERS ====================
        with tab2:
            st.subheader("🔥 Best Selling Products")
            
            col_metric1, col_metric2 = st.columns(2)
            
            # Top products by quantity
            top_by_qty = df_items.groupby("name")["qty"].sum().sort_values(ascending=False).head(10)
            
            with col_metric1:
                st.write("**Top 10 by Quantity Sold**")
                fig_qty = px.bar(
                    x=top_by_qty.values,
                    y=top_by_qty.index,
                    orientation='h',
                    labels={'x': 'Quantity Sold', 'y': 'Product'},
                    color=top_by_qty.values,
                    color_continuous_scale="Reds"
                )
                fig_qty.update_layout(showlegend=False, height=400)
                st.plotly_chart(fig_qty, use_container_width=True)
            
            # Top products by revenue
            top_by_revenue = df_items.groupby("name")["revenue"].sum().sort_values(ascending=False).head(10)
            
            with col_metric2:
                st.write("**Top 10 by Revenue Generated**")
                fig_rev = px.bar(
                    x=top_by_revenue.values,
                    y=top_by_revenue.index,
                    orientation='h',
                    labels={'x': 'Revenue (₹)', 'y': 'Product'},
                    color=top_by_revenue.values,
                    color_continuous_scale="Greens"
                )
                fig_rev.update_layout(showlegend=False, height=400)
                st.plotly_chart(fig_rev, use_container_width=True)
            
            # Product performance table
            st.markdown("---")
            st.write("**📋 Complete Product Performance**")
            
            product_stats = df_items.groupby("name").agg({
                "qty": "sum",
                "revenue": "sum",
                "price": "mean"
            }).reset_index()
            product_stats.columns = ["Product", "Qty Sold", "Revenue", "Avg Price"]
            product_stats = product_stats.sort_values("Revenue", ascending=False)
            product_stats["Revenue"] = product_stats["Revenue"].apply(lambda x: f"₹{x:,.2f}")
            product_stats["Avg Price"] = product_stats["Avg Price"].apply(lambda x: f"₹{x:,.2f}")
            
            st.dataframe(product_stats, use_container_width=True, hide_index=True)
        
        # ==================== TAB 3: CUSTOMERS ====================
        with tab3:
            st.subheader("👥 Customer Analysis")
            
            # Top customers
            top_customers = sorted(customer_data.items(), key=lambda x: x[1]["revenue"], reverse=True)[:10]
            
            if top_customers:
                customer_names = [c[0] for c in top_customers]
                customer_revenue = [c[1]["revenue"] for c in top_customers]
                customer_orders = [c[1]["orders"] for c in top_customers]
                
                # Revenue by customer
                fig_cust_rev = px.bar(
                    x=customer_revenue,
                    y=customer_names,
                    orientation='h',
                    title="Top 10 Customers by Revenue",
                    labels={'x': 'Revenue (₹)', 'y': 'Customer'},
                    color=customer_revenue,
                    color_continuous_scale="Purples"
                )
                fig_cust_rev.update_layout(showlegend=False)
                st.plotly_chart(fig_cust_rev, use_container_width=True)
                
                # Customer metrics
                col_cust1, col_cust2, col_cust3 = st.columns(3)
                
                with col_cust1:
                    st.metric("Total Customers", len(customer_data))
                with col_cust2:
                    avg_customer_value = total_revenue / len(customer_data) if len(customer_data) > 0 else 0
                    st.metric("Avg Customer Value", f"₹{avg_customer_value:,.0f}")
                with col_cust3:
                    repeat_customers = sum(1 for c in customer_data.values() if c["orders"] > 1)
                    st.metric("Repeat Customers", repeat_customers)
                
                # Customer table
                st.markdown("---")
                st.write("**📋 Customer Details**")
                
                customer_table = []
                for name, data in sorted(customer_data.items(), key=lambda x: x[1]["revenue"], reverse=True):
                    customer_table.append({
                        "Customer": name,
                        "Orders": data["orders"],
                        "Revenue": f"₹{data['revenue']:,.2f}",
                        "Avg Order": f"₹{data['revenue'] / data['orders']:,.2f}"
                    })
                
                df_customers = pd.DataFrame(customer_table)
                st.dataframe(df_customers, use_container_width=True, hide_index=True)
        
        # ==================== TAB 4: RECOMMENDATIONS ====================
        with tab4:
            st.subheader("💡 AI-Powered Recommendations")
            
            # Calculate insights
            best_product = df_items.groupby("name")["revenue"].sum().idxmax()
            best_product_revenue = df_items.groupby("name")["revenue"].sum().max()
            
            worst_product = df_items.groupby("name")["revenue"].sum().idxmin()
            worst_product_revenue = df_items.groupby("name")["revenue"].sum().min()
            
            avg_discount_pct = (total_discount / (total_revenue + total_discount) * 100) if (total_revenue + total_discount) > 0 else 0
            
            # Display recommendations
            st.write("### 🎯 Key Insights")
            
            col_rec1, col_rec2 = st.columns(2)
            
            with col_rec1:
                st.success(f"**🏆 Star Product:** {best_product}")
                st.write(f"Generated ₹{best_product_revenue:,.0f} in revenue")
                st.write("💡 **Recommendation:** Stock more of this product and consider bundling it with slower-moving items.")
                
                st.markdown("---")
                
                if avg_discount_pct > 10:
                    st.warning(f"**💸 High Discount Rate:** {avg_discount_pct:.1f}%")
                    st.write("💡 **Recommendation:** Review your discount strategy. High discounts may be impacting profitability.")
                else:
                    st.info(f"**💸 Discount Rate:** {avg_discount_pct:.1f}%")
                    st.write("💡 **Recommendation:** Your discount rate is healthy. Consider strategic discounts to boost sales.")
            
            with col_rec2:
                st.warning(f"**📉 Slow Mover:** {worst_product}")
                st.write(f"Only generated ₹{worst_product_revenue:,.0f} in revenue")
                st.write("💡 **Recommendation:** Consider promotional offers or bundling with popular items to move inventory.")
                
                st.markdown("---")
                
                if avg_order_value < 200:
                    st.info(f"**📊 Average Order Value:** ₹{avg_order_value:.0f}")
                    st.write("💡 **Recommendation:** Implement upselling strategies or minimum order incentives to increase AOV.")
                else:
                    st.success(f"**📊 Average Order Value:** ₹{avg_order_value:.0f}")
                    st.write("💡 **Recommendation:** Great AOV! Maintain quality service and consider loyalty programs.")
            
            # Growth opportunities
            st.markdown("---")
            st.write("### 🚀 Growth Opportunities")
            
            opportunities = []
            
            # Check for repeat customers
            repeat_rate = (repeat_customers / len(customer_data) * 100) if len(customer_data) > 0 else 0
            if repeat_rate < 30:
                opportunities.append({
                    "Area": "Customer Retention",
                    "Current": f"{repeat_rate:.1f}% repeat rate",
                    "Opportunity": "Implement loyalty program to increase repeat purchases",
                    "Impact": "High"
                })
            
            # Check product diversity
            unique_products = df_items["name"].nunique()
            if unique_products < 10:
                opportunities.append({
                    "Area": "Product Range",
                    "Current": f"{unique_products} products",
                    "Opportunity": "Expand product range to attract more customers",
                    "Impact": "Medium"
                })
            
            # Check discount usage
            if avg_discount_pct > 15:
                opportunities.append({
                    "Area": "Pricing Strategy",
                    "Current": f"{avg_discount_pct:.1f}% avg discount",
                    "Opportunity": "Optimize pricing to reduce dependency on discounts",
                    "Impact": "High"
                })
            
            # Check AOV
            if avg_order_value < 300:
                opportunities.append({
                    "Area": "Order Value",
                    "Current": f"₹{avg_order_value:.0f} AOV",
                    "Opportunity": "Implement combo offers and upselling",
                    "Impact": "Medium"
                })
            
            if opportunities:
                df_opportunities = pd.DataFrame(opportunities)
                st.dataframe(df_opportunities, use_container_width=True, hide_index=True)
            else:
                st.success("🎉 Your business is performing well across all metrics!")
        
        # ==================== TAB 5: PERFORMANCE ====================
        with tab5:
            st.subheader("🎯 Performance Metrics")
            
            # Revenue breakdown
            col_perf1, col_perf2 = st.columns(2)
            
            with col_perf1:
                st.write("**💰 Revenue Breakdown**")
                
                # Pie chart of revenue by product
                product_revenue = df_items.groupby("name")["revenue"].sum().sort_values(ascending=False).head(5)
                other_revenue = df_items.groupby("name")["revenue"].sum().sort_values(ascending=False)[5:].sum()
                
                if other_revenue > 0:
                    product_revenue["Others"] = other_revenue
                
                fig_pie = px.pie(
                    values=product_revenue.values,
                    names=product_revenue.index,
                    title="Revenue Distribution (Top 5 Products)"
                )
                st.plotly_chart(fig_pie, use_container_width=True)
            
            with col_perf2:
                st.write("**📊 Sales Distribution**")
                
                # Items per order distribution
                items_per_order = df_sales["items_count"].value_counts().sort_index()
                
                fig_dist = px.bar(
                    x=items_per_order.index,
                    y=items_per_order.values,
                    labels={'x': 'Items per Order', 'y': 'Number of Orders'},
                    title="Items per Order Distribution"
                )
                st.plotly_chart(fig_dist, use_container_width=True)
            
            # Performance score
            st.markdown("---")
            st.write("**🏆 Business Health Score**")
            
            # Calculate score (out of 100)
            score = 0
            
            # Revenue growth (20 points)
            if total_revenue > 10000:
                score += 20
            elif total_revenue > 5000:
                score += 15
            elif total_revenue > 1000:
                score += 10
            else:
                score += 5
            
            # Order volume (20 points)
            if total_orders > 100:
                score += 20
            elif total_orders > 50:
                score += 15
            elif total_orders > 20:
                score += 10
            else:
                score += 5
            
            # Customer retention (20 points)
            if repeat_rate > 50:
                score += 20
            elif repeat_rate > 30:
                score += 15
            elif repeat_rate > 10:
                score += 10
            else:
                score += 5
            
            # AOV (20 points)
            if avg_order_value > 500:
                score += 20
            elif avg_order_value > 300:
                score += 15
            elif avg_order_value > 150:
                score += 10
            else:
                score += 5
            
            # Discount efficiency (20 points)
            if avg_discount_pct < 5:
                score += 20
            elif avg_discount_pct < 10:
                score += 15
            elif avg_discount_pct < 15:
                score += 10
            else:
                score += 5
            
            # Display score
            col_score1, col_score2, col_score3 = st.columns([1, 2, 1])
            
            with col_score2:
                # Gauge chart
                fig_gauge = go.Figure(go.Indicator(
                    mode="gauge+number+delta",
                    value=score,
                    domain={'x': [0, 1], 'y': [0, 1]},
                    title={'text': "Health Score"},
                    delta={'reference': 80},
                    gauge={
                        'axis': {'range': [None, 100]},
                        'bar': {'color': "darkblue"},
                        'steps': [
                            {'range': [0, 40], 'color': "lightgray"},
                            {'range': [40, 70], 'color': "gray"},
                            {'range': [70, 100], 'color': "lightgreen"}
                        ],
                        'threshold': {
                            'line': {'color': "red", 'width': 4},
                            'thickness': 0.75,
                            'value': 90
                        }
                    }
                ))
                st.plotly_chart(fig_gauge, use_container_width=True)
                
                if score >= 80:
                    st.success("🎉 Excellent! Your business is performing great!")
                elif score >= 60:
                    st.info("👍 Good performance! Room for improvement.")
                elif score >= 40:
                    st.warning("⚠️ Average performance. Focus on key areas.")
                else:
                    st.error("📉 Needs attention. Review recommendations.")

except Exception as e:
    st.error(f"❌ Error analyzing data: {e}")
    import traceback
    st.code(traceback.format_exc())
