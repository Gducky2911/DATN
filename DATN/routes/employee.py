"""
Employee Routes
Các chức năng dành cho nhân viên
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, Order, OrderItem, Table, Reservation, Payment, Menu, Promotion, User
from datetime import datetime, date
from sqlalchemy import func

bp = Blueprint('employee', __name__, url_prefix='/employee')


def employee_required(f):
    """Decorator để kiểm tra quyền employee"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'employee':
            flash('Bạn không có quyền truy cập trang này.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@bp.route('/dashboard')
@login_required
@employee_required
def dashboard():
    """Dashboard nhân viên"""
    from datetime import datetime, date
    
    if current_user.employee_type == 'waiter':
        # Thống kê cho waiter
        occupied_tables = Table.query.filter_by(status='occupied').count()
        available_tables = Table.query.filter_by(status='available').count()
        
        # Đơn hàng hôm nay
        today_orders = Order.query.filter(
            db.func.date(Order.order_time) == date.today()
        ).count()
        
        # Đặt bàn hôm nay
        today_reservations = Reservation.query.filter(
            db.func.date(Reservation.reservation_time) == date.today()
        ).count()
        
        # Bàn đang hoạt động
        active_tables = Table.query.filter_by(status='occupied').all()
        
        # Đặt bàn sắp tới (trong 2 giờ tới)
        from datetime import timedelta
        next_2_hours = datetime.now() + timedelta(hours=2)
        upcoming_reservations = Reservation.query.filter(
            Reservation.reservation_time.between(datetime.now(), next_2_hours),
            Reservation.status.in_(['confirmed', 'pending'])
        ).order_by(Reservation.reservation_time).limit(5).all()
        
        return render_template('employee/waiter_dashboard.html',
                             occupied_tables=occupied_tables,
                             today_orders=today_orders,
                             today_reservations=today_reservations,
                             available_tables=available_tables,
                             active_tables=active_tables,
                             upcoming_reservations=upcoming_reservations)
    
    elif current_user.employee_type == 'chef':
        # Nhân viên bếp: xem món cần nấu
        preparing_items = OrderItem.query.join(Order).filter(
            Order.status.in_(['pending', 'preparing']),
            OrderItem.status.in_(['pending', 'preparing'])
        ).order_by(Order.order_time).all()
        
        pending_count = OrderItem.query.join(Order).filter(
            Order.status.in_(['pending', 'preparing']),
            OrderItem.status == 'pending'
        ).count()
        
        preparing_count = OrderItem.query.join(Order).filter(
            Order.status.in_(['pending', 'preparing']),
            OrderItem.status == 'preparing'
        ).count()
        
        return render_template('employee/chef_dashboard.html',
                             preparing_items=preparing_items,
                             pending_count=pending_count,
                             preparing_count=preparing_count)
    
    elif current_user.employee_type == 'cashier':
        pending_payments = Order.query.filter_by(status='ready').count()
        completed_payments = Payment.query.filter_by(payment_status='completed').count()
        total_transactions = Payment.query.count()
        
        today_revenue = db.session.query(db.func.sum(Payment.final_amount)).filter(
            Payment.payment_status == 'completed',
            db.func.date(Payment.payment_time) == datetime.utcnow().date()
        ).scalar() or 0
        
        ready_orders = Order.query.options(
            db.joinedload(Order.customer)
        ).filter(
            Order.status == 'ready',
            ~Order.payment.has()  
        ).order_by(Order.order_time.desc()).limit(10).all()
        
        recent_payments = Payment.query.options(
            db.joinedload(Payment.order)
        ).filter(
            Payment.payment_status == 'completed',
            Payment.payment_time.isnot(None)
        ).order_by(Payment.payment_time.desc()).limit(5).all()
        
        return render_template('employee/cashier_dashboard.html',
                             pending_payments=pending_payments,
                             today_revenue=today_revenue,
                             completed_payments=completed_payments,
                             total_transactions=total_transactions,
                             ready_orders=ready_orders,
                             recent_payments=recent_payments)
    
    elif current_user.employee_type == 'delivery':
        # Nhân viên giao hàng
        from datetime import datetime, date

        # Đơn chờ giao (chưa có shipper nhận)
        delivery_orders = Order.query.options(
            db.joinedload(Order.customer)
        ).filter_by(
            order_type='delivery',
            status='ready'
        ).all()

        # Đơn tôi đang giao
        my_deliveries = Order.query.options(
            db.joinedload(Order.customer)
        ).filter(
            Order.order_type == 'delivery',
            Order.status == 'delivering',
            Order.shipper_id == current_user.user_id
        ).all()

        # Đơn hoàn thành hôm nay (của tôi)
        completed_today = Order.query.filter(
            Order.order_type == 'delivery',
            Order.status == 'completed',
            Order.shipper_id == current_user.user_id,
            db.func.date(Order.completed_time) == date.today()
        ).count()

        # Tổng đơn tôi đã giao
        total_deliveries = Order.query.filter(
            Order.order_type == 'delivery',
            Order.shipper_id == current_user.user_id
        ).count()

        return render_template('employee/delivery_dashboard.html',
                            delivery_orders=delivery_orders,
                            my_deliveries=my_deliveries,
                            completed_today=completed_today,
                            total_deliveries=total_deliveries)

    else:
        # Fallback cho loại nhân viên không xác định
        return f"""
        <div class="container">
            <div class="alert alert-info">
                <h4>Dashboard không khả dụng</h4>
                <p>Loại nhân viên của bạn: {current_user.employee_type}</p>
                <a href="/employee/orders" class="btn btn-primary">Xem đơn hàng</a>
            </div>
        </div>
        """

# Chức năng cho Waiter
@bp.route('/tables')
@login_required
@employee_required
def tables():
    """Quản lý bàn (Waiter)"""
    if current_user.employee_type != 'waiter':
        flash('Chức năng này chỉ dành cho nhân viên phục vụ.', 'warning')
        return redirect(url_for('employee.dashboard'))
    
    # THÊM EAGER LOADING cho reservations và customer
    all_tables = Table.query.options(
        db.joinedload(Table.reservations).joinedload(Reservation.customer)
    ).order_by(Table.table_number).all()
    
    return render_template('employee/tables.html', tables=all_tables)


@bp.route('/table/<int:table_id>/update-status', methods=['POST'])
@login_required
@employee_required
def update_table_status(table_id):
    """Cập nhật trạng thái bàn"""
    if current_user.employee_type != 'waiter':
        return jsonify({'error': 'Unauthorized'}), 403
    
    table = Table.query.get_or_404(table_id)
    new_status = request.form.get('status')
    
    if new_status in ['available', 'occupied', 'reserved']:
        table.status = new_status
        db.session.commit()
        flash(f'Đã cập nhật trạng thái bàn {table.table_number}.', 'success')
    
    return redirect(url_for('employee.tables'))


@bp.route('/reservations')
@login_required
@employee_required
def reservations():
    """Quản lý đặt bàn (Waiter)"""
    if current_user.employee_type != 'waiter':
        flash('Chức năng này chỉ dành cho nhân viên phục vụ.', 'warning')
        return redirect(url_for('employee.dashboard'))
    
    status_filter = request.args.get('status', 'all')
    
    # THÊM EAGER LOADING cho cả Table và Customer
    query = Reservation.query.options(
        db.joinedload(Reservation.table),
        db.joinedload(Reservation.customer)
    )
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    reservations = query.order_by(Reservation.reservation_time.asc()).all()
    
    return render_template('employee/reservations.html',
                         reservations=reservations,
                         status_filter=status_filter)

@bp.route('/reservation/<int:reservation_id>/confirm', methods=['POST'])
@login_required
@employee_required
def confirm_reservation(reservation_id):
    """Xác nhận đặt bàn"""
    if current_user.employee_type != 'waiter':
        return jsonify({'error': 'Unauthorized'}), 403
    
    reservation = Reservation.query.get_or_404(reservation_id)
    reservation.status = 'confirmed'
    
    # Cập nhật trạng thái bàn
    if reservation.table:
        reservation.table.status = 'reserved'
    
    db.session.commit()
    
    flash('Đã xác nhận đặt bàn.', 'success')
    return redirect(url_for('employee.reservations'))


@bp.route('/reservation/<int:reservation_id>/complete', methods=['POST'])
@login_required
@employee_required
def complete_reservation(reservation_id):
    """Hoàn thành đặt bàn (khách đã đến)"""
    if current_user.employee_type != 'waiter':
        return jsonify({'error': 'Unauthorized'}), 403
    
    reservation = Reservation.query.get_or_404(reservation_id)
    reservation.status = 'completed'
    
    # Cập nhật trạng thái bàn
    if reservation.table:
        reservation.table.status = 'occupied'
    
    db.session.commit()
    
    flash('Khách đã đến. Bàn đang được sử dụng.', 'success')
    return redirect(url_for('employee.reservations'))


@bp.route('/orders')
@login_required
@employee_required
def orders():
    """Xem danh sách đơn hàng"""
    status_filter = request.args.get('status', 'all')
    
    query = Order.query
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    orders = query.order_by(Order.order_time.desc()).all()
    
    return render_template('employee/orders.html',
                         orders=orders,
                         status_filter=status_filter)


@bp.route('/order/<int:order_id>')
@login_required
@employee_required
def order_detail(order_id):
    """Chi tiết đơn hàng"""
    order = Order.query.get_or_404(order_id)
    return render_template('employee/order_detail.html', order=order)


# Chức năng cho Chef
@bp.route('/kitchen')
@login_required
@employee_required
def kitchen():
    if current_user.employee_type != 'chef':
        flash('Chức năng này chỉ dành cho nhân viên bếp.', 'warning')
        return redirect(url_for('employee.dashboard'))

    preparing_items = OrderItem.query.join(Order).options(
        db.joinedload(OrderItem.menu_item),
        db.joinedload(OrderItem.order).joinedload(Order.table)
    ).filter(
        OrderItem.status.in_(['pending', 'preparing'])
    ).order_by(Order.order_time).all()

    pending_count = sum(1 for i in preparing_items if i.status == 'pending')
    preparing_count = sum(1 for i in preparing_items if i.status == 'preparing')

    completed_items_today = OrderItem.query.join(Order).options(
        db.joinedload(OrderItem.menu_item),
        db.joinedload(OrderItem.order).joinedload(Order.table)
    ).filter(
        OrderItem.status == 'completed',
        db.func.date(Order.completed_time) == date.today()
    ).order_by(Order.completed_time.desc()).all()

    return render_template(
        'employee/chef_dashboard.html',
        preparing_items=preparing_items,
        completed_items_today=completed_items_today,
        pending_count=pending_count,
        preparing_count=preparing_count
    )

@bp.route('/order-item/<int:item_id>/start-cooking', methods=['POST'])
@login_required
@employee_required
def start_cooking(item_id):
    """Bắt đầu nấu món"""
    if current_user.employee_type != 'chef':
        return jsonify({'error': 'Unauthorized'}), 403

    order_item = OrderItem.query.get_or_404(item_id)
    order_item.status = 'preparing'

    # Gán đầu bếp đang nấu món này
    order_item.chef_id = current_user.user_id

    # Cập nhật trạng thái order
    if order_item.order.status == 'pending':
        order_item.order.status = 'preparing'

    db.session.commit()

    flash(f'Đã bắt đầu nấu món {order_item.menu_item.name}.', 'success')
    return redirect(url_for('employee.kitchen'))


@bp.route('/order-item/<int:item_id>/complete-cooking', methods=['POST'])
@login_required
@employee_required
def complete_cooking(item_id):
    """Hoàn thành nấu món"""
    if current_user.employee_type != 'chef':
        return jsonify({'error': 'Unauthorized'}), 403

    order_item = OrderItem.query.get_or_404(item_id)

    # Kiểm tra chef ownership - chỉ chef đã nhận món mới được hoàn thành
    if order_item.chef_id and order_item.chef_id != current_user.user_id:
        flash('Bạn không phải đầu bếp đang nấu món này.', 'warning')
        return redirect(url_for('employee.kitchen'))

    order_item.status = 'completed'

    # Kiểm tra nếu tất cả món trong order đã hoàn thành
    all_completed = all(item.status == 'completed' for item in order_item.order.order_items)

    if all_completed:
        order_item.order.status = 'ready'
        order_item.order.completed_time = datetime.utcnow()
    db.session.commit()

    flash(f'Món {order_item.menu_item.name} đã hoàn thành.', 'success')
    return redirect(url_for('employee.kitchen'))


# Chức năng cho Cashier
@bp.route('/payments')
@login_required
@employee_required
def payments():
    """Quản lý thanh toán (Cashier)"""
    if current_user.employee_type != 'cashier':
        flash('Chức năng này chỉ dành cho thu ngân.', 'warning')
        return redirect(url_for('employee.dashboard'))

    status_filter = request.args.get('status', 'all')

    query = Payment.query.options(
        db.joinedload(Payment.order).joinedload(Order.customer),
        db.joinedload(Payment.order).joinedload(Order.table)
    )

    if status_filter != 'all':
        query = query.filter(Payment.payment_status == status_filter)

    payments = query.order_by(Payment.payment_time.desc()).all()

    pending_payments = Order.query.filter_by(status='ready').count()

    today_revenue = db.session.query(
        func.coalesce(func.sum(Payment.final_amount), 0)
    ).filter(
        Payment.payment_status == 'completed',
        func.date(Payment.payment_time) == datetime.utcnow().date()
    ).scalar()

    recent_payments = (
        Payment.query
        .filter(Payment.payment_status == 'completed')
        .order_by(Payment.payment_time.desc())
        .limit(10)
        .all()
    )

    return render_template(
        'employee/payments.html',
        payments=payments,
        pending_payments=pending_payments,
        today_revenue=today_revenue,
        recent_payments=recent_payments,
        status_filter=status_filter
    )



@bp.route('/payment/<int:payment_id>/confirm', methods=['POST'])
@login_required
@employee_required
def confirm_payment(payment_id):
    """Xác nhận thanh toán"""
    if current_user.employee_type != 'cashier':
        return jsonify({'error': 'Unauthorized'}), 403
    
    payment = Payment.query.get_or_404(payment_id)
    payment.payment_status = 'completed'
    payment.payment_time = datetime.utcnow()
    
    # Cập nhật order
    payment.order.status = 'completed'
    payment.order.completed_time = datetime.utcnow()
    
    # Giải phóng bàn nếu là dine-in
    if payment.order.order_type == 'dine-in' and payment.order.table:
        payment.order.table.status = 'available'
    
    db.session.commit()
    
    flash('Đã xác nhận thanh toán.', 'success')
    return redirect(url_for('employee.payments'))


@bp.route('/order/<int:order_id>/create-payment', methods=['GET', 'POST'])
@login_required
@employee_required
def create_payment(order_id):
    """Tạo hóa đơn thanh toán"""
    if current_user.employee_type != 'cashier':
        flash('Chức năng này chỉ dành cho thu ngân.', 'warning')
        return redirect(url_for('employee.dashboard'))
    
    order = Order.query.get_or_404(order_id)
    
    if order.payment:
        flash('Đơn hàng này đã có hóa đơn thanh toán.', 'info')
        return redirect(url_for('employee.order_detail', order_id=order_id))
    
    if request.method == 'POST':
        payment_method = request.form.get('payment_method')
        promo_code = request.form.get('promo_code', '').strip()
        
        amount = order.total_amount
        discount_amount = 0
        
        # Áp dụng mã khuyến mãi nếu có
        if promo_code:
            promo = Promotion.query.filter_by(code=promo_code).first()
            if promo and promo.is_valid():
                if amount >= promo.min_order_amount:
                    discount_amount = amount * promo.discount_percent / 100
                    if promo.max_discount and discount_amount > promo.max_discount:
                        discount_amount = promo.max_discount
                    promo.usage_count += 1
                else:
                    flash(f'Đơn hàng phải từ {promo.min_order_amount:,.0f}đ để dùng mã này.', 'warning')
            else:
                flash('Mã khuyến mãi không hợp lệ.', 'warning')
        
        final_amount = amount - discount_amount
        
        new_payment = Payment(
            order_id=order_id,
            amount=amount,
            payment_method=payment_method,
            payment_status='pending',
            promo_code=promo_code if promo_code else None,
            discount_amount=discount_amount,
            final_amount=final_amount
        )
        
        db.session.add(new_payment)
        db.session.commit()
        
        flash('Đã tạo hóa đơn thanh toán.', 'success')
        return redirect(url_for('employee.order_detail', order_id=order_id))
    
    return render_template('employee/create_payment.html', order=order)

@bp.route('/promo/validate', methods=['POST'])
@login_required
@employee_required
def validate_promo():
    promo_code = request.json.get('promo_code', '').upper()
    order_id = request.json.get('order_id')

    order = Order.query.get_or_404(order_id)
    promo = Promotion.query.filter_by(code=promo_code).first()

    if not promo:
        return jsonify({'success': False, 'message': 'Mã không tồn tại'})

    if not promo.is_valid():
        return jsonify({'success': False, 'message': 'Mã đã hết hạn hoặc không còn hiệu lực'})

    if order.total_amount < promo.min_order_amount:
        return jsonify({
            'success': False,
            'message': f'Đơn tối thiểu {promo.min_order_amount:,.0f}đ'
        })

    discount = order.total_amount * promo.discount_percent / 100
    if promo.max_discount and discount > promo.max_discount:
        discount = promo.max_discount

    return jsonify({
        'success': True,
        'discount': round(discount),
        'final_amount': round(order.total_amount - discount),
        'percent': promo.discount_percent
    })


# Chức năng cho Delivery
@bp.route('/deliveries')
@login_required
@employee_required
def deliveries():
    """Quản lý giao hàng (Delivery)"""
    if current_user.employee_type != 'delivery':
        flash('Chức năng này chỉ dành cho nhân viên giao hàng.', 'warning')
        return redirect(url_for('employee.dashboard'))
    
    status_filter = request.args.get('status', 'all')
    
    # Query cho đơn giao hàng
    query = Order.query.options(
        db.joinedload(Order.customer)
    ).filter_by(order_type='delivery')
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    deliveries = query.order_by(Order.order_time.desc()).all()
    
    return render_template('employee/deliveries.html',
                         deliveries=deliveries,
                         status_filter=status_filter)


@bp.route('/delivery/<int:order_id>/start', methods=['POST'])
@login_required
@employee_required
def start_delivery(order_id):
    """Bắt đầu giao hàng"""
    if current_user.employee_type != 'delivery':
        return jsonify({'error': 'Unauthorized'}), 403

    order = Order.query.get_or_404(order_id)

    # Kiểm tra đơn hàng đã ready chưa
    if order.status != 'ready':
        flash('Đơn hàng chưa sẵn sàng để giao. Vui lòng đợi bếp hoàn thành.', 'warning')
        return redirect(url_for('employee.deliveries'))

    # Gán shipper cho đơn hàng
    order.shipper_id = current_user.user_id
    order.status = 'delivering'  # Trạng thái đang giao

    db.session.commit()

    flash('Đã nhận đơn giao hàng.', 'success')
    return redirect(url_for('employee.deliveries'))


@bp.route('/delivery/<int:order_id>/complete', methods=['POST'])
@login_required
@employee_required
def complete_delivery(order_id):
    """Hoàn thành giao hàng"""
    if current_user.employee_type != 'delivery':
        return jsonify({'error': 'Unauthorized'}), 403

    order = Order.query.get_or_404(order_id)

    # Kiểm tra shipper ownership - chỉ shipper đã nhận đơn mới được hoàn thành
    if order.shipper_id and order.shipper_id != current_user.user_id:
        flash('Bạn không phải shipper đang giao đơn hàng này.', 'warning')
        return redirect(url_for('employee.deliveries'))

    order.status = 'completed'
    order.completed_time = datetime.utcnow()

    db.session.commit()

    flash('Đã hoàn thành giao hàng.', 'success')
    return redirect(url_for('employee.deliveries'))
