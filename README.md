# 🎆 GMR Fireworks - Store Management System

A comprehensive, professional-grade Point of Sale (POS) and inventory management system designed for GMR Fireworks. This application streamlines billing, inventory tracking, returns, and provides AI-powered insights for smarter decision-making.

## 🚀 Key Features

*   **🛒 Sales & Billing**: 
    *   Generate professional Tax Invoices and Quotations instantly.
    *   Automatic PDF generation with custom branding.
    *   Direct WhatsApp sharing integration.
    *   Support for discounts and multiple payment methods.
*   **📦 Inventory Management**:
    *   Real-time stock tracking and low-stock alerts.
    *   Searchable item master database.
    *   Batch import/export via Excel.
*   **↩️ Returns & Exchanges**:
    *   Process returns seamlessly with automatic stock adjustment.
    *   Calculate refund amounts and manage exchange inventory.
*   **📊 Reports & Analytics**:
    *   Daily, Weekly, and Monthly sales summaries.
    *   Exportable reports (Excel/CSV).
    *   Visual dashboards for sales trends.
*   **🧠 AI Insights**:
    *   Advanced analytics powered by AI to identify top-selling products and customer trends.
    *   Predictive recommendations for restocking.
*   **📧 Automated E-mail Reports**:
    *   Send daily sales summaries to owners/managers automatically via email.

## 🛠️ Technology Stack

*   **Frontend**: [Streamlit](https://streamlit.io/) (Python)
*   **Backend**: Python
*   **Database**: Google Firebase (Firestore)
*   **Storage**: Firebase Storage (for PDF bills)
*   **PDF Generation**: ReportLab
*   **Data Analysis**: Pandas, Plotly

## ⚙️ Installation & Setup

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/yourusername/gmr-fireworks-store.git
    cd gmr-fireworks-store
    ```

2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Firebase Configuration**:
    *   This app requires a Firebase project.
    *   Place your `serviceAccountKey.json` file in the root directory.
    *   Update `firebase_config.py` with your Storage Bucket URL if necessary.

4.  **Run the Application**:
    ```bash
    streamlit run app.py
    ```

## ⚠️ Data Privacy Note

This repository does **not** contain sensitive credentials (`serviceAccountKey.json`, `.env`, or secrets). Ensure you configure these securely in your deployment environment.

---
© 2024 GMR Fireworks. All Rights Reserved.
