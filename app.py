from flask import Flask, render_template, request, redirect, session, flash, url_for, Response
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.exceptions import abort
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import re
from datetime import datetime, timedelta
from itsdangerous import URLSafeTimedSerializer


app = Flask(__name__)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

app.config['SECRET_KEY'] = 'supersecretkey'
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])


app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sme.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="staff")

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    buying_price = db.Column(db.Float, nullable=False)
    selling_price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    product = db.relationship('Product', backref='sales')
    quantity = db.Column(db.Integer, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    profit = db.Column(db.Float)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User')




class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/export-sales")
@login_required
def export_sales():
    sales = Sale.query.all()

    data = "Product,Quantity,Total,Profit,Date\n"

    for s in sales:
        data += f"{s.product.name},{s.quantity},{s.total_amount},{s.profit},{s.date}\n"

    return Response(
        data,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=sales_report.csv"}
    )


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login"))

        if current_user.role != "admin":
            flash("Access denied. Admin only.", "danger")
            return redirect(url_for("dashboard"))

        return func(*args, **kwargs)

    return wrapper

@app.route("/admin/users")
@login_required
@admin_required
def manage_users():

    users = User.query.all()
    return render_template("manage_users.html", users=users)

@app.route("/admin/toggle_role/<int:user_id>")
@admin_required
def toggle_role(user_id):
    if current_user.role != "admin":
        flash("Unauthorized access!", "danger")
        return redirect(url_for("dashboard"))

    user = User.query.get_or_404(user_id)

    if user.role == "admin":
        user.role = "staff"
    else:
        user.role = "admin"

    db.session.commit()

    flash("User role updated.", "success")
    return redirect("/admin/users")

@app.route("/admin/delete_user/<int:user_id>")
@admin_required
def delete_user(user_id):
    if current_user.role != "admin":
        flash("Unauthorized access!", "danger")
        return redirect(url_for("dashboard"))

    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("Admin cannot delete their own account!", "danger")
        return redirect("/admin/users")

    db.session.delete(user)
    db.session.commit()

    flash("User deleted successfully.", "success")
    return redirect("/admin/users")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        password = request.form["password"]

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("Username already exists.", "warning")
            return redirect("/register")

        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "danger")
            return redirect("/register")

        if not re.search(r"[A-Z]", password):
            flash("Password must contain at least one uppercase letter.", "danger")
            return redirect("/register")

        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            flash("Password must contain at least one special character.", "danger")
            return redirect("/register")

        hashed_password = generate_password_hash(password)

        if User.query.count() == 0:
            role = "admin"
        else:
            role = "staff"

        new_user = User(
            username=username,
            password=hashed_password,
            role=role
        )

        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)

        flash(f"Registered as {role}", "success")
        return redirect("/")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if not user:
            flash("Account not found.", "danger")
            return redirect("/login")

        if not check_password_hash(user.password, password):
            flash("Incorrect password.", "danger")
            return redirect("/login")

        login_user(user)

        flash(f"Login successful. Welcome {user.username}!", "success")
        return redirect("/")

    return render_template("login.html")


@app.route("/logout")
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect("/login")



@app.route("/")
@login_required
def dashboard():

    today = datetime.utcnow().date()

    total_products = Product.query.count()

    total_sales = db.session.query(func.sum(Sale.total_amount)).scalar() or 0
    total_expenses = db.session.query(func.sum(Expense.amount)).scalar() or 0

    today_sales = db.session.query(func.sum(Sale.total_amount))\
        .filter(func.date(Sale.date) == today).scalar() or 0

    today_expenses = db.session.query(func.sum(Expense.amount))\
        .filter(func.date(Expense.date) == today).scalar() or 0

    if current_user.role == "admin":
        total_profit = total_sales - total_expenses
        today_profit = today_sales - today_expenses
        show_financials = True
    else:
        total_profit = None
        today_profit = None
        total_expenses = None
        show_financials = False

    last_7_days = datetime.utcnow() - timedelta(days=6)

    sales_data = (
        db.session.query(
            func.date(Sale.date),
            func.sum(Sale.total_amount)
        )
        .filter(Sale.date >= last_7_days)
        .group_by(func.date(Sale.date))
        .all()
    )

    week_labels = []
    week_sales = []

    for i in range(7):
        day = datetime.utcnow() - timedelta(days=6 - i)
        week_labels.append(day.strftime("%a"))

        found = False
        for sale in sales_data:
            if sale[0] == day.date():
                week_sales.append(float(sale[1]))
                found = True
                break

        if not found:
            week_sales.append(0)

    low_stock = Product.query.filter(Product.quantity <= 5).all()
    return render_template(
        "dashboard.html",
        total_products=total_products,
        total_sales=total_sales,
        total_expenses=total_expenses,
        total_profit=total_profit,
        today_profit=today_profit,
        week_labels=week_labels,
        week_sales=week_sales,
        show_financials=show_financials
    )

@app.route("/search")
@login_required
def search():

    query = request.args.get("query")

    if query:
        results = Product.query.filter(
            Product.name.ilike(f"%{query}%")
        ).all()
    else:
        results = []

    return render_template(
        "search_results.html",
        query=query,
        results=results
    )



@app.route("/profile")
def profile():
    return render_template("profile.html")


@app.route("/settings")
@login_required
@admin_required  
def settings():
    print(current_user.username)
    print(current_user.role)
    return render_template("settings.html")


@app.route("/change_password", methods=["GET", "POST"])
def change_password():

    if request.method == "POST":
        current = request.form["current_password"]
        new = request.form["new_password"]

        user = User.query.get(session["user_id"])

        if not check_password_hash(user.password, current):
            flash("Current password incorrect.", "danger")
            return redirect("/change_password")

        user.password = generate_password_hash(new)
        db.session.commit()

        flash("Password updated successfully.", "success")
        return redirect("/settings")

    return render_template("change_password.html")

@app.route("/update_profile", methods=["GET", "POST"])
def update_profile():

    user = User.query.get(session["user_id"])

    if request.method == "POST":

        new_username = request.form["username"].strip().lower()

        user.username = new_username
        db.session.commit()

        session["username"] = new_username

        flash("Profile updated successfully.", "success")
        return redirect("/settings")

    return render_template("update_profile.html", user=user)

@app.route("/system_preferences")
def system_preferences():
    return render_template("system_preferences.html")


@app.route("/notifications")
def notifications():
    return render_template("notifications.html")


@app.route("/products")
@login_required
def products():
    products = Product.query.all()
    return render_template("products.html", products=products)


@app.route("/add-product", methods=["GET", "POST"])
@login_required
def add_product():
    if request.method == "POST":
        name = request.form["name"]

        try:
            buying_price = float(request.form["buying_price"])
            selling_price = float(request.form["selling_price"])
            quantity = int(request.form["quantity"])
        except:
            flash("Invalid input values!", "danger")
            return redirect("/add-product")

        if buying_price <= 0 or selling_price <= 0:
            flash("Prices must be greater than zero!", "warning")
            return redirect("/add-product")

        if selling_price <= buying_price:
            flash("Selling price must be greater than buying price!", "danger")
            return redirect("/add-product")

        if quantity < 0:
            flash("Quantity cannot be negative!", "warning")
            return redirect("/add-product")

        new_product = Product(
            name=name,
            buying_price=buying_price,
            selling_price=selling_price,
            quantity=quantity
        )

        db.session.add(new_product)
        db.session.commit()

        flash("Product added successfully!", "success")
        return redirect("/products")

    return render_template("add_product.html")


@app.route("/sales")
@login_required
def sales():
    sales = Sale.query.filter_by(user_id=current_user.id).all()

    total_profit = sum(s.profit for s in sales)

    return render_template("sales.html", sales=sales, total_profit=total_profit)


@app.route("/add-sale", methods=["GET", "POST"])
@login_required
def add_sale():
    products = Product.query.all()

    if request.method == "POST":
        product_id = int(request.form["product_id"])
        quantity = int(request.form["quantity"])

        product = Product.query.get(product_id)

        if not product:
            flash("Product not found!", "danger")
            return redirect("/add-sale")

        if quantity <= 0:
            flash("Quantity must be greater than zero!", "warning")
            return redirect("/add-sale")

        if quantity > product.quantity:
            flash(f"Only {product.quantity} items available in stock!", "danger")
            return redirect("/add-sale")

        total_amount = product.selling_price * quantity
        profit = (product.selling_price - product.buying_price) * quantity

        product.quantity -= quantity

        new_sale = Sale(
            product_id=product.id,
            quantity=quantity,
            total_amount=total_amount,
            profit=profit,
            user_id=current_user.id
            )

        db.session.add(new_sale)
        db.session.commit()

        flash("Sale recorded successfully!", "success")
        return redirect("/sales")

    return render_template("add_sale.html", products=products)

@app.route("/delete-sale/<int:id>")
@login_required
def delete_sale(id):
    sale = Sale.query.get_or_404(id)

    product = Product.query.get(sale.product_id)
    if product:
        product.quantity += sale.quantity

    db.session.delete(sale)
    db.session.commit()

    return redirect("/sales")

@app.route("/expenses")
@login_required
@admin_required 
def expenses():
    expenses = Expense.query.all()
    return render_template("expenses.html", expenses=expenses)


@app.route("/add-expense", methods=["GET", "POST"])
@login_required
def add_expense():
    if request.method == "POST":
        new_expense = Expense(
            description=request.form["description"],
            amount=float(request.form["amount"])
        )

        db.session.add(new_expense)
        db.session.commit()

        return redirect("/expenses")

    return render_template("add_expense.html")

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":
        username = request.form.get("username")

        user = User.query.filter_by(username=username).first()

        if user:
            token = serializer.dumps(user.username, salt="password-reset")

            reset_link = url_for('reset_password', token=token, _external=True)

            print("\nPassword Reset Link:")
            print(reset_link)
            print("\n")

            flash("Password reset link generated. Check terminal.", "info")
            return redirect("/login")

        flash("Username not found!", "danger")
        all_users = User.query.all()
        print("ALL USERS IN DB:", all_users)


    return render_template("forgot_password.html")

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):

    try:
        username = serializer.loads(token, salt="password-reset", max_age=600)
    except:
        flash("Reset link expired or invalid!", "danger")
        return redirect("/login")

    user = User.query.filter_by(username=username).first()

    if request.method == "POST":
        new_password = request.form.get("password")

        hashed_password = generate_password_hash(new_password)

        user.password = hashed_password
        db.session.commit()

        flash("Password reset successful!", "success")
        return redirect("/login")

    return render_template("reset_password.html")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)

