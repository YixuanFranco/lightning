# Generated by Django 2.1.3 on 2019-05-24 03:55

import api_basebone.core.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api_basebone', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='adminlog',
            name='params',
            field=api_basebone.core.fields.JSONField(default={}),
        ),
    ]
