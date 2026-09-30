#include <cstdint>
#include <iostream>
#include <vector>

int main() {
    constexpr std::size_t n = 1'000'000;
    std::vector<std::uint64_t> values(n);
    std::uint64_t checksum = 0;
    for (std::size_t i = 0; i < n; ++i) {
        values[i] = (static_cast<std::uint64_t>(i) * 1664525u + 1013904223u) & 0xffffffffu;
        checksum ^= (values[i] + i * 31u);
    }
    std::cout << checksum << "\n";
    return 0;
}
