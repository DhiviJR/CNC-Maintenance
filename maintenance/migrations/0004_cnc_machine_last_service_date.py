from django.db import migrations, models


##############################################################################
# Class Name : Migration
#
# Parameters : None.
#
# Note : Adds a place to save each CNC machine's last service date.
##############################################################################
class Migration(migrations.Migration):

    dependencies = [
        ('maintenance', '0003_cnc_machine_service_frequency'),
    ]

    operations = [
        migrations.AddField(
            model_name='cncmachine',
            name='last_service_date',
            field=models.DateField(blank=True, null=True, verbose_name='Last Service Date'),
        ),
    ]
