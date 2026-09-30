import sys
def main(n: int = 2_000_000) -> None:
    value = 0
    for i in range(n):
        value = (value * 1664525 + i + 1013904223) & 0xFFFFFFFF
    print(value)
if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2_000_000)
