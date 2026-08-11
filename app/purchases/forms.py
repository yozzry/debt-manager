from datetime import date
from decimal import Decimal, InvalidOperation

from flask_wtf import FlaskForm
from wtforms import SelectField, DateField, TextAreaField
from wtforms.validators import DataRequired, Optional, Length


def _to_decimal(value):
    try:
        return Decimal(str(value).strip().replace(',', ''))
    except (InvalidOperation, TypeError, ValueError):
        return None


class PurchaseOrderForm(FlaskForm):
    supplier_id = SelectField('المورد', choices=[], coerce=int, validators=[
        DataRequired(message='المورد مطلوب'),
    ])
    date = DateField('التاريخ', format='%Y-%m-%d', default=date.today, validators=[
        DataRequired(message='التاريخ مطلوب'),
    ])
    notes = TextAreaField('ملاحظات', validators=[
        Optional(),
        Length(max=1000, message='الملاحظات طويلة جداً'),
    ])

    def get_items_from_request(self, request):
        """قراءة بنود الأمر المرسلة كصفوف متكررة.
        كل صف = (product_id, quantity, unit_cost) عبر getlist.
        تُرجع (items, errors) حيث items قائمة بالقيم المُعالجة."""
        from app.models import Product, db
        product_ids = request.form.getlist('product_id')
        quantities = request.form.getlist('quantity')
        unit_costs = request.form.getlist('unit_cost')

        items = []
        errors = []
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
            if not product:
                errors.append(f'البند {idx + 1}: المنتج غير موجود')
                continue
            qty_raw = quantities[idx] if idx < len(quantities) else ''
            cost_raw = unit_costs[idx] if idx < len(unit_costs) else ''
            qty = _to_decimal(qty_raw)
            cost = _to_decimal(cost_raw)
            if qty is None or qty <= 0:
                errors.append(f'البند "{product.name}": الكمية يجب أن تكون رقماً أكبر من صفر')
                continue
            if cost is None or cost < 0:
                errors.append(f'البند "{product.name}": سعر التكلفة غير صالح')
                continue
            items.append({
                'product': product,
                'quantity': qty,
                'unit_cost': cost,
            })
        if not items:
            errors.append('يجب إضافة بند واحد على الأقل بمنتج وكمية')
        return items, errors
