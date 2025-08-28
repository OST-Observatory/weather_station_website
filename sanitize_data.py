"""
Sanitize existing rows to satisfy DB constraints before/after migrations.

Currently fixes:
- humidity to [0, 100]
- rain to be non-negative (rain >= 0)
- pressure to a reasonable range (870 .. 1100) (within DB constraint 800..1200)
- is_raining (if field exists): coerce to {0, 1}

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

    from django.db import transaction
    from django.db.models import Q
    from datasets.models import Dataset

    def clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    field_names = {f.name for f in Dataset._meta.get_fields()}

    # 1) Humidity to [0, 100]
    invalid_q = Q(humidity__lt=0.0) | Q(humidity__gt=100.0)
    qs = Dataset.objects.filter(invalid_q)
    total = qs.count()
    if total:
        print(f"Found {total} rows with invalid humidity. Clamping to [0, 100] ...")
        updated_instances = []
        for obj in qs.iterator(chunk_size=1000):
            obj.humidity = clamp(float(obj.humidity or 0.0), 0.0, 100.0)
            updated_instances.append(obj)
        with transaction.atomic():
            Dataset.objects.bulk_update(updated_instances, ["humidity"], batch_size=1000)
        print(f"Updated {len(updated_instances)} rows for humidity.")
    else:
        print("No invalid humidity values found.")

    # 2) Rain non-negative
    qs = Dataset.objects.filter(rain__lt=0.0)
    total = qs.count()
    if total:
        print(f"Found {total} rows with negative rain. Setting to 0 ...")
        updated_instances = []
        for obj in qs.iterator(chunk_size=1000):
            obj.rain = 0.0
            updated_instances.append(obj)
        with transaction.atomic():
            Dataset.objects.bulk_update(updated_instances, ["rain"], batch_size=1000)
        print(f"Updated {len(updated_instances)} rows for rain.")
    else:
        print("No negative rain values found.")

    # 3) Pressure to reasonable range (870..1100)
    qs = Dataset.objects.filter(Q(pressure__lt=800.0) | Q(pressure__gt=1200.0) | Q(pressure__lt=870.0) | Q(pressure__gt=1100.0))
    total = qs.count()
    if total:
        print(f"Found {total} rows with out-of-range pressure. Clamping to [870, 1100] ...")
        updated_instances = []
        for obj in qs.iterator(chunk_size=1000):
            obj.pressure = clamp(float(obj.pressure or 0.0), 870.0, 1100.0)
            updated_instances.append(obj)
        with transaction.atomic():
            Dataset.objects.bulk_update(updated_instances, ["pressure"], batch_size=1000)
        print(f"Updated {len(updated_instances)} rows for pressure.")
    else:
        print("No out-of-range pressure values found.")

    # 4) is_raining to {0,1} if field exists
    if 'is_raining' in field_names:
        qs = Dataset.objects.exclude(is_raining__in=[0, 1])
        total = qs.count()
        if total:
            print(f"Found {total} rows with invalid is_raining. Coercing to 0/1 ...")
            updated_instances = []
            for obj in qs.iterator(chunk_size=1000):
                try:
                    ivalue = int(round(float(obj.is_raining or 0)))
                except Exception:
                    ivalue = 0
                obj.is_raining = 1 if ivalue >= 1 else 0
                updated_instances.append(obj)
            with transaction.atomic():
                Dataset.objects.bulk_update(updated_instances, ["is_raining"], batch_size=1000)
            print(f"Updated {len(updated_instances)} rows for is_raining.")
        else:
            print("No invalid is_raining values found (or none exist).")
    else:
        print("Field is_raining does not exist on this schema. Skipping.")


if __name__ == "__main__":
    main()


