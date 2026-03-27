import streamlit as st
from firebase_config import db, firestore_module
from datetime import datetime, timedelta
import pandas as pd
from utils import inject_custom_css, render_sidebar, check_auth, get_ist_time, clear_items_cache, clear_dashboard_cache, get_all_items

st.set_page_config(page_title="Returns & Exchanges", layout="wide", initial_sidebar_state="expanded", page_icon="↩️")
inject_custom_css()
check_auth()
render_sidebar()

st.title("🔄 Returns & Exchanges")
st.caption("Process refunds or exchanges. Stock is automatically restored when a return is approved.")
st.markdown("---")

tab1, tab2 = st.tabs(["🔙 Process Return", "📋 Return History"])

# ── Pre-load from Sales History page ──────────────────────────────────────
if "selected_sale_for_return" in st.session_state:
    raw = st.session_state.pop("selected_sale_for_return")
    st.session_state["return_sale"] = {
        "id":       raw.get("id"),
        "customer": raw.get("Customer", ""),
        "phone":    raw.get("Phone", ""),
        "total":    raw.get("Total", 0),
        "subtotal": raw.get("Subtotal", 0),
        "discount_amount": raw.get("Discount", 0),
        "discount_type": raw.get("Dis_type", "No Discount"),
        "items":    raw.get("raw_items", []),
        "date":     raw.get("Date", ""),
    }

# ══════════════════════════════════════════════════════════
# TAB 1 — PROCESS RETURN
# ══════════════════════════════════════════════════════════
with tab1:
    st.subheader("Step 1 — Find Original Sale")

    with st.container(border=True):
        sc1, sc2, sc3 = st.columns([2, 2, 1])
        with sc1:
            s_date = st.date_input("Sale Date", value=get_ist_time().date())
        with sc2:
            s_cust = st.text_input("Customer Name (optional)", placeholder="Leave blank to see all sales for that day")
        with sc3:
            st.write("")
            st.write("")
            do_search = st.button("🔍 Search", type="primary", use_container_width=True)

    if do_search:
        try:
            s_str = s_date.strftime("%Y-%m-%d")
            docs  = db.collection("sales").where("date", "==", s_str).stream()
            results = []
            for d in docs:
                dd = d.to_dict()
                if dd.get("voided", False):
                    continue
                cname = dd.get("customer_name", "")
                if s_cust and s_cust.lower() not in cname.lower():
                    continue
                results.append({
                    "id":       d.id,
                    "customer": cname,
                    "phone":    dd.get("customer_phone", ""),
                    "total":    dd.get("total", 0),
                    "subtotal": dd.get("subtotal", 0),
                    "discount_amount": dd.get("discount_amount", 0),
                    "discount_type": dd.get("discount_type", "No Discount"),
                    "items":    dd.get("items", []),
                    "date":     dd.get("date", s_str),
                })
            st.session_state["return_results"] = results
            if not results:
                st.warning("No sales found. Try a different date or name.")
        except Exception as e:
            st.error(f"Search failed: {e}")

    # Show search results
    if "return_results" in st.session_state and not st.session_state.get("return_sale"):
        results = st.session_state["return_results"]
        st.markdown(f"**{len(results)} sale(s) found — select one to continue:**")
        for i, s in enumerate(results):
            items_summary = ", ".join(f"{it['name']} x{it['qty']}" for it in s["items"])
            with st.expander(f"{'🧾'} #{i+1} — {s['customer']} — ₹{s['total']:,.2f} — {items_summary[:60]}…"):
                st.write(f"**Customer:** {s['customer']}  |  **Date:** {s['date']}  |  **Total:** ₹{s['total']:,.2f}")
                if st.button("Select this Sale →", key=f"pick_{s['id']}", type="primary"):
                    st.session_state["return_sale"] = s
                    del st.session_state["return_results"]
                    st.rerun()

    # Process the selected sale
    if "return_sale" in st.session_state:
        sale = st.session_state["return_sale"]
        st.success(f"**Selected:** {sale['customer']} | Sale Date: {sale['date']} | Total: ₹{sale['total']:,.2f}")

        if st.button("✖ Clear / Search Again"):
            del st.session_state["return_sale"]
            st.session_state.pop("return_results", None)
            st.session_state.pop(f"exchange_cart_{sale['id']}", None)
            st.rerun()

        st.divider()
        st.subheader("Step 2 — Select Items to Return")

        if not sale["items"]:
            st.warning("This sale has no items recorded.")
        else:
            return_items = []

            for idx, item in enumerate(sale["items"]):
                sold_qty = item.get("qty", 0)
                price    = item.get("price", 0)
                cost     = item.get("cost", 0)

                with st.container(border=True):
                    ri1, ri2, ri3 = st.columns([4, 2, 2])
                    with ri1:
                        st.markdown(f"**{item.get('name', '?')}**")
                        st.caption(f"Sold: {sold_qty} unit(s) @ ₹{price:,.2f} each")
                    with ri2:
                        ret_qty = st.number_input(
                            "Qty to Return", min_value=0, max_value=sold_qty, value=0,
                            key=f"rq_{idx}_{item.get('id', idx)}"
                        )
                    with ri3:
                        if ret_qty > 0:
                            st.metric("Line Refund", f"₹{ret_qty * price:,.2f}")
                            return_items.append({
                                "id":    item.get("id"),
                                "name":  item.get("name", "?"),
                                "qty":   ret_qty,
                                "price": price,
                                "cost":  cost,
                            })

            if return_items:
                return_subtotal = sum(i["qty"] * i["price"] for i in return_items)
                sale_subtotal = max(float(sale.get("subtotal", 0) or 0), 0.0)
                sale_discount = max(float(sale.get("discount_amount", 0) or 0), 0.0)
                return_discount = round(min(sale_discount, (return_subtotal / sale_subtotal) * sale_discount), 2) if sale_subtotal > 0 else 0.0
                total_refund = round(max(0.0, return_subtotal - return_discount), 2)
                exchange_cart_key = f"exchange_cart_{sale['id']}"
                if exchange_cart_key not in st.session_state:
                    st.session_state[exchange_cart_key] = []
                st.divider()
                st.subheader("Step 3 — Confirm Return")

                with st.container(border=True):
                    rd1, rd2 = st.columns(2)
                    with rd1:
                        ret_reason = st.text_area("Reason for Return *", placeholder="e.g. Defective product, wrong item dispatched…")
                        ret_type   = st.radio("Action", ["💸 Refund Cash/UPI", "🔄 Exchange for another item"], horizontal=True)
                    with rd2:
                        st.metric("Items Being Returned", sum(i["qty"] for i in return_items))
                        st.metric("Total Refund Amount", f"₹{total_refund:,.2f}")
                        if return_discount > 0:
                            st.caption(f"Refund adjusted for existing sale discount: -₹{return_discount:,.2f}")
                        st.caption("Stock will be added back to inventory automatically.")

                    exchange_items = st.session_state.get(exchange_cart_key, [])
                    exchange_subtotal = round(sum(i.get("qty", 0) * i.get("price", 0) for i in exchange_items), 2)
                    settlement_amount = round(exchange_subtotal - total_refund, 2)

                    if ret_type == "🔄 Exchange for another item":
                        st.divider()
                        st.subheader("Step 4 — Select Exchange Items")
                        try:
                            items_master = get_all_items()
                            if not items_master:
                                st.warning("No products available in inventory for exchange.")
                            else:
                                ex1, ex2, ex3 = st.columns([4, 1, 1])
                                with ex1:
                                    exchange_opts = ["— Select a product —"] + list(items_master.keys())

                                    def fmt_exchange(x):
                                        if x == "— Select a product —":
                                            return x
                                        it = items_master[x]
                                        return f"{it.get('name', x)} | Stock: {it.get('stock', 0)} | ₹{it.get('price', 0):,.2f}"

                                    exchange_selected_id = st.selectbox(
                                        "Exchange Product",
                                        exchange_opts,
                                        format_func=fmt_exchange,
                                        key=f"exchange_product_{sale['id']}"
                                    )
                                with ex2:
                                    exchange_qty = st.number_input(
                                        "Qty",
                                        min_value=1,
                                        value=1,
                                        step=1,
                                        key=f"exchange_qty_{sale['id']}"
                                    )
                                with ex3:
                                    st.write("")
                                    st.write("")
                                    add_exchange_item = st.button("➕ Add", key=f"add_exchange_item_{sale['id']}", type="secondary")

                                if add_exchange_item:
                                    if exchange_selected_id == "— Select a product —":
                                        st.error("Please select an exchange product.")
                                    else:
                                        prod = items_master[exchange_selected_id]
                                        available = int(prod.get("stock", 0) or 0)
                                        already = sum(i.get("qty", 0) for i in exchange_items if i.get("id") == exchange_selected_id)
                                        if available <= 0:
                                            st.error(f"{prod.get('name', 'Item')} is out of stock.")
                                        elif already + exchange_qty > available:
                                            st.error(f"Only {max(0, available - already)} unit(s) available for exchange.")
                                        else:
                                            updated = False
                                            for exi in exchange_items:
                                                if exi.get("id") == exchange_selected_id:
                                                    exi["qty"] += int(exchange_qty)
                                                    updated = True
                                                    break
                                            if not updated:
                                                exchange_items.append({
                                                    "id": exchange_selected_id,
                                                    "name": prod.get("name", exchange_selected_id),
                                                    "qty": int(exchange_qty),
                                                    "price": float(prod.get("price", 0) or 0),
                                                    "cost": float(prod.get("cost_price", 0) or 0),
                                                })
                                            st.session_state[exchange_cart_key] = exchange_items
                                            st.rerun()

                                if exchange_items:
                                    st.markdown("**Exchange Cart**")
                                    for ex_idx, ex_item in enumerate(exchange_items):
                                        exr1, exr2, exr3, exr4 = st.columns([4, 1, 2, 1])
                                        exr1.write(ex_item.get("name", "-"))
                                        exr2.write(f"x{ex_item.get('qty', 0)}")
                                        exr3.write(f"₹{ex_item.get('qty', 0) * ex_item.get('price', 0):,.2f}")
                                        if exr4.button("🗑", key=f"ex_rm_{sale['id']}_{ex_idx}"):
                                            exchange_items.pop(ex_idx)
                                            st.session_state[exchange_cart_key] = exchange_items
                                            st.rerun()

                                exchange_subtotal = round(sum(i.get("qty", 0) * i.get("price", 0) for i in exchange_items), 2)
                                settlement_amount = round(exchange_subtotal - total_refund, 2)
                                sc1, sc2, sc3 = st.columns(3)
                                sc1.metric("Exchange Subtotal", f"₹{exchange_subtotal:,.2f}")
                                if settlement_amount > 0:
                                    sc2.metric("Customer Pays", f"₹{settlement_amount:,.2f}")
                                    sc3.caption("Collect this amount from customer.")
                                elif settlement_amount < 0:
                                    sc2.metric("Refund Balance", f"₹{abs(settlement_amount):,.2f}")
                                    sc3.caption("Return this balance to customer.")
                                else:
                                    sc2.metric("Settlement", "₹0.00")
                                    sc3.caption("No additional amount to collect/refund.")
                        except Exception as ex_err:
                            st.error(f"Failed to load exchange items: {ex_err}")

                    if st.button("✅ Process Return", type="primary", use_container_width=True):
                        if not ret_reason.strip():
                            st.error("Please provide a reason.")
                        elif ret_type == "🔄 Exchange for another item" and not exchange_items:
                            st.error("Add at least one exchange item before processing.")
                        else:
                            try:
                                action_type = "Exchange" if ret_type == "🔄 Exchange for another item" else "Refund"
                                ret_doc = {
                                    "original_sale_id":   sale["id"],
                                    "original_sale_date": sale["date"],
                                    "customer_name":      sale["customer"],
                                    "customer_phone":     sale["phone"],
                                    "return_items":       return_items,
                                    "return_subtotal":    return_subtotal,
                                    "return_discount_amount": return_discount,
                                    "return_amount":      total_refund,
                                    "return_type":        action_type,
                                    "reason":             ret_reason.strip(),
                                    "exchange_items":     exchange_items if action_type == "Exchange" else [],
                                    "exchange_subtotal":  exchange_subtotal if action_type == "Exchange" else 0.0,
                                    "settlement_amount":  settlement_amount if action_type == "Exchange" else (-total_refund),
                                    "date":               get_ist_time().strftime("%Y-%m-%d"),
                                    "timestamp":          get_ist_time(),
                                    "processed_by":       st.session_state.get("username", "Admin"),
                                }

                                exchange_sale_ref = db.collection("sales").document() if action_type == "Exchange" else None

                                @firestore_module.transactional
                                def exec_return(tx, r_ref, r_doc, sale_id, ex_ref=None):
                                    # ── READ PHASE ──
                                    sale_ref  = db.collection("sales").document(sale_id)
                                    sale_snap = sale_ref.get(transaction=tx)
                                    if not sale_snap.exists:
                                        raise ValueError("Original sale not found.")

                                    sd = sale_snap.to_dict()
                                    if sd.get("voided", False):
                                        raise ValueError("Cannot process a return for a voided sale.")

                                    s_items = sd.get("items", [])

                                    live_return_subtotal = 0.0
                                    for ri in r_doc["return_items"]:
                                        matched_item = None
                                        for si in s_items:
                                            same_item = ((si.get("id") and si.get("id") == ri["id"]) or si.get("name") == ri["name"])
                                            if same_item:
                                                matched_item = si
                                                break
                                        if not matched_item:
                                            raise ValueError(f"Item '{ri['name']}' is no longer available for return in this sale.")
                                        current_qty = int(matched_item.get("qty", 0) or 0)
                                        if current_qty < ri["qty"]:
                                            raise ValueError(
                                                f"Return quantity for '{ri['name']}' exceeds remaining sold quantity. "
                                                f"Available: {current_qty}, Requested: {ri['qty']}."
                                            )
                                        live_return_subtotal += ri["qty"] * ri["price"]

                                    live_sale_subtotal = max(float(sd.get("subtotal", 0) or 0), 0.0)
                                    live_sale_discount = max(float(sd.get("discount_amount", 0) or 0), 0.0)
                                    live_return_discount = round(
                                        min(live_sale_discount, (live_return_subtotal / live_sale_subtotal) * live_sale_discount), 2
                                    ) if live_sale_subtotal > 0 else 0.0
                                    live_return_amount = round(max(0.0, live_return_subtotal - live_return_discount), 2)

                                    # Fetch all item docs in one pass
                                    item_snaps = {}
                                    for ri in r_doc["return_items"]:
                                        if ri["id"]:
                                            iref = db.collection("items_master").document(ri["id"])
                                            item_snaps[ri["id"]] = iref.get(transaction=tx)

                                    exchange_snaps = {}
                                    returned_qty_by_item = {}
                                    for ri in r_doc.get("return_items", []):
                                        if ri.get("id"):
                                            returned_qty_by_item[ri["id"]] = returned_qty_by_item.get(ri["id"], 0) + int(ri.get("qty", 0) or 0)

                                    for exi in r_doc.get("exchange_items", []):
                                        ex_id = exi.get("id")
                                        if not ex_id:
                                            raise ValueError("Exchange item id missing.")
                                        ex_ref_item = db.collection("items_master").document(ex_id)
                                        ex_snap = ex_ref_item.get(transaction=tx)
                                        if not ex_snap.exists:
                                            raise ValueError(f"Exchange item '{exi.get('name', ex_id)}' not found.")
                                        current_stock = int(ex_snap.to_dict().get("stock", 0) or 0)
                                        effective_stock = current_stock + returned_qty_by_item.get(ex_id, 0)
                                        if effective_stock < int(exi.get("qty", 0) or 0):
                                            raise ValueError(
                                                f"Insufficient stock for exchange item '{exi.get('name', ex_id)}'. "
                                                f"Available after return: {effective_stock}, Requested: {int(exi.get('qty', 0) or 0)}."
                                            )
                                        exchange_snaps[ex_id] = ex_snap

                                    # ── WRITE PHASE ──
                                    # 1. Restore stock
                                    for ri in r_doc["return_items"]:
                                        iid = ri["id"]
                                        if iid and iid in item_snaps and item_snaps[iid].exists:
                                            cur = item_snaps[iid].to_dict().get("stock", 0)
                                            tx.update(db.collection("items_master").document(iid),
                                                      {"stock": cur + ri["qty"]})

                                    # 1b. Deduct stock for exchange items
                                    for exi in r_doc.get("exchange_items", []):
                                        ex_id = exi.get("id")
                                        if ex_id and ex_id in exchange_snaps and exchange_snaps[ex_id].exists:
                                            base_stock = int(exchange_snaps[ex_id].to_dict().get("stock", 0) or 0)
                                            restored_for_same_item = returned_qty_by_item.get(ex_id, 0)
                                            new_stock = base_stock + restored_for_same_item - int(exi.get("qty", 0) or 0)
                                            tx.update(db.collection("items_master").document(ex_id), {"stock": new_stock})

                                    # 2. Patch original sale document
                                    for ri in r_doc["return_items"]:
                                        for si in s_items:
                                            if (si.get("id") and si["id"] == ri["id"]) or si.get("name") == ri["name"]:
                                                si["qty"] = max(0, si.get("qty", 0) - ri["qty"])
                                    # Remove fully-returned items from the sub-list
                                    new_items     = [i for i in s_items if i.get("qty", 0) > 0]
                                    new_subtotal  = round(max(0.0, live_sale_subtotal - live_return_subtotal), 2)
                                    new_discount  = round(max(0.0, live_sale_discount - live_return_discount), 2)
                                    new_total     = round(max(0.0, float(sd.get("total", 0) or 0) - live_return_amount), 2)
                                    tx.update(sale_ref, {
                                        "items":            new_items,
                                        "total":            new_total,
                                        "subtotal":         new_subtotal,
                                        "discount_amount":  new_discount,
                                        "has_returns":      True,
                                    })

                                    return_record = dict(r_doc)
                                    return_record["return_subtotal"] = round(live_return_subtotal, 2)
                                    return_record["return_discount_amount"] = live_return_discount
                                    return_record["return_amount"] = live_return_amount

                                    # 3. Create return record
                                    exchange_sale_id = None
                                    if ex_ref and r_doc.get("exchange_items"):
                                        exchange_sale_doc = {
                                            "customer_name": sd.get("customer_name", ""),
                                            "customer_phone": sd.get("customer_phone", ""),
                                            "items": r_doc.get("exchange_items", []),
                                            "subtotal": round(sum((i.get("qty", 0) * i.get("price", 0)) for i in r_doc.get("exchange_items", [])), 2),
                                            "discount_type": "Exchange Credit",
                                            "discount_amount": round(live_return_amount, 2),
                                            "total": round(sum((i.get("qty", 0) * i.get("price", 0)) for i in r_doc.get("exchange_items", [])), 2),
                                            "payment_method": "Exchange",
                                            "exchange_reference_sale_id": sale_id,
                                            "exchange_credit_applied": round(live_return_amount, 2),
                                            "exchange_settlement_amount": round(r_doc.get("settlement_amount", 0), 2),
                                            "date": get_ist_time().strftime("%Y-%m-%d"),
                                            "timestamp": get_ist_time(),
                                            "voided": False,
                                        }
                                        tx.create(ex_ref, exchange_sale_doc)
                                        exchange_sale_id = ex_ref.id
                                        return_record["exchange_sale_id"] = exchange_sale_id

                                    tx.create(r_ref, return_record)

                                r_ref = db.collection("returns").document()
                                exec_return(db.transaction(), r_ref, ret_doc, sale["id"], exchange_sale_ref)
                                clear_items_cache()
                                clear_dashboard_cache()

                                if action_type == "Exchange":
                                    if settlement_amount > 0:
                                        st.success(f"✅ Exchange processed! Collect ₹{settlement_amount:,.2f} from customer.")
                                    elif settlement_amount < 0:
                                        st.success(f"✅ Exchange processed! Refund ₹{abs(settlement_amount):,.2f} to customer.")
                                    else:
                                        st.success("✅ Exchange processed successfully with zero settlement.")
                                else:
                                    st.success("✅ Return processed! Stock restored and refund recorded.")
                                st.balloons()
                                del st.session_state["return_sale"]
                                st.session_state.pop("return_results", None)
                                st.session_state.pop(exchange_cart_key, None)
                                st.rerun()

                            except Exception as e:
                                st.error(f"Return failed: {e}")

# ══════════════════════════════════════════════════════════
# TAB 2 — RETURN HISTORY
# ══════════════════════════════════════════════════════════
with tab2:
    st.subheader("📋 Return History")

    with st.container(border=True):
        h1, h2, h3 = st.columns([2, 2, 1])
        with h1: from_dt = st.date_input("From", value=get_ist_time().date() - timedelta(days=30))
        with h2: to_dt   = st.date_input("To",   value=get_ist_time().date())
        with h3:
            st.write("")
            st.write("")
            fetch_hist = st.button("Load History", type="primary", use_container_width=True)

    if fetch_hist:
        try:
            f_str = from_dt.strftime("%Y-%m-%d")
            t_str = to_dt.strftime("%Y-%m-%d")
            # No order_by here to avoid Firestore composite index requirement
            docs  = db.collection("returns").where("date", ">=", f_str).where("date", "<=", t_str).stream()
            rows  = []
            for d in docs:
                dd = d.to_dict()
                items_str = ", ".join(f"{i['name']} ×{i['qty']}" for i in dd.get("return_items", []))
                rows.append({
                    "Date":       dd.get("date"),
                    "Customer":   dd.get("customer_name"),
                    "Items":      items_str,
                    "Refund (₹)": dd.get("return_amount", 0),
                    "Type":       dd.get("return_type", "Refund"),
                    "Reason":     dd.get("reason", ""),
                    "By":         dd.get("processed_by", "Admin"),
                })
            # Sort by date descending in Python
            rows.sort(key=lambda x: x["Date"] or "", reverse=True)

            if rows:
                df = pd.DataFrame(rows)
                st.metric("Total Refunded", f"₹{df['Refund (₹)'].sum():,.2f}", f"{len(df)} return(s)")
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("No returns found in this date range.")
        except Exception as e:
            st.error(f"Error: {e}")
