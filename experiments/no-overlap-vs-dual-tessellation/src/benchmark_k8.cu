// The dual-plane baseline and triangular weight construction are adapted from
// Microsoft ConvStencil src/2d/gpu.cu at commit
// 89688a1b51ec41b4a81028b0661363ba3afd6050. ConvStencil is distributed under
// the MIT License; see ../LICENSE.ConvStencil. This k=8 comparison harness is
// specific to the Issue #66 experiment.

#include <cuda_runtime.h>
#include <mma.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <exception>
#include <stdexcept>
#include <string>
#include <vector>

namespace wmma = nvcuda::wmma;

namespace {

constexpr int kBlockRows = 32;
constexpr int kBlockColumns = 64;
constexpr int kStencilLength = 8;
constexpr int kLeftHalo = 3;
constexpr int kDataRows = kBlockRows + kStencilLength - 1;
constexpr int kInputColumns = kBlockColumns + kStencilLength;
constexpr int kChunkElements = kStencilLength * kDataRows;
constexpr int kBaselineGroupCount = 8;
constexpr int kBaselinePlaneElements = kBaselineGroupCount * kChunkElements;
constexpr int kNoOverlapChunkCount = 9;
constexpr int kNoOverlapElements = kNoOverlapChunkCount * kChunkElements;
constexpr int kWarpCount = 8;
constexpr int kMmaCount = 16;
constexpr int kWeightRows = 64;
constexpr int kTensorDimension = 8;

static_assert(kInputColumns == kNoOverlapChunkCount * kStencilLength);
static_assert(kBaselinePlaneElements == 2496);
static_assert(kNoOverlapElements == 2808);
static_assert(kChunkElements % 4 == 0);

__constant__ double device_weight_matrices[2 * kWeightRows * kTensorDimension];

void cuda_check(cudaError_t status, const char* operation) {
    if (status != cudaSuccess) {
        throw std::runtime_error(std::string(operation) + ": " +
                                 cudaGetErrorString(status));
    }
}

__global__ void k8_convstencil_baseline_kernel(
    const double* __restrict__ input,
    double* __restrict__ output,
    int leading_dimension) {
    __shared__ __align__(32) double shared_memory[2][kBaselinePlaneElements];
    const int begin =
        (blockIdx.x * kBlockRows) * leading_dimension +
        blockIdx.y * kBlockColumns + 1;
    const int thread_id = threadIdx.x;

    for (int index = thread_id;
         index < kDataRows * kInputColumns;
         index += blockDim.x) {
        const int row = index / kInputColumns;
        const int column = index % kInputColumns;
        const double value =
            input[begin + row * leading_dimension + column];
        if (column < kBlockColumns) {
            const int shared_index =
                (column / kStencilLength) * kChunkElements +
                kStencilLength * row + column % kStencilLength;
            shared_memory[0][shared_index] = value;
        }
        if (column >= kStencilLength) {
            const int shifted_column = column - kStencilLength;
            const int shared_index =
                (shifted_column / kStencilLength) * kChunkElements +
                kStencilLength * row + shifted_column % kStencilLength;
            shared_memory[1][shared_index] = value;
        }
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
            kTensorDimension);
        wmma::load_matrix_sync(
            weight_fragments[1][index],
            device_weight_matrices +
                kWeightRows * kTensorDimension + index * 32,
            kTensorDimension);
    }

    wmma::fragment<wmma::accumulator, 8, 8, 4, double> accumulator;
    wmma::fragment<wmma::matrix_a, 8, 8, 4, double, wmma::row_major>
        input_fragment;
    for (int column = warp_id * 32;
         column < warp_id * 32 + 32;
         column += kStencilLength) {
        wmma::fill_fragment(accumulator, 0.0);
#pragma unroll
        for (int compute_index = 0; compute_index < kMmaCount; ++compute_index) {
            wmma::load_matrix_sync(
                input_fragment,
                shared_memory[0] + column + compute_index * 4,
                kChunkElements);
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
                kChunkElements);
            wmma::mma_sync(
                accumulator,
                input_fragment,
                weight_fragments[1][compute_index],
                accumulator);
        }
        wmma::store_matrix_sync(
            output + begin +
                (kLeftHalo + column / kStencilLength) * leading_dimension +
                kLeftHalo,
            accumulator,
            kTensorDimension,
            wmma::mem_row_major);
    }
}

__global__ void k8_no_overlap_kernel(
    const double* __restrict__ input,
    double* __restrict__ output,
    int leading_dimension) {
    __shared__ __align__(32) double shared_input[kNoOverlapElements];
    const int begin =
        (blockIdx.x * kBlockRows) * leading_dimension +
        blockIdx.y * kBlockColumns + 1;
    const int thread_id = threadIdx.x;

    for (int index = thread_id;
         index < kDataRows * kInputColumns;
         index += blockDim.x) {
        const int row = index / kInputColumns;
        const int column = index % kInputColumns;
        const int shared_index =
            (column / kStencilLength) * kChunkElements +
            kStencilLength * row + column % kStencilLength;
        shared_input[shared_index] =
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
            kTensorDimension);
        wmma::load_matrix_sync(
            weight_fragments[1][index],
            device_weight_matrices +
                kWeightRows * kTensorDimension + index * 32,
            kTensorDimension);
    }

    wmma::fragment<wmma::accumulator, 8, 8, 4, double> accumulator;
    wmma::fragment<wmma::matrix_a, 8, 8, 4, double, wmma::row_major>
        input_fragment;
    for (int column = warp_id * 32;
         column < warp_id * 32 + 32;
         column += kStencilLength) {
        wmma::fill_fragment(accumulator, 0.0);
#pragma unroll
        for (int compute_index = 0; compute_index < kMmaCount; ++compute_index) {
            wmma::load_matrix_sync(
                input_fragment,
                shared_input + column + compute_index * 4,
                kChunkElements);
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
                shared_input +
                    kChunkElements + column + compute_index * 4,
                kChunkElements);
            wmma::mma_sync(
                accumulator,
                input_fragment,
                weight_fragments[1][compute_index],
                accumulator);
        }
        wmma::store_matrix_sync(
            output + begin +
                (kLeftHalo + column / kStencilLength) * leading_dimension +
                kLeftHalo,
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
    std::vector<double> weights(kStencilLength * kStencilLength);
    for (int index = 0; index < static_cast<int>(weights.size()); ++index) {
        const int value = (index * 11 + 5) % 23;
        weights[index] = static_cast<double>(value - 11) / 31.0;
    }
    return weights;
}

std::vector<double> make_weight_matrices(const std::vector<double>& weights) {
    std::vector<double> matrices(
        2 * kWeightRows * kTensorDimension,
        0.0);
    for (int output_column = 0;
         output_column < kTensorDimension;
         ++output_column) {
        for (int row = 0; row < kStencilLength; ++row) {
            for (int inner = 0; inner < kStencilLength; ++inner) {
                const int matrix_row = row * kStencilLength + inner;
                if (inner >= output_column) {
                    matrices[matrix_row * kTensorDimension + output_column] =
                        weights[row * kStencilLength + inner - output_column];
                } else {
                    matrices[kWeightRows * kTensorDimension +
                             matrix_row * kTensorDimension + output_column] =
                        weights[row * kStencilLength + inner - output_column +
                                kStencilLength];
                }
            }
        }
    }
    return matrices;
}

double cpu_reference_at(const std::vector<double>& input,
                        const std::vector<double>& weights,
                        int output_row,
                        int output_column,
                        int leading_dimension) {
    double result = 0.0;
    for (int kernel_row = 0; kernel_row < kStencilLength; ++kernel_row) {
        for (int kernel_column = 0;
             kernel_column < kStencilLength;
             ++kernel_column) {
            result +=
                input[static_cast<size_t>(output_row - kLeftHalo + kernel_row) *
                          leading_dimension +
                      output_column - kLeftHalo + kernel_column] *
                weights[kernel_row * kStencilLength + kernel_column];
        }
    }
    return result;
}

void launch_kernel(const std::string& kernel,
                   int height,
                   int width,
                   int leading_dimension,
                   const double* device_input,
                   double* device_output) {
    const dim3 block(32 * kWarpCount);
    const dim3 grid(height / kBlockRows, width / kBlockColumns);
    if (kernel == "baseline") {
        k8_convstencil_baseline_kernel<<<grid, block>>>(
            device_input, device_output, leading_dimension);
    } else if (kernel == "no-overlap") {
        k8_no_overlap_kernel<<<grid, block>>>(
            device_input, device_output, leading_dimension);
    } else {
        throw std::invalid_argument("unknown k=8 kernel");
    }
}

float time_kernel(const std::string& kernel,
                  int repetitions,
                  int height,
                  int width,
                  int leading_dimension,
                  const double* device_input,
                  double* device_output) {
    cudaEvent_t start = nullptr;
    cudaEvent_t stop = nullptr;
    cuda_check(cudaEventCreate(&start), "cudaEventCreate(start)");
    cuda_check(cudaEventCreate(&stop), "cudaEventCreate(stop)");
    cuda_check(cudaEventRecord(start), "cudaEventRecord(start)");
    for (int repetition = 0; repetition < repetitions; ++repetition) {
        launch_kernel(
            kernel,
            height,
            width,
            leading_dimension,
            device_input,
            device_output);
    }
    cuda_check(cudaGetLastError(), "timed kernel launch");
    cuda_check(cudaEventRecord(stop), "cudaEventRecord(stop)");
    cuda_check(cudaEventSynchronize(stop), "cudaEventSynchronize(stop)");
    float elapsed_ms = 0.0F;
    cuda_check(
        cudaEventElapsedTime(&elapsed_ms, start, stop),
        "cudaEventElapsedTime");
    cudaEventDestroy(start);
    cudaEventDestroy(stop);
    return elapsed_ms;
}

int calibrated_repetitions(float single_launch_ms) {
    constexpr double kTargetSampleMs = 150.0;
    if (!(single_launch_ms > 0.0F)) {
        throw std::runtime_error("kernel calibration returned non-positive time");
    }
    return std::clamp(
        static_cast<int>(std::lround(kTargetSampleMs / single_launch_ms)),
        1,
        1000000);
}

struct DeviceBuffers {
    double* input = nullptr;
    double* output = nullptr;

    DeviceBuffers() = default;
    DeviceBuffers(const DeviceBuffers&) = delete;
    DeviceBuffers& operator=(const DeviceBuffers&) = delete;
    DeviceBuffers(DeviceBuffers&& other) noexcept
        : input(other.input), output(other.output) {
        other.input = nullptr;
        other.output = nullptr;
    }

    ~DeviceBuffers() {
        cudaFree(input);
        cudaFree(output);
    }
};

DeviceBuffers allocate_and_upload(const std::vector<double>& input,
                                  const std::vector<double>& weight_matrices) {
    DeviceBuffers buffers;
    const size_t byte_count = input.size() * sizeof(double);
    cuda_check(cudaMalloc(&buffers.input, byte_count), "cudaMalloc(input)");
    cuda_check(cudaMalloc(&buffers.output, byte_count), "cudaMalloc(output)");
    cuda_check(
        cudaMemcpy(
            buffers.input,
            input.data(),
            byte_count,
            cudaMemcpyHostToDevice),
        "cudaMemcpy(input)");
    cuda_check(cudaMemset(buffers.output, 0, byte_count), "cudaMemset(output)");
    cuda_check(
        cudaMemcpyToSymbol(
            device_weight_matrices,
            weight_matrices.data(),
            weight_matrices.size() * sizeof(double)),
        "cudaMemcpyToSymbol(weights)");
    return buffers;
}

void validate_dimensions(int height, int width) {
    if (height <= 0 || width <= 0 || height % kBlockRows != 0 ||
        width % kBlockColumns != 0) {
        throw std::invalid_argument(
            "dimensions must tile complete 32x64 output blocks");
    }
}

int run_correctness(const std::string& kernel, int height, int width) {
    validate_dimensions(height, width);
    const int rows = height + kStencilLength - 1;
    const int columns = width + kStencilLength + 1;
    const std::vector<double> input = make_input(rows, columns);
    const std::vector<double> weights = make_weights();
    const std::vector<double> weight_matrices = make_weight_matrices(weights);
    DeviceBuffers buffers = allocate_and_upload(input, weight_matrices);

    launch_kernel(
        kernel,
        height,
        width,
        columns,
        buffers.input,
        buffers.output);
    cuda_check(cudaGetLastError(), "correctness kernel launch");
    cuda_check(cudaDeviceSynchronize(), "correctness kernel synchronize");

    std::vector<double> output(input.size(), 0.0);
    cuda_check(
        cudaMemcpy(
            output.data(),
            buffers.output,
            output.size() * sizeof(double),
            cudaMemcpyDeviceToHost),
        "cudaMemcpy(output)");

    double max_abs_error = 0.0;
    for (int row = kLeftHalo; row < height + kLeftHalo; ++row) {
        for (int column = kLeftHalo + 1;
             column < width + kLeftHalo + 1;
             ++column) {
            const double expected =
                cpu_reference_at(input, weights, row, column, columns);
            const double actual =
                output[static_cast<size_t>(row) * columns + column];
            max_abs_error =
                std::max(max_abs_error, std::abs(expected - actual));
        }
    }
    const bool pass = max_abs_error <= 1.0e-10;
    std::printf(
        "{\"kernel\":\"%s\",\"height\":%d,\"width\":%d,"
        "\"correctness_pass\":%s,\"max_abs_error\":%.17g}\n",
        kernel.c_str(),
        height,
        width,
        pass ? "true" : "false",
        max_abs_error);
    return pass ? 0 : 2;
}

int run_resources() {
    cudaDeviceProp properties{};
    cuda_check(cudaGetDeviceProperties(&properties, 0), "cudaGetDeviceProperties");
    cudaFuncAttributes baseline{};
    cudaFuncAttributes no_overlap{};
    cuda_check(
        cudaFuncGetAttributes(&baseline, k8_convstencil_baseline_kernel),
        "cudaFuncGetAttributes(k8 baseline)");
    cuda_check(
        cudaFuncGetAttributes(&no_overlap, k8_no_overlap_kernel),
        "cudaFuncGetAttributes(k8 no-overlap)");
    int baseline_blocks = 0;
    int no_overlap_blocks = 0;
    cuda_check(
        cudaOccupancyMaxActiveBlocksPerMultiprocessor(
            &baseline_blocks,
            k8_convstencil_baseline_kernel,
            32 * kWarpCount,
            0),
        "cudaOccupancyMaxActiveBlocksPerMultiprocessor(k8 baseline)");
    cuda_check(
        cudaOccupancyMaxActiveBlocksPerMultiprocessor(
            &no_overlap_blocks,
            k8_no_overlap_kernel,
            32 * kWarpCount,
            0),
        "cudaOccupancyMaxActiveBlocksPerMultiprocessor(k8 no-overlap)");
    std::printf(
        "{\"device\":{\"name\":\"%s\",\"compute_capability\":\"%d.%d\"},"
        "\"kernels\":{"
        "\"k8_baseline\":{\"registers_per_thread\":%d,"
        "\"static_shared_bytes\":%zu,\"active_blocks_per_sm\":%d},"
        "\"k8_no_overlap\":{\"registers_per_thread\":%d,"
        "\"static_shared_bytes\":%zu,\"active_blocks_per_sm\":%d}}}\n",
        properties.name,
        properties.major,
        properties.minor,
        baseline.numRegs,
        baseline.sharedSizeBytes,
        baseline_blocks,
        no_overlap.numRegs,
        no_overlap.sharedSizeBytes,
        no_overlap_blocks);
    return 0;
}

int run_measurement(int height, int width) {
    constexpr int kWarmupCount = 5;
    constexpr int kPairCount = 21;
    validate_dimensions(height, width);
    const int rows = height + kStencilLength - 1;
    const int columns = width + kStencilLength + 1;
    const std::vector<double> input = make_input(rows, columns);
    const std::vector<double> weights = make_weights();
    const std::vector<double> weight_matrices = make_weight_matrices(weights);
    DeviceBuffers buffers = allocate_and_upload(input, weight_matrices);

    for (int warmup = 0; warmup < kWarmupCount; ++warmup) {
        launch_kernel(
            "baseline", height, width, columns, buffers.input, buffers.output);
        launch_kernel(
            "no-overlap", height, width, columns, buffers.input, buffers.output);
    }
    cuda_check(cudaGetLastError(), "warmup kernel launch");
    cuda_check(cudaDeviceSynchronize(), "warmup synchronize");

    const float baseline_calibration = time_kernel(
        "baseline", 1, height, width, columns, buffers.input, buffers.output);
    const float no_overlap_calibration = time_kernel(
        "no-overlap", 1, height, width, columns, buffers.input, buffers.output);
    const int baseline_repetitions =
        calibrated_repetitions(baseline_calibration);
    const int no_overlap_repetitions =
        calibrated_repetitions(no_overlap_calibration);

    std::vector<float> baseline_times(kPairCount);
    std::vector<float> no_overlap_times(kPairCount);
    for (int pair = 0; pair < kPairCount; ++pair) {
        const auto measure = [&](const char* kernel, int repetitions) {
            return time_kernel(
                kernel,
                repetitions,
                height,
                width,
                columns,
                buffers.input,
                buffers.output);
        };
        if (pair % 2 == 0) {
            baseline_times[pair] = measure("baseline", baseline_repetitions);
            no_overlap_times[pair] =
                measure("no-overlap", no_overlap_repetitions);
        } else {
            no_overlap_times[pair] =
                measure("no-overlap", no_overlap_repetitions);
            baseline_times[pair] = measure("baseline", baseline_repetitions);
        }
    }

    std::printf(
        "{\"height\":%d,\"width\":%d,\"blocks_per_kernel\":%d,"
        "\"warmups\":%d,\"pairs\":%d,"
        "\"baseline_calibration_ms\":%.9g,"
        "\"no_overlap_calibration_ms\":%.9g,"
        "\"baseline_repetitions\":%d,"
        "\"no_overlap_repetitions\":%d,\"samples\":[",
        height,
        width,
        (height / kBlockRows) * (width / kBlockColumns),
        kWarmupCount,
        kPairCount,
        baseline_calibration,
        no_overlap_calibration,
        baseline_repetitions,
        no_overlap_repetitions);
    for (int pair = 0; pair < kPairCount; ++pair) {
        std::printf(
            "%s{\"pair\":%d,\"order\":\"%s\","
            "\"baseline_total_ms\":%.9g,"
            "\"no_overlap_total_ms\":%.9g}",
            pair == 0 ? "" : ",",
            pair,
            pair % 2 == 0 ? "AB" : "BA",
            baseline_times[pair],
            no_overlap_times[pair]);
    }
    std::printf("]}\n");
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "resources") {
            return run_resources();
        }
        if (argc != 4) {
            std::fprintf(
                stderr,
                "usage: benchmark_k8 resources | "
                "benchmark_k8 {baseline|no-overlap|measure} HEIGHT WIDTH\n");
            return 1;
        }
        const std::string command = argv[1];
        const int height = std::stoi(argv[2]);
        const int width = std::stoi(argv[3]);
        if (command == "measure") {
            return run_measurement(height, width);
        }
        if (command == "baseline" || command == "no-overlap") {
            return run_correctness(command, height, width);
        }
        throw std::invalid_argument("unknown command");
    } catch (const std::exception& error) {
        std::fprintf(stderr, "%s\n", error.what());
        return 1;
    }
}
