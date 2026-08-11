from datetime import date
from decimal import Decimal, InvalidOperation

from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, TextAreaField, DateField
from wtforms.validators import Optional, Length


def _to_decimal(value):
    try:
        return Decimal(str(value).strip().replace(',', ''))
    except (InvalidOperation, TypeError, ValueError):
        return None


class SaleForm(FlaskForm):
    client_id = SelectField('العميل', choices=[], coerce=int, validators=[Optional()])
    payment_method = SelectField('طريقة الدفع', choices=[
        ('cash', 'نقدي'),
        ('credit', 'آجل'),
    ], default='cash')
    discount_type = SelectField('نوع الخصم', choices=[
        ('amount', 'مبلغ'),
        ('percent', 'نسبة مئوية'),
    ], default='amount')
    discount_value = StringField('قيمة الخصم', validators=[Optional()])
    date = DateField('التاريخ', format='%Y-%m-%d', default=date.today, validators=[Optional()])
    notes = TextAreaField('ملاحظات', validators=[
        Optional(),
        Length(max=1000, message='الملاحظات طويلة جداً'),
    ])

    def get_discount_decimal(self):
        val = _to_decimal(self.discount_value.data)
        return val if val is not None else Decimal('0')

    def get_items_from_request(self, request):
        """قراءة بنود البيع من الصفوف المتكررة.
        تُرجع (items, errors) حيث items قائمة dict لكل بند."""
        from app.models import Product, db
        product_ids = request.form.getlist('product_id')
        quantities = request.form.getlist('quantity')
        unit_prices = request.form.getlist('unit_price')

        items = []
        errors = []
        seen = {}
        for idx in range(len(product_ids)):
            pid_raw = (product_ids[idx] or '').strip()
            if not pid_raw:
                continue
            try:
                pid = int(pid_raw)
            except (TypeError, ValueError):
                errors.append(f'البند {idx + 1}: معرّف المنتج غير صالح')
                continue
            product = db.session.get(Product, pid)
            if not product or not product.is_active:
                errors.append(f'البند {idx + 1}: المنتج غير موجود أو غير نشط')
                continue
            qty_raw = quantities[idx] if idx < len(quantities) else ''
            price_raw = unit_prices[idx] if idx < len(unit_prices) else ''
            qty = _to_decimal(qty_raw)
            price = _to_decimal(price_raw)
            if qty is None or qty <= 0:
                errors.append(f'البند "{product.name}": الكمية يجب أن تكون رقماً أكبر من صفر')
                continue
            if price is None or price < 0:
                errors.append(f'البند "{product.name}": السعر غير صالح')
                continue
            if pid in seen:
                seen[pid]['quantity'] += qty
                seen[pid]['unit_price'] = price
            else:
                seen[pid] = {'product': product, 'quantity': qty, 'unit_price': price}
        items = list(seen.values())
        if not items:
            errors.append('يجب إضافة بند واحد على الأقل بمنتج وكمية')
        return items, errors
