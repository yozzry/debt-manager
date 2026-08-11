import re
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, SelectField, BooleanField
from wtforms.validators import DataRequired, Length, Optional, NumberRange, ValidationError


def validate_phone_ar(form, field):
    phone = field.data.strip() if field.data else ''
    if not phone:
        return
    cleaned = phone.replace(' ', '').replace('-', '').replace('+', '')
    if not cleaned.isdigit() or len(cleaned) < 3:
        raise ValidationError('رقم الهاتف غير صالح — يجب أن يحتوي على أرقام فقط (3 أرقام على الأقل)')


def validate_name_simple(form, field):
    name = field.data.strip() if field.data else ''
    if not name:
        raise ValidationError('الاسم مطلوب')
    if len(name) > 200:
        raise ValidationError('الاسم طويل جداً (الحد الأقصى 200 حرف)')


class ClientForm(FlaskForm):
    name = StringField('اسم العميل', validators=[
        DataRequired(message='اسم العميل مطلوب'),
        Length(min=1, max=200, message='الاسم يجب أن يكون بين 1 و 200 حرف'),
    ])
    type = SelectField('النوع', choices=[
        ('customer', 'عميل'),
        ('supplier', 'مورد'),
        ('employee', 'موظف'),
    ], default='customer')
    company_name = StringField('اسم الشركة / الجهة', validators=[
        Optional(),
        Length(max=200, message='اسم الشركة طويل جداً'),
    ])
    tax_id = StringField('الرقم الضريبي', validators=[
        Optional(),
        Length(max=100, message='الرقم الضريبي طويل جداً'),
    ])
    phone = StringField('رقم الهاتف', validators=[
        Optional(),
        validate_phone_ar,
    ])
    notes = TextAreaField('ملاحظات', validators=[
        Optional(),
        Length(max=1000, message='الملاحظات طويلة جداً'),
    ])


class ClientSettingsForm(FlaskForm):
    reminder_enabled = BooleanField('تفعيل التذكير')
    reminder_template = SelectField('قالب الرسالة', choices=[
        ('1', 'قالب 1'),
        ('2', 'قالب 2'),
        ('3', 'قالب 3'),
    ], default='1', coerce=str)
    reminder_frequency = SelectField('التكرار', choices=[
        ('', 'افتراضي (من الإعدادات)'),
        ('daily', 'يومياً'),
        ('weekly', 'أسبوعياً'),
        ('monthly', 'شهرياً'),
    ], default='')
    reminder_day = SelectField('اليوم', choices=[
        ('', 'افتراضي'),
        ('sun', 'الأحد'), ('mon', 'الاثنين'), ('tue', 'الثلاثاء'),
        ('wed', 'الأربعاء'), ('thu', 'الخميس'), ('fri', 'الجمعة'), ('sat', 'السبت'),
    ], default='')
    reminder_dom = StringField('يوم الشهر', validators=[Optional()])
    reminder_times = StringField('أوقات التذكير (اختياري)', validators=[
        Optional(),
    ])
