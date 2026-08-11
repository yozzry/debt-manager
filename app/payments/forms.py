from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, DateField
from wtforms.validators import DataRequired, NumberRange, Length, Optional


class PaymentForm(FlaskForm):
    amount = FloatField('المبلغ', validators=[
        DataRequired(message='المبلغ مطلوب'),
        NumberRange(min=0.01, message='المبلغ يجب أن يكون أكبر من صفر'),
    ])
    notes = StringField('ملاحظات', validators=[
        Optional(),
        Length(max=500, message='الملاحظات طويلة جداً'),
    ])
    payment_method = StringField('طريقة الدفع', validators=[
        Optional(),
        Length(max=50, message='اسم طريقة الدفع طويل جداً'),
    ])
    date = DateField('التاريخ', validators=[
        Optional(),
    ])


class PaymentEditForm(FlaskForm):
    amount = FloatField('المبلغ', validators=[
        DataRequired(message='المبلغ مطلوب'),
        NumberRange(min=0.01, message='المبلغ يجب أن يكون أكبر من صفر'),
    ])
    notes = StringField('ملاحظات', validators=[
        Optional(),
        Length(max=500, message='الملاحظات طويلة جداً'),
    ])
    payment_method = StringField('طريقة الدفع', validators=[
        Optional(),
        Length(max=50, message='اسم طريقة الدفع طويل جداً'),
    ])
    date = DateField('التاريخ', validators=[
        Optional(),
    ])
