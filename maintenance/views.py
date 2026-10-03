import json
from decimal import Decimal
from datetime import timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Count, Sum, Avg, Q, F, Min, Max
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import (
    CNCMachine,
    FailureCategory,
    FailureSubCategory,
    SparePart,
    BreakdownTicket,
    TicketSpareUsage,
    MachineStateLog
)
from .focas.simulator import CNCSimulator
from .focas.collector import TelemetryCollector

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


# ==============================================================================
# 1. EXECUTIVE DASHBOARD & REAL-TIME ANALYTICS (Section 4 of Notes)
# ==============================================================================

def dashboard_view(request):
    """
    Renders the central executive analytics dashboard answering all requirements:
    4.a Running vs Idle CNCs
    4.b Maintenance Speed (MTTA & MTTR)
    4.c Breakdown Frequency & MTBF
    4.d 4M Failure Root-Cause Pareto & Cross-Machine comparison
    4.e Maintenance Cost per machine, per month, per year
    """
    machines = CNCMachine.objects.filter(is_active=True)
    total_machines = machines.count()

    # 4.a Fleet Status
    running_count = machines.filter(current_status='RUNNING').count()
    idle_count = machines.filter(current_status='IDLE').count()
    alarm_count = machines.filter(current_status__in=['ALARM', 'EMERGENCY_STOP']).count()
    maintenance_count = machines.filter(current_status='UNDER_MAINTENANCE').count()
    offline_count = machines.filter(current_status='OFFLINE').count()

    utilization_pct = round((running_count / total_machines * 100), 1) if total_machines > 0 else 0

    # Date range filter (default: last 30 days)
    days = int(request.GET.get('days', 30))
    since_date = timezone.now() - timedelta(days=days)

    tickets = BreakdownTicket.objects.filter(alarm_time__gte=since_date)
    selected_machine = request.GET.get('machine', '')
    if selected_machine:
        tickets = tickets.filter(machine__machine_code=selected_machine)

    selected_shift = request.GET.get('shift', '')
    if selected_shift:
        tickets = tickets.filter(shift=selected_shift)

    # 4.b Maintenance Speed (MTTA and MTTR)
    mtta_data = tickets.filter(response_time_seconds__isnull=False).aggregate(
        avg_resp=Avg('response_time_seconds'),
        min_resp=Min('response_time_seconds'),
        max_resp=Max('response_time_seconds')
    )
    avg_mtta_sec = int(mtta_data['avg_resp'] or 0)
    avg_mtta_min = round(avg_mtta_sec / 60, 1)

    mttr_data = tickets.filter(total_downtime_seconds__isnull=False).aggregate(
        avg_downtime=Avg('total_downtime_seconds'),
        min_downtime=Min('total_downtime_seconds'),
        max_downtime=Max('total_downtime_seconds')
    )
    avg_mttr_sec = int(mttr_data['avg_downtime'] or 0)
    avg_mttr_min = round(avg_mttr_sec / 60, 1)

    # 4.c Breakdown Frequency & Reliability (MTBF)
    breakdown_by_machine = (
        tickets.values('machine__machine_code', 'machine__name')
        .annotate(fail_count=Count('id'), total_downtime=Sum('total_downtime_seconds'))
        .order_by('-fail_count')
    )

    # Calculate MTBF for each machine: (Operating Hours) / (Failures)
    total_period_hours = days * 24
    machine_reliability = []
    for item in breakdown_by_machine:
        cnt = item['fail_count']
        downtime_hrs = (item['total_downtime'] or 0) / 3600
        operating_hrs = max(0, total_period_hours - downtime_hrs)
        mtbf_hrs = round(operating_hrs / cnt, 1) if cnt > 0 else total_period_hours
        availability_pct = round((operating_hrs / total_period_hours) * 100, 1) if total_period_hours > 0 else 100
        machine_reliability.append({
            'code': item['machine__machine_code'],
            'name': item['machine__name'],
            'count': cnt,
            'mtbf': mtbf_hrs,
            'availability': availability_pct,
            'downtime_hrs': round(downtime_hrs, 1)
        })

    # 4.d 4M Root-Cause Analysis (Pareto)
    cause_data = (
        tickets.filter(failure_sub_category__isnull=False)
        .values('failure_sub_category__category__name', 'failure_sub_category__name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    category_summary = (
        tickets.filter(failure_sub_category__isnull=False)
        .values('failure_sub_category__category__code', 'failure_sub_category__category__name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # 4.e Maintenance Cost Tracking
    cost_data = tickets.aggregate(
        total_cost=Sum('total_spares_cost'),
        avg_cost=Avg('total_spares_cost')
    )
    total_maintenance_cost = cost_data['total_cost'] or Decimal('0.00')

    cost_by_machine = (
        tickets.values('machine__machine_code')
        .annotate(cost=Sum('total_spares_cost'))
        .order_by('-cost')
    )

    # Active Alarms right now
    active_alarms = BreakdownTicket.objects.filter(status__in=['OPEN_ALARM', 'ACKNOWLEDGED', 'UNDER_REPAIR']).order_by('-alarm_time')

    context = {
        'total_machines': total_machines,
        'running_count': running_count,
        'idle_count': idle_count,
        'alarm_count': alarm_count,
        'maintenance_count': maintenance_count,
        'offline_count': offline_count,
        'utilization_pct': utilization_pct,
        'days': days,
        'selected_machine': selected_machine,
        'selected_shift': selected_shift,
        'machines': machines,
        'total_tickets': tickets.count(),
        'avg_mtta_min': avg_mtta_min,
        'avg_mttr_min': avg_mttr_min,
        'machine_reliability': machine_reliability,
        'category_summary': list(category_summary),
        'cause_data': list(cause_data[:8]),
        'total_maintenance_cost': total_maintenance_cost,
        'cost_by_machine': list(cost_by_machine),
        'active_alarms': active_alarms,
    }
    return render(request, 'maintenance/dashboard.html', context)


def api_dashboard_data(request):
    """JSON API for real-time dashboard refresh & charts."""
    machines = CNCMachine.objects.filter(is_active=True).order_by('machine_code')
    machine_list = []
    for m in machines:
        machine_list.append({
            'machine_code': m.machine_code,
            'name': m.name,
            'location': m.location,
            'ip_address': m.ip_address,
            'current_status': m.current_status,
            'status_display': m.get_current_status_display(),
            'last_status_change': m.last_status_change.strftime("%Y-%m-%d %H:%M:%S") if m.last_status_change else ""
        })

    status_counts = {
        'RUNNING': machines.filter(current_status='RUNNING').count(),
        'IDLE': machines.filter(current_status='IDLE').count(),
        'ALARM': machines.filter(current_status='ALARM').count(),
        'EMERGENCY_STOP': machines.filter(current_status='EMERGENCY_STOP').count(),
        'UNDER_MAINTENANCE': machines.filter(current_status='UNDER_MAINTENANCE').count(),
        'OFFLINE': machines.filter(current_status='OFFLINE').count(),
    }

    active_tickets = list(BreakdownTicket.objects.filter(
        status__in=['OPEN_ALARM', 'ACKNOWLEDGED', 'UNDER_REPAIR']
    ).values(
        'ticket_number', 'machine__machine_code', 'status', 'trigger_source',
        'focas_alarm_code', 'alarm_time'
    )[:10])

    for t in active_tickets:
        t['alarm_time'] = t['alarm_time'].strftime("%Y-%m-%d %H:%M:%S")

    return JsonResponse({
        'status_counts': status_counts,
        'machines': machine_list,
        'active_tickets': active_tickets,
        'server_time': timezone.now().strftime("%Y-%m-%d %H:%M:%S")
    })


# ==============================================================================
# 2. CNC MACHINE FLEET & QR CODE ENGINE (Step 3.a)
# ==============================================================================

def machine_list_view(request):
    """Overview of all machines in the fleet with live status badges."""
    machines = CNCMachine.objects.filter(is_active=True).order_by('machine_code')
    return render(request, 'maintenance/machine_list.html', {'machines': machines})


def machine_detail_view(request, machine_code):
    """Detailed view for a single machine with history and QR code."""
    machine = get_object_or_404(CNCMachine, machine_code=machine_code)
    recent_tickets = machine.tickets.order_by('-alarm_time')[:10]
    recent_logs = machine.state_logs.order_by('-start_time')[:15]
    return render(request, 'maintenance/machine_detail.html', {
        'machine': machine,
        'recent_tickets': recent_tickets,
        'recent_logs': recent_logs
    })


def qr_print_view(request, machine_code):
    """Printable sticker sheet with high-resolution QR code for machine mounting."""
    machine = get_object_or_404(CNCMachine, machine_code=machine_code)
    if not machine.qr_code_image:
        machine.generate_qr_code()
        machine.save()
    return render(request, 'maintenance/qr_print.html', {'machine': machine})


# ==============================================================================
# 3. TECHNICIAN MOBILE QR SCANNER & ATTENDANCE LOGGING (Steps 3.a & 3.b)
# ==============================================================================

def scanner_view(request):
    """
    Mobile & device camera QR scanner page.
    Supports general scanning or targeted verification for a specific machine / ticket.
    """
    machines = CNCMachine.objects.filter(is_active=True).order_by('machine_code')
    target_machine = request.GET.get('target_machine', '')
    ticket_id = request.GET.get('ticket_id', '')

    target_obj = None
    target_ticket = None

    if target_machine:
        target_obj = CNCMachine.objects.filter(machine_code=target_machine).first()
    if ticket_id:
        target_ticket = BreakdownTicket.objects.filter(id=ticket_id).first()

    return render(request, 'maintenance/scanner.html', {
        'machines': machines,
        'target_machine': target_machine,
        'target_obj': target_obj,
        'target_ticket': target_ticket,
        'ticket_id': ticket_id,
    })


def scan_machine_action(request, machine_code):
    """
    Step 3.a & 3.b: Triggered when QR code on CNC machine is verified via camera scan.
    Logs scan time (t_scan), records attendance, and transitions ticket to ACKNOWLEDGED.
    """
    machine = get_object_or_404(CNCMachine, machine_code=machine_code)
    now = timezone.now()
    ticket_id = request.GET.get('ticket_id')

    # If ticket_id was specified, validate that ticket belongs to this machine
    if ticket_id:
        target_ticket = BreakdownTicket.objects.filter(id=ticket_id).first()
        if target_ticket and target_ticket.machine.machine_code != machine_code:
            messages.error(
                request,
                f"❌ Invalid QR Code Mismatch! Scanned QR for machine '{machine_code}', but ticket {target_ticket.ticket_number} is for machine '{target_ticket.machine.machine_code}'."
            )
            return redirect(f"/scanner/?target_machine={target_ticket.machine.machine_code}&ticket_id={target_ticket.id}")

    # Look for active breakdown ticket (either specified or open)
    open_ticket = None
    if ticket_id:
        open_ticket = BreakdownTicket.objects.filter(id=ticket_id, machine=machine, status='OPEN_ALARM').first()
    
    if not open_ticket:
        open_ticket = BreakdownTicket.objects.filter(
            machine=machine,
            status='OPEN_ALARM'
        ).order_by('-alarm_time').first()

    if open_ticket:
        # Step 3.b: Log time of scan (t_scan)
        open_ticket.scan_time = now
        open_ticket.status = 'ACKNOWLEDGED'
        if request.user.is_authenticated:
            open_ticket.technician = request.user
        else:
            default_tech = User.objects.filter(username='tech_john').first() or User.objects.first()
            open_ticket.technician = default_tech

        open_ticket.recalculate_durations()
        open_ticket.save()

        # Update machine status to indicate technician is attending
        machine.current_status = 'UNDER_MAINTENANCE'
        machine.save(update_fields=['current_status'])

        messages.success(
            request,
            f"Physical QR Verified! Attendance logged for {machine.machine_code}. Response Time: {open_ticket.response_time_seconds // 60}m {open_ticket.response_time_seconds % 60}s"
        )
        return redirect('ticket_detail', ticket_id=open_ticket.id)

    # Check if there is a ticket already in progress
    in_progress = BreakdownTicket.objects.filter(
        machine=machine,
        status__in=['ACKNOWLEDGED', 'UNDER_REPAIR']
    ).first()

    if in_progress:
        messages.info(request, f"Ticket {in_progress.ticket_number} is already in progress for {machine.machine_code}.")
        return redirect('ticket_detail', ticket_id=in_progress.id)

    # If no open alarm, offer to create manual maintenance request
    messages.warning(request, f"No active alarm on {machine.machine_code}. You can create a maintenance request if needed.")
    return redirect('create_ticket_for_machine', machine_code=machine.machine_code)


# ==============================================================================
# 4. MAINTENANCE DIAGNOSIS & RESOLUTION WORKFLOW (Steps 3.c – 3.g)
# ==============================================================================

def ticket_detail_view(request, ticket_id):
    """
    Primary technician resolution interface:
    - Step 3.c & 3.d: 4M Failure Category & Sub-Category selection
    - Step 3.e: Spares / Tools replacement logging & automatic cost computation
    - Step 3.f: Complete Resolution (t_resolve)
    - Step 3.g: Production Resumption (t_run)
    """
    ticket = get_object_or_404(BreakdownTicket, id=ticket_id)
    categories = FailureCategory.objects.filter(is_active=True).prefetch_related('sub_categories')
    spare_parts = SparePart.objects.filter(is_active=True).order_by('part_name')

    if request.method == 'POST':
        action = request.POST.get('action')

        # ----------------------------------------------------------------------
        # Step 3.c & 3.d: Submit 4M Diagnosis
        # ----------------------------------------------------------------------
        if action == 'submit_diagnosis':
            sub_cat_id = request.POST.get('sub_category_id')
            symptom_notes = request.POST.get('symptom_notes', '')

            if sub_cat_id:
                ticket.failure_sub_category = get_object_or_404(FailureSubCategory, id=sub_cat_id)
            ticket.symptom_notes = symptom_notes
            ticket.diagnosed_time = timezone.now()
            ticket.status = 'UNDER_REPAIR'
            ticket.save()
            messages.success(request, "4M Failure Diagnosis recorded successfully!")
            return redirect('ticket_detail', ticket_id=ticket.id)

        # ----------------------------------------------------------------------
        # Step 3.e: Add Replaced Spare Part / Tool
        # ----------------------------------------------------------------------
        elif action == 'add_spare':
            part_code = request.POST.get('part_code')
            qty_str = request.POST.get('quantity', '1')
            notes = request.POST.get('notes', '')

            try:
                qty = Decimal(qty_str)
                part = get_object_or_404(SparePart, part_code=part_code)
                TicketSpareUsage.objects.create(
                    ticket=ticket,
                    spare_part=part,
                    quantity=qty,
                    unit_price_at_use=part.unit_price,
                    notes=notes
                )
                messages.success(request, f"Added {qty}x {part.part_name} (₹{part.unit_price * qty}) to repair log.")
            except Exception as e:
                messages.error(request, f"Error adding spare part: {e}")
            return redirect('ticket_detail', ticket_id=ticket.id)

        # ----------------------------------------------------------------------
        # Remove Spare Part
        # ----------------------------------------------------------------------
        elif action == 'remove_spare':
            usage_id = request.POST.get('usage_id')
            usage = get_object_or_404(TicketSpareUsage, id=usage_id, ticket=ticket)
            usage.delete()
            messages.info(request, "Spare part removed from log.")
            return redirect('ticket_detail', ticket_id=ticket.id)

        # ----------------------------------------------------------------------
        # Step 3.f: Complete Repair & Resolution (t_resolve)
        # ----------------------------------------------------------------------
        elif action == 'complete_repair':
            res_notes = request.POST.get('resolution_notes', '')
            now = timezone.now()
            machine = ticket.machine

            # SAFETY CHECK: Poll live machine status via FOCAS if client available
            try:
                success, result = TelemetryCollector.poll_focas_machine(machine)
                if success:
                    machine.refresh_from_db()
            except Exception:
                pass

            # Block completion if machine is STILL in ALARM or EMERGENCY_STOP
            if machine.current_status in ['ALARM', 'EMERGENCY_STOP']:
                messages.error(
                    request,
                    f"⚠️ CANNOT COMPLETE REPAIR! Machine {machine.machine_code} is still reporting an active '{machine.get_current_status_display()}' state from the CNC controller. Please check the machine, clear the physical alarm on the control panel, and try again."
                )
                return redirect('ticket_detail', ticket_id=ticket.id)

            ticket.resolution_notes = res_notes
            ticket.resolve_time = now
            ticket.status = 'RESOLVED'
            ticket.recalculate_durations()
            ticket.save()

            # Machine status updated to IDLE / Waiting for operator cycle start
            machine.current_status = 'IDLE'
            machine.save(update_fields=['current_status'])

            messages.success(
                request,
                f"Repair Completed! Resolution time logged (MTTR: {ticket.total_downtime_seconds // 60}m). Machine is now IDLE ready for production."
            )
            return redirect('ticket_detail', ticket_id=ticket.id)

        # ----------------------------------------------------------------------
        # Step 3.g: Production Resumption (t_run)
        # ----------------------------------------------------------------------
        elif action == 'resume_production':
            now = timezone.now()
            ticket.next_run_time = now
            ticket.status = 'CLOSED_RUNNING'
            ticket.recalculate_durations()
            ticket.save()

            machine = ticket.machine
            machine.current_status = 'RUNNING'
            machine.save(update_fields=['current_status'])

            messages.success(request, f"Machine {machine.machine_code} resumed production! Ticket closed.")
            return redirect('ticket_detail', ticket_id=ticket.id)

    return render(request, 'maintenance/ticket_detail.html', {
        'ticket': ticket,
        'categories': categories,
        'spare_parts': spare_parts,
    })


def create_ticket_for_machine(request, machine_code):
    """Manually creates a breakdown ticket for a machine (Operator Call)."""
    machine = get_object_or_404(CNCMachine, machine_code=machine_code)
    if request.method == 'POST':
        trigger = request.POST.get('trigger_source', 'MANUAL')
        symptom = request.POST.get('symptom_notes', '')
        ticket = BreakdownTicket.objects.create(
            machine=machine,
            trigger_source=trigger,
            status='OPEN_ALARM',
            alarm_time=timezone.now(),
            symptom_notes=symptom,
        )
        machine.current_status = 'ALARM'
        machine.save(update_fields=['current_status'])
        messages.success(request, f"Maintenance ticket {ticket.ticket_number} created!")
        return redirect('ticket_detail', ticket_id=ticket.id)

    return render(request, 'maintenance/create_ticket.html', {'machine': machine})


def ticket_list_view(request):
    """Browse and filter all maintenance tickets."""
    tickets = BreakdownTicket.objects.select_related('machine', 'technician', 'failure_sub_category__category').order_by('-alarm_time')

    # Filters
    status = request.GET.get('status')
    if status:
        tickets = tickets.filter(status=status)

    machine_code = request.GET.get('machine')
    if machine_code:
        tickets = tickets.filter(machine__machine_code=machine_code)

    shift = request.GET.get('shift')
    if shift:
        tickets = tickets.filter(shift=shift)

    category = request.GET.get('category')
    if category:
        tickets = tickets.filter(failure_sub_category__category__code=category)

    machines = CNCMachine.objects.filter(is_active=True)
    return render(request, 'maintenance/ticket_list.html', {
        'tickets': tickets,
        'machines': machines,
        'selected_status': status,
        'selected_machine': machine_code,
        'selected_shift': shift,
        'selected_category': category,
    })


# ==============================================================================
# 5. INDUSTRIAL ADDITIONS: ANDON BOARD & INTERACTIVE SIMULATOR (Phase 5)
# ==============================================================================

def andon_board_view(request):
    """
    High-visibility Shop Floor Andon display for TV screens.
    Shows real-time machine status blocks, flashing active alarms, and elapsed times.
    """
    machines = CNCMachine.objects.filter(is_active=True).order_by('machine_code')
    active_alarms = BreakdownTicket.objects.filter(
        status__in=['OPEN_ALARM', 'ACKNOWLEDGED', 'UNDER_REPAIR']
    ).select_related('machine', 'technician').order_by('-alarm_time')
    return render(request, 'maintenance/andon.html', {
        'machines': machines,
        'active_alarms': active_alarms
    })


def simulator_view(request):
    """
    Interactive CNC Simulator Control Panel.
    Allows testing state transitions (Running, Idle, Alarm, E-Stop) for any machine.
    """
    machines = CNCMachine.objects.filter(is_active=True).order_by('machine_code')
    return render(request, 'maintenance/simulator.html', {'machines': machines})


@require_POST
def api_simulate_action(request):
    """API endpoint to inject telemetry into a machine from the web UI."""
    data = json.loads(request.body)
    machine_code = data.get('machine_code')
    target_state = data.get('state', 'RUNNING')
    alarm_code = data.get('alarm_code')
    alarm_msg = data.get('alarm_msg')

    machine = get_object_or_404(CNCMachine, machine_code=machine_code)
    sim = CNCSimulator(machine_code=machine_code, initial_state=target_state)
    if alarm_code or alarm_msg:
        sim.set_state(target_state, alarm_code=alarm_code, alarm_msg=alarm_msg)

    telemetry = sim.get_telemetry()
    TelemetryCollector.process_machine_telemetry(machine, telemetry)

    return JsonResponse({
        'success': True,
        'machine_code': machine_code,
        'new_status': machine.current_status,
        'message': f"Machine {machine_code} switched to {machine.current_status}"
    })


# ==============================================================================
# 6. EXPORT MODULES (Excel & PDF)
# ==============================================================================

def export_tickets_excel(request):
    """Generates a professional Excel workbook of maintenance logs."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CNC Maintenance Logs"

    headers = [
        "Ticket Number", "Machine", "Status", "Trigger", "Shift",
        "Alarm Time (t_alarm)", "Scan Time (t_scan)", "Resolve Time (t_resolve)", "Next Run Time (t_run)",
        "Response Time (min)", "Repair Time (min)", "Total Downtime (min)",
        "4M Category", "Sub-Category", "Spares Cost (INR)"
    ]

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    alignment = Alignment(horizontal="center", vertical="center")

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = alignment

    tickets = BreakdownTicket.objects.select_related('machine', 'failure_sub_category__category').order_by('-alarm_time')

    for row_idx, t in enumerate(tickets, 2):
        ws.cell(row=row_idx, column=1, value=t.ticket_number)
        ws.cell(row=row_idx, column=2, value=t.machine.machine_code)
        ws.cell(row=row_idx, column=3, value=t.get_status_display())
        ws.cell(row=row_idx, column=4, value=t.get_trigger_source_display())
        ws.cell(row=row_idx, column=5, value=t.shift)
        ws.cell(row=row_idx, column=6, value=t.alarm_time.strftime("%Y-%m-%d %H:%M") if t.alarm_time else "")
        ws.cell(row=row_idx, column=7, value=t.scan_time.strftime("%Y-%m-%d %H:%M") if t.scan_time else "")
        ws.cell(row=row_idx, column=8, value=t.resolve_time.strftime("%Y-%m-%d %H:%M") if t.resolve_time else "")
        ws.cell(row=row_idx, column=9, value=t.next_run_time.strftime("%Y-%m-%d %H:%M") if t.next_run_time else "")
        ws.cell(row=row_idx, column=10, value=round((t.response_time_seconds or 0) / 60, 1))
        ws.cell(row=row_idx, column=11, value=round((t.repair_time_seconds or 0) / 60, 1))
        ws.cell(row=row_idx, column=12, value=round((t.total_downtime_seconds or 0) / 60, 1))
        ws.cell(row=row_idx, column=13, value=t.failure_sub_category.category.name if t.failure_sub_category else "")
        ws.cell(row=row_idx, column=14, value=t.failure_sub_category.name if t.failure_sub_category else "")
        ws.cell(row=row_idx, column=15, value=float(t.total_spares_cost))

    # Auto-fit column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="cnc_maintenance_logs_{timezone.now().strftime("%Y%m%d_%H%M")}.xlsx"'
    wb.save(response)
    return response


def export_tickets_pdf(request):
    """Generates an executive PDF report of CNC maintenance logs."""
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="cnc_maintenance_report_{timezone.now().strftime("%Y%m%d_%H%M")}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1E3A8A'))
    story.append(Paragraph("CNC Machine Maintenance & Breakdown Report", title_style))
    story.append(Paragraph(f"Generated: {timezone.now().strftime('%d-%b-%Y %H:%M')}", styles['Normal']))
    story.append(Spacer(1, 15))

    tickets = BreakdownTicket.objects.select_related('machine', 'failure_sub_category__category').order_by('-alarm_time')[:50]
    data = [["Ticket", "Machine", "Status", "Alarm Time", "Response", "MTTR", "4M Category", "Cost (₹)"]]

    for t in tickets:
        data.append([
            t.ticket_number,
            t.machine.machine_code,
            t.get_status_display()[:10],
            t.alarm_time.strftime("%d-%b %H:%M") if t.alarm_time else "-",
            f"{(t.response_time_seconds or 0) // 60}m",
            f"{(t.total_downtime_seconds or 0) // 60}m",
            t.failure_sub_category.category.code if t.failure_sub_category else "-",
            f"₹{t.total_spares_cost:,.2f}"
        ])

    table = Table(data, colWidths=[110, 80, 90, 90, 70, 70, 90, 90])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F4F6')]),
    ]))

    story.append(table)
    doc.build(story)
    return response


def fetch_live_status_action(request, machine_code):
    """
    Directly queries the physical FANUC CNC controller via FOCAS Ethernet
    and updates the machine status immediately.
    """
    machine = get_object_or_404(CNCMachine, machine_code=machine_code)
    success, result = TelemetryCollector.poll_focas_machine(machine)
    if success:
        messages.success(
            request,
            f"Live FOCAS Telemetry Received for {machine.machine_code}! Status: {result['derived_status']} ({result['status_text']}). Mode: {result['aut_mode_name']}, Run: {result['run_status_name']}."
        )
    else:
        messages.warning(
            request,
            f"Could not connect to CNC at {machine.ip_address}:{machine.port} (FOCAS response: {result}). Status updated to OFFLINE."
        )
    return redirect('machine_detail', machine_code=machine.machine_code)

