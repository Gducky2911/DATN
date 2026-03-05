
from models import (
    db, User, Table, Menu, Order, OrderItem,
    Payment, Inventory, Feedback, Promotion, Reservation, MenuIngredient
)
from datetime import datetime, timedelta, date
import random


def seed_database():
    print("Dang tao du lieu mau...")
    now = datetime.utcnow()
    today = date.today()

    print("Tao Users...")

    # Admin
    admin = User(
        name="Admin",
        email="admin@restaurant.vn",
        phone="0123456789",
        role="admin",
        active=True
    )
    admin.set_password("admin123")
    db.session.add(admin)

    employees_data = [
        ("Nguyễn Văn A", "waiter@restaurant.vn", "0987654321", "waiter", "waiter123", today - timedelta(days=90)),
        ("Trần Thị B", "chef@restaurant.vn", "0987654322", "chef", "chef123", today - timedelta(days=200)),  # hết hạn
        ("Lê Văn C", "cashier@restaurant.vn", "0987654323", "cashier", "cashier123", today),
        ("Phạm Thị D", "delivery@restaurant.vn", "0987654324", "delivery", "delivery123", today - timedelta(days=150)),
    ]

    for name, email, phone, emp_type, password, health_date in employees_data:
        emp = User(
            name=name,
            email=email,
            phone=phone,
            role="employee",
            employee_type=emp_type,
            health_check_date=health_date,
            active=True
        )
        emp.set_password(password)
        db.session.add(emp)

    # Customers
    customers_data = [
        ("Khách Hàng 1", "customer@restaurant.vn", "0901234567", "customer123"),
        ("Khách Hàng 2", "customer2@restaurant.vn", "0901234568", "customer123"),
        ("Khách Hàng 3", "customer3@restaurant.vn", "0901234569", "customer123"),
    ]

    for name, email, phone, password in customers_data:
        customer = User(
            name=name,
            email=email,
            phone=phone,
            role="customer",
            active=True
        )
        customer.set_password(password)
        db.session.add(customer)

    db.session.commit()

    print("Tao Tables...")
    tables_data = [
        ("T01", 2, "available", "indoor"),
        ("T02", 2, "available", "indoor"),
        ("T03", 4, "available", "indoor"),
        ("T04", 4, "available", "indoor"),
        ("T05", 6, "available", "indoor"),
        ("T06", 6, "available", "outdoor"),
        ("T07", 8, "available", "vip"),
        ("T08", 10, "available", "vip"),
        ("T09", 4, "occupied", "indoor"),
        ("T10", 2, "reserved", "outdoor"),
    ]

    for table_num, capacity, status, location in tables_data:
        db.session.add(Table(
            table_number=table_num,
            capacity=capacity,
            status=status,
            location=location
        ))

    db.session.commit()

    #03. Tao Menu
    print("Tao Menu...") 
    menu_data = [ ("Gỏi Cuốn", "Gỏi cuốn tôm thịt tươi ngon", 35000, "appetizer", "goi-cuon.jpg", True, 10, 180), ("Nem Rán", "Nem rán giòn rụm", 40000, "appetizer", "nem-ran.jpg", True, 15, 250), ("Salad Trộn", "Salad rau củ tươi", 45000, "appetizer", "salad.jpg", True, 8, 120), ("Phở Bò", "Phở bò Hà Nội truyền thống", 65000, "main", "pho-bo.jpg", True, 20, 450), ("Bún Chả", "Bún chả Hà Nội", 60000, "main", "bun-cha.jpg", True, 18, 520), ("Cơm Tấm", "Cơm tấm sườn bì chả", 55000, "main", "com-tam.jpg", True, 15, 650), ("Bún Bò Huế", "Bún bò Huế cay nồng", 70000, "main", "bun-bo-hue.jpg", True, 22, 480), ("Bánh Xèo", "Bánh xèo miền Tây", 50000, "main", "banh-xeo.jpg", True, 20, 380), ("Cá Kho Tộ", "Cá kho tộ đậm đà", 80000, "main", "ca-kho-to.jpg", True, 25, 410), ("Gà Nướng", "Gà nướng mật ong", 120000, "main", "ga-nuong.jpg", True, 30, 720), ("Chè Thái", "Chè thái hoa quả", 30000, "dessert", "che-thai.jpg", True, 10, 300), ("Bánh Flan", "Bánh flan caramel", 25000, "dessert", "banh-flan.jpg", True, 8, 180), ("Chè Ba Màu", "Chè ba màu truyền thống", 28000, "dessert", "che-ba-mau.jpg", True, 10, 260), ("Trà Đá", "Trà đá mát lạnh", 10000, "drink", "tra-da.jpg", True, 3, 0), ("Cà Phê Sữa Đá", "Cà phê sữa đá Việt Nam", 25000, "drink", "ca-phe-sua.jpg", True, 8, 120), ("Nước Chanh", "Nước chanh tươi", 20000, "drink", "nuoc-chanh.jpg", True, 5, 80), ("Sinh Tố Bơ", "Sinh tố bơ béo ngậy", 35000, "drink", "sinh-to-bo.jpg", True, 10, 250), ("Bia Sài Gòn", "Bia Sài Gòn chai", 20000, "drink", "bia.jpg", True, 2, 150), ]
    for name, desc, price, category, image, available, prep_time, calories in menu_data:
        db.session.add(Menu(
            name=name,
            description=desc,
            price=price,
            category=category,
            image_url=image,
            available=available,
            preparation_time=prep_time,
            calories=calories
        ))

    db.session.commit()

    print("Tao Inventory...")
    # (name, quantity, unit, unit_cost, threshold, supplier, expiry)
    inventory_data = [
        ("Thịt Bò", 50, "kg", 280000, 20, "Nhà cung cấp A", today + timedelta(days=5)),      # 280k/kg
        ("Thịt Heo", 40, "kg", 120000, 15, "Nhà cung cấp A", today + timedelta(days=3)),     # 120k/kg
        ("Tôm", 20, "kg", 250000, 10, "Nhà cung cấp B", today + timedelta(days=2)),          # 250k/kg
        ("Rau Sống", 30, "kg", 25000, 10, "Nhà cung cấp C", today + timedelta(days=1)),      # 25k/kg
        ("Gạo", 200, "kg", 18000, 50, "Nhà cung cấp E", today + timedelta(days=365)),        # 18k/kg
        ("Dầu Ăn", 40, "liter", 45000, 15, "Nhà cung cấp E", today + timedelta(days=300)),   # 45k/liter
    ]

    for name, qty, unit, unit_cost, threshold, supplier, expiry in inventory_data:
        db.session.add(Inventory(
            name=name,
            quantity=qty,
            unit=unit,
            unit_cost=unit_cost,
            threshold=threshold,
            supplier=supplier,
            expiry_date=expiry
        ))

    db.session.commit()

    print("Tao MenuIngredient (lien ket mon an - nguyen lieu)...")
    # Lấy menu items và inventory items
    menus = {m.name: m.menu_id for m in Menu.query.all()}
    inventories = {i.name: i.item_id for i in Inventory.query.all()}

    # Định nghĩa nguyên liệu cho từng món (menu_name, inventory_name, quantity_needed)
    menu_ingredients_data = [
        # Gỏi Cuốn
        ("Gỏi Cuốn", "Tôm", 0.1),
        ("Gỏi Cuốn", "Thịt Heo", 0.05),
        ("Gỏi Cuốn", "Rau Sống", 0.1),

        # Nem Rán
        ("Nem Rán", "Thịt Heo", 0.15),
        ("Nem Rán", "Rau Sống", 0.05),
        ("Nem Rán", "Dầu Ăn", 0.1),

        # Salad Trộn
        ("Salad Trộn", "Rau Sống", 0.2),
        ("Salad Trộn", "Dầu Ăn", 0.02),

        # Phở Bò
        ("Phở Bò", "Thịt Bò", 0.2),
        ("Phở Bò", "Rau Sống", 0.1),

        # Bún Chả
        ("Bún Chả", "Thịt Heo", 0.2),
        ("Bún Chả", "Rau Sống", 0.1),
        ("Bún Chả", "Dầu Ăn", 0.05),

        # Cơm Tấm
        ("Cơm Tấm", "Thịt Heo", 0.2),
        ("Cơm Tấm", "Gạo", 0.2),
        ("Cơm Tấm", "Dầu Ăn", 0.05),

        # Bún Bò Huế
        ("Bún Bò Huế", "Thịt Bò", 0.2),
        ("Bún Bò Huế", "Rau Sống", 0.1),
        ("Bún Bò Huế", "Dầu Ăn", 0.03),

        # Bánh Xèo
        ("Bánh Xèo", "Tôm", 0.1),
        ("Bánh Xèo", "Thịt Heo", 0.1),
        ("Bánh Xèo", "Rau Sống", 0.15),
        ("Bánh Xèo", "Dầu Ăn", 0.2),

        # Cá Kho Tộ (đi kèm cơm)
        ("Cá Kho Tộ", "Gạo", 0.2),
        ("Cá Kho Tộ", "Dầu Ăn", 0.1),

        # Gà Nướng
        ("Gà Nướng", "Dầu Ăn", 0.1),
        ("Gà Nướng", "Rau Sống", 0.1),
    ]

    for menu_name, inv_name, qty in menu_ingredients_data:
        if menu_name in menus and inv_name in inventories:
            db.session.add(MenuIngredient(
                menu_id=menus[menu_name],
                inventory_id=inventories[inv_name],
                quantity_needed=qty
            ))

    db.session.commit()

    print("Hoan thanh tao du lieu mau!")
