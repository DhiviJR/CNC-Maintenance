from django.urls import path
from . import views

urlpatterns = [
    # 1. Executive Analytics & Dashboard (Section 4)
    path('', views.dashboard_view, name='dashboard'),
    path('api/dashboard-data/', views.api_dashboard_data, name='api_dashboard_data'),

    # 2. CNC Fleet & QR Management
    path('machines/', views.machine_list_view, name='machine_list'),
    path('machines/<str:machine_code>/', views.machine_detail_view, name='machine_detail'),
    path('machines/<str:machine_code>/qr-print/', views.qr_print_view, name='qr_print'),
    path('machines/<str:machine_code>/fetch-live-status/', views.fetch_live_status_action, name='fetch_live_status'),

    # 3. Technician Mobile QR Scanner & Workflow (Section 3)
    path('scanner/', views.scanner_view, name='scanner'),
    path('scan/<str:machine_code>/', views.scan_machine_action, name='scan_machine'),
    path('tickets/', views.ticket_list_view, name='ticket_list'),
    path('tickets/<int:ticket_id>/', views.ticket_detail_view, name='ticket_detail'),
    path('tickets/create/<str:machine_code>/', views.create_ticket_for_machine, name='create_ticket_for_machine'),

    # 4. Industrial Additions: Andon Board & Interactive Simulator
    path('andon/', views.andon_board_view, name='andon_board'),
    path('preventive-maintenance/', views.preventive_maintenance_view, name='preventive_maintenance'),
    path('simulator/', views.simulator_view, name='simulator'),
    path('api/simulate/', views.api_simulate_action, name='api_simulate_action'),

    # 5. Export Reports
    path('export/excel/', views.export_tickets_excel, name='export_tickets_excel'),
    path('export/pdf/', views.export_tickets_pdf, name='export_tickets_pdf'),
    path('export-excel/', views.export_tickets_excel, name='export_excel'),
    path('export-pdf/', views.export_tickets_pdf, name='export_pdf'),
]
