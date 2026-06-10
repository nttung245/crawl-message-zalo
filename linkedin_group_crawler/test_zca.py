import asyncio
from app.modules.zalo.services.zca_api_bridge import list_zca_groups

async def test():
    try:
        res = await list_zca_groups({"cookies": "[]", "imei": "12345", "userAgent": "test"})
        print(res)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
