import pytest
from mongomock_motor import AsyncMongoMockClient


@pytest.fixture
def db():
    client = AsyncMongoMockClient()
    return client["test_inventory_db"]
