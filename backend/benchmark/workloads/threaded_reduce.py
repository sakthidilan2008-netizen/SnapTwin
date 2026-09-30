import sys
from concurrent.futures import ThreadPoolExecutor
def main(n: int = 100_000, workers: int = 4) -> None:
    size = max(1, n // workers)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        values = list(pool.map(lambda start: sum(range(start, min(start + size, n))), range(0, n, size)))
    print(sum(values))
if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 100_000)
