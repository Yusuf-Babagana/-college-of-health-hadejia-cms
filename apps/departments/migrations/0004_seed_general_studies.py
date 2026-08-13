from django.db import migrations


def seed_general_studies(apps, schema_editor):
    Department = apps.get_model('departments', 'Department')
    Department.objects.get_or_create(
        code='GST',
        defaults={
            'name': 'General Studies',
            'description': 'College-wide General Studies courses, available to every student '
                            'at the matching level regardless of their own department.',
            'is_general_studies': True,
        },
    )


def remove_general_studies(apps, schema_editor):
    Department = apps.get_model('departments', 'Department')
    Department.objects.filter(code='GST', is_general_studies=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('departments', '0003_department_is_general_studies'),
    ]

    operations = [
        migrations.RunPython(seed_general_studies, remove_general_studies),
    ]
