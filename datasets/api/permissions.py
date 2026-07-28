"""Permissions for weather upload endpoints."""

from rest_framework.permissions import BasePermission


class IsActiveUploadDevice(BasePermission):
    """Accept only authenticated UploadDevice identities — never staff/admins alone."""

    message = 'Upload credentials required.'

    def has_permission(self, request, view):
        device = getattr(request, 'upload_device', None)
        if device is None:
            return False
        return bool(device.is_active)
