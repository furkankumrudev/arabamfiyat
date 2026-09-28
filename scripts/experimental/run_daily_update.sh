#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/../lib.sh"
require_python

# Bands keep each search page small enough for the ingestion layer to paginate.
PRICE_BANDS="0-100000,100001-200000,200001-300000,300001-400000,400001-500000,500001-600000,600001-700000,700001-800000,800001-900000,900001-1000000,1000001-1100000,1100001-1200000,1200001-1300000,1300001-1400000,1400001-1500000,1500001-1600000,1600001-1700000,1700001-1800000,1800001-1900000,1900001-2000000,2000001-2250000,2250001-2500000,2500001-2750000,2750001-3000000,3000001-3250000,3250001-3500000,3500001-3750000,3750001-4000000,4000001-4250000,4250001-4500000,4500001-4750000,4750001-5000000,5000001-6000000,6000001-7500000,7500001-10000000,10000001-15000000,15000001+"

SEGMENT="${SEGMENT:-general}"
CHECKPOINT="${CHECKPOINT:-data/runtime/daily_recent_checkpoint.json}"

echo "Pulling ${SEGMENT} listings from the last 24 hours..."
"$PYTHON" -m src.experimental.sahibinden.recent_listing_scraper \
    --days 1 --filter-segments "$SEGMENT" --max-pages 0 --page-size 50 \
    --price-bands "$PRICE_BANDS" --delay-min 3 --delay-max 6 \
    --manual-wait-seconds 180 --max-old-pages 3 --max-stale-pages 0 \
    --max-repeated-pages 3 --stop-on-access \
    --checkpoint-path "$CHECKPOINT" "$@"

echo "Rebuilding cleaned analysis table..."
"$PYTHON" -m src.maintenance.clean_vehicle_data
