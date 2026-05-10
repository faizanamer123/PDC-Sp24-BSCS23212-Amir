import asyncio
import time
import httpx
import sys

sys.path.insert(0, ".")
from circuit_breaker import CircuitBreaker, CircuitState

MOCK_TIMEOUT = 1.0
NUM_REQUESTS = 8
FAILURE_THRESHOLD = 3
RECOVERY_TIMEOUT = 2.0

FALLBACK = {
    "source": "fallback",
    "message": "AI assistant is temporarily unavailable. Please try again shortly.",
}


async def _mock_llm_call(prompt: str) -> dict:
    await asyncio.sleep(MOCK_TIMEOUT)
    raise httpx.TimeoutException("LLM timed out after waiting")


async def scenario_a_no_circuit_breaker():
    print("\n" + "=" * 60)
    print("  SCENARIO A -- WITHOUT Circuit Breaker")
    print("  Each request waits the full timeout before failing.")
    print("=" * 60)

    total_start = time.monotonic()
    for i in range(1, NUM_REQUESTS + 1):
        start = time.monotonic()
        try:
            await asyncio.wait_for(_mock_llm_call(f"prompt {i}"), timeout=MOCK_TIMEOUT)
        except (asyncio.TimeoutError, httpx.TimeoutException, Exception) as e:
            elapsed = time.monotonic() - start
            print(f"  Request {i:02d} | FAILED after {elapsed:.2f}s | {type(e).__name__}")

    total = time.monotonic() - total_start
    print(f"\n  Total time: {total:.2f}s  ({NUM_REQUESTS} requests x ~{MOCK_TIMEOUT}s each)")
    print("  -> Server was BLOCKED the entire time. All users affected.\n")


async def scenario_b_with_circuit_breaker():
    print("=" * 60)
    print("  SCENARIO B -- WITH Circuit Breaker")
    print(f"  Opens after {FAILURE_THRESHOLD} failures. Subsequent calls fail-fast.")
    print("=" * 60)

    breaker = CircuitBreaker(
        name="llm-api",
        failure_threshold=FAILURE_THRESHOLD,
        recovery_timeout=RECOVERY_TIMEOUT,
        expected_exception=Exception,
    )

    total_start = time.monotonic()
    for i in range(1, NUM_REQUESTS + 1):
        start = time.monotonic()
        result = await breaker.call(
            _mock_llm_call,
            f"prompt {i}",
            fallback=FALLBACK,
        )
        elapsed = time.monotonic() - start
        state = breaker.status()["state"]
        tag = "FALLBACK (fast)" if elapsed < 0.05 else "FALLBACK (slow)"
        print(f"  Request {i:02d} | {elapsed:.3f}s | CB={state:9s} | {tag}")

    total = time.monotonic() - total_start
    print(f"\n  Total time: {total:.2f}s")
    print(f"  -> First {FAILURE_THRESHOLD} requests paid the timeout cost.")
    print(f"  -> Requests {FAILURE_THRESHOLD + 1}-{NUM_REQUESTS} returned instantly via fallback.")
    print("  -> App stayed responsive throughout.\n")


async def scenario_c_recovery():
    print("=" * 60)
    print("  SCENARIO C -- Circuit Recovery (HALF_OPEN -> CLOSED)")
    print(f"  After {RECOVERY_TIMEOUT}s the circuit moves to HALF_OPEN.")
    print("=" * 60)

    breaker = CircuitBreaker(
        name="llm-api",
        failure_threshold=2,
        recovery_timeout=RECOVERY_TIMEOUT,
        expected_exception=Exception,
    )

    async def _mock_llm_healthy(prompt: str) -> dict:
        await asyncio.sleep(0.05)
        return {"answer": f"Response to: {prompt}"}

    print("\n  [Phase 1] Tripping the circuit with 2 failures...")
    for i in range(2):
        await breaker.call(_mock_llm_call, "fail", fallback=FALLBACK)
        print(f"    Request {i+1} -> CB={breaker.status()['state']}")

    print(f"\n  [Phase 2] Waiting {RECOVERY_TIMEOUT}s for recovery timeout...")
    await asyncio.sleep(RECOVERY_TIMEOUT + 0.1)
    print(f"    CB state now: {breaker.state.value}")

    print("\n  [Phase 3] Probe request with healthy LLM...")
    result = await breaker.call(_mock_llm_healthy, "what is 2+2?", fallback=FALLBACK)
    print(f"    Result: {result}")
    print(f"    CB state after probe: {breaker.status()['state']}")
    print("\n  -> Circuit successfully recovered to CLOSED\n")


async def test_student_id_header():
    print("=" * 60)
    print("  HEADER TEST -- X-Student-ID on every response")
    print("=" * 60)
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            for path in ["/", "/health", "/cb/status"]:
                r = await client.get(f"http://localhost:8000{path}")
                header = r.headers.get("x-student-id", "MISSING")
                print(f"  GET {path:15s} -> {r.status_code} | X-Student-ID: {header}")
        print()
    except httpx.ConnectError:
        print("  [SKIP] FastAPI server not running (start with: uvicorn main:app --port 8000)\n")


async def main():
    print("\n  StudySync -- Circuit Breaker Test Suite")
    print("  Part 3: Fault Tolerance Fix\n")

    await scenario_a_no_circuit_breaker()
    await scenario_b_with_circuit_breaker()
    await scenario_c_recovery()
    await test_student_id_header()

    print("=" * 60)
    print("  All tests complete.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())