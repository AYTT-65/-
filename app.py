from pathlib import Path
import os
import sqlite3
import secrets
import json
from functools import wraps
from datetime import datetime
from decimal import Decimal, InvalidOperation
from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "store.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "store-local-secret-key")
app.config["DATABASE"] = DATABASE
app.config["UPLOAD_FOLDER"] = BASE_DIR / "static" / "uploads"
ENDPOINT_PERMISSIONS = {
    "shop": "shop", "store_products": "store_products", "store_offers": "store_offers",
    "store_search": "store_products", "store_category": "store_products", "product_detail": "store_products",
    "cart": "cart", "checkout": "cart", "orders": "orders", "reserve_product": "shop", "account": "account",
    "dashboard": "dashboard", "products": "products", "new_product": "new_product", "edit_product": "products", "delete_product": "products",
    "sales": "sales", "sale_detail": "sales", "reservation_admin": "reservation_admin",
    "update_reservation_status": "reservation_admin", "banners_admin": "banners_admin", "new_banner": "banners_admin", "edit_banner": "banners_admin", "delete_banner": "banners_admin",
}
ADMIN_ENDPOINTS = {
    "dashboard", "products", "new_product", "edit_product", "delete_product",
    "sales", "sale_detail", "reservation_admin", "update_reservation_status",
    "banners_admin", "new_banner", "edit_banner", "delete_banner",
}
INTERFACE_OPTIONS = [
    ("shop", "الرئيسية والمتجر"), ("store_products", "المنتجات"), ("store_offers", "العروض"),
    ("orders", "متابعة الطلبات"), ("cart", "السلة"), ("account", "حسابي"),
    ("dashboard", "لوحة التحكم"), ("products", "إدارة المنتجات"), ("new_product", "إضافة منتج"),
    ("sales", "المبيعات والفواتير"), ("reservation_admin", "إدارة الحجوزات"),
    ("banners_admin", "إدارة الإعلانات"),
]
ORDER_STATUSES = [
    "قيد التدقيق",
    "جاري تجهيز الطلب",
    "تم تسليم الطلب لشركة التوصيل",
    "الطلب في طريقه إليك",
    "وصل المندوب",
    "تم تسليم الطلب",
]
DELIVERY_FEE = 5000
GOVERNORATES = [
    "بغداد", "الأنبار", "بابل", "البصرة", "كربلاء", "النجف", "نينوى",
    "دهوك", "أربيل", "السليمانية", "ديالى", "ذي قار", "صلاح الدين",
    "كركوك", "ميسان", "المثنى", "واسط", "القادسية",
]
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.before_request
def enforce_interface_permissions():
    required = ENDPOINT_PERMISSIONS.get(request.endpoint)
    if not required:
        return None
    if not session.get("customer_name"):
        return redirect(url_for("customer_entry"))
    profile = get_db().execute(
        "SELECT is_admin, permissions, active FROM account_profiles WHERE login_name = ?",
        (session["customer_name"],),
    ).fetchone()
    if not profile:
        session.clear()
        return redirect(url_for("customer_entry"))
    if not profile["active"]:
        session.clear()
        flash("هذا الحساب معطل. تواصل مع المدير.", "error")
        return redirect(url_for("customer_entry"))
    if profile["is_admin"] or request.endpoint not in ADMIN_ENDPOINTS:
        return None
    flash("هذه الصفحة متاحة للمدير فقط.", "error")
    return redirect(url_for("shop"))


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            sku TEXT NOT NULL UNIQUE,
            price REAL NOT NULL DEFAULT 0,
            stock INTEGER NOT NULL DEFAULT 0,
            description TEXT DEFAULT '',
            icon TEXT DEFAULT '📦',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL DEFAULT 'عميل نقدي',
            total REAL NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            FOREIGN KEY(sale_id) REFERENCES sales(id) ON DELETE CASCADE,
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            customer_number TEXT NOT NULL,
            account_code TEXT NOT NULL DEFAULT '',
            customer_address TEXT NOT NULL DEFAULT '',
            governorate TEXT NOT NULL DEFAULT '',
            product_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'جديد',
            order_code TEXT NOT NULL DEFAULT '',
            quantity INTEGER NOT NULL DEFAULT 1,
            total REAL NOT NULL DEFAULT 0,
            stock_deducted INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS banners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            price REAL NOT NULL DEFAULT 0,
            discount REAL NOT NULL DEFAULT 0,
            image TEXT NOT NULL DEFAULT '',
            product_id INTEGER,
            sort_order INTEGER NOT NULL DEFAULT 0,
            duration INTEGER NOT NULL DEFAULT 5,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS account_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login_name TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            account_code TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            permissions TEXT NOT NULL DEFAULT '["shop"]',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        """
    )
    profile_columns = {row[1] for row in db.execute("PRAGMA table_info(account_profiles)").fetchall()}
    if "is_admin" not in profile_columns:
        db.execute("ALTER TABLE account_profiles ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    if "permissions" not in profile_columns:
        db.execute("ALTER TABLE account_profiles ADD COLUMN permissions TEXT NOT NULL DEFAULT '[\"shop\"]'")
    if "active" not in profile_columns:
        db.execute("ALTER TABLE account_profiles ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    columns = {row[1] for row in db.execute("PRAGMA table_info(products)").fetchall()}
    if "image" not in columns:
        db.execute("ALTER TABLE products ADD COLUMN image TEXT DEFAULT ''")
    for column, definition in {
        "old_price": "REAL NOT NULL DEFAULT 0",
        "discount": "REAL NOT NULL DEFAULT 0",
        "specifications": "TEXT DEFAULT ''",
        "visible": "INTEGER NOT NULL DEFAULT 1",
        "featured": "INTEGER NOT NULL DEFAULT 0",
        "advertised": "INTEGER NOT NULL DEFAULT 0",
    }.items():
        if column not in columns:
            db.execute(f"ALTER TABLE products ADD COLUMN {column} {definition}")
    reservation_columns = {row[1] for row in db.execute("PRAGMA table_info(reservations)").fetchall()}
    if "customer_address" not in reservation_columns:
        db.execute("ALTER TABLE reservations ADD COLUMN customer_address TEXT NOT NULL DEFAULT ''")
    if "governorate" not in reservation_columns:
        db.execute("ALTER TABLE reservations ADD COLUMN governorate TEXT NOT NULL DEFAULT ''")
    if "account_code" not in reservation_columns:
        db.execute("ALTER TABLE reservations ADD COLUMN account_code TEXT NOT NULL DEFAULT ''")
    if "order_code" not in reservation_columns:
        db.execute("ALTER TABLE reservations ADD COLUMN order_code TEXT NOT NULL DEFAULT ''")
    if "quantity" not in reservation_columns:
        db.execute("ALTER TABLE reservations ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1")
    if "total" not in reservation_columns:
        db.execute("ALTER TABLE reservations ADD COLUMN total REAL NOT NULL DEFAULT 0")
    if "stock_deducted" not in reservation_columns:
        db.execute("ALTER TABLE reservations ADD COLUMN stock_deducted INTEGER NOT NULL DEFAULT 0")
    if "delivery_fee" not in reservation_columns:
        db.execute("ALTER TABLE reservations ADD COLUMN delivery_fee REAL NOT NULL DEFAULT 5000")
    old_reservations = db.execute(
        "SELECT product_id, SUM(quantity) AS quantity FROM reservations WHERE stock_deducted = 0 GROUP BY product_id"
    ).fetchall()
    if old_reservations:
        db.execute(
            """
            UPDATE products
            SET stock = MAX(0, stock - COALESCE(
                (SELECT SUM(r.quantity) FROM reservations r
                 WHERE r.product_id = products.id AND r.stock_deducted = 0), 0
            ))
            """
        )
        db.execute("UPDATE reservations SET stock_deducted = 1 WHERE stock_deducted = 0")
    db.execute("UPDATE reservations SET status = ? WHERE status = 'جديد' OR status = ''", (ORDER_STATUSES[0],))
    db.execute("UPDATE products SET advertised = 1 WHERE id IN (SELECT product_id FROM banners WHERE active = 1 AND product_id IS NOT NULL)")
    account = db.execute("SELECT id FROM account_profiles WHERE login_name = 'علي'").fetchone()
    if account is None:
        db.execute(
            "INSERT INTO account_profiles (login_name, account_code, password_hash, is_admin, permissions, created_at) VALUES (?, ?, ?, 1, ?, ?)",
            ("علي", "1", generate_password_hash("1"), json.dumps([key for key, _label in INTERFACE_OPTIONS], ensure_ascii=False), datetime.now().isoformat(timespec="seconds")),
        )
    else:
        db.execute(
            "UPDATE account_profiles SET is_admin = 1, account_code = '1', password_hash = ? WHERE login_name = 'علي'",
            (generate_password_hash("1"),),
        )
    db.execute("UPDATE account_profiles SET is_admin = 0 WHERE login_name <> 'علي'")
    db.execute(
        "UPDATE account_profiles SET permissions = ? WHERE is_admin = 0 AND (permissions IS NULL OR permissions = '' OR permissions = '[]')",
        (json.dumps(["shop"]),),
    )
    app.config["UPLOAD_FOLDER"].mkdir(parents=True, exist_ok=True)
    db.commit()


def format_date(value):
    try:
        return datetime.fromisoformat(value).strftime("%Y/%m/%d - %I:%M %p")
    except (ValueError, TypeError):
        return value


@app.template_filter("currency")
def currency(value):
    return f"{float(value):,.2f} د.ع"


@app.template_filter("date_ar")
def date_ar(value):
    return format_date(value)


@app.context_processor
def inject_layout_data():
    db = get_db()
    profile = db.execute(
        "SELECT is_admin, permissions FROM account_profiles WHERE login_name = ?",
        (session.get("customer_name", ""),),
    ).fetchone()
    is_admin = bool(profile and profile["is_admin"])
    try:
        permissions = set(json.loads(profile["permissions"] or "[]")) if profile else set()
    except (TypeError, json.JSONDecodeError):
        permissions = set()
    if is_admin:
        permissions = {key for key, _label in INTERFACE_OPTIONS}
    return {
        "low_stock_count": db.execute("SELECT COUNT(*) FROM products WHERE stock <= 5").fetchone()[0],
        "cart_count": sum(session.get("reservation_cart", {}).values()),
        "now": datetime.now,
        "is_admin": is_admin,
        "user_permissions": permissions,
        "interface_options": INTERFACE_OPTIONS,
    }


@app.route("/", methods=["GET", "POST"])
def customer_entry():
    if request.method == "POST":
        customer_name = request.form.get("customer_name", "").strip() or request.form.get("username_or_email", "").strip()
        password = request.form.get("password", "").strip()
        account_code = request.form.get("account_code", "").strip().upper() or password.upper()
        if not customer_name or not account_code:
            flash("أدخل اسم الزبون ورمز الحساب.", "error")
            return render_template("customer_entry.html")
        db = get_db()
        profile = db.execute("SELECT * FROM account_profiles WHERE login_name = ? OR email = ?", (customer_name, customer_name)).fetchone()
        if profile and not profile["active"]:
            flash("هذا الحساب معطل. تواصل مع المدير.", "error")
            return redirect(url_for("customer_entry"))
        if profile and not check_password_hash(profile["password_hash"], password):
            flash("بيانات الدخول غير صحيحة.", "error")
            return redirect(url_for("customer_entry"))
        if profile:
            customer_name = profile["login_name"]
            account_code = profile["account_code"]
        else:
            flash("هذا المستخدم غير موجود. أنشئ حسابًا جديدًا من رابط التسجيل.", "error")
            return redirect(url_for("customer_entry"))
        session["customer_name"] = customer_name
        session["account_code"] = account_code
        return redirect(url_for("shop"))
    db = get_db()
    login_products = db.execute(
        "SELECT * FROM products WHERE visible = 1 AND image <> '' ORDER BY id DESC"
    ).fetchall()
    return render_template("customer_entry.html", login_products=login_products)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        login_name = request.form.get("login_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirmation = request.form.get("password_confirmation", "")
        if not login_name or not email or not password:
            flash("اكتب الاسم والبريد الإلكتروني وكلمة المرور.", "error")
        elif len(password) < 6:
            flash("كلمة المرور يجب أن تكون 6 أحرف على الأقل.", "error")
        elif password != confirmation:
            flash("كلمتا المرور غير متطابقتين.", "error")
        elif login_name == "علي":
            flash("اسم المستخدم غير متاح.", "error")
        else:
            db = get_db()
            existing = db.execute(
                "SELECT id FROM account_profiles WHERE login_name = ? OR email = ?",
                (login_name, email),
            ).fetchone()
            if existing:
                flash("اسم المستخدم أو البريد الإلكتروني مستخدم مسبقًا.", "error")
            else:
                account_code = f"USR-{secrets.token_hex(4).upper()}"
                db.execute(
                    "INSERT INTO account_profiles (login_name, email, phone, account_code, password_hash, is_admin, permissions, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
                    (login_name, email, phone, account_code, generate_password_hash(password), json.dumps(["shop", "store_products", "store_offers", "orders", "cart", "account"], ensure_ascii=False), datetime.now().isoformat(timespec="seconds")),
                )
                db.commit()
                session["customer_name"] = login_name
                session["account_code"] = account_code
                flash("تم إنشاء حسابك وتسجيل دخولك بنجاح.", "success")
                return redirect(url_for("shop"))
    return render_template("register.html")


def admin_only(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        profile = get_db().execute(
            "SELECT is_admin, active FROM account_profiles WHERE login_name = ?",
            (session.get("customer_name", ""),),
        ).fetchone()
        if not profile or not profile["is_admin"] or not profile["active"]:
            flash("هذه الصفحة متاحة للمدير فقط.", "error")
            return redirect(url_for("shop"))
        return view(*args, **kwargs)
    return wrapped


@app.get("/admin/users")
@admin_only
def admin_users():
    db = get_db()
    query = request.args.get("q", "").strip()
    sql = "SELECT id, login_name, email, phone, account_code, is_admin, permissions, active, created_at FROM account_profiles"
    params = []
    if query:
        sql += " WHERE login_name LIKE ? OR email LIKE ? OR phone LIKE ?"
        search = f"%{query}%"
        params = [search, search, search]
    users = db.execute(sql + " ORDER BY is_admin DESC, id DESC", params).fetchall()
    permission_map = {}
    for user in users:
        try:
            permission_map[user["id"]] = set(json.loads(user["permissions"] or "[]"))
        except (TypeError, json.JSONDecodeError):
            permission_map[user["id"]] = set()
    return render_template("admin_users.html", users=users, permission_map=permission_map, query=query)


@app.post("/admin/users/<int:user_id>/permissions")
@admin_only
def update_admin_user(user_id):
    db = get_db()
    user = db.execute("SELECT login_name FROM account_profiles WHERE id = ?", (user_id,)).fetchone()
    if not user or user["login_name"] == "علي":
        flash("لا يمكن تعديل حساب المدير الأساسي علي.", "error")
        return redirect(url_for("admin_users"))
    permissions = {"shop", "store_products", "store_offers", "orders", "cart", "account"}
    permissions.update(key for key, _label in INTERFACE_OPTIONS if request.form.get(f"permission_{key}") == "on")
    db.execute(
        "UPDATE account_profiles SET permissions = ? WHERE id = ?",
        (json.dumps(sorted(permissions), ensure_ascii=False), user_id),
    )
    db.commit()
    flash("تم تحديث صلاحيات المستخدم.", "success")
    return redirect(url_for("admin_users", q=request.form.get("q", "")))


@app.post("/admin/users/<int:user_id>/delete")
@admin_only
def delete_admin_user(user_id):
    db = get_db()
    user = db.execute("SELECT login_name FROM account_profiles WHERE id = ?", (user_id,)).fetchone()
    if user and user["login_name"] != "علي":
        db.execute("DELETE FROM account_profiles WHERE id = ?", (user_id,))
        db.commit()
        flash("تم حذف المستخدم.", "success")
    else:
        flash("لا يمكن حذف حساب المدير الأساسي علي.", "error")
    return redirect(url_for("admin_users"))


@app.route("/account", methods=["GET", "POST"])
def account():
    if "account_code" not in session:
        return redirect(url_for("customer_entry"))
    db = get_db()
    profile = db.execute("SELECT * FROM account_profiles WHERE login_name = ?", (session.get("customer_name", ""),)).fetchone()
    if profile is None:
        profile = db.execute("SELECT * FROM account_profiles WHERE account_code = ? ORDER BY id DESC LIMIT 1", (session["account_code"],)).fetchone()
    if request.method == "POST":
        if request.form.get("action") == "profile":
            login_name = request.form.get("login_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            phone = request.form.get("phone", "").strip()
            duplicate = db.execute(
                "SELECT id FROM account_profiles WHERE (login_name = ? OR email = ?) AND id <> ?",
                (login_name, email, profile["id"]),
            ).fetchone()
            if not login_name or not email:
                flash("اسم المستخدم والبريد الإلكتروني مطلوبان.", "error")
            elif duplicate:
                flash("اسم المستخدم أو البريد الإلكتروني مستخدم مسبقًا.", "error")
            else:
                db.execute(
                    "UPDATE account_profiles SET login_name = ?, email = ?, phone = ? WHERE id = ?",
                    (login_name, email, phone, profile["id"]),
                )
                db.commit()
                session["customer_name"] = login_name
                flash("تم تحديث بيانات الحساب.", "success")
            return redirect(url_for("account"))
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        if not profile or not check_password_hash(profile["password_hash"], current_password):
            flash("كلمة المرور الحالية غير صحيحة.", "error")
        elif len(new_password) < 6:
            flash("كلمة المرور الجديدة يجب أن تكون 6 أحرف على الأقل.", "error")
        else:
            db.execute("UPDATE account_profiles SET password_hash = ? WHERE id = ?", (generate_password_hash(new_password), profile["id"]))
            db.commit()
            flash("تم تغيير كلمة المرور بأمان.", "success")
        return redirect(url_for("account"))
    return render_template("account.html", profile=profile, account_code=session["account_code"])


@app.get("/logout")
def logout():
    session.pop("customer_name", None)
    session.pop("account_code", None)
    session.pop("reservation_cart", None)
    return redirect(url_for("customer_entry"))


@app.route("/dashboard")
def dashboard():
    db = get_db()
    stats = {
        "products": db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "stock": db.execute("SELECT COALESCE(SUM(stock), 0) FROM products").fetchone()[0],
        "customer_orders_value": db.execute("SELECT COALESCE(SUM(total), 0) FROM reservations").fetchone()[0],
        "sales": db.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
    }
    recent_sales = db.execute("SELECT * FROM sales ORDER BY id DESC LIMIT 5").fetchall()
    top_products = db.execute(
        """
        SELECT p.*, COALESCE(SUM(si.quantity), 0) sold
        FROM products p LEFT JOIN sale_items si ON p.id = si.product_id
        GROUP BY p.id ORDER BY sold DESC, p.id DESC LIMIT 5
        """
    ).fetchall()
    reservations = db.execute(
        """
        SELECT
            CASE WHEN r.order_code = '' THEN 'طلب #' || r.id ELSE r.order_code END AS order_code,
            r.customer_name,
            r.account_code,
            r.status,
            MAX(r.created_at) AS created_at,
            SUM(r.total) AS order_total,
            GROUP_CONCAT(p.name, '، ') AS product_names
        FROM reservations r
        JOIN products p ON p.id = r.product_id
        GROUP BY CASE WHEN r.order_code = '' THEN 'طلب #' || r.id ELSE r.order_code END,
                 r.customer_name, r.account_code, r.status
        ORDER BY MAX(r.id) DESC LIMIT 10
        """
    ).fetchall()
    return render_template("dashboard.html", stats=stats, recent_sales=recent_sales, top_products=top_products, reservations=reservations)


@app.route("/products")
def products():
    db = get_db()
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    sql = "SELECT * FROM products WHERE (name LIKE ? OR sku LIKE ?)"
    params = [f"%{query}%", f"%{query}%"]
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY id DESC"
    rows = db.execute(sql, params).fetchall()
    categories = db.execute("SELECT DISTINCT category FROM products ORDER BY category").fetchall()
    return render_template("products.html", products=rows, categories=categories, query=query, selected_category=category)


@app.route("/products/new", methods=["GET", "POST"])
def new_product():
    if request.method == "POST":
        return save_product()
    return render_template("product_form.html", product=None, page_title="إضافة منتج جديد")


@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
def edit_product(product_id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if product is None:
        flash("المنتج المطلوب غير موجود.", "error")
        return redirect(url_for("products"))
    if request.method == "POST":
        return save_product(product_id)
    return render_template("product_form.html", product=product, page_title="تعديل بيانات المنتج")


def save_product(product_id=None):
    db = get_db()
    form = request.form
    name = form.get("name", "").strip()
    category = form.get("category", "").strip()
    sku = form.get("sku", "").strip().upper()
    description = form.get("description", "").strip()
    specifications = form.get("specifications", "").strip()
    icon = form.get("icon", "📦").strip() or "📦"
    image = ""
    advertised = 1 if form.get("advertised") == "on" else 0
    uploaded_image = request.files.get("image")
    if product_id:
        existing = db.execute("SELECT image FROM products WHERE id = ?", (product_id,)).fetchone()
        image = existing["image"] if existing else ""
    if uploaded_image and uploaded_image.filename:
        safe_name = secure_filename(uploaded_image.filename)
        if not safe_name:
            flash("اسم الصورة غير صالح.", "error")
            return render_template("product_form.html", product=dict(form), page_title="تعديل بيانات المنتج" if product_id else "إضافة منتج جديد")
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{safe_name}"
        uploaded_image.save(app.config["UPLOAD_FOLDER"] / filename)
        image = f"uploads/{filename}"
    try:
        price = float(form.get("price", "0"))
        old_price = float(form.get("old_price", "0") or 0)
        discount = float(form.get("discount", "0") or 0)
        stock = int(form.get("stock", "0"))
        if min(price, old_price, discount) < 0 or stock < 0:
            raise ValueError
        featured = 1 if form.get("featured") == "on" else 0
        visible = 1 if form.get("visible", "on") == "on" else 0
    except ValueError:
        flash("تحقق من أن السعر والمخزون أرقام صحيحة وغير سالبة.", "error")
        return render_template("product_form.html", product=dict(form), page_title="تعديل بيانات المنتج" if product_id else "إضافة منتج جديد")
    if not name or not category or not sku:
        flash("الاسم والتصنيف ورمز المنتج حقول مطلوبة.", "error")
        return render_template("product_form.html", product=dict(form), page_title="تعديل بيانات المنتج" if product_id else "إضافة منتج جديد")
    try:
        if product_id:
            db.execute(
                "UPDATE products SET name=?, category=?, sku=?, price=?, old_price=?, discount=?, stock=?, description=?, specifications=?, icon=?, image=?, visible=?, featured=?, advertised=? WHERE id=?",
                (name, category, sku, price, old_price, discount, stock, description, specifications, icon, image, visible, featured, advertised, product_id),
            )
            flash("تم تحديث بيانات المنتج بنجاح.", "success")
        else:
            db.execute(
                "INSERT INTO products (name, category, sku, price, old_price, discount, stock, description, specifications, icon, image, visible, featured, advertised, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (name, category, sku, price, old_price, discount, stock, description, specifications, icon, image, visible, featured, advertised, datetime.now().isoformat(timespec="seconds")),
            )
            flash("تمت إضافة المنتج إلى المخزون.", "success")
        db.commit()
    except sqlite3.IntegrityError:
        flash("رمز المنتج مستخدم مسبقًا، اختر رمزًا آخر.", "error")
        return render_template("product_form.html", product=dict(form), page_title="تعديل بيانات المنتج" if product_id else "إضافة منتج جديد")
    return redirect(url_for("products"))


@app.post("/products/<int:product_id>/delete")
def delete_product(product_id):
    db = get_db()
    try:
        db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        db.commit()
        flash("تم حذف المنتج.", "success")
    except sqlite3.IntegrityError:
        flash("لا يمكن حذف منتج تم بيعه سابقًا. يمكنك تعديل مخزونه بدلًا من ذلك.", "error")
    return redirect(url_for("products"))


@app.route("/shop")
def shop():
    if "customer_name" not in session or "account_code" not in session:
        return redirect(url_for("customer_entry"))
    db = get_db()
    query = request.args.get("q", "").strip()
    if query:
        return redirect(url_for("store_search", q=query))
    products_list = db.execute("SELECT * FROM products WHERE visible = 1 AND stock > 0 ORDER BY id DESC").fetchall()
    categories = db.execute("SELECT category, COUNT(*) AS count FROM products WHERE visible = 1 GROUP BY category ORDER BY category").fetchall()
    featured_products = db.execute("SELECT * FROM products WHERE visible = 1 AND stock > 0 AND featured = 1 ORDER BY id DESC LIMIT 4").fetchall()
    offers_products = db.execute("SELECT * FROM products WHERE visible = 1 AND stock > 0 AND (discount > 0 OR old_price > price) ORDER BY id DESC LIMIT 4").fetchall()
    banners = db.execute("SELECT p.*, p.price AS banner_price FROM products p WHERE p.visible = 1 AND p.stock > 0 AND p.advertised = 1 ORDER BY p.id DESC").fetchall()
    return render_template("shop.html", products=products_list, featured_products=featured_products, offers_products=offers_products, categories=categories, banners=banners, customer_name=session["customer_name"], query=query)


def visible_products_sql(where="", params=()):
    db = get_db()
    sql = "SELECT * FROM products WHERE visible = 1 AND stock > 0"
    if where:
        sql += f" AND {where}"
    sql += " ORDER BY id DESC"
    return db.execute(sql, params).fetchall()


@app.get("/store/products")
def store_products():
    if "account_code" not in session:
        return redirect(url_for("customer_entry"))
    return render_template("product_listing.html", page_title="المنتجات", products=visible_products_sql())


@app.get("/store/offers")
def store_offers():
    if "account_code" not in session:
        return redirect(url_for("customer_entry"))
    return render_template("product_listing.html", page_title="العروض", products=visible_products_sql("(discount > 0 OR old_price > price)"))


@app.get("/store/search")
def store_search():
    if "account_code" not in session:
        return redirect(url_for("customer_entry"))
    query = request.args.get("q", "").strip()
    search = f"%{query}%"
    products_list = visible_products_sql(
        "(name LIKE ? OR sku LIKE ? OR category LIKE ? OR description LIKE ? OR specifications LIKE ?)",
        (search, search, search, search, search),
    ) if query else []
    return render_template("product_listing.html", page_title="نتائج البحث", products=products_list, query=query, search_only=True)


@app.get("/store/category/<path:category>")
def store_category(category):
    if "account_code" not in session:
        return redirect(url_for("customer_entry"))
    return render_template("product_listing.html", page_title=category, products=visible_products_sql("category = ?", (category,)), selected_category=category)


@app.route("/dashboard/banners")
def banners_admin():
    db = get_db()
    banners = db.execute(
        "SELECT b.*, p.name AS product_name FROM banners b LEFT JOIN products p ON p.id = b.product_id ORDER BY b.sort_order, b.id DESC"
    ).fetchall()
    return render_template("banners.html", banners=banners)


@app.route("/dashboard/banners/new", methods=["GET", "POST"])
def new_banner():
    db = get_db()
    products_list = db.execute("SELECT id, name, price, image, icon FROM products ORDER BY name").fetchall()
    if request.method == "POST":
        return save_banner(products_list)
    return render_template("banner_form.html", banner=None, products=products_list, page_title="إضافة إعلان")


@app.route("/dashboard/banners/<int:banner_id>/edit", methods=["GET", "POST"])
def edit_banner(banner_id):
    db = get_db()
    banner = db.execute("SELECT * FROM banners WHERE id = ?", (banner_id,)).fetchone()
    if banner is None:
        flash("الإعلان المطلوب غير موجود.", "error")
        return redirect(url_for("banners_admin"))
    products_list = db.execute("SELECT id, name, price, image, icon FROM products ORDER BY name").fetchall()
    if request.method == "POST":
        return save_banner(products_list, banner_id)
    return render_template("banner_form.html", banner=banner, products=products_list, page_title="تعديل الإعلان")


def save_banner(products_list, banner_id=None):
    db = get_db()
    form = request.form
    title = form.get("title", "").strip()
    description = form.get("description", "").strip()
    try:
        price = max(0, float(form.get("price", "0")))
        discount = max(0, float(form.get("discount", "0")))
        sort_order = int(form.get("sort_order", "0"))
        duration = max(3, int(form.get("duration", "5")))
        product_id = int(form.get("product_id")) if form.get("product_id") else None
    except (TypeError, ValueError):
        flash("تحقق من أرقام الإعلان والمنتج المختار.", "error")
        return render_template("banner_form.html", banner=dict(form), products=products_list, page_title="تعديل الإعلان" if banner_id else "إضافة إعلان")
    if not title:
        flash("عنوان الإعلان مطلوب.", "error")
        return render_template("banner_form.html", banner=dict(form), products=products_list, page_title="تعديل الإعلان" if banner_id else "إضافة إعلان")
    image = ""
    if banner_id:
        current = db.execute("SELECT image FROM banners WHERE id = ?", (banner_id,)).fetchone()
        image = current["image"] if current else ""
    upload = request.files.get("image")
    if upload and upload.filename:
        safe_name = secure_filename(upload.filename)
        if not safe_name:
            flash("اسم الصورة غير صالح.", "error")
            return render_template("banner_form.html", banner=dict(form), products=products_list, page_title="تعديل الإعلان" if banner_id else "إضافة إعلان")
        filename = f"banner_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{safe_name}"
        upload.save(app.config["UPLOAD_FOLDER"] / filename)
        image = f"uploads/{filename}"
    active = 1 if form.get("active") == "on" else 0
    values = (title, description, price, discount, image, product_id, sort_order, duration, active)
    if banner_id:
        previous = db.execute("SELECT product_id FROM banners WHERE id = ?", (banner_id,)).fetchone()
        db.execute("UPDATE banners SET title=?, description=?, price=?, discount=?, image=?, product_id=?, sort_order=?, duration=?, active=? WHERE id=?", (*values, banner_id))
        if previous and previous["product_id"] and previous["product_id"] != product_id:
            db.execute("UPDATE products SET advertised = 0 WHERE id = ? AND NOT EXISTS (SELECT 1 FROM banners WHERE product_id = ? AND active = 1 AND id != ?)", (previous["product_id"], previous["product_id"], banner_id))
        flash("تم تحديث الإعلان.", "success")
    else:
        db.execute("INSERT INTO banners (title, description, price, discount, image, product_id, sort_order, duration, active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (*values, datetime.now().isoformat(timespec="seconds")))
        flash("تمت إضافة الإعلان.", "success")
    if product_id:
        db.execute("UPDATE products SET advertised = ? WHERE id = ?", (active, product_id))
    db.commit()
    return redirect(url_for("banners_admin"))


@app.post("/dashboard/banners/<int:banner_id>/delete")
def delete_banner(banner_id):
    db = get_db()
    banner = db.execute("SELECT product_id FROM banners WHERE id = ?", (banner_id,)).fetchone()
    db.execute("DELETE FROM banners WHERE id = ?", (banner_id,))
    if banner and banner["product_id"]:
        db.execute("UPDATE products SET advertised = 0 WHERE id = ? AND NOT EXISTS (SELECT 1 FROM banners WHERE product_id = ? AND active = 1)", (banner["product_id"], banner["product_id"]))
    db.commit()
    flash("تم حذف الإعلان.", "success")
    return redirect(url_for("banners_admin"))


@app.route("/products/<int:product_id>")
def product_detail(product_id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if product is None:
        flash("المنتج المطلوب غير موجود.", "error")
        return redirect(url_for("shop"))
    return render_template("product_detail.html", product=product)


@app.post("/cart/add/<int:product_id>")
def add_to_cart(product_id):
    if "customer_name" not in session or "account_code" not in session:
        return redirect(url_for("customer_entry"))
    db = get_db()
    product = db.execute("SELECT id, name, stock FROM products WHERE id = ?", (product_id,)).fetchone()
    if product is None:
        flash("المنتج المطلوب غير موجود.", "error")
        return redirect(url_for("shop"))
    try:
        quantity = max(1, int(request.form.get("quantity", 1)))
    except (TypeError, ValueError):
        quantity = 1
    cart = session.get("reservation_cart", {})
    current = int(cart.get(str(product_id), 0))
    if product["stock"] <= 0:
        flash(f"المنتج {product['name']} غير متوفر حاليًا.", "error")
        return redirect(url_for("shop"))
    if current + quantity > product["stock"]:
        flash(f"الكمية المطلوبة من {product['name']} أكبر من المتوفر ({product['stock']}).", "error")
        return redirect(url_for("shop"))
    cart[str(product_id)] = current + quantity
    session["reservation_cart"] = {key: value for key, value in cart.items() if value > 0}
    flash("تمت إضافة المنتج إلى طلبك.", "success")
    return redirect(url_for("cart"))


@app.route("/cart")
def cart():
    if "account_code" not in session:
        return redirect(url_for("customer_entry"))
    cart_data = session.get("reservation_cart", {})
    db = get_db()
    items = []
    total = Decimal("0")
    for product_id, quantity in cart_data.items():
        product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if product:
            line_total = Decimal(str(product["price"])) * int(quantity)
            items.append({"product": product, "quantity": int(quantity), "line_total": line_total})
            total += line_total
    return render_template("cart.html", items=items, total=total)


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if "account_code" not in session:
        return redirect(url_for("customer_entry"))
    cart_data = session.get("reservation_cart", {})
    db = get_db()
    items = []
    total = Decimal("0")
    for product_id, quantity in cart_data.items():
        product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if product is None:
            flash("أحد المنتجات في السلة لم يعد موجودًا.", "error")
            return redirect(url_for("cart"))
        if product["stock"] <= 0 or int(quantity) > product["stock"]:
            flash(f"المنتج {product['name']} لم تعد كميته المطلوبة متوفرة. عدّل السلة بعد توفره.", "error")
            return redirect(url_for("cart"))
        line_total = Decimal(str(product["price"])) * int(quantity)
        items.append((product, int(quantity), line_total))
        total += line_total
    if not items:
        flash("أضف منتجًا واحدًا على الأقل قبل إتمام الطلب.", "error")
        return redirect(url_for("shop"))
    if request.method == "GET":
        return render_template("reservation_form.html", items=items, total=total)

    customer_name = request.form.get("customer_name", "").strip()
    customer_number = request.form.get("customer_number", "").strip()
    customer_address = request.form.get("customer_address", "").strip()
    governorate = request.form.get("governorate", "").strip()
    if len(customer_name.split()) < 3:
        flash("اكتب الاسم الثلاثي كاملًا.", "error")
    elif not customer_number.isdigit():
        flash("أدخل رقم تواصل صحيحًا.", "error")
    elif not customer_address or not governorate:
        flash("العنوان والمحافظة حقول مطلوبة لإتمام الحجز.", "error")
    else:
        order_code = secrets.token_hex(4).upper()
        for product, quantity, _line_total in items:
            updated = db.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?",
                (quantity, product["id"], quantity),
            )
            if updated.rowcount != 1:
                db.rollback()
                flash(f"المنتج {product['name']} لم تعد كميته المطلوبة متوفرة.", "error")
                return redirect(url_for("cart"))
        for product, quantity, line_total in items:
            db.execute(
                "INSERT INTO reservations (customer_name, customer_number, account_code, customer_address, governorate, product_id, created_at, status, order_code, quantity, total, stock_deducted) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (customer_name, customer_number, session["account_code"], customer_address, governorate, product["id"], datetime.now().isoformat(timespec="seconds"), ORDER_STATUSES[0], order_code, quantity, float(line_total), 1),
            )
        db.commit()
        session["reservation_cart"] = {}
        flash(f"تم تسجيل الطلب رقم {order_code} بإجمالي {float(total):,.2f} د.ع.", "success")
        return redirect(url_for("orders"))
    return render_template("reservation_form.html", items=items, total=total, reservation=request.form)


@app.post("/cart/remove/<int:product_id>")
def remove_from_cart(product_id):
    cart_data = session.get("reservation_cart", {})
    cart_data.pop(str(product_id), None)
    session["reservation_cart"] = cart_data
    return redirect(url_for("cart"))


@app.route("/orders")
def orders():
    if "account_code" not in session:
        return redirect(url_for("customer_entry"))
    db = get_db()
    reservations = db.execute(
        """
         SELECT r.*, p.name AS product_name, p.price, p.image, p.icon,
             CASE WHEN r.order_code = '' THEN r.total ELSE (SELECT COALESCE(SUM(r2.total), 0) FROM reservations r2 WHERE r2.order_code = r.order_code) END AS order_total
        FROM reservations r JOIN products p ON p.id = r.product_id
        WHERE r.account_code = ? ORDER BY r.id DESC
        """,
        (session["account_code"],),
    ).fetchall()
    return render_template("orders.html", reservations=reservations, account_code=session["account_code"], order_statuses=ORDER_STATUSES, delivery_fee=DELIVERY_FEE)


@app.post("/orders/<int:reservation_id>/delete")
def delete_order(reservation_id):
    if "account_code" not in session:
        return redirect(url_for("customer_entry"))
    db = get_db()
    reservation = db.execute(
        "SELECT order_code FROM reservations WHERE id = ? AND account_code = ?",
        (reservation_id, session["account_code"]),
    ).fetchone()
    if reservation and reservation["order_code"]:
        reservations_to_delete = db.execute(
            "SELECT product_id, quantity, stock_deducted FROM reservations WHERE order_code = ? AND account_code = ?",
            (reservation["order_code"], session["account_code"]),
        ).fetchall()
        for item in reservations_to_delete:
            if item["stock_deducted"]:
                db.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (item["quantity"], item["product_id"]))
        result = db.execute(
            "DELETE FROM reservations WHERE order_code = ? AND account_code = ?",
            (reservation["order_code"], session["account_code"]),
        )
    elif reservation:
        item = db.execute(
            "SELECT product_id, quantity, stock_deducted FROM reservations WHERE id = ?",
            (reservation_id,),
        ).fetchone()
        if item and item["stock_deducted"]:
            db.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (item["quantity"], item["product_id"]))
        result = db.execute("DELETE FROM reservations WHERE id = ?", (reservation_id,))
    else:
        result = None
    db.commit()
    if result and result.rowcount:
        flash("تم حذف الطلب بنجاح.", "success")
    else:
        flash("الطلب غير موجود أو لا ينتمي إلى حسابك.", "error")
    return redirect(url_for("orders"))


@app.route("/dashboard/reservations")
def reservation_admin():
    db = get_db()
    reservations = db.execute(
        "SELECT r.*, p.name AS product_name FROM reservations r JOIN products p ON p.id = r.product_id ORDER BY r.id DESC"
    ).fetchall()
    return render_template("reservation_admin.html", reservations=reservations, order_statuses=ORDER_STATUSES)


@app.post("/dashboard/reservations/<int:reservation_id>/status")
def update_reservation_status(reservation_id):
    status = request.form.get("status", "").strip()
    if status not in ORDER_STATUSES:
        flash("حالة الطلب غير صحيحة.", "error")
        return redirect(url_for("reservation_admin"))
    db = get_db()
    db.execute("UPDATE reservations SET status = ? WHERE id = ?", (status, reservation_id))
    db.commit()
    flash("تم تحديث حالة الطلب.", "success")
    return redirect(url_for("reservation_admin"))


@app.route("/reservations/<int:product_id>", methods=["GET", "POST"])
def reserve_product(product_id):
    if "customer_name" not in session or "account_code" not in session:
        return redirect(url_for("customer_entry"))
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if product is None:
        flash("المنتج المطلوب غير موجود.", "error")
        return redirect(url_for("shop"))
    if request.method == "GET":
        items = [(product, 1, Decimal(str(product["price"]))) ]
        return render_template("reservation_form.html", items=items, total=Decimal(str(product["price"])), single_product=True, max_quantity=product["stock"])

    try:
        quantity = int(request.form.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 0
    if quantity < 1 or quantity > product["stock"]:
        flash("اختر كمية صحيحة ضمن الكمية المتوفرة.", "error")
        return render_template("reservation_form.html", items=[(product, max(1, min(quantity, product["stock"])), Decimal(str(product["price"])) * max(1, min(quantity, product["stock"])))], total=Decimal(str(product["price"])) * max(1, min(quantity, product["stock"])), reservation=request.form, single_product=True, max_quantity=product["stock"])
    customer_name = request.form.get("customer_name", "").strip()
    customer_number = request.form.get("customer_number", "").strip()
    customer_address = request.form.get("customer_address", "").strip()
    governorate = request.form.get("governorate", "").strip()
    reservation_items = [(product, quantity, Decimal(str(product["price"])) * quantity)]
    total = Decimal(str(product["price"])) * quantity
    name_parts = customer_name.split()
    if len(name_parts) < 3:
        flash("اكتب الاسم الثلاثي كاملًا.", "error")
        return render_template("reservation_form.html", items=reservation_items, total=total, reservation=request.form, single_product=True, max_quantity=product["stock"])
    if not customer_number.isdigit():
        flash("أدخل رقم تواصل صحيحًا.", "error")
        return render_template("reservation_form.html", items=reservation_items, total=total, reservation=request.form, single_product=True, max_quantity=product["stock"])
    if len(customer_address) < 10 or governorate not in GOVERNORATES:
        flash("اكتب العنوان بالتفصيل واختر محافظة صحيحة.", "error")
        return render_template("reservation_form.html", items=reservation_items, total=total, reservation=request.form, single_product=True, max_quantity=product["stock"])
    order_code = secrets.token_hex(4).upper()
    updated = db.execute(
        "UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?",
        (quantity, product_id, quantity),
    )
    if updated.rowcount != 1:
        db.rollback()
        flash("الكمية المطلوبة لم تعد متوفرة.", "error")
        return redirect(url_for("shop"))
    db.execute(
        "INSERT INTO reservations (customer_name, customer_number, account_code, customer_address, governorate, product_id, created_at, status, order_code, quantity, total, stock_deducted) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (customer_name, customer_number, session["account_code"], customer_address, governorate, product_id, datetime.now().isoformat(timespec="seconds"), ORDER_STATUSES[0], order_code, quantity, float(total), 1),
    )
    db.commit()
    flash(f"تم حجز {product['name']} بنجاح. المبلغ الكلي: {float(total):,.2f} د.ع.", "success")
    return redirect(url_for("shop"))


@app.route("/sales", methods=["GET", "POST"])
def sales():
    db = get_db()
    if request.method == "POST":
        customer = "عميل نقدي"
        quantities = {}
        for key, value in request.form.items():
            if key.startswith("quantity_") and value:
                try:
                    quantity = int(value)
                    if quantity > 0:
                        quantities[int(key.replace("quantity_", ""))] = quantity
                except ValueError:
                    continue
        if not quantities:
            flash("اختر منتجًا واحدًا على الأقل وأدخل الكمية.", "error")
            return redirect(url_for("sales"))
        products_by_id = {}
        total = Decimal("0")
        for product_id, quantity in quantities.items():
            product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
            if product is None or product["stock"] < quantity:
                flash(f"الكمية المطلوبة غير متوفرة للمنتج رقم {product_id}.", "error")
                return redirect(url_for("sales"))
            products_by_id[product_id] = product
            total += Decimal(str(product["price"])) * quantity
        sale = db.execute("INSERT INTO sales (customer_name, total, created_at) VALUES (?, ?, ?)", (customer, float(total), datetime.now().isoformat(timespec="seconds")))
        sale_id = sale.lastrowid
        for product_id, quantity in quantities.items():
            product = products_by_id[product_id]
            db.execute("INSERT INTO sale_items (sale_id, product_id, quantity, price) VALUES (?, ?, ?, ?)", (sale_id, product_id, quantity, product["price"]))
            db.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (quantity, product_id))
        db.commit()
        flash(f"تم تسجيل البيع بقيمة {float(total):,.2f} د.ع.", "success")
        return redirect(url_for("sales"))
    query = request.args.get("q", "").strip()
    products_list = db.execute("SELECT * FROM products WHERE stock > 0 AND (name LIKE ? OR sku LIKE ?) ORDER BY name", (f"%{query}%", f"%{query}%")).fetchall()
    sales_list = db.execute("SELECT * FROM sales ORDER BY id DESC LIMIT 15").fetchall()
    return render_template("sales.html", products=products_list, sales=sales_list, query=query)


@app.route("/sales/<int:sale_id>")
def sale_detail(sale_id):
    db = get_db()
    sale = db.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
    if sale is None:
        flash("الفاتورة غير موجودة.", "error")
        return redirect(url_for("sales"))
    items = db.execute("SELECT si.*, p.name, p.icon, p.sku FROM sale_items si JOIN products p ON p.id = si.product_id WHERE si.sale_id = ?", (sale_id,)).fetchall()
    return render_template("sale_detail.html", sale=sale, items=items)


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
