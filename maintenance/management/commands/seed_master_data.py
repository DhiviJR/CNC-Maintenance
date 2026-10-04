from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from maintenance.models import (
    ProductionLine,
    CNCMachine,
    FailureCategory,
    FailureSubCategory,
    SparePart
)


class Command(BaseCommand):
    help = "Seed initial master data: 4M categories, sub-categories, spare parts, and sample CNC machines."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding Master Data..."))

        # 1. Ensure Superuser / Admin & Technician users
        admin_user, created = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@factory.com", "is_staff": True, "is_superuser": True}
        )
        if created:
            admin_user.set_password("admin123")
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("Created admin user: admin / admin123"))

        tech_user, created = User.objects.get_or_create(
            username="tech_john",
            defaults={"first_name": "John", "last_name": "Doe", "email": "john@factory.com", "is_staff": True}
        )
        if created:
            tech_user.set_password("tech123")
            tech_user.save()
            self.stdout.write(self.style.SUCCESS("Created technician user: tech_john / tech123"))

        # 2. 4M Categories
        four_m = [
            ("MAN", "Man (Personnel / Human Factor)", "Human factors including operator error, lack of training, improper handling, or negligence."),
            ("MACHINE", "Machine (Mechanical / Electrical Equipment)", "Physical equipment failure including servo alarms, spindle wear, hydraulic leaks, and sensor faults."),
            ("MATERIAL", "Material (Raw Stock / Workpiece Defect)", "Workpiece variances such as raw material hardness, casting defects, or incorrect dimensions."),
            ("METHOD", "Method (Program / Process / Feeds & Speeds)", "Procedural issues such as G-code errors, excessive feed rates, or improper clamping."),
        ]
        cat_map = {}
        for code, name, desc in four_m:
            cat, _ = FailureCategory.objects.get_or_create(code=code, defaults={"name": name, "description": desc})
            cat_map[code] = cat

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(cat_map)} 4M categories."))

        # 3. 4M Sub-Categories
        sub_categories = [
            # Machine
            ("MACHINE", "MCH-SPN-01", "Spindle Bearing Overheat / Noise", "Excessive heat or vibration on main spindle bearings."),
            ("MACHINE", "MCH-SRV-02", "Servo Axis Overload / Error", "X/Y/Z servo drive alarm or current overload."),
            ("MACHINE", "MCH-HYD-03", "Hydraulic Pressure Low / Leak", "Hydraulic pack pressure loss or valve leakage."),
            ("MACHINE", "MCH-PNM-04", "Pneumatic Air Pressure Loss", "Main line pressure drop below 5 bar interlock."),
            ("MACHINE", "MCH-LUB-05", "Way Lubrication Low Level / Blockage", "Central slideway lubrication pump empty or line clogged."),
            ("MACHINE", "MCH-COL-06", "Coolant Pump Trip / Flow Failure", "Coolant delivery motor overload or filter clogged."),
            ("MACHINE", "MCH-ATC-07", "Automatic Tool Changer Jam", "Tool arm stuck during tool exchange sequence."),
            ("MACHINE", "MCH-SNS-08", "Door Interlock / Limit Sensor Fault", "Safety door limit switch stuck or wire broken."),

            # Man
            ("MAN", "MAN-ERR-01", "Operator Incorrect Part Clamping", "Part clamped out of alignment leading to collision."),
            ("MAN", "MAN-OFS-02", "Incorrect Tool Offset Entry", "Tool wear or geometry offset entered with wrong sign."),
            ("MAN", "MAN-TRN-03", "Lack of Operating Procedure Knowledge", "Operator unfamiliar with machine cycle start interlocks."),
            ("MAN", "MAN-NEG-04", "Neglected Pre-Operation Daily Check", "Failure to check oil levels before shift start."),

            # Material
            ("MATERIAL", "MAT-HRD-01", "Raw Material Hard Spot / Inconsistency", "Hard casting spot broke cutting insert."),
            ("MATERIAL", "MAT-DIM-02", "Raw Blank Over-sized / Under-sized", "Casting blank thickness outside permissible tolerance."),
            ("MATERIAL", "MAT-DEF-03", "Porosity / Structural Casting Defect", "Internal air pockets caused chatter or tool failure."),

            # Method
            ("METHOD", "MET-GCD-01", "G-Code / M-Code Syntax Error", "Incorrect syntax or non-existent code called in CNC program."),
            ("METHOD", "MET-FSP-02", "Excessive Feed Rate / Spindle Speed", "Cutting parameters too aggressive for chosen tool/material."),
            ("METHOD", "MET-CLP-03", "Improper Clamping Pressure / Setup", "Hydraulic chuck pressure set too low for cutting forces."),
            ("METHOD", "MET-WRK-04", "Incorrect Work Coordinate Preset (G54)", "Origin work offset established at wrong datum surface."),
        ]

        sub_count = 0
        for cat_code, sub_code, name, desc in sub_categories:
            _, created = FailureSubCategory.objects.get_or_create(
                sub_category_code=sub_code,
                defaults={"category": cat_map[cat_code], "name": name, "description": desc}
            )
            if created:
                sub_count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {sub_count} 4M sub-categories."))

        # 4. Spare Parts Master Catalog
        spare_parts = [
            ("BRG-7014C", "Angular Contact Spindle Bearing 7014C", "MECHANICAL", "70x110x20mm High Precision", "PCS", Decimal("18500.00"), 4),
            ("BRG-6205", "Deep Groove Ball Bearing 6205-2RS", "MECHANICAL", "25x52x15mm", "PCS", Decimal("650.00"), 15),
            ("BELT-TIM-500", "Timing Belt 500-5M-25", "MECHANICAL", "High torque neoprene", "PCS", Decimal("1200.00"), 8),
            ("SOL-24V-HYD", "Hydraulic Solenoid Valve 24V DC", "HYDRAULIC", "Rexroth 4WE6 Directional", "PCS", Decimal("7800.00"), 3),
            ("SEAL-HYD-50", "Hydraulic Cylinder Seal Kit 50mm", "HYDRAULIC", "Polyurethane high-pressure", "SETS", Decimal("2200.00"), 6),
            ("PNM-VAL-52", "Pneumatic 5/2 Way Solenoid Valve", "PNEUMATIC", "SMC SY5120-5LZD-01", "PCS", Decimal("3400.00"), 5),
            ("SNS-PROX-12", "Inductive Proximity Sensor M12", "ELECTRICAL", "Omron PNP NO 4mm sensing", "PCS", Decimal("1450.00"), 12),
            ("RLY-OMR-24", "Miniature Power Relay 24V DC", "ELECTRICAL", "Omron MY4N-D2 4PDT", "PCS", Decimal("420.00"), 20),
            ("LUB-WAY-68", "Mobil Vactra No. 2 Way Oil", "LUBRICANT", "ISO VG 68 Slideway Oil", "LTRS", Decimal("380.00"), 50),
            ("LUB-SPN-10", "Spindle Lubricating Oil ISO VG 10", "LUBRICANT", "Shell Tellus S2 V 10", "LTRS", Decimal("520.00"), 30),
            ("TOOL-CNMG-120408", "Carbide Turning Insert CNMG 120408-PM", "TOOLING", "Sandvik CoroTurn 107", "PACKS", Decimal("4500.00"), 10),
            ("TOOL-APMT-1135", "Milling Insert APMT 1135PDER-M2", "TOOLING", "Mitsubishi TiAlN Coated", "PACKS", Decimal("3800.00"), 10),
            ("WIP-WAY-100", "Telescopic Slideway Wiper Brass Lip", "CONSUMABLE", "1000mm replacement strip", "METERS", Decimal("950.00"), 15),
        ]

        part_count = 0
        for code, name, cat, spec, uom, price, qty in spare_parts:
            _, created = SparePart.objects.get_or_create(
                part_code=code,
                defaults={
                    "part_name": name,
                    "category": cat,
                    "specification": spec,
                    "unit_of_measure": uom,
                    "unit_price": price,
                    "stock_quantity": qty,
                }
            )
            if created:
                part_count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {part_count} spare parts in master catalog."))

        # 5. Production Lines Master Table
        lines_data = [
            ("LINE-01", "Line 1 - Crankshaft Machining", "Shop Floor Bay 1", "High-volume crankshaft production line"),
            ("LINE-02", "Line 2 - Cylinder Block Line", "Shop Floor Bay 1", "Heavy VMC cylinder block line"),
            ("LINE-03", "Line 3 - Gearbox Turning Cell", "Shop Floor Bay 2", "High precision turning and lathe cell"),
            ("LINE-04", "Line 4 - Sub-Assembly Line", "Shop Floor Bay 3", "General component sub-assembly line"),
        ]

        production_lines = {}
        for l_code, l_name, l_loc, l_desc in lines_data:
            line_obj, _ = ProductionLine.objects.get_or_create(
                line_code=l_code,
                defaults={
                    "name": l_name,
                    "location": l_loc,
                    "description": l_desc,
                    "is_active": True,
                }
            )
            production_lines[l_code] = line_obj
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(production_lines)} production lines in master catalog."))

        # 6. CNC Machines Fleet
        machines = [
            ("CNC-01", "Fanuc Robodrill α-D21MiB5", "α-D21MiB5", "FANUC 31i-B", "192.168.1.101", 8193, "Bay 1 - Machining Line A", "LINE-01"),
            ("CNC-02", "Doosan DNM 5700 VMC", "DNM 5700", "FANUC 0i-MF Plus", "192.168.1.102", 8193, "Bay 1 - Machining Line A", "LINE-01"),
            ("CNC-03", "BFW Dhruva VMC 400", "Dhruva 400", "FANUC 0i-MF", "192.168.1.103", 8193, "Bay 2 - High Precision Bay", "LINE-02"),
            ("CNC-04", "Ace Micromatic Spark CNC Lathe", "Spark 200", "FANUC 0i-TF", "192.168.1.104", 8193, "Bay 2 - Turning Cell", "LINE-03"),
            ("CNC-05", "Mazak VCN-530C Vertical", "VCN-530C", "SmoothG / Fanuc", "192.168.1.105", 8193, "Bay 3 - Heavy Machining", "LINE-04"),
        ]

        mach_count = 0
        for m_code, name, model, ctrl, ip, port, loc, l_code in machines:
            p_line = production_lines.get(l_code)
            mach, created = CNCMachine.objects.get_or_create(
                machine_code=m_code,
                defaults={
                    "name": name,
                    "model_number": model,
                    "controller_type": ctrl,
                    "ip_address": ip,
                    "port": port,
                    "location": loc,
                    "production_line": p_line,
                    "line_name": p_line.name if p_line else "",
                    "current_status": "IDLE" if m_code in ["CNC-02", "CNC-04"] else "RUNNING" if m_code in ["CNC-01", "CNC-03"] else "OFFLINE",
                }
            )
            if not created and not mach.production_line:
                mach.production_line = p_line
                mach.line_name = p_line.name if p_line else mach.line_name
                mach.save()
            if created:
                mach_count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {mach_count} CNC machines (with auto-generated QR codes)."))
        self.stdout.write(self.style.SUCCESS("All Master Data successfully initialized!"))
