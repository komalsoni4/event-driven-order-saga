from pydantic_settings import BaseSettings, SettingsConfigDict


class SagaSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_connection_url: str | None = None

    mongo_host: str = "mongo"
    mongo_port: int = 27017
    mongo_connection_url: str | None = None

    cors_origins: str = "http://localhost:8080"

    max_retries: int = 3
    retry_base_delay_ms: int = 5000

    payment_fail_threshold_cents: int = 100_000
    admin_api_key: str = "local-admin-key"

    @property
    def rabbitmq_url(self) -> str:
        if self.rabbitmq_connection_url:
            return self.rabbitmq_connection_url
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/"
        )

    @property
    def mongo_url(self) -> str:
        if self.mongo_connection_url:
            return self.mongo_connection_url
        return f"mongodb://{self.mongo_host}:{self.mongo_port}"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
