#include <cuda_runtime.h>
#include <mma.h>

#include <cmath>
#include <cstdio>

namespace wmma = nvcuda::wmma;

namespace {

constexpr int kM = 8;
constexpr int kN = 8;
constexpr int kK = 4;
constexpr int kElementCountA = kM * kK;
constexpr int kElementCountB = kK * kN;
constexpr int kElementCountC = kM * kN;

bool cuda_ok(cudaError_t status, const char* operation) {
    if (status == cudaSuccess) {
        return true;
    }

    std::fprintf(stderr, "%s failed: %s\n", operation, cudaGetErrorString(status));
    return false;
}

__global__ void fp64_wmma_probe(const double* matrix_a,
                                const double* matrix_b,
                                double* matrix_c) {
    wmma::fragment<wmma::matrix_a, kM, kN, kK, double, wmma::row_major> a;
    wmma::fragment<wmma::matrix_b, kM, kN, kK, double, wmma::col_major> b;
    wmma::fragment<wmma::accumulator, kM, kN, kK, double> c;

    wmma::load_matrix_sync(a, matrix_a, kK);
    wmma::load_matrix_sync(b, matrix_b, kK);
    wmma::fill_fragment(c, 0.0);
    wmma::mma_sync(c, a, b, c);
    wmma::store_matrix_sync(matrix_c, c, kN, wmma::mem_row_major);
}

}  // namespace

int main() {
    int device = 0;
    cudaDeviceProp properties{};
    if (!cuda_ok(cudaGetDevice(&device), "cudaGetDevice") ||
        !cuda_ok(cudaGetDeviceProperties(&properties, device),
                 "cudaGetDeviceProperties")) {
        return 1;
    }

    double* matrix_a = nullptr;
    double* matrix_b = nullptr;
    double* matrix_c = nullptr;
    if (!cuda_ok(cudaMallocManaged(&matrix_a, kElementCountA * sizeof(double)),
                 "cudaMallocManaged(A)") ||
        !cuda_ok(cudaMallocManaged(&matrix_b, kElementCountB * sizeof(double)),
                 "cudaMallocManaged(B)") ||
        !cuda_ok(cudaMallocManaged(&matrix_c, kElementCountC * sizeof(double)),
                 "cudaMallocManaged(C)")) {
        cudaFree(matrix_a);
        cudaFree(matrix_b);
        cudaFree(matrix_c);
        return 1;
    }

    for (int index = 0; index < kElementCountA; ++index) {
        matrix_a[index] = 1.0;
    }
    for (int index = 0; index < kElementCountB; ++index) {
        matrix_b[index] = 1.0;
    }

    fp64_wmma_probe<<<1, 32>>>(matrix_a, matrix_b, matrix_c);
    const bool launch_pass = cuda_ok(cudaGetLastError(), "fp64_wmma_probe launch") &&
                             cuda_ok(cudaDeviceSynchronize(),
                                     "fp64_wmma_probe synchronize");

    bool numeric_pass = launch_pass;
    if (launch_pass) {
        for (int index = 0; index < kElementCountC; ++index) {
            if (std::abs(matrix_c[index] - 4.0) > 1.0e-12) {
                numeric_pass = false;
                break;
            }
        }
    }

    std::printf(
        "{\"compute_capability\":\"%d.%d\",\"numeric_pass\":%s}\n",
        properties.major,
        properties.minor,
        numeric_pass ? "true" : "false");

    cudaFree(matrix_a);
    cudaFree(matrix_b);
    cudaFree(matrix_c);
    return numeric_pass ? 0 : 2;
}
