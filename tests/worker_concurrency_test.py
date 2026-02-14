import asyncio
import time

import httpx


async def trigger_transcription(client, name, delay=0):
    await asyncio.sleep(delay)
    print(f"[{name}] Sending request...")
    # Mock file upload
    files = {
        "mic_file": ("mic.wav", b"fake audio content", "audio/wav"),
        "tab_file": ("tab.wav", b"fake audio content", "audio/wav"),
    }
    data = {"metadata": '{"title": "Test", "date": "2023-01-01", "duration": 60}'}

    start = time.time()
    try:
        response = await client.post(
            "http://localhost:8001/transcribe", files=files, data=data, timeout=60.0
        )
        duration = time.time() - start
        print(f"[{name}] Finished in {duration:.2f}s. Status: {response.status_code}")
        return response.status_code
    except Exception as e:
        print(f"[{name}] Failed: {e}")
        return 500


async def test_worker_concurrency():
    # Note: This test assumes the worker is running on port 8001
    # and that it actually processes something.
    # Since we don't want to actually run whisper, we might need to mock process_meeting in a real test.
    # For now, we just want to see if the lock logic holds (requests don't crash).

    print("Testing worker concurrency...")
    async with httpx.AsyncClient() as client:
        # Check health
        resp = await client.get("http://localhost:8001/health")
        print(f"Health: {resp.json()}")

        # Send 2 requests almost simultaneously
        # We expect them to be processed sequentially
        task1 = asyncio.create_task(trigger_transcription(client, "Req1", 0))
        task2 = asyncio.create_task(trigger_transcription(client, "Req2", 0.5))

        results = await asyncio.gather(task1, task2)
        print(f"Results: {results}")


if __name__ == "__main__":
    try:
        asyncio.run(test_worker_concurrency())
    except Exception as e:
        print(f"Test failed: {e}")
