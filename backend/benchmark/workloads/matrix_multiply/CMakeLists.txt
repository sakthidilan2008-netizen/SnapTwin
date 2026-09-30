cmake_minimum_required(VERSION 3.20)
project(matrix_multiply LANGUAGES CXX)

# Release build optimization flags
set(CMAKE_CXX_FLAGS_RELEASE "/O2 /Ob2 /GL" CACHE STRING "Release flags" FORCE)
set(CMAKE_EXE_LINKER_FLAGS_RELEASE "/LTCG" CACHE STRING "Release linker flags" FORCE)

# Scalar version
add_executable(matrix_multiply main.cpp)
set_target_properties(matrix_multiply PROPERTIES 
    CXX_STANDARD 17 
    CXX_STANDARD_REQUIRED ON
)

# NEON version (ARM64 with NEON intrinsics)
add_executable(matrix_multiply_neon main_neon.cpp)
set_target_properties(matrix_multiply_neon PROPERTIES 
    CXX_STANDARD 17 
    CXX_STANDARD_REQUIRED ON
)
# Enable ARM64 NEON intrinsics
if(MSVC)
    target_compile_options(matrix_multiply_neon PRIVATE /arch:ARM64)
else()
    target_compile_options(matrix_multiply_neon PRIVATE -march=armv8-a)
endif()
