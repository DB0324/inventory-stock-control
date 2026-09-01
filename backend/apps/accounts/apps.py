from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"

    # The package lives at apps.accounts, but the app *label* stays "accounts"
    # so tables are accounts_user rather than apps_accounts_user, and so
    # AUTH_USER_MODEL reads "accounts.User".
    name = "apps.accounts"
    label = "accounts"