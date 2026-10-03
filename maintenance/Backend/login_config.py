"""Demo login credentials for the CNC maintenance application."""

from types import MappingProxyType


LOGIN_CREDENTIALS = MappingProxyType({
    "admin": "myadmin",
    "Maintenance": "mymaintenance",
    "Developer": "mydeveloper",
})

LOGIN_ROLES = MappingProxyType({
    "admin": "Customer",
    "Maintenance": "Maintenance Man",
    "Developer": "Developer",
})
