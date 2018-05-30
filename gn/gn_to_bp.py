#!/usr/bin/env python
#
# Copyright 2016 Google Inc.
#
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Generate Android.bp for Skia from GN configuration.

import json
import os
import pprint
import string
import subprocess
import tempfile

import gn_to_bp_utils

# First we start off with a template for Android.bp,
# with holes for source lists and include directories.
bp = string.Template('''// This file is autogenerated by gn_to_bp.py.

cc_library_static {
    name: "libskia",
    cflags: [
        $cflags
    ],

    cppflags:[
        $cflags_cc
    ],

    export_include_dirs: [
        $export_includes
    ],

    local_include_dirs: [
        $local_includes
    ],

    srcs: [
        $srcs
    ],

    arch: {
        arm: {
            srcs: [
                $arm_srcs
            ],

            neon: {
                srcs: [
                    $arm_neon_srcs
                ],
            },
        },

        arm64: {
            srcs: [
                $arm64_srcs
            ],
        },

        mips: {
            srcs: [
                $none_srcs
            ],
        },

        mips64: {
            srcs: [
                $none_srcs
            ],
        },

        x86: {
            srcs: [
                $x86_srcs
            ],
            cflags: [
                // Clang seems to think new/malloc will only be 4-byte aligned
                // on x86 Android. We're pretty sure it's actually 8-byte
                // alignment. tests/OverAlignedTest.cpp has more information,
                // and should fail if we're wrong.
                "-Wno-over-aligned"
            ],
        },

        x86_64: {
            srcs: [
                $x86_srcs
            ],
        },
    },

    defaults: ["skia_deps",
               "skia_pgo",
    ],
}

// Build libskia with PGO by default.
// Location of PGO profile data is defined in build/soong/cc/pgo.go
// and is separate from skia.
// To turn it off, set ANDROID_PGO_NO_PROFILE_USE environment variable
// or set enable_profile_use property to false.
cc_defaults {
    name: "skia_pgo",
    pgo: {
        instrumentation: true,
        profile_file: "hwui/hwui.profdata",
        benchmarks: ["hwui", "skia"],
        enable_profile_use: true,
    },
}

// "defaults" property to disable profile use for Skia tools and benchmarks.
cc_defaults {
    name: "skia_pgo_no_profile_use",
    defaults: [
        "skia_pgo",
    ],
    pgo: {
        enable_profile_use: false,
    },
}

cc_defaults {
    name: "skia_deps",
    shared_libs: [
        "libEGL",
        "libGLESv2",
        "libdng_sdk",
        "libexpat",
        "libft2",
        "libheif",
        "libicui18n",
        "libicuuc",
        "libjpeg",
        "liblog",
        "libpiex",
        "libpng",
        "libvulkan",
        "libz",
        "libcutils",
        "libnativewindow",
    ],
    static_libs: [
        "libarect",
        "libsfntly",
        "libwebp-decode",
        "libwebp-encode",
    ],
    group_static_libs: true,
}

cc_defaults {
    name: "skia_tool_deps",
    defaults: [
        "skia_deps",
        "skia_pgo_no_profile_use"
    ],
    static_libs: [
        "libjsoncpp",
        "libskia",
    ],
    cflags: [
        "-Wno-unused-parameter",
        "-Wno-unused-variable",
    ],
}

cc_test {
    name: "skia_dm",

    defaults: [
        "skia_tool_deps"
    ],

    local_include_dirs: [
        $dm_includes
    ],

    srcs: [
        $dm_srcs
    ],

    shared_libs: [
        "libbinder",
        "libutils",
    ],
}

cc_test {
    name: "skia_nanobench",

    defaults: [
        "skia_tool_deps"
    ],

    local_include_dirs: [
        $nanobench_includes
    ],

    srcs: [
        $nanobench_srcs
    ],

    data: [
        "resources/*",
    ],
}''')

# We'll run GN to get the main source lists and include directories for Skia.
gn_args = {
  'is_official_build':   'true',
  'skia_enable_tools':   'true',
  'skia_enable_skottie': 'false', # requires rapidjson third-party
  'skia_use_libheif':    'true',
  'skia_use_vulkan':     'true',
  'target_cpu':          '"none"',
  'target_os':           '"android"',
  'skia_vulkan_header':  '"Skia_Vulkan_Android.h"',
}

js = gn_to_bp_utils.GenerateJSONFromGN(gn_args)

def strip_slashes(lst):
  return {str(p.lstrip('/')) for p in lst}

srcs            = strip_slashes(js['targets']['//:skia']['sources'])
cflags          = strip_slashes(js['targets']['//:skia']['cflags'])
cflags_cc       = strip_slashes(js['targets']['//:skia']['cflags_cc'])
local_includes  = strip_slashes(js['targets']['//:skia']['include_dirs'])
export_includes = strip_slashes(js['targets']['//:public']['include_dirs'])
defines      = [str(d) for d in js['targets']['//:skia']['defines']]

dm_srcs         = strip_slashes(js['targets']['//:dm']['sources'])
dm_includes     = strip_slashes(js['targets']['//:dm']['include_dirs'])

nanobench_target = js['targets']['//:nanobench']
nanobench_srcs     = strip_slashes(nanobench_target['sources'])
nanobench_includes = strip_slashes(nanobench_target['include_dirs'])

gn_to_bp_utils.GrabDependentValues(js, '//:skia', 'sources', srcs, None)
gn_to_bp_utils.GrabDependentValues(js, '//:dm', 'sources', dm_srcs, 'skia')
gn_to_bp_utils.GrabDependentValues(js, '//:nanobench', 'sources',
                                   nanobench_srcs, 'skia')

# skcms is a little special, kind of a second-party library.
srcs          .add("third_party/skcms/skcms.c")
local_includes.add("third_party/skcms")
dm_includes   .add("third_party/skcms")

# need to manually include the vulkanmemoryallocator headers. If HWUI ever needs
# direct access to the allocator we need to add it to export_includes as well.
srcs.add("third_party/vulkanmemoryallocator/GrVulkanMemoryAllocator.cpp")
local_includes.add("third_party/vulkanmemoryallocator/")

# No need to list headers.
srcs            = {s for s in srcs           if not s.endswith('.h')}
dm_srcs         = {s for s in dm_srcs        if not s.endswith('.h')}
nanobench_srcs  = {s for s in nanobench_srcs if not s.endswith('.h')}

cflags = gn_to_bp_utils.CleanupCFlags(cflags)
cflags_cc = gn_to_bp_utils.CleanupCCFlags(cflags_cc)

# We need to add the include path to the vulkan defines and header file set in
# then skia_vulkan_header gn arg that is used for framework builds.
local_includes.add("platform_tools/android/vulkan")
export_includes.add("platform_tools/android/vulkan")

here = os.path.dirname(__file__)
defs = gn_to_bp_utils.GetArchSources(os.path.join(here, 'opts.gni'))

gn_to_bp_utils.WriteUserConfig('include/config/SkUserConfig.h', defines)

# Turn a list of strings into the style bpfmt outputs.
def bpfmt(indent, lst, sort=True):
  if sort:
    lst = sorted(lst)
  return ('\n' + ' '*indent).join('"%s",' % v for v in lst)

# OK!  We have everything to fill in Android.bp...
with open('Android.bp', 'w') as f:
  print >>f, bp.substitute({
    'export_includes': bpfmt(8, export_includes),
    'local_includes':  bpfmt(8, local_includes),
    'srcs':            bpfmt(8, srcs),
    'cflags':          bpfmt(8, cflags, False),
    'cflags_cc':       bpfmt(8, cflags_cc),

    'arm_srcs':      bpfmt(16, defs['armv7']),
    'arm_neon_srcs': bpfmt(20, defs['neon']),
    'arm64_srcs':    bpfmt(16, defs['arm64'] +
                               defs['crc32']),
    'none_srcs':     bpfmt(16, defs['none']),
    'x86_srcs':      bpfmt(16, defs['sse2'] +
                               defs['ssse3'] +
                               defs['sse41'] +
                               defs['sse42'] +
                               defs['avx'  ] +
                               defs['hsw'  ]),

    'dm_includes'       : bpfmt(8, dm_includes),
    'dm_srcs'           : bpfmt(8, dm_srcs),

    'nanobench_includes'    : bpfmt(8, nanobench_includes),
    'nanobench_srcs'        : bpfmt(8, nanobench_srcs),
  })
