import asyncio
import json
import sys

async def test():
    proc = await asyncio.create_subprocess_exec(
        "node",
        "scripts/zca_api_bridge.js",
        "list-groups",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    input_payload = {"auth": {"cookies": "[]", "imei": "123", "userAgent": "test"}}
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(json.dumps(input_payload).encode("utf-8")),
        timeout=120,
    )
    print("STDOUT:", stdout.decode("utf-8"))
    print("STDERR:", stderr.decode("utf-8"))
    print("RETURNCODE:", proc.returncode)

if __name__ == "__main__":
    asyncio.run(test())
