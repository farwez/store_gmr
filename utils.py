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
        /* FORCE LIGHT MODE COLORS - GLOBAL OVERRIDES */
        :root {
            --primary-color: #4F46E5;
            --background-color: #f8fafc;
            --secondary-background-color: #ffffff;
            --text-color: #1e293b; /* Slate-800 */
            --font: "Inter", sans-serif;
        }
        
        /* Force App Background & Text */
        .stApp {
            background-color: var(--background-color) !important;
            color: var(--text-color) !important;
        }
        
        /* Force Text Colors to be Dark (Visible on Light BG) */
        h1, h2, h3, h4, h5, h6, 
        p, div, span, label, 
        .stMarkdown, .stText,
        [data-testid="stMarkdownContainer"] {
            color: #1e293b !important;
        }
        
        /* Force visibility of all text content */
        * {
            -webkit-text-fill-color: initial !important;
        }
        
        /* -------------------------------------
           SIDEBAR FIXES
           ------------------------------------- */
        /* Explicit Sidebar Background */
        section[data-testid="stSidebar"] {
            background-color: #ffffff !important;
            border-right: 1px solid #e2e8f0;
        }
        
        /* Sidebar text visibility */
        section[data-testid="stSidebar"] * {
            color: #1e293b !important;
        }
        
        /* Hide Native Navigation (Double Sidebar Fix) - ULTRA AGGRESSIVE */
        [data-testid="stSidebarNav"],
        [data-testid="stSidebarNavItems"],
        [data-testid="stSidebarNavLink"],
        section[data-testid="stSidebar"] nav,
        section[data-testid="stSidebar"] ul[role="navigation"],
        .css-1544g2n,
        .css-17lntkn,
        div[class*="stSidebarNav"] {
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
            width: 0 !important;
            overflow: hidden !important;
            position: absolute !important;
            left: -9999px !important;
        }

        /* Adjust Sidebar Top Padding */
        section[data-testid="stSidebar"] > div {
            padding-top: 2rem;
        }
        
        /* Sidebar Link Styling */
        div[data-testid="stPageLink-NavLink"] {
            background-color: transparent;
            border-radius: 6px;
            margin-bottom: 4px;
            padding: 8px 12px;
            transition: all 0.2s;
        }
        
        div[data-testid="stPageLink-NavLink"]:hover {
            background-color: #f1f5f9 !important;
            transform: translateX(5px);
        }
        
        /* Active Link Styling */
        div[data-testid="stPageLink-NavLink"][aria-current="page"] {
            background-color: #e0e7ff !important; /* Indigo-50 */
            border-left: 4px solid #4F46E5 !important;
        }
        
        div[data-testid="stPageLink-NavLink"][aria-current="page"] p {
            color: #4338ca !important; /* Indigo-700 */
            font-weight: 600 !important;
        }

        /* -------------------------------------
           INPUT WIDGETS FIXES
           ------------------------------------- */
        /* Force Input Fields to be White with DARK TEXT */
        .stTextInput input, 
        .stNumberInput input, 
        .stTextArea textarea {
            color: #000000 !important;
            background-color: #ffffff !important;
            border: 1px solid #cbd5e1 !important;
            -webkit-text-fill-color: #000000 !important;
        }
        
        /* Input placeholder text */
        .stTextInput input::placeholder,
        .stNumberInput input::placeholder,
        .stTextArea textarea::placeholder {
            color: #9ca3af !important;
            opacity: 1 !important;
        }
        
        /* Input labels */
        .stTextInput label,
        .stNumberInput label,
        .stTextArea label,
        .stSelectbox label {
            color: #374151 !important;
            font-weight: 500 !important;
        }
        
        /* Selectbox Container */
        .stSelectbox div[data-baseweb="select"] > div {
            color: #000000 !important;
            background-color: #ffffff !important;
            border: 1px solid #cbd5e1 !important;
        }
        
        /* Selectbox selected value text */
        .stSelectbox div[data-baseweb="select"] span {
            color: #000000 !important;
        }
        
        /* Selectbox Dropdown Menu */
        div[data-baseweb="popover"] {
            background-color: #ffffff !important;
        }
        
        /* Selectbox Options/Items in Dropdown */
        ul[role="listbox"] li {
            color: #000000 !important;
            background-color: #ffffff !important;
        }
        
        /* Selectbox Hover State */
        ul[role="listbox"] li:hover {
            background-color: #f1f5f9 !important;
            color: #4F46E5 !important;
        }
        
        /* Selected Option */
        ul[role="listbox"] li[aria-selected="true"] {
            background-color: #e0e7ff !important;
            color: #4338ca !important;
        }
        
        /* -------------------------------------
           OTHER UI ELEMENTS
           ------------------------------------- */
        /* Metrics Cards */
        [data-testid="stMetricValue"] {
            color: #4F46E5 !important;
        }
        
        /* Tables / Dataframes */
        [data-testid="stDataFrame"] {
            color: #1e293b !important;
        }

        /* Mobile specific adjustments */
        @media (max-width: 768px) {
            section[data-testid="stSidebar"] > div {
                padding-top: 1rem;
            }
            font-weight: 600;
        }
        
        div[data-testid="stMetricValue"] {
            color: #111827 !important;
            font-size: 1.5rem;
            font-weight: 700;
        }
        
        /* Buttons - Primary */
        button[kind="primary"] {
            background-color: #4f46e5;
            color: white !important;
            border-radius: 0.375rem;
            border: none;
            padding: 0.5rem 1rem;
            font-weight: 500;
            transition: all 0.2s;
        }
        button[kind="primary"]:hover {
            background-color: #4338ca;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        }
        
        /* Buttons - Secondary */
        button[kind="secondary"] {
            background-color: #ffffff;
            color: #1f2937 !important; /* Force dark text */
            border: 1px solid #d1d5db;
            border-radius: 0.375rem;
            transition: all 0.2s;
        }
        button[kind="secondary"]:hover {
            border-color: #4f46e5;
            color: #4f46e5 !important;
            background-color: #fdfbff;
        }
        
        /* Input Fields */
        div[data-baseweb="input"] {
            background-color: #ffffff;
            border-radius: 0.375rem;
            border: 1px solid #d1d5db;
        }
        
        /* Dataframes */
        div[data-testid="stDataFrame"] {
            background-color: #ffffff;
            border-radius: 0.5rem;
            padding: 0.5rem;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
            border: 1px solid #e5e7eb;
        }
        
        /* Success/Error/Warning/Info Messages */
        div.stAlert {
            background-color: #ffffff;
            border-radius: 0.5rem;
            border: none;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
        }
        
    </style>
    
    <script>
        // Remove native navigation IMMEDIATELY (prevents flash/glitch)
        (function() {
            const hideNav = () => {
                // Target all possible navigation elements
                const selectors = [
                    '[data-testid="stSidebarNav"]',
                    '[data-testid="stSidebarNavItems"]',
                    '[data-testid="stSidebarNavLink"]',
                    'section[data-testid="stSidebar"] nav',
                    'section[data-testid="stSidebar"] ul[role="navigation"]',
                    '.css-1544g2n',
                    '.css-17lntkn'
                ];
                
                selectors.forEach(selector => {
                    const elements = document.querySelectorAll(selector);
                    elements.forEach(el => {
                        if (el) {
                            el.style.display = 'none';
                            el.style.visibility = 'hidden';
                            el.style.height = '0';
                            el.style.overflow = 'hidden';
                            el.remove(); // Actually remove from DOM
                        }
                    });
                });
            };
            
            // Run immediately
            hideNav();
            
            // Run again after DOM loads
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', hideNav);
            }
            
            // Run periodically to catch late-rendered elements
            const observer = new MutationObserver(hideNav);
            observer.observe(document.body, { childList: true, subtree: true });
            
            // Stop observing after 3 seconds (navigation should be loaded by then)
            setTimeout(() => observer.disconnect(), 3000);
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


