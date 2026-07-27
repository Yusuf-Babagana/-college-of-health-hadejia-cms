from django.db import migrations

PROGRAMMES = [
    ('Diploma in Community Health', 'DCH'),
    ('Certificate in Community Health (JCHEW)', 'CCH'),
    ('Diploma in Health Information Management', 'DHIM'),
    ('Diploma in Environmental Health', 'DEH'),
    ('Diploma in X-Ray and Imaging', 'DXI'),
    ('Diploma in Nutrition and Dietetics', 'DND'),
    ('Retraining in Community Health (JCHEW holders)', 'RCH'),
]


def seed_programmes(apps, schema_editor):
    Programme = apps.get_model('admissions', 'Programme')
    for name, short_code in PROGRAMMES:
        Programme.objects.get_or_create(short_code=short_code, defaults={'name': name})


def remove_programmes(apps, schema_editor):
    Programme = apps.get_model('admissions', 'Programme')
    Programme.objects.filter(short_code__in=[code for _, code in PROGRAMMES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_programmes, remove_programmes),
    ]
