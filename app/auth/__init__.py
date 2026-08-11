from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse

from app.models import db, User
from app import limiter
from app.auth.forms import LoginForm, AddUserForm
from app.utils import landing_url

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/mode/<mode>')
@login_required
def switch_mode(mode):
    session['app_mode'] = mode if mode in ('debt', 'commerce') else 'debt'
    return redirect(landing_url())


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10/minute")
def login():
    from flask_login import current_user
    if current_user.is_authenticated:
        return redirect(landing_url())
    from app.models import Settings, User
    if Settings.get('login_locked', 'false') == 'true' or Settings.get('login_locked') is True:
        admin = User.query.filter_by(username='admin').first()
        if admin and not admin.is_active_flag:
            admin = None
        if request.method == 'POST':
            pw = request.form.get('unlock_password', '')
            if admin and admin.check_password(pw):
                login_user(admin, remember=True)
                return redirect(landing_url())
            flash('كلمة المرور غير صحيحة', 'danger')
        elif admin is None:
            flash('لا يوجد حساب مدير متاح — أضف مستخدم admin أولاً', 'danger')
        return render_template('login.html', login_locked=True)
    if request.method == 'POST':
        form = LoginForm(request.form)
        if form.validate():
            user = User.query.filter_by(username=form.username.data.strip()).first()
            if user and user.check_password(form.password.data) and user.is_active_flag:
                login_user(user, remember=request.form.get('remember') == 'on')
                next_url = request.args.get('next', '')
                if next_url:
                    parsed = urlparse(next_url)
                    if parsed.netloc or parsed.scheme:
                        next_url = ''
                return redirect(next_url or landing_url())
        flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    return render_template('login.html', login_locked=False)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/users')
@login_required
def users():
    if not current_user.is_admin:
        flash('غير مصرح', 'danger')
        return redirect(url_for('clients.index'))
    all_users = User.query.all()
    return render_template('users.html', users=all_users)


@auth_bp.route('/users/add', methods=['POST'])
@login_required
def user_add():
    if not current_user.is_admin:
        flash('غير مصرح', 'danger')
        return redirect(url_for('clients.index'))
    form = AddUserForm(request.form)
    if form.validate():
        username = form.username.data.strip()
        password = form.password.data
        role = form.role.data
        if User.query.filter_by(username=username).first():
            flash('اسم المستخدم موجود بالفعل', 'danger')
            return redirect(url_for('auth.users'))
        u = User(username=username, role=role)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        flash(f'تم إضافة المستخدم "{username}"', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(error, 'danger')
    return redirect(url_for('auth.users'))


@auth_bp.route('/users/<int:uid>/toggle', methods=['POST'])
@login_required
def user_toggle(uid):
    if not current_user.is_admin:
        flash('غير مصرح', 'danger')
        return redirect(url_for('clients.index'))
    u = db.session.get(User, uid)
    if not u:
        flash('المستخدم غير موجود', 'danger')
        return redirect(url_for('auth.users'))
    if u.id == current_user.id:
        flash('لا يمكنك تعطيل حسابك الخاص', 'warning')
        return redirect(url_for('auth.users'))
    u.is_active_flag = not u.is_active_flag
    db.session.commit()
    flash(f'تم {"تفعيل" if u.is_active_flag else "تعطيل"} المستخدم "{u.username}"', 'success')
    return redirect(url_for('auth.users'))


@auth_bp.route('/users/<int:uid>/delete', methods=['POST'])
@login_required
def user_delete(uid):
    if not current_user.is_admin:
        flash('غير مصرح', 'danger')
        return redirect(url_for('clients.index'))
    u = db.session.get(User, uid)
    if not u:
        flash('المستخدم غير موجود', 'danger')
        return redirect(url_for('auth.users'))
    if u.id == current_user.id:
        flash('لا يمكنك حذف حسابك الخاص', 'warning')
        return redirect(url_for('auth.users'))
    db.session.delete(u)
    db.session.commit()
    flash(f'تم حذف المستخدم "{u.username}"', 'success')
    return redirect(url_for('auth.users'))
