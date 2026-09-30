import sys
def main(n: int = 100_000) -> None:
    data = list(range(n)); total = 0
    for i in range(0, n, 3): total += data[i]
    print(total)
if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 100_000)
