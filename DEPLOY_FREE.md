# Free deployment path

This repository can be deployed without a paid plan by using free tiers from multiple providers:

- Render free web services: the three APIs and the UI
- MongoDB Atlas free cluster: MongoDB
- A free hosted RabbitMQ-compatible broker: RabbitMQ connection URL

The included `render.yaml` creates four Render services. It does not create MongoDB or RabbitMQ because those providers require their own accounts and connection credentials.

## Required hosted secrets

For each backend Render service, set:

- `MONGO_CONNECTION_URL`: MongoDB Atlas connection string
- `RABBITMQ_CONNECTION_URL`: hosted AMQP connection string
- `ADMIN_API_KEY`: a long random value
- `CORS_ORIGINS`: the public UI URL, for example `https://order-saga-ui.onrender.com`

For the UI service, set:

- `ORDER_SERVICE_URL`: public order-service URL
- `INVENTORY_SERVICE_URL`: public inventory-service URL
- `PAYMENT_SERVICE_URL`: public payment-service URL

## Deployment steps

1. Create a free MongoDB Atlas cluster and copy its connection string.
2. Create a free RabbitMQ-compatible broker and copy its AMQP URL.
3. In Render, choose **New > Blueprint** and connect this GitHub repository.
4. Select the `render.yaml` blueprint and deploy the four services.
5. Fill the `sync: false` environment variables in each service.
6. After Render assigns the UI URL, set that URL as `CORS_ORIGINS` in all backend services.
7. Set the three backend URLs in the UI service and redeploy the UI.

Free services may sleep when unused, so the first request after inactivity can be slow. This setup is for a portfolio demo, not production traffic.