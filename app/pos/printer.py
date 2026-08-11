# الطباعة الحرارية لإيصالات نقطة البيع عبر python-escpos
from app.models import Settings


def _fmt_amount(n):
    return f'{float(n or 0):,.2f}'


def _wrap_line(text, width=44):
    """تقسيم النص إلى أسطر لا تتجاوز عرض الطابعة الحرارية."""
    text = str(text)
    if len(text) <= width:
        return [text]
    words = text.split(' ')
    lines = []
    current = ''
    for w in words:
        if not current:
            current = w
        elif len(current) + 1 + len(w) <= width:
            current += ' ' + w
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def _text(p, text, width=44):
    for line in _wrap_line(text, width):
        p.textln(line)


def build_receipt_bytes(sale):
    """بناء دفق ESC/POS لإيصال البيع بدون اتصال بطابعة فعلية. تُرجع bytes."""
    from escpos.printer import Dummy

    p = Dummy()
    try:
        p.charcode('CP1256')

        p.set(align='center', bold=True, height=2, width=2)
        p.textln('DEBT MANAGER')
        p.set(align='center', bold=False, height=1, width=1)
        p.textln('نظام إدارة المديونيات')
        p.textln('========================')

        p.set(align='center', bold=True)
        _text(p, f'فاتورة {sale.invoice_number}', 40)
        p.set(align='center', bold=False)
        created = sale.created_at.strftime('%H:%M') if sale.created_at else ''
        p.textln(f'{sale.date:%Y-%m-%d} {created}'.strip())
        if sale.client:
            _text(p, f'العميل: {sale.client.name}', 40)

        p.textln('------------------------')

        p.set(align='left')
        for it in sale.items:
            _text(p, it.product.name, 40)
            line_total = float(it.quantity) * float(it.unit_price)
            p.textln(f'{it.quantity:g} x {_fmt_amount(it.unit_price)}')
            p.set(align='right')
            p.textln(f'= {_fmt_amount(line_total)}')
            p.set(align='left')

        p.textln('------------------------')
        p.set(align='right')
        _text(p, f'المجموع الفرعي: {_fmt_amount(sale.subtotal)}', 40)
        if float(sale.discount or 0):
            _text(p, f'الخصم: {_fmt_amount(sale.discount)}', 40)
        p.set(bold=True, height=2, width=2)
        p.textln(f'الإجمالي: {_fmt_amount(sale.total)}')
        p.set(bold=False, height=1, width=1)
        p.set(align='right')
        _text(p, f'طريقة الدفع: {sale.payment_method_label}', 40)
        if sale.notes:
            p.textln('ملاحظات:')
            p.set(align='left')
            _text(p, sale.notes, 40)

        p.set(align='center')
        p.textln('')
        p.textln('شكراً لتعاملكم معنا')
        p.cut()
        return bytes(p.output)
    finally:
        p.close()


def print_receipt(sale):
    """إرسال الإيصال إلى طابعة حرارية حسب اسم الطابعة المحفوظ في الإعدادات.

    تُرجع (ok: bool, msg: str) — لا تُرمي استثناءات.
    """
    printer_name = (Settings.get('pos_printer_name', '') or '').strip()
    if not printer_name:
        return False, 'الطباعة الحرارية معطلة — حدد اسم الطابعة من الإعدادات أولاً'
    try:
        from escpos.printer import Win32Raw
    except Exception as e:
        return False, f'وحدة الطباعة الحرارية غير متوفرة على هذا الجهاز: {e}'
    try:
        data = build_receipt_bytes(sale)
        p = Win32Raw(printer_name)
        p._raw(data)
        p.close()
        return True, 'تم إرسال الإيصال إلى الطابعة'
    except Exception as e:
        return False, f'فشلت الطباعة على "{printer_name}": {e}'
