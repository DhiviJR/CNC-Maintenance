import random
from decimal import Decimal
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from maintenance.models import (
    CNCMachine,
    FailureCategory,
    FailureSubCategory,
    SparePart,
    BreakdownTicket,
    TicketSpareUsage
)


class Command(BaseCommand):
    help = "Seed realistic historical tickets and downtime logs to populate Section 4 dashboard analytics."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding Demo Breakdown Tickets & Analytics Data..."))

        machines = list(CNCMachine.objects.filter(is_active=True))
        sub_categories = list(FailureSubCategory.objects.all())
        spare_parts = list(SparePart.objects.all())
        tech_user = User.objects.filter(username="tech_john").first() or User.objects.first()

        if not machines or not sub_categories:
            self.stdout.write(self.style.ERROR("Please run 'python manage.py seed_master_data' first!"))
            return

        shifts = ['Shift A', 'Shift B', 'Shift C']
        alarms_catalog = [
            ("DS0300 (APC) AXIS NEED ZRN", "Servo reference return required on X/Z axis."),
            ("EX1022 SPINDLE OVERHEAT", "Spindle motor temperature reached 78°C."),
            ("AL-401 SERVO VRDY OFF", "X-Axis servo velocity control ready signal OFF."),
            ("PN-05 LOW AIR PRESSURE", "Pneumatic supply dropped below 4.2 bar."),
            ("HYD-02 HYDRAULIC PRESSURE LOW", "Hydraulic chuck clamping pressure fault."),
            ("EMG-01 EMERGENCY STOP", "Operator pushed E-Stop button on panel."),
        ]

        # Generate 20 historical resolved tickets across the last 30 days
        now = timezone.now()
        created_count = 0

        for i in range(25):
            days_ago = random.randint(1, 28)
            hours_ago = random.randint(0, 23)
            mins_ago = random.randint(0, 59)
            t_alarm = now - timedelta(days=days_ago, hours=hours_ago, minutes=mins_ago)

            # Response time (MTTA): 3 to 18 minutes
            resp_mins = random.randint(3, 18)
            t_scan = t_alarm + timedelta(minutes=resp_mins)

            # Repair duration: 15 to 90 minutes
            repair_mins = random.randint(15, 90)
            t_resolve = t_scan + timedelta(minutes=repair_mins)

            # Ramp-up restart delay: 2 to 10 minutes
            ramp_mins = random.randint(2, 10)
            t_run = t_resolve + timedelta(minutes=ramp_mins)

            machine = random.choice(machines)
            sub_cat = random.choice(sub_categories)
            alarm_info = random.choice(alarms_catalog)
            shift = random.choice(shifts)

            ticket = BreakdownTicket.objects.create(
                machine=machine,
                trigger_source='EMERGENCY' if 'EMERGENCY' in alarm_info[0] else 'ALARM',
                status='CLOSED_RUNNING',
                shift=shift,
                focas_alarm_code=alarm_info[0],
                focas_alarm_msg=alarm_info[1],
                alarm_time=t_alarm,
                scan_time=t_scan,
                diagnosed_time=t_scan + timedelta(minutes=3),
                resolve_time=t_resolve,
                next_run_time=t_run,
                technician=tech_user,
                failure_sub_category=sub_cat,
                symptom_notes=f"Detected abnormal alarm code {alarm_info[0]} during production cycle.",
                resolution_notes="Inspected machine, replaced worn components, verified axis alignment and restored cycle.",
            )

            # Add 1 or 2 spare parts used
            if spare_parts and random.random() > 0.3:
                part = random.choice(spare_parts)
                qty = Decimal(random.choice([1, 2, 4]))
                TicketSpareUsage.objects.create(
                    ticket=ticket,
                    spare_part=part,
                    quantity=qty,
                    unit_price_at_use=part.unit_price,
                    notes="Preventive swap of damaged element."
                )

            created_count += 1

        # Create 1 Open Alarm ticket for immediate demonstration
        alarm_machine = machines[0]
        alarm_machine.current_status = 'ALARM'
        alarm_machine.save()

        BreakdownTicket.objects.create(
            machine=alarm_machine,
            trigger_source='ALARM',
            status='OPEN_ALARM',
            shift='Shift A',
            focas_alarm_code='EX1022 SPINDLE OVERHEAT',
            focas_alarm_msg='Spindle motor thermal overload triggered by sensor.',
            alarm_time=now - timedelta(minutes=14),
            symptom_notes='High pitch squeal observed from spindle bearings.',
        )

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {created_count} historical tickets + 1 active alarm on {alarm_machine.machine_code}!"))
