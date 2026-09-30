#include <cstdint>
#include <iostream>
#include <vector>
#include <cmath>

// Scalar matrix multiplication: C = A * B
// Matrices: 256x256 (single-precision float)
// Deterministic initialization using LCG seeded random values

int main() {
    constexpr size_t N = 256;
    constexpr size_t TOTAL = N * N;
    
    // Allocate matrices
    std::vector<float> A(TOTAL);
    std::vector<float> B(TOTAL);
    std::vector<float> C(TOTAL, 0.0f);
    
    // Deterministic initialization using LCG (seed-based)
    // A is initialized with LCG sequence mapped to [0, 1)
    uint32_t seed_a = 2654435761u;
    for (size_t i = 0; i < TOTAL; ++i) {
        seed_a = (seed_a * 1664525u + 22695477u);
        A[i] = static_cast<float>(seed_a & 0x7fffffff) / 2147483647.0f;
    }
    
    // B is initialized with different LCG sequence
    uint32_t seed_b = 1376312589u;
    for (size_t i = 0; i < TOTAL; ++i) {
        seed_b = (seed_b * 1103515245u + 12345u);
        B[i] = static_cast<float>(seed_b & 0x7fffffff) / 2147483647.0f;
    }
    
    // Scalar matrix multiplication: C = A * B
    // Standard triple-nested loop (row-major order)
    for (size_t i = 0; i < N; ++i) {
        for (size_t j = 0; j < N; ++j) {
            float sum = 0.0f;
            for (size_t k = 0; k < N; ++k) {
                sum += A[i * N + k] * B[k * N + j];
            }
            C[i * N + j] = sum;
        }
    }
    
    // Compute deterministic output checksum via Kahan summation
    // (reduces floating-point error accumulation)
    double checksum = 0.0;
    double carry = 0.0;
    for (size_t i = 0; i < TOTAL; ++i) {
        double c_val = static_cast<double>(C[i]);
        double y = c_val - carry;
        double t = checksum + y;
        carry = (t - checksum) - y;
        checksum = t;
    }
    
    // Output as hex to preserve floating-point bit pattern
    uint64_t bits;
    std::memcpy(&bits, &checksum, sizeof(bits));
    std::cout << "0x" << std::hex << bits << "\n";
    
    return 0;
}
