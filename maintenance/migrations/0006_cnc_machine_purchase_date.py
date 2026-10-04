from django.db import migrations, models


##############################################################################
# Class Name : Migration
#
# Parameters : None.
#
# Note : Adds the purchase date to each CNC machine record.
##############################################################################
class Migration(migrations.Migration):

    dependencies = [
        ('maintenance', '0005_productionline_cncmachine_production_line'),
    ]

    operations = [
        migrations.AddField(
            model_name='cncmachine',
            name='purchase_date',
            field=models.DateField(blank=True, null=True, verbose_name='Purchase Date'),
        ),
    ]
