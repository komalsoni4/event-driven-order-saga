SEED_STOCK = [
    {"sku": "SKU-1", "available_qty": 100},
    {"sku": "SKU-2", "available_qty": 100},
    {"sku": "SKU-3", "available_qty": 100},
    {"sku": "SKU-4", "available_qty": 100},
    # Deliberately low stock so the insufficient-stock / short-circuit saga
    # path can be demoed just by ordering a couple of units of this SKU.
    {"sku": "SKU-5", "available_qty": 2},
]
