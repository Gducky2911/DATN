"""
Customer Routes
Các chức năng dành cho khách hàng
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_required, current_user
from models import db, Menu, Order, OrderItem, Table, Reservation, Payment, Feedback, Promotion, Inventory, MenuIngredient
from datetime import datetime, timedelta
from sqlalchemy import func

# Số tiền cọc cố định cho bàn thứ 2 trở đi (cùng thời điểm)
DEPOSIT_AMOUNT = 200000  # 200.000 VND

bp = Blueprint('customer', __name__, url_prefix='/customer')


def customer_required(f):
    """Decorator để kiểm tra quyền customer"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'customer':
            flash('Bạn không có quyền truy cập trang này.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@bp.route('/dashboard')
@login_required
@customer_required
def dashboard():
    """Dashboard khách hàng"""
    # Thống kê
    total_orders = Order.query.filter_by(customer_id=current_user.user_id).count()
    pending_orders = Order.query.filter_by(
        customer_id=current_user.user_id, 
        status='pending'
    ).count()
    completed_orders = Order.query.filter_by(
        customer_id=current_user.user_id, 
        status='completed'
    ).count()
    
    # Đơn hàng gần đây
    recent_orders = Order.query.filter_by(
        customer_id=current_user.user_id
    ).order_by(Order.order_time.desc()).limit(5).all()
    
    # Đặt bàn sắp tới
    upcoming_reservations = Reservation.query.filter(
        Reservation.customer_id == current_user.user_id,
        Reservation.reservation_time > datetime.utcnow(),
        Reservation.status.in_(['pending', 'confirmed'])
    ).order_by(Reservation.reservation_time).limit(5).all()
    
    return render_template('customer/dashboard.html',
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         completed_orders=completed_orders,
                         recent_orders=recent_orders,
                         upcoming_reservations=upcoming_reservations)


@bp.route('/menu')
@login_required
@customer_required
def menu():
    """Xem menu"""
    category = request.args.get('category', 'all')
    search = request.args.get('search', '')
    
    query = Menu.query.filter_by(available=True)
    
    if category != 'all':
        query = query.filter_by(category=category)
    
    if search:
        query = query.filter(Menu.name.contains(search))
    
    menu_items = query.all()
    
    # Đếm số lượng theo category
    categories = db.session.query(
        Menu.category, 
        func.count(Menu.menu_id)
    ).filter_by(available=True).group_by(Menu.category).all()
    
    return render_template('customer/menu.html',
                         menu_items=menu_items,
                         categories=categories,
                         current_category=category,
                         search=search)


@bp.route('/reservation', methods=['GET', 'POST'])
@login_required
@customer_required
def reservation():
    """Đặt bàn"""
    if request.method == 'POST':
        table_id = request.form.get('table_id')
        reservation_date = request.form.get('reservation_date')
        reservation_time = request.form.get('reservation_time')
        number_of_guests = request.form.get('number_of_guests')
        notes = request.form.get('notes', '')
        confirm_deposit = request.form.get('confirm_deposit')  # Checkbox xác nhận cọc

        # Kiểm tra điền đủ thông tin
        if not all([table_id, reservation_date, reservation_time, number_of_guests]):
            flash('Vui lòng điền đầy đủ thông tin.', 'warning')
            return redirect(url_for('customer.reservation'))

        # Chuyển đổi sang datetime
        try:
            reservation_datetime = datetime.strptime(
                f"{reservation_date} {reservation_time}",
                "%Y-%m-%d %H:%M"
            )
        except ValueError:
            flash('Định dạng ngày/giờ không hợp lệ.', 'warning')
            return redirect(url_for('customer.reservation'))

        # Kiểm tra thời gian hợp lệ (phải ở tương lai)
        if reservation_datetime <= datetime.utcnow():
            flash('Vui lòng chọn thời gian trong tương lai.', 'warning')
            return redirect(url_for('customer.reservation'))

        # Kiểm tra bàn tồn tại
        table = Table.query.get(table_id)
        if not table:
            flash('Bàn không tồn tại.', 'danger')
            return redirect(url_for('customer.reservation'))

        # Kiểm tra số lượng khách phù hợp
        if int(number_of_guests) > table.capacity:
            flash(f'Bàn chỉ chứa tối đa {table.capacity} người.', 'warning')
            return redirect(url_for('customer.reservation'))

        # Kiểm tra bàn đã được đặt chưa (trong khoảng ±2 giờ)
        existing_table = Reservation.query.filter(
            Reservation.table_id == table_id,
            Reservation.status.in_(['pending', 'confirmed']),
            Reservation.reservation_time.between(
                reservation_datetime - timedelta(hours=2),
                reservation_datetime + timedelta(hours=2)
            )
        ).first()

        if existing_table:
            flash('Bàn này đã được đặt vào thời gian đó. Vui lòng chọn bàn hoặc thời gian khác.', 'warning')
            return redirect(url_for('customer.reservation'))

        # KIỂM TRA GIỚI HẠN: User đã đặt bàn khác cùng thời điểm chưa?
        existing_my_reservation = Reservation.query.filter(
            Reservation.customer_id == current_user.user_id,
            Reservation.status.in_(['pending', 'confirmed']),
            Reservation.reservation_time.between(
                reservation_datetime - timedelta(hours=2),
                reservation_datetime + timedelta(hours=2)
            )
        ).first()

        # Nếu đã có bàn cùng thời điểm -> yêu cầu đặt cọc
        requires_deposit = existing_my_reservation is not None
        deposit_amount = DEPOSIT_AMOUNT if requires_deposit else 0

        if requires_deposit and not confirm_deposit:
            flash(f'Bạn đã đặt bàn khác vào thời điểm này. Để đặt thêm bàn, vui lòng xác nhận đặt cọc {DEPOSIT_AMOUNT:,.0f}đ.', 'warning')
            return redirect(url_for('customer.reservation',
                                    need_deposit='true',
                                    table_id=table_id,
                                    reservation_date=reservation_date,
                                    reservation_time=reservation_time,
                                    number_of_guests=number_of_guests,
                                    notes=notes))

        # Tạo đặt bàn mới
        new_reservation = Reservation(
            customer_id=current_user.user_id,
            table_id=table_id,
            reservation_time=reservation_datetime,
            number_of_guests=int(number_of_guests),
            status='deposit_required' if requires_deposit else 'pending',
            notes=notes,
            deposit_amount=deposit_amount,
            deposit_paid=False
        )

        db.session.add(new_reservation)
        db.session.commit()

        if requires_deposit:
            flash(f'Đặt bàn thành công! Bạn cần đặt cọc {deposit_amount:,.0f}đ để xác nhận. Vui lòng thanh toán tại quầy hoặc chuyển khoản.', 'info')
        else:
            flash('Đặt bàn thành công! Chúng tôi sẽ xác nhận sớm nhất.', 'success')
        return redirect(url_for('customer.my_reservations'))

    # Xử lý GET request
    available_tables = Table.query.filter_by(status='available').all()

    # Tính ngày tối thiểu (ít nhất sau 1 giờ)
    min_date = (datetime.utcnow() + timedelta(hours=1)).strftime('%Y-%m-%d')

    # Kiểm tra xem có cần hiển thị form deposit không
    need_deposit = request.args.get('need_deposit') == 'true'

    # Truyền biến vào template
    return render_template(
        'customer/reservation.html',
        available_tables=available_tables,
        min_date=min_date,
        restaurant_name="Nhà hàng AI",
        restaurant_phone="0123 456 789",
        need_deposit=need_deposit,
        deposit_amount=DEPOSIT_AMOUNT,
        prefill_table_id=request.args.get('table_id'),
        prefill_date=request.args.get('reservation_date'),
        prefill_time=request.args.get('reservation_time'),
        prefill_guests=request.args.get('number_of_guests'),
        prefill_notes=request.args.get('notes', '')
    )

@bp.route('/my-reservations')
@login_required
@customer_required
def my_reservations():
    """Xem danh sách đặt bàn của tôi"""
    reservations = Reservation.query.filter_by(
        customer_id=current_user.user_id
    ).order_by(Reservation.reservation_time.desc()).all()
    
    return render_template('customer/my_reservations.html',
                         reservations=reservations)


@bp.route('/order/new', methods=['POST'])
@login_required
@customer_required
def new_order():
    order_type = request.form.get('order_type')
    table_id = request.form.get('table_id') if order_type == 'dine-in' else None
    delivery_address = request.form.get('delivery_address') if order_type == 'delivery' else None
    notes = request.form.get('notes', '')

    cart_items = request.form.getlist('cart_items[]')

    if not cart_items:
        flash('Vui lòng chọn ít nhất một món.', 'warning')
        return redirect(url_for('customer.menu'))

    # Kiểm tra nguyên liệu trước khi đặt (với lock để tránh race condition)
    try:
        insufficient_ingredients = []

        # Thu thập tất cả inventory_id cần kiểm tra
        inventory_ids_to_check = set()
        for item_data in cart_items:
            menu_id, quantity = item_data.split(':')
            menu_item = Menu.query.get(menu_id)
            if menu_item:
                for ingredient in menu_item.ingredients:
                    inventory_ids_to_check.add(ingredient.inventory_id)

        # Lock các inventory rows để tránh race condition
        locked_inventories = {
            inv.item_id: inv
            for inv in Inventory.query.filter(
                Inventory.item_id.in_(inventory_ids_to_check)
            ).with_for_update().all()
        }

        # Kiểm tra đủ nguyên liệu không
        for item_data in cart_items:
            menu_id, quantity = item_data.split(':')
            quantity = int(quantity)
            menu_item = Menu.query.get(menu_id)

            if menu_item:
                for ingredient in menu_item.ingredients:
                    inv = locked_inventories.get(ingredient.inventory_id)
                    if inv:
                        needed = ingredient.quantity_needed * quantity
                        if inv.quantity < needed:
                            insufficient_ingredients.append(
                                f"{menu_item.name} (thiếu {inv.name}: cần {needed:.2f} {inv.unit}, còn {inv.quantity:.2f})"
                            )

        if insufficient_ingredients:
            db.session.rollback()  # Release locks
            flash(f'Không đủ nguyên liệu: {", ".join(insufficient_ingredients)}', 'danger')
            return redirect(url_for('customer.menu'))

        # Tạo đơn hàng mới (vẫn trong transaction với lock)
        new_order = Order(
            customer_id=current_user.user_id,
            table_id=table_id,
            order_type=order_type,
            status='pending',
            delivery_address=delivery_address,
            notes=notes
        )

        db.session.add(new_order)
        db.session.flush()

        for item_data in cart_items:
            menu_id, quantity = item_data.split(':')
            quantity = int(quantity)
            menu_item = Menu.query.get(menu_id)

            if menu_item and menu_item.available:
                # Thêm order item
                db.session.add(OrderItem(
                    order_id=new_order.order_id,
                    menu_id=menu_id,
                    quantity=quantity,
                    price=menu_item.price,
                    status='pending'
                ))

                # TRỪ NGUYÊN LIỆU TRONG KHO (sử dụng locked inventory)
                for ingredient in menu_item.ingredients:
                    inv = locked_inventories.get(ingredient.inventory_id)
                    if inv:
                        needed = ingredient.quantity_needed * quantity
                        inv.quantity -= needed
                        inv.last_updated = datetime.utcnow()

        new_order.calculate_total()
        db.session.commit()

        flash('Đặt hàng thành công!', 'success')
        return redirect(url_for('customer.menu', order_success='true'))

    except Exception as e:
        db.session.rollback()
        flash(f'Có lỗi xảy ra khi đặt hàng: {str(e)}', 'danger')
        return redirect(url_for('customer.menu'))





@bp.route('/orders')
@login_required
@customer_required
def my_orders():
    """Xem đơn hàng của tôi"""
    status_filter = request.args.get('status', 'all')
    
    query = Order.query.filter_by(customer_id=current_user.user_id)
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    orders = query.order_by(Order.order_time.desc()).all()
    
    return render_template('customer/my_orders.html',
                         orders=orders,
                         status_filter=status_filter)


@bp.route('/order/<int:order_id>')
@login_required
@customer_required
def order_detail(order_id):
    """Chi tiết đơn hàng"""
    order = Order.query.get_or_404(order_id)
    
    # Kiểm tra quyền
    if order.customer_id != current_user.user_id:
        flash('Bạn không có quyền xem đơn hàng này.', 'danger')
        return redirect(url_for('customer.my_orders'))
    
    return render_template('customer/order_detail.html', order=order)


@bp.route('/order/<int:order_id>/track')
@login_required
@customer_required
def track_order(order_id):
    """Theo dõi trạng thái đơn hàng real-time"""
    order = Order.query.get_or_404(order_id)
    
    # Kiểm tra quyền
    if order.customer_id != current_user.user_id:
        flash('Bạn không có quyền theo dõi đơn hàng này.', 'danger')
        return redirect(url_for('customer.my_orders'))
    
    return render_template('customer/track_order.html', order=order)


@bp.route('/order/<int:order_id>/cancel', methods=['POST'])
@login_required
@customer_required
def cancel_order(order_id):
    """Hủy đơn hàng"""
    order = Order.query.get_or_404(order_id)

    # Kiểm tra quyền
    if order.customer_id != current_user.user_id:
        flash('Bạn không có quyền hủy đơn hàng này.', 'danger')
        return redirect(url_for('customer.my_orders'))

    # Chỉ hủy được đơn pending
    if order.status != 'pending':
        flash('Chỉ có thể hủy đơn hàng đang chờ xử lý.', 'warning')
        return redirect(url_for('customer.order_detail', order_id=order_id))

    # HOÀN TRẢ NGUYÊN LIỆU VÀO KHO
    for order_item in order.order_items:
        menu_item = order_item.menu_item
        if menu_item:
            for ingredient in menu_item.ingredients:
                # Cộng lại nguyên liệu đã trừ
                restored = ingredient.quantity_needed * order_item.quantity
                ingredient.inventory.quantity += restored
                ingredient.inventory.last_updated = datetime.utcnow()

    order.status = 'cancelled'
    db.session.commit()

    flash('Đã hủy đơn hàng và hoàn trả nguyên liệu.', 'info')
    return redirect(url_for('customer.my_orders'))


@bp.route('/feedback/new/<int:order_id>', methods=['GET', 'POST'])
@login_required
@customer_required
def new_feedback(order_id):
    """Tạo đánh giá mới"""
    order = Order.query.get_or_404(order_id)
    
    # Kiểm tra quyền
    if order.customer_id != current_user.user_id:
        flash('Bạn không có quyền đánh giá đơn hàng này.', 'danger')
        return redirect(url_for('customer.my_orders'))
    
    # Chỉ đánh giá được đơn completed
    if order.status != 'completed':
        flash('Chỉ có thể đánh giá đơn hàng đã hoàn thành.', 'warning')
        return redirect(url_for('customer.order_detail', order_id=order_id))
    
    # Kiểm tra đã đánh giá chưa
    if order.feedback:
        flash('Bạn đã đánh giá đơn hàng này rồi.', 'info')
        return redirect(url_for('customer.order_detail', order_id=order_id))
    
    if request.method == 'POST':
        rating = request.form.get('rating')
        comment = request.form.get('comment', '')
        feedback_type = request.form.get('feedback_type', 'general')
        
        if not rating:
            flash('Vui lòng chọn số sao đánh giá.', 'warning')
            return redirect(url_for('customer.new_feedback', order_id=order_id))
        
        new_feedback = Feedback(
            customer_id=current_user.user_id,
            order_id=order_id,
            rating=int(rating),
            comment=comment,
            feedback_type=feedback_type
        )
        
        db.session.add(new_feedback)
        db.session.commit()
        
        flash('Cảm ơn bạn đã đánh giá!', 'success')
        return redirect(url_for('customer.order_detail', order_id=order_id))
    
    return render_template('customer/new_feedback.html', order=order)


@bp.route('/promotions')
@login_required
@customer_required
def promotions():
    """Xem các chương trình khuyến mãi"""
    now = datetime.utcnow()
    
    active_promotions = Promotion.query.filter(
        Promotion.active == True,
        Promotion.start_date <= now,
        Promotion.end_date >= now
    ).all()
    
    return render_template('customer/promotions.html',
                         promotions=active_promotions)


@bp.route('/profile')
@login_required
@customer_required
def profile():
    """Trang thông tin cá nhân"""
    return render_template('customer/profile.html')


@bp.route('/profile/update', methods=['POST'])
@login_required
@customer_required
def update_profile():
    """Cập nhật thông tin cá nhân"""
    name = request.form.get('name')
    phone = request.form.get('phone')
    
    if name:
        current_user.name = name
    if phone:
        current_user.phone = phone
    
    db.session.commit()
    
    flash('Cập nhật thông tin thành công!', 'success')
    return redirect(url_for('customer.profile'))


# API endpoints
@bp.route('/api/order/<int:order_id>/status')
@login_required
@customer_required
def get_order_status(order_id):
    order = Order.query.get_or_404(order_id)

    if order.customer_id != current_user.user_id:
        return jsonify({'error': 'Unauthorized'}), 403

    # Thông tin shipper (nếu có)
    shipper_info = None
    if order.shipper:
        shipper_info = {
            'name': order.shipper.name,
            'phone': order.shipper.phone
        }

    return jsonify({
        'order_id': order.order_id,
        'status': order.status,
        'order_type': order.order_type,
        'total_amount': float(order.total_amount),
        'order_time': order.order_time.strftime('%Y-%m-%d %H:%M:%S'),
        'items': [{
            'name': item.menu_item.name,
            'quantity': item.quantity,
            'status': item.status,
            'price': float(item.price),
            'chef_name': item.chef.name if item.chef else None
        } for item in order.order_items],
        'payment_status': order.payment.payment_status if order.payment else None,
        'shipper': shipper_info
    })


@bp.route('/api/check-table-availability')
@login_required
@customer_required
def check_table_availability():
    """API kiểm tra bàn còn trống"""
    date = request.args.get('date')
    time = request.args.get('time')
    
    if not date or not time:
        return jsonify({'error': 'Missing parameters'}), 400
    
    reservation_datetime = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    
    reserved_tables = db.session.query(Reservation.table_id).filter(
        Reservation.status.in_(['pending', 'confirmed']),
        Reservation.reservation_time.between(
            reservation_datetime - timedelta(hours=2),
            reservation_datetime + timedelta(hours=2)
        )
    ).all()
    
    reserved_ids = [t[0] for t in reserved_tables]
    
    available_tables = Table.query.filter(
        Table.status == 'available',
        ~Table.table_id.in_(reserved_ids)
    ).all()
    
    return jsonify({
        'available_tables': [
            {
                'table_id': t.table_id,
                'table_number': t.table_number,
                'capacity': t.capacity,
                'location': t.location
            }
            for t in available_tables
        ]
    })
