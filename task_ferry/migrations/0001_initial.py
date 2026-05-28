from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    
    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    
    operations = [
        migrations.CreateModel(
            name="Job",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "state",
                    models.CharField(
                        db_index=True,
                        default="pending",
                        help_text="Current lifecycle state of the job.",
                        max_length=32,
                    ),
                ),
                (
                    "progress_percentage",
                    models.IntegerField(
                        default=0,
                        help_text="0-100. Updated via cache mid-run; persisted to DB at completion.",
                    ),
                ),
                (
                    "progress_state",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Human-readable description of the current step.",
                        max_length=255,
                    ),
                ),
                (
                    "error",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Short error string (exception message).",
                    ),
                ),
                (
                    "human_readable_error",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Longer, user-facing error description.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "content_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="task_ferry_jobs",
                        to="contenttypes.contenttype",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="task_ferry_jobs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
    ]
