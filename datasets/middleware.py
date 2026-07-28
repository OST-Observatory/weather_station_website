"""Lightweight Redis/cache-backed rate limit for the HTML dashboard."""

from __future__ import annotations

import time

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse


class DashboardRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, 'DASHBOARD_RATE_LIMIT_ENABLED', True):
            return self.get_response(request)

        path = request.path
        # Match dashboard under FORCE_SCRIPT_NAME and bare paths.
        if not (path.endswith('/dashboard/') or path.endswith('/dashboard')):
            return self.get_response(request)

        limit = int(getattr(settings, 'DASHBOARD_RATE_LIMIT_PER_MINUTE', 60))
        ident = request.META.get('REMOTE_ADDR', 'unknown')
        window = int(time.time() // 60)
        key = f'dashboard-rl:{ident}:{window}'
        try:
            count = cache.get(key)
            if count is None:
                cache.add(key, 1, timeout=70)
                count = 1
            else:
                try:
                    count = cache.incr(key)
                except ValueError:
                    cache.set(key, 1, timeout=70)
                    count = 1
        except Exception:
            return self.get_response(request)

        if count > limit:
            return HttpResponse('Too Many Requests', status=429)

        return self.get_response(request)
