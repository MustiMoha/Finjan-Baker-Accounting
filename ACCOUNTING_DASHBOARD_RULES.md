# Accounting Dashboard Rules

- Tech Stack: Python (Streamlit), Supabase (Auth/DB), Google Drive API (Drive/Sheets), openpyxl.
- Financial Logic: Enforce double-entry (Debits = Credits). Support custom fiscal years.
- Excel Handling: NEVER use pandas to save the master .xlsm file. ONLY use openpyxl with `keep_vba=True` to preserve macros and formatting.
- Role-Based Access: Check `user_roles` table in Supabase for 'admin', 'staff', or 'auditor' before rendering page content.
- Visualization: Use Plotly with JavaScript event listeners for drill-down capabilities.
