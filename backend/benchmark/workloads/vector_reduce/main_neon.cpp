#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>

// ARM64 NEON intrinsics
#ifdef __ARM_NEON__
#include <arm_neon.h>
#endif

int main() {
    constexpr std::size_t n = 1'000'000;
    std::vector<std::uint64_t> values(n);
    std::vector<std::uint64_t> temp(n);
    std::uint64_t checksum = 0;

#ifdef __ARM_NEON__
    // NEON-optimized path: process 2 uint64_t at a time using 128-bit NEON registers
    // Generate values using simple SIMD operations
    for (std::size_t i = 0; i < n; i += 2) {
        uint64x2_t indices = vsetq_lane_u64(i + 1, vsetq_lane_u64(i, vdupq_n_u64(0)), 1);
        uint64x2_t mult = vdupq_n_u64(1664525u);
        uint64x2_t add = vdupq_n_u64(1013904223u);
        uint64x2_t generated = vandq_u64(vaddq_u64(vmulq_u64(indices, mult), add), vdupq_n_u64(0xffffffffu));
        
        vst1q_u64(&values[i], generated);

        // Compute checksum contribution
        uint64x2_t indices_shift = vsetq_lane_u64((i + 1) * 31u, vsetq_lane_u64(i * 31u, vdupq_n_u64(0)), 1);
        uint64x2_t xor_values = veorq_u64(generated, indices_shift);
        
        checksum ^= vgetq_lane_u64(xor_values, 0);
        checksum ^= vgetq_lane_u64(xor_values, 1);
    }
#else
    // Scalar fallback
    for (std::size_t i = 0; i < n; ++i) {
        values[i] = (static_cast<std::uint64_t>(i) * 1664525u + 1013904223u) & 0xffffffffu;
        checksum ^= (values[i] + i * 31u);
    }
#endif

    std::cout << checksum << "\n";
    return 0;
}
