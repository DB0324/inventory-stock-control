import pytest
from django.core.cache import cache

from apps.catalog.models import Category, Item
from apps.stock.models import Location, LocationAssignment


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    """Login rate-limit counters live in the cache, which -- unlike the
    database -- pytest-django does not roll back between tests.

    Without this, tests that attempt several logins spend the budget for
    every later test using the same email, and the failure surfaces somewhere
    unrelated as a mystery 429. Autouse and global, because the leak is not
    confined to the tests that do the throttling.
    """
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def manager(db, django_user_model):
    return django_user_model.objects.create_user(
        email="manager@test.local", password="x", full_name="Test Manager",
        role=django_user_model.Role.MANAGER,
    )


@pytest.fixture
def warehouse(db):
    return Location.objects.create(code="WH", name="Warehouse")


@pytest.fixture
def shop(db):
    return Location.objects.create(code="SF", name="Shop floor")


@pytest.fixture
def staff_wh(db, django_user_model, manager, warehouse):
    """Assigned to the warehouse only. The shop is deliberately excluded so
    the scoping tests have something to be refused at."""
    user = django_user_model.objects.create_user(
        email="staff@test.local", password="x", full_name="WH Staff",
        role=django_user_model.Role.STAFF,
    )
    LocationAssignment.objects.create(user=user, location=warehouse, assigned_by=manager)
    return user


@pytest.fixture
def category(db):
    return Category.objects.create(name="Fasteners")


@pytest.fixture
def item(db, category):
    return Item.objects.create(
        sku="A-100", name="Hex bolt M8", reorder_level=10, category=category,
    )