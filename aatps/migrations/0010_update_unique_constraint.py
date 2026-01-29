from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Update unique_together to modern UniqueConstraint.

    This migration replaces the deprecated unique_together Meta option
    with the more flexible UniqueConstraint in the constraints list.
    """

    dependencies = [
        ('aatps', '0009_add_performance_indexes'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='killmailparticipant',
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name='killmailparticipant',
            constraint=models.UniqueConstraint(
                fields=['killmail', 'character'],
                name='unique_killmail_participant'
            ),
        ),
    ]
