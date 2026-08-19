// The baseline kernel, lookup layout, and triangular weight construction are
// adapted from Microsoft ConvStencil src/2d/gpu.cu at commit
// 89688a1b51ec41b4a81028b0661363ba3afd6050. ConvStencil is distributed under
// the MIT License; see ../LICENSE.ConvStencil. The standalone validation
// harness is specific to this experiment.

#include <cuda_runtime.h>
#include <mma.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <stdexcept>
#include <string>
#include <vector>

namespace wmma = nvcuda::wmma;

namespace {

constexpr int kBlockRows = 32;
constexpr int kBaselineBlockColumns = 64;
constexpr int kHalo = 3;
constexpr int kDataBlockColumns = kBaselineBlockColumns + 2 * kHalo;
constexpr int kDataBlockRows = kBlockRows + 2 * kHalo;
constexpr int kPadding = 2;
constexpr int kSharedColumns = 7 * kDataBlockRows + kPadding;
constexpr int kSharedRows = kDataBlockColumns / 8;
constexpr int kSharedPlaneElements =
    kSharedRows * kSharedColumns + 4;
constexpr int kUnitLength = 7;
constexpr int kWarpCount = 8;
constexpr int kMmaCount = 13;
constexpr int kWeightRows = 52;
constexpr int kTensorDimension = 8;

constexpr int kLastInputFragmentIndex =
    (kSharedRows - 1) * kSharedColumns +
    (kWarpCount - 1) * 28 + 3 * kUnitLength +
    (kMmaCount - 1) * 4 + 3;
static_assert(kLastInputFragmentIndex < kSharedPlaneElements);
static_assert(kSharedPlaneElements % 4 == 0);

__constant__ double device_weight_matrices[2 * kWeightRows * kTensorDimension];

void cuda_check(cudaError_t status, const char* operation) {
    if (status != cudaSuccess) {
        throw std::runtime_error(std::string(operation) + ": " +
                                 cudaGetErrorString(status));
    }
}

__global__ void convstencil_baseline_kernel(
    const double* __restrict__ input,
    double* __restrict__ output,
    int leading_dimension,
    const int* __restrict__ lookup_a,
    const int* __restrict__ lookup_b) {
    __shared__ double shared_memory[2][kSharedPlaneElements];
    const int begin =
        (blockIdx.x * kBlockRows) * leading_dimension +
        blockIdx.y * kBaselineBlockColumns + 1;
    const int thread_id = threadIdx.x;

#pragma unroll
    for (int index = thread_id;
         index < kDataBlockRows * kDataBlockColumns;
         index += blockDim.x) {
        const int row = index / kDataBlockColumns;
        const int column = index % kDataBlockColumns;
        shared_memory[0][lookup_a[index]] =
            input[begin + row * leading_dimension + column];
        shared_memory[1][lookup_b[index]] =
            input[begin + row * leading_dimension + column];
    }
    __syncthreads();

    const int warp_id = threadIdx.x / 32;
    wmma::fragment<wmma::matrix_b, 8, 8, 4, double, wmma::row_major>
        weight_fragments[2][kMmaCount];
#pragma unroll
    for (int index = 0; index < kMmaCount; ++index) {
        wmma::load_matrix_sync(
            weight_fragments[0][index],
            device_weight_matrices + index * 32,
            8);
        wmma::load_matrix_sync(
            weight_fragments[1][index],
            device_weight_matrices + kWeightRows * kTensorDimension + index * 32,
            8);
    }

    wmma::fragment<wmma::accumulator, 8, 8, 4, double> accumulator;
    wmma::fragment<wmma::matrix_a, 8, 8, 4, double, wmma::row_major>
        input_fragment;
    for (int column = warp_id * 28;
         column < warp_id * 28 + 28;
         column += kUnitLength) {
        wmma::fill_fragment(accumulator, 0.0);
#pragma unroll
        for (int compute_index = 0; compute_index < kMmaCount; ++compute_index) {
            wmma::load_matrix_sync(
                input_fragment,
                shared_memory[0] + column + compute_index * 4,
                kSharedColumns);
            wmma::mma_sync(
                accumulator,
                input_fragment,
                weight_fragments[0][compute_index],
                accumulator);
        }
#pragma unroll
        for (int compute_index = 0; compute_index < kMmaCount; ++compute_index) {
            wmma::load_matrix_sync(
                input_fragment,
                shared_memory[1] + column + compute_index * 4,
                kSharedColumns);
            wmma::mma_sync(
                accumulator,
                input_fragment,
                weight_fragments[1][compute_index],
                accumulator);
        }
        wmma::store_matrix_sync(
            output + begin +
                (kHalo + column / kUnitLength) * leading_dimension + kHalo,
            accumulator,
            kTensorDimension,
            wmma::mem_row_major);
    }
}

std::vector<double> make_input(int rows, int columns) {
    std::vector<double> input(static_cast<size_t>(rows) * columns);
    for (int row = 0; row < rows; ++row) {
        for (int column = 0; column < columns; ++column) {
            const int value = (row * 37 + column * 19 + row * column * 3) % 101;
            input[static_cast<size_t>(row) * columns + column] =
                static_cast<double>(value - 50) / 29.0;
        }
    }
    return input;
}

std::vector<double> make_weights() {
    std::vector<double> weights(49);
    for (int index = 0; index < 49; ++index) {
        const int value = (index * 11 + 5) % 23;
        weights[index] = static_cast<double>(value - 11) / 31.0;
    }
    return weights;
}

std::vector<double> make_weight_matrices(const std::vector<double>& weights) {
    std::vector<double> matrices(2 * kWeightRows * kTensorDimension, 0.0);
    for (int column = 0; column < kTensorDimension; ++column) {
        for (int row = 0; row < kUnitLength; ++row) {
            for (int inner = 0; inner < kUnitLength; ++inner) {
                if (inner >= column) {
                    matrices[(row * kUnitLength + inner) * kTensorDimension +
                             column] =
                        weights[row * kUnitLength + inner - column];
                }
                if (inner < column) {
                    matrices[kWeightRows * kTensorDimension +
                             (row * kUnitLength + inner) * kTensorDimension +
                             column] =
                        weights[row * kUnitLength + inner - column +
                                kUnitLength];
                }
            }
        }
    }
    return matrices;
}

void make_baseline_lookups(std::vector<int>& lookup_a,
                           std::vector<int>& lookup_b) {
    const int sentinel = kSharedRows * kSharedColumns - 1;
    for (int row = 0; row < kDataBlockRows; ++row) {
        for (int column = 0; column < kDataBlockColumns; ++column) {
            const int index = row * kDataBlockColumns + column;
            if ((column + 1) % 8 != 0 &&
                column < kDataBlockColumns - 2 * kHalo - 1) {
                lookup_a[index] =
                    (column / 8) * kSharedColumns +
                    kUnitLength * row + column % 8;
            } else {
                lookup_a[index] = sentinel;
            }
            if ((column + 2) % 8 != 0 && column > 2 * kHalo) {
                lookup_b[index] =
                    ((column - kUnitLength) / 8) * kSharedColumns +
                    kUnitLength * row + (column - kUnitLength) % 8;
            } else {
                lookup_b[index] = sentinel;
            }
        }
    }
}

double cpu_reference_at(const std::vector<double>& input,
                        const std::vector<double>& weights,
                        int output_row,
                        int output_column,
                        int leading_dimension) {
    double result = 0.0;
    for (int kernel_row = 0; kernel_row < kUnitLength; ++kernel_row) {
        for (int kernel_column = 0;
             kernel_column < kUnitLength;
             ++kernel_column) {
            result +=
                input[static_cast<size_t>(output_row - kHalo + kernel_row) *
                          leading_dimension +
                      output_column - kHalo + kernel_column] *
                weights[kernel_row * kUnitLength + kernel_column];
        }
    }
    return result;
}

int run_baseline_correctness(int height, int width) {
    if (height <= 0 || width <= 0 || height % kBlockRows != 0 ||
        width % kBaselineBlockColumns != 0) {
        throw std::invalid_argument(
            "baseline dimensions must be positive multiples of 32x64");
    }

    const int rows = height + 2 * kHalo;
    const int columns = width + 2 * kHalo + 2;
    const size_t element_count = static_cast<size_t>(rows) * columns;
    const size_t byte_count = element_count * sizeof(double);

    const std::vector<double> input = make_input(rows, columns);
    const std::vector<double> weights = make_weights();
    const std::vector<double> weight_matrices = make_weight_matrices(weights);
    std::vector<double> output(element_count, 0.0);

    std::vector<int> lookup_a(kDataBlockRows * kDataBlockColumns);
    std::vector<int> lookup_b(kDataBlockRows * kDataBlockColumns);
    make_baseline_lookups(lookup_a, lookup_b);

    double* device_input = nullptr;
    double* device_output = nullptr;
    int* device_lookup_a = nullptr;
    int* device_lookup_b = nullptr;
    cuda_check(cudaMalloc(&device_input, byte_count), "cudaMalloc(input)");
    cuda_check(cudaMalloc(&device_output, byte_count), "cudaMalloc(output)");
    cuda_check(
        cudaMalloc(&device_lookup_a, lookup_a.size() * sizeof(int)),
        "cudaMalloc(lookup_a)");
    cuda_check(
        cudaMalloc(&device_lookup_b, lookup_b.size() * sizeof(int)),
        "cudaMalloc(lookup_b)");

    try {
        cuda_check(
            cudaMemcpy(
                device_input, input.data(), byte_count, cudaMemcpyHostToDevice),
            "cudaMemcpy(input)");
        cuda_check(cudaMemset(device_output, 0, byte_count), "cudaMemset(output)");
        cuda_check(
            cudaMemcpy(
                device_lookup_a,
                lookup_a.data(),
                lookup_a.size() * sizeof(int),
                cudaMemcpyHostToDevice),
            "cudaMemcpy(lookup_a)");
        cuda_check(
            cudaMemcpy(
                device_lookup_b,
                lookup_b.data(),
                lookup_b.size() * sizeof(int),
                cudaMemcpyHostToDevice),
            "cudaMemcpy(lookup_b)");
        cuda_check(
            cudaMemcpyToSymbol(
                device_weight_matrices,
                weight_matrices.data(),
                weight_matrices.size() * sizeof(double)),
            "cudaMemcpyToSymbol(weights)");

        const dim3 grid(height / kBlockRows, width / kBaselineBlockColumns);
        convstencil_baseline_kernel<<<grid, 32 * kWarpCount>>>(
            device_input,
            device_output,
            columns,
            device_lookup_a,
            device_lookup_b);
        cuda_check(cudaGetLastError(), "convstencil_baseline_kernel launch");
        cuda_check(
            cudaDeviceSynchronize(), "convstencil_baseline_kernel synchronize");
        cuda_check(
            cudaMemcpy(
                output.data(), device_output, byte_count, cudaMemcpyDeviceToHost),
            "cudaMemcpy(output)");
    } catch (...) {
        cudaFree(device_input);
        cudaFree(device_output);
        cudaFree(device_lookup_a);
        cudaFree(device_lookup_b);
        throw;
    }

    cudaFree(device_input);
    cudaFree(device_output);
    cudaFree(device_lookup_a);
    cudaFree(device_lookup_b);

    double max_abs_error = 0.0;
    for (int row = kHalo; row < height + kHalo; ++row) {
        for (int column = kHalo + 1;
             column < width + kHalo + 1;
             ++column) {
            const double expected =
                cpu_reference_at(input, weights, row, column, columns);
            const double actual =
                output[static_cast<size_t>(row) * columns + column];
            max_abs_error =
                std::max(max_abs_error, std::abs(expected - actual));
        }
    }

    const bool correctness_pass = max_abs_error <= 1.0e-10;
    std::printf(
        "{\"kernel\":\"baseline\",\"height\":%d,\"width\":%d,"
        "\"correctness_pass\":%s,\"max_abs_error\":%.17g}\n",
        height,
        width,
        correctness_pass ? "true" : "false",
        max_abs_error);
    return correctness_pass ? 0 : 2;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 4 || std::string(argv[1]) != "baseline") {
        std::fprintf(stderr, "usage: benchmark baseline HEIGHT WIDTH\n");
        return 1;
    }

    try {
        return run_baseline_correctness(std::stoi(argv[2]), std::stoi(argv[3]));
    } catch (const std::exception& error) {
        std::fprintf(stderr, "%s\n", error.what());
        return 1;
    }
}
