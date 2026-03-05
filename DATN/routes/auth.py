
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from models import db, User, Order

bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash('Email hoặc mật khẩu không đúng.', 'danger')
            return redirect(url_for('auth.login'))

        if not user.active:
            flash('Tài khoản đã bị khóa.', 'warning')
            return redirect(url_for('auth.login'))

        login_user(user, remember=remember)

        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)

        if user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif user.role == 'employee':
            return redirect(url_for('employee.dashboard'))
        else:
            return redirect(url_for('customer.dashboard'))

    return render_template('auth/login.html')


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not all([name, email, password, confirm_password]):
            flash('Vui lòng điền đầy đủ thông tin.', 'warning')
            return redirect(url_for('auth.register'))

        if password != confirm_password:
            flash('Mật khẩu xác nhận không khớp.', 'danger')
            return redirect(url_for('auth.register'))

        if len(password) < 6:
            flash('Mật khẩu phải có ít nhất 6 ký tự.', 'warning')
            return redirect(url_for('auth.register'))

        if User.query.filter_by(email=email).first():
            flash('Email đã tồn tại.', 'warning')
            return redirect(url_for('auth.register'))

        new_user = User(
            name=name,
            email=email,
            phone=phone,
            role='customer'
        )
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        flash('Đăng ký thành công! Vui lòng đăng nhập.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

