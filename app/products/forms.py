from decimal import Decimal, InvalidOperation
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, DecimalField, BooleanField
from wtforms.validators import DataRequired, Length, Optional, NumberRange, ValidationError

MOVEMENT_TYPES = [
    ('IN', 'إضافة (وارد)'),
    ('OUT', 'صرف (منصرف)'),
    ('ADJUST', 'تسوية مباشرة'),
]


def _to_decimal(value):
    try:
        return Decimal(str(value).strip().replace(',', ''))
    except (InvalidOperation, TypeError, ValueError):
        return None


def validate_positive_decimal(form, field):
    val = _to_decimal(field.data)
    if val is None:
        raise ValidationError('القيمة يجب أن تكون رقماً صحيحاً')
    if val <= 0:
        raise ValidationError('القيمة يجب أن تكون أكبر من صفر')


def validate_non_negative_decimal(form, field):
    val = _to_decimal(field.data)
    if val is None:
        raise ValidationError('القيمة يجب أن تكون رقماً صحيحاً')
    if val < 0:
        raise ValidationError('القيمة لا يمكن أن تكون سالبة')


class ProductForm(FlaskForm):
    name = StringField('اسم المنتج', validators=[
        DataRequired(message='اسم المنتج مطلوب'),
        Length(min=1, max=200, message='الاسم يجب أن يكون بين 1 و 200 حرف'),
    ])
    sku = StringField('رمز SKU', validators=[
        Optional(),
        Length(max=100, message='رمز SKU طويل جداً'),
    ])
    barcode = StringField('الباركود', validators=[
        Optional(),
        Length(max=100, message='الباركود طويل جداً'),
    ])
    category_id = SelectField('التصنيف', choices=[], coerce=int, validators=[Optional()])
    unit = StringField('الوحدة', validators=[
        Optional(),
        Length(max=30, message='اسم الوحدة طويل جداً'),
    ])
    cost_price = DecimalField('سعر التكلفة', validators=[
        Optional(),
        validate_non_negative_decimal,
    ])
    selling_price = DecimalField('سعر البيع', validators=[
        Optional(),
        validate_non_negative_decimal,
    ])
    min_stock = DecimalField('الحد الأدنى للمخزون', validators=[
        Optional(),
        validate_non_negative_decimal,
    ])
    description = TextAreaField('الوصف', validators=[
        Optional(),
        Length(max=1000, message='الوصف طويل جداً'),
    ])
    is_active = BooleanField('المنتج نشط')

    def get_field_decimal(self, field_name):
        val = _to_decimal(self.data.get(field_name))
        return val if val is not None else Decimal('0')


class CategoryForm(FlaskForm):
    name = StringField('اسم التصنيف', validators=[
        DataRequired(message='اسم التصنيف مطلوب'),
        Length(min=1, max=200, message='الاسم يجب أن يكون بين 1 و 200 حرف'),
    ])
    description = TextAreaField('الوصف', validators=[
        Optional(),
        Length(max=1000, message='الوصف طويل جداً'),
    ])


class StockAdjustForm(FlaskForm):
    movement_type = SelectField('نوع الحركة', choices=MOVEMENT_TYPES, default='IN')
    quantity = StringField('الكمية', validators=[
        DataRequired(message='الكمية مطلوبة'),
        validate_positive_decimal,
    ])
    notes = StringField('السبب / ملاحظات', validators=[
        Optional(),
        Length(max=500, message='الملاحظات طويلة جداً'),
    ])

    def get_quantity_decimal(self):
        val = _to_decimal(self.quantity.data)
        return val if val is not None else Decimal('0')
