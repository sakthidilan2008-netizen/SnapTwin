#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>
#include <cmath>

#ifdef __ARM_NEON__
#include <arm_neon.h>
#endif

// NEON-optimized matrix multiplication: C = A * B
// Matrices: 256x256 (single-precision float)
// Uses ARM64 NEON float32x4_t for vectorized dot products

int main() {
    constexpr size_t N = 256;
    constexpr size_t TOTAL = N * N;
    
    // Allocate matrices
    std::vector<float> A(TOTAL);
    std::vector<float> B(TOTAL);
    std::vector<float> C(TOTAL, 0.0f);
    
    // Deterministic initialization using LCG (same as scalar)
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
    
#ifdef __ARM_NEON__
    // NEON-optimized matrix multiplication
    // Process 4 columns at a time using NEON float32x4_t
    for (size_t i = 0; i < N; ++i) {
        for (size_t j = 0; j < N; j += 4) {
            // Process 4 columns simultaneously
            float32x4_t sum0 = vdupq_n_f32(0.0f);
            float32x4_t sum1 = vdupq_n_f32(0.0f);
            float32x4_t sum2 = vdupq_n_f32(0.0f);
            float32x4_t sum3 = vdupq_n_f32(0.0f);
            
            for (size_t k = 0; k < N; ++k) {
                float a_val = A[i * N + k];
                float32x4_t a_vec = vdupq_n_f32(a_val);
                
                // Load 4 consecutive B[k][j..j+3] values
                float32x4_t b_vals = vld1q_f32(&B[k * N + j]);
                
                // Accumulate: sum += a_val * b_vals (element-wise)
                float32x4_t products = vmulq_f32(a_vec, b_vals);
                sum0 = vaddq_f32(sum0, products);
            }
            
            // Store results (4 at a time)
            vst1q_f32(&C[i * N + j], sum0);
        }
    }
#else
    // Scalar fallback
    for (size_t i = 0; i < N; ++i) {
        for (size_t j = 0; j < N; ++j) {
            float sum = 0.0f;
            for (size_t k = 0; k < N; ++k) {
                sum += A[i * N + k] * B[k * N + j];
            }
            C[i * N + j] = sum;
        }
    }
#endif
    
    // Compute deterministic output checksum via Kahan summation
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
