import re
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length, ValidationError


def validate_phone_ar(form, field):
    phone = field.data.strip() if field.data else ''
    if not phone:
        return
    cleaned = phone.replace(' ', '').replace('-', '')
    if not re.match(r'^(\+?\d{7,15}|\d{7,15})$', cleaned):
        raise ValidationError('رقم الهاتف غير صالح — يجب أن يحتوي على أرقام فقط (7-15 رقم)')


class LoginForm(FlaskForm):
    username = StringField('اسم المستخدم', validators=[
        DataRequired(message='اسم المستخدم مطلوب'),
    ])
    password = PasswordField('كلمة المرور', validators=[
        DataRequired(message='كلمة المرور مطلوبة'),
    ])


class AddUserForm(FlaskForm):
    username = StringField('اسم المستخدم', validators=[
        DataRequired(message='اسم المستخدم مطلوب'),
        Length(min=3, max=80, message='اسم المستخدم يجب أن يكون بين 3 و 80 حرف'),
    ])
    password = PasswordField('كلمة المرور', validators=[
        DataRequired(message='كلمة المرور مطلوبة'),
        Length(min=8, message='كلمة المرور يجب أن تكون 8 أحرف على الأقل'),
    ])
    role = SelectField('الدور', choices=[
        ('viewer', 'مشاهد'),
        ('editor', 'محرر'),
        ('cashier', 'أمين صندوق'),
        ('accountant', 'محاسب'),
        ('admin', 'مدير'),
    ], default='viewer')
