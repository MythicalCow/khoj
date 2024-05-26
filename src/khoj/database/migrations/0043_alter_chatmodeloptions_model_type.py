# Generated by Django 4.2.10 on 2024-05-26 12:35

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("database", "0042_serverchatsettings"),
    ]

    operations = [
        migrations.AlterField(
            model_name="chatmodeloptions",
            name="model_type",
            field=models.CharField(
                choices=[("openai", "Openai"), ("offline", "Offline"), ("anthropic", "Anthropic")],
                default="offline",
                max_length=200,
            ),
        ),
    ]
