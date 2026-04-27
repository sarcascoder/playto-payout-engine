import os

from celery import Celery
from celery.schedules import schedule

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("playto_payouts")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Watchdog every 10s. Idempotency TTL purge every hour."""
    sender.add_periodic_task(
        schedule(10),
        sender.signature("payouts.tasks.reap_stuck_payouts"),
        name="reap-stuck-payouts",
    )
    sender.add_periodic_task(
        schedule(3600),
        sender.signature("payouts.tasks.purge_expired_idempotency"),
        name="purge-expired-idempotency",
    )
