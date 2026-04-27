from django.contrib.auth.base_user import BaseUserManager


class MerchantManager(BaseUserManager):
    """Custom manager for the Merchant user model.

    Django requires a custom manager when AUTH_USER_MODEL points at a model
    that doesn't use a username (we use email). _create_user is the shared
    primitive; create_user / create_superuser delegate.
    """
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra_fields)
