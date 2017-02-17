
"""
SIMD friendly random number generation.

Currently uses only Philox4x64 which assumes 128-bit, but for GPU usage,
switch to a 32-bit. See include/Random123/index.html for details.

"""

import numpy as np
import ctypes
from tvb_hpc.compiler import CppCompiler
from tvb_hpc.utils import include_dir

rng_template = """
#include <Random123/philox.h>
#include <Random123/boxmuller.hpp>

extern "C" {

void tvb_rng(long long int seed, unsigned int nout,
             float * __restrict out) {

    out = (float *) __builtin_assume_aligned(out, 64);

    // TODO other variants might vectorize better?
    %(loop_pragma)s
    for(unsigned int i=0; i<(nout/4); ++i) {
        philox4x32_ctr_t ctr;
        philox4x32_key_t key;

        ctr.v[0] = seed + 4*i;
        ctr.v[1] = seed + 4*i + 1;
        ctr.v[2] = seed + 4*i + 2;
        ctr.v[3] = seed + 4*i + 3;

        philox4x32_ctr_t result = philox4x32(ctr, key);

        r123::float2 normal = r123::boxmuller(result.v[0], result.v[1]);
        out[i*4 + 0] = normal.x;
        out[i*4 + 1] = normal.y;

        r123::float2 normal2 = r123::boxmuller(result.v[2], result.v[3]);
        out[i*4 + 2] = normal2.x;
        out[i*4 + 3] = normal2.y;
    }
}

}

"""


class RNG:

    def __init__(self, comp=None):
        self.comp = comp or CppCompiler()  # type: Compiler

    def build(self, spec):
        self.comp.cflags += ['-I' + include_dir]
        loop_pragma = ''
        if spec.openmp:
            loop_pragma = '#pragma omp parallel for'
        code = rng_template % {
            'loop_pragma': loop_pragma,
        }
        self.dll = self.comp('rng', code)
        self.fn = self.dll.tvb_rng
        self.fn.restype = None
        self.fn.argtypes = [ctypes.c_longlong,
                            ctypes.c_uint,
                            ctypes.POINTER(ctypes.c_float)]

    def fill(self, array, seed=42):
        assert array.dtype == np.float32
        self.fn(
            self.fn.argtypes[0](seed),
            self.fn.argtypes[1](array.size),
            array.ctypes.data_as(self.fn.argtypes[2])
        )
