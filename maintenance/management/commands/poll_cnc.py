import time
from django.core.management.base import BaseCommand
from maintenance.models import CNCMachine
from maintenance.focas.collector import TelemetryCollector
from maintenance.focas.focas_client import FanucFocasClient
from maintenance.focas.simulator import CNCSimulator


class Command(BaseCommand):
    help = "Poll CNC machines via FANUC FOCAS or run in simulation mode."

    def add_arguments(self, parser):
        parser.add_argument('--interval', type=int, default=5, help="Polling interval in seconds")
        parser.add_argument('--simulate', action='store_true', help="Run in simulation mode")
        parser.add_argument('--machine', type=str, default=None, help="Specific machine code to poll")

    def handle(self, *args, **options):
        interval = options['interval']
        simulate = options['simulate']
        machine_code = options['machine']

        self.stdout.write(self.style.SUCCESS("=" * 65))
        self.stdout.write(self.style.SUCCESS("CNC Telemetry Collector Started"))
        self.stdout.write(self.style.SUCCESS(f"Mode: {'SIMULATION' if simulate else 'LIVE FANUC FOCAS'}"))
        self.stdout.write(self.style.SUCCESS(f"Polling Interval: {interval} seconds"))
        self.stdout.write(self.style.SUCCESS("Press Ctrl+C to terminate"))
        self.stdout.write(self.style.SUCCESS("=" * 65))

        simulators = {}

        try:
            while True:
                query = CNCMachine.objects.filter(is_active=True)
                if machine_code:
                    query = query.filter(machine_code=machine_code)

                machines = list(query)
                if not machines:
                    self.stdout.write(self.style.WARNING("No active CNC machines found."))
                    time.sleep(interval)
                    continue

                for m in machines:
                    if simulate:
                        if m.machine_code not in simulators:
                            simulators[m.machine_code] = CNCSimulator(m.machine_code, m.current_status if m.current_status in CNCSimulator.PRESETS else 'RUNNING')
                        sim = simulators[m.machine_code]
                        data = sim.get_telemetry()
                        TelemetryCollector.process_machine_telemetry(m, data)
                        self.stdout.write(f"[{m.machine_code}] Simulated State: {data['derived_status']} ({data['status_text']})")
                    else:
                        success, res = TelemetryCollector.poll_focas_machine(m)
                        if success:
                            self.stdout.write(self.style.SUCCESS(f"[{m.machine_code}] FOCAS Read OK: {res['derived_status']}"))
                        else:
                            self.stdout.write(self.style.ERROR(f"[{m.machine_code}] FOCAS Read Failed: {res}"))

                time.sleep(interval)

        except KeyboardInterrupt:
            self.stdout.write(self.style.NOTICE("\nStopping telemetry polling collector..."))
