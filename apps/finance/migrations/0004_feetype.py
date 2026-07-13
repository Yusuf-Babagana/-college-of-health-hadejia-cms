import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0003_payment'),
    ]

    operations = [
        migrations.CreateModel(
            name='FeeType',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(db_index=True, default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=100, unique=True)),
                ('description', models.CharField(blank=True, max_length=200)),
            ],
            options={
                'verbose_name': 'Fee Type',
                'verbose_name_plural': 'Fee Types',
                'ordering': ['name'],
            },
        ),
    ]
