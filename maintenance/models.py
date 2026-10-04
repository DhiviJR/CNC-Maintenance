import io
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.files.base import ContentFile
import qrcode


class ProductionLine(models.Model):
    """Master table for Production / Shop Floor Lines."""
    line_code = models.CharField(max_length=50, unique=True, verbose_name="Line Code", help_text="Unique Line Code (e.g. LINE-01)")
    name = models.CharField(max_length=100, verbose_name="Line Name", help_text="Descriptive Line Name (e.g. Crankshaft Machining Line)")
    location = models.CharField(max_length=100, blank=True, default="Shop Floor Bay 1")
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Production Line"
        verbose_name_plural = "Production Lines"
        ordering = ['line_code']

    def __str__(self):
        return f"{self.line_code} - {self.name}" if self.name else self.line_code


class CNCMachine(models.Model):
    SERVICE_FREQUENCY_CHOICES = [
        (month, f"{month} month" if month == 1 else f"{month} months")
        for month in range(1, 13)
    ]

    STATUS_CHOICES = [
        ('RUNNING', 'Running'),
        ('IDLE', 'Idle'),
        ('ALARM', 'Alarm'),
        ('EMERGENCY_STOP', 'Emergency Stop'),
        ('UNDER_MAINTENANCE', 'Under Maintenance'),
        ('OFFLINE', 'Offline'),
    ]

    production_line = models.ForeignKey(
        ProductionLine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='machines',
        verbose_name="Line",
        help_text="Select Production Line from Master Table"
    )
    line_name = models.CharField(max_length=100, default="", verbose_name="Line Name")
    service_frequency = models.PositiveSmallIntegerField(
        choices=SERVICE_FREQUENCY_CHOICES,
        default=1,
        verbose_name="Service Frequency (Months)",
    )
    last_service_date = models.DateField(blank=True, null=True, verbose_name="Last Service Date")
    machine_code = models.CharField(max_length=50, primary_key=True, help_text="Unique Machine Identifier (e.g. CNC-01)")
    name = models.CharField(max_length=100, help_text="Machine name (e.g. Fanuc Robodrill Alpha)")
    model_number = models.CharField(max_length=100, blank=True, null=True)
    controller_type = models.CharField(max_length=50, default="FANUC 0i-MF / 31i")
    purchase_date = models.DateField(blank=True, null=True, verbose_name="Purchase Date")
    ip_address = models.GenericIPAddressField(default="192.168.1.101")
    port = models.PositiveIntegerField(default=8193)
    timeout = models.PositiveIntegerField(default=10, help_text="Timeout in seconds for FOCAS connection")
    location = models.CharField(max_length=100, blank=True, default="Shop Floor Bay 1")
    current_status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='OFFLINE')
    last_status_change = models.DateTimeField(default=timezone.now)
    last_polled_at = models.DateTimeField(null=True, blank=True)
    qr_code_image = models.ImageField(upload_to='machine_qr_codes/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "CNC Machine"
        verbose_name_plural = "CNC Machines"
        ordering = ['machine_code']

    def __str__(self):
        return f"{self.machine_code} - {self.name} [{self.get_current_status_display()}]"

    def generate_qr_code(self):
        """Generates a QR code image encoding the machine scan payload."""
        payload = f"CNC_MACHINE:{self.machine_code}"
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        filename = f"qr_{self.machine_code}.png"
        self.qr_code_image.save(filename, ContentFile(buffer.getvalue()), save=False)

    def save(self, *args, **kwargs):
        if self.production_line:
            self.line_name = self.production_line.name
        if not self.qr_code_image:
            self.generate_qr_code()
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and self.production_line:
            kwargs['update_fields'] = set(update_fields) | {'line_name'}
        super().save(*args, **kwargs)


class FailureCategory(models.Model):
    CATEGORY_CHOICES = [
        ('MAN', 'Man (Personnel / Human Factor)'),
        ('MACHINE', 'Machine (Mechanical / Electrical Equipment)'),
        ('MATERIAL', 'Material (Raw Stock / Workpiece Defect)'),
        ('METHOD', 'Method (Program / Process / Feeds & Speeds)'),
    ]

    code = models.CharField(max_length=20, unique=True, choices=CATEGORY_CHOICES)
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "4M Failure Category"
        verbose_name_plural = "4M Failure Categories"
        ordering = ['code']

    def __str__(self):
        return f"{self.get_code_display()}"


class FailureSubCategory(models.Model):
    category = models.ForeignKey(FailureCategory, on_delete=models.CASCADE, related_name='sub_categories')
    sub_category_code = models.CharField(max_length=30, unique=True, help_text="e.g. MCH-SPN-01")
    name = models.CharField(max_length=150, help_text="e.g. Spindle Bearing Overheat")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "4M Failure Sub-Category"
        verbose_name_plural = "4M Failure Sub-Categories"
        ordering = ['category', 'sub_category_code']

    def __str__(self):
        return f"[{self.category.code}] {self.sub_category_code} - {self.name}"


class SparePart(models.Model):
    PART_CATEGORIES = [
        ('MECHANICAL', 'Mechanical (Bearings, Gears, Belts)'),
        ('ELECTRICAL', 'Electrical (Servos, Sensors, Contactors)'),
        ('PNEUMATIC', 'Pneumatic (Valves, Cylinders, Regulators)'),
        ('HYDRAULIC', 'Hydraulic (Seals, Pumps, Filters)'),
        ('TOOLING', 'Tooling / Inserts (Holders, Carbide Inserts)'),
        ('LUBRICANT', 'Lubricants & Oils (Spindle Oil, Waylube)'),
        ('CONSUMABLE', 'Consumables & Wipers'),
    ]

    UOM_CHOICES = [
        ('PCS', 'Pieces (pcs)'),
        ('SETS', 'Sets'),
        ('LTRS', 'Litres (L)'),
        ('METERS', 'Meters (m)'),
        ('PACKS', 'Packs'),
    ]

    part_code = models.CharField(max_length=50, primary_key=True, help_text="Unique Part / Tool Code (e.g. BRG-7014C)")
    part_name = models.CharField(max_length=150)
    category = models.CharField(max_length=50, choices=PART_CATEGORIES, default='MECHANICAL')
    specification = models.CharField(max_length=200, blank=True, help_text="Technical dimensions or spec")
    unit_of_measure = models.CharField(max_length=20, choices=UOM_CHOICES, default='PCS')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), help_text="Unit price")
    stock_quantity = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=5)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Spare Part / Tool Catalog"
        verbose_name_plural = "Spare Parts & Tools Master"
        ordering = ['part_code']

    def __str__(self):
        return f"{self.part_code} - {self.part_name} (₹{self.unit_price} / {self.unit_of_measure})"


class BreakdownTicket(models.Model):
    TRIGGER_CHOICES = [
        ('ALARM', 'CNC Alarm Triggered'),
        ('EMERGENCY', 'Emergency Stop Button Pressed'),
        ('IDLE_TIMEOUT', 'Prolonged Unproductive Idle'),
        ('MANUAL', 'Manual Technician / Operator Call'),
    ]

    STATUS_CHOICES = [
        ('OPEN_ALARM', 'Open / Alarm Triggered'),
        ('ACKNOWLEDGED', 'Acknowledged / QR Scanned On-Site'),
        ('UNDER_REPAIR', 'Under Repair / Diagnosed'),
        ('RESOLVED', 'Resolved / Repair Complete'),
        ('CLOSED_RUNNING', 'Closed / Machine Resumed Production'),
    ]

    SHIFT_CHOICES = [
        ('Shift A', 'Shift A (06:00 - 14:00)'),
        ('Shift B', 'Shift B (14:00 - 22:00)'),
        ('Shift C', 'Shift C (22:00 - 06:00)'),
    ]

    ticket_number = models.CharField(max_length=30, unique=True, editable=False)
    machine = models.ForeignKey(CNCMachine, on_delete=models.CASCADE, related_name='tickets')
    trigger_source = models.CharField(max_length=30, choices=TRIGGER_CHOICES, default='ALARM')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='OPEN_ALARM')
    shift = models.CharField(max_length=20, choices=SHIFT_CHOICES, default='Shift A')

    # FOCAS captured values
    focas_alarm_code = models.CharField(max_length=50, blank=True, null=True)
    focas_alarm_msg = models.TextField(blank=True, null=True)

    # Core Timestamps (Steps 2, 3.b, 3.c, 3.f, 3.g in notes)
    alarm_time = models.DateTimeField(default=timezone.now, help_text="Time of alarm / breakdown trigger (t_alarm)")
    scan_time = models.DateTimeField(null=True, blank=True, help_text="Time technician scanned QR code at CNC (t_scan)")
    diagnosed_time = models.DateTimeField(null=True, blank=True, help_text="Time 4M failure category was chosen")
    resolve_time = models.DateTimeField(null=True, blank=True, help_text="Time repair & parts replacement completed (t_resolve)")
    next_run_time = models.DateTimeField(null=True, blank=True, help_text="Time machine resumed cutting / running (t_run)")

    # Derived Durations in Seconds for high-speed indexing & KPI calculation
    response_time_seconds = models.IntegerField(null=True, blank=True, help_text="t_scan - t_alarm (Mean Time to Acknowledge)")
    repair_time_seconds = models.IntegerField(null=True, blank=True, help_text="t_resolve - t_scan (Active repair duration)")
    total_downtime_seconds = models.IntegerField(null=True, blank=True, help_text="t_resolve - t_alarm (Total MTTR)")
    ramp_up_delay_seconds = models.IntegerField(null=True, blank=True, help_text="t_run - t_resolve (Delay until production resume)")

    # Personnel and Diagnosis
    technician = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='maintenance_tickets')
    failure_sub_category = models.ForeignKey(FailureSubCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')
    symptom_notes = models.TextField(blank=True, help_text="Observed machine behavior or alarms")
    resolution_notes = models.TextField(blank=True, help_text="Detailed actions taken to fix the issue")

    # Financial Costing
    total_spares_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Breakdown & Maintenance Ticket"
        verbose_name_plural = "Breakdown & Maintenance Tickets"
        ordering = ['-alarm_time']

    def __str__(self):
        return f"{self.ticket_number} - {self.machine_id} [{self.get_status_display()}]"

    def save(self, *args, **kwargs):
        if not self.ticket_number:
            prefix = timezone.now().strftime("TKT-%Y%m%d-")
            last_ticket = BreakdownTicket.objects.filter(ticket_number__startswith=prefix).order_by('-ticket_number').first()
            if last_ticket:
                try:
                    seq = int(last_ticket.ticket_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            else:
                seq = 1
            self.ticket_number = f"{prefix}{seq:04d}"
        
        self.recalculate_durations()
        super().save(*args, **kwargs)

    def recalculate_durations(self):
        """Computes response time, repair time, total downtime, and restart delay."""
        if self.alarm_time and self.scan_time:
            self.response_time_seconds = max(0, int((self.scan_time - self.alarm_time).total_seconds()))

        if self.scan_time and self.resolve_time:
            self.repair_time_seconds = max(0, int((self.resolve_time - self.scan_time).total_seconds()))

        if self.alarm_time and self.resolve_time:
            self.total_downtime_seconds = max(0, int((self.resolve_time - self.alarm_time).total_seconds()))

        if self.resolve_time and self.next_run_time:
            self.ramp_up_delay_seconds = max(0, int((self.next_run_time - self.resolve_time).total_seconds()))

    def update_spares_total(self):
        """Calculates total cost of all parts consumed for this ticket."""
        total = self.spares_used.aggregate(total=models.Sum('line_total'))['total'] or Decimal('0.00')
        self.total_spares_cost = total
        self.save(update_fields=['total_spares_cost'])


class TicketSpareUsage(models.Model):
    ticket = models.ForeignKey(BreakdownTicket, on_delete=models.CASCADE, related_name='spares_used')
    spare_part = models.ForeignKey(SparePart, on_delete=models.PROTECT, related_name='usages')
    quantity = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('1.00'))
    unit_price_at_use = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    notes = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Replaced Spare / Tool"
        verbose_name_plural = "Replaced Spares & Tools"

    def save(self, *args, **kwargs):
        if not self.unit_price_at_use and self.spare_part:
            self.unit_price_at_use = self.spare_part.unit_price
        self.line_total = self.unit_price_at_use * self.quantity
        super().save(*args, **kwargs)
        self.ticket.update_spares_total()

    def delete(self, *args, **kwargs):
        ticket = self.ticket
        super().delete(*args, **kwargs)
        ticket.update_spares_total()

    def __str__(self):
        return f"{self.spare_part.part_code} x {self.quantity} for {self.ticket.ticket_number}"


class MachineStateLog(models.Model):
    machine = models.ForeignKey(CNCMachine, on_delete=models.CASCADE, related_name='state_logs')
    state = models.CharField(max_length=30, choices=CNCMachine.STATUS_CHOICES)
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(default=0)
    aut = models.IntegerField(null=True, blank=True, help_text="FANUC AUT mode")
    run = models.IntegerField(null=True, blank=True, help_text="FANUC RUN status")
    motion = models.IntegerField(null=True, blank=True, help_text="FANUC Motion status")
    emergency = models.IntegerField(null=True, blank=True, help_text="FANUC Emergency flag")
    alarm = models.IntegerField(null=True, blank=True, help_text="FANUC Alarm flag")

    class Meta:
        verbose_name = "Machine State Telemetry Log"
        verbose_name_plural = "Machine State Telemetry Logs"
        ordering = ['-start_time']

    def __str__(self):
        return f"{self.machine.machine_code} - {self.state} at {self.start_time}"

