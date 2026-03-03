import streamlit as st
import base64
import os
import pandas as pd
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import A4, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.pdfgen import canvas
from io import BytesIO
import urllib.parse
from firebase_config import bucket, db, storage_available

# Helper for IST Time
def get_ist_time():
    """Returns current time in IST (UTC + 5:30)"""
    return datetime.utcnow() + timedelta(hours=5, minutes=30)

def today_string():
    return get_ist_time().strftime("%Y-%m-%d")


# Custom CSS Injection
def inject_custom_css():
    st.markdown("""
    <style>
        /* 1. GLOBAL LIGHT THEME ENFORCEMENT */
        :root {
            --primary: #4F46E5;
            --background: #f8fafc;
            --text: #1e293b;
            --secondary: #ffffff;
        }
        
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
            background-color: #f8fafc !important;
        }
        
        /* Force text colors to be dark (slate-800) */
        h1, h2, h3, h4, h5, h6, p, label, span, div, li {
            color: #1e293b !important;
        }
        
        /* Overaggressive text override for complex widgets */
        [data-testid="stMarkdownContainer"] p, 
        [data-testid="stWidgetLabel"] p,
        .stSelectbox div, .stTextInput div, .stNumberInput div {
            color: #1e293b !important;
        }

        /* 2. SIDEBAR STYLING */
        section[data-testid="stSidebar"] {
            background-color: #ffffff !important;
            border-right: 1px solid #e2e8f0;
        }
        
        section[data-testid="stSidebar"] * {
            color: #1e293b !important;
        }
        
        /* Hide native nav */
        [data-testid="stSidebarNav"] {
            display: none !important;
        }
        
        /* Custom Nav Link Styling - restoring premium feel */
        div[data-testid="stPageLink-NavLink"] {
            background-color: transparent;
            border-radius: 8px;
            margin-bottom: 4px;
            padding: 8px 12px;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        div[data-testid="stPageLink-NavLink"]:hover {
            background-color: #f1f5f9 !important;
            transform: translateX(4px);
        }
        
        div[data-testid="stPageLink-NavLink"][aria-current="page"] {
            background-color: #e0e7ff !important;
            border-left: 4px solid #4F46E5 !important;
        }
        
        div[data-testid="stPageLink-NavLink"][aria-current="page"] p {
            color: #4338ca !important;
            font-weight: 600 !important;
        }

        /* 3. INPUT WIDGETS (Inputs, Selects, etc) */
        .stTextInput input, .stNumberInput input, .stTextArea textarea, .stDateInput input {
            background-color: #ffffff !important;
            color: #000000 !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 8px !important;
        }
        
        /* SELECTBOX & DROPDOWN - CRITICAL FIX */
        /* The select box itself (closed) */
        div[data-baseweb="select"] > div {
            background-color: #ffffff !important;
            color: #000000 !important;
            border-radius: 8px !important;
        }
        
        /* The persistent selected item text */
        div[data-baseweb="select"] [v-data-testid="stSelectbox"] span,
        div[data-baseweb="select"] span {
            color: #000000 !important;
        }

        /* THE DROPDOWN LIST (OPENED) */
        /* This is usually in a portal at the body level */
        div[data-baseweb="popover"], 
        div[role="listbox"],
        div[data-baseweb="menu"],
        ul[role="listbox"] {
            background-color: #ffffff !important;
            color: #1e293b !important;
            border: 1px solid #e2e8f0 !important;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1) !important;
            border-radius: 8px !important;
        }

        /* Items in the list */
        li[role="option"], 
        [role="listbox"] li,
        [data-baseweb="popover"] li {
            background-color: #ffffff !important;
            color: #1e293b !important;
            padding: 10px 15px !important;
            margin: 2px 5px !important;
            border-radius: 6px !important;
        }

        /* Hover & Active States in List */
        li[role="option"]:hover,
        [role="listbox"] li:hover,
        [data-baseweb="popover"] li:hover {
            background-color: #f1f5f9 !important;
            color: #4F46E5 !important;
        }

        /* 4. METRICS & CARDS */
        [data-testid="stMetric"] {
            background-color: white !important;
            padding: 20px !important;
            border-radius: 12px !important;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
            border: 1px solid #f1f5f9 !important;
        }
        
        [data-testid="stMetricValue"] {
            color: #4F46E5 !important;
            font-weight: 700 !important;
        }
        
        /* 5. BUTTONS */
        button[kind="primary"] {
            background-color: #4f46e5 !important;
            color: white !important;
            border: none !important;
            border-radius: 8px !important;
            box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.2) !important;
        }
        
        button[kind="secondary"] {
            background-color: white !important;
            color: #1e293b !important;
            border: 1px solid #d1d5db !important;
            border-radius: 8px !important;
        }

        /* Clean up some native Streamlit spacing */
        .main .block-container {
            padding-top: 3rem !important;
        }
        
    </style>
    
    <script>
        // Smoothly hide native navigation
        (function() {
            const hide = () => {
                const nav = document.querySelector('[data-testid="stSidebarNav"]');
                if (nav) nav.style.display = 'none';
            };
            hide();
            new MutationObserver(hide).observe(document.body, {childList:true, subtree:true});
        })();
    </script>
    """, unsafe_allow_html=True)

# --- CACHED DATA OPERATIONS ---

@st.cache_data(ttl=300)
def get_all_items():
    """Fetch all items from Firestore with caching to reduce reads and improve speed."""
    try:
        items_ref = db.collection("items_master").stream()
        # Convert to dictionary for easy lookup: {id: data}
        items_dict = {item.id: item.to_dict() for item in items_ref}
        return items_dict
    except Exception as e:
        print(f"Error fetching items: {e}")
        return {}

def clear_items_cache():
    """Clear the items cache to force a refresh."""
    st.cache_data.clear()

# --- CUSTOM SIDEBAR ---

def render_sidebar():
    """Render a custom sidebar using streamlit-option-menu styled links"""
    try:
        with st.sidebar:
            st.image("https://img.icons8.com/color/96/shop.png", width=60)
            st.subheader("Store Manager")
            st.markdown("---")
            
            # Dashboard
            st.page_link("app.py", label="Dashboard", icon="🏠")
            
            # Core Operations
            st.markdown("###### Operations", help="Manage daily tasks")
            st.page_link("pages/2_Sales.py", label="New Sale", icon="🛒")
            st.page_link("pages/1_Items_Master.py", label="Inventory / Items", icon="📦")
            st.page_link("pages/5_Returns.py", label="Returns / Exchange", icon="↩️")
            
            # History & Reports
            st.markdown("###### History & Reports", help="View past data")
            st.page_link("pages/7_Sales_History.py", label="Sales History", icon="📜")
            st.page_link("pages/3_Reports.py", label="Reports", icon="📊")
            st.page_link("pages/6_Email_Reports.py", label="Email Reports", icon="📧")
            
            # Advanced Analytics
            st.markdown("###### Analytics", help="Deep insights")
            st.page_link("pages/4_AI_Insights.py", label="AI Insights", icon="🧠")
            # You can add more pages here dynamically
            
            st.markdown("---")
            if st.button("🔄 Refresh Data", type="secondary", use_container_width=True):
                clear_items_cache()
                st.rerun()
                
            st.caption(f"v1.2.0 • {get_ist_time().strftime('%d-%b')}")
            
    except Exception as e:
        st.error(f"Sidebar Error: {e}")


def generate_bill_pdf(filename, items, subtotal, discount_amount, discount_type, total, customer_name="", customer_phone="", payment_method="", invoice_title="TAX INVOICE"):
    try:
        if not items:
            raise ValueError("Cannot generate bill with empty items list")
        
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import Paragraph, Spacer, HRFlowable
        from reportlab.lib.units import inch
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
        
        doc = SimpleDocTemplate(filename, pagesize=A4,
                               topMargin=0.5*inch, bottomMargin=0.5*inch,
                               leftMargin=0.75*inch, rightMargin=0.75*inch)
        elements = []
        styles = getSampleStyleSheet()
        
        # Store header with logo placeholder
        header_style = ParagraphStyle(
            'StoreHeader',
            parent=styles['Heading1'],
            fontSize=28,
            textColor=colors.HexColor('#1f77b4'),
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        elements.append(Paragraph("🏪 GMR FIREWORKS", header_style))
        
        # Store details
        store_details_style = ParagraphStyle(
            'StoreDetails',
            parent=styles['Normal'],
            fontSize=10,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#666666')
        )
        elements.append(Paragraph("123 Main Street, City, State - 123456", store_details_style))
        elements.append(Paragraph("Phone: +91-1234567890 | Email: store@example.com", store_details_style))
        elements.append(Paragraph("GSTIN: 22AAAAA0000A1Z5 (if applicable)", store_details_style))
        elements.append(Spacer(1, 0.2*inch))
        
        # Horizontal line
        elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#1f77b4')))
        elements.append(Spacer(1, 0.15*inch))
        
        # Invoice title
        invoice_style = ParagraphStyle(
            'InvoiceTitle',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#333333'),
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        elements.append(Paragraph(invoice_title, invoice_style))
        elements.append(Spacer(1, 0.15*inch))
        
        # Customer information and bill details side by side
        info_style = styles['Normal']
        info_style.fontSize = 10
        
        from reportlab.platypus import TableStyle as TS
        
        # Payment info included
        payment_info = f"<br/>Payment Mode: {payment_method}" if payment_method else ""
        
        info_data = [
            [
                Paragraph(f"<b>Bill To:</b><br/>{customer_name}<br/>Phone: {customer_phone if customer_phone else 'N/A'}", info_style),
                Paragraph(f"<b>Ref No:</b> {get_ist_time().strftime('%Y%m%d%H%M%S')}<br/><b>Date:</b> {get_ist_time().strftime('%d-%m-%Y')}<br/><b>Time:</b> {get_ist_time().strftime('%I:%M %p')}{payment_info}", info_style)
            ]
        ]
        info_table = Table(info_data, colWidths=[3.5*inch, 3*inch])
        info_table.setStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ])
        elements.append(info_table)
        elements.append(Spacer(1, 0.25*inch))
        
        # Items table
        data = [["#", "Item Description", "Qty", "Price", "Amount"]]
        
        for idx, item in enumerate(items, 1):
            item_total = item.get('qty', 0) * item.get('price', 0)
            data.append([
                str(idx),
                str(item.get("name", "Unknown")), 
                str(item.get("qty", 0)), 
                f"₹{item.get('price', 0):,.2f}",
                f"₹{item_total:,.2f}"
            ])
        
        # Create table with styling
        table = Table(data, colWidths=[0.5*inch, 3.5*inch, 0.75*inch, 1.25*inch, 1.25*inch])
        table.setStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),  # Item names left-aligned
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#1f77b4')),
        ])
        
        elements.append(table)
        elements.append(Spacer(1, 0.15*inch))
        
        # Totals section
        totals_data = [
            ["", "", "", "Subtotal:", f"₹{subtotal:,.2f}"]
        ]
        
        if discount_amount > 0:
            discount_label = f"Discount ({discount_type.replace('Discount', '').strip()}):"
            totals_data.append(["", "", "", discount_label, f"- ₹{discount_amount:,.2f}"])
        
        totals_data.append(["", "", "", "Grand Total:", f"₹{total:,.2f}"])
        
        totals_table = Table(totals_data, colWidths=[0.5*inch, 3.5*inch, 0.75*inch, 1.25*inch, 1.25*inch])
        totals_table.setStyle([
            ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (3, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (3, -1), (-1, -1), 12),
            ('TEXTCOLOR', (3, -1), (-1, -1), colors.HexColor('#1f77b4')),
            ('LINEABOVE', (3, -1), (-1, -1), 2, colors.HexColor('#1f77b4')),
            ('TOPPADDING', (3, -1), (-1, -1), 8),
        ])
        
        elements.append(totals_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Footer
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
        elements.append(Spacer(1, 0.1*inch))
        
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=9,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#666666')
        )
        elements.append(Paragraph("Thank you for your business! 🙏", footer_style))
        # REMOVED: computer-generated message
        
        doc.build(elements)
        return True
    except Exception as e:
        print(f"Error generating PDF: {e}")
        raise

def upload_bill_to_firebase(local_file, bill_name):
    try:
        if bucket is None:
            print("⚠️ Storage bucket not available, skipping cloud upload")
            return None
            
        blob = bucket.blob(f"bills/{bill_name}")
        blob.upload_from_filename(local_file)
        blob.make_public()
        return blob.public_url
    except Exception as e:
        print(f"⚠️ Error uploading to Firebase (continuing without cloud upload): {e}")
        return None

def build_whatsapp_message(items, subtotal, discount_amount, discount_type, total, customer_name=""):
    """Build a professional WhatsApp message for the bill"""
    
    # Header with store branding
    # Professional & Simple Header
    message = "*🏪 GMR FIREWORKS*\n"
    message += "Tax Invoice\n"
    message += "──────────────────────\n"
    
    # Customer & Date (Compact)
    if customer_name:
        message += f"👤 *{customer_name}*\n"
        
    from datetime import datetime
    message += f"📅 {get_ist_time().strftime('%d-%b-%Y')} | ⏰ {get_ist_time().strftime('%I:%M %p')}\n"
    message += "──────────────────────\n"
    
    # Items List (Clean)
    for item in items:
        line_total = item['qty'] * item['price']
        message += f"• *{item['name']}*\n"
        message += f"   {item['qty']} × ₹{item['price']:,} = *₹{line_total:,.2f}*\n"
    
    message += "──────────────────────\n"
    
    # Payment Details
    if discount_amount > 0:
        message += f"Subtotal: ₹{subtotal:,.2f}\n"
        discount_label = discount_type.replace("Discount", "").strip()
        message += f"Discount: -₹{discount_amount:,.2f}\n"
    
    message += f"*GRAND TOTAL: ₹{total:,.2f}*\n"
    message += "──────────────────────\n\n"
    
    message += "🙏 *Thank you for your business!*"
    
    return urllib.parse.quote(message)

def generate_bill_html(items, subtotal, discount_amount, discount_type, total, customer_name, customer_phone, payment_method="", invoice_title="TAX INVOICE"):
    """Generate an HTML representation of the bill for preview"""
    
    html = f"""
    <div style="background-color: white; padding: 30px; border: 1px solid #e5e7eb; border-radius: 8px; max-width: 800px; margin: 0 auto; font-family: 'Inter', sans-serif; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
        <!-- Header -->
        <div style="text-align: center; margin-bottom: 20px;">
            <h1 style="color: #1f77b4; margin: 0; font-size: 28px;">🏪 GMR FIREWORKS</h1>
            <p style="color: #666; font-size: 14px; margin: 5px 0;">123 Main Street, City, State - 123456</p>
            <p style="color: #666; font-size: 14px; margin: 5px 0;">Phone: +91-1234567890 | Email: store@example.com</p>
        </div>
        
        <hr style="border: 0; border-top: 2px solid #1f77b4; margin: 20px 0;">
        
        <h2 style="text-align: center; color: #333; margin-bottom: 20px;">{invoice_title}</h2>
        
        <!-- Info -->
        <div style="display: flex; justify-content: space-between; margin-bottom: 30px;">
            <div style="width: 48%;">
                <p style="margin: 0; font-weight: bold;">Bill To:</p>
                <p style="margin: 5px 0; color: #333;">{customer_name}</p>
                <p style="margin: 0; color: #666; font-size: 14px;">Phone: {customer_phone if customer_phone else 'N/A'}</p>
            </div>
            <div style="width: 48%; text-align: right;">
                <p style="margin: 2px 0; font-size: 14px;"><b>Date:</b> {get_ist_time().strftime('%d-%m-%Y')}</p>
                <p style="margin: 2px 0; font-size: 14px;"><b>Time:</b> {get_ist_time().strftime('%I:%M %p')}</p>
                <p style="margin: 2px 0; font-size: 14px;"><b>Payment:</b> {payment_method if payment_method else 'Not Specified'}</p>
            </div>
        </div>
        
        <!-- Table -->
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
            <thead style="background-color: #1f77b4; color: white;">
                <tr>
                    <th style="padding: 10px; text-align: center; border: 1px solid #1f77b4;">#</th>
                    <th style="padding: 10px; text-align: left; border: 1px solid #1f77b4;">Item Description</th>
                    <th style="padding: 10px; text-align: center; border: 1px solid #1f77b4;">Qty</th>
                    <th style="padding: 10px; text-align: right; border: 1px solid #1f77b4;">Price</th>
                    <th style="padding: 10px; text-align: right; border: 1px solid #1f77b4;">Amount</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for idx, item in enumerate(items, 1):
        line_total = item['qty'] * item['price']
        html += f"""
                <tr>
                    <td style="padding: 8px; text-align: center; border: 1px solid #e5e7eb;">{idx}</td>
                    <td style="padding: 8px; text-align: left; border: 1px solid #e5e7eb;">{item['name']}</td>
                    <td style="padding: 8px; text-align: center; border: 1px solid #e5e7eb;">{item['qty']}</td>
                    <td style="padding: 8px; text-align: right; border: 1px solid #e5e7eb;">₹{item['price']:,.2f}</td>
                    <td style="padding: 8px; text-align: right; border: 1px solid #e5e7eb;">₹{line_total:,.2f}</td>
                </tr>
        """
        
    html += f"""
            </tbody>
        </table>
        
        <!-- Totals -->
        <div style="display: flex; justify-content: flex-end;">
            <div style="width: 50%;">
                <div style="display: flex; justify-content: space-between; padding: 5px 0;">
                    <span>Subtotal:</span>
                    <span>₹{subtotal:,.2f}</span>
                </div>
    """
    
    if discount_amount > 0:
        discount_label = discount_type.replace("Discount", "").strip()
        html += f"""
                <div style="display: flex; justify-content: space-between; padding: 5px 0; color: #ef4444;">
                    <span>Discount ({discount_label}):</span>
                    <span>- ₹{discount_amount:,.2f}</span>
                </div>
        """
        
    html += f"""
                <div style="display: flex; justify-content: space-between; padding: 10px 0; border-top: 2px solid #1f77b4; font-weight: bold; color: #1f77b4; font-size: 18px; margin-top: 5px;">
                    <span>Grand Total:</span>
                    <span>₹{total:,.2f}</span>
                </div>
            </div>
        </div>
        
        <!-- Footer -->
        <div style="margin-top: 30px; text-align: center; color: #666; font-size: 12px; border-top: 1px solid #e5e7eb; padding-top: 20px;">
            <p style="margin: 5px 0;">Thank you for your business! 🙏</p>
        </div>
    </div>
    """
    return html


