import django.db.models.deletion
from django.db import migrations, models


def backfill_fee_type(apps, schema_editor):
    """Existing fee structures predate the fee-type split; file them all
    under a default 'Tuition Fee' type so the new FK is never null.
    """
    FeeType = apps.get_model('finance', 'FeeType')
    FeeStructure = apps.get_model('finance', 'FeeStructure')

    fee_structures = FeeStructure.objects.filter(fee_type__isnull=True)
    if not fee_structures.exists():
        return

    tuition, _ = FeeType.objects.get_or_create(
        name='Tuition Fee',
        defaults={'description': 'Standard tuition fee.'},
    )
    fee_structures.update(fee_type=tuition)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0004_feetype'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='feestructure',
            options={
                'ordering': ['-session__name', 'department__code', 'level', 'fee_type__name'],
                'verbose_name': 'Fee Structure',
                'verbose_name_plural': 'Fee Structures',
            },
        ),
        migrations.AlterField(
            model_name='feestructure',
            name='description',
            field=models.CharField(blank=True, help_text='e.g. Library + Sports Levy', max_length=200),
        ),
        migrations.RemoveConstraint(
            model_name='feestructure',
            name='unique_fee_structure_per_dept_level_session',
        ),
        migrations.AddField(
            model_name='feestructure',
            name='fee_type',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='fee_structures',
                to='finance.feetype',
            ),
        ),
        migrations.RunPython(backfill_fee_type, noop_reverse),
        migrations.AlterField(
            model_name='feestructure',
            name='fee_type',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='fee_structures',
                to='finance.feetype',
            ),
        ),
        migrations.AddConstraint(
            model_name='feestructure',
            constraint=models.UniqueConstraint(
                fields=('department', 'level', 'session', 'fee_type'),
                name='unique_fee_structure_per_dept_level_session_type',
            ),
        ),
    ]
