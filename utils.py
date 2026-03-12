import streamlit as st
import base64
import hashlib
import json
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

def hash_password(password):
    """Simple SHA-256 hashing for passwords."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_user(username, password):
    """Verify credentials against Firestore."""
    try:
        user_doc = db.collection("users").document(username.lower()).get()
        if user_doc.exists:
            data = user_doc.to_dict()
            if data.get("password") == hash_password(password):
                return {"username": username, "name": data.get("name", username)}
        return None
    except Exception as e:
        print(f"Auth error: {e}")
        return None

def create_user(username, password, name=""):
    """Create a new user in Firestore."""
    try:
        user_ref = db.collection("users").document(username.lower())
        if user_ref.get().exists:
            return False, "Username already exists"
        
        user_ref.set({
            "username": username.lower(),
            "password": hash_password(password),
            "name": name or username,
            "created_at": get_ist_time()
        })
        return True, "User created successfully"
    except Exception as e:
        return False, str(e)

def check_auth(quiet=False):
    """Check if user is authenticated and handle role-based redirection."""
    # The session persistence is handled at the app level to avoid cycles
    if not st.session_state.get("authenticated", False):
        if not quiet:
            st.warning("⚠️ Access Denied. Please login.")
            if st.button("Go to Login"):
                st.switch_page("app.py")
            st.stop()
        return False
    return True

def check_admin():
    """Admin restriction removed. All users have equal access."""
    if not check_auth():
        st.stop()

# --- SETTINGS MANAGEMENT ---
@st.cache_data(ttl=600)
def get_settings():
    """Fetch store settings from Firestore with caching."""
    try:
        settings_ref = db.collection("settings").document("store_info").get()
        if settings_ref.exists:
            return settings_ref.to_dict()
        else:
            # Default fallback settings
            return {
                "store_name": "MY STORE",
                "address": "Set Address in Settings",
                "phone": "0000000000",
                "email": "store@example.com",
                "gstin": "",
                "currency": "₹"
            }
    except Exception as e:
        print(f"Error fetching settings: {e}")
        return {}


# Custom CSS Injection
def inject_custom_css():
    st.markdown("""
    <style>
        /* 1. GLOBAL LIGHT THEME ENFORCEMENT */
        :root {
            --brand-primary: #4f46e5;
            --brand-secondary: #4338ca;
            --brand-gradient: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            --bg-main: #f8fafc;
            --card-bg: #ffffff;
            --sidebar-bg: #ffffff;
            --text-main: #0f172a;
            --text-muted: #475569;
            --border-color: #e2e8f0;
            --radius-lg: 20px;
            --radius-md: 12px;
            --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
            --shadow-md: 0 10px 15px -3px rgba(0,0,0,0.05), 0 4px 6px -2px rgba(0,0,0,0.05);
            --shadow-lg: 0 20px 25px -5px rgba(0,0,0,0.08), 0 10px 10px -5px rgba(0,0,0,0.04);
        }
        
        .stApp {
            background-color: var(--bg-main) !important;
            font-family: 'Inter', sans-serif !important;
        }

        /* ------------------------------------- */
        /* ENHANCED TEXT VISIBILITY (DESKTOP)    */
        /* ------------------------------------- */
        p, .stMarkdown p, .stText, [data-testid="stMarkdownContainer"] p, label, .stRadio div[role="radiogroup"] label, .stCheckbox label {
            color: var(--text-main) !important;
            font-size: 15px !important;
        }
        
        /* Ensures dropdown text and inputs are clearly visible */
        .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] span {
            color: #0f172a !important; 
            font-size: 15px !important;
            font-weight: 500 !important;
        }

        /* ------------------------------------- */
        /* MOBILE RESPONSIVE ADJUSTMENTS         */
        /* ------------------------------------- */
        @media (max-width: 768px) {
            .stMain { padding: 0.5rem !important; }
            [data-testid="stMetric"] { padding: 15px !important; }
            h1 { font-size: 24px !important; }
            h2 { font-size: 20px !important; }
            h3 { font-size: 18px !important; }
            
            /* FORCE LARGER, DARKER TEXT ON MOBILE */
            p, .stMarkdown p, .stText, [data-testid="stMarkdownContainer"] p, label, .stRadio div[role="radiogroup"] label, .stCheckbox label {
                font-size: 16px !important; 
                line-height: 1.5 !important;
                color: #000000 !important;
                font-weight: 500 !important;
            }
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] span {
                font-size: 16px !important; 
                color: #000000 !important;
                padding: 10px 12px !important;
            }
        }

        h1, h2, h3, h4, h5, h6 {
            font-family: 'Outfit', sans-serif !important;
            color: var(--text-main) !important;
            font-weight: 700 !important;
        }

        /* ============================================ */
        /*   2. SIDEBAR — PREMIUM DARK DESIGN           */
        /* ============================================ */
        [data-testid="stSidebar"] {
            background: linear-gradient(160deg, #0f172a 100%, #1e293b 100%) !important;
            border-right: none !important;
            box-shadow: 4px 0 30px rgba(0,0,0,0.15) !important;
        }
        
        /* All text inside sidebar white */
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] h4,
        [data-testid="stSidebar"] h5,
        [data-testid="stSidebar"] small,
        [data-testid="stSidebar"] .stMarkdown p {
            color: #e2e8f0 !important;
        }
        
        /* Section headers like 'Operations' */
        [data-testid="stSidebar"] h6 {
            color: #94a3b8 !important;
            font-size: 11px !important;
            font-weight: 700 !important;
            letter-spacing: 1.5px !important;
            text-transform: uppercase !important;
            padding: 16px 16px 4px 16px !important;
        }

        /* COLLAPSE/EXPAND ARROW — max visibility on white main area */
        [data-testid="stSidebarCollapseButton"],
        [data-testid="collapsedControl"] {
            background: #4f46e5 !important;
            border: 2px solid #6366f1 !important;
            border-radius: 10px !important;
            min-width: 40px !important;
            min-height: 40px !important;
            position: fixed !important;
            top: 12px !important;
            left: 12px !important;
            z-index: 9999 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            box-shadow: 0 4px 14px rgba(79,70,229,0.5) !important;
            transition: all 0.2s ease !important;
            cursor: pointer !important;
        }
        [data-testid="stSidebarCollapseButton"]:hover,
        [data-testid="collapsedControl"]:hover {
            background: #7c3aed !important;
            transform: scale(1.1) !important;
            box-shadow: 0 6px 20px rgba(124,58,237,0.6) !important;
        }
        [data-testid="stSidebarCollapseButton"] svg,
        [data-testid="collapsedControl"] svg {
            fill: #ffffff !important;
            color: #ffffff !important;
            width: 20px !important;
            height: 20px !important;
        }

        /* Hide native navigation list */
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
            display: none !important;
        }

        /* Nav links — normal state */
        div[data-testid="stPageLink-NavLink"] {
            padding: 11px 16px !important;
            border-radius: 10px !important;
            margin: 2px 10px !important;
            transition: all 0.2s ease !important;
            border: 1px solid transparent !important;
        }
        div[data-testid="stPageLink-NavLink"] p {
            color: #cbd5e1 !important;
            font-size: 14px !important;
            font-weight: 500 !important;
        }

        /* Nav links — hover */
        div[data-testid="stPageLink-NavLink"]:hover {
            background: rgba(255,255,255,0.07) !important;
            border-color: rgba(255,255,255,0.1) !important;
        }
        div[data-testid="stPageLink-NavLink"]:hover p {
            color: #ffffff !important;
        }

        /* Nav links — ACTIVE page */
        div[data-testid="stPageLink-NavLink"][aria-current="page"] {
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%) !important;
            box-shadow: 0 4px 15px rgba(99,102,241,0.4) !important;
            border-color: transparent !important;
        }
        div[data-testid="stPageLink-NavLink"][aria-current="page"] p {
            color: #ffffff !important;
            font-weight: 700 !important;
        }
        
        /* Dividers inside sidebar */
        [data-testid="stSidebar"] hr {
            border-color: #334155 !important;
        }
        
        /* Sidebar buttons (Refresh / Logout) */
        [data-testid="stSidebar"] button {
            background: #1e293b !important;
            border: 1px solid #334155 !important;
            color: #e2e8f0 !important;
            border-radius: 10px !important;
        }
        [data-testid="stSidebar"] button:hover {
            background: #334155 !important;
            border-color: #475569 !important;
            color: #ffffff !important;
        }

        /* 5. INPUTS - CLEAN WHITE */
        .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {
            background: white !important;
            border-radius: 12px !important;
            border: 1px solid var(--border-color) !important;
            padding: 8px 12px !important;
            color: black !important;
        }
        
        div[data-baseweb="select"] span {
            color: #0f172a !important;
        }

        /* 3. CARDS & METRICS (Glassmorphism) */
        [data-testid="stMetric"] {
            background: var(--card-bg) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: var(--radius-lg) !important;
            padding: 24px !important;
            box-shadow: var(--shadow-md) !important;
            transition: all 0.3s ease !important;
        }

        [data-testid="stMetric"]:hover {
            transform: translateY(-5px);
        }

        [data-testid="stMetricValue"] {
            color: var(--brand-primary) !important;
            font-size: 2rem !important;
            font-weight: 800 !important;
            font-family: 'Outfit' !important;
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

        /* 6. ALERTS & TOASTS */
        div.stAlert {
            border-radius: var(--radius) !important;
            border: none !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05) !important;
            background-color: white !important;
        }

        /* 7. TABLES - PREMIUM WHITE */
        [data-testid="stDataFrame"] {
            background: white !important;
            border-radius: var(--radius) !important;
            padding: 10px !important;
            border: 1px solid var(--border-color) !important;
        }

        /* 8. TABS STYLING */
        div[data-testid="stTabs"] button {
            font-family: 'Outfit', sans-serif !important;
            font-weight: 600 !important;
            color: var(--text-muted) !important;
        }

        div[data-testid="stTabs"] button[aria-selected="true"] {
            color: var(--brand-primary) !important;
        }
        
        /* 9. SCROLLBARS */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #f1f5f9; }
        ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

        /* MainMenu, Footer, and Header visibility */
        #MainMenu {visibility: visible;}
        footer {visibility: hidden;}
        
        /* Forcely hide native sidebar to prevent delay/interference */
        [data-testid="stSidebarNav"] {
            display: none !important;
        }
        
        [data-testid="stHeader"] {
            background: rgba(255, 255, 255, 0.8) !important;
            backdrop-filter: blur(8px) !important;
            border-bottom: 1px solid var(--border-color) !important;
        }
        
        /* 4. BUTTONS - PREMIUM FEEL */
        button[kind="primary"] {
            background: var(--brand-gradient) !important;
            border: none !important;
            padding: 0.6rem 1.5rem !important;
            border-radius: 12px !important;
            font-weight: 600 !important;
            color: white !important;
            box-shadow: 0 4px 14px 0 rgba(99, 102, 241, 0.39) !important;
            transition: all 0.2s ease !important;
        }

        button[kind="primary"]:hover {
            box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5) !important;
            transform: scale(1.02);
        }

        button[kind="secondary"] {
            background: white !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 12px !important;
            color: var(--text-main) !important;
            transition: all 0.2s ease !important;
        }
        
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@400;600;800&display=swap" rel="stylesheet">

    
    <script>
        (function() {
            function applyAll() {
                // 1. Hide the native Streamlit auto-generated nav links
                const nav = document.querySelector('[data-testid="stSidebarNav"]');
                if (nav) nav.style.display = 'none';

                // 2. Completely hide the native collapse arrow button (we replace it)
                const collapseBtn = document.querySelector('[data-testid="stSidebarCollapseButton"]');
                if (collapseBtn) collapseBtn.style.display = 'none';
                
                // 3. Style the sidebar dark if present
                const sidebar = document.querySelector('[data-testid="stSidebar"]');
                if (sidebar) {
                    sidebar.style.background = 'linear-gradient(160deg, #0f172a 0%, #1e293b 100%)';
                    sidebar.style.borderRight = 'none';
                }

                // 4. Inject our permanent floating hamburger if not already done
                if (!document.getElementById('gmr-sidebar-toggle')) {
                    const btn = document.createElement('button');
                    btn.id = 'gmr-sidebar-toggle';
                    btn.innerHTML = '&#9776;';  // hamburger ≡
                    btn.title = 'Toggle Menu';
                    btn.style.cssText = `
                        position: fixed;
                        top: 10px;
                        left: 10px;
                        z-index: 99999;
                        background: #4f46e5;
                        color: white;
                        border: none;
                        border-radius: 10px;
                        width: 42px;
                        height: 42px;
                        font-size: 22px;
                        cursor: pointer;
                        box-shadow: 0 4px 15px rgba(79,70,229,0.5);
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        transition: all 0.2s;
                    `;
                    btn.onmouseover = () => { btn.style.background = '#7c3aed'; btn.style.transform = 'scale(1.1)'; };
                    btn.onmouseout  = () => { btn.style.background = '#4f46e5'; btn.style.transform = 'scale(1)'; };
                    btn.onclick = () => {
                        // Click the underlying Streamlit collapse button
                        const nativeBtn = document.querySelector('[data-testid="stSidebarCollapseButton"] button') ||
                                          document.querySelector('[data-testid="collapsedControl"] button') ||
                                          document.querySelector('[data-testid="stSidebarCollapseButton"]') ||
                                          document.querySelector('[data-testid="collapsedControl"]');
                        if (nativeBtn) nativeBtn.click();
                    };
                    document.body.appendChild(btn);
                }
            }

            // Run on load and observe for dynamic changes
            applyAll();
            new MutationObserver(applyAll).observe(document.body, {childList: true, subtree: true});
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
    # On app.py, we don't want to stop execution if not authenticated
    # because the login screen needs to be shown.
    if not st.session_state.get("authenticated", False):
        return
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
            st.page_link("pages/4_Credit_Book.py", label="Credit Book (Udhaar)", icon="📙")
            st.page_link("pages/6_Expense_Tracker.py", label="Daily Expense Tracker", icon="💸")
            st.page_link("pages/5_Returns.py", label="Returns / Exchange", icon="↩️")
            st.page_link("pages/8_Stock_Adjustments.py", label="Stock Adjustments", icon="📦")
            
            # History & Reports
            st.markdown("###### History & Reports", help="View past data")
            st.page_link("pages/7_Sales_History.py", label="Sales History", icon="📜")
            st.page_link("pages/3_Reports.py", label="Reports", icon="📊")
            
            st.markdown("###### System", help="App Settings")
            st.page_link("pages/9_Settings.py", label="Settings", icon="⚙️")
            
            st.markdown("---")
            if st.button("🔄 Refresh Data", type="secondary", use_container_width=True):
                clear_items_cache()
                st.rerun()
                
            st.caption(f"v1.2.0 • {get_ist_time().strftime('%d-%b')}")
            
            if st.button("🔓 Logout", use_container_width=True):
                # Clear local storage via JS
                st.markdown("""
                    <script>
                        localStorage.removeItem('gmr_auth_session');
                        window.location.reload();
                    </script>
                """, unsafe_allow_html=True)
                st.session_state["authenticated"] = False
                st.session_state["username"] = None
                st.session_state["user_role"] = None
                st.rerun()
            
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
        
        # Get store settings
        sett = get_settings()
        store_name = sett.get("store_name", "MY STORE").upper()
        store_address = sett.get("address", "Set Address in Settings")
        store_phone = sett.get("phone", "0000000000")
        store_email = sett.get("email", "")
        store_gst = sett.get("gstin", "")

        # Store header
        header_style = ParagraphStyle(
            'StoreHeader',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#4F46E5'),
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        # Remove emoji from PDF header to avoid character rendering issues
        elements.append(Paragraph(f"{store_name}", header_style))
        
        # Store details
        store_details_style = ParagraphStyle(
            'StoreDetails',
            parent=styles['Normal'],
            fontSize=9,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#64748b')
        )
        
        details_text = store_address
        if store_phone: details_text += f" | Phone: {store_phone}"
        if store_email: details_text += f" | Email: {store_email}"
        elements.append(Paragraph(details_text, store_details_style))
        
        if store_gst:
            elements.append(Paragraph(f"GSTIN: {store_gst}", store_details_style))
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
                f"Rs. {item.get('price', 0):,.2f}",
                f"Rs. {item_total:,.2f}"
            ])
        
        # Create table with styling
        table = Table(data, colWidths=[0.5*inch, 3.5*inch, 0.75*inch, 1.25*inch, 1.25*inch])
        table.setStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
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
            ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#4F46E5')),
        ])
        
        elements.append(table)
        elements.append(Spacer(1, 0.15*inch))
        
        # Totals section
        totals_data = [
            ["", "", "", "Subtotal:", f"Rs. {subtotal:,.2f}"]
        ]
        
        if discount_amount > 0:
            # Replace ₹ with Rs. in PDF to prevent font rendering errors
            pdf_discount_type = discount_type.replace('Discount', '').replace('₹', 'Rs.').strip()
            discount_label = f"Discount ({pdf_discount_type}):"
            totals_data.append(["", "", "", discount_label, f"- Rs. {discount_amount:,.2f}"])
        
        totals_data.append(["", "", "", "Grand Total:", f"Rs. {total:,.2f}"])
        
        totals_table = Table(totals_data, colWidths=[0.5*inch, 3.5*inch, 0.75*inch, 1.25*inch, 1.25*inch])
        totals_table.setStyle([
            ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (3, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (3, -1), (-1, -1), 12),
            ('TEXTCOLOR', (3, -1), (-1, -1), colors.HexColor('#4F46E5')),
            ('LINEABOVE', (3, -1), (-1, -1), 2, colors.HexColor('#4F46E5')),
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
        # Remove emoji from footer
        elements.append(Paragraph("Thank you for your business!", footer_style))
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

def build_whatsapp_message(items, subtotal, discount_amount, discount_type, total, customer_name="", invoice_title="Tax Invoice"):
    """Build a professional WhatsApp message for the bill"""
    
    # Header with store branding
    # Professional & Simple Header
    message = "*🏪 GMR FIREWORKS*\n"
    message += f"{invoice_title}\n"
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
    sett = get_settings()
    store_name = sett.get("store_name", "MY STORE").upper()
    store_address = sett.get("address", "Set Address in Settings")
    store_phone = sett.get("phone", "")
    store_email = sett.get("email", "")
    
    html = f"""
    <div style="background-color: white; padding: 30px; border: 1px solid #e2e8f0; border-radius: 12px; max-width: 800px; margin: 0 auto; font-family: 'Inter', sans-serif; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);">
        <!-- Header -->
        <div style="text-align: center; margin-bottom: 20px;">
            <h1 style="color: #4F46E5; margin: 0; font-size: 24px; font-weight: 800;">🏪 {store_name}</h1>
            <p style="color: #64748b; font-size: 13px; margin: 5px 0;">{store_address}</p>
            <p style="color: #64748b; font-size: 13px; margin: 5px 0;">{"Phone: " + store_phone if store_phone else ""} {"| Email: " + store_email if store_email else ""}</p>
        </div>
        
        <hr style="border: 0; border-top: 2px solid #4F46E5; margin: 20px 0; opacity: 0.2;">
        
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


def generate_thermal_bill_html(items, subtotal, discount_amount, discount_type, total, customer_name, customer_phone, payment_method="", invoice_title="TAX INVOICE"):
    """Generate a high-contrast, compact HTML for 58mm/80mm thermal printers."""
    sett = get_settings()
    store_name = sett.get("store_name", "MY STORE").upper()
    store_address = sett.get("address", "Set Address in Settings")
    store_phone = sett.get("phone", "")
    
    html = f"""
    <html>
    <head>
        <style>
            @media print {{
                body {{ margin: 0; padding: 0; width: 80mm; }}
                @page {{ size: 80mm auto; margin: 0; }}
            }}
            body {{
                font-family: 'Courier New', Courier, monospace;
                width: 72mm;
                margin: 0 auto;
                padding: 5px;
                font-size: 12px;
                line-height: 1.2;
                color: black;
            }}
            .text-center {{ text-align: center; }}
            .text-right {{ text-align: right; }}
            .bold {{ font-weight: bold; }}
            .dashed-line {{ border-top: 1px dashed black; margin: 5px 0; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th {{ border-bottom: 1px dashed black; padding: 2px 0; }}
            td {{ padding: 2px 0; }}
            .total-row {{ font-size: 14px; font-weight: bold; margin-top: 5px; }}
        </style>
    </head>
    <body onload="window.print();">
        <div class="text-center">
            <div class="bold" style="font-size: 16px;">{store_name}</div>
            <div style="font-size: 10px;">{store_address}</div>
            {"<div style='font-size: 10px;'>Phone: " + store_phone + "</div>" if store_phone else ""}
        </div>
        
        <div class="dashed-line"></div>
        <div class="text-center bold">{invoice_title}</div>
        <div class="dashed-line"></div>
        
        <div>Date: {get_ist_time().strftime('%d-%m-%Y')}</div>
        <div>Time: {get_ist_time().strftime('%I:%M %p')}</div>
        {f"<div>Cust: {customer_name}</div>" if customer_name else ""}
        {f"<div>Ph: {customer_phone}</div>" if customer_phone else ""}
        {f"<div>Pay: {payment_method}</div>" if payment_method else ""}
        
        <div class="dashed-line"></div>
        
        <table>
            <thead>
                <tr>
                    <th align="left">ITEM</th>
                    <th align="center">QTY</th>
                    <th align="right">AMT</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for item in items:
        line_total = item['qty'] * item['price']
        html += f"""
                <tr>
                    <td align="left">{item['name'][:18]}</td>
                    <td align="center">{item['qty']}</td>
                    <td align="right">{line_total:,.0f}</td>
                </tr>
        """
        
    html += f"""
            </tbody>
        </table>
        
        <div class="dashed-line"></div>
        
        <div class="text-right">Subtotal: {subtotal:,.2f}</div>
        {f"<div class='text-right'>Disc: -{discount_amount:,.2f}</div>" if discount_amount > 0 else ""}
        <div class="text-right total-row">TOTAL: ₹{total:,.2f}</div>
        
        <div class="dashed-line"></div>
        <div class="text-center" style="margin-top: 10px;">
            THANK YOU! VISIT AGAIN<br>
            *** GMR FIREWORKS ***
        </div>
    </body>
    </html>
    """
    return html


def trigger_thermal_print(html_content):
    """Utility to inject a hidden print trigger component."""
    import streamlit.components.v1 as components
    # We use a hidden iframe to trigger print without affecting the main UI
    print_js = f"""
    <iframe id="receiptFrame" style="display:none;"></iframe>
    <script>
        const doc = document.getElementById('receiptFrame').contentWindow.document;
        doc.open();
        doc.write({json.dumps(html_content)});
        doc.close();
        // The onload in HTML will trigger window.print()
    </script>
    """
    components.html(print_js, height=0, width=0)


