import logging
from django.utils import timezone
from maintenance.models import CNCMachine, BreakdownTicket, MachineStateLog
from .focas_client import FanucFocasClient
from .decoder import FocasDecoder

logger = logging.getLogger(__name__)


class TelemetryCollector:
    """
    Ingests and processes CNC telemetry, detects state transitions,
    manages MachineStateLog histories, and triggers BreakdownTickets.
    """

    @classmethod
    def process_machine_telemetry(cls, machine: CNCMachine, decoded_data: dict):
        """
        Receives decoded FOCAS telemetry dictionary and applies business logic.
        Ensures ALARM status persists while ticket is unattended (OPEN_ALARM),
        and UNDER_MAINTENANCE persists while ticket is being attended/repaired.
        """
        raw = decoded_data.get('raw', {})
        raw_status = decoded_data.get('derived_status', 'OFFLINE')
        alarm_code = decoded_data.get('alarm_code')
        alarm_msg = decoded_data.get('alarm_msg')

        now = timezone.now()
        previous_status = machine.current_status

        # Update last polled time
        machine.last_polled_at = now

        # Check for active breakdown ticket
        active_ticket = BreakdownTicket.objects.filter(
            machine=machine,
            status__in=['OPEN_ALARM', 'ACKNOWLEDGED', 'UNDER_REPAIR']
        ).first()

        # Determine effective machine status based on ticket lifecycle:
        # 1. Unattended ticket (OPEN_ALARM) -> Keep ALARM (blinking red on Andon TV)
        # 2. Attended / In-repair ticket (ACKNOWLEDGED/UNDER_REPAIR) -> Keep UNDER_MAINTENANCE (orange/yellow)
        # 3. No active ticket -> Follow raw telemetry (RUNNING, IDLE, OFFLINE)
        if active_ticket:
            if active_ticket.status == 'OPEN_ALARM':
                new_status = 'ALARM' if raw_status not in ['ALARM', 'EMERGENCY_STOP'] else raw_status
            elif active_ticket.status in ['ACKNOWLEDGED', 'UNDER_REPAIR']:
                new_status = 'UNDER_MAINTENANCE'
        else:
            new_status = raw_status

        # Detect State Transition
        if previous_status != new_status:
            logger.info(f"Machine {machine.machine_code} status transition: {previous_status} -> {new_status}")

            # Close open state log
            last_log = MachineStateLog.objects.filter(machine=machine, end_time__isnull=True).order_by('-start_time').first()
            if last_log:
                last_log.end_time = now
                last_log.duration_seconds = max(0, int((now - last_log.start_time).total_seconds()))
                last_log.save()

            # Create new state log
            MachineStateLog.objects.create(
                machine=machine,
                state=new_status,
                start_time=now,
                aut=raw.get('aut'),
                run=raw.get('run'),
                motion=raw.get('motion'),
                emergency=raw.get('emergency'),
                alarm=raw.get('alarm'),
            )

            # Update machine status
            machine.current_status = new_status
            machine.last_status_change = now

        # Step 2: Trigger Alert on ALARM or EMERGENCY_STOP if no active ticket exists
        if raw_status in ['ALARM', 'EMERGENCY_STOP']:
            if not active_ticket:
                trigger = 'EMERGENCY' if raw_status == 'EMERGENCY_STOP' else 'ALARM'
                BreakdownTicket.objects.create(
                    machine=machine,
                    trigger_source=trigger,
                    status='OPEN_ALARM',
                    alarm_time=now,
                    focas_alarm_code=alarm_code or ("E-STOP ACTIVATED" if raw_status == 'EMERGENCY_STOP' else "FOCAS ALARM"),
                    focas_alarm_msg=alarm_msg or ("Machine in Emergency Stop" if raw_status == 'EMERGENCY_STOP' else "CNC controller alarm bit set"),
                )
                logger.info(f"Triggered breakdown ticket for machine {machine.machine_code} at {now}")
                machine.current_status = raw_status
                machine.last_status_change = now

        # Step 3.g: Production Resumption - Next Run Time after Resolution
        elif raw_status == 'RUNNING' and not active_ticket:
            resolved_ticket = BreakdownTicket.objects.filter(
                machine=machine,
                status='RESOLVED'
            ).order_by('-resolve_time').first()

            if resolved_ticket:
                resolved_ticket.next_run_time = now
                resolved_ticket.status = 'CLOSED_RUNNING'
                resolved_ticket.save()
                logger.info(f"Production resumed for ticket {resolved_ticket.ticket_number} (t_run: {now})")

        machine.save()
        return machine

    @classmethod
    def poll_focas_machine(cls, machine: CNCMachine, client=None):
        """
        Polls a real machine via FOCAS client. Falls back cleanly if unreachable.
        """
        now = timezone.now()
        machine.last_polled_at = now

        if client is None:
            try:
                client = FanucFocasClient(
                    ip=machine.ip_address,
                    port=machine.port,
                    timeout=machine.timeout
                )
            except Exception as e:
                logger.error(f"Cannot initialize FOCAS client for {machine.machine_code}: {e}")
                if machine.current_status != 'OFFLINE':
                    machine.current_status = 'OFFLINE'
                    machine.last_status_change = now
                machine.save()
                return False, str(e)

        success, result = client.read_status()
        if success:
            decoded = FocasDecoder.decode(result)
            cls.process_machine_telemetry(machine, decoded)
            return True, decoded
        else:
            logger.warning(f"FOCAS read failed for {machine.machine_code}: {result}")
            if machine.current_status != 'OFFLINE':
                machine.current_status = 'OFFLINE'
                machine.last_status_change = now
            machine.save()
            return False, result
