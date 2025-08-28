"""
Sanitize existing rows to satisfy DB constraints before/after migrations.

Currently fixes:
- humidity to [0, 100]
- rain to be non-negative (rain >= 0)
- pressure to a reasonable range (870 .. 1100) (within DB constraint 800..1200)
- is_raining (if DB column exists): coerce to {0, 1}

Usage:
  python sanitize_data.py

Optional:
  Set DJANGO_SETTINGS_MODULE if not using default settings module.
"""

import os
import sys


def main():
    # Ensure Django is configured
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'weather_station.settings')
    try:
        import django  # noqa: WPS433 (local import by design)
        django.setup()
    except Exception as exc:  # pragma: no cover
        print(f"Failed to setup Django: {exc}")
        sys.exit(1)

    from django.db import connection
    from django.db.models import Q
    from datasets.models import Dataset

    def db_has_column(table: str, column: str) -> bool:
        try:
            with connection.cursor() as cursor:
                desc = connection.introspection.get_table_description(cursor, table)
            cols = {c.name for c in desc}
            return column in cols
        except Exception:
            return False

    # 1) Humidity to [0, 100] using direct UPDATEs to avoid selecting all columns
    lt = Dataset.objects.filter(humidity__lt=0.0)
    gt = Dataset.objects.filter(humidity__gt=100.0)
    lt_count = lt.count()
    gt_count = gt.count()
    if lt_count or gt_count:
        print(f"Clamping humidity: {lt_count} rows <0, {gt_count} rows >100")
        if lt_count:
            lt.update(humidity=0.0)
        if gt_count:
            gt.update(humidity=100.0)
    else:
        print("No invalid humidity values found.")

    # 2) Rain non-negative
    rn = Dataset.objects.filter(rain__lt=0.0)
    rn_count = rn.count()
    if rn_count:
        print(f"Setting negative rain to 0 for {rn_count} rows ...")
        rn.update(rain=0.0)
    else:
        print("No negative rain values found.")

    # 3) Pressure to reasonable range (870..1100)
    p_low = Dataset.objects.filter(pressure__lt=870.0)
    p_high = Dataset.objects.filter(pressure__gt=1100.0)
    p_low_count = p_low.count()
    p_high_count = p_high.count()
    if p_low_count or p_high_count:
        print(f"Clamping pressure: {p_low_count} rows <870, {p_high_count} rows >1100")
        if p_low_count:
            p_low.update(pressure=870.0)
        if p_high_count:
            p_high.update(pressure=1100.0)
    else:
        print("No out-of-range pressure values found.")

    # 4) is_raining to {0,1} if DB column exists (production may not have it yet)
    if db_has_column('datasets_dataset', 'is_raining'):
        # Anything not equal to 0 becomes 1
        ir_not_zero = Dataset.objects.exclude(is_raining=0)
        ir_count = ir_not_zero.count()
        if ir_count:
            print(f"Normalizing is_raining to 0/1 for {ir_count} rows ...")
            # First set all NULL to 0
            Dataset.objects.filter(is_raining__isnull=True).update(is_raining=0)
            # Then set any non-zero to 1
            Dataset.objects.exclude(Q(is_raining=0) | Q(is_raining__isnull=True)).update(is_raining=1)
        else:
            print("No invalid is_raining values found.")
    else:
        print("Column is_raining does not exist in DB schema. Skipping.")


if __name__ == "__main__":
    main()


