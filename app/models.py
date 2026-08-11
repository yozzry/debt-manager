from datetime import datetime, date, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='viewer', nullable=False)
    is_active_flag = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_cashier(self):
        return self.role == 'cashier'

    @property
    def is_accountant(self):
        return self.role == 'accountant'

    @property
    def can_edit(self):
        return self.role in ('admin', 'editor')

    @property
    def can_pos(self):
        """تشغيل نقطة البيع: مدير أو أمين صندوق."""
        return self.role in ('admin', 'cashier')

    @property
    def can_accounting(self):
        """إدارة المحاسبة: مدير أو محاسب."""
        return self.role in ('admin', 'accountant')

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'is_active': self.is_active_flag,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


CLIENT_TYPES = ('customer', 'supplier', 'employee')


class Client(db.Model):
    __tablename__ = 'clients'
    __table_args__ = (
        db.Index('idx_client_status', 'status'),
        db.Index('idx_client_name', 'name'),
        db.Index('idx_client_phone', 'phone'),
        db.Index('idx_client_updated', 'updated_at'),
        db.Index('idx_client_type', 'type'),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(20), default='customer', nullable=False)  # customer, supplier, employee
    company_name = db.Column(db.String(200), nullable=True)
    tax_id = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(30))
    notes = db.Column(db.Text)
    total_debt = db.Column(db.Numeric(10, 2), default=0.0, nullable=False)
    total_paid = db.Column(db.Numeric(10, 2), default=0.0, nullable=False)
    base_debt = db.Column(db.Numeric(10, 2), default=0.0, nullable=False)
    base_paid = db.Column(db.Numeric(10, 2), default=0.0, nullable=False)
    status = db.Column(db.String(20), default='due', nullable=False)
    reminder_enabled = db.Column(db.Boolean, default=True)
    reminder_template = db.Column(db.Integer, default=1)
    reminder_times = db.Column(db.Text, nullable=True)
    reminder_frequency = db.Column(db.String(10), nullable=True)
    reminder_day = db.Column(db.String(10), nullable=True)
    reminder_dom = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    invoices = db.relationship('Invoice', backref='client', lazy=True, cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='client', lazy=True, cascade='all, delete-orphan')
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)
    account = db.relationship('Account', foreign_keys=[account_id],
                              lazy='joined')

    @property
    def balance(self):
        return max(0.0, float(self.total_debt) - float(self.total_paid))

    @property
    def is_supplier(self):
        return self.type == 'supplier'

    @property
    def type_label(self):
        return {
            'customer': 'عميل',
            'supplier': 'مورد',
            'employee': 'موظف',
        }.get(self.type, 'عميل')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'company_name': self.company_name,
            'tax_id': self.tax_id,
            'phone': self.phone,
            'notes': self.notes,
            'total_debt': float(self.total_debt),
            'total_paid': float(self.total_paid),
            'balance': self.balance,
            'status': self.status,
            'reminder_enabled': self.reminder_enabled,
            'reminder_template': self.reminder_template,
            'reminder_times': self.reminder_times,
            'reminder_frequency': self.reminder_frequency,
            'reminder_day': self.reminder_day,
            'reminder_dom': self.reminder_dom,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Category(db.Model):
    __tablename__ = 'categories'
    __table_args__ = (
        db.Index('idx_category_name', 'name'),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=_utcnow)

    products = db.relationship('Product', backref='category', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Product(db.Model):
    __tablename__ = 'products'
    __table_args__ = (
        db.Index('idx_product_name', 'name'),
        db.Index('idx_product_sku', 'sku'),
        db.Index('idx_product_barcode', 'barcode'),
        db.Index('idx_product_category', 'category_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    sku = db.Column(db.String(100), nullable=True)
    barcode = db.Column(db.String(100), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    unit = db.Column(db.String(30), default='قطعة')
    cost_price = db.Column(db.Numeric(10, 2), default=0.0, nullable=False)
    selling_price = db.Column(db.Numeric(10, 2), default=0.0, nullable=False)
    current_stock = db.Column(db.Numeric(10, 2), default=0.0, nullable=False)
    min_stock = db.Column(db.Numeric(10, 2), default=0.0, nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    stock_movements = db.relationship('StockMovement', backref='product',
                                      lazy=True, cascade='all, delete-orphan')

    @property
    def stock_status(self):
        stock = float(self.current_stock or 0)
        if stock <= 0:
            return 'out'
        if stock <= float(self.min_stock or 0):
            return 'low'
        return 'ok'

    @property
    def stock_status_label(self):
        return {'out': 'نفذ المخزون', 'low': 'منخفض', 'ok': 'متوفر'}.get(self.stock_status, 'متوفر')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'sku': self.sku,
            'barcode': self.barcode,
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else None,
            'unit': self.unit,
            'cost_price': float(self.cost_price or 0),
            'selling_price': float(self.selling_price or 0),
            'current_stock': float(self.current_stock or 0),
            'min_stock': float(self.min_stock or 0),
            'stock_status': self.stock_status,
            'description': self.description,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class StockMovement(db.Model):
    __tablename__ = 'stock_movements'
    __table_args__ = (
        db.Index('idx_stock_product', 'product_id'),
        db.Index('idx_stock_type', 'movement_type'),
        db.Index('idx_stock_reference', 'reference'),
        db.Index('idx_stock_created', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    movement_type = db.Column(db.String(10), nullable=False)  # IN / OUT / ADJUST
    quantity = db.Column(db.Numeric(10, 2), nullable=False)
    balance_after = db.Column(db.Numeric(10, 2), default=0.0, nullable=False)
    reference = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else None,
            'movement_type': self.movement_type,
            'quantity': float(self.quantity or 0),
            'balance_after': float(self.balance_after or 0),
            'reference': self.reference,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Invoice(db.Model):
    __tablename__ = 'invoices'
    __table_args__ = (
        db.Index('idx_invoice_client', 'client_id'),
        db.Index('idx_invoice_date', 'date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    description = db.Column(db.String(500))
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=True)
    date = db.Column(db.Date, default=date.today)
    image_path = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=_utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'client_id': self.client_id,
            'description': self.description,
            'amount': float(self.amount),
            'date': self.date.isoformat() if self.date else None,
            'image_path': self.image_path,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Payment(db.Model):
    __tablename__ = 'payments'
    __table_args__ = (
        db.Index('idx_payment_client', 'client_id'),
        db.Index('idx_payment_date', 'date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    date = db.Column(db.Date, default=date.today)
    notes = db.Column(db.String(500))
    payment_method = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=_utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'client_id': self.client_id,
            'amount': float(self.amount),
            'date': self.date.isoformat() if self.date else None,
            'notes': self.notes,
            'payment_method': self.payment_method,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Settings(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    value_type = db.Column(db.String(10), default='string')

    _TYPE_CONVERTERS = {
        'string': lambda v: str(v) if v is not None else '',
        'int': lambda v: int(v),
        'float': lambda v: float(v),
        'bool': lambda v: str(v).lower() in ('true', '1', 'yes'),
        'json': lambda v: __import__('json').loads(v) if isinstance(v, str) else v,
    }

    @classmethod
    def get(cls, key, default=None):
        row = cls.query.filter_by(key=key).first()
        if not row:
            return default
        if row.value_type == 'bool':
            return row.value.lower() in ('true', '1', 'yes')
        if row.value_type == 'int':
            try:
                return int(row.value)
            except (ValueError, TypeError):
                return default
        if row.value_type == 'float':
            try:
                return float(row.value)
            except (ValueError, TypeError):
                return default
        if row.value_type == 'json':
            import json as _json
            try:
                return _json.loads(row.value) if row.value else default
            except (ValueError, TypeError):
                return default
        return row.value if row is not None else default

    @classmethod
    def set(cls, key, value, value_type=None):
        if value_type is None:
            if isinstance(value, bool):
                value_type = 'bool'
            elif isinstance(value, int):
                value_type = 'int'
            elif isinstance(value, float):
                value_type = 'float'
            elif isinstance(value, (dict, list)):
                value_type = 'json'
            else:
                value_type = 'string'
        if value_type == 'json':
            import json as _json
            serialized = _json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        elif value_type == 'bool':
            serialized = 'true' if value else 'false'
        else:
            serialized = str(value) if value is not None else ''
        row = cls.query.filter_by(key=key).first()
        if row:
            row.value = serialized
            row.value_type = value_type
        else:
            db.session.add(cls(key=key, value=serialized, value_type=value_type))
        db.session.commit()


class ActivityLog(db.Model):
    __tablename__ = 'activity_log'
    __table_args__ = (
        db.Index('idx_activity_user', 'user_id'),
        db.Index('idx_activity_entity', 'entity_type', 'entity_id'),
        db.Index('idx_activity_created', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(50), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    user = db.relationship('User', backref='activities', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'user': self.user.username if self.user else None,
            'action': self.action,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'details': self.details,
            'ip_address': self.ip_address,
            'created_at': self.created_at.isoformat(),
        }


class ImportCache(db.Model):
    __tablename__ = 'import_cache'

    id = db.Column(db.Integer, primary_key=True)
    cache_key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    data_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    @classmethod
    def store(cls, key, data):
        import json as _json
        existing = cls.query.filter_by(cache_key=key).first()
        serialized = _json.dumps(data, ensure_ascii=False, default=str)
        if existing:
            existing.data_json = serialized
            existing.created_at = _utcnow()
        else:
            db.session.add(cls(cache_key=key, data_json=serialized))
        db.session.commit()

    @classmethod
    def get_data(cls, key):
        import json as _json
        row = cls.query.filter_by(cache_key=key).first()
        if not row:
            return None
        from datetime import timedelta
        if _utcnow() - row.created_at > timedelta(hours=1):
            db.session.delete(row)
            db.session.commit()
            return None
        return _json.loads(row.data_json)

    @classmethod
    def pop(cls, key):
        row = cls.query.filter_by(cache_key=key).first()
        if row:
            db.session.delete(row)
            db.session.commit()

    @classmethod
    def cleanup_expired(cls):
        from datetime import timedelta
        cutoff = _utcnow() - timedelta(hours=1)
        cls.query.filter(cls.created_at < cutoff).delete()
        db.session.commit()


PURCHASE_STATUSES = ('draft', 'received', 'cancelled')


class PurchaseOrder(db.Model):
    __tablename__ = 'purchase_orders'
    __table_args__ = (
        db.Index('idx_purchase_supplier', 'supplier_id'),
        db.Index('idx_purchase_status', 'status'),
        db.Index('idx_purchase_date', 'date'),
        db.Index('idx_purchase_number', 'order_number'),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    date = db.Column(db.Date, default=date.today, nullable=False)
    status = db.Column(db.String(20), default='draft', nullable=False)  # draft / received / cancelled
    total_amount = db.Column(db.Numeric(10, 2), default=0.0, nullable=False)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    supplier = db.relationship('Client', foreign_keys=[supplier_id], backref='purchase_orders')
    items = db.relationship('PurchaseItem', backref='order', lazy='select',
                            cascade='all, delete-orphan')
    creator = db.relationship('User', foreign_keys=[created_by])

    @property
    def status_label(self):
        return {'draft': 'مسودة', 'received': 'مستلمة', 'cancelled': 'ملغاة'}.get(self.status, self.status)

    def recalc_total(self):
        self.total_amount = sum(float(i.quantity or 0) * float(i.unit_cost or 0) for i in self.items)

    def to_dict(self):
        return {
            'id': self.id,
            'order_number': self.order_number,
            'supplier_id': self.supplier_id,
            'supplier_name': self.supplier.name if self.supplier else None,
            'date': self.date.isoformat() if self.date else None,
            'status': self.status,
            'total_amount': float(self.total_amount or 0),
            'notes': self.notes,
            'items': [i.to_dict() for i in self.items],
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class PurchaseItem(db.Model):
    __tablename__ = 'purchase_items'
    __table_args__ = (
        db.Index('idx_purchase_item_order', 'order_id'),
        db.Index('idx_purchase_item_product', 'product_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), nullable=False)
    unit_cost = db.Column(db.Numeric(10, 2), default=0.0, nullable=False)

    product = db.relationship('Product')

    @property
    def total(self):
        return float(self.quantity or 0) * float(self.unit_cost or 0)

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else None,
            'quantity': float(self.quantity or 0),
            'unit_cost': float(self.unit_cost or 0),
            'total': self.total,
        }


SALE_METHODS = ('cash', 'credit')
SALE_STATUSES = ('completed', 'cancelled')


class Sale(db.Model):
    __tablename__ = 'sales'
    __table_args__ = (
        db.Index('idx_sale_client', 'client_id'),
        db.Index('idx_sale_date', 'date'),
        db.Index('idx_sale_status', 'status'),
        db.Index('idx_sale_number', 'invoice_number'),
    )

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)
    date = db.Column(db.Date, default=date.today, nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), default=0.0, nullable=False)
    discount = db.Column(db.Numeric(10, 2), default=0.0, nullable=False)
    total = db.Column(db.Numeric(10, 2), default=0.0, nullable=False)
    payment_method = db.Column(db.String(20), default='cash', nullable=False)  # cash / credit
    status = db.Column(db.String(20), default='completed', nullable=False)  # completed / cancelled
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    client = db.relationship('Client', foreign_keys=[client_id], backref='sales')
    items = db.relationship('SaleItem', backref='sale', lazy='select',
                            cascade='all, delete-orphan')
    creator = db.relationship('User', foreign_keys=[created_by])
    invoice = db.relationship('Invoice', foreign_keys='Invoice.sale_id',
                              uselist=False, backref='sale')

    @property
    def status_label(self):
        return {'completed': 'مكتملة', 'cancelled': 'ملغاة'}.get(self.status, self.status)

    @property
    def payment_method_label(self):
        return {'cash': 'نقدي', 'credit': 'آجل'}.get(self.payment_method, self.payment_method)

    def to_dict(self):
        return {
            'id': self.id,
            'invoice_number': self.invoice_number,
            'client_id': self.client_id,
            'client_name': self.client.name if self.client else None,
            'date': self.date.isoformat() if self.date else None,
            'subtotal': float(self.subtotal or 0),
            'discount': float(self.discount or 0),
            'total': float(self.total or 0),
            'payment_method': self.payment_method,
            'status': self.status,
            'items': [i.to_dict() for i in self.items],
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class SaleItem(db.Model):
    __tablename__ = 'sale_items'
    __table_args__ = (
        db.Index('idx_sale_item_sale', 'sale_id'),
        db.Index('idx_sale_item_product', 'product_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), default=0.0, nullable=False)

    product = db.relationship('Product')

    @property
    def total(self):
        return float(self.quantity or 0) * float(self.unit_price or 0)

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else None,
            'quantity': float(self.quantity or 0),
            'unit_price': float(self.unit_price or 0),
            'total': self.total,
        }


ACCOUNT_TYPES = ('asset', 'liability', 'equity', 'income', 'expense')

NORMAL_BALANCE = {
    'asset': 'debit',
    'liability': 'credit',
    'equity': 'credit',
    'income': 'credit',
    'expense': 'debit',
}


class Account(db.Model):
    __tablename__ = 'accounts'
    __table_args__ = (
        db.Index('idx_account_code', 'code'),
        db.Index('idx_account_type', 'account_type'),
        db.Index('idx_account_parent', 'parent_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    account_type = db.Column(db.String(20), nullable=False)  # asset/liability/equity/income/expense
    parent_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)
    opening_balance = db.Column(db.Numeric(14, 2), default=0.0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    parent = db.relationship('Account', remote_side=[id], backref='children')
    lines = db.relationship('JournalEntryLine', backref='account', lazy='dynamic')

    @property
    def normal_balance(self):
        return NORMAL_BALANCE.get(self.account_type, 'debit')

    @property
    def is_leaf(self):
        return len(self.children) == 0

    def balance(self):
        """الرصيد الحالي من الحركات المباشرة + الرصيد الافتتاحي."""
        total_debit = float(self.lines.with_entities(db.func.coalesce(db.func.sum(JournalEntryLine.debit), 0)).scalar() or 0)
        total_credit = float(self.lines.with_entities(db.func.coalesce(db.func.sum(JournalEntryLine.credit), 0)).scalar() or 0)
        opening = float(self.opening_balance or 0)
        if self.normal_balance == 'debit':
            return opening + total_debit - total_credit
        return opening + total_credit - total_debit

    @property
    def type_label(self):
        return {'asset': 'أصل', 'liability': 'خصم', 'equity': 'حقوق ملكية',
                'income': 'إيراد', 'expense': 'مصروف'}.get(self.account_type, self.account_type)

    @property
    def normal_balance_label(self):
        return 'مدين' if self.normal_balance == 'debit' else 'دائن'

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'account_type': self.account_type,
            'parent_id': self.parent_id,
            'opening_balance': float(self.opening_balance or 0),
            'is_active': self.is_active,
            'balance': self.balance(),
        }


class JournalEntry(db.Model):
    __tablename__ = 'journal_entries'
    __table_args__ = (
        db.Index('idx_journal_date', 'date'),
        db.Index('idx_journal_number', 'entry_number'),
        db.Index('idx_journal_source', 'source_type', 'source_id', unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    entry_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    date = db.Column(db.Date, default=date.today, nullable=False)
    description = db.Column(db.String(500))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    source_type = db.Column(db.String(30), nullable=True)
    source_id = db.Column(db.Integer, nullable=True)

    lines = db.relationship('JournalEntryLine', backref='entry', lazy='select',
                            cascade='all, delete-orphan')
    creator = db.relationship('User', foreign_keys=[created_by])

    @property
    def total(self):
        return sum(float(l.debit or 0) for l in self.lines)

    @property
    def is_balanced(self):
        debits = sum(float(l.debit or 0) for l in self.lines)
        credits = sum(float(l.credit or 0) for l in self.lines)
        return abs(debits - credits) < 0.005

    def to_dict(self):
        return {
            'id': self.id,
            'entry_number': self.entry_number,
            'date': self.date.isoformat() if self.date else None,
            'description': self.description,
            'total': self.total,
            'lines': [l.to_dict() for l in self.lines],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'source_type': self.source_type,
            'source_id': self.source_id,
        }


class JournalEntryLine(db.Model):
    __tablename__ = 'journal_entry_lines'
    __table_args__ = (
        db.Index('idx_journal_line_entry', 'entry_id'),
        db.Index('idx_journal_line_account', 'account_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    debit = db.Column(db.Numeric(14, 2), default=0.0, nullable=False)
    credit = db.Column(db.Numeric(14, 2), default=0.0, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'entry_id': self.entry_id,
            'account_id': self.account_id,
            'account_code': self.account.code if self.account else None,
            'account_name': self.account.name if self.account else None,
            'debit': float(self.debit or 0),
            'credit': float(self.credit or 0),
        }


class LedgerEntry(db.Model):
    """دفتر الأستاذ: صف لكل سطر قيد مع الرصيد الجاري للحساب.

    يُبنى من journal_entry_lines بالترتيب (التاريخ، رقم القيد، رقم السطر)
    ويُعاد حسابه عند إضافة/حذف أي قيد يمس الحساب.
    """
    __tablename__ = 'ledger_entries'
    __table_args__ = (
        db.Index('idx_ledger_account_date', 'account_id', 'date'),
        db.Index('idx_ledger_entry', 'entry_id'),
        db.UniqueConstraint('line_id', name='uq_ledger_line'),
    )

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'), nullable=False)
    line_id = db.Column(db.Integer, db.ForeignKey('journal_entry_lines.id'),
                        nullable=False, unique=True)
    date = db.Column(db.Date, nullable=False, index=True)
    debit = db.Column(db.Numeric(14, 2), default=0.0, nullable=False)
    credit = db.Column(db.Numeric(14, 2), default=0.0, nullable=False)
    running_balance = db.Column(db.Numeric(14, 2), default=0.0, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    account = db.relationship('Account', backref='ledger_entries')
    entry = db.relationship('JournalEntry', backref='ledger_entries')

    def to_dict(self):
        return {
            'id': self.id,
            'account_id': self.account_id,
            'account_code': self.account.code if self.account else None,
            'account_name': self.account.name if self.account else None,
            'entry_id': self.entry_id,
            'entry_number': self.entry.entry_number if self.entry else None,
            'date': self.date.isoformat() if self.date else None,
            'debit': float(self.debit or 0),
            'credit': float(self.credit or 0),
            'running_balance': float(self.running_balance or 0),
        }
