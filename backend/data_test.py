import random
from datetime import datetime, timedelta
import asyncio
from db import get_db
from models import SmsEvent

_NEXT_PROVIDER_STATUS_POOL = (
    10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10,
    11, 11, 11, 11,
    6, 6, 6,
    13,
    14,
)

phone_number = "09123456789"

async def seed_sms_events():
    async for session in get_db():
        for i in range(100):
            body = f"Sample message {i+1}"
            created_at = datetime.utcnow() - timedelta(
                days=random.randint(0, 30),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59)
            )

            provider_status = random.choice(_NEXT_PROVIDER_STATUS_POOL)

            sms = SmsEvent(
                phone=phone_number,
                body=body,
                status="SENT",
                created_at=created_at,
                updated_at=created_at,
                retry_count=random.randint(0, 3),
                segment_count=random.randint(1, 3),
                provider_status=provider_status
            )
            session.add(sms)

        await session.commit()
    print("100 async rows added successfully with provider_status!")

asyncio.run(seed_sms_events())