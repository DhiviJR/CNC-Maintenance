from django.db import migrations, models


##############################################################################
# Class Name : Migration
#
# Parameters : None.
#
# Note : Adds a line name to each CNC machine record.
##############################################################################
class Migration(migrations.Migration):

    dependencies = [
        ('maintenance', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='cncmachine',
            name='line_name',
            field=models.CharField(default='', max_length=100, verbose_name='Line Name'),
        ),
    ]
