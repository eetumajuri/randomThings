import json
import os
import shutil
import stat
import tkinter as tk
from collections import deque
from datetime import date, datetime
from tkinter import ttk, messagebox, simpledialog

FILE_PATH = "orders.json"
BACKUP_PATH = "orders_backup.json"
LOG_PATH = "orders_audit.log"

STATUSES = ["pending", "processing", "shipped", "completed", "cancelled"]

MAX_ITEMS_PER_ORDER = 20
MAX_ITEM_NAME_LENGTH = 60
MAX_PRICE = 1_000_000.0
HISTORY_LIMIT = 20  # how many undo steps to keep


# ---------- Audit log ----------

def log_action(action: str):
    """Append a timestamped line to the audit log. Never raises to the caller."""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} | {action}\n")
    except OSError:
        pass  # logging must never crash the app


# ---------- Secure, atomic data layer ----------

def _secure_permissions(path):
    """Restrict the file to owner read/write only. No-op if unsupported (e.g. Windows)."""
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, NotImplementedError):
        pass


def load_orders():
    if not os.path.exists(FILE_PATH):
        return []
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # Main file is corrupted or unreadable — try to recover from backup.
        if os.path.exists(BACKUP_PATH):
            try:
                with open(BACKUP_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                log_action("RECOVERY: orders.json was corrupted, restored from backup")
                return data
            except (json.JSONDecodeError, OSError):
                pass
        log_action("ERROR: orders.json corrupted and no valid backup found")
        raise RuntimeError(
            "orders.json is corrupted and no valid backup could be recovered. "
            "Check orders_audit.log for details."
        )


def save_orders(orders):
    """Atomic write: write to a temp file, then replace the real file.
    Also keeps a rolling backup of the last known-good state."""
    tmp_path = FILE_PATH + ".tmp"

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(orders, f, indent=4)

    # Back up the current good file before overwriting it.
    if os.path.exists(FILE_PATH):
        try:
            shutil.copyfile(FILE_PATH, BACKUP_PATH)
            _secure_permissions(BACKUP_PATH)
        except OSError:
            pass

    os.replace(tmp_path, FILE_PATH)
    _secure_permissions(FILE_PATH)


# ---------- Validation ----------

class ValidationError(ValueError):
    pass


def validate_items(raw_items):
    """raw_items: list of strings. Returns cleaned list or raises ValidationError."""
    cleaned = [i.strip() for i in raw_items if i.strip()]

    if not cleaned:
        raise ValidationError("Order must contain at least one item.")
    if len(cleaned) > MAX_ITEMS_PER_ORDER:
        raise ValidationError(f"An order can have at most {MAX_ITEMS_PER_ORDER} items.")
    for item in cleaned:
        if len(item) > MAX_ITEM_NAME_LENGTH:
            raise ValidationError(
                f"Item name too long (max {MAX_ITEM_NAME_LENGTH} characters): '{item[:20]}...'"
            )
    return cleaned


def validate_price(raw_price):
    try:
        price = float(raw_price)
    except (TypeError, ValueError):
        raise ValidationError("Price must be a number.")

    if price <= 0:
        raise ValidationError("Price must be greater than zero.")
    if price > MAX_PRICE:
        raise ValidationError(f"Price seems unrealistic (max {MAX_PRICE:,.2f}).")

    return round(price, 2)


def validate_status(raw_status):
    status = (raw_status or "").strip().lower()
    if status not in STATUSES:
        raise ValidationError(f"Status must be one of: {', '.join(STATUSES)}")
    return status


def validate_order_id(orders, raw_id):
    try:
        order_id = int(raw_id)
    except (TypeError, ValueError):
        raise ValidationError("Order ID must be a whole number.")
    if not any(o["id"] == order_id for o in orders):
        raise ValidationError(f"No order found with ID {order_id}.")
    return order_id


# ---------- Order operations (validated + logged) ----------

def add_order(items, price, status="pending"):
    orders = load_orders()
    clean_items = validate_items(items)
    clean_price = validate_price(price)
    clean_status = validate_status(status)

    new_id = max((o["id"] for o in orders), default=0) + 1
    new_order = {
        "id": new_id,
        "items": clean_items,
        "price": clean_price,
        "status": clean_status,
        "date": str(date.today()),
    }
    orders.append(new_order)
    save_orders(orders)
    log_action(f"ADD order #{new_id}: {clean_items} @ {clean_price:.2f}")
    return new_order


def update_status(order_id, new_status):
    orders = load_orders()
    clean_status = validate_status(new_status)
    order_id = validate_order_id(orders, order_id)

    for order in orders:
        if order["id"] == order_id:
            old_status = order["status"]
            order["status"] = clean_status
            save_orders(orders)
            log_action(f"UPDATE order #{order_id}: status {old_status} -> {clean_status}")
            return True
    return False


def delete_order(order_id):
    orders = load_orders()
    order_id = validate_order_id(orders, order_id)

    new_orders = [o for o in orders if o["id"] != order_id]
    save_orders(new_orders)
    log_action(f"DELETE order #{order_id}")
    return True


def get_orders_by_status(status):
    return [o for o in load_orders() if o["status"] == status]


# ---------- GUI ----------

class OrderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Order Manager")
        self.geometry("850x520")

        # Undo history: list of (description, full_orders_snapshot) taken
        # BEFORE each mutating action.
        self.history = deque(maxlen=HISTORY_LIMIT)

        self._build_toolbar()
        self._build_table()
        self._build_statusbar()
        self.refresh_table()

    # -- layout --

    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=8)
        bar.pack(side="top", fill="x")

        ttk.Button(bar, text="Add Order", command=self.open_add_dialog).pack(side="left", padx=4)
        ttk.Button(bar, text="Update Status", command=self.open_update_dialog).pack(side="left", padx=4)
        ttk.Button(bar, text="Delete Order", command=self.delete_selected).pack(side="left", padx=4)
        self.undo_btn = ttk.Button(bar, text="Undo", command=self.undo_last)
        self.undo_btn.pack(side="left", padx=4)
        ttk.Button(bar, text="Refresh", command=self.refresh_table).pack(side="left", padx=4)

        ttk.Label(bar, text="Filter by status:").pack(side="left", padx=(20, 4))
        self.status_filter = tk.StringVar(value="all")
        filter_box = ttk.Combobox(
            bar, textvariable=self.status_filter,
            values=["all"] + STATUSES, width=12, state="readonly"
        )
        filter_box.pack(side="left")
        filter_box.bind("<<ComboboxSelected>>", lambda e: self.refresh_table())

        self._update_undo_button_state()

    def _build_table(self):
        columns = ("id", "items", "price", "status", "date")
        self.tree = ttk.Treeview(self, columns=columns, show="headings")

        headings = {"id": "ID", "items": "Items", "price": "Price", "status": "Status", "date": "Date"}
        widths = {"id": 50, "items": 340, "price": 80, "status": 100, "date": 100}

        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="w")

        self.tree.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_statusbar(self):
        self.status_var = tk.StringVar(value="Ready.")
        bar = ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w", padding=4)
        bar.pack(side="bottom", fill="x")

    def set_status(self, text):
        self.status_var.set(text)

    # -- undo helpers --

    def _snapshot_before_change(self, description):
        """Call this right before a mutating action so it can be undone."""
        try:
            current = load_orders()
        except RuntimeError:
            current = []
        self.history.append((description, current))
        self._update_undo_button_state()

    def _update_undo_button_state(self):
        self.undo_btn.config(state="normal" if self.history else "disabled")

    def undo_last(self):
        if not self.history:
            return
        description, snapshot = self.history.pop()
        try:
            save_orders(snapshot)
            log_action(f"UNDO: reverted '{description}'")
            self.refresh_table()
            self.set_status(f"Undid: {description}")
        except OSError as e:
            messagebox.showerror("Undo failed", str(e))
        self._update_undo_button_state()

    # -- data refresh --

    def refresh_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        try:
            status = self.status_filter.get()
            orders = get_orders_by_status(status) if status != "all" else load_orders()
        except RuntimeError as e:
            messagebox.showerror("Data error", str(e))
            return

        for o in orders:
            self.tree.insert("", "end", values=(
                o["id"], ", ".join(o["items"]), f"{o['price']:.2f}", o["status"], o["date"],
            ))
        self.set_status(f"{len(orders)} order(s) shown.")

    def get_selected_id(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("No selection", "Please select an order first.")
            return None
        values = self.tree.item(selection[0], "values")
        return int(values[0])

    # -- actions --

    def open_add_dialog(self):
        items_str = simpledialog.askstring("Add Order", "Enter items (comma-separated):")
        if items_str is None:
            return
        price_str = simpledialog.askstring("Add Order", "Enter price:")
        if price_str is None:
            return

        try:
            self._snapshot_before_change("Add order")
            new_order = add_order(items_str.split(","), price_str)
        except ValidationError as e:
            self.history.pop()  # nothing actually changed, drop the snapshot
            self._update_undo_button_state()
            messagebox.showerror("Invalid input", str(e))
            return

        self.refresh_table()
        self.set_status(f"Added order #{new_order['id']}.")

    def open_update_dialog(self):
        order_id = self.get_selected_id()
        if order_id is None:
            return

        new_status = simpledialog.askstring("Update Status", f"Enter new status {STATUSES}:")
        if new_status is None:
            return

        try:
            self._snapshot_before_change(f"Update order #{order_id}")
            update_status(order_id, new_status)
        except ValidationError as e:
            self.history.pop()
            self._update_undo_button_state()
            messagebox.showerror("Invalid input", str(e))
            return

        self.refresh_table()
        self.set_status(f"Updated order #{order_id}.")

    def delete_selected(self):
        order_id = self.get_selected_id()
        if order_id is None:
            return

        confirm = messagebox.askyesno(
            "Confirm delete",
            f"Delete order #{order_id}? You can reverse this with Undo right after."
        )
        if not confirm:
            return

        try:
            self._snapshot_before_change(f"Delete order #{order_id}")
            delete_order(order_id)
        except ValidationError as e:
            self.history.pop()
            self._update_undo_button_state()
            messagebox.showerror("Invalid input", str(e))
            return

        self.refresh_table()
        self.set_status(f"Deleted order #{order_id}.")


if __name__ == "__main__":
    app = OrderApp()
    app.mainloop()
