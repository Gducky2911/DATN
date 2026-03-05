
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, User, Menu, Table, Order, OrderItem, Payment, Inventory, Feedback, Promotion, Reservation, InventoryInspection, MenuIngredient
from datetime import datetime, timedelta
from sqlalchemy import func
from werkzeug.utils import secure_filename
from openai import OpenAI
import os, json, base64
from config import Config

bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    """Decorator để kiểm tra quyền admin"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Bạn không có quyền truy cập trang này.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def allowed_file(filename):
    """Kiểm tra file upload hợp lệ"""
    from flask import current_app
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


@bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    """Dashboard admin - Thống kê tổng quan"""
    # Thống kê users
    total_customers = User.query.filter_by(role='customer').count()
    total_employees = User.query.filter_by(role='employee').count()
    
    # Thống kê đơn hàng
    total_orders = Order.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()
    completed_orders = Order.query.filter_by(status='completed').count()
    
    # Doanh thu
    total_revenue = db.session.query(func.sum(Payment.final_amount)).filter(
        Payment.payment_status == 'completed'
    ).scalar() or 0

    # Doanh thu hôm nay
    today_revenue = db.session.query(func.sum(Payment.final_amount)).filter(
        Payment.payment_status == 'completed',
        func.date(Payment.payment_time) == datetime.utcnow().date()
    ).scalar() or 0

    # Doanh thu tháng này
    month_revenue = db.session.query(func.sum(Payment.final_amount)).filter(
        Payment.payment_status == 'completed',
        func.extract('year', Payment.payment_time) == datetime.utcnow().year,
        func.extract('month', Payment.payment_time) == datetime.utcnow().month
    ).scalar() or 0

    total_ingredient_cost = db.session.query(
        func.sum(MenuIngredient.quantity_needed * Inventory.unit_cost * OrderItem.quantity)
    ).join(Menu, MenuIngredient.menu_id == Menu.menu_id
    ).join(Inventory, MenuIngredient.inventory_id == Inventory.item_id
    ).join(OrderItem, OrderItem.menu_id == Menu.menu_id
    ).join(Order, OrderItem.order_id == Order.order_id
    ).filter(Order.status == 'completed').scalar() or 0

    total_profit = total_revenue - total_ingredient_cost

    # Chi phí hôm nay
    today_ingredient_cost = db.session.query(
        func.sum(MenuIngredient.quantity_needed * Inventory.unit_cost * OrderItem.quantity)
    ).join(Menu, MenuIngredient.menu_id == Menu.menu_id
    ).join(Inventory, MenuIngredient.inventory_id == Inventory.item_id
    ).join(OrderItem, OrderItem.menu_id == Menu.menu_id
    ).join(Order, OrderItem.order_id == Order.order_id
    ).filter(
        Order.status == 'completed',
        func.date(Order.completed_time) == datetime.utcnow().date()
    ).scalar() or 0

    today_profit = today_revenue - today_ingredient_cost

    # Chi phí tháng này
    month_ingredient_cost = db.session.query(
        func.sum(MenuIngredient.quantity_needed * Inventory.unit_cost * OrderItem.quantity)
    ).join(Menu, MenuIngredient.menu_id == Menu.menu_id
    ).join(Inventory, MenuIngredient.inventory_id == Inventory.item_id
    ).join(OrderItem, OrderItem.menu_id == Menu.menu_id
    ).join(Order, OrderItem.order_id == Order.order_id
    ).filter(
        Order.status == 'completed',
        func.extract('year', Order.completed_time) == datetime.utcnow().year,
        func.extract('month', Order.completed_time) == datetime.utcnow().month
    ).scalar() or 0

    month_profit = month_revenue - month_ingredient_cost

    # Tỷ lệ lợi nhuận (%)
    profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
    
    # Món bán chạy
    top_dishes = db.session.query(
        Menu.name,
        func.sum(OrderItem.quantity).label('total_sold')
    ).join(OrderItem).join(Order).filter(
        Order.status == 'completed'
    ).group_by(Menu.menu_id).order_by(func.sum(OrderItem.quantity).desc()).limit(5).all()
    
    # Đánh giá trung bình
    avg_rating = db.session.query(func.avg(Feedback.rating)).scalar() or 0
    
    # Nguyên liệu sắp hết
    low_stock_items = Inventory.query.filter(
        Inventory.quantity <= Inventory.threshold
    ).count()
    
    revenue_chart = []
    for i in range(6, -1, -1):
        date = datetime.utcnow().date() - timedelta(days=i)
        revenue = db.session.query(func.sum(Payment.final_amount)).filter(
            Payment.payment_status == 'completed',
            func.date(Payment.payment_time) == date
        ).scalar() or 0
        revenue_chart.append({
            'date': date.strftime('%d/%m'),
            'revenue': float(revenue)
        })
    
    # Đơn hàng gần đây
    recent_orders = Order.query.order_by(Order.order_time.desc()).limit(10).all()
    
    return render_template('admin/dashboard.html',
                         total_customers=total_customers,
                         total_employees=total_employees,
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         completed_orders=completed_orders,
                         total_revenue=total_revenue,
                         today_revenue=today_revenue,
                         month_revenue=month_revenue,
                         total_profit=total_profit,
                         today_profit=today_profit,
                         month_profit=month_profit,
                         profit_margin=profit_margin,
                         total_ingredient_cost=total_ingredient_cost,
                         top_dishes=top_dishes,
                         avg_rating=avg_rating,
                         low_stock_items=low_stock_items,
                         revenue_chart=revenue_chart,
                         recent_orders=recent_orders)


# ===== QUẢN LÝ USERS =====
@bp.route('/users')
@login_required
@admin_required
def users():
    """Quản lý người dùng"""
    role_filter = request.args.get('role', 'all')
    
    query = User.query
    
    if role_filter != 'all':
        query = query.filter_by(role=role_filter)
    
    users = query.order_by(User.created_at.desc()).all()
    
    return render_template('admin/users.html',
                         users=users,
                         role_filter=role_filter)


@bp.route('/user/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    """Thêm người dùng mới"""
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        role = request.form.get('role')
        employee_type = request.form.get('employee_type') if role == 'employee' else None
        password = request.form.get('password')
        
        # Validation
        if not all([name, email, role, password]):
            flash('Vui lòng điền đầy đủ thông tin.', 'warning')
            return redirect(url_for('admin.add_user'))
        
        if User.query.filter_by(email=email).first():
            flash('Email đã tồn tại.', 'warning')
            return redirect(url_for('admin.add_user'))
        
        new_user = User(
            name=name,
            email=email,
            phone=phone,
            role=role,
            employee_type=employee_type
        )
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Đã thêm người dùng mới.', 'success')
        return redirect(url_for('admin.users'))
    
    return render_template('admin/add_user.html')


@bp.route('/user/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    """Chỉnh sửa người dùng"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        user.name = request.form.get('name')
        user.phone = request.form.get('phone')
        user.role = request.form.get('role')
        user.employee_type = request.form.get('employee_type') if user.role == 'employee' else None
        user.active = True if request.form.get('active') else False

        health_check_date = request.form.get('health_check_date')

        if user.role == 'employee' and health_check_date:
            user.health_check_date = datetime.strptime(health_check_date, '%Y-%m-%d').date()
        elif user.role != 'employee':
            user.health_check_date = None
        # Đổi mật khẩu nếu có
        new_password = request.form.get('new_password')
        if new_password:
            user.set_password(new_password)
        
        db.session.commit()
        
        flash('Đã cập nhật thông tin người dùng.', 'success')
        return redirect(url_for('admin.users'))
    
    return render_template('admin/edit_user.html', user=user)


@bp.route('/user/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Xóa người dùng"""
    user = User.query.get_or_404(user_id)
    
    # Không cho xóa chính mình
    if user.user_id == current_user.user_id:
        flash('Không thể xóa tài khoản của chính bạn.', 'danger')
        return redirect(url_for('admin.users'))
    
    db.session.delete(user)
    db.session.commit()
    
    flash('Đã xóa người dùng.', 'success')
    return redirect(url_for('admin.users'))

@bp.route('/user/<int:user_id>/toggle', methods=['POST', 'GET'])
@login_required
@admin_required
def toggle_user_status(user_id):
    """Bật/tắt trạng thái hoạt động của người dùng"""
    user = User.query.get_or_404(user_id)
    
    # Không cho khóa chính mình
    if user.user_id == current_user.user_id:
        flash('Không thể thay đổi trạng thái tài khoản của chính bạn.', 'danger')
        return redirect(url_for('admin.users'))
    
    user.active = not user.active  # Đảo ngược trạng thái
    db.session.commit()
    
    flash(f"Đã {'kích hoạt' if user.active else 'vô hiệu hóa'} tài khoản của {user.name}.", 'success')
    return redirect(url_for('admin.users'))



# ===== QUẢN LÝ MENU =====
@bp.route('/menu')
@login_required
@admin_required
def menu():
    """Quản lý thực đơn"""
    category_filter = request.args.get('category', 'all')
    
    query = Menu.query
    
    if category_filter != 'all':
        query = query.filter_by(category=category_filter)
    
    menu_items = query.order_by(Menu.name).all()
    
    return render_template('admin/menu.html',
                         menu_items=menu_items,
                         category_filter=category_filter)


@bp.route('/menu/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_menu_item():
    """Thêm món ăn mới"""
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        category = request.form.get('category')
        preparation_time = request.form.get('preparation_time', 15)
        available = True if request.form.get('available') else False
        
        # Upload hình ảnh
        image_url = 'default.jpg'
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Tạo tên file unique
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_{filename}"
                
                from flask import current_app
                filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                image_url = filename
        
        new_item = Menu(
            name=name,
            description=description,
            price=float(price),
            category=category,
            image_url=image_url,
            available=available,
            preparation_time=int(preparation_time)
        )
        
        db.session.add(new_item)
        db.session.commit()
        
        flash('Đã thêm món ăn mới.', 'success')
        return redirect(url_for('admin.menu'))
    
    return render_template('admin/add_menu_item.html')


@bp.route('/menu/<int:menu_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_menu_item(menu_id):
    menu_item = Menu.query.get_or_404(menu_id)

    if request.method == 'POST':
        # Update basic info
        menu_item.name = request.form.get('name')
        menu_item.description = request.form.get('description')
        menu_item.price = float(request.form.get('price'))
        menu_item.category = request.form.get('category')
        menu_item.preparation_time = int(request.form.get('preparation_time', 15))
        menu_item.available = True if request.form.get('available') else False

        # Handle image upload (ONLY if user selects new image)
        file = request.files.get('image')

        if file and file.filename and allowed_file(file.filename):
            from flask import current_app

            upload_folder = current_app.config['UPLOAD_FOLDER']

            # 1️⃣ Delete old image (if exists)
            if menu_item.image_url:
                old_path = os.path.join(upload_folder, menu_item.image_url)
                if os.path.exists(old_path):
                    os.remove(old_path)

            # 2️⃣ Save new image
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            new_filename = f"{timestamp}_{filename}"

            new_path = os.path.join(upload_folder, new_filename)
            file.save(new_path)

            # 3️⃣ Update DB
            menu_item.image_url = new_filename

        db.session.commit()
        flash('Đã cập nhật món ăn.', 'success')
        return redirect(url_for('admin.menu'))

    return render_template('admin/edit_menu_item.html', menu_item=menu_item)



@bp.route('/menu/<int:menu_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_menu_item(menu_id):
    """Xóa món ăn"""
    menu_item = Menu.query.get_or_404(menu_id)
    
    db.session.delete(menu_item)
    db.session.commit()
    
    flash('Đã xóa món ăn.', 'success')
    return redirect(url_for('admin.menu'))

@bp.route('/menu/toggle/<int:menu_id>')
@login_required
@admin_required
def toggle_menu_availability(menu_id):
    menu_item = Menu.query.get_or_404(menu_id)
    menu_item.available = not menu_item.available  # Đảo trạng thái
    db.session.commit()
    flash(f"Đã {'mở' if menu_item.available else 'đóng'} món '{menu_item.name}'.", "info")
    return redirect(url_for('admin.menu'))


# ===== QUẢN LÝ BÀN =====
@bp.route('/tables')
@login_required
@admin_required
def tables():
    """Quản lý bàn"""
    tables = Table.query.order_by(Table.table_number).all()
    
    return render_template('admin/tables.html', tables=tables)


@bp.route('/table/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_table():
    """Thêm bàn mới"""
    if request.method == 'POST':
        table_number = request.form.get('table_number')
        capacity = request.form.get('capacity')
        location = request.form.get('location', 'indoor')
        
        if Table.query.filter_by(table_number=table_number).first():
            flash('Số bàn đã tồn tại.', 'warning')
            return redirect(url_for('admin.add_table'))
        
        new_table = Table(
            table_number=table_number,
            capacity=int(capacity),
            location=location,
            status='available'
        )
        
        db.session.add(new_table)
        db.session.commit()
        
        flash('Đã thêm bàn mới.', 'success')
        return redirect(url_for('admin.tables'))
    
    return render_template('admin/add_table.html')


@bp.route('/table/<int:table_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_table(table_id):
    """Chỉnh sửa bàn"""
    table = Table.query.get_or_404(table_id)
    
    if request.method == 'POST':
        table.table_number = request.form.get('table_number')
        table.capacity = int(request.form.get('capacity'))
        table.location = request.form.get('location')
        table.status = request.form.get('status')
        
        db.session.commit()
        
        flash('Đã cập nhật thông tin bàn.', 'success')
        return redirect(url_for('admin.tables'))
    
    return render_template('admin/edit_table.html', table=table)


@bp.route('/table/<int:table_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_table(table_id):
    """Xóa bàn"""
    table = Table.query.get_or_404(table_id)
    
    db.session.delete(table)
    db.session.commit()
    
    flash('Đã xóa bàn.', 'success')
    return redirect(url_for('admin.tables'))


# ===== QUẢN LÝ ĐƠN HÀNG =====
@bp.route('/orders')
@login_required
@admin_required
def orders():
    """Quản lý đơn hàng"""
    status_filter = request.args.get('status', 'all')
    type_filter = request.args.get('type', 'all')
    
    query = Order.query
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    if type_filter != 'all':
        query = query.filter_by(order_type=type_filter)
    
    orders = query.order_by(Order.order_time.desc()).all()
    
    return render_template('admin/orders.html',
                         orders=orders,
                         status_filter=status_filter,
                         type_filter=type_filter)


@bp.route('/order/<int:order_id>')
@login_required
@admin_required
def order_detail(order_id):
    """Chi tiết đơn hàng"""
    order = Order.query.get_or_404(order_id)
    
    return render_template('admin/order_detail.html', order=order)


# ===== QUẢN LÝ KHO =====
@bp.route('/inventory')
@login_required
@admin_required
def inventory():
    """Quản lý kho nguyên liệu"""
    inventory_items = Inventory.query.order_by(Inventory.name).all()
    
    return render_template('admin/inventory.html', inventory=inventory_items)


@bp.route('/inventory/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_inventory_item():
    """Thêm nguyên liệu"""
    if request.method == 'POST':
        name = request.form.get('name')
        quantity = request.form.get('quantity')
        unit = request.form.get('unit')
        unit_cost = request.form.get('unit_cost', 0)
        threshold = request.form.get('threshold')
        supplier = request.form.get('supplier')

        new_item = Inventory(
            name=name,
            quantity=float(quantity),
            unit=unit,
            unit_cost=float(unit_cost),
            threshold=float(threshold),
            supplier=supplier
        )

        db.session.add(new_item)
        db.session.commit()

        flash('Đã thêm nguyên liệu mới.', 'success')
        return redirect(url_for('admin.inventory'))

    return render_template('admin/add_inventory_item.html')


@bp.route('/inventory/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_inventory_item(item_id):
    """Chỉnh sửa nguyên liệu"""
    item = Inventory.query.get_or_404(item_id)
    
    if request.method == 'POST':
        item.name = request.form.get('name')
        item.quantity = float(request.form.get('quantity'))
        item.unit = request.form.get('unit')
        item.unit_cost = float(request.form.get('unit_cost', 0))
        item.threshold = float(request.form.get('threshold'))
        item.supplier = request.form.get('supplier')
        item.last_updated = datetime.utcnow()

        db.session.commit()

        flash('Đã cập nhật nguyên liệu.', 'success')
        return redirect(url_for('admin.inventory'))

    return render_template('admin/edit_inventory_item.html', item=item)


@bp.route('/inventory/<int:item_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_inventory_item(item_id):
    """Xóa nguyên liệu"""
    item = Inventory.query.get_or_404(item_id)
    
    db.session.delete(item)
    db.session.commit()
    
    flash('Đã xóa nguyên liệu.', 'success')
    return redirect(url_for('admin.inventory'))

@bp.route("/inventory/<int:item_id>/inspect", methods=["POST"])
@login_required
@admin_required
def inspect_inventory(item_id):
    item = Inventory.query.get_or_404(item_id)

    file = request.files.get("image")
    if not file:
        flash("Vui lòng tải lên hình ảnh nguyên liệu", "danger")
        return redirect(url_for("admin.inventory"))

    filename = secure_filename(file.filename)

    upload_folder = os.path.join(
        current_app.root_path,
        "static/uploads/inventory"
    )
    os.makedirs(upload_folder, exist_ok=True)

    image_path = os.path.join(upload_folder, filename)
    file.save(image_path)

    image_url = f"/static/uploads/inventory/{filename}"

    public_base = current_app.config["PUBLIC_BASE_URL"]
    public_image_url = public_base + image_url

    client = OpenAI(api_key=current_app.config["OPENAI_API_KEY"])

    prompt = """
        Bạn là hệ thống AI kiểm tra an toàn vệ sinh thực phẩm.

        NHIỆM VỤ:
        Phân tích hình ảnh nguyên liệu thực phẩm.

        QUY TẮC BẮT BUỘC:
        - CHỈ trả về JSON thuần
        - KHÔNG markdown
        - KHÔNG ```json
        - KHÔNG giải thích
        - KHÔNG thêm text bên ngoài

        FORMAT CHÍNH XÁC (bắt buộc):
        {
        "status": "safe" | "warning" | "unsafe",
        "issues": ["mô tả ngắn gọn"],
        "confidence": 0.0,
        "recommendation": "khuyến nghị"
        }

        Nếu không chắc chắn → status = "warning"
        """


    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": public_image_url
                        }
                    }
                ]
            }
        ],
        temperature=0.2,
        max_tokens=300
    )

    ai_result = response.choices[0].message.content

    # -----------------------------
    # 3. PARSE JSON
    # -----------------------------
    try:
        data = json.loads(ai_result)
    except Exception:
        flash("AI phân tích thất bại (JSON không hợp lệ)", "danger")
        return redirect(url_for("admin.inventory"))

    inspection = InventoryInspection(
        inventory_id=item.item_id,
        image_url=image_url,
        ai_status=data.get("status"),
        ai_issues=", ".join(data.get("issues", [])),
        ai_confidence=data.get("confidence"),
        ai_recommendation=data.get("recommendation"),
        inspected_at=datetime.utcnow()
    )
    # 🔥 CẬP NHẬT TRẠNG THÁI AI VÀO INVENTORY
    item.ai_status = data.get("status")
    item.ai_checked_at = datetime.utcnow()

    db.session.add(inspection)
    db.session.commit()

    flash("🤖 Đã phân tích VSATTP bằng AI", "success")
    return redirect(url_for("admin.inventory"))



# ===== QUẢN LÝ KHUYẾN MÃI =====
@bp.route('/promotions')
@login_required
@admin_required
def promotions():
    """Quản lý khuyến mãi"""
    promotions = Promotion.query.order_by(Promotion.start_date.desc()).all()

    
    return render_template('admin/promotions.html',
                         promotions=promotions)


@bp.route('/promotion/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_promotion():
    """Thêm khuyến mãi"""
    if request.method == 'POST':
        code = request.form.get('code').upper()
        description = request.form.get('description')
        discount_percent = request.form.get('discount_percent')
        min_order_amount = request.form.get('min_order_amount', 0)
        max_discount = request.form.get('max_discount')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        usage_limit = request.form.get('usage_limit')
        active = True if request.form.get('active') else False
        
        if Promotion.query.filter_by(code=code).first():
            flash('Mã khuyến mãi đã tồn tại.', 'warning')
            return redirect(url_for('admin.add_promotion'))
        
        new_promo = Promotion(
            code=code,
            description=description,
            discount_percent=float(discount_percent),
            min_order_amount=float(min_order_amount),
            max_discount=float(max_discount) if max_discount else None,
            start_date=datetime.strptime(start_date, '%Y-%m-%d'),
            end_date=datetime.strptime(end_date, '%Y-%m-%d'),
            usage_limit=int(usage_limit) if usage_limit else None,
            active=active
        )
        
        db.session.add(new_promo)
        db.session.commit()
        
        flash('Đã thêm khuyến mãi mới.', 'success')
        return redirect(url_for('admin.promotions'))
    
    return render_template('admin/add_promotion.html')


@bp.route('/promotion/<int:promo_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_promotion(promo_id):
    """Chỉnh sửa khuyến mãi"""
    promo = Promotion.query.get_or_404(promo_id)
    
    if request.method == 'POST':
        promo.code = request.form.get('code').upper()
        promo.description = request.form.get('description')
        promo.discount_percent = float(request.form.get('discount_percent'))
        promo.min_order_amount = float(request.form.get('min_order_amount', 0))
        max_discount = request.form.get('max_discount')
        promo.max_discount = float(max_discount) if max_discount else None
        promo.start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
        promo.end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
        usage_limit = request.form.get('usage_limit')
        promo.usage_limit = int(usage_limit) if usage_limit else None
        promo.active = True if request.form.get('active') else False
        
        db.session.commit()
        
        flash('Đã cập nhật khuyến mãi.', 'success')
        return redirect(url_for('admin.promotions'))
    
    return render_template('admin/edit_promotion.html', promo=promo)


@bp.route('/promotion/<int:promo_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_promotion(promo_id):
    """Xóa khuyến mãi"""
    promo = Promotion.query.get_or_404(promo_id)
    
    db.session.delete(promo)
    db.session.commit()
    
    flash('Đã xóa khuyến mãi.', 'success')
    return redirect(url_for('admin.promotions'))


# ===== FEEDBACK =====
@bp.route('/feedback')
@login_required
@admin_required
def feedback():
    """Xem feedback từ khách hàng"""
    feedbacks = Feedback.query.order_by(Feedback.created_at.desc()).all()
    
    return render_template('admin/feedback.html',
                         feedbacks=feedbacks)


@bp.route('/feedback/<int:feedback_id>/respond', methods=['POST'])
@login_required
@admin_required
def respond_feedback(feedback_id):
    """Phản hồi feedback"""
    feedback = Feedback.query.get_or_404(feedback_id)
    response = request.form.get('response')
    
    feedback.response = response
    db.session.commit()
    
    flash('Đã phản hồi feedback.', 'success')
    return redirect(url_for('admin.feedback'))


# ===== BÁO CÁO & THỐNG KÊ =====
@bp.route('/reports')
@login_required
@admin_required
def reports():
    """Báo cáo & thống kê"""
    # Lấy tham số thời gian
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    # Mặc định: 30 ngày gần đây
    if not start_date_str:
        start_date = datetime.utcnow().date() - timedelta(days=30)
    else:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    
    if not end_date_str:
        end_date = datetime.utcnow().date()
    else:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    
    # Doanh thu theo ngày
    daily_revenue = db.session.query(
        func.date(Payment.payment_time).label('date'),
        func.sum(Payment.final_amount).label('revenue')
    ).filter(
        Payment.payment_status == 'completed',
        func.date(Payment.payment_time).between(start_date, end_date)
    ).group_by(func.date(Payment.payment_time)).order_by('date').all()
    
    # Món bán chạy
    top_dishes = db.session.query(
        Menu.name,
        func.sum(OrderItem.quantity).label('total_sold'),
        func.sum(OrderItem.quantity * OrderItem.price).label('revenue')
    ).join(OrderItem).join(Order).filter(
        Order.status == 'completed',
        func.date(Order.completed_time).between(start_date, end_date)
    ).group_by(Menu.menu_id).order_by(func.sum(OrderItem.quantity).desc()).limit(10).all()
    
    # Thống kê theo loại đơn
    order_types = db.session.query(
        Order.order_type,
        func.count(Order.order_id).label('count'),
        func.sum(Order.total_amount).label('revenue')
    ).filter(
        Order.status == 'completed',
        func.date(Order.completed_time).between(start_date, end_date)
    ).group_by(Order.order_type).all()
    
    # Khách hàng top
    top_customers = db.session.query(
        User.name,
        User.email,
        func.count(Order.order_id).label('order_count'),
        func.sum(Order.total_amount).label('total_spent')
    ).join(Order, User.user_id == Order.customer_id).filter(
        Order.status == 'completed',
        func.date(Order.completed_time).between(start_date, end_date)
    ).group_by(User.user_id).order_by(func.sum(Order.total_amount).desc()).limit(10).all()
    
    return render_template('admin/reports.html',
                         daily_revenue=daily_revenue,
                         top_dishes=top_dishes,
                         order_types=order_types,
                         top_customers=top_customers,
                         start_date=start_date,
                         end_date=end_date)


# ===== QUẢN LÝ NGUYÊN LIỆU MÓN ĂN =====
@bp.route('/menu/<int:menu_id>/ingredients')
@login_required
@admin_required
def menu_ingredients(menu_id):
    """Xem và quản lý nguyên liệu của món ăn"""
    menu_item = Menu.query.get_or_404(menu_id)
    inventory_items = Inventory.query.order_by(Inventory.name).all()

    return render_template('admin/menu_ingredients.html',
                         menu_item=menu_item,
                         inventory_items=inventory_items)


@bp.route('/menu/<int:menu_id>/ingredients/add', methods=['POST'])
@login_required
@admin_required
def add_menu_ingredient(menu_id):
    """Thêm nguyên liệu cho món ăn"""
    menu_item = Menu.query.get_or_404(menu_id)

    inventory_id = request.form.get('inventory_id')
    quantity_needed = request.form.get('quantity_needed')

    if not inventory_id or not quantity_needed:
        flash('Vui lòng chọn nguyên liệu và số lượng.', 'warning')
        return redirect(url_for('admin.menu_ingredients', menu_id=menu_id))

    # Validate số lượng phải là số dương
    try:
        quantity_needed_float = float(quantity_needed)
        if quantity_needed_float <= 0:
            flash('Số lượng nguyên liệu phải là số dương.', 'warning')
            return redirect(url_for('admin.menu_ingredients', menu_id=menu_id))
    except ValueError:
        flash('Số lượng nguyên liệu không hợp lệ.', 'warning')
        return redirect(url_for('admin.menu_ingredients', menu_id=menu_id))

    # Kiểm tra đã có nguyên liệu này chưa
    existing = MenuIngredient.query.filter_by(
        menu_id=menu_id,
        inventory_id=inventory_id
    ).first()

    if existing:
        flash('Nguyên liệu này đã được thêm. Vui lòng sửa số lượng thay vì thêm mới.', 'warning')
        return redirect(url_for('admin.menu_ingredients', menu_id=menu_id))

    new_ingredient = MenuIngredient(
        menu_id=menu_id,
        inventory_id=int(inventory_id),
        quantity_needed=float(quantity_needed)
    )

    db.session.add(new_ingredient)
    db.session.commit()

    flash('Đã thêm nguyên liệu cho món ăn.', 'success')
    return redirect(url_for('admin.menu_ingredients', menu_id=menu_id))


@bp.route('/menu/ingredient/<int:ingredient_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_menu_ingredient(ingredient_id):
    """Sửa số lượng nguyên liệu"""
    ingredient = MenuIngredient.query.get_or_404(ingredient_id)

    quantity_needed = request.form.get('quantity_needed')
    if quantity_needed:
        try:
            quantity_needed_float = float(quantity_needed)
            if quantity_needed_float <= 0:
                flash('Số lượng nguyên liệu phải là số dương.', 'warning')
                return redirect(url_for('admin.menu_ingredients', menu_id=ingredient.menu_id))
            ingredient.quantity_needed = quantity_needed_float
            db.session.commit()
            flash('Đã cập nhật số lượng nguyên liệu.', 'success')
        except ValueError:
            flash('Số lượng nguyên liệu không hợp lệ.', 'warning')

    return redirect(url_for('admin.menu_ingredients', menu_id=ingredient.menu_id))


@bp.route('/menu/ingredient/<int:ingredient_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_menu_ingredient(ingredient_id):
    """Xóa nguyên liệu khỏi món ăn"""
    ingredient = MenuIngredient.query.get_or_404(ingredient_id)
    menu_id = ingredient.menu_id

    db.session.delete(ingredient)
    db.session.commit()

    flash('Đã xóa nguyên liệu khỏi món ăn.', 'success')
    return redirect(url_for('admin.menu_ingredients', menu_id=menu_id))


# ===== QUẢN LÝ CHEF/SHIPPER =====
@bp.route('/order-item/<int:item_id>/assign-chef', methods=['POST'])
@login_required
@admin_required
def assign_chef(item_id):
    """Admin gán/đổi đầu bếp cho món"""
    order_item = OrderItem.query.get_or_404(item_id)

    chef_id = request.form.get('chef_id')
    if chef_id:
        chef = User.query.filter_by(
            user_id=chef_id,
            role='employee',
            employee_type='chef'
        ).first()

        if chef:
            order_item.chef_id = chef.user_id
            db.session.commit()
            flash(f'Đã gán đầu bếp {chef.name} cho món {order_item.menu_item.name}.', 'success')
        else:
            flash('Đầu bếp không hợp lệ.', 'danger')
    else:
        order_item.chef_id = None
        db.session.commit()
        flash('Đã bỏ gán đầu bếp.', 'info')

    return redirect(url_for('admin.order_detail', order_id=order_item.order_id))


@bp.route('/order/<int:order_id>/assign-shipper', methods=['POST'])
@login_required
@admin_required
def assign_shipper(order_id):
    """Admin gán/đổi shipper cho đơn hàng"""
    order = Order.query.get_or_404(order_id)

    if order.order_type != 'delivery':
        flash('Chỉ có thể gán shipper cho đơn giao hàng.', 'warning')
        return redirect(url_for('admin.order_detail', order_id=order_id))

    shipper_id = request.form.get('shipper_id')
    if shipper_id:
        shipper = User.query.filter_by(
            user_id=shipper_id,
            role='employee',
            employee_type='delivery'
        ).first()

        if shipper:
            order.shipper_id = shipper.user_id
            if order.status == 'ready':
                order.status = 'delivering'
            db.session.commit()
            flash(f'Đã gán shipper {shipper.name} cho đơn hàng #{order.order_id}.', 'success')
        else:
            flash('Shipper không hợp lệ.', 'danger')
    else:
        order.shipper_id = None
        db.session.commit()
        flash('Đã bỏ gán shipper.', 'info')

    return redirect(url_for('admin.order_detail', order_id=order_id))


# ===== QUẢN LÝ ĐẶT BÀN (xác nhận cọc) =====
@bp.route('/reservations')
@login_required
@admin_required
def reservations():
    """Quản lý đặt bàn"""
    status_filter = request.args.get('status', 'all')

    query = Reservation.query.options(
        db.joinedload(Reservation.table),
        db.joinedload(Reservation.customer)
    )

    if status_filter != 'all':
        query = query.filter_by(status=status_filter)

    reservations = query.order_by(Reservation.reservation_time.desc()).all()

    return render_template('admin/reservations.html',
                         reservations=reservations,
                         status_filter=status_filter)


@bp.route('/reservation/<int:reservation_id>/confirm-deposit', methods=['POST'])
@login_required
@admin_required
def confirm_deposit(reservation_id):
    """Xác nhận đã nhận tiền cọc"""
    reservation = Reservation.query.get_or_404(reservation_id)

    if reservation.deposit_amount > 0:
        reservation.deposit_paid = True
        reservation.status = 'pending'  # Chuyển sang pending để waiter xác nhận
        db.session.commit()
        flash(f'Đã xác nhận nhận cọc {reservation.deposit_amount:,.0f}đ.', 'success')
    else:
        flash('Đơn đặt bàn này không yêu cầu cọc.', 'info')

    return redirect(url_for('admin.reservations'))


# ===== API lấy danh sách chef/shipper =====
@bp.route('/api/chefs')
@login_required
@admin_required
def get_chefs():
    """API lấy danh sách đầu bếp"""
    chefs = User.query.filter_by(
        role='employee',
        employee_type='chef',
        active=True
    ).all()

    return jsonify([{
        'user_id': c.user_id,
        'name': c.name
    } for c in chefs])


@bp.route('/api/shippers')
@login_required
@admin_required
def get_shippers():
    """API lấy danh sách shipper"""
    shippers = User.query.filter_by(
        role='employee',
        employee_type='delivery',
        active=True
    ).all()

    return jsonify([{
        'user_id': s.user_id,
        'name': s.name,
        'phone': s.phone
    } for s in shippers])
