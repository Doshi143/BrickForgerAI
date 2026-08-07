"""One-off script: creates the three Stripe Products/Prices this app's
billing needs (Builder subscription, Master Builder subscription, credit
top-up) via the Stripe API, rather than expecting them to already exist in
the dashboard. Run once per Stripe mode (test, then again for live once
Phase 6d flips to live) -- see web/DEPLOYMENT.md's Phase 6b.

Usage: python scripts/create_stripe_prices.py
Prints the three resulting Price IDs -- these get hardcoded into
app/billing.py (per DEPLOYMENT.md's own instruction: "use them directly
in the Checkout code... rather than expecting me to have already put
them in env vars"), not read from an env var at request time.
"""
from __future__ import annotations

import os

import stripe
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]


def main() -> None:
    mode = "TEST" if stripe.api_key.startswith("sk_test_") else "LIVE"
    print(f"Creating prices in {mode} mode...\n")

    builder_product = stripe.Product.create(name="BrickForgerAI — Builder")
    builder_price = stripe.Price.create(
        product=builder_product.id,
        unit_amount=900,
        currency="gbp",
        recurring={"interval": "month"},
    )
    print(f"Builder (£9/mo, 12 credits):        {builder_price.id}")

    master_product = stripe.Product.create(name="BrickForgerAI — Master Builder")
    master_price = stripe.Price.create(
        product=master_product.id,
        unit_amount=2000,
        currency="gbp",
        recurring={"interval": "month"},
    )
    print(f"Master Builder (£20/mo, 30 credits): {master_price.id}")

    topup_product = stripe.Product.create(name="BrickForgerAI — Credit top-up")
    topup_price = stripe.Price.create(
        product=topup_product.id,
        unit_amount=600,
        currency="gbp",
    )
    print(f"Credit top-up (£6, +5 credits):      {topup_price.id}")

    print("\nSave these into app/billing.py's PRICE_IDS / TOPUP_PRICE_ID constants.")


if __name__ == "__main__":
    main()
