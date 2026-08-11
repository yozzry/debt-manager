from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, DateField
from wtforms.validators import DataRequired, NumberRange, Length, Optional


class InvoiceForm(FlaskForm):
    amount = FloatField('المبلغ', validators=[
        DataRequired(message='المبلغ مطلوب'),
        NumberRange(min=0.01, message='المبلغ يجب أن يكون أكبر من صفر'),
    ])
    description = StringField('الوصف', validators=[
        Optional(),
        Length(max=500, message='الوصف طويل جداً'),
    ])
    date = DateField('التاريخ', validators=[
        Optional(),
    ])


class InvoiceEditForm(FlaskForm):
    amount = FloatField('المبلغ', validators=[
        DataRequired(message='المبلغ مطلوب'),
        NumberRange(min=0.01, message='المبلغ يجب أن يكون أكبر من صفر'),
    ])
    description = StringField('الوصف', validators=[
        Optional(),
        Length(max=500, message='الوصف طويل جداً'),
    ])
    date = DateField('التاريخ', validators=[
        Optional(),
    ])
