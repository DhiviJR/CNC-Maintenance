from django.urls import path
from maintenance.views import login_page, logout_page


urlpatterns = [
    path('', login_page, name='login'),
    path('logout/', logout_page, name='logout'),
]
