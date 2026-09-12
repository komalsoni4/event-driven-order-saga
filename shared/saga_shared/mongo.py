from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase


def get_client(mongo_url: str) -> AsyncIOMotorClient:
    return AsyncIOMotorClient(mongo_url)


def get_database(client: AsyncIOMotorClient, name: str) -> AsyncIOMotorDatabase:
    return client[name]
