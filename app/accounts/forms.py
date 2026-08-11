from datetime import date
from decimal import Decimal, InvalidOperation

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, DateField, TextAreaField
from wtforms.validators import DataRequired, Optional, Length, ValidationError


def _to_decimal(value):
    try:
        return Decimal(str(value).strip().replace(',', ''))
    except (InvalidOperation, TypeError, ValueError):
        return None


class AccountForm(FlaskForm):
    code = StringField('رقم الحساب', validators=[
        DataRequired(message='رقم الحساب مطلوب'),
        Length(max=30, message='رقم الحساب طويل جداً'),
    ])
    name = StringField('اسم الحساب', validators=[
        DataRequired(message='اسم الحساب مطلوب'),
        Length(max=200, message='الاسم يجب أن يكون بين 1 و 200 حرف'),
    ])
    account_type = SelectField('النوع', choices=[
        ('asset', 'أصل'),
        ('liability', 'خصم'),
        ('equity', 'حقوق ملكية'),
        ('income', 'إيراد'),
        ('expense', 'مصروف'),
    ], default='asset')
    parent_id = SelectField('الحساب الأب', choices=[], coerce=int, validators=[Optional()])
    opening_balance = StringField('الرصيد الافتتاحي', validators=[Optional()])

    def get_opening_balance_decimal(self):
        val = _to_decimal(self.opening_balance.data)
        return val if val is not None else Decimal('0')


class JournalEntryForm(FlaskForm):
    date = DateField('التاريخ', format='%Y-%m-%d', default=date.today, validators=[
        DataRequired(message='التاريخ مطلوب'),
    ])
    description = TextAreaField('البيان', validators=[
        DataRequired(message='بيان القيد مطلوب'),
        Length(max=500, message='البيان طويل جداً'),
    ])

    def get_lines_from_request(self, request):
        """قراءة خطوط القيد من الصفوف المتكررة (account_id/debit/credit).
        تُرجع (lines, errors)."""
        from app.models import Account, db
        account_ids = request.form.getlist('account_id')
        debits = request.form.getlist('debit')
        credits = request.form.getlist('credit')

        lines = []
        errors = []
        for idx in range(len(account_ids)):
            aid_raw = (account_ids[idx] or '').strip()
            if not aid_raw:
                continue
            try:
                aid = int(aid_raw)
            except (TypeError, ValueError):
                errors.append(f'السطر {idx + 1}: معرّف الحساب غير صالح')
                continue
            account = db.session.get(Account, aid)
            if not account or not account.is_active:
                errors.append(f'السطر {idx + 1}: الحساب غير موجود أو غير نشط')
                continue
            if not account.is_leaf:
                errors.append(f'السطر {idx + 1}: لا يمكن الترحيل لحساب "{account.name}" لأنه يحتوي حسابات فرعية')
                continue
            debit = _to_decimal(debits[idx]) if idx < len(debits) else None
            credit = _to_decimal(credits[idx]) if idx < len(credits) else None
            debit = debit if debit is not None else Decimal('0')
            credit = credit if credit is not None else Decimal('0')
            if debit < 0 or credit < 0:
                errors.append(f'السطر "{account.name}": لا يمكن استخدام مبالغ سالبة')
                continue
            if debit > 0 and credit > 0:
                errors.append(f'السطر "{account.name}": لا يمكن أن يكون ديناً وائتماناً معاً')
                continue
            if debit == 0 and credit == 0:
                errors.append(f'السطر "{account.name}": أدخل مبلغاً في العمود المدين أو الدائن')
                continue
            lines.append({'account': account, 'debit': debit, 'credit': credit})
        if len(lines) < 2:
            errors.append('يجب أن يحتوي القيد على سطرين على الأقل')
            return lines, errors
        total_debit = sum(float(l['debit']) for l in lines)
        total_credit = sum(float(l['credit']) for l in lines)
        if total_debit <= 0 or total_credit <= 0:
            errors.append('يجب أن يتضمن القيد قيداً مديناً وآخر دائناً على الأقل')
        elif abs(total_debit - total_credit) > 0.005:
            errors.append(f'القيد غير متوازن — مجموع المدين ({total_debit:,.2f}) لا يساوي مجموع الدائن ({total_credit:,.2f})')
        return lines, errors
