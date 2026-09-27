from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from maintenance.models import (
    CNCMachine,
    FailureCategory,
    FailureSubCategory,
    SparePart,
    BreakdownTicket,
    TicketSpareUsage
)
from maintenance.focas.decoder import FocasDecoder
from maintenance.focas.simulator import CNCSimulator
from maintenance.focas.collector import TelemetryCollector


class FocasDecoderTest(TestCase):
    def test_running_decode(self):
        sample = {'aut': 1, 'run': 2, 'motion': 1, 'mstb': 0, 'emergency': 0, 'alarm': 0, 'edit': 0}
        res = FocasDecoder.decode(sample)
        self.assertEqual(res['derived_status'], 'RUNNING')
        self.assertTrue(res['is_running'])
        self.assertFalse(res['is_alarm'])

    def test_alarm_decode(self):
        sample = {'aut': 1, 'run': 0, 'motion': 0, 'mstb': 0, 'emergency': 0, 'alarm': 1, 'edit': 0}
        res = FocasDecoder.decode(sample)
        self.assertEqual(res['derived_status'], 'ALARM')
        self.assertTrue(res['is_alarm'])

    def test_emergency_decode(self):
        sample = {'aut': 1, 'run': 0, 'motion': 0, 'mstb': 0, 'emergency': 1, 'alarm': 0, 'edit': 0}
        res = FocasDecoder.decode(sample)
        self.assertEqual(res['derived_status'], 'EMERGENCY_STOP')
        self.assertTrue(res['is_emergency'])

    def test_idle_decode(self):
        sample = {'aut': 1, 'run': 0, 'motion': 0, 'mstb': 0, 'emergency': 0, 'alarm': 0, 'edit': 0}
        res = FocasDecoder.decode(sample)
        self.assertEqual(res['derived_status'], 'IDLE')
        self.assertTrue(res['is_idle'])


class MaintenanceWorkflowTest(TestCase):
    def setUp(self):
        self.machine = CNCMachine.objects.create(
            machine_code="TEST-CNC-01",
            name="Test CNC Machine",
            current_status="RUNNING"
        )
        self.category = FailureCategory.objects.create(
            code="MACHINE",
            name="Machine Equipment"
        )
        self.sub_category = FailureSubCategory.objects.create(
            category=self.category,
            sub_category_code="MCH-001",
            name="Spindle Fault"
        )
        self.part = SparePart.objects.create(
            part_code="PART-001",
            part_name="Test Bearing",
            unit_price=Decimal("1500.00"),
            stock_quantity=10
        )

    def test_telemetry_trigger_ticket(self):
        sim = CNCSimulator("TEST-CNC-01", initial_state="ALARM")
        data = sim.get_telemetry()
        TelemetryCollector.process_machine_telemetry(self.machine, data)

        self.machine.refresh_from_db()
        self.assertEqual(self.machine.current_status, "ALARM")

        # Ticket should be auto-created
        ticket = BreakdownTicket.objects.filter(machine=self.machine).first()
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.status, "OPEN_ALARM")
        self.assertIsNotNone(ticket.alarm_time)

    def test_ticket_lifecycle_and_durations(self):
        t0 = timezone.now() - timedelta(minutes=45)
        ticket = BreakdownTicket.objects.create(
            machine=self.machine,
            trigger_source="ALARM",
            alarm_time=t0
        )
        self.assertTrue(ticket.ticket_number.startswith("TKT-"))

        # Step 3.b: Technician scans QR
        t_scan = t0 + timedelta(minutes=10)
        ticket.scan_time = t_scan
        ticket.status = "ACKNOWLEDGED"
        ticket.save()
        self.assertEqual(ticket.response_time_seconds, 600)  # 10 minutes

        # Step 3.c & 3.e: Diagnosis & Spares
        ticket.failure_sub_category = self.sub_category
        TicketSpareUsage.objects.create(
            ticket=ticket,
            spare_part=self.part,
            quantity=Decimal("2.0"),
            unit_price_at_use=Decimal("1500.00")
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.total_spares_cost, Decimal("3000.00"))

        # Step 3.f: Resolution complete
        t_resolve = t_scan + timedelta(minutes=20)
        ticket.resolve_time = t_resolve
        ticket.status = "RESOLVED"
        ticket.save()
        self.assertEqual(ticket.repair_time_seconds, 1200)   # 20 minutes
        self.assertEqual(ticket.total_downtime_seconds, 1800) # 30 minutes total

        # Step 3.g: Production resumed
        t_run = t_resolve + timedelta(minutes=5)
        ticket.next_run_time = t_run
        ticket.status = "CLOSED_RUNNING"
        ticket.save()
        self.assertEqual(ticket.ramp_up_delay_seconds, 300)   # 5 minutes

