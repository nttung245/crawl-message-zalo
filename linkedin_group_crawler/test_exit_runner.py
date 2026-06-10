import asyncio
import sys

async def test():
    proc = await asyncio.create_subprocess_exec(
        "node",
        "test_exit.js",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    print("OUT:", out.decode('utf-8'))
    print("ERR:", err.decode('utf-8'))
    print("RC:", proc.returncode)

if __name__ == "__main__":
    asyncio.run(test())
