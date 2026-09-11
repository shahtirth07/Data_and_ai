import os
import random
from datetime import date, timedelta

import pandas as pd

SEED = 42
NUM_ROWS = 5000

regions = ["West", "East", "South", "Midwest", "Northeast"]
categories = ["Electronics", "Home", "Apparel", "Grocery"]
channel_options = ["online", "store"]

products_by_category = {
    "Electronics": ["Laptop", "Headphones", "Phone Case"],
    "Home": ["Blender", "Lamp", "Towel Set"],
    "Apparel": ["T-Shirt", "Jeans", "Jacket"],
    "Grocery": ["Coffee Beans", "Pasta", "Olive Oil"],
}

return_product = "Headphones"

base_prices = {
    "Laptop": 899.0,
    "Headphones": 79.0,
    "Phone Case": 24.0,
    "Blender": 59.0,
    "Lamp": 35.0,
    "Towel Set": 28.0,
    "T-Shirt": 18.0,
    "Jeans": 48.0,
    "Jacket": 89.0,
    "Coffee Beans": 14.0,
    "Pasta": 3.5,
    "Olive Oil": 12.0,
}

rng = random.Random(SEED)

start_date = date(2025, 1, 1)
end_date = date(2025, 12, 31)
day_span = (end_date - start_date).days

rows = []

for i in range(NUM_ROWS):
    order_id = i + 1

    day_offset = rng.randint(0, day_span)
    order_date = start_date + timedelta(days=day_offset)
    month = order_date.month

    region_roll = rng.random()
    if month >= 10:
        if region_roll < 0.45:
            region = "West"
        else:
            region_index = rng.randint(0, len(regions) - 1)
            region = regions[region_index]
    else:
        if region_roll < 0.18:
            region = "West"
        else:
            region_index = rng.randint(0, len(regions) - 1)
            region = regions[region_index]

    category_index = rng.randint(0, len(categories) - 1)
    category = categories[category_index]

    product_list = products_by_category[category]
    product_index = rng.randint(0, len(product_list) - 1)
    product = product_list[product_index]

    channel_index = rng.randint(0, len(channel_options) - 1)
    channel = channel_options[channel_index]

    unit_price = base_prices[product]
    price_jitter = rng.uniform(-0.05, 0.05)
    unit_price = round(unit_price * (1.0 + price_jitter), 2)

    if product == return_product:
        return_roll = rng.random()
        if return_roll < 0.55:
            quantity = 0
        else:
            quantity = rng.randint(1, 5)
    else:
        quantity = rng.randint(1, 8)

    if region == "West":
        if month >= 10:
            quantity = quantity + rng.randint(3, 8)

    amount = round(quantity * unit_price, 2)

    row = {
        "order_id": order_id,
        "order_date": order_date.isoformat(),
        "region": region,
        "category": category,
        "product": product,
        "channel": channel,
        "quantity": quantity,
        "unit_price": unit_price,
        "amount": amount,
    }
    rows.append(row)

df = pd.DataFrame(rows)

script_dir = os.path.dirname(os.path.abspath(__file__))
output_path = os.path.join(script_dir, "orders.csv")
df.to_csv(output_path, index=False)

print("Wrote", len(df), "rows to", output_path)
