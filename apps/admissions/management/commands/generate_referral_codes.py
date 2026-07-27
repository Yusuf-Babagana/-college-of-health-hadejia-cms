from django.core.management.base import BaseCommand

from apps.admissions.models import ReferralCode
from apps.core.utils.generators import generate_reference_code


class Command(BaseCommand):
    help = 'Bulk-generate admission referral codes that waive the application fee.'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=10, help='Number of codes to generate.')
        parser.add_argument('--prefix', type=str, default='', help='Optional prefix, e.g. COHST-')
        parser.add_argument('--batch-label', type=str, default='', help='Optional label to group this batch.')

    def handle(self, *args, **options):
        count = options['count']
        prefix = options['prefix']
        batch_label = options['batch_label']

        codes = []
        while len(codes) < count:
            code = generate_reference_code(prefix=prefix, length=8)
            if not ReferralCode.objects.filter(code=code).exists() and code not in codes:
                codes.append(code)

        ReferralCode.objects.bulk_create([
            ReferralCode(code=code, batch_label=batch_label) for code in codes
        ])

        self.stdout.write(self.style.SUCCESS(f'Generated {count} referral code(s):'))
        for code in codes:
            self.stdout.write(f'  {code}')
