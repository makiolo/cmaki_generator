#!/bin/bash

source $(pwd)/find.script
source $(pwd)/../toolchain/find.script

# need use zlib from toolchain
export PKG_CONFIG_PATH=$toolchain_BASE/lib/pkgconfig

./configure --prefix=$haxx_libcurl_HOME --without-ssl && make -j $CORES && make -j $CORES install

