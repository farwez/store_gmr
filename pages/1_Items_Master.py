import streamlit as st
import pandas as pd
from firebase_config import db
from utils import inject_custom_css, render_sidebar, clear_items_cache, check_auth, get_ist_time

st.set_page_config(page_title="Items Master", layout="wide", initial_sidebar_state="expanded", page_icon="📦")
inject_custom_css()
check_auth()
render_sidebar()

st.title("📦 Items Master")
st.caption("Manage your product catalog — add, edit, and monitor all stock in one place.")

# ═══════════════════════════════════════════════════════════════
# FETCH ITEMS (live, not cached, so stock is always fresh here)
# ═══════════════════════════════════════════════════════════════
@st.cache_data(ttl=30)
def load_items():
    docs = db.collection("items_master").stream()
    rows = []
    for d in docs:
        data = d.to_dict()
        rows.append({
            "id": d.id,
            "name": data.get("name", ""),
            "price": data.get("price", 0.0),
            "cost_price": data.get("cost_price", 0.0),
            "stock": data.get("stock", 0),
            "barcode": data.get("barcode", ""),
            "qty_per_box": data.get("qty_per_box", 0),
        })
    rows.sort(key=lambda x: x["name"].lower())
    return rows

@st.cache_data(ttl=60)
def fetch_stock_entries(limit=300):
    docs = (
        db.collection("stock_entries")
        .order_by("timestamp", direction="DESCENDING")
        .limit(limit)
        .stream()
    )
    rows = []
    for d in docs:
        data = d.to_dict()
        rows.append({
            "date": data.get("date", ""),
            "item_name": data.get("item_name", ""),
            "boxes": int(data.get("boxes", 0) or 0),
            "qty_per_box": int(data.get("qty_per_box", 0) or 0),
            "qty_added": int(data.get("qty_added", 0) or 0),
            "previous_stock": int(data.get("previous_stock", 0) or 0),
            "new_stock": int(data.get("new_stock", 0) or 0),
            "cost_price": float(data.get("cost_price", 0) or 0),
            "selling_price": float(data.get("selling_price", 0) or 0),
            "entry_type": data.get("entry_type", "bulk_stock_entry"),
            "created_by": data.get("created_by", ""),
            "notes": data.get("notes", ""),
        })
    return rows

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "➕ Add Item",
    "📥 Bulk Stock Entry",
    "📋 Manage Items",
    "🧾 Stock Entry History",
    "📊 Inventory Summary"
])

# ═══════════════════════════════════════════════════════════════
# TAB 1 — ADD ITEM
# ═══════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Add New Product to Catalog")
    with st.form("add_item_form", clear_on_submit=True, enter_to_submit=False):
        fa1, fa2 = st.columns(2)
        with fa1:
            new_name  = st.text_input("Product Name *", placeholder="e.g. 2.5 Inch Shell")
            new_cost  = st.number_input("Purchase / Cost Price (₹)", min_value=0.0, step=5.0, format="%.2f")
            new_boxes = st.number_input("Cotton Boxes", min_value=0, step=1, value=0)
        with fa2:
            new_price = st.number_input("Selling Price (₹) *", min_value=0.0, step=5.0, format="%.2f")
            new_qty_per_box = st.number_input("Quantity per Box", min_value=0, step=1, value=0)

        opening_stock = int(new_boxes) * int(new_qty_per_box)
        st.caption(f"Opening Stock (auto): **{opening_stock} units**")

        new_barcode = st.text_input("Barcode / SKU (Optional)", placeholder="Scan or type manually")

        if new_price > 0 and new_cost > 0:
            margin = ((new_price - new_cost) / new_price) * 100
            st.caption(f"💡 Estimated Margin: **{margin:.1f}%** | Profit per unit: ₹{new_price - new_cost:.2f}")

        submitted = st.form_submit_button("➕ Add to Catalog", type="primary", use_container_width=True)

        if submitted:
            if not new_name.strip():
                st.error("Product name is required.")
            elif new_price <= 0:
                st.error("Selling price must be greater than ₹0.")
            else:
                try:
                    doc_ref = db.collection("items_master").document()
                    doc_ref.set({
                        "name":       new_name.strip(),
                        "price":      new_price,
                        "cost_price": new_cost,
                        "stock":      opening_stock,
                        "qty_per_box": int(new_qty_per_box),
                        "barcode":    new_barcode.strip(),
                        "created_at": get_ist_time(),
                    })

                    db.collection("stock_entries").add({
                        "date": get_ist_time().strftime("%Y-%m-%d"),
                        "timestamp": get_ist_time(),
                        "item_id": doc_ref.id,
                        "item_name": new_name.strip(),
                        "boxes": int(new_boxes),
                        "qty_per_box": int(new_qty_per_box),
                        "qty_added": opening_stock,
                        "previous_stock": 0,
                        "new_stock": opening_stock,
                        "cost_price": float(new_cost),
                        "selling_price": float(new_price),
                        "entry_type": "new_item_opening_stock",
                        "created_by": st.session_state.get("username", ""),
                        "notes": "Opening stock entry",
                    })

                    clear_items_cache()
                    load_items.clear()
                    fetch_stock_entries.clear()
                    st.success(f"✅ '{new_name}' added to catalog!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

# ═══════════════════════════════════════════════════════════════
# TAB 2 — BULK STOCK ENTRY
# ═══════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Bulk Stock Entry (Cotton Boxes)")

    try:
        items = load_items()
        if not items:
            st.info("No products yet. Add an item first.")
        else:
            with st.form("bulk_stock_entry_form", clear_on_submit=True, enter_to_submit=False):
                all_names = [it["name"] for it in items]
                selected_item_name = st.selectbox("Select Product *", all_names)
                selected_item = next((it for it in items if it["name"] == selected_item_name), None)

                sb1, sb2 = st.columns(2)
                with sb1:
                    boxes = st.number_input("How many cotton boxes?", min_value=1, step=1, value=1)
                    cp = st.number_input(
                        "Cost Price (₹)",
                        min_value=0.0,
                        step=5.0,
                        format="%.2f",
                        value=float(selected_item.get("cost_price", 0.0)) if selected_item else 0.0,
                    )
                with sb2:
                    default_qpb = int(selected_item.get("qty_per_box", 0)) if selected_item else 0
                    qty_per_box = st.number_input("Quantity inside each box", min_value=1, step=1, value=max(1, default_qpb))
                    sp = st.number_input(
                        "Selling Price (₹)",
                        min_value=0.0,
                        step=5.0,
                        format="%.2f",
                        value=float(selected_item.get("price", 0.0)) if selected_item else 0.0,
                    )

                qty_added = int(boxes) * int(qty_per_box)
                current_stock = int(selected_item.get("stock", 0)) if selected_item else 0
                new_stock = current_stock + qty_added
                st.caption(f"Current: **{current_stock}** | Added: **{qty_added}** | New Stock: **{new_stock}**")

                notes = st.text_input("Notes (Optional)", placeholder="Supplier, bill no, etc.")
                submitted_stock = st.form_submit_button("📥 Save Stock Entry", type="primary", use_container_width=True)

                if submitted_stock and selected_item:
                    try:
                        db.collection("items_master").document(selected_item["id"]).update({
                            "stock": new_stock,
                            "cost_price": float(cp),
                            "price": float(sp),
                            "qty_per_box": int(qty_per_box),
                            "updated_at": get_ist_time(),
                        })

                        db.collection("stock_entries").add({
                            "date": get_ist_time().strftime("%Y-%m-%d"),
                            "timestamp": get_ist_time(),
                            "item_id": selected_item["id"],
                            "item_name": selected_item["name"],
                            "boxes": int(boxes),
                            "qty_per_box": int(qty_per_box),
                            "qty_added": qty_added,
                            "previous_stock": current_stock,
                            "new_stock": new_stock,
                            "cost_price": float(cp),
                            "selling_price": float(sp),
                            "entry_type": "bulk_stock_entry",
                            "created_by": st.session_state.get("username", ""),
                            "notes": notes.strip(),
                        })

                        clear_items_cache()
                        load_items.clear()
                        fetch_stock_entries.clear()
                        st.success(f"✅ Stock updated for '{selected_item['name']}'. Added {qty_added} units.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
    except Exception as e:
        st.error(f"Error: {e}")

# ═══════════════════════════════════════════════════════════════
# TAB 3 — MANAGE ITEMS
# ═══════════════════════════════════════════════════════════════
with tab3:
    st.subheader("All Products")

    try:
        items = load_items()

        if not items:
            st.info("No products yet. Go to **Add Item** to get started.")
        else:
            # Search & filter
            sf1, sf2, sf3 = st.columns([3, 1, 1])
            with sf1:
                q = st.text_input("🔍 Search", placeholder="Type product name…")
            with sf2:
                filter_stock = st.selectbox("Stock Filter", ["All", "In Stock", "Low Stock (≤5)", "Out of Stock (0)"])
            with sf3:
                st.write(f"**{len(items)} products**")

            filtered = items
            if q:
                filtered = [i for i in filtered if q.lower() in i["name"].lower() or q in i["barcode"]]
            if filter_stock == "In Stock":
                filtered = [i for i in filtered if i["stock"] > 5]
            elif filter_stock == "Low Stock (≤5)":
                filtered = [i for i in filtered if 0 < i["stock"] <= 5]
            elif filter_stock == "Out of Stock (0)":
                filtered = [i for i in filtered if i["stock"] == 0]

            if not filtered:
                st.warning("No items match.")
            else:
                for item in filtered:
                    stk = item["stock"]
                    stk_color = "#dc2626" if stk == 0 else "#ea580c" if stk <= 5 else "#16a34a"
                    stk_badge = f"<span style='background:{stk_color};color:white;padding:2px 10px;border-radius:20px;font-size:13px;font-weight:600;'>{stk} in stock</span>"
                    margin_pct = ((item["price"] - item["cost_price"]) / item["price"] * 100) if item["price"] > 0 else 0

                    with st.container(border=True):
                        hd, act = st.columns([4, 1.5])
                        with hd:
                            st.markdown(f"**{item['name']}** &nbsp; {stk_badge}", unsafe_allow_html=True)
                            st.caption(f"Sell: ₹{item['price']:,.2f}  |  Cost: ₹{item['cost_price']:,.2f}  |  Margin: {margin_pct:.1f}%  {('| SKU: ' + item['barcode']) if item['barcode'] else ''}")
                        with act:
                            edit_key = f"edit_{item['id']}"
                            del_key  = f"del_{item['id']}"
                            ea, da = st.columns(2)
                            if ea.button("✏️", key=f"e_{item['id']}", use_container_width=True):
                                st.session_state[edit_key] = not st.session_state.get(edit_key, False)
                            if da.button("🗑️", key=f"d_{item['id']}", use_container_width=True):
                                st.session_state[del_key] = True

                        # EDIT FORM (inline)
                        if st.session_state.get(edit_key, False):
                            with st.form(f"ef_{item['id']}", enter_to_submit=False):
                                st.markdown(f"**Edit: {item['name']}**")
                                ec1, ec2, ec3, ec4 = st.columns(4)
                                en  = ec1.text_input("Name", value=item["name"])
                                ep  = ec2.number_input("Sell Price (₹)", value=float(item["price"]), format="%.2f")
                                eco = ec3.number_input("Cost (₹)", value=float(item["cost_price"]), format="%.2f")
                                es  = ec4.number_input("Stock", value=int(item["stock"]))
                                eb  = st.text_input("Barcode/SKU", value=item["barcode"])
                                us, cn = st.columns(2)
                                if us.form_submit_button("✅ Update", use_container_width=True, type="primary"):
                                    db.collection("items_master").document(item["id"]).update({
                                        "name": en.strip(), "price": ep, "cost_price": eco,
                                        "stock": es, "barcode": eb.strip()
                                    })
                                    clear_items_cache()
                                    load_items.clear()
                                    del st.session_state[edit_key]
                                    st.rerun()
                                if cn.form_submit_button("Cancel", use_container_width=True):
                                    del st.session_state[edit_key]
                                    st.rerun()

                        # DELETE CONFIRM
                        if st.session_state.get(del_key, False):
                            st.warning(f"⚠️ Delete **{item['name']}**? This cannot be undone.")
                            dy, dn = st.columns(2)
                            if dy.button("Yes, Delete", key=f"dy_{item['id']}", type="primary"):
                                db.collection("items_master").document(item["id"]).delete()
                                clear_items_cache()
                                load_items.clear()
                                del st.session_state[del_key]
                                st.rerun()
                            if dn.button("Cancel", key=f"dn_{item['id']}"):
                                del st.session_state[del_key]
                                st.rerun()

    except Exception as e:
        st.error(f"Error: {e}")

# ═══════════════════════════════════════════════════════════════
# TAB 4 — STOCK ENTRY HISTORY
# ═══════════════════════════════════════════════════════════════
with tab4:
    st.subheader("🧾 Stock Entry History")
    try:
        entries = fetch_stock_entries()
        if not entries:
            st.info("No stock entries yet.")
        else:
            df = pd.DataFrame(entries)
            df["date_obj"] = pd.to_datetime(df["date"], errors="coerce").dt.date

            min_date = df["date_obj"].min()
            max_date = df["date_obj"].max()

            f1, f2, f3 = st.columns([1.2, 1, 1])
            with f1:
                view_mode = st.selectbox("View", ["All", "Date Wise", "Date Range"])
            with f2:
                selected_date = st.date_input(
                    "Date",
                    value=max_date if max_date else None,
                    min_value=min_date if min_date else None,
                    max_value=max_date if max_date else None,
                    disabled=(view_mode != "Date Wise"),
                )
            with f3:
                date_range = st.date_input(
                    "Range",
                    value=(min_date, max_date) if min_date and max_date else (),
                    min_value=min_date if min_date else None,
                    max_value=max_date if max_date else None,
                    disabled=(view_mode != "Date Range"),
                )

            filtered_df = df.copy()
            if view_mode == "Date Wise" and selected_date:
                filtered_df = filtered_df[filtered_df["date_obj"] == selected_date]
            elif view_mode == "Date Range" and isinstance(date_range, tuple) and len(date_range) == 2:
                start_date, end_date = date_range
                filtered_df = filtered_df[
                    (filtered_df["date_obj"] >= start_date) & (filtered_df["date_obj"] <= end_date)
                ]

            if filtered_df.empty:
                st.warning("No stock entries for selected date filter.")
                st.stop()

            hm1, hm2 = st.columns(2)
            hm1.metric("Total Boxes Entered", int(filtered_df["boxes"].sum()))
            hm2.metric("Total Units Added", int(filtered_df["qty_added"].sum()))

            display_df = filtered_df[
                [
                    "date",
                    "item_name",
                    "boxes",
                    "qty_per_box",
                    "qty_added",
                    "previous_stock",
                    "new_stock",
                    "cost_price",
                    "selling_price",
                    "entry_type",
                    "created_by",
                    "notes",
                ]
            ].copy()
            display_df.columns = [
                "Date",
                "Item",
                "Boxes",
                "Qty/Box",
                "Qty Added",
                "Old Stock",
                "New Stock",
                "CP (₹)",
                "SP (₹)",
                "Type",
                "By",
                "Notes",
            ]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error: {e}")

# ═══════════════════════════════════════════════════════════════
# TAB 5 — INVENTORY SUMMARY
# ═══════════════════════════════════════════════════════════════
with tab5:
    st.subheader("📊 Inventory Valuation Summary")
    try:
        items = load_items()
        if not items:
            st.info("No products.")
        else:
            df = pd.DataFrame(items)
            df["Stock Value (₹)"] = df["cost_price"] * df["stock"]
            df["MRP Value (₹)"]   = df["price"] * df["stock"]
            df["Margin (%)"]      = ((df["price"] - df["cost_price"]) / df["price"].replace(0, 1) * 100).round(1)
            df["Status"]          = df["stock"].apply(lambda x: "❌ Out" if x == 0 else "⚠️ Low" if x <= 5 else "✅ OK")

            sv1, sv2, sv3 = st.columns(3)
            sv1.metric("Total Stock Value (Cost)", f"₹{df['Stock Value (₹)'].sum():,.0f}")
            sv2.metric("Total MRP Value", f"₹{df['MRP Value (₹)'].sum():,.0f}")
            sv3.metric("Potential Gross Profit", f"₹{(df['MRP Value (₹)'].sum() - df['Stock Value (₹)'].sum()):,.0f}")

            st.dataframe(
                df[["name", "stock", "cost_price", "price", "Stock Value (₹)", "Margin (%)", "Status"]].rename(columns={
                    "name": "Product", "stock": "Qty", "cost_price": "Cost (₹)", "price": "Sell (₹)"
                }),
                use_container_width=True, hide_index=True
            )
    except Exception as e:
        st.error(f"Error: {e}")
