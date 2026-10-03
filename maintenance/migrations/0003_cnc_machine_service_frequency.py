from django.db import migrations, models


##############################################################################
# Class Name : Migration
#
# Parameters : None.
#
# Note : Adds the service frequency to each CNC machine.
##############################################################################
class Migration(migrations.Migration):

    dependencies = [
        ('maintenance', '0002_cnc_machine_line_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='cncmachine',
            name='service_frequency',
            field=models.PositiveSmallIntegerField(
                choices=[
                    (1, '1 month'),
                    (2, '2 months'),
                    (3, '3 months'),
                    (4, '4 months'),
                    (5, '5 months'),
                    (6, '6 months'),
                    (7, '7 months'),
                    (8, '8 months'),
                    (9, '9 months'),
                    (10, '10 months'),
                    (11, '11 months'),
                    (12, '12 months'),
                ],
                default=1,
                verbose_name='Service Frequency (Months)',
            ),
        ),
    ]
