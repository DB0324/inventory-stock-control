from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"

    # Same trick as accounts: package is apps.catalog, label stays "catalog"
    # so the tables come out as catalog_item and not apps_catalog_item.
    name = "apps.catalog"
    label = "catalog"
