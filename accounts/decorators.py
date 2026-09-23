
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied

from .models import User

ADMIN_ONLY = (User.Role.ADMIN,)
STAFF_ONLY = (User.Role.STAFF,)
SUPPORT_TEAM = (User.Role.STAFF, User.Role.ADMIN)
COMPLAINANT_ONLY = (User.Role.COMPLAINANT,)


def role_required(*roles):
 

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.user.role in roles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied

        return _wrapped

    return decorator


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
  

    allowed_roles = ()

    def test_func(self):
        return self.request.user.role in self.allowed_roles