from django import forms
from maintenance.models import CNCMachine, ProductionLine


##############################################################################
# Class Name : MachineForm
#
# Parameters : None.
#
# Note : Provides editable CNC machine details for the machine page.
##############################################################################
class MachineForm(forms.ModelForm):
    production_line = forms.ModelChoiceField(
        queryset=ProductionLine.objects.filter(is_active=True),
        required=False,
        label='Line',
    )

    ##############################################################################
    # Class Name : Meta
    #
    # Parameters : None.
    #
    # Note : Selects the machine fields shown in the edit form.
    ##############################################################################
    class Meta:
        model = CNCMachine
        fields = (
            'production_line',
            'service_frequency',
            'last_service_date',
            'name',
            'model_number',
            'controller_type',
            'purchase_date',
            'ip_address',
            'port',
            'timeout',
            'location',
            'is_active',
        )
        widgets = {
            'last_service_date': forms.DateInput(attrs={'type': 'date'}),
            'purchase_date': forms.DateInput(attrs={'type': 'date'}),
        }
