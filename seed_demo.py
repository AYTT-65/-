from datetime import datetime
from app import app, get_db

products = [
    ('iPad 9', 'أجهزة iPad', 'IPD-009', 300000, 330000, 30000, 12, 'أداء قوي للدراسة والألعاب والترفيه.', 'شاشة 10.2 بوصة، ذاكرة 64GB، بطارية طويلة', '📱', 1),
    ('سماعة AirPods', 'سماعات', 'AUD-001', 85000, 95000, 10000, 20, 'صوت نقي واتصال سريع طوال اليوم.', 'بلوتوث، عزل ضوضاء، علبة شحن', '🎧', 1),
    ('شاحن سريع USB-C', 'شواحن', 'CHG-020', 25000, 0, 0, 30, 'شحن سريع وآمن لأجهزتك.', 'قدرة 20W، حماية من الحرارة', '🔌', 0),
    ('Magic Keyboard', 'كيبورد', 'KEY-010', 120000, 0, 0, 8, 'تجربة كتابة مريحة وأنيقة.', 'اتصال لاسلكي، تصميم نحيف', '⌨️', 1),
]

with app.app_context():
    db = get_db()
    for name, category, sku, price, old_price, discount, stock, description, specifications, icon, featured in products:
        db.execute('''INSERT OR IGNORE INTO products
            (name, category, sku, price, old_price, discount, stock, description, specifications, icon, featured, visible, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)''',
            (name, category, sku, price, old_price, discount, stock, description, specifications, icon, featured, datetime.now().isoformat(timespec='seconds')))
    product_ids = {row['sku']: row['id'] for row in db.execute('SELECT id, sku FROM products').fetchall()}
    banners = [
        ('iPad 9', 'أداء قوي للدراسة والألعاب والترفيه', 300000, 30000, product_ids.get('IPD-009'), 1),
        ('صوتك أوضح', 'سماعات خفيفة بصوت غني واتصال سريع', 85000, 10000, product_ids.get('AUD-001'), 2),
        ('كل طاقتك', 'شاحن سريع يحافظ على أجهزتك', 25000, 0, product_ids.get('CHG-020'), 3),
    ]
    for title, description, price, discount, product_id, sort_order in banners:
        if not db.execute('SELECT 1 FROM banners WHERE title = ?', (title,)).fetchone():
            db.execute('''INSERT INTO banners
                (title, description, price, discount, product_id, sort_order, duration, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 5, 1, ?)''',
                (title, description, price, discount, product_id, sort_order, datetime.now().isoformat(timespec='seconds')))
    db.commit()
    print('Demo products and banners are ready.')
