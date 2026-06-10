from rest_framework.throttling import AnonRateThrottle


class DownloadRateThrottle(AnonRateThrottle):
    scope = 'downloads'
