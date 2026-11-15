from django.core.management.base import BaseCommand

from apps.finance import services
from apps.finance.models import FeeStructure


class Command(BaseCommand):
    help = (
        'Bills every eligible student for every published fee structure that applies right now. '
        'Idempotent - already-invoiced students are skipped. Safety net / backfill: invoices are '
        'normally issued automatically when a fee is published, a level opens a semester, or a '
        'student is admitted or moved.'
    )

    def handle(self, *args, **options):
        total = 0
        for fee_structure in FeeStructure.objects.filter(is_published=True).select_related(
            'fee_type', 'department', 'programme', 'session', 'semester',
        ):
            created, skipped = services.bulk_generate_invoices(fee_structure=fee_structure)
            total += created
            if created:
                self.stdout.write(f'{fee_structure}: {created} created, {skipped} already invoiced')
        self.stdout.write(self.style.SUCCESS(f'Done - {total} invoice(s) created.'))
