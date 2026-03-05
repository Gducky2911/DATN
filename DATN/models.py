
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    
    role = db.Column(db.String(20), nullable=False, default='customer')  
    # admin, employee, customer

    employee_type = db.Column(db.String(50))  
    # waiter, chef, cashier, delivery

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    active = db.Column(db.Boolean, default=True)

    # ✅ Giấy khám sức khỏe (chỉ áp dụng cho employee)
    health_check_date = db.Column(db.Date, nullable=True)

    # Relationships
    reservations = db.relationship('Reservation', backref='customer', lazy=True)
    orders = db.relationship('Order', foreign_keys='Order.customer_id', backref='customer', lazy=True)
    feedbacks = db.relationship('Feedback', backref='customer', lazy=True)

    def set_password(self, password):
        """Mã hóa mật khẩu"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Kiểm tra mật khẩu"""
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.user_id)

    def health_check_expiry_date(self):
        """Ngày hết hạn giấy khám (6 tháng)"""
        if not self.health_check_date:
            return None
        return self.health_check_date + timedelta(days=180)

    def is_health_check_valid(self):
        """Giấy khám còn hiệu lực không"""
        if self.role != 'employee' or not self.health_check_date:
            return False
        return date.today() <= self.health_check_expiry_date()

    def is_health_check_near_expiry(self, days=30):
        """Giấy khám sắp hết hạn (mặc định 30 ngày)"""
        expiry = self.health_check_expiry_date()
        if not expiry:
            return False
        return 0 <= (expiry - date.today()).days <= days

    def __repr__(self):
        return f'<User {self.email}>'


class Table(db.Model):
    """Model Table - Quản lý bàn ăn"""
    __tablename__ = 'tables'
    
    table_id = db.Column(db.Integer, primary_key=True)
    table_number = db.Column(db.String(10), unique=True, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='available')  # available, occupied, reserved
    location = db.Column(db.String(50))  # indoor, outdoor, vip
    
    # Relationships
    reservations = db.relationship('Reservation', backref='table', lazy=True)
    orders = db.relationship('Order', backref='table', lazy=True)
    
    def __repr__(self):
        return f'<Table {self.table_number}>'


class Reservation(db.Model):
    """Model Reservation - Quản lý đặt bàn"""
    __tablename__ = 'reservations'

    reservation_id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey('tables.table_id'), nullable=False)
    reservation_time = db.Column(db.DateTime, nullable=False)
    number_of_guests = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, completed, cancelled, deposit_required
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Tiền cọc (cho bàn thứ 2 trở đi cùng thời điểm)
    deposit_amount = db.Column(db.Float, default=0)
    deposit_paid = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Reservation {self.reservation_id}>'


class Menu(db.Model):
    """Model Menu - Quản lý thực đơn"""
    __tablename__ = 'menu'
    
    menu_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)  # appetizer, main, dessert, drink
    image_url = db.Column(db.String(255))
    available = db.Column(db.Boolean, default=True)
    preparation_time = db.Column(db.Integer, default=15)  # minutes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    calories = db.Column(db.Integer, nullable=True)

    
    # Relationships
    order_items = db.relationship('OrderItem', backref='menu_item', lazy=True)
    
    def __repr__(self):
        return f'<Menu {self.name}>'


class Order(db.Model):
    """Model Order - Quản lý đơn hàng"""
    __tablename__ = 'orders'

    order_id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey('tables.table_id'))
    order_type = db.Column(db.String(20), nullable=False)  # dine-in, takeaway, delivery
    status = db.Column(db.String(20), default='pending')  # pending, preparing, ready, completed, cancelled, delivering
    order_time = db.Column(db.DateTime, default=datetime.utcnow)
    completed_time = db.Column(db.DateTime)
    total_amount = db.Column(db.Float, default=0.0)
    delivery_address = db.Column(db.String(255))
    notes = db.Column(db.Text)

    # Shipper giao hàng (cho đơn delivery)
    shipper_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)
    shipper = db.relationship('User', foreign_keys=[shipper_id], backref='delivery_orders')

    # Relationships
    order_items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    payment = db.relationship('Payment', backref='order', uselist=False, lazy=True)
    feedback = db.relationship('Feedback', backref='order', uselist=False, lazy=True)
    
    def calculate_total(self):
        """Tính tổng tiền đơn hàng"""
        total = sum(item.price * item.quantity for item in self.order_items)
        self.total_amount = total
        return total
    
    def __repr__(self):
        return f'<Order {self.order_id}>'


class OrderItem(db.Model):
    """Model OrderItem - Chi tiết món trong đơn hàng"""
    __tablename__ = 'order_items'

    order_item_id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.order_id'), nullable=False)
    menu_id = db.Column(db.Integer, db.ForeignKey('menu.menu_id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, preparing, completed
    notes = db.Column(db.String(255))

    # Đầu bếp nấu món này
    chef_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)
    chef = db.relationship('User', foreign_keys=[chef_id], backref='cooked_items')

    def __repr__(self):
        return f'<OrderItem {self.order_item_id}>'


class Payment(db.Model):
    """Model Payment - Quản lý thanh toán"""
    __tablename__ = 'payments'
    
    payment_id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.order_id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)  # cash, card, e-wallet
    payment_status = db.Column(db.String(20), default='pending')  # pending, completed, failed
    payment_time = db.Column(db.DateTime)
    transaction_id = db.Column(db.String(100))
    promo_code = db.Column(db.String(50))
    discount_amount = db.Column(db.Float, default=0.0)
    final_amount = db.Column(db.Float)
    
    def __repr__(self):
        return f'<Payment {self.payment_id}>'


from datetime import datetime, date

class Inventory(db.Model):
    """Model Inventory - Quản lý kho nguyên liệu"""
    __tablename__ = 'inventory'
    
    item_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Float, nullable=False, default=0)
    unit = db.Column(db.String(20), nullable=False)  # kg, liter, piece
    unit_cost = db.Column(db.Float, default=0)  # Giá vốn trên mỗi đơn vị (VND)
    threshold = db.Column(db.Float, default=10)  # Ngưỡng cảnh báo
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    supplier = db.Column(db.String(100))
    ai_status = db.Column(db.String(20))       # safe | warning | unsafe
    ai_checked_at = db.Column(db.DateTime)
    # ✅ Hạn sử dụng
    expiry_date = db.Column(db.Date, nullable=True)

    def is_low_stock(self):
        """Kiểm tra nguyên liệu sắp hết"""
        return self.quantity <= self.threshold

    def is_expired(self):
        """Kiểm tra nguyên liệu đã hết hạn"""
        return self.expiry_date and self.expiry_date < date.today()

    def is_near_expiry(self, days=3):
        """Kiểm tra nguyên liệu sắp hết hạn (mặc định 3 ngày)"""
        if not self.expiry_date:
            return False
        return 0 <= (self.expiry_date - date.today()).days <= days
    
    inspections = db.relationship(
        "InventoryInspection",
        backref="inventory",
        lazy=True,
        order_by="desc(InventoryInspection.inspected_at)"
    )

    def __repr__(self):
        return f'<Inventory {self.name}>'

class Feedback(db.Model):
    """Model Feedback - Đánh giá của khách hàng"""
    __tablename__ = 'feedback'
    
    feedback_id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.order_id'))
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    comment = db.Column(db.Text)
    feedback_type = db.Column(db.String(20), default='general')  # food, service, general
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    response = db.Column(db.Text)  # Admin response
    
    def __repr__(self):
        return f'<Feedback {self.feedback_id}>'


class Promotion(db.Model):
    """Model Promotion - Quản lý khuyến mãi"""
    __tablename__ = 'promotions'
    
    promo_id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text)
    discount_percent = db.Column(db.Float, nullable=False)
    discount_amount = db.Column(db.Float)
    min_order_amount = db.Column(db.Float, default=0)
    max_discount = db.Column(db.Float)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    active = db.Column(db.Boolean, default=True)
    usage_limit = db.Column(db.Integer)
    usage_count = db.Column(db.Integer, default=0)
    
    def is_valid(self):
        """Kiểm tra mã khuyến mãi còn hiệu lực"""
        now = datetime.utcnow()
        if not self.active:
            return False
        if now < self.start_date or now > self.end_date:
            return False
        if self.usage_limit and self.usage_count >= self.usage_limit:
            return False
        return True
    
    def __repr__(self):
        return f'<Promotion {self.code}>'

class MenuIngredient(db.Model):
    """Model MenuIngredient - Liên kết món ăn với nguyên liệu"""
    __tablename__ = 'menu_ingredients'

    id = db.Column(db.Integer, primary_key=True)
    menu_id = db.Column(db.Integer, db.ForeignKey('menu.menu_id'), nullable=False)
    inventory_id = db.Column(db.Integer, db.ForeignKey('inventory.item_id'), nullable=False)
    quantity_needed = db.Column(db.Float, nullable=False)  # Số lượng cần cho 1 phần

    # Relationships
    menu = db.relationship('Menu', backref=db.backref('ingredients', lazy=True))
    inventory = db.relationship('Inventory', backref=db.backref('used_in_menu', lazy=True))

    def __repr__(self):
        return f'<MenuIngredient {self.menu_id}-{self.inventory_id}>'


class InventoryInspection(db.Model):
    __tablename__ = "inventory_inspection"

    id = db.Column(db.Integer, primary_key=True)

    inventory_id = db.Column(
        db.Integer,
        db.ForeignKey("inventory.item_id"),
        nullable=False
    )

    image_url = db.Column(db.String(255))
    ai_status = db.Column(db.String(20))  
    # safe | warning | unsafe

    ai_issues = db.Column(db.Text)
    ai_confidence = db.Column(db.Float)

    ai_recommendation = db.Column(db.Text)

    inspected_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )
