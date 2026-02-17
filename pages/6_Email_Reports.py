import streamlit as st
from firebase_config import db
from datetime import datetime, timedelta
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import io
import streamlit as st
from utils import inject_custom_css, render_sidebar

st.set_page_config(page_title="Email Reports", layout="wide", page_icon="📧")
inject_custom_css()
render_sidebar()

st.title("📧 Email Reports")

# Create tabs
tab1, tab2, tab3 = st.tabs(["⚙️ Email Settings", "📤 Send Report", "📜 Email History"])

# ==================== TAB 1: EMAIL SETTINGS ====================
with tab1:
    st.markdown("### ⚙️ Configuration")
    st.markdown("Setup your email to enable automated reporting.")
    st.markdown("---")
    
    col_main, col_help = st.columns([2, 1])
    
    with col_main:
        with st.form("email_settings_form"):
            st.subheader("Credentials")
            
            sender_email = st.text_input("Sender Email (Gmail)", placeholder="your.store@gmail.com")
            sender_password = st.text_input("App Password", type="password", help="Generated from Google Account Security")
            
            st.subheader("Recipients")
            recipient_emails = st.text_area(
                "Send Reports To",
                placeholder="owner@example.com, manager@example.com",
                help="Enter multiple emails separated by commas"
            )
            
            with st.expander("🔌 Advanced SMTP Settings (Optional)"):
                smtp_server = st.text_input("SMTP Server", value="smtp.gmail.com")
                smtp_port = st.number_input("SMTP Port", value=587)
            
            submit_btn = st.form_submit_button("💾 Save Configuration", type="primary", use_container_width=True)
            
            if submit_btn:
                # Save to session state (in production, save to database)
                st.session_state["email_settings"] = {
                    "smtp_server": smtp_server,
                    "smtp_port": smtp_port,
                    "sender_email": sender_email,
                    "sender_password": sender_password,
                    "recipient_emails": recipient_emails
                }
                st.success("✅ Settings saved successfully!")
                
    with col_help:
        with st.container(border=True):
            st.markdown("#### 🆘 Quick Guide")
            st.markdown("""
            **How to get App Password?**
            1. Go to [Google Account](https://myaccount.google.com/)
            2. Select **Security**
            3. Enable **2-Step Verification**
            4. Search for **App Passwords**
            5. Create new for 'Mail'
            6. Copy the 16-digit code
            """)
            st.info("We recommend using a dedicated Gmail account for store notifications.")

# ==================== TAB 2: SEND REPORT ====================
with tab2:
    st.subheader("📤 Send Email Report")
    
    # Check if email is configured
    if "email_settings" not in st.session_state:
        st.warning("⚠️ Please configure email settings first in the 'Email Settings' tab")
    else:
        # Report type selection
        report_type = st.selectbox(
            "Report Type",
            ["Daily Summary", "Weekly Summary", "Monthly Summary", "Custom Date Range"]
        )
        
        # Date selection based on report type
        if report_type == "Daily Summary":
            report_date = st.date_input("Select Date", value=datetime.now())
            start_date = report_date
            end_date = report_date
        elif report_type == "Weekly Summary":
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=7)
            st.write(f"Report Period: {start_date} to {end_date}")
        elif report_type == "Monthly Summary":
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=30)
            st.write(f"Report Period: {start_date} to {end_date}")
        else:  # Custom
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start Date")
            with col2:
                end_date = st.date_input("End Date")
        
        # Additional options
        include_excel = st.checkbox("📎 Attach Excel Report", value=True)
        
        if st.button("📧 Send Email Report", type="primary", use_container_width=True):
            try:
                with st.spinner("Generating report..."):
                    # Fetch sales data
                    all_sales = db.collection("sales").stream()
                    sales_data = []
                    
                    for sale in all_sales:
                        data = sale.to_dict()
                        sale_date_str = data.get("date", "")
                        
                        try:
                            sale_date = datetime.strptime(sale_date_str, "%Y-%m-%d").date()
                        except:
                            continue
                        
                        if start_date <= sale_date <= end_date:
                            sales_data.append({
                                "Date": sale_date_str,
                                "Customer": data.get("customer_name", "N/A"),
                                "Items": len(data.get("items", [])),
                                "Total": data.get("total", 0)
                            })
                    
                    if not sales_data:
                        st.warning("No sales data found for the selected period")
                    else:
                        df = pd.DataFrame(sales_data)
                        
                        # Calculate summary
                        total_sales = len(df)
                        total_revenue = df['Total'].sum()
                        avg_order = df['Total'].mean()
                        
                        # Create email
                        settings = st.session_state["email_settings"]
                        
                        msg = MIMEMultipart()
                        msg['From'] = settings["sender_email"]
                        msg['To'] = settings["recipient_emails"]
                        msg['Subject'] = f"Sales Report - {start_date} to {end_date}"
                        
                        # Email body
                        body = f"""
                        <html>
                        <body style="font-family: Arial, sans-serif;">
                            <h2 style="color: #1f77b4;">📊 Sales Report</h2>
                            <p><strong>Period:</strong> {start_date} to {end_date}</p>
                            <hr>
                            
                            <h3>Summary</h3>
                            <table style="border-collapse: collapse; width: 100%;">
                                <tr style="background-color: #f2f2f2;">
                                    <td style="padding: 10px; border: 1px solid #ddd;"><strong>Total Sales</strong></td>
                                    <td style="padding: 10px; border: 1px solid #ddd;">{total_sales}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px; border: 1px solid #ddd;"><strong>Total Revenue</strong></td>
                                    <td style="padding: 10px; border: 1px solid #ddd;">₹{total_revenue:,.2f}</td>
                                </tr>
                                <tr style="background-color: #f2f2f2;">
                                    <td style="padding: 10px; border: 1px solid #ddd;"><strong>Average Order Value</strong></td>
                                    <td style="padding: 10px; border: 1px solid #ddd;">₹{avg_order:,.2f}</td>
                                </tr>
                            </table>
                            
                            <br>
                            <p style="color: #666;">This is an automated report from your Store Management System.</p>
                            <p style="color: #666;">Generated on: {datetime.now().strftime('%d-%m-%Y %I:%M %p')}</p>
                        </body>
                        </html>
                        """
                        
                        msg.attach(MIMEText(body, 'html'))
                        
                        # Attach Excel if requested
                        if include_excel:
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                df.to_excel(writer, index=False, sheet_name='Sales Report')
                            output.seek(0)
                            
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(output.read())
                            encoders.encode_base64(part)
                            part.add_header('Content-Disposition', f'attachment; filename=sales_report_{start_date}_to_{end_date}.xlsx')
                            msg.attach(part)
                        
                        # Send email
                        with st.spinner("Sending email..."):
                            server = smtplib.SMTP(settings["smtp_server"], settings["smtp_port"])
                            server.starttls()
                            server.login(settings["sender_email"], settings["sender_password"])
                            
                            recipients = [email.strip() for email in settings["recipient_emails"].split(",")]
                            server.send_message(msg)
                            server.quit()
                        
                        # Log email sent
                        db.collection("email_logs").add({
                            "report_type": report_type,
                            "start_date": str(start_date),
                            "end_date": str(end_date),
                            "recipients": recipients,
                            "total_sales": total_sales,
                            "total_revenue": total_revenue,
                            "sent_at": datetime.now()
                        })
                        
                        st.success(f"✅ Email sent successfully to {len(recipients)} recipient(s)!")
                        st.balloons()
            
            except smtplib.SMTPAuthenticationError:
                st.error("❌ Authentication failed. Please check your email and app password.")
            except Exception as e:
                st.error(f"❌ Error sending email: {e}")
                import traceback
                st.code(traceback.format_exc())

# ==================== TAB 3: EMAIL HISTORY ====================
with tab3:
    st.subheader("📜 Email History")
    
    try:
        # Fetch email logs
        logs_ref = db.collection("email_logs").order_by("sent_at", direction="DESCENDING").limit(50).stream()
        logs_data = []
        
        for log in logs_ref:
            data = log.to_dict()
            logs_data.append({
                "Date": data.get("sent_at", datetime.now()).strftime("%d-%m-%Y %I:%M %p") if isinstance(data.get("sent_at"), datetime) else "N/A",
                "Report Type": data.get("report_type", "N/A"),
                "Period": f"{data.get('start_date', 'N/A')} to {data.get('end_date', 'N/A')}",
                "Recipients": ", ".join(data.get("recipients", [])),
                "Sales": data.get("total_sales", 0),
                "Revenue": f"₹{data.get('total_revenue', 0):,.2f}"
            })
        
        if logs_data:
            df = pd.DataFrame(logs_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No email history yet. Send your first report!")
    
    except Exception as e:
        st.error(f"Error loading email history: {e}")

# ==================== SCHEDULE SECTION ====================
# Placeholder for future scheduler logic
